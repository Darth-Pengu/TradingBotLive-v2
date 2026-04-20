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
_TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
TRADE_MODE = "paper" if _TEST_MODE else "live"

# FEE-MODEL-001 (2026-04-20): revised to match live reality observed on v4 single
# trade (id=6580, mint yh3n441..., 0.365 SOL round-trip cost 0.094 SOL = 25.8% of
# position — ~96x worse than the old priority-fee-only model).
#
# Slippage ranges are per-tier 3-tuples: (low_pct, high_pct, size_impact_exp).
# Applied slippage = random.uniform(low, high) * (amount_sol / REF_AMOUNT)^exp
# REF_AMOUNT = 0.1 SOL is the calibration anchor. Higher exp = more size impact.
# Pre-grad pump.fun BC tiers use exp=0.7 (thin curve, strong impact).
# Post-grad AMM tiers use exp=0.3 (deeper pools, weaker impact).
SLIPPAGE_REF_AMOUNT = 0.1  # SOL — calibration anchor
SLIPPAGE_RANGES = {
    # Pre-grad BUY on pump.fun BC (most Speed Demon entries)
    "alpha_snipe":   (3.0, 12.0, 0.7),
    "confirmation":  (2.0, 8.0, 0.7),
    # Post-grad BUY on Raydium / pumpswap (Analyst dip-buys, post-migration)
    "post_grad_dip": (0.5, 2.0, 0.3),
    # SELL on pre-grad BC (same dynamics as BUY — thin curve)
    "sell":          (3.0, 15.0, 0.7),
    # SELL on post-grad pools (deeper liquidity, tighter)
    "sell_postgrad": (0.5, 2.5, 0.3),
}

# Legacy constants (kept for any callers that still reference them)
PUMPPORTAL_FEE_PCT = 0.005
JUPITER_NETWORK_FEE_SOL = 0.001

# FEE-MODEL-001 per-path fee components (env-var overridable for recalibration
# without code changes). Each applied as documented in _simulate_fees.
# Platform fees (percentage, applied to notional on each side)
PAPER_FEE_PUMPFUN_PCT = float(os.getenv("PAPER_FEE_PUMPFUN_PCT", "0.01"))    # 1% each side
PAPER_FEE_RAYDIUM_PCT = float(os.getenv("PAPER_FEE_RAYDIUM_PCT", "0.0025"))  # 0.25% each side
PAPER_FEE_JUPITER_PCT = float(os.getenv("PAPER_FEE_JUPITER_PCT", "0.006"))   # 0.6% each side (LP included)
# Priority fees (SOL per round-trip; split in half per side)
PAPER_PRIORITY_FEE_PREGRAD_SOL = float(os.getenv("PAPER_PRIORITY_FEE_PREGRAD_SOL", "0.0010"))
PAPER_PRIORITY_FEE_POSTGRAD_SOL = float(os.getenv("PAPER_PRIORITY_FEE_POSTGRAD_SOL", "0.0020"))
# Jito tips (SOL per round-trip; split in half per side; pre-grad=0 until EXEC-005 lands)
PAPER_JITO_TIP_POSTGRAD_SOL = float(os.getenv("PAPER_JITO_TIP_POSTGRAD_SOL", "0.0010"))
PAPER_JITO_TIP_PREGRAD_SOL = float(os.getenv("PAPER_JITO_TIP_PREGRAD_SOL", "0.0"))
GRADUATION_THRESHOLD = 0.95  # matches services/execution.py

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
    """Get current token price. Jupiter V3 primary, GeckoTerminal fallback (free, no auth)."""
    jup_key = os.getenv("JUPITER_API_KEY", "").strip()

    # Primary: Jupiter V3
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
                    price = (data.get("data", {}).get(mint, {}).get("usdPrice") or
                             data.get("data", {}).get(mint, {}).get("price"))
                    if price:
                        return float(price)
                elif resp.status == 401:
                    logger.warning("Jupiter 401 — API key invalid/missing, trying GeckoTerminal")
    except Exception:
        pass

    # Fallback: GeckoTerminal (free, no auth needed)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}",
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price_str = data.get("data", {}).get("attributes", {}).get("price_usd")
                    if price_str:
                        logger.debug("GeckoTerminal price for %s: $%s", mint[:12], price_str)
                        return float(price_str)
    except Exception:
        pass

    logger.warning("Could not fetch price for %s from Jupiter or GeckoTerminal", mint[:12])
    return 0.0


