"""
ZMN Bot Market Health Detection Service
=========================================
- Daily 7:00 AM Sydney: comprehensive market health check
- Intraday every 5 min: rug cascade detection, SOL price shock, network congestion
- Publishes mode to Redis pub/sub "market:mode" and caches to "market:health" (5-min TTL)
- Trading session tracker: broadcasts current session to Redis "market:session"
- Emergency events -> "alerts:emergency" Redis channel
- All scheduled tasks use Australia/Sydney timezone (auto DST via pytz)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
import pytz
import redis.asyncio as aioredis
from dotenv import load_dotenv

from services.async_utils import supervise  # FIX-PUBSUB-ISOLATION

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("market_health")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "").strip()
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")

# --- Market mode thresholds ---
# Format: (mode, pumpfun_vol_24h_USD, migrations_per_hour, solana_dex_vol_24h_USD)
#
# MARKET-MODE-001 fix (2026-04-30): grad_rate column re-typed from "ratio"
# to "migrations per hour". Prior behavior:
#   - signal_aggregator wrote market:grad_rate_estimate as `migrations /
#     new_tokens` (a ratio typically ~0.0001 in steady state)
#   - market_health thresholds (0.5/0.8/1.0/1.5) assumed migrations-per-hour
#   - Definition mismatch -> ratio (always tiny) never beat any threshold ->
#     HIBERNATE-forever for ~weeks
# Fix: read market:migration_count_1h directly (signal_aggregator's existing
# rolling counter) + recalibrate thresholds against current Solana baseline.
#
# Calibration sample 2026-04-30 13:26 UTC:
#   - dex_vol=$1.4B, migrations/hr=73, pumpfun_vol=$209M
#   - Expected mode under new thresholds: NORMAL (active baseline market)
# Calibration intent:
#   - HIBERNATE only fires under genuine outage / dead market
#   - DEFENSIVE under sustained quiet (low new_tokens or migrations)
#   - NORMAL under typical conditions
#   - AGGRESSIVE / FRENZY under elevated volume + grad activity
# pumpfun_vol_estimate is still a 15% slice of dex_vol (TODO: PumpPortal stats
# API for true volume).
MARKET_MODES = [
    ("FRENZY",     400e6, 200, 4e9),
    ("AGGRESSIVE", 200e6, 100, 2e9),
    ("NORMAL",     100e6,  30, 1e9),
    ("DEFENSIVE",   50e6,  10, 500e6),
    ("HIBERNATE",      0,   0, 0),
]

# --- API URLs ---
DEFILLAMA_URL = "https://api.llama.fi/overview/dexs/Solana"
CFGI_URL = "https://cfgi.io/api/solana-fear-greed-index/1d"
JUPITER_PRICE_URL = "https://api.jup.ag/price/v3"
SOL_MINT = "So11111111111111111111111111111111111111112"

# --- Sydney timezone (auto DST: AEDT UTC+11 / AEST UTC+10) ---
SYDNEY_TZ = pytz.timezone("Australia/Sydney")


def get_sydney_time():
    """Get current time in Sydney (handles DST automatically)."""
    return datetime.now(pytz.utc).astimezone(SYDNEY_TZ)


def sydney_to_utc(hour, minute=0):
    """Convert a Sydney local time to UTC for scheduling."""
    sydney_now = get_sydney_time()
    naive = sydney_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    sydney_target = SYDNEY_TZ.localize(naive.replace(tzinfo=None))
    return sydney_target.astimezone(pytz.utc)


def get_current_session_sydney() -> tuple[str, str]:
    """Return (session_name, quality) based on current Sydney time."""
    h = get_sydney_time().hour
    if 7 <= h < 16:
        return "ASIAN", "moderate"
    elif 16 <= h < 20:
        return "TRANSITION", "low"
    elif 20 <= h < 24:
        return "EU_OPEN", "good"
    elif 0 <= h < 4:
        return "EU_US_OVERLAP", "peak"
    elif 4 <= h < 7:
        return "US_ONLY", "good"
    else:
        return "DEAD_ZONE", "avoid"

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
# FIX-MARKET-MODE-MISCLASSIFICATION: last-good DefiLlama dex volume so a transient
# API failure does not zero the dex leg and force a spurious HIBERNATE.
_last_dex_vol: float | None = None
_last_dex_vol_time: float = 0.0
_LAST_DEX_VOL_MAX_AGE = 3600.0  # seconds; use last-good only if fresher than this


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
    """Fetch SOL price -- tries multiple sources, no single point of failure."""
    sources = [
        ("Binance", "https://api.binance.com/api/v3/ticker/price", {"symbol": "SOLUSDT"}, lambda d: float(d.get("price", 0)) or None),
        ("CoinGecko", "https://api.coingecko.com/api/v3/simple/price", {"ids": "solana", "vs_currencies": "usd"}, lambda d: d.get("solana", {}).get("usd")),
    ]
    for name, url, params, extract in sources:
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = extract(data)
                    if price and float(price) > 0:
                        logger.debug("SOL price from %s: $%.2f", name, float(price))
                        return float(price)
                else:
                    logger.debug("%s HTTP %d", name, resp.status)
        except Exception as e:
            logger.debug("%s error: %s", name, e)

    # Last resort: Jupiter V3 (requires API key)
    try:
        headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
        async with session.get(JUPITER_PRICE_URL, params={"ids": SOL_MINT}, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                sol_data = data.get("data", {}).get(SOL_MINT, {})
                price = sol_data.get("usdPrice") or sol_data.get("price")
                if price:
                    return float(price)
    except Exception as e:
        logger.warning("All SOL price sources failed. Last: %s", e)

    return None


async def _fetch_defillama(session: aiohttp.ClientSession) -> float | None:
    """Returns Solana DEX 24h volume in USD, or None if unavailable.

    FIX-MARKET-MODE-MISCLASSIFICATION (FULL-CODE-AUDIT D07-F4): returns None
    (sentinel = "unknown"), NOT 0.0, on any failure/unexpected shape. A 0.0 here
    used to zero the dex leg AND the derived pumpfun leg, force-vetoing the market
    to HIBERNATE on a mere API blip — conflating a data outage with a dead market.
    The caller treats None as unknown (last-good fallback, then abstain).
    """
    try:
        data = await _fetch_json(session, DEFILLAMA_URL)
        if data and "totalDataChart" in data:
            chart = data.get("totalDataChart", [])
            if chart and len(chart[-1]) > 1:
                return float(chart[-1][1])
        if data and "total24h" in data:
            return float(data["total24h"])
    except Exception as e:
        logger.warning("DefiLlama fetch failed: %s", e)
    return None


async def _fetch_cfgi(session: aiohttp.ClientSession) -> float:
    """Returns crypto Fear & Greed Index (0-100) from Alternative.me.
    cfgi.io is defunct (404 confirmed) — removed to stop noisy log spam."""
    try:
        data = await _fetch_json(session, "https://api.alternative.me/fng/?limit=1")
        if data and isinstance(data, dict):
            entries = data.get("data", [])
            if entries and isinstance(entries, list):
                val = entries[0].get("value")
                if val is not None:
                    return float(val)
    except Exception as e:
        logger.debug("Alternative.me F&G fetch failed: %s", e)
    return 50.0


async def _fetch_cfgi_io_solana(session: aiohttp.ClientSession) -> float | None:
    """Fetch Solana-specific CFGI from cfgi.io v2 API.

    Returns cfgi value 0-100 or None on any failure.
    Written to market:health.cfgi_sol (NOT .cfgi) so existing readers are unaffected.
    """
    api_key = os.environ.get("CFGI_API_KEY")
    if not api_key:
        return None

    url = "https://cfgi.io/api/api_request_v2.php"
    params = {
        "api_key": api_key,
        "token": "SOL",
        "period": 2,      # 1h granularity
        "values": 1,       # most recent value only
        "fields": "cfgi",  # just the aggregate score
    }

    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.warning("cfgi.io returned HTTP %d", resp.status)
                return None
            data = await resp.json(content_type=None)
            if isinstance(data, list) and len(data) > 0:
                cfgi = data[0].get("cfgi")
                if cfgi is not None:
                    logger.info("cfgi.io SOL CFGI: %s", cfgi)
                    return float(cfgi)
            logger.warning("cfgi.io unexpected response shape: %s", data)
            return None
    except asyncio.TimeoutError:
        logger.warning("cfgi.io request timed out after 10s")
        return None
    except Exception as e:
        logger.warning("cfgi.io fetch failed: %s", e)
        return None


async def _fetch_priority_fee(session: aiohttp.ClientSession) -> dict:
    """Fetch priority fee estimate from Helius (gatekeeper fallback)."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getPriorityFeeEstimate",
        "params": [{"options": {"includeAllPriorityFeeLevels": True}}],
    }
    for rpc_url in (HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
        if not rpc_url:
            continue
        try:
            async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("result", {}).get("priorityFeeLevels", {})
        except Exception as e:
            logger.warning("Priority fee fetch failed on %s: %s", rpc_url[:40], e)
    return {}


def _determine_market_mode(dex_vol: float | None, grad_rate: float | None, pumpfun_vol: float | None = None) -> str:
    """Determine market mode from thresholds. Check from highest to lowest.

    FIX-MARKET-MODE-MISCLASSIFICATION (FULL-CODE-AUDIT D07-F1/F3/F4/F7,
    MARKET-MODE-001-RE-CALIBRATE-002): the prior 3-leg AND conflated MISSING DATA
    with a DEAD MARKET — an absent migration counter (grad_rate defaulted to 0) or
    a DefiLlama blip (dex_vol coerced to 0) single-leg-vetoed an otherwise-healthy
    market straight to HIBERNATE. That is the 2026-05-28 outage misclassification.

    New rules:
      * dex_vol (DefiLlama, the one real volume signal) is the binding leg.
      * An UNKNOWN grad_rate (None — counter absent / redis error) ABSTAINS: it
        does not veto. A KNOWN grad_rate (including a genuine 0) is still enforced.
        => a transiently-starved migration counter no longer forces HIBERNATE.
      * pumpfun_vol is NO LONGER a binding leg. It was a fabricated 0.15*dex_vol
        placeholder (collinear with dex_vol, never the binding constraint at the
        tier boundaries); it is kept only as a labelled estimate in published
        state. The param is retained for signature/backward compat and ignored.
      * dex_vol UNKNOWN (None, even after last-good fallback) => DEFENSIVE, NOT
        HIBERNATE. A total data outage is degraded-cautious-but-trading, never
        block-everything. (Genuine low volume still falls through to HIBERNATE.)
    """
    if dex_vol is None:
        # No real volume signal at all -> degraded, not a confirmed dead market.
        return "DEFENSIVE"
    for mode, pf_thresh, gr_thresh, dex_thresh in MARKET_MODES:
        dex_ok = dex_vol >= dex_thresh
        grad_ok = (grad_rate is None) or (grad_rate >= gr_thresh)  # unknown abstains
        if dex_ok and grad_ok:
            return mode
    return "HIBERNATE"


def _compute_sentiment_score(cfgi: float, grad_rate: float, sol_24h_change: float, dex_vol: float, launch_rate: float) -> float:
    """Composite sentiment score 0-100 per Section 8."""
    # Scale inputs to 0-100 range
    cfgi_scaled = max(0, min(100, cfgi))

    # MARKET-MODE-001 fix (2026-04-30): grad_rate is now migrations-per-hour
    # (was ratio). Baseline ~50/hr, saturates around 200/hr. Old scaling
    # `grad_rate * 50` was calibrated for a 0-2 ratio range -> 0-100.
    grad_scaled = max(0, min(100, grad_rate * 0.5))

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

    if not redis_conn:
        return

    # Publish mode change (even in TEST_MODE — bot_core needs market mode for paper trading)
    await redis_conn.publish("market:mode", json.dumps(state))
    # Cache with 5-min TTL
    await redis_conn.set("market:health", json.dumps(state), ex=300)
    # Store mode as a simple key for bot_core startup check
    await redis_conn.set("market:mode:current", state["mode"])
    # Keep market:sol_price in sync (bot_core exit checker reads this)
    sol_price = state.get("sol_price")
    if sol_price and float(sol_price) > 0:
        await redis_conn.set("market:sol_price", str(sol_price), ex=300)


async def _publish_emergency(redis_conn: aioredis.Redis | None, reason: str):
    logger.critical("EMERGENCY: %s", reason)
    if not redis_conn:
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
    global _last_dex_vol, _last_dex_vol_time

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

                # FIX-MARKET-MODE-MISCLASSIFICATION: dex_vol is None when DefiLlama
                # failed (sentinel, not 0.0). Fall back to last-good if fresh; else
                # leave UNKNOWN. Never coerce to 0 (that would force HIBERNATE).
                data_degraded = False
                if dex_vol is not None:
                    _last_dex_vol = dex_vol
                    _last_dex_vol_time = now
                elif _last_dex_vol is not None and (now - _last_dex_vol_time) < _LAST_DEX_VOL_MAX_AGE:
                    logger.warning(
                        "DefiLlama unavailable — using last-good dex_vol=%.0f (age %.0fs)",
                        _last_dex_vol, now - _last_dex_vol_time,
                    )
                    dex_vol = _last_dex_vol
                    data_degraded = True
                else:
                    logger.warning("DefiLlama unavailable and no fresh last-good — dex_vol UNKNOWN (will not force HIBERNATE)")
                    data_degraded = True

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

                # pumpfun_vol_estimate is kept as a LABELLED observability estimate
                # only — it is NO LONGER a binding classifier leg (was a fabricated
                # 0.15*dex_vol placeholder, collinear with dex_vol). See
                # _determine_market_mode. None when dex_vol is unknown.
                pumpfun_vol_estimate = (dex_vol * 0.15) if dex_vol is not None else None
                # FIX-MARKET-MODE-MISCLASSIFICATION: distinguish an ABSENT migration
                # counter (unknown -> None -> ABSTAINS in the classifier, does not
                # veto) from a genuine 0. `if mig_raw:` would treat "0" as absent
                # too, so test `is not None`. The 2026-05-28 outage was exactly this:
                # a pubsub-crash-starved counter defaulted to 0 and force-vetoed a
                # healthy $1.75B market to HIBERNATE. Absent != dead market.
                grad_rate_estimate = None
                if redis_conn:
                    try:
                        mig_raw = await redis_conn.get("market:migration_count_1h")
                        if mig_raw is not None:
                            grad_rate_estimate = float(mig_raw)
                        else:
                            logger.warning("market:migration_count_1h absent — grad_rate UNKNOWN (abstaining, not forcing HIBERNATE)")
                            data_degraded = True
                    except Exception as e:
                        logger.warning("market:migration_count_1h read failed: %s — grad_rate UNKNOWN", e)
                        data_degraded = True

                # Check for manual override (set via POST /api/market-mode-override)
                override = None
                if redis_conn:
                    try:
                        override = await redis_conn.get("market:mode:override")
                    except Exception:
                        pass
                if override and override.upper() in ("NORMAL", "AGGRESSIVE", "DEFENSIVE", "FRENZY", "HIBERNATE"):
                    mode = override.upper()
                    logger.info("Market mode OVERRIDE active: %s", mode)
                else:
                    mode = _determine_market_mode(dex_vol, grad_rate_estimate, pumpfun_vol_estimate)
                # Stage 2: cfgi.io SOL is PRIMARY, Alternative.me BTC is fallback
                cfgi_sol = None
                try:
                    cfgi_sol = await _fetch_cfgi_io_solana(session)
                except Exception as e:
                    logger.warning("cfgi.io fetch failed (non-fatal): %s", e)

                # Primary CFGI = SOL (cfgi.io), fallback to BTC (Alternative.me)
                primary_cfgi = cfgi_sol if cfgi_sol is not None else cfgi
                # None-safe: grad_rate/dex_vol may be unknown (None) now.
                sentiment = _compute_sentiment_score(
                    primary_cfgi, grad_rate_estimate or 0.0, sol_24h_change, dex_vol or 0.0, 0,
                )

                state = {
                    "mode": mode,
                    "sentiment_score": sentiment,
                    "sol_price": sol_price,
                    "sol_1h_change": round(sol_1h_change, 4),
                    "sol_24h_change": round(sol_24h_change, 4),
                    "dex_volume_24h": dex_vol,
                    "cfgi": primary_cfgi,
                    "cfgi_btc": cfgi,
                    "pumpfun_vol_estimate": pumpfun_vol_estimate,
                    "data_degraded": data_degraded,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                if cfgi_sol is not None:
                    state["cfgi_sol"] = cfgi_sol
                    state["cfgi_sol_source"] = "cfgi.io"
                    state["cfgi_sol_timestamp"] = datetime.now(timezone.utc).isoformat()
                await _publish_market_state(redis_conn, state)

                # --- Broadcast current trading session (Sydney time) ---
                session_name, session_quality = get_current_session_sydney()
                syd = get_sydney_time()
                session_data = {
                    "session": session_name,
                    "quality": session_quality,
                    "sydney_time": syd.strftime("%H:%M %Z"),
                    "sydney_hour": syd.hour,
                }
                if redis_conn:
                    await redis_conn.set("market:session", json.dumps(session_data), ex=300)

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
    Detect rug cascade events by monitoring recent stop-loss exits.
    If >= 5 tokens hit stop-loss in the last 30 minutes, emit defensive alert.
    """
    if not redis_conn:
        return

    RUG_CASCADE_THRESHOLD = int(os.getenv("RUG_CASCADE_THRESHOLD", "5"))
    RUG_CASCADE_WINDOW_MINUTES = 30
    COOLDOWN_SECONDS = 3600
    last_alert_time = 0.0

    while True:
        await asyncio.sleep(300)
        try:
            import time as _t
            now = _t.time()
            if now - last_alert_time < COOLDOWN_SECONDS:
                continue

            from services.db import get_pool
            pool = await get_pool()
            window_start = now - (RUG_CASCADE_WINDOW_MINUTES * 60)

            count = await pool.fetchval(
                """SELECT COUNT(*) FROM paper_trades
                   WHERE exit_time > $1
                   AND realised_pnl_sol < 0
                   AND exit_reason LIKE 'stop_loss%'""",
                window_start,
            )

            if count and count >= RUG_CASCADE_THRESHOLD:
                reason = f"Rug cascade detected: {count} stop-loss exits in {RUG_CASCADE_WINDOW_MINUTES}min"
                logger.warning(reason)
                await redis_conn.publish("alerts:emergency", json.dumps({
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
                await redis_conn.set("market:loss_override", "DEFENSIVE", ex=3600)
                last_alert_time = now
            else:
                logger.debug("Rug cascade check: %s stop-loss exits in last %dmin (threshold: %d)",
                             count or 0, RUG_CASCADE_WINDOW_MINUTES, RUG_CASCADE_THRESHOLD)
        except Exception as e:
            logger.warning("Rug cascade check error: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    from services.sentry_init import init_sentry
    init_sentry("market-health")
    logger.info("Market Health service starting (TEST_MODE=%s)", TEST_MODE)

    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5, socket_keepalive=True, health_check_interval=30, retry_on_timeout=True)
        await redis_conn.ping()
        logger.info("Redis connected: %s", REDIS_URL)
    except Exception as e:
        logger.warning("Redis connection failed: %s -- market health will log only", e)
        redis_conn = None

    # FIX-PUBSUB-ISOLATION: supervise each loop (backstop — both self-heal today).
    await asyncio.gather(
        supervise(lambda: daily_health_check(redis_conn), "daily_health_check"),
        supervise(lambda: rug_cascade_monitor(redis_conn), "rug_cascade_monitor"),
    )


if __name__ == "__main__":
    asyncio.run(main())
