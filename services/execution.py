"""
ZMN Bot Execution Layer
========================
Two execution paths — no Telegram dependency anywhere:
  1. PumpPortal Local API (bonding curve tokens) — POST https://pumpportal.fun/api/trade-local
  2. Jupiter Swap V2 API (graduated/AMM tokens) — https://api.jup.ag/swap/v2/

Features:
- choose_execution_api() routing
- Jito MEV protection for PumpPortal trades (Jupiter has built-in MEV protection)
- Retry logic: 5 attempts, 500ms initial, 1.5x backoff, escalate fee tier on each retry
- TEST_MODE=true: build and log transaction details, do NOT sign or send
"""

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum

import aiohttp
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("execution")

TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_STAKED_URL = os.getenv("HELIUS_STAKED_URL", "")
HELIUS_PARSE_TX_URL = os.getenv("HELIUS_PARSE_TX_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")
TRADING_WALLET_PRIVATE_KEY = os.getenv("TRADING_WALLET_PRIVATE_KEY", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "").strip()

if not TEST_MODE:
    _helius_urls = [u for u in (HELIUS_STAKED_URL, HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL) if u]
    if not _helius_urls:
        raise RuntimeError(
            "execution.py: TEST_MODE=false but no Helius URL configured. "
            "Set at least one of HELIUS_STAKED_URL / HELIUS_RPC_URL / HELIUS_GATEKEEPER_URL. "
            "Refusing to start — would produce silent sell-storm errors."
        )
    logger.info("execution.py: live mode OK, %d Helius URL(s) configured", len(_helius_urls))

# --- Endpoints ---
PUMPPORTAL_TRADE_URL = "https://pumpportal.fun/api/trade-local"
JUPITER_ORDER_URL = "https://api.jup.ag/swap/v2/order"
JUPITER_EXECUTE_URL = "https://api.jup.ag/swap/v2/execute"
PUMPPORTAL_LOCAL_URL = "https://pumpportal.fun/api/trade-local"
GRADUATION_THRESHOLD = 0.95
JITO_ENDPOINT = os.getenv("JITO_ENDPOINT", "https://mainnet.block-engine.jito.wtf/api/v1/bundles")
JITO_DONTFRONT_PUBKEY = "jitodontfront111111111111111111111111111111"

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000

# --- Live execution logging (writes to live_trade_log Postgres table) ---
_live_log_pool = None

def set_live_log_pool(pool):
    """bot_core calls this at startup to wire in DB pool for live logging."""
    global _live_log_pool
    _live_log_pool = pool

async def live_execution_log(event_type, trade_id=None, mint=None, signature=None,
                              bundle_id=None, action=None, size_sol=None,
                              expected_price=None, actual_price=None,
                              jito_tip_lamports=None, priority_fee_lamports=None,
                              rpc_url_hint=None, error_msg=None, extra=None):
    """Log a live execution event. Non-fatal. Skipped in TEST_MODE."""
    if TEST_MODE:
        return
    ts_ms = int(time.time() * 1000)
    slippage_pct = None
    if expected_price and actual_price and expected_price > 0:
        slippage_pct = ((actual_price - expected_price) / expected_price) * 100
    logger.info("LIVE_EVENT %s trade_id=%s mint=%s sig=%s action=%s size=%s slip=%s tip=%s",
                event_type, trade_id, (mint or "")[:12], (signature or "")[:16],
                action, size_sol, f"{slippage_pct:.2f}%" if slippage_pct else "n/a",
                jito_tip_lamports)
    if _live_log_pool is None:
        return
    try:
        raw = dict(extra or {})
        if error_msg:
            raw["error_msg"] = error_msg
        await _live_log_pool.execute(
            """INSERT INTO live_trade_log (trade_id, event_type, ts_ms, mint, signature,
               bundle_id, action, size_sol, expected_price, actual_price, slippage_pct,
               jito_tip_lamports, priority_fee_lamports, rpc_url_hint, error_msg, raw_payload)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb)""",
            trade_id, event_type, ts_ms, mint, signature, bundle_id,
            action, size_sol, expected_price, actual_price, slippage_pct,
            jito_tip_lamports, priority_fee_lamports, rpc_url_hint,
            error_msg, json.dumps(raw) if raw else None)
    except Exception as e:
        logger.warning("live_execution_log DB write failed (non-fatal): %s", e)

