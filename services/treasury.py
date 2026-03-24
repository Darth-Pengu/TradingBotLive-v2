"""
ToxiBot Treasury Sweep Service
================================
Automatically transfers excess SOL from trading wallet to holding wallet.
- Polls Helius getBalance every 5 minutes
- If balance > 30 SOL: transfer (balance - 25) SOL to holding wallet
- Minimum transfer: 1 SOL
- 3 consecutive failures → EMERGENCY_STOP
- Uses SystemProgram.transfer via Helius RPC (NOT Jito — low priority)
- TEST_MODE=true: log what WOULD be swept, never execute
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aiohttp
import aiosqlite
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("treasury")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
TRADING_WALLET_PRIVATE_KEY = os.getenv("TRADING_WALLET_PRIVATE_KEY", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
HOLDING_WALLET_ADDRESS = os.getenv("HOLDING_WALLET_ADDRESS", "")
DISCORD_WEBHOOK_TREASURY = os.getenv("DISCORD_WEBHOOK_TREASURY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "toxibot.db")

# Hard-coded treasury rules — never make these configurable at runtime
TREASURY_RULES = {
    "trigger_threshold_sol": 30.0,
    "target_balance_sol": 25.0,
    "min_transfer_sol": 1.0,
    "check_interval_seconds": 300,
    "max_retries": 3,
    "sweep_priority_fee": 0.000005,
}

LAMPORTS_PER_SOL = 1_000_000_000


async def _init_db(db: aiosqlite.Connection):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS treasury_sweeps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            amount_sol REAL NOT NULL,
            balance_before_sol REAL NOT NULL,
            balance_after_sol REAL NOT NULL,
            signature TEXT,
            status TEXT NOT NULL DEFAULT 'success',
            error_message TEXT
        )
    """)
    await db.commit()


