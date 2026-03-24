"""
ToxiBot Signal Aggregator
===========================
Layer 3 of the signal stack:
- Deduplicates by token address within 60-second window
- Multi-source confidence: base 50 + 15 per additional source
- Applies market mode multiplier (HIBERNATE → skip all)
- Applies bonding curve filter (reject 30-55% KOTH zone for Speed Demon unless ML >= 85%)
- Routes through ML gate before forwarding to execution
- Enriches signals with Rugcheck safety data
- Outputs scored signals to Redis "signals:scored" for bot_core consumption
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
logger = logging.getLogger("signal_aggregator")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
RUGCHECK_API_KEY = os.getenv("RUGCHECK_API_KEY", "")
BITQUERY_API_KEY = os.getenv("BITQUERY_API_KEY", "")
VYBE_API_KEY = os.getenv("VYBE_API_KEY", "")

# --- Deduplication ---
DEDUP_WINDOW_SECONDS = 60
_seen_tokens: dict[str, dict] = {}  # mint -> {first_seen, sources, signal_data}
SEEN_CLEANUP_INTERVAL = 300

# --- Confidence scoring ---
BASE_CONFIDENCE = 50
PER_SOURCE_BONUS = 15

# --- Bonding curve KOTH zone (Section 3) ---
KOTH_ZONE_LOW = 0.30
KOTH_ZONE_HIGH = 0.55
KOTH_ML_OVERRIDE = 85  # ML >= 85% can override KOTH zone rejection

# --- Hard filters for Speed Demon (Section 3) ---
SPEED_DEMON_FILTERS = {
    "min_liquidity_sol": 5,
    "max_bundle_detected": False,
    "max_bundled_supply_pct": 10,
    "max_bot_transaction_ratio": 0.60,
    "max_fresh_wallet_ratio": 0.40,
}

# --- Analyst filters (Section 3) ---
ANALYST_FILTERS = {
    "min_liquidity_sol": 10,
    "min_sources": 2,
}

# --- Rugcheck ---
RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary"

# --- ML thresholds (Section 12) ---
ML_THRESHOLDS = {
    "speed_demon": 65,
    "analyst": 70,
    "whale_tracker": 70,
}


async def _fetch_rugcheck(session: aiohttp.ClientSession, mint: str) -> dict:
    """Fetch token safety report from Rugcheck."""
    url = RUGCHECK_URL.format(mint=mint)
    headers = {}
    if RUGCHECK_API_KEY:
        headers["Authorization"] = f"Bearer {RUGCHECK_API_KEY}"
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.debug("Rugcheck HTTP %d for %s", resp.status, mint[:12])
    except Exception as e:
        logger.debug("Rugcheck error for %s: %s", mint[:12], e)
    return {}


async def _fetch_token_details(session: aiohttp.ClientSession, mint: str) -> dict:
    """Fetch additional token details from available APIs."""
    details = {}

    # Try BitQuery for holder/volume data
    if BITQUERY_API_KEY:
        try:
            query = """
            {
              Solana {
                DEXTradeByTokens(
                  where: {Trade: {Currency: {MintAddress: {is: "%s"}}}}
                  limit: {count: 1}
                ) {
                  Trade {
                    Currency { MintAddress Name }
                    Amount
                  }
                  count
                }
              }
            }
            """ % mint
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {BITQUERY_API_KEY}",
            }
            async with session.post(
                "https://streaming.bitquery.io/graphql",
                json={"query": query},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    trades = data.get("data", {}).get("Solana", {}).get("DEXTradeByTokens", [])
                    if trades:
                        details["trade_count"] = trades[0].get("count", 0)
        except Exception as e:
            logger.debug("BitQuery error for %s: %s", mint[:12], e)

    return details


def _compute_confidence(sources: set[str]) -> int:
    """Multi-source confidence: base 50 + 15 per additional source."""
    return BASE_CONFIDENCE + max(0, (len(sources) - 1)) * PER_SOURCE_BONUS


def _classify_target_personalities(signal: dict, rugcheck: dict) -> list[str]:
    """Determine which personalities this signal should be routed to."""
    targets = []
    age = signal.get("age_seconds", 0)
    sig_type = signal.get("signal_type", "")

    # Speed Demon: new tokens, 0-30s (alpha), 30s-3min (confirmation), 5-15min post-grad
    if sig_type in ("new_token", "new_pool") and age <= 180:
        targets.append("speed_demon")
    elif sig_type == "migration" and 300 <= age <= 900:
        targets.append("speed_demon")  # Post-grad dip tier

    # Analyst: confirmed tokens, multi-source signals
    if sig_type in ("new_pool", "token_trade", "sse_event", "migration"):
        targets.append("analyst")

    # Whale Tracker: account trades from tracked wallets
    if sig_type == "account_trade":
        targets.append("whale_tracker")

    return targets


def _apply_hard_filters(personality: str, signal: dict, rugcheck: dict) -> tuple[bool, str]:
    """
    Apply personality-specific hard filters.
    Returns (pass, reason) — if pass is False, reason explains why.
    """
    raw = signal.get("raw_data", {})
    bc_progress = raw.get("bondingCurveProgress", raw.get("bonding_curve_progress", 0))
    if isinstance(bc_progress, str):
        try:
            bc_progress = float(bc_progress)
        except ValueError:
            bc_progress = 0

    if personality == "speed_demon":
        liq = raw.get("liquidity_sol", raw.get("vSolInBondingCurve", 0))
        if isinstance(liq, str):
            try:
                liq = float(liq)
            except ValueError:
                liq = 0
        if liq < SPEED_DEMON_FILTERS["min_liquidity_sol"]:
            return False, f"liquidity {liq} < {SPEED_DEMON_FILTERS['min_liquidity_sol']}"

        if raw.get("bundle_detected", False):
            return False, "bundle detected"

        bundled_pct = raw.get("bundled_supply_pct", 0)
        if bundled_pct > SPEED_DEMON_FILTERS["max_bundled_supply_pct"]:
            return False, f"bundled supply {bundled_pct}% > {SPEED_DEMON_FILTERS['max_bundled_supply_pct']}%"

        bot_ratio = raw.get("bot_transaction_ratio", 0)
        if bot_ratio > SPEED_DEMON_FILTERS["max_bot_transaction_ratio"]:
            return False, f"bot ratio {bot_ratio} > {SPEED_DEMON_FILTERS['max_bot_transaction_ratio']}"

        fresh_ratio = raw.get("fresh_wallet_ratio", 0)
        if fresh_ratio > SPEED_DEMON_FILTERS["max_fresh_wallet_ratio"]:
            return False, f"fresh wallet ratio {fresh_ratio} > {SPEED_DEMON_FILTERS['max_fresh_wallet_ratio']}"

    if personality == "analyst":
        liq = raw.get("liquidity_sol", 0)
        if isinstance(liq, str):
            try:
                liq = float(liq)
            except ValueError:
                liq = 0
        if liq < ANALYST_FILTERS["min_liquidity_sol"]:
            return False, f"liquidity {liq} < {ANALYST_FILTERS['min_liquidity_sol']}"

    # Rugcheck safety gate (all personalities)
    risk_level = rugcheck.get("riskLevel", rugcheck.get("score", ""))
    if risk_level in ("danger", "high"):
        return False, f"rugcheck risk: {risk_level}"

    return True, ""


def _check_koth_zone(bc_progress: float, personality: str, ml_score: float) -> tuple[bool, str]:
    """Check if token is in KOTH dump zone (30-55% bonding curve)."""
    if personality == "speed_demon" and KOTH_ZONE_LOW <= bc_progress <= KOTH_ZONE_HIGH:
        if ml_score >= KOTH_ML_OVERRIDE:
            return True, f"KOTH zone but ML {ml_score} >= {KOTH_ML_OVERRIDE}"
        return False, f"KOTH zone ({bc_progress:.0%}) — ML {ml_score} < {KOTH_ML_OVERRIDE}"

    if personality == "analyst":
        # Analyst avoids 30-60% zone
        if 0.30 <= bc_progress <= 0.60:
            return False, f"Analyst KOTH avoidance zone ({bc_progress:.0%})"

    return True, ""


async def _request_ml_score(redis_conn: aioredis.Redis, features: dict, timeout: float = 5.0) -> float:
    """Request ML score from ml_engine via Redis pub/sub."""
    request_id = f"req_{time.time()}"
    request = {
        "request_id": request_id,
        "features": features,
    }

    # Subscribe to response channel before publishing request
    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("ml:score_response")

    await redis_conn.publish("ml:score_request", json.dumps(request))

    # Wait for response
    deadline = time.time() + timeout
    try:
        async for message in pubsub.listen():
            if time.time() > deadline:
                break
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            if data.get("request_id") == request_id:
                await pubsub.unsubscribe("ml:score_response")
                return data.get("ml_score", 50.0)
    except Exception:
        pass

    await pubsub.unsubscribe("ml:score_response")
    return 50.0  # Default neutral if timeout


async def _cleanup_seen_tokens():
    """Periodically clean up the dedup cache."""
    while True:
        await asyncio.sleep(SEEN_CLEANUP_INTERVAL)
        now = time.time()
        expired = [mint for mint, data in _seen_tokens.items()
                   if now - data["first_seen"] > DEDUP_WINDOW_SECONDS * 10]
        for mint in expired:
            del _seen_tokens[mint]
        if expired:
            logger.debug("Cleaned %d expired tokens from dedup cache", len(expired))


async def _process_signals(redis_conn: aioredis.Redis):
    """Main processing loop: read raw signals, aggregate, score, and route."""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Pop from raw signal queue (blocking pop with 5s timeout)
                result = await redis_conn.brpop("signals:raw", timeout=5)
                if not result:
                    continue

                _, raw_json = result
                signal = json.loads(raw_json)
                mint = signal.get("mint", "")
                source = signal.get("source", "unknown")

                if not mint:
                    continue

                now = time.time()

                # --- Deduplication ---
                if mint in _seen_tokens:
                    entry = _seen_tokens[mint]
                    if now - entry["first_seen"] <= DEDUP_WINDOW_SECONDS:
                        entry["sources"].add(source)
                        entry["signal_data"] = signal  # update with latest
                        logger.debug("Dedup: %s already seen (sources: %s)", mint[:12], entry["sources"])
                        continue
                    else:
                        # Window expired — treat as new
                        del _seen_tokens[mint]

                _seen_tokens[mint] = {
                    "first_seen": now,
                    "sources": {source},
                    "signal_data": signal,
                }

                # --- Get market mode ---
                market_mode = "NORMAL"
                mode_str = await redis_conn.get("market:mode:current")
                if mode_str:
                    market_mode = mode_str

                if market_mode == "HIBERNATE":
                    logger.debug("HIBERNATE mode — skipping %s", mint[:12])
                    continue

                # --- Enrich with Rugcheck ---
                rugcheck = await _fetch_rugcheck(session, mint)

                # --- Classify target personalities ---
                targets = _classify_target_personalities(signal, rugcheck)
                if not targets:
                    continue

                # --- Confidence score ---
                confidence = _compute_confidence(_seen_tokens[mint]["sources"])

                # --- Build feature dict for ML scoring ---
                raw = signal.get("raw_data", {})
                features = {
                    "liquidity_sol": float(raw.get("vSolInBondingCurve", raw.get("liquidity_sol", 0))),
                    "liquidity_velocity": float(raw.get("liquidity_velocity", 0)),
                    "bonding_curve_progress": float(raw.get("bondingCurveProgress", raw.get("bonding_curve_progress", 0))),
                    "buy_sell_ratio_5min": float(raw.get("buy_sell_ratio_5min", 1.0)),
                    "holder_count": int(raw.get("holder_count", raw.get("holders", 0))),
                    "top10_holder_pct": float(raw.get("top10_holder_pct", 0)),
                    "unique_buyers_30min": int(raw.get("unique_buyers_30min", 0)),
                    "volume_acceleration_15min": float(raw.get("volume_acceleration_15min", 0)),
                    "dev_wallet_hold_pct": float(raw.get("dev_wallet_hold_pct", 0)),
                    "bundle_detected": 1 if raw.get("bundle_detected", False) else 0,
                    "bundled_supply_pct": float(raw.get("bundled_supply_pct", 0)),
                    "bot_transaction_ratio": float(raw.get("bot_transaction_ratio", 0)),
                    "fresh_wallet_ratio": float(raw.get("fresh_wallet_ratio", 0)),
                    "creator_dead_tokens_30d": int(raw.get("creator_dead_tokens_30d", 0)),
                    "token_age_seconds": float(signal.get("age_seconds", 0)),
                    "market_cap_usd": float(raw.get("market_cap_usd", raw.get("usdMarketCap", 0))),
                    "volume_24h_usd": float(raw.get("volume_24h_usd", 0)),
                    "price_change_5min_pct": float(raw.get("price_change_5min_pct", 0)),
                    "price_change_1h_pct": float(raw.get("price_change_1h_pct", 0)),
                    "sol_price_usd": 0,  # Filled from market health
                    "cfgi_score": 0,
                    "market_mode_encoded": MARKET_MODE_ENCODING.get(market_mode, 2),
                    "hour_of_day": datetime.now(timezone.utc).hour,
                    "is_weekend": 1 if datetime.now(timezone.utc).weekday() >= 5 else 0,
                    "signal_source_count": len(_seen_tokens[mint]["sources"]),
                    "whale_wallet_count": int(raw.get("whale_wallet_count", 0)),
                }

                # Fill in market health data
                health_str = await redis_conn.get("market:health")
                if health_str:
                    health = json.loads(health_str)
                    features["sol_price_usd"] = health.get("sol_price", 0)
                    features["cfgi_score"] = health.get("cfgi", 0)

                # --- Request ML score ---
                ml_score = await _request_ml_score(redis_conn, features)

                # --- Route to each target personality ---
                bc_progress = features["bonding_curve_progress"]

                for personality in targets:
                    # Hard filters
                    passed, reason = _apply_hard_filters(personality, signal, rugcheck)
                    if not passed:
                        logger.debug("Rejected %s for %s: %s", mint[:12], personality, reason)
                        continue

                    # KOTH zone check
                    passed, reason = _check_koth_zone(bc_progress, personality, ml_score)
                    if not passed:
                        logger.debug("KOTH reject %s for %s: %s", mint[:12], personality, reason)
                        continue

                    # ML threshold check
                    threshold = ML_THRESHOLDS.get(personality, 70)
                    if market_mode == "FRENZY":
                        threshold -= 5
                    elif market_mode == "DEFENSIVE":
                        threshold += 10

                    if ml_score < threshold:
                        logger.debug("ML reject %s for %s: %.1f < %d", mint[:12], personality, ml_score, threshold)
                        continue

                    # Source count check for Analyst
                    if personality == "analyst" and len(_seen_tokens[mint]["sources"]) < ANALYST_FILTERS.get("min_sources", 2):
                        logger.debug("Analyst needs 2+ sources for %s (has %d)", mint[:12], len(_seen_tokens[mint]["sources"]))
                        continue

                    # --- SIGNAL PASSED ALL GATES ---
                    scored_signal = {
                        "mint": mint,
                        "personality": personality,
                        "ml_score": ml_score,
                        "confidence": confidence,
                        "market_mode": market_mode,
                        "features": features,
                        "rugcheck": rugcheck,
                        "signal": signal,
                        "sources": list(_seen_tokens[mint]["sources"]),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                    await redis_conn.lpush("signals:scored", json.dumps(scored_signal))
                    logger.info("SCORED: %s → %s (ML=%.1f, conf=%d, mode=%s)",
                                mint[:12], personality, ml_score, confidence, market_mode)

            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON in signal: %s", e)
            except Exception as e:
                logger.error("Signal processing error: %s", e)
                await asyncio.sleep(1)


async def main():
    logger.info("Signal Aggregator starting (TEST_MODE=%s)", TEST_MODE)

    if TEST_MODE:
        logger.info("TEST_MODE — aggregator will process signals but not route to execution")

    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_conn.ping()
        logger.info("Redis connected: %s", REDIS_URL)
    except Exception as e:
        logger.error("Redis connection REQUIRED for aggregator: %s", e)
        logger.error("Signal aggregator cannot run without Redis — exiting")
        return

    await asyncio.gather(
        _process_signals(redis_conn),
        _cleanup_seen_tokens(),
    )


if __name__ == "__main__":
    asyncio.run(main())