# --- Slippage configs (from AGENT_CONTEXT Section 5) ---
PUMPPORTAL_SLIPPAGE = {
    "alpha_snipe": 25,
    "confirmation": 15,
    "post_grad_dip": 10,
    "sell": 10,
}

JUPITER_SLIPPAGE_BPS = {
    "graduated_deep": 50,       # 0.5% — pools >$1M liquidity
    "graduated_medium": 150,    # 1.5% — pools $100K-$1M
    "graduated_shallow": 350,   # 3.5% — pools <$100K
}

# --- Env var helpers ---
def _env_int(name: str, default: int) -> int:
    try:
        val = os.environ.get(name, "")
        return int(val) if val else default
    except (ValueError, TypeError):
        return default

def _env_float(name: str, default: float) -> float:
    try:
        val = os.environ.get(name, "")
        return float(val) if val else default
    except (ValueError, TypeError):
        return default

# --- Jito tip tiers (env-var overridable, defaults from AGENT_CONTEXT Section 5) ---
JITO_TIPS_LAMPORTS = {
    "normal": _env_int("JITO_TIP_LAMPORTS_NORMAL", 1_000_000),
    "competitive": _env_int("JITO_TIP_LAMPORTS_COMPETITIVE", 10_000_000),
    "frenzy_snipe": _env_int("JITO_TIP_LAMPORTS_FRENZY", 100_000_000),
}

# --- Retry config ---
RETRY_CONFIG = {
    "max_retries": 5,
    "initial_delay_ms": 500,
    "backoff_factor": 1.5,
    "escalate_fee": True,
    "preflight": True,
    "commitment": "confirmed",
    "encoding": "base64",
}

# --- Priority fee tiers (env-var overridable, for retry escalation) ---
PRIORITY_FEE_TIERS = [
    _env_float("PRIORITY_FEE_TIER_1_SOL", 0.0001),
    _env_float("PRIORITY_FEE_TIER_2_SOL", 0.0005),
    _env_float("PRIORITY_FEE_TIER_3_SOL", 0.001),
    _env_float("PRIORITY_FEE_TIER_4_SOL", 0.005),
    _env_float("PRIORITY_FEE_TIER_5_SOL", 0.01),
]

logger.info("EXECUTION_CONFIG jito_tips_lamports=%s priority_fee_tiers=%s",
            JITO_TIPS_LAMPORTS, PRIORITY_FEE_TIERS)


class ExecutionError(Exception):
    pass


class ExecutionAPI(str, Enum):
    PUMPPORTAL = "pumpportal"
    JUPITER = "jupiter"


@dataclass
class Token:
    mint: str
    pool: str = "auto"
    bonding_curve_progress: float = 0.0
    liquidity_usd: float = 0.0


@dataclass
class ExecutionResult:
    success: bool
    signature: str | None = None
    api_used: str = ""
    attempts: int = 0
    error: str | None = None
    simulated: bool = False


def choose_execution_api(token: Token) -> ExecutionAPI:
    """Route to correct API based on token state (AGENT_CONTEXT Section 5)."""
    PUMPPORTAL_POOLS = {"pump", "pump-amm", "launchlab", "bonk"}
    JUPITER_POOLS = {"raydium", "raydium-cpmm", "orca", "meteora", "pumpswap"}

    if token.pool in PUMPPORTAL_POOLS and token.bonding_curve_progress < 1.0:
        return ExecutionAPI.PUMPPORTAL
    elif token.pool in JUPITER_POOLS:
        return ExecutionAPI.JUPITER
    else:
        return ExecutionAPI.PUMPPORTAL  # Default to PumpPortal with pool="auto"


def _get_jupiter_slippage(liquidity_usd: float) -> int:
    if liquidity_usd > 1_000_000:
        return JUPITER_SLIPPAGE_BPS["graduated_deep"]
    elif liquidity_usd > 100_000:
        return JUPITER_SLIPPAGE_BPS["graduated_medium"]
    else:
        return JUPITER_SLIPPAGE_BPS["graduated_shallow"]


