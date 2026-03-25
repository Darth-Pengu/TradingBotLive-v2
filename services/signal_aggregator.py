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
VYBE_API_KEY = os.getenv("VYBE_API_KEY", "")
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_PARSE_TX_URL = os.getenv("HELIUS_PARSE_TX_URL", "")
HELIUS_PARSE_HISTORY_URL = os.getenv("HELIUS_PARSE_HISTORY_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")

# Nansen smart money confidence boost
NANSEN_SM_CONFIDENCE_BOOST = 20  # +20 confidence if any smart money bought
NANSEN_SM_MAX_CONFIDENCE = 3     # 3+ smart money wallets = max confidence

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
# /v1/tokens/{mint}/report is public (no auth required)
# Response includes: {score, risks[], tokenMeta, markets[], lpLockedPct, ...}
# risks[]: [{name, level, description, score, value}, ...]
RUGCHECK_REPORT_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"

# Score thresholds — Rugcheck score is 0-100 where HIGHER = MORE RISK
# (opposite of a "safety score")
RUGCHECK_REJECT_SCORE = 50  # Reject tokens with risk score >= 50

# --- ML thresholds (Section 12) ---
ML_THRESHOLDS = {
    "speed_demon": 65,
    "analyst": 70,
    "whale_tracker": 70,
}


async def _fetch_rugcheck(session: aiohttp.ClientSession, mint: str) -> dict:
    """
    Fetch token safety report from Rugcheck.
    The report endpoint is public — no auth needed.
    Returns: {score, risks[], tokenMeta, markets[], lpLockedPct, ...}
    """
    url = RUGCHECK_REPORT_URL.format(mint=mint)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                # Normalize the response for our filters
                risks = data.get("risks", [])
                risk_levels = [r.get("level", "") for r in risks]
                has_danger = "danger" in risk_levels or "critical" in risk_levels
                has_high = "high" in risk_levels or "warn" in risk_levels
                return {
                    "score": data.get("score", 0),
                    "score_normalised": data.get("score_normalised", 0),
                    "lp_locked_pct": data.get("lpLockedPct", 0),
                    "risks": risks,
                    "risk_names": [r.get("name", "") for r in risks],
                    "has_danger": has_danger,
                    "has_high_risk": has_high,
                    "token_type": data.get("tokenType", ""),
                }
            elif resp.status == 429:
                logger.warning("Rugcheck rate limited for %s", mint[:12])
            else:
                logger.debug("Rugcheck HTTP %d for %s", resp.status, mint[:12])
    except Exception as e:
        logger.debug("Rugcheck error for %s: %s", mint[:12], e)
    return {}


async def _fetch_token_details(session: aiohttp.ClientSession, mint: str, redis_conn: aioredis.Redis | None = None) -> dict:
    """
    Fetch additional token details from free APIs:
    - Helius getTokenLargestAccounts → holder concentration
    - GeckoTerminal pool data → DEX volume, liquidity
    - Vybe Network + Helius Enhanced Transactions → creator wallet history
    """
    details = {}

    # Run independent fetches concurrently
    results = await asyncio.gather(
        _fetch_holder_data(session, mint),
        _fetch_gecko_pool_data(session, mint),
        _fetch_creator_history(session, mint, redis_conn),
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, dict):
            details.update(result)

    return details


