"""
ZMN Bot Execution Layer
========================
Two execution paths — no Telegram dependency anywhere:
  1. PumpPortal Local API (bonding curve tokens) — POST https://pumpportal.fun/api/trade-local
  2. Jupiter Swap API (graduated/AMM tokens) — https://api.jup.ag/swap/v1/

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

# --- Endpoints ---
PUMPPORTAL_TRADE_URL = "https://pumpportal.fun/api/trade-local"
JUPITER_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"
JITO_ENDPOINT = os.getenv("JITO_ENDPOINT", "https://mainnet.block-engine.jito.wtf/api/v1/bundles")
JITO_DONTFRONT_PUBKEY = "jitodontfront111111111111111111111111111111"

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000

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

# --- Jito tip tiers (from AGENT_CONTEXT Section 5) ---
JITO_TIPS_LAMPORTS = {
    "normal": 1_000_000,        # 0.001 SOL
    "competitive": 10_000_000,  # 0.01 SOL
    "frenzy_snipe": 100_000_000,  # 0.1 SOL — hard maximum, never exceed
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

# --- Priority fee tiers (for escalation on retry) ---
PRIORITY_FEE_TIERS = [0.0001, 0.0005, 0.001, 0.005, 0.01]  # SOL


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
    if token.pool in ("pump", "pump-amm") and token.bonding_curve_progress < 1.0:
        return ExecutionAPI.PUMPPORTAL
    elif token.pool in ("raydium", "raydium-cpmm", "orca", "meteora", "pumpswap"):
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
            raise ExecutionError(f"PumpPortal HTTP {resp.status}: {body[:200]}")
        tx_bytes = await resp.read()

    # Sign with trading wallet keypair
    from solders.transaction import VersionedTransaction
    from solders.keypair import Keypair

    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    tx.sign([keypair])

    # Send via Jito bundle for MEV protection (Jupiter has built-in MEV — no Jito needed)
    signed_bytes = bytes(tx)
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
    """Execute swap via Jupiter Ultra API. Returns tx signature."""

    if TEST_MODE:
        action = "buy" if input_mint == SOL_MINT else "sell"
        logger.info("TEST_MODE Jupiter %s: %s → %s, amount=%d lamports, slippage=%d bps",
                     action, input_mint[:8], output_mint[:8], amount_lamports, slippage_bps)
        return "TEST_MODE_SIMULATED_TX"

    # Jupiter API headers (api key for api.jup.ag)
    jup_headers = {}
    if JUPITER_API_KEY:
        jup_headers["x-api-key"] = JUPITER_API_KEY

    # Step 1: Get quote
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount_lamports,
        "slippageBps": slippage_bps,
        "onlyDirectRoutes": False,
    }
    async with session.get(JUPITER_QUOTE_URL, params=params, headers=jup_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"Jupiter quote HTTP {resp.status}: {body[:200]}")
        quote = await resp.json()

    # Step 2: Get swap transaction
    priority_fee = await _get_dynamic_priority_fee(session)
    swap_payload = {
        "quoteResponse": quote,
        "userPublicKey": TRADING_WALLET_ADDRESS,
        "wrapAndUnwrapSol": True,
        "prioritizationFeeLamports": priority_fee,
    }
    async with session.post(JUPITER_SWAP_URL, json=swap_payload, headers=jup_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ExecutionError(f"Jupiter swap HTTP {resp.status}: {body[:200]}")
        swap_data = await resp.json()

    # Step 3: Sign and send
    from solders.transaction import VersionedTransaction
    from solders.keypair import Keypair

    tx_bytes = base64.b64decode(swap_data["swapTransaction"])
    tx = VersionedTransaction.from_bytes(tx_bytes)
    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx.sign([keypair])

    # Jupiter Ultra has built-in MEV protection — no Jito wrap needed
    signature = await _send_transaction(session, bytes(tx), skip_preflight=skip_preflight)
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
    for rpc_url in (HELIUS_STAKED_URL, HELIUS_GATEKEEPER_URL):
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
) -> ExecutionResult:
    """
    Execute a trade with retry logic.
    action: "buy" or "sell"
    Returns ExecutionResult with success status, signature, etc.
    """
    api = choose_execution_api(token)
    delay_ms = RETRY_CONFIG["initial_delay_ms"]
    last_error = ""

    for attempt in range(1, RETRY_CONFIG["max_retries"] + 1):
        # Preflight on attempt 1, skip on retries 2+ (AGENT_CONTEXT Section 5)
        skip_preflight = attempt > 1

        try:
            if api == ExecutionAPI.PUMPPORTAL:
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
                api_used=api.value,
                attempts=attempt,
                simulated=TEST_MODE,
            )

        except ExecutionError as e:
            last_error = str(e)
            logger.warning("Execution attempt %d/%d failed: %s", attempt, RETRY_CONFIG["max_retries"], e)
        except Exception as e:
            last_error = str(e)
            logger.error("Unexpected execution error attempt %d: %s", attempt, e)

        if attempt < RETRY_CONFIG["max_retries"]:
            await asyncio.sleep(delay_ms / 1000.0)
            delay_ms *= RETRY_CONFIG["backoff_factor"]

    return ExecutionResult(
        success=False,
        api_used=api.value,
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