async def _get_dynamic_priority_fee(session: aiohttp.ClientSession) -> int:
    """Get dynamic priority fee from Helius in microlamports."""
    if not HELIUS_RPC_URL:
        return 100_000  # 0.0001 SOL default
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getPriorityFeeEstimate",
        "params": [{"options": {"priorityLevel": "High"}}],
    }
    for rpc_url in (HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
        if not rpc_url:
            continue
        try:
            async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
                fee = result.get("result", {}).get("priorityFeeEstimate", 100_000)
                return int(fee)
        except Exception:
            continue
    return 100_000


# ---------------------------------------------------------------------------
# PumpPortal Local API
# ---------------------------------------------------------------------------
async def _execute_pumpportal(
    session: aiohttp.ClientSession,
    action: str,
    mint: str,
    amount_sol: float,
    slippage_pct: int,
    priority_fee_sol: float,
    pool: str = "auto",
    use_jito: bool = True,
    skip_preflight: bool = False,
) -> str:
    """Execute trade via PumpPortal Local API. Returns tx signature."""

    payload = {
        "publicKey": TRADING_WALLET_ADDRESS,
        "action": action,
        "mint": mint,
        "amount": amount_sol,
        "denominatedInSol": "true",
        "slippage": slippage_pct,
        "priorityFee": priority_fee_sol,
        "pool": pool,
    }

    if TEST_MODE:
        logger.info("TEST_MODE PumpPortal %s: %s %.4f SOL (slippage=%d%%, fee=%.6f SOL, pool=%s, jito=%s)",
                     action, mint, amount_sol, slippage_pct, priority_fee_sol, pool, use_jito)
        return "TEST_MODE_SIMULATED_TX"

    async with session.post(PUMPPORTAL_TRADE_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"PumpPortal HTTP {resp.status}: {body[:2048]}")
        tx_bytes = await resp.read()

    # Sign with trading wallet keypair
    from solders.transaction import VersionedTransaction
    from solders.keypair import Keypair

    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    signed_tx = VersionedTransaction(tx.message, [keypair])

    # Send via Jito bundle for MEV protection (Jupiter has built-in MEV — no Jito needed)
    signed_bytes = bytes(signed_tx)
    if use_jito:
        try:
            bundle_id = await _send_jito_bundle(session, signed_bytes, tip_tier="normal")
            logger.info("PumpPortal trade sent via Jito bundle: %s", bundle_id)
            return bundle_id
        except ExecutionError as e:
            logger.warning("Jito bundle failed, falling back to direct send: %s", e)

    # Fallback: send directly via Helius RPC
    signature = await _send_transaction(session, signed_bytes, skip_preflight=skip_preflight)
    return signature


# ---------------------------------------------------------------------------
# PumpPortal Local API — pre-graduation path (form data, not JSON)
# ---------------------------------------------------------------------------
async def _execute_pumpportal_local(
    session: aiohttp.ClientSession,
    action: str,
    mint: str,
    amount_sol: float,
    slippage_bps: int,
    pool: str = "pump",
) -> str:
    """Execute trade via PumpPortal Local API for pre-graduation tokens.
    Uses form data (not JSON). Response is raw unsigned tx bytes."""

    if TEST_MODE:
        logger.info("TEST_MODE PumpPortal Local %s: %s %.4f SOL (slippage=%d bps, pool=%s)",
                     action, mint, amount_sol, slippage_bps, pool)
        return "TEST_MODE_PUMPPORTAL_TX"

    slippage_pct = slippage_bps // 100

    if action == "buy":
        form_data = {
            "publicKey": TRADING_WALLET_ADDRESS,
            "action": "buy",
            "mint": mint,
            "amount": str(amount_sol),
            "denominatedInSol": "true",
            "slippage": str(slippage_pct),
            "priorityFee": "0.0005",
            "pool": pool,
        }
    else:
        form_data = {
            "publicKey": TRADING_WALLET_ADDRESS,
            "action": "sell",
            "mint": mint,
            "amount": "100%",
            "denominatedInSol": "false",
            "slippage": str(slippage_pct),
            "priorityFee": "0.0005",
            "pool": pool,
        }

    async with session.post(
        PUMPPORTAL_LOCAL_URL, data=form_data,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"PumpPortal Local HTTP {resp.status}: {body[:2048]}")
        tx_bytes = await resp.read()

    # Sign with trading wallet keypair
    from solders.transaction import VersionedTransaction
    from solders.keypair import Keypair

    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    signed_tx = VersionedTransaction(tx.message, [keypair])
    signed_bytes = bytes(signed_tx)

    # Send via Helius RPC
    tx_b64 = base64.b64encode(signed_bytes).decode("utf-8")
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [tx_b64, {
            "encoding": "base64",
            "skipPreflight": False,
            "preflightCommitment": "confirmed",
        }],
    }

    for rpc_url in (HELIUS_STAKED_URL, HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
        if not rpc_url:
            continue
        try:
            async with session.post(rpc_url, json=rpc_payload,
                                    timeout=aiohttp.ClientTimeout(total=30)) as rpc_resp:
                result = await rpc_resp.json()
                if "error" in result:
                    logger.warning("PumpPortal Local sendTransaction error on %s: %s",
                                   rpc_url[:40], result["error"])
                    continue
                signature = result["result"]
                logger.info("PumpPortal Local %s executed: sig=%s", action, signature[:16])
                await live_execution_log(event_type="TX_SUBMIT", mint=mint, action=action,
                    size_sol=amount_sol, signature=signature, rpc_url_hint=rpc_url[:40])
                return signature
        except Exception as e:
            logger.warning("PumpPortal Local sendTransaction failed on %s: %s", rpc_url[:40], e)

    raise ExecutionError("PumpPortal Local: no Helius URL available for transaction submission")


async def _execute_pumpportal_local_with_session(
    action: str, mint: str, amount_sol: float, slippage_bps: int, pool: str = "pump",
) -> str:
    async with aiohttp.ClientSession() as session:
        return await _execute_pumpportal_local(session, action, mint, amount_sol, slippage_bps, pool)


# ---------------------------------------------------------------------------
# Jupiter Ultra API
# ---------------------------------------------------------------------------
async def _execute_jupiter(
    session: aiohttp.ClientSession,
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int,
    skip_preflight: bool = False,
) -> str:
    """Execute swap via Jupiter Swap V2 API. Returns tx signature.
    V2 flow: GET /order (quote + assembled tx) → sign → POST /execute (managed landing).
    No separate Helius confirmation needed — /execute returns only on-chain confirmation."""

    # EXEC-002: derive for both TEST_MODE log and live live_execution_log at L491.
    # Previously only set inside the TEST_MODE branch, causing NameError on any
    # successful live Jupiter TX_SUBMIT and triggering execute_trade's retry loop.
    action = "buy" if input_mint == SOL_MINT else "sell"
    amount_sol = amount_lamports / LAMPORTS_PER_SOL

    if TEST_MODE:
        logger.info("TEST_MODE Jupiter %s: %s → %s, amount=%d lamports, slippage=%d bps",
                     action, input_mint[:8], output_mint[:8], amount_lamports, slippage_bps)
        return "TEST_MODE_SIMULATED_TX"

    jup_headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}

    # Step 1: GET /swap/v2/order — returns quote + pre-assembled unsigned transaction
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "taker": TRADING_WALLET_ADDRESS,
        "slippageBps": slippage_bps,
    }
    async with session.get(JUPITER_ORDER_URL, params=params, headers=jup_headers,
                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"Jupiter /order HTTP {resp.status}: {body[:200]}")
        order = await resp.json()

    tx_b64 = order.get("transaction")
    request_id = order.get("requestId")
    if not tx_b64:
        err = order.get("errorMessage") or order.get("error", "no transaction returned")
        raise ExecutionError(f"Jupiter /order returned no transaction: {err}")
    if not request_id:
        raise ExecutionError("Jupiter /order returned no requestId")

    out_amount = order.get("outAmount", "0")
    price_impact = order.get("priceImpact", 0)
    router = order.get("router", "unknown")
    logger.info("Jupiter order: outAmount=%s, priceImpact=%.4f, router=%s",
                out_amount, float(price_impact), router)

    # Step 2: Sign the transaction locally
    from solders.transaction import VersionedTransaction
    from solders.keypair import Keypair

    tx_bytes = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    signed_tx = VersionedTransaction(tx.message, [keypair])
    signed_b64 = base64.b64encode(bytes(signed_tx)).decode("utf-8")

    # Step 3: POST /swap/v2/execute — managed landing (confirmed on-chain)
    execute_payload = {
        "signedTransaction": signed_b64,
        "requestId": request_id,
        "lastValidBlockHeight": order.get("lastValidBlockHeight", ""),
    }
    async with session.post(JUPITER_EXECUTE_URL, json=execute_payload,
                            headers={**jup_headers, "Content-Type": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=60)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"Jupiter /execute HTTP {resp.status}: {body[:200]}")
        result = await resp.json()

    status = result.get("status", "")
    if status != "Success":
        err = result.get("error") or result.get("errorMessage", "unknown")
        code = result.get("code", -1)
        raise ExecutionError(f"Jupiter /execute failed: {err} (code={code})")

    signature = result.get("signature", "")
    logger.info("Jupiter V2 swap executed: sig=%s slot=%s", signature[:16] if signature else "?",
                result.get("slot", "?"))
    await live_execution_log(event_type="TX_SUBMIT", mint=output_mint if action == "buy" else input_mint,
        action=action, size_sol=amount_sol, signature=signature, rpc_url_hint="jupiter_v2_execute")
    return signature


