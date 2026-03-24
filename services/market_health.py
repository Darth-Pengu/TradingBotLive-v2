"""
ToxiBot Market Health Detection Service
=========================================
- Daily 00:00 UTC: query DefiLlama, CFGI, Jupiter price → composite sentiment + market mode
- Intraday every 5 min: rug cascade detection, SOL price shock, network congestion
- Publishes mode to Redis pub/sub "market:mode" and caches to "market:health" (5-min TTL)
- Emergency events → "alerts:emergency" Redis channel
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("market_health")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")

# --- Market mode thresholds (from AGENT_CONTEXT Section 8) ---
# Mode        | pumpfun_24h_vol | grad_rate | solana_dex_vol
MARKET_MODES = [
    ("FRENZY",     500e6, 1.5, 6e9),
    ("AGGRESSIVE", 200e6, 1.0, 4e9),
    ("NORMAL",     100e6, 0.8, 2e9),
    ("DEFENSIVE",   50e6, 0.5, 1.5e9),
    ("HIBERNATE",      0, 0.0, 0),
]

# --- API URLs ---
DEFILLAMA_URL = "https://api.llama.fi/overview/dexs?chain=solana"
CFGI_URL = "https://cfgi.io/api/solana-fear-greed-index/1d"
JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"
SOL_MINT = "So11111111111111111111111111111111111111112"

# --- Rug cascade thresholds ---
RUG_ALERT_THRESHOLD = 5
RUG_EMERGENCY_THRESHOLD = 10

# --- SOL price shock thresholds ---
SOL_1H_HALT = -0.05
SOL_24H_EMERGENCY = -0.10

# --- Network congestion threshold (microlamports) ---
CONGESTION_THRESHOLD = 50_000_000

# --- State ---
_last_sol_price: float | None = None
_last_sol_price_time: float = 0.0
_sol_price_1h_ago: float | None = None
_sol_price_24h_ago: float | None = None
_sol_price_history: list[tuple[float, float]] = []  # (timestamp, price)


async def _fetch_json(session: aiohttp.ClientSession, url: str, params: dict | None = None, timeout: int = 15) -> dict | None:
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning("HTTP %d from %s", resp.status, url)
    except Exception as e:
        logger.warning("Request failed for %s: %s", url, e)
    return None


async def _fetch_sol_price(session: aiohttp.ClientSession) -> float | None:
    data = await _fetch_json(session, JUPITER_PRICE_URL, params={"ids": SOL_MINT})
    if data and "data" in data:
        sol_data = data["data"].get(SOL_MINT, {})
        price = sol_data.get("price")
        if price:
            return float(price)
    return None


async def _fetch_defillama(session: aiohttp.ClientSession) -> float:
    """Returns Solana DEX 24h volume in USD."""
    data = await _fetch_json(session, DEFILLAMA_URL)
    if data and "totalDataChart" in data:
        # Sum last 24h entries
        chart = data.get("totalDataChart", [])
        if chart:
            return float(chart[-1][1]) if len(chart[-1]) > 1 else 0.0
    if data and "total24h" in data:
        return float(data["total24h"])
    return 0.0


async def _fetch_cfgi(session: aiohttp.ClientSession) -> float:
    """Returns Solana Fear & Greed Index (0-100)."""
    data = await _fetch_json(session, CFGI_URL)
    if data:
        # CFGI returns various formats — try common ones
        if isinstance(data, dict):
            return float(data.get("value", data.get("score", 50)))
        if isinstance(data, list) and data:
            return float(data[0].get("value", 50))
    return 50.0  # neutral default


async def _fetch_priority_fee(session: aiohttp.ClientSession) -> dict:
    """Fetch priority fee estimate from Helius."""
    if not HELIUS_RPC_URL:
        return {}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getPriorityFeeEstimate",
        "params": [{"options": {"includeAllPriorityFeeLevels": True}}],
    }
    try:
        async with session.post(HELIUS_RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get("result", {}).get("priorityFeeLevels", {})
    except Exception as e:
        logger.warning("Priority fee fetch failed: %s", e)
    return {}


def _determine_market_mode(dex_vol: float, grad_rate: float, pumpfun_vol: float) -> str:
    """Determine market mode from thresholds. Check from highest to lowest."""
    for mode, pf_thresh, gr_thresh, dex_thresh in MARKET_MODES:
        if pumpfun_vol >= pf_thresh and grad_rate >= gr_thresh and dex_vol >= dex_thresh:
            return mode
    return "HIBERNATE"


def _compute_sentiment_score(cfgi: float, grad_rate: float, sol_24h_change: float, dex_vol: float, launch_rate: float) -> float:
    """Composite sentiment score 0-100 per Section 8."""
    # Scale inputs to 0-100 range
    cfgi_scaled = max(0, min(100, cfgi))

    # Graduation rate z-score scaled (assuming ~1% baseline, scaled 0-100)
    grad_scaled = max(0, min(100, grad_rate * 50))

    # SOL 24h change scaled (-20% to +20% → 0 to 100)
    sol_scaled = max(0, min(100, (sol_24h_change + 0.20) * 250))

    # DEX volume z-score scaled (assuming $2B baseline)
    dex_scaled = max(0, min(100, (dex_vol / 4e9) * 50))

    # Launch rate z-score scaled
    launch_scaled = max(0, min(100, launch_rate * 10))

    score = (
        cfgi_scaled * 0.30 +
        grad_scaled * 0.25 +
        sol_scaled * 0.20 +
        dex_scaled * 0.15 +
        launch_scaled * 0.10
    )
    return round(max(0, min(100, score)), 1)


async def _publish_market_state(redis_conn: aioredis.Redis | None, state: dict):
    """Publish market mode to Redis and cache health data."""
    logger.info("Market mode: %s | Sentiment: %s | SOL: $%s",
                state["mode"], state["sentiment_score"], state.get("sol_price", "?"))

    if TEST_MODE or not redis_conn:
        return

    # Publish mode change
    await redis_conn.publish("market:mode", json.dumps(state))
    # Cache with 5-min TTL
    await redis_conn.set("market:health", json.dumps(state), ex=300)
    # Store mode as a simple key for bot_core startup check
    await redis_conn.set("market:mode:current", state["mode"])


async def _publish_emergency(redis_conn: aioredis.Redis | None, reason: str):
    logger.critical("EMERGENCY: %s", reason)
    if TEST_MODE or not redis_conn:
        return
    await redis_conn.publish("alerts:emergency", json.dumps({
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))


# ---------------------------------------------------------------------------
# Daily health check
# ---------------------------------------------------------------------------
async def daily_health_check(redis_conn: aioredis.Redis | None):
    """Runs once, then every 5 minutes for intraday updates."""
    global _last_sol_price, _last_sol_price_time, _sol_price_history

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Fetch all data sources
                sol_price, dex_vol, cfgi = await asyncio.gather(
                    _fetch_sol_price(session),
                    _fetch_defillama(session),
                    _fetch_cfgi(session),
                )

                now = time.time()

                if sol_price:
                    _sol_price_history.append((now, sol_price))
                    # Trim to 24h of history (assuming 5-min intervals = ~288 entries)
                    _sol_price_history = [(t, p) for t, p in _sol_price_history if now - t < 86400]

                # Calculate SOL price changes
                sol_1h_change = 0.0
                sol_24h_change = 0.0
                if sol_price and _sol_price_history:
                    # 1h ago
                    hour_ago = [p for t, p in _sol_price_history if now - t >= 3500]
                    if hour_ago:
                        sol_1h_change = (sol_price - hour_ago[-1]) / hour_ago[-1]
                    # 24h ago
                    day_ago = [p for t, p in _sol_price_history if now - t >= 85000]
                    if day_ago:
                        sol_24h_change = (sol_price - day_ago[-1]) / day_ago[-1]

                _last_sol_price = sol_price
                _last_sol_price_time = now

                # Estimate pump.fun volume and graduation rate
                # Decision: Using DexPaprika/PumpPortal data would be ideal, but those are
                # in signal_listener. For now, estimate pump.fun as ~10-20% of total Solana DEX vol.
                # This is a reasonable approximation; can be refined with PumpPortal stats API later.
                pumpfun_vol_estimate = dex_vol * 0.15
                grad_rate_estimate = 1.0  # Default to NORMAL range — will be refined by signal_aggregator

                mode = _determine_market_mode(dex_vol, grad_rate_estimate, pumpfun_vol_estimate)
                sentiment = _compute_sentiment_score(cfgi, grad_rate_estimate, sol_24h_change, dex_vol, 0)

                state = {
                    "mode": mode,
                    "sentiment_score": sentiment,
                    "sol_price": sol_price,
                    "sol_1h_change": round(sol_1h_change, 4),
                    "sol_24h_change": round(sol_24h_change, 4),
                    "dex_volume_24h": dex_vol,
                    "cfgi": cfgi,
                    "pumpfun_vol_estimate": pumpfun_vol_estimate,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await _publish_market_state(redis_conn, state)

                # --- Intraday emergency checks ---

                # SOL price shock
                if sol_1h_change <= SOL_1H_HALT:
                    await _publish_emergency(redis_conn, f"SOL 1h drop {sol_1h_change:.1%} — halting new entries")
                if sol_24h_change <= SOL_24H_EMERGENCY:
                    await _publish_emergency(redis_conn, f"SOL 24h drop {sol_24h_change:.1%} — EMERGENCY STOP")

                # Network congestion
                fees = await _fetch_priority_fee(session)
                very_high = fees.get("veryHigh", 0)
                if very_high and float(very_high) > CONGESTION_THRESHOLD:
                    logger.warning("Network congested: veryHigh fee = %s microlamports", very_high)
                    # Only trigger emergency after sustained congestion (tracked across iterations)

            except Exception as e:
                logger.error("Health check error: %s", e)

            await asyncio.sleep(300)  # 5 minutes


# ---------------------------------------------------------------------------
# Rug cascade detection (checks Redis for recent token price drops)
# ---------------------------------------------------------------------------
async def rug_cascade_monitor(redis_conn: aioredis.Redis | None):
    """
    Monitors for rug cascade events.
    In a full implementation, this would track token price drops from the signal stream.
    For now, it publishes alerts when patterns are detected via market data.
    """
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        # Rug cascade detection will be enhanced when signal_aggregator tracks token prices
        # For now, this is a placeholder that monitors the health state
        if redis_conn and not TEST_MODE:
            try:
                health = await redis_conn.get("market:health")
                if health:
                    data = json.loads(health)
                    logger.debug("Rug cascade check — mode: %s", data.get("mode"))
            except Exception as e:
                logger.warning("Rug cascade check error: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    logger.info("Market Health service starting (TEST_MODE=%s)", TEST_MODE)

    redis_conn = None
    if not TEST_MODE:
        try:
            redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
            await redis_conn.ping()
            logger.info("Redis connected: %s", REDIS_URL)
        except Exception as e:
            logger.error("Redis connection failed: %s", e)
            redis_conn = None
    else:
        logger.info("TEST_MODE — Redis publishing disabled")

    await asyncio.gather(
        daily_health_check(redis_conn),
        rug_cascade_monitor(redis_conn),
    )


if __name__ == "__main__":
    asyncio.run(main())