async def _fetch_holder_data(session: aiohttp.ClientSession, mint: str) -> dict:
    """Fetch top holder data via Helius getTokenLargestAccounts (RPC, gatekeeper fallback)."""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [mint],
    }
    for rpc_url in (HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
        if not rpc_url:
            continue
        try:
            async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                accounts = data.get("result", {}).get("value", [])
                if not accounts:
                    return {}

                amounts = [float(a.get("uiAmount", 0) or 0) for a in accounts[:20]]
                total_supply_sample = sum(amounts)
                top10_sum = sum(amounts[:10])
                top10_pct = (top10_sum / total_supply_sample * 100) if total_supply_sample > 0 else 0

                return {
                    "holder_count_sample": len(accounts),
                    "top10_holder_pct": round(top10_pct, 1),
                }
        except Exception as e:
            logger.debug("Helius holder data error for %s on %s: %s", mint[:12], rpc_url[:40], e)
    return {}


async def _fetch_gecko_pool_data(session: aiohttp.ClientSession, mint: str) -> dict:
    """Fetch pool/volume data from GeckoTerminal."""
    try:
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}/pools"
        async with session.get(url, headers={"Accept": "application/json"},
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            pools = data.get("data", [])
            if not pools:
                return {}

            # Use the first (highest volume) pool
            attrs = pools[0].get("attributes", {})
            return {
                "volume_24h_usd": float(attrs.get("volume_usd", {}).get("h24", 0) or 0),
                "reserve_usd": float(attrs.get("reserve_in_usd", 0) or 0),
                "price_change_5min_pct": float(attrs.get("price_change_percentage", {}).get("m5", 0) or 0),
                "price_change_1h_pct": float(attrs.get("price_change_percentage", {}).get("h1", 0) or 0),
                "trade_count_24h": int(attrs.get("transactions", {}).get("h24", {}).get("buys", 0) or 0)
                                 + int(attrs.get("transactions", {}).get("h24", {}).get("sells", 0) or 0),
            }
    except Exception as e:
        logger.debug("GeckoTerminal pool error for %s: %s", mint[:12], e)
    return {}


async def _fetch_creator_history(session: aiohttp.ClientSession, mint: str, redis_conn: aioredis.Redis | None = None) -> dict:
    """Fetch creator wallet history via Vybe Network + Helius Enhanced Transactions API."""
    details = {}

    # Step 1: Get creator address from Vybe Network
    creator = ""
    if VYBE_API_KEY:
        try:
            url = f"https://api.vybenetwork.xyz/token/{mint}"
            headers = {"Authorization": f"Bearer {VYBE_API_KEY}"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    creator = data.get("creator", "")
                    details["creator_address"] = creator
        except Exception as e:
            logger.debug("Vybe error for %s: %s", mint[:12], e)

    if not creator or not HELIUS_PARSE_HISTORY_URL:
        return details

    # Step 2: Check Redis cache for creator history (24hr TTL)
    cache_key = f"creator_history:{creator}"
    if redis_conn:
        try:
            cached = await redis_conn.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                details.update(cached_data)
                logger.debug("Creator history cache hit for %s", creator[:12])
                return details
        except Exception:
            pass

    # Step 3: Fetch token creation transactions from Helius Enhanced Transactions API
    try:
        url = HELIUS_PARSE_HISTORY_URL.replace("{address}", creator)
        params = {
            "type": "CREATE_ACCOUNT",
            "limit": 50,
        }
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.debug("Helius creator history HTTP %d for %s", resp.status, creator[:12])
                return details

            txs = await resp.json()
            if not isinstance(txs, list):
                return details

            # Extract token mints from creation transactions
            created_mints = []
            for tx in txs:
                # Helius enhanced tx format: tokenTransfers[] contains mint addresses
                token_transfers = tx.get("tokenTransfers", [])
                for transfer in token_transfers:
                    token_mint = transfer.get("mint", "")
                    if token_mint and token_mint != mint:
                        created_mints.append(token_mint)

                # Also check account data for created token accounts
                account_data = tx.get("accountData", [])
                for acc in account_data:
                    if acc.get("tokenBalanceChanges"):
                        for change in acc["tokenBalanceChanges"]:
                            token_mint = change.get("mint", "")
                            if token_mint and token_mint != mint:
                                created_mints.append(token_mint)

            # Deduplicate
            created_mints = list(set(created_mints))
            prev_token_count = len(created_mints)
            details["creator_prev_tokens_count"] = prev_token_count

            # Step 4: Check previous tokens against Rugcheck for rug history
            rug_count = 0
            graduated_count = 0
            if created_mints:
                # Check up to 10 previous tokens to avoid rate limiting
                check_mints = created_mints[:10]
                rugcheck_tasks = [_fetch_rugcheck(session, m) for m in check_mints]
                rugcheck_results = await asyncio.gather(*rugcheck_tasks, return_exceptions=True)

                for rc_result in rugcheck_results:
                    if isinstance(rc_result, dict) and rc_result:
                        if rc_result.get("has_danger"):
                            rug_count += 1
                        # Token type indicates graduation status
                        if rc_result.get("token_type") in ("graduated", "raydium", "orca", "meteora"):
                            graduated_count += 1

            details["creator_rug_count"] = rug_count
            details["creator_graduation_rate"] = round(graduated_count / prev_token_count, 2) if prev_token_count > 0 else 0.0

            logger.info("Creator %s: %d prev tokens, %d rugs, %.0f%% graduation rate",
                         creator[:12], prev_token_count, rug_count,
                         details["creator_graduation_rate"] * 100)

    except Exception as e:
        logger.debug("Helius creator history error for %s: %s", creator[:12], e)
        return details

    # Step 5: Cache results in Redis with 24hr TTL
    creator_cache = {
        "creator_prev_tokens_count": details.get("creator_prev_tokens_count", 0),
        "creator_rug_count": details.get("creator_rug_count", 0),
        "creator_graduation_rate": details.get("creator_graduation_rate", 0.0),
    }
    if redis_conn:
        try:
            await redis_conn.set(cache_key, json.dumps(creator_cache), ex=86400)
        except Exception:
            pass

    return details


async def _check_dev_wallet_sells(session: aiohttp.ClientSession, dev_wallet: str, mint: str) -> dict:
    """
    Check if dev has sold >20% of holdings in first 2 minutes using
    Helius Enhanced Transactions API (SWAP type filter).
    Falls back to raw_data fields if Helius unavailable.
    """
    if not dev_wallet or not HELIUS_PARSE_HISTORY_URL:
        return {}

    t0 = time.time()
    try:
        url = HELIUS_PARSE_HISTORY_URL.replace("{address}", dev_wallet)
        params = {"limit": 20, "type": "SWAP"}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            elapsed_ms = (time.time() - t0) * 1000
            logger.debug("Helius dev sell check %s: %.0fms (HTTP %d)", dev_wallet[:12], elapsed_ms, resp.status)

            if resp.status != 200:
                return {}

            txs = await resp.json()
            if not isinstance(txs, list):
                return {}

        total_sold = 0.0
        total_held = 0.0
        now = time.time()

        for tx in txs:
            timestamp = tx.get("timestamp", 0)
            # Only check transactions in the first 2 minutes of token life
            # (we approximate by checking recent swaps)
            if timestamp and (now - timestamp) > 300:
                continue

            for transfer in tx.get("tokenTransfers", []):
                if transfer.get("mint") != mint:
                    continue
                amount = float(transfer.get("tokenAmount", 0) or 0)
                from_addr = transfer.get("fromUserAccount", "")
                to_addr = transfer.get("toUserAccount", "")

                if from_addr == dev_wallet:
                    total_sold += amount
                elif to_addr == dev_wallet:
                    total_held += amount

        sell_pct = (total_sold / (total_sold + total_held) * 100) if (total_sold + total_held) > 0 else 0

        return {
            "dev_sold_pct": round(sell_pct, 1),
            "dev_sell_detected": sell_pct > 20,
            "dev_total_sold": total_sold,
            "dev_total_held": total_held,
        }

    except Exception as e:
        logger.debug("Helius dev sell check error for %s: %s", dev_wallet[:12], e)
    return {}


async def _check_bundle_detection(session: aiohttp.ClientSession, tx_signatures: list[str]) -> dict:
    """
    Check for coordinated buys using Helius Enhanced Transaction parsing.
    POST /v0/transactions — parse results to check if multiple buys landed
    in the same slot from fresh wallets.
    Falls back to raw_data bundle_detected field if Helius unavailable.
    """
    if not tx_signatures or not HELIUS_PARSE_TX_URL:
        return {}

    # Limit to 20 signatures per request
    sigs = tx_signatures[:20]

    t0 = time.time()
    try:
        url = HELIUS_PARSE_TX_URL
        payload = {"transactions": sigs}
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed_ms = (time.time() - t0) * 1000
            logger.debug("Helius bundle check: %.0fms (HTTP %d, %d txs)", elapsed_ms, resp.status, len(sigs))

            if resp.status != 200:
                return {}

            txs = await resp.json()
            if not isinstance(txs, list):
                return {}

        # Group buys by slot to detect coordinated activity
        slot_buyers: dict[int, list[str]] = {}
        buyer_ages: dict[str, bool] = {}  # wallet -> is_fresh

        for tx in txs:
            slot = tx.get("slot", 0)
            tx_type = tx.get("type", "")

            # Look for buy-side token transfers
            for transfer in tx.get("tokenTransfers", []):
                buyer = transfer.get("toUserAccount", "")
                if not buyer:
                    continue
                slot_buyers.setdefault(slot, []).append(buyer)

            # Check fee payer as potential fresh wallet
            fee_payer = tx.get("feePayer", "")
            if fee_payer:
                # Account data can tell us wallet age via nativeTransfers
                native = tx.get("nativeTransfers", [])
                # Fresh wallets often only have 1-2 native transfers total
                buyer_ages[fee_payer] = len(native) <= 2

        # Detect bundles: 3+ buys in same slot
        bundled_slots = {slot: buyers for slot, buyers in slot_buyers.items() if len(buyers) >= 3}
        fresh_in_bundle = 0
        total_in_bundle = 0

        for slot, buyers in bundled_slots.items():
            total_in_bundle += len(buyers)
            fresh_in_bundle += sum(1 for b in buyers if buyer_ages.get(b, False))

        is_bundled = len(bundled_slots) > 0
        bundled_supply_pct = 0.0
        if total_in_bundle > 0 and len(txs) > 0:
            bundled_supply_pct = round(total_in_bundle / len(txs) * 100, 1)

        return {
            "bundle_detected": is_bundled,
            "bundled_slots_count": len(bundled_slots),
            "bundled_supply_pct": bundled_supply_pct,
            "fresh_wallet_ratio": round(fresh_in_bundle / total_in_bundle, 2) if total_in_bundle > 0 else 0.0,
            "helius_bundle_check": True,
        }

    except Exception as e:
        logger.debug("Helius bundle check error: %s", e)
    return {}


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

        # Dev sold >20% in first 2 minutes — reject (Helius enhanced detection)
        dev_sold_pct = raw.get("dev_sold_pct", 0)
        if dev_sold_pct > 20:
            return False, f"dev sold {dev_sold_pct}% > 20% (Helius enhanced)"

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
    # Check for danger/critical risk levels in the risks array
    if rugcheck.get("has_danger"):
        risk_names = rugcheck.get("risk_names", [])
        return False, f"rugcheck danger risks: {', '.join(risk_names[:3])}"

    # Also reject if the overall risk score is too high (higher = riskier)
    rugcheck_score = rugcheck.get("score", 0)
    if rugcheck_score >= RUGCHECK_REJECT_SCORE:
        return False, f"rugcheck risk score {rugcheck_score} >= {RUGCHECK_REJECT_SCORE}"

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

                # --- Enrich with Rugcheck + token details (concurrent) ---
                rugcheck, token_details = await asyncio.gather(
                    _fetch_rugcheck(session, mint),
                    _fetch_token_details(session, mint, redis_conn),
                )

                # --- Helius enhanced checks: dev wallet sells + bundle detection ---
                raw_data = signal.get("raw_data", {})
                creator_addr = token_details.get("creator_address", raw_data.get("traderPublicKey", ""))
                early_tx_sigs = [raw_data.get("signature", "")] if raw_data.get("signature") else []
                # Gather additional signatures from PumpPortal trade data if available
                if raw_data.get("tx_signatures"):
                    early_tx_sigs.extend(raw_data["tx_signatures"][:19])

                dev_sell_data, bundle_data = await asyncio.gather(
                    _check_dev_wallet_sells(session, creator_addr, mint),
                    _check_bundle_detection(session, early_tx_sigs),
                    return_exceptions=True,
                )
                if isinstance(dev_sell_data, dict):
                    token_details.update(dev_sell_data)
                if isinstance(bundle_data, dict):
                    # Helius bundle data overrides raw_data values with more reliable detection
                    if bundle_data.get("helius_bundle_check"):
                        signal.setdefault("raw_data", {}).update({
                            "bundle_detected": bundle_data.get("bundle_detected", False),
                            "bundled_supply_pct": bundle_data.get("bundled_supply_pct", 0),
                            "fresh_wallet_ratio": bundle_data.get("fresh_wallet_ratio", 0),
                        })

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
                    "top10_holder_pct": float(token_details.get("top10_holder_pct", raw.get("top10_holder_pct", 0))),
                    "unique_buyers_30min": int(raw.get("unique_buyers_30min", 0)),
                    "volume_acceleration_15min": float(raw.get("volume_acceleration_15min", 0)),
                    "dev_wallet_hold_pct": float(raw.get("dev_wallet_hold_pct", 0)),
                    "dev_sold_pct": float(token_details.get("dev_sold_pct", raw.get("dev_sold_pct", 0))),
                    "bundle_detected": 1 if raw.get("bundle_detected", False) else 0,
                    "bundled_supply_pct": float(raw.get("bundled_supply_pct", 0)),
                    "bot_transaction_ratio": float(raw.get("bot_transaction_ratio", 0)),
                    "fresh_wallet_ratio": float(raw.get("fresh_wallet_ratio", 0)),
                    "creator_prev_tokens_count": int(token_details.get("creator_prev_tokens_count", raw.get("creator_prev_tokens_count", 0))),
                    "creator_rug_count": int(token_details.get("creator_rug_count", raw.get("creator_rug_count", 0))),
                    "creator_graduation_rate": float(token_details.get("creator_graduation_rate", raw.get("creator_graduation_rate", 0))),
                    "token_age_seconds": float(signal.get("age_seconds", 0)),
                    "market_cap_usd": float(raw.get("market_cap_usd", raw.get("usdMarketCap", 0))),
                    "volume_24h_usd": float(token_details.get("volume_24h_usd", raw.get("volume_24h_usd", 0))),
                    "price_change_5min_pct": float(token_details.get("price_change_5min_pct", raw.get("price_change_5min_pct", 0))),
                    "price_change_1h_pct": float(token_details.get("price_change_1h_pct", raw.get("price_change_1h_pct", 0))),
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

                    # --- Nansen smart money confirmation (Analyst + Whale Tracker only) ---
                    # Speed Demon skips this — latency is critical for 30-sec alpha snipes
                    nansen_sm_count = 0
                    if personality in ("analyst", "whale_tracker") and NANSEN_API_KEY:
                        try:
                            from services.nansen_client import get_smart_money_buyers
                            sm_data = await get_smart_money_buyers(session, mint, hours_back=1, redis_conn=redis_conn)
                            if sm_data:
                                buyers = sm_data.get("data", sm_data.get("result", []))
                                if isinstance(buyers, list):
                                    nansen_sm_count = len(buyers)
                                    if nansen_sm_count > 0:
                                        confidence += NANSEN_SM_CONFIDENCE_BOOST
                                        logger.info("Nansen: %d smart money buyers for %s (+%d confidence)",
                                                     nansen_sm_count, mint[:12], NANSEN_SM_CONFIDENCE_BOOST)
                                    if nansen_sm_count >= NANSEN_SM_MAX_CONFIDENCE:
                                        confidence = 100  # Max confidence
                                        logger.info("Nansen: %d+ smart money → MAX CONFIDENCE for %s",
                                                     nansen_sm_count, mint[:12])
                        except Exception as e:
                            logger.debug("Nansen SM check failed for %s: %s", mint[:12], e)

                    # --- SIGNAL PASSED ALL GATES ---
                    scored_signal = {
                        "mint": mint,
                        "personality": personality,
                        "ml_score": ml_score,
                        "confidence": confidence,
                        "nansen_smart_money_count": nansen_sm_count,
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