# ---------------------------------------------------------------------------
# Jito bundle wrapping (for PumpPortal trades only)
# ---------------------------------------------------------------------------
async def _send_jito_bundle(session: aiohttp.ClientSession, tx_bytes: bytes, tip_tier: str = "normal") -> str:
    """Wrap transaction in a Jito bundle for MEV protection."""
    tip = JITO_TIPS_LAMPORTS.get(tip_tier, JITO_TIPS_LAMPORTS["normal"])
    # Hard cap: never exceed 0.1 SOL
    tip = min(tip, JITO_TIPS_LAMPORTS["frenzy_snipe"])

    tx_b64 = base64.b64encode(tx_bytes).decode("utf-8")

    bundle_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [[tx_b64]],
    }

    async with session.post(JITO_ENDPOINT, json=bundle_payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"Jito bundle HTTP {resp.status}: {body[:200]}")
        result = await resp.json()
        bundle_id = result.get("result", "")
        logger.info("Jito bundle submitted: %s (tip: %d lamports)", bundle_id, tip)
        return bundle_id


# ---------------------------------------------------------------------------
# Send transaction via Helius RPC
# ---------------------------------------------------------------------------
async def _send_transaction(session: aiohttp.ClientSession, tx_bytes: bytes, skip_preflight: bool = False) -> str:
    """Send transaction via HELIUS_STAKED_URL (fastest landing), fallback to HELIUS_GATEKEEPER_URL."""
    tx_b64 = base64.b64encode(tx_bytes).decode("utf-8")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [tx_b64, {
            "encoding": "base64",
            "skipPreflight": skip_preflight,
            "preflightCommitment": "confirmed",
        }],
    }
    last_error = ""
    helius_api_key = os.getenv("HELIUS_API_KEY", "").strip()
    for rpc_url in (HELIUS_STAKED_URL, HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
        if not rpc_url:
            continue
        try:
            # Named/staked RPCs use Bearer auth — strip ?api-key= from URL if present
            url = rpc_url.split("?")[0] if "?api-key=" in rpc_url and rpc_url == HELIUS_STAKED_URL else rpc_url
            headers = {"Authorization": f"Bearer {helius_api_key}"} if helius_api_key and rpc_url == HELIUS_STAKED_URL else {}
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                result = await resp.json()
                if "error" in result:
                    last_error = f"sendTransaction error: {result['error']}"
                    logger.warning("sendTransaction failed on %s: %s", rpc_url[:40], last_error)
                    continue
                return result["result"]
        except Exception as e:
            last_error = str(e)
            logger.warning("sendTransaction error on %s: %s", rpc_url[:40], e)
    raise ExecutionError(last_error or "No Helius URL configured for transaction submission")


# ---------------------------------------------------------------------------
# Helius Enhanced Trade Confirmation
# ---------------------------------------------------------------------------
async def _confirm_trade_helius(session: aiohttp.ClientSession, signature: str) -> dict:
    """
    Confirm a trade landed successfully using Helius Enhanced Transaction parsing.
    POST /v0/transactions — parse result to verify swap completed.
    Retries 3 times with 2s delays. No caching (real-time confirmation).
    Falls back to treating as unconfirmed if Helius unavailable.

    Returns: {"confirmed": bool, "details": dict}
    """
    if not HELIUS_PARSE_TX_URL or not signature or signature.startswith("TEST_MODE"):
        return {"confirmed": True, "details": {}}

    url = HELIUS_PARSE_TX_URL
    payload = {"transactions": [signature]}

    for attempt in range(1, 4):
        t0 = time.time()
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                elapsed_ms = (time.time() - t0) * 1000
                logger.debug("Helius trade confirm attempt %d: %.0fms (HTTP %d)", attempt, elapsed_ms, resp.status)

                if resp.status != 200:
                    if attempt < 3:
                        await asyncio.sleep(2)
                        continue
                    return {"confirmed": False, "details": {"error": f"HTTP {resp.status}"}}

                txs = await resp.json()
                if not isinstance(txs, list) or not txs:
                    if attempt < 3:
                        await asyncio.sleep(2)
                        continue
                    return {"confirmed": False, "details": {"error": "empty response"}}

                tx = txs[0]
                tx_error = tx.get("transactionError")
                tx_type = tx.get("type", "")
                source = tx.get("source", "")
                token_transfers = tx.get("tokenTransfers", [])

                if tx_error:
                    logger.warning("Trade %s failed on-chain: %s", signature[:16], tx_error)
                    return {"confirmed": False, "details": {"error": str(tx_error), "type": tx_type}}

                # Swap completed successfully
                logger.info("Trade confirmed via Helius: %s (type=%s, source=%s, transfers=%d)",
                             signature[:16], tx_type, source, len(token_transfers))
                return {
                    "confirmed": True,
                    "details": {
                        "type": tx_type,
                        "source": source,
                        "token_transfers": len(token_transfers),
                        "slot": tx.get("slot", 0),
                    },
                }

        except Exception as e:
            logger.debug("Helius confirm attempt %d error: %s", attempt, e)
            if attempt < 3:
                await asyncio.sleep(2)

    logger.warning("Trade confirmation failed after 3 attempts for %s — treating as unconfirmed", signature[:16])
    return {"confirmed": False, "details": {"error": "timeout after 3 attempts"}}


# ---------------------------------------------------------------------------
# Token balance helper (for Jupiter sells)
# ---------------------------------------------------------------------------
async def _get_token_balance(session: aiohttp.ClientSession, mint: str, wallet: str) -> int:
    """Get token balance in raw units via Helius RPC getTokenAccountsByOwner."""
    for rpc_url in (HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
        if not rpc_url:
            continue
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [wallet, {"mint": mint}, {"encoding": "jsonParsed"}],
            }
            async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                accounts = data.get("result", {}).get("value", [])
                if accounts:
                    info = accounts[0].get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                    amount = info.get("tokenAmount", {}).get("amount", "0")
                    return int(amount)
        except Exception as e:
            logger.debug("Token balance fetch failed on %s: %s", rpc_url[:30], e)
    return 0


# ---------------------------------------------------------------------------
# High-level execution with retry
# ---------------------------------------------------------------------------
async def execute_trade(
    action: str,
    token: Token,
    amount_sol: float,
    slippage_tier: str = "confirmation",
    jito_tip_tier: str = "normal",
    use_jito: bool = True,
    bonding_curve_progress: float | None = None,
    signal_type: str = "",
) -> ExecutionResult:
    """
    Execute a trade with retry logic.
    action: "buy" or "sell"
    bonding_curve_progress: if provided, used for PumpPortal Local routing
    signal_type: e.g. "migration" — forces Jupiter even if pre-graduation
    Returns ExecutionResult with success status, signature, etc.
    """
    # Determine effective bonding curve progress
    bc_progress = bonding_curve_progress if bonding_curve_progress is not None else token.bonding_curve_progress

    # Route: pre-graduation tokens go through PumpPortal Local API,
    # unless signal_type is "migration" (already graduating → use Jupiter)
    use_pumpportal_local = (
        bc_progress < GRADUATION_THRESHOLD and signal_type != "migration"
    )

    api = choose_execution_api(token)
    router_label = "pumpportal" if use_pumpportal_local else "jupiter_v2"
    delay_ms = RETRY_CONFIG["initial_delay_ms"]
    last_error = ""

    for attempt in range(1, RETRY_CONFIG["max_retries"] + 1):
        # Preflight on attempt 1, skip on retries 2+ (AGENT_CONTEXT Section 5)
        skip_preflight = attempt > 1

        try:
            if use_pumpportal_local:
                # PumpPortal Local path for pre-graduation tokens
                slippage_bps_pp = PUMPPORTAL_SLIPPAGE.get(slippage_tier, 15) * 100  # convert pct to bps
                signature = await _execute_pumpportal_local_with_session(
                    action, token.mint, amount_sol, slippage_bps_pp, token.pool,
                )
            elif api == ExecutionAPI.PUMPPORTAL:
                slippage = PUMPPORTAL_SLIPPAGE.get(slippage_tier, 15)
                fee_idx = min(attempt - 1, len(PRIORITY_FEE_TIERS) - 1)
                priority_fee = PRIORITY_FEE_TIERS[fee_idx] if RETRY_CONFIG["escalate_fee"] else PRIORITY_FEE_TIERS[0]

                signature = await _execute_pumpportal_with_session(
                    action, token.mint, amount_sol, slippage, priority_fee, token.pool,
                    use_jito=use_jito, skip_preflight=skip_preflight,
                )
            else:
                slippage_bps = _get_jupiter_slippage(token.liquidity_usd)
                if action == "buy":
                    amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)
                    signature = await _execute_jupiter_with_session(
                        SOL_MINT, token.mint, amount_lamports, slippage_bps,
                        skip_preflight=skip_preflight,
                    )
                else:
                    # For sells: fetch actual token balance from wallet
                    # amount_sol is the SOL value but Jupiter needs token units
                    async with aiohttp.ClientSession() as bal_session:
                        token_amount = await _get_token_balance(bal_session, token.mint, TRADING_WALLET_ADDRESS)
                    if token_amount <= 0:
                        raise ExecutionError(f"No token balance found for {token.mint[:12]}")
                    signature = await _execute_jupiter_with_session(
                        token.mint, SOL_MINT, token_amount, slippage_bps,
                        skip_preflight=skip_preflight,
                    )

            # Confirm trade landed via Helius Enhanced Transaction parsing
            if not TEST_MODE and signature:
                async with aiohttp.ClientSession() as confirm_session:
                    confirmation = await _confirm_trade_helius(confirm_session, signature)
                if not confirmation["confirmed"]:
                    err_detail = confirmation["details"].get("error", "unconfirmed")
                    logger.warning("Trade %s not confirmed: %s — retrying", signature[:16], err_detail)
                    last_error = f"trade not confirmed: {err_detail}"
                    if attempt < RETRY_CONFIG["max_retries"]:
                        await asyncio.sleep(delay_ms / 1000.0)
                        delay_ms *= RETRY_CONFIG["backoff_factor"]
                    continue

            return ExecutionResult(
                success=True,
                signature=signature,
                api_used=router_label,
                attempts=attempt,
                simulated=TEST_MODE,
            )

        except ExecutionError as e:
            last_error = str(e)
            logger.warning("Execution attempt %d/%d failed: %s", attempt, RETRY_CONFIG["max_retries"], e)
            await live_execution_log(event_type="ERROR", mint=token.mint, action=action,
                size_sol=amount_sol, error_msg=str(e), extra={"attempt": attempt})
        except Exception as e:
            last_error = str(e)
            logger.error("Unexpected execution error attempt %d: %s", attempt, e)
            await live_execution_log(event_type="ERROR", mint=token.mint, action=action,
                size_sol=amount_sol, error_msg=str(e), extra={"attempt": attempt})

        if attempt < RETRY_CONFIG["max_retries"]:
            await asyncio.sleep(delay_ms / 1000.0)
            delay_ms *= RETRY_CONFIG["backoff_factor"]

    return ExecutionResult(
        success=False,
        api_used=router_label,
        attempts=RETRY_CONFIG["max_retries"],
        error=last_error,
        simulated=TEST_MODE,
    )