async def _get_balance(session: aiohttp.ClientSession, address: str) -> float | None:
    """Get SOL balance via Helius RPC getBalance."""
    if not HELIUS_RPC_URL:
        logger.error("HELIUS_RPC_URL not set")
        return None

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address],
    }
    try:
        async with session.post(HELIUS_RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                result = await resp.json()
                lamports = result.get("result", {}).get("value", 0)
                return lamports / LAMPORTS_PER_SOL
            logger.warning("getBalance HTTP %d", resp.status)
    except Exception as e:
        logger.error("getBalance failed: %s", e)
    return None


async def _execute_sweep(session: aiohttp.ClientSession, amount_sol: float) -> str:
    """Build, sign, and send SOL transfer to holding wallet."""
    from solders.system_program import transfer, TransferParams
    from solders.transaction import Transaction
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey

    amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)
    trading_keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    holding_pubkey = Pubkey.from_string(HOLDING_WALLET_ADDRESS)

    ix = transfer(TransferParams(
        from_pubkey=trading_keypair.pubkey(),
        to_pubkey=holding_pubkey,
        lamports=amount_lamports,
    ))

    # Add compute budget instruction for priority fee (sweep_priority_fee = 0.000005 SOL)
    from solders.compute_budget import set_compute_unit_price
    priority_microlamports = int(TREASURY_RULES["sweep_priority_fee"] * LAMPORTS_PER_SOL * 1_000)  # convert to microlamports
    compute_ix = set_compute_unit_price(priority_microlamports)

    # Get latest blockhash
    bh_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getLatestBlockhash",
        "params": [{"commitment": "confirmed"}],
    }
    async with session.post(HELIUS_RPC_URL, json=bh_payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        bh_result = await resp.json()
        blockhash_str = bh_result["result"]["value"]["blockhash"]

    from solders.hash import Hash
    blockhash = Hash.from_string(blockhash_str)

    tx = Transaction.new_signed_with_payer(
        [compute_ix, ix],
        payer=trading_keypair.pubkey(),
        signing_keypairs=[trading_keypair],
        recent_blockhash=blockhash,
    )

    # Send transaction
    import base64
    tx_bytes = bytes(tx)
    tx_b64 = base64.b64encode(tx_bytes).decode("utf-8")

    send_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [tx_b64, {"encoding": "base64", "skipPreflight": False}],
    }
    async with session.post(HELIUS_RPC_URL, json=send_payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        send_result = await resp.json()
        if "error" in send_result:
            raise Exception(f"sendTransaction error: {send_result['error']}")
        return send_result["result"]


async def _send_discord_notification(session: aiohttp.ClientSession, message: str):
    webhook = DISCORD_WEBHOOK_TREASURY or DISCORD_WEBHOOK_URL
    if not webhook:
        logger.info("Discord (no webhook): %s", message)
        return
    try:
        async with session.post(webhook, json={"content": message}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status not in (200, 204):
                logger.warning("Discord webhook HTTP %d", resp.status)
    except Exception as e:
        logger.warning("Discord notification failed: %s", e)


async def _log_sweep(db: aiosqlite.Connection, amount: float, before: float, after: float,
                     signature: str | None, status: str, error: str | None = None):
    await db.execute(
        "INSERT INTO treasury_sweeps (timestamp, amount_sol, balance_before_sol, balance_after_sol, signature, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), amount, before, after, signature, status, error),
    )
    await db.commit()


async def run_treasury_sweep():
    logger.info("Treasury sweep service starting (TEST_MODE=%s)", TEST_MODE)

    if not HOLDING_WALLET_ADDRESS:
        logger.error("HOLDING_WALLET_ADDRESS not set — treasury service cannot start")
        return

    redis_conn = None
    if not TEST_MODE:
        try:
            redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
            await redis_conn.ping()
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)

    db = await aiosqlite.connect(DATABASE_PATH)
    await _init_db(db)

    consecutive_failures = 0

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                balance = await _get_balance(session, TRADING_WALLET_ADDRESS)
                if balance is None:
                    logger.warning("Could not fetch trading wallet balance")
                    consecutive_failures += 1
                else:
                    logger.info("Trading wallet balance: %.4f SOL", balance)

                    if balance > TREASURY_RULES["trigger_threshold_sol"]:
                        transfer_amount = balance - TREASURY_RULES["target_balance_sol"]

                        if transfer_amount < TREASURY_RULES["min_transfer_sol"]:
                            logger.info("Transfer amount %.4f SOL below minimum — skipping", transfer_amount)
                        else:
                            logger.info("Sweep triggered: %.4f SOL → holding wallet", transfer_amount)

                            if TEST_MODE:
                                logger.info("TEST_MODE — would sweep %.4f SOL (balance: %.4f → %.4f)",
                                            transfer_amount, balance, balance - transfer_amount)
                                await _log_sweep(db, transfer_amount, balance, balance - transfer_amount,
                                                 "TEST_MODE", "test")
                                consecutive_failures = 0
                            else:
                                try:
                                    signature = await _execute_sweep(session, transfer_amount)
                                    after_balance = balance - transfer_amount
                                    logger.info("Sweep success: %s (%.4f SOL)", signature, transfer_amount)
                                    await _log_sweep(db, transfer_amount, balance, after_balance, signature, "success")
                                    await _send_discord_notification(
                                        session,
                                        f"Treasury sweep: {transfer_amount:.4f} SOL → holding wallet. "
                                        f"Trading balance: {after_balance:.4f} SOL. Tx: {signature}"
                                    )
                                    consecutive_failures = 0
                                except Exception as e:
                                    logger.error("Sweep execution failed: %s", e)
                                    await _log_sweep(db, transfer_amount, balance, balance, None, "failed", str(e))
                                    consecutive_failures += 1
                    else:
                        consecutive_failures = 0  # Balance check succeeded, just no sweep needed

                # 3 consecutive failures → EMERGENCY_STOP
                if consecutive_failures >= TREASURY_RULES["max_retries"]:
                    msg = f"Treasury sweep failed {consecutive_failures} consecutive times — possible wallet compromise"
                    logger.critical(msg)
                    if redis_conn:
                        await redis_conn.publish("alerts:emergency", json.dumps({
                            "reason": msg,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
                    await _send_discord_notification(session, f"EMERGENCY: {msg}")
                    # Halt — require manual restart
                    break

            except Exception as e:
                logger.error("Treasury sweep loop error: %s", e)
                consecutive_failures += 1

            await asyncio.sleep(TREASURY_RULES["check_interval_seconds"])

    await db.close()
    logger.info("Treasury sweep service stopped")


if __name__ == "__main__":
    asyncio.run(run_treasury_sweep())