def _simulate_slippage(tier: str, amount_sol: float = SLIPPAGE_REF_AMOUNT) -> float:
    """Return simulated slippage percentage accounting for position-size impact.

    FEE-MODEL-001 (2026-04-20): added amount_sol param + size exponent. BC price
    impact scales with position size; flat ranges understated live reality by ~10x.
    Legacy callers omitting amount_sol get the base range (no size scaling).
    """
    entry = SLIPPAGE_RANGES.get(tier, (0.5, 2.0, 0.3))
    # Backward compat: old 2-tuple entries default to exp=0.3 if somehow present.
    if len(entry) == 2:
        low, high = entry
        exp = 0.3
    else:
        low, high, exp = entry
    base = random.uniform(low, high)
    size_factor = (max(amount_sol, 0.001) / SLIPPAGE_REF_AMOUNT) ** exp
    return round(base * size_factor, 2)


def _simulate_fees(action: str, amount_sol: float, pool: str,
                   bonding_curve_progress: float = 0.0) -> dict:
    """Return simulated fees in SOL with per-component breakdown.

    FEE-MODEL-001 (2026-04-20): returns dict with platform/lp/priority/jito/total.
    Called once per side (buy or sell); priority + jito split in half so full
    round-trip sums correctly.

    Pre-grad path (pump.fun BC): platform fee only (1% each side by default);
    priority half of 0.001 SOL; Jito 0 until EXEC-005 lands.
    Post-grad path (Raydium / pumpswap / Jupiter): platform + LP fees (~0.25%
    each side for Raydium, or ~0.6% bundled for Jupiter); priority half of 0.002
    SOL; Jito half of 0.001 SOL.
    """
    is_pregrad = (bonding_curve_progress < GRADUATION_THRESHOLD
                  and pool in ("pump", "pump-amm", "auto", "launchlab", "bonk"))
    is_jupiter_pool = pool in ("raydium", "raydium-cpmm", "orca", "meteora", "pumpswap")

    # Platform fee (one side)
    if is_pregrad:
        platform = amount_sol * PAPER_FEE_PUMPFUN_PCT
    elif is_jupiter_pool:
        platform = amount_sol * PAPER_FEE_JUPITER_PCT
    else:
        # Post-grad on pump.fun (pump-amm after migration) — treat like Raydium
        platform = amount_sol * PAPER_FEE_RAYDIUM_PCT

    # LP fee (one side) — only on AMM pools (pre-grad BC has no separate LP)
    if is_pregrad:
        lp = 0.0
    elif is_jupiter_pool:
        lp = 0.0  # already bundled into PAPER_FEE_JUPITER_PCT
    else:
        lp = amount_sol * PAPER_FEE_RAYDIUM_PCT

    # Priority + Jito per-side (half of round-trip values)
    if is_pregrad:
        priority = PAPER_PRIORITY_FEE_PREGRAD_SOL / 2
        jito = PAPER_JITO_TIP_PREGRAD_SOL / 2  # 0.0 by default
    else:
        priority = PAPER_PRIORITY_FEE_POSTGRAD_SOL / 2
        jito = PAPER_JITO_TIP_POSTGRAD_SOL / 2

    total = platform + lp + priority + jito
    return {
        "platform": round(platform, 6),
        "lp": round(lp, 6),
        "priority": round(priority, 6),
        "jito": round(jito, 6),
        "total": round(total, 6),
        "pregrad": is_pregrad,
        "action": action,
    }


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
    rugcheck_risk: str = "unknown",
    bonding_curve_price: float = 0.0,
    bonding_curve_progress: float = 0.0,
) -> dict:
    """Simulate a paper buy trade. Returns result dict with fake signature."""
    # Get real price — Jupiter/Gecko primary, bonding curve fallback
    price = await _get_token_price(mint)
    if price <= 0 and bonding_curve_price > 0:
        price = bonding_curve_price
        logger.info("PAPER: using bonding curve price for %s: $%.10f", mint[:12], price)
    if price <= 0:
        logger.warning("PAPER: price fetch failed for %s — skipping", mint[:12])
        return {"success": False, "error": "price_fetch_failed", "simulated": True}

    # FEE-MODEL-001: simulate size-aware slippage + per-path fee breakdown.
    # Slippage pushes entry_price up (buy-side cost).
    slippage = _simulate_slippage(slippage_tier, amount_sol)
    entry_price = price * (1 + slippage / 100)

    fee_breakdown = _simulate_fees("buy", amount_sol, pool, bonding_curve_progress)
    fees = fee_breakdown["total"]
    net_amount = amount_sol - fees

    # Generate fake signature
    sig = f"PAPER_{uuid.uuid4().hex[:16]}"
    now = time.time()

    # Calculate market cap (pump.fun tokens = 1 billion supply)
    total_supply = 1_000_000_000
    market_cap = entry_price * total_supply if entry_price > 0 else 0

    # Store in PostgreSQL
    trade_id = await pg_pool.fetchval(
        """INSERT INTO paper_trades
           (mint, personality, entry_price, amount_sol, slippage_pct, fees_sol,
            entry_time, signal_source, ml_score, entry_signature,
            market_mode_at_entry, fear_greed_at_entry, rugcheck_risk, market_cap_at_entry,
            trade_mode)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
           RETURNING id""",
        mint, personality, entry_price, net_amount, slippage, fees,
        now, signal_source, ml_score, sig, market_mode, fear_greed, rugcheck_risk,
        market_cap, TRADE_MODE,
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
        "fee_breakdown": fee_breakdown,  # FEE-MODEL-001: per-component breakdown for analysis
        "simulated": True,
        # Determine which router would have been used
        # (bonding_curve_progress now received as kwarg; post-grad path triggered at >= 0.95)
        "router": "paper_mode",  # paper mode doesn't route — just logs
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
    exit_price_override: float = 0.0,
    pool: str = "auto",
    bonding_curve_progress: float = 0.0,
) -> dict:
    """Simulate a paper sell trade. Returns result dict with P/L.

    exit_price_override: caller (bot_core) should ALWAYS pass the current market
    price it already knows. This avoids a redundant Jupiter/Gecko fetch that fails
    on bonding-curve tokens and corrupts P/L records.
    """

    if exit_price_override > 0:
        current_price = exit_price_override
    else:
        # Fallback — caller should always pass exit_price_override.
        # Log a warning so we can track any remaining call sites that don't.
        logger.warning(
            "paper_sell called WITHOUT exit_price_override for %s — "
            "this is a bug, caller should always pass the price. "
            "Trying Redis fallback.", mint[:12]
        )
        # Try Redis cache (same source bot_core uses)
        if redis_conn:
            try:
                cached = await redis_conn.get(f"token:latest_price:{mint}")
                if cached:
                    current_price = float(cached)
                    logger.info("paper_sell: Redis fallback price for %s: %.10f", mint[:12], current_price)
                else:
                    current_price = 0.0
            except Exception:
                current_price = 0.0
        else:
            current_price = 0.0

        if current_price <= 0:
            logger.error("paper_sell: no price anywhere for %s — recording as breakeven", mint[:12])
            current_price = entry_price

    # FEE-MODEL-001: size-aware exit slippage; pre-grad vs post-grad tier by bc_progress.
    # Selling on BC / pool pushes price down (exit_price dips below current_price).
    sell_amount = amount_sol * sell_pct
    sell_tier = "sell" if bonding_curve_progress < GRADUATION_THRESHOLD else "sell_postgrad"
    slippage = _simulate_slippage(sell_tier, sell_amount)
    exit_price = current_price * (1 - slippage / 100)

    # Per-path fee breakdown (separate sell-side components).
    fee_breakdown = _simulate_fees("sell", sell_amount, pool, bonding_curve_progress)
    fees = fee_breakdown["total"]
    hold_seconds = time.time() - entry_time if entry_time > 0 else 0

    if entry_price > 0:
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        pnl_sol = (exit_price - entry_price) / entry_price * sell_amount - fees
    else:
        pnl_pct = 0.0
        pnl_sol = -fees

    outcome = "win" if pnl_sol > 0 else "loss"
    sig = f"PAPER_{uuid.uuid4().hex[:16]}"

    # Calculate exit market cap
    total_supply = 1_000_000_000
    market_cap_exit = exit_price * total_supply if exit_price > 0 else 0

    # Update PostgreSQL
    if trade_id:
        await pg_pool.execute(
            """UPDATE paper_trades SET exit_price=$1, exit_time=$2, hold_seconds=$3,
               realised_pnl_sol=$4, realised_pnl_pct=$5, exit_reason=$6, exit_signature=$7,
               market_cap_at_exit=$9, outcome=$10
               WHERE id=$8""",
            exit_price, time.time(), hold_seconds, pnl_sol, pnl_pct, reason, sig, trade_id,
            market_cap_exit, outcome,
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
        "fee_breakdown": fee_breakdown,  # FEE-MODEL-001: per-component breakdown
        "slippage_pct": slippage,
        "simulated": True,
        "router": "paper_mode",  # paper mode doesn't route — just logs
    }