async def _execute_pumpportal_with_session(action, mint, amount_sol, slippage, priority_fee, pool,
                                           use_jito=True, skip_preflight=False):
    async with aiohttp.ClientSession() as session:
        return await _execute_pumpportal(session, action, mint, amount_sol, slippage, priority_fee, pool,
                                         use_jito=use_jito, skip_preflight=skip_preflight)


async def _execute_jupiter_with_session(input_mint, output_mint, amount_lamports, slippage_bps,
                                        skip_preflight=False):
    async with aiohttp.ClientSession() as session:
        return await _execute_jupiter(session, input_mint, output_mint, amount_lamports, slippage_bps,
                                      skip_preflight=skip_preflight)


# ---------------------------------------------------------------------------
# Main (for standalone testing)
# ---------------------------------------------------------------------------
async def main():
    logger.info("Execution service ready (TEST_MODE=%s)", TEST_MODE)

    if TEST_MODE:
        # Demo: simulate a trade
        token = Token(mint="DemoMint111111111111111111111111111111111", pool="pump", bonding_curve_progress=0.5)
        result = await execute_trade("buy", token, 0.5, slippage_tier="alpha_snipe")
        logger.info("Demo result: %s", result)
    else:
        logger.info("Execution service running — awaiting trade requests")
        # In production, this is called by bot_core, not run standalone
        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
