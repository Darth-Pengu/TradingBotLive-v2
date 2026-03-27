"""
ZMN Bot Paper Trading Simulator
=================================
Simulates trade execution with realistic conditions when TEST_MODE=true.
Real signals, real ML scoring, real risk management — fake transactions.

- Realistic slippage simulation per tier
- Realistic fee simulation (PumpPortal 0.5%, Jupiter 0.001 SOL)
- Positions tracked in Redis + SQLite paper_trades table
- Full trade logging to logs/paper_trades.log
- Stats tracked in Redis for dashboard consumption
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("paper_trader")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Slippage simulation ranges (percentage)
SLIPPAGE_RANGES = {
    "alpha_snipe": (1.0, 4.0),
    "confirmation": (0.5, 2.0),
    "post_grad_dip": (0.3, 1.0),
    "sell": (0.3, 1.5),
}

# Fee simulation
PUMPPORTAL_FEE_PCT = 0.005  # 0.5%
JUPITER_NETWORK_FEE_SOL = 0.001

# Paper trade log
LOG_DIR = Path("logs")
PAPER_LOG_PATH = LOG_DIR / "paper_trades.log"


def _paper_log(message: str):
    """Append to paper_trades.log."""
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    with open(PAPER_LOG_PATH, "a") as f:
        f.write(line)
    logger.info("PAPER: %s", message)


async def _get_token_price(mint: str) -> float:
    """Get current token price via Jupiter V3 (with auth) or Binance fallback."""
    jup_key = os.getenv("JUPITER_API_KEY", "").strip()
    try:
        headers = {"x-api-key": jup_key} if jup_key else {}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.jup.ag/price/v3",
                params={"ids": mint},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = data.get("data", {}).get(mint, {}).get("usdPrice") or data.get("data", {}).get(mint, {}).get("price")
                    if price:
                        return float(price)
    except Exception:
        pass
    # Price fetch failed — return 0.0, caller must check and skip trade
    logger.warning("Could not fetch price for %s — returning 0.0", mint[:12])
    return 0.0


def _simulate_slippage(tier: str) -> float:
    """Return simulated slippage percentage."""
    low, high = SLIPPAGE_RANGES.get(tier, (0.5, 2.0))
    return round(random.uniform(low, high), 2)


def _simulate_fees(amount_sol: float, pool: str) -> float:
    """Return simulated fee in SOL."""
    if pool in ("pump", "pump-amm", "auto"):
        return round(amount_sol * PUMPPORTAL_FEE_PCT, 6)
    else:
        return JUPITER_NETWORK_FEE_SOL


async def paper_buy(
    pg_pool,
    redis_conn: aioredis.Redis | None,
    mint: str,
    amount_sol: float,
    personality: str,
    slippage_tier: str = "confirmation",
    pool: str = "auto",
    ml_score: float = 0.0,
    signal_source: str = "",
    market_mode: str = "NORMAL",
    fear_greed: float = 50.0,
) -> dict:
    """Simulate a paper buy trade. Returns result dict with fake signature."""
    # Get real price — skip trade if price fetch fails
    price = await _get_token_price(mint)
    if price <= 0:
        logger.warning("PAPER: price fetch failed for %s — skipping", mint[:12])
        return {"success": False, "error": "price_fetch_failed", "simulated": True}

    # Simulate slippage (buying pushes price up)
    slippage = _simulate_slippage(slippage_tier)
    entry_price = price * (1 + slippage / 100)

    # Simulate fees
    fees = _simulate_fees(amount_sol, pool)
    net_amount = amount_sol - fees

    # Generate fake signature
    sig = f"PAPER_{uuid.uuid4().hex[:16]}"
    now = time.time()

    # Store in PostgreSQL
    trade_id = await pg_pool.fetchval(
        """INSERT INTO paper_trades
           (mint, personality, entry_price, amount_sol, slippage_pct, fees_sol,
            entry_time, signal_source, ml_score, entry_signature,
            market_mode_at_entry, fear_greed_at_entry)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
           RETURNING id""",
        mint, personality, entry_price, net_amount, slippage, fees,
        now, signal_source, ml_score, sig, market_mode, fear_greed,
    )

    # Store in Redis for live tracking
    if redis_conn:
        try:
            await redis_conn.hset(f"paper:positions:{mint}", mapping={
                "trade_id": trade_id,
                "personality": personality,
                "entry_price": entry_price,
                "amount_sol": net_amount,
                "entry_time": now,
                "ml_score": ml_score,
            })
            await redis_conn.hincrby("paper:stats", "total_trades", 1)
            await redis_conn.hincrby(f"paper:stats:personality:{personality}", "trades", 1)
            await redis_conn.hincrby(f"paper:stats:source:{signal_source}", "trades", 1)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await redis_conn.hincrby(f"paper:stats:daily:{today}", "trades", 1)
        except Exception as e:
            logger.debug("Redis paper stats error: %s", e)

    _paper_log(
        f"PAPER BUY | {personality} | TOKEN: {mint[:12]}... | "
        f"Amount: {net_amount:.4f} SOL | Price: ${entry_price:.10f} | "
        f"ML Score: {ml_score:.0f}% | Signal: {signal_source} | "
        f"Slippage: {slippage:.1f}% | Fees: {fees:.4f} SOL"
    )

    return {
        "success": True,
        "signature": sig,
        "trade_id": trade_id,
        "entry_price": entry_price,
        "amount_sol": net_amount,
        "slippage_pct": slippage,
        "fees_sol": fees,
        "simulated": True,
    }


async def paper_sell(
    pg_pool,
    redis_conn: aioredis.Redis | None,
    mint: str,
    sell_pct: float,
    reason: str,
    personality: str,
    trade_id: int = 0,
    entry_price: float = 0.0,
    entry_time: float = 0.0,
    amount_sol: float = 0.0,
    signal_source: str = "",
) -> dict:
    """Simulate a paper sell trade. Returns result dict with P/L."""

    # Get current real price — use entry price if fetch fails (neutral P/L)
    current_price = await _get_token_price(mint)
    if current_price <= 0:
        logger.warning("PAPER SELL: price fetch failed for %s — using entry price", mint[:12])
        current_price = entry_price

    # Simulate exit slippage (selling pushes price down)
    slippage = _simulate_slippage("sell")
    exit_price = current_price * (1 - slippage / 100)

    # Calculate P/L
    sell_amount = amount_sol * sell_pct
    fees = _simulate_fees(sell_amount, "auto")
    hold_seconds = time.time() - entry_time if entry_time > 0 else 0

    if entry_price > 0:
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        pnl_sol = (exit_price - entry_price) / entry_price * sell_amount - fees
    else:
        pnl_pct = 0.0
        pnl_sol = -fees

    outcome = "profit" if pnl_sol > 0 else "loss"
    sig = f"PAPER_{uuid.uuid4().hex[:16]}"

    # Update PostgreSQL
    if trade_id:
        await pg_pool.execute(
            """UPDATE paper_trades SET exit_price=$1, exit_time=$2, hold_seconds=$3,
               realised_pnl_sol=$4, realised_pnl_pct=$5, exit_reason=$6, exit_signature=$7
               WHERE id=$8""",
            exit_price, time.time(), hold_seconds, pnl_sol, pnl_pct, reason, sig, trade_id,
        )

    # Update Redis stats
    if redis_conn:
        try:
            await redis_conn.delete(f"paper:positions:{mint}")
            if pnl_sol > 0:
                await redis_conn.hincrby("paper:stats", "winning_trades", 1)
                if signal_source:
                    await redis_conn.hincrby(f"paper:stats:source:{signal_source}", "wins", 1)
            await redis_conn.hincrbyfloat("paper:stats", "total_pnl_sol", pnl_sol)
            await redis_conn.hincrbyfloat(f"paper:stats:personality:{personality}", "pnl", pnl_sol)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await redis_conn.hincrbyfloat(f"paper:stats:daily:{today}", "pnl", pnl_sol)
        except Exception as e:
            logger.debug("Redis paper stats error: %s", e)

    # Format hold time
    m, s = divmod(int(hold_seconds), 60)
    h, m = divmod(m, 60)
    hold_str = f"{h}h {m}m {s}s" if h else f"{m}m {s:02d}s"

    _paper_log(
        f"PAPER SELL | {personality} | TOKEN: {mint[:12]}... | "
        f"Amount: {sell_pct*100:.0f}% | Exit Price: ${exit_price:.10f} | "
        f"Hold: {hold_str} | P/L: {'+' if pnl_sol>=0 else ''}{pnl_sol:.4f} SOL "
        f"({'+' if pnl_pct>=0 else ''}{pnl_pct:.1f}%) | "
        f"Reason: {reason} | Fees: {fees:.4f} SOL"
    )

    return {
        "success": True,
        "signature": sig,
        "pnl_sol": pnl_sol,
        "pnl_pct": pnl_pct,
        "exit_price": exit_price,
        "outcome": outcome,
        "hold_seconds": hold_seconds,
        "fees_sol": fees,
        "simulated": True,
    }
