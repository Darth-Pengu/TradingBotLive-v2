"""
ZMN Bot Signal Aggregator
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
import math
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
HELIUS_ENRICHMENT_ENABLED = os.getenv("HELIUS_ENRICHMENT_ENABLED", "true").lower() == "true"
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SOCIALDATA_API_KEY = os.getenv("SOCIALDATA_API_KEY", "")
SPEED_DEMON_FILTERS_ENABLED = os.getenv("SPEED_DEMON_FILTERS_ENABLED", "true").lower() == "true"

# Haiku enrichment config
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_ENABLED = os.getenv("HAIKU_ENRICHMENT_ENABLED", "false").lower() == "true" and bool(ANTHROPIC_API_KEY)
HAIKU_CACHE_TTL = 86400  # 24 hours — Redis-backed, survives restarts

HAIKU_SYSTEM_PROMPT = """You are a Solana memecoin risk analyst.
Analyze the token data provided and return ONLY a JSON object.
No explanation, no markdown, just raw JSON.

Return exactly:
{
  "risk_score": 0-100,
  "confidence": "low"|"medium"|"high",
  "red_flags": ["flag1", "flag2"],
  "green_flags": ["flag1"],
  "recommendation": "strong_buy"|"buy"|"pass"|"hard_pass",
  "reasoning": "one sentence max"
}

risk_score: 0=safest, 100=highest risk
recommendation thresholds:
- strong_buy: risk_score < 20, multiple green flags
- buy: risk_score < 40
- pass: risk_score 40-70
- hard_pass: risk_score > 70 OR any critical red flag"""

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

# Rugcheck score is unbounded integer — higher = more risk
# Real world scores: safe tokens ~100-500, risky tokens 1000+, rugs 5000+
# Primary gate: has_danger level check (already implemented in _apply_hard_filters)
# Secondary gate: reject extreme scores only
# Rugcheck scores are unbounded integers, NOT 0-100.
# Safe tokens ~100-500, risky ~1000-3000, rugs 5000+, TRUMP scored 18,715.
# Threshold calibrated per AGENT_CONTEXT Section 21. Overridable via env var.
RUGCHECK_REJECT_SCORE = int(os.getenv("RUGCHECK_REJECT_THRESHOLD", "2000"))

# --- ML thresholds (Section 12) ---
# Production thresholds (used when ML model is trained with >= 200 samples)
ML_THRESHOLDS = {
    "speed_demon": 65,
    "analyst": 70,
    "whale_tracker": 70,
}
# Bootstrap thresholds (used during cold start when model is untrained)
# Deliberately lower to allow paper trades through for data collection
ML_BOOTSTRAP_THRESHOLDS = {
    "speed_demon": 40,
    "analyst": 45,
    "whale_tracker": 45,
}
# Aggressive paper trading mode: set AGGRESSIVE_PAPER_TRADING=true to drop
# all ML thresholds to 1, letting every signal through for data collection.
# Retrain the accelerated model every 500 new samples.
AGGRESSIVE_PAPER = os.getenv("AGGRESSIVE_PAPER_TRADING", "false").lower() == "true"
if AGGRESSIVE_PAPER:
    ML_THRESHOLDS = {"speed_demon": 1, "analyst": 1, "whale_tracker": 1}
    ML_BOOTSTRAP_THRESHOLDS = {"speed_demon": 1, "analyst": 1, "whale_tracker": 1}
    logging.getLogger("signal_aggregator").warning(
        "AGGRESSIVE PAPER TRADING active — ML thresholds set to 1 for all personalities"
    )

# --- Market mode encoding for ML features (defined locally to avoid circular import) ---
MARKET_MODE_ENCODING = {
    "HIBERNATE": 0,
    "DEFENSIVE": 1,
    "NORMAL": 2,
    "AGGRESSIVE": 3,
    "FRENZY": 4,
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
                # Extract top holders for concentration check
                top_holders = []
                for h in data.get("topHolders", [])[:5]:
                    top_holders.append({
                        "pct": float(h.get("pct", 0) or 0) / 100.0,  # normalize to 0-1
                        "address": h.get("address", ""),
                    })
                return {
                    "score": data.get("score", 0),
                    "score_normalised": data.get("score_normalised", 0),
                    "lp_locked_pct": data.get("lpLockedPct", 0),
                    "risks": risks,
                    "risk_names": [r.get("name", "") for r in risks],
                    "has_danger": has_danger,
                    "has_high_risk": has_high,
                    "token_type": data.get("tokenType", ""),
                    "top_holders": top_holders,
                    "result": (data.get("rugged") and "rug") or "",
                    "mint_authority_enabled": data.get("mintAuthority") is not None and data.get("mintAuthority") != "",
                    "freeze_authority_enabled": data.get("freezeAuthority") is not None and data.get("freezeAuthority") != "",
                    "is_honeypot": any("honeypot" in r.get("name", "").lower() for r in risks),
                }
            elif resp.status == 429:
                logger.warning("Rugcheck rate limited for %s", mint[:12])
            else:
                logger.debug("Rugcheck HTTP %d for %s", resp.status, mint[:12])
    except Exception as e:
        logger.debug("Rugcheck error for %s: %s", mint[:12], e)
    return {}


async def _get_rugcheck_enriched(session: aiohttp.ClientSession, mint: str, redis_conn: aioredis.Redis | None = None) -> dict:
    """Fetch rugcheck with Redis cache (5 min TTL). Adds bundle_pct, is_copycat etc."""
    if redis_conn:
        try:
            cached = await redis_conn.get(f"rugcheck:{mint}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    rc = await _fetch_rugcheck(session, mint)
    if not rc:
        return rc

    # Enrich with bundle percentage and copycat detection
    risks = rc.get("risks", [])
    risk_names = rc.get("risk_names", [])
    bundle_pct = 0.0
    for risk in risks:
        name = (risk.get("name", "") or "").lower()
        if "bundle" in name:
            val = str(risk.get("value", "0"))
            try:
                bundle_pct = float(val.replace("%", "").strip() or 0)
            except (ValueError, TypeError):
                pass
    rc["bundle_pct"] = bundle_pct
    rc["is_copycat"] = any("copycat" in r.lower() or "clone" in r.lower() for r in risk_names)
    rc["freeze_authority"] = any("freeze" in r.lower() for r in risk_names)
    rc["rugcheck_risks"] = [r.lower() for r in risk_names]

    if redis_conn:
        try:
            await redis_conn.set(f"rugcheck:{mint}", json.dumps(rc), ex=300)
        except Exception:
            pass
    return rc


def _score_rugcheck(rugcheck: dict) -> tuple:
    """
    Returns (hard_reject: bool, reason: str,
             size_multiplier: float, risk_level: str)

    hard_reject = True only for unrecoverable risks
    size_multiplier = how much to scale position
    """
    if not rugcheck:
        # No data — trade with caution
        return False, "", 0.6, "unknown"

    risks = rugcheck.get("risks", [])
    risk_names = [r.get("name", "").lower() for r in risks]
    score = int(rugcheck.get("score", 50) or 50)

    # ── HARD REJECTS (unrecoverable) ───────────────
    # Honeypot: cannot sell tokens
    if rugcheck.get("is_honeypot"):
        return True, "honeypot", 0, "fatal"

    # Blacklisted contract
    if any("blacklist" in r for r in risk_names):
        return True, "blacklisted", 0, "fatal"

    # Freeze authority active (funds can freeze)
    if rugcheck.get("freeze_authority_enabled"):
        return True, "freeze_authority", 0, "fatal"

    # Explicit scam/rug pattern detected
    if rugcheck.get("result") in ("rug", "scam"):
        return True, "confirmed_rug", 0, "fatal"

    # ── SOFT RISKS (reduce size, still trade) ──────
    multiplier = 1.0
    risk_level = "low"

    # Mint authority not revoked (can print tokens)
    if rugcheck.get("mint_authority_enabled"):
        multiplier *= 0.6
        risk_level = "medium"

    # Top holder concentration > 20%
    top_holders = rugcheck.get("top_holders", [])
    if top_holders:
        top_pct = sum(h.get("pct", 0) for h in top_holders[:3])
        if top_pct > 0.5:
            multiplier *= 0.5
            risk_level = "high"
        elif top_pct > 0.3:
            multiplier *= 0.7
            risk_level = "medium"

    # General danger flags
    if rugcheck.get("has_danger"):
        multiplier *= 0.7
        risk_level = "medium"

    # Bundle detected in rugcheck
    if any("bundle" in r for r in risk_names):
        multiplier *= 0.6
        risk_level = "high"

    # Low rugcheck score
    if score < 30:
        multiplier *= 0.5
        risk_level = "high"
    elif score < 50:
        multiplier *= 0.75
        risk_level = "medium"

    # Apply floor — never go below 0.15x
    multiplier = max(0.15, multiplier)

    return False, "", multiplier, risk_level


_socialdata_last_call = 0.0


async def _get_twitter_followers(session: aiohttp.ClientSession, twitter_url: str,
                                  redis_conn: aioredis.Redis | None = None) -> int:
    """Look up Twitter follower count via SocialData.tools. Returns -1 if unknown."""
    global _socialdata_last_call

    if not SOCIALDATA_API_KEY or not twitter_url:
        return -1

    username = twitter_url.rstrip("/").split("/")[-1]
    username = username.replace("@", "").split("?")[0]
    if not username or len(username) < 2:
        return -1

    cache_key = f"twitter:followers:{username.lower()}"
    if redis_conn:
        try:
            cached = await redis_conn.get(cache_key)
            if cached:
                return int(cached)
        except Exception:
            pass

    # Rate limit: 120 req/min = 0.5s between calls
    elapsed = time.time() - _socialdata_last_call
    if elapsed < 0.5:
        await asyncio.sleep(0.5 - elapsed)
    _socialdata_last_call = time.time()

    try:
        url = f"https://api.socialdata.tools/twitter/user/{username}"
        async with session.get(url, headers={"Authorization": f"Bearer {SOCIALDATA_API_KEY}"},
                               timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 401:
                logger.error("SocialData API key invalid — check SOCIALDATA_API_KEY env var")
                return -1
            if resp.status == 402:
                logger.error("SocialData out of credits")
                return -1
            if resp.status == 429:
                logger.warning("SocialData rate limited")
                await asyncio.sleep(2)
                return -1
            if resp.status == 404:
                # Account doesn't exist or is suspended — cache as 0
                if redis_conn:
                    await redis_conn.set(cache_key, "0", ex=86400)
                return 0
            if resp.status != 200:
                logger.debug("SocialData HTTP %d for %s", resp.status, username)
                return -1

            data = await resp.json()
            followers = int(data.get("followers_count", -1))
            if redis_conn and followers >= 0:
                await redis_conn.set(cache_key, str(followers), ex=86400)
            return followers
    except Exception as e:
        logger.debug("SocialData error: %s", e)
        return -1


def _apply_speed_demon_prefilters(signal: dict, rugcheck: dict) -> tuple[bool, str, float]:
    """
    Speed Demon pre-filters based on owner's manual trading criteria.
    Returns (passes, reject_reason, position_size_multiplier).
    multiplier: 1.0 = normal (0.45 SOL), 1.67 = high confidence (0.75 SOL).
    """
    if not SPEED_DEMON_FILTERS_ENABLED:
        return True, "", 1.0

    raw = signal.get("raw_data", {})
    score = 1.0

    # --- HARD REJECT ---

    # 1. No social links
    if not signal.get("has_social", False):
        return False, "no_social_links", 0

    # 2. Token too old (over 11 minutes = 660s)
    age = signal.get("age_seconds", raw.get("age_seconds", 999))
    if age > 660:
        return False, "token_too_old", 0

    # 3. Bundle concentration too high (>10% of supply)
    bundle_pct = rugcheck.get("bundle_pct", 0)
    if bundle_pct > 10:
        return False, f"bundle_{bundle_pct:.0f}pct", 0

    # 4. Known rug patterns from RugCheck
    rc_risks = rugcheck.get("rugcheck_risks", [])
    for pattern in ("honeypot", "rug pull", "scam", "blacklist"):
        if any(pattern in r for r in rc_risks):
            return False, f"rugcheck_{pattern.replace(' ', '_')}", 0

    # 5. Copycat/clone token
    if rugcheck.get("is_copycat", False):
        return False, "copycat", 0

    # 6. Insufficient liquidity/fees (< 0.5 SOL real buying)
    liq = float(raw.get("vSolInBondingCurve", raw.get("liquidity_sol", 0)) or 0)
    if liq < 0.5:
        return False, "low_liquidity", 0

    # --- SOFT SCORING (increases position size) ---

    # Twitter followers
    followers = signal.get("twitter_followers", -1)
    if followers >= 2000:
        score *= 1.5
    elif followers >= 500:
        score *= 1.2
    elif followers == 0:
        score *= 0.7

    # Low market cap (under $20K = early entry)
    mc = float(raw.get("usdMarketCap", raw.get("market_cap_usd", 999999)) or 999999)
    if mc < 20000:
        score *= 1.3

    # Low bundle (under 5%)
    if 0 < bundle_pct < 5:
        score *= 1.2

    # Multiple social links
    social_count = sum([
        signal.get("has_twitter", False),
        signal.get("has_telegram", False),
        signal.get("has_website", False),
    ])
    if social_count >= 2:
        score *= 1.2

    return True, "", min(score, 1.67)


async def _fetch_token_details(session: aiohttp.ClientSession, mint: str, redis_conn: aioredis.Redis | None = None) -> dict:
    """
    Fetch additional token details from multiple APIs:
    - Nansen labeled top holders → holder concentration WITH labels (replaces Helius)
    - Helius getTokenLargestAccounts → fallback holder data if Nansen unavailable
    - GeckoTerminal pool data → DEX volume, liquidity
    - Vybe Network + Helius Enhanced Transactions → creator wallet history
    - Nansen token flow summary → 6-segment flow analysis (P0)
    - Nansen quant scores → risk/reward indicators for ML (P0)
    """
    details = {}

    # Run ALL independent fetches concurrently — Nansen calls are rate-limited
    # internally via nansen_client._rate_limit so safe to fire in parallel
    fetch_tasks = [
        _fetch_gecko_pool_data(session, mint),
        _fetch_creator_history(session, mint, redis_conn),
    ]

    # Nansen enrichment (P0 + P1) — runs alongside free API fetches
    if NANSEN_API_KEY:
        fetch_tasks.append(_fetch_nansen_enrichment(session, mint, redis_conn))
    else:
        # Fallback to Helius for holder data when Nansen unavailable
        fetch_tasks.append(_fetch_holder_data(session, mint))

    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, dict):
            details.update(result)

    return details


async def _fetch_nansen_enrichment(session: aiohttp.ClientSession, mint: str, redis_conn: aioredis.Redis | None = None) -> dict:
    """
    Nansen per-token enrichment DISABLED — endpoints return 404 on current plan:
    /nansen-scores/token, /tgm/token-current-top-holders, /tgm/token-recent-flows-summary
    These were burning ~158K credits/day for zero value.
    Re-enable when Nansen plan supports these endpoints.
    ML features default to 0 when this returns empty (backwards compatible).
    """
    return {}


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


async def _get_creator_stats(
    session: aiohttp.ClientSession,
    creator_wallet: str,
    redis_conn: aioredis.Redis | None = None,
) -> dict:
    """
    Fetch creator wallet stats: prior launches, rug rate, avg hold time.
    Cached in Redis for 1 hour (key: "creator:{wallet}").
    """
    if not creator_wallet:
        return {"creator_prev_launches": 0, "creator_rug_rate": 0.5, "creator_avg_hold_hours": 0}

    cache_key = f"creator:{creator_wallet}"
    if redis_conn:
        try:
            cached = await redis_conn.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    helius_url = HELIUS_PARSE_HISTORY_URL
    if not helius_url:
        return {"creator_prev_launches": 0, "creator_rug_rate": 0.5, "creator_avg_hold_hours": 0}

    try:
        url = helius_url.replace("{address}", creator_wallet)
        params = {"type": "CREATE_ACCOUNT", "limit": 50}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                return {"creator_prev_launches": 0, "creator_rug_rate": 0.5, "creator_avg_hold_hours": 0}
            txs = await resp.json()

        if not isinstance(txs, list):
            return {"creator_prev_launches": 0, "creator_rug_rate": 0.5, "creator_avg_hold_hours": 0}

        # Count token creation events
        prev_launches = len(txs)
        stats = {
            "creator_prev_launches": prev_launches,
            "creator_rug_rate": 0.3 if prev_launches == 0 else 0.5,
            "creator_avg_hold_hours": 0,
        }

        if redis_conn:
            try:
                await redis_conn.set(cache_key, json.dumps(stats), ex=3600)
            except Exception:
                pass
        return stats

    except Exception as e:
        logger.debug("Creator stats fetch failed for %s: %s", creator_wallet[:12] if creator_wallet else "?", e)
        return {"creator_prev_launches": 0, "creator_rug_rate": 0.5, "creator_avg_hold_hours": 0}


async def _haiku_enrichment(
    mint: str,
    token_name: str,
    features: dict,
    redis_conn: aioredis.Redis | None = None,
) -> dict:
    """
    Call Claude Haiku 4.5 for qualitative token analysis.
    Runs async — does NOT block primary ML scoring.
    Average latency: 200-400ms. Cost: ~$0.0003/call.
    Hard timeout: 3s — never blocks trade execution.
    """
    if not HAIKU_ENABLED:
        return {}

    cache_key = f"haiku:{mint}"
    if redis_conn:
        try:
            cached = await redis_conn.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    prompt = f"""Token: {token_name} ({mint[:8]}...)

On-chain metrics:
- Liquidity: {features.get('liquidity_sol', 0):.2f} SOL
- Buy/Sell ratio 5min: {features.get('buy_sell_ratio_5min', 0):.2f}
- Bonding curve: {features.get('bonding_curve_progress', 0):.1%}
- Holder count: {features.get('holder_count', 0)}
- Top 10 holders: {features.get('top10_holder_pct', 0):.1f}%
- Dev wallet holds: {features.get('dev_wallet_hold_pct', 0):.1f}%
- Bundle detected: {bool(features.get('bundle_detected', 0))}
- Fresh wallet ratio: {features.get('fresh_wallet_ratio', 0):.2f}
- Creator prev launches: {features.get('creator_prev_launches', 0)}
- Creator rug rate: {features.get('creator_rug_rate', 0):.2f}
- Mint authority revoked: {bool(features.get('mint_authority_revoked', 0))}
- Token age: {features.get('token_age_seconds', 0)/60:.1f} minutes

Analyze and return JSON only."""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": HAIKU_MODEL,
                    "max_tokens": 200,
                    "system": HAIKU_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=3.0),
            ) as resp:
                if resp.status == 400:
                    try:
                        err_body = await resp.json()
                        err_msg = (err_body.get("error", {}).get("message", "unknown")
                                   if isinstance(err_body, dict) else str(err_body)[:100])
                    except Exception:
                        err_msg = "could not parse error body"
                    logger.warning("Haiku 400 for %s: %s — check ANTHROPIC_API_KEY and model name",
                                   mint[:8], err_msg)
                    return {}
                if resp.status != 200:
                    logger.debug("Haiku API %d for %s", resp.status, mint[:8])
                    return {}
                data = await resp.json()
                text = data["content"][0]["text"].strip()

                result = json.loads(text)
                result["source"] = "haiku"
                result["mint"] = mint

                if redis_conn:
                    try:
                        await redis_conn.set(cache_key, json.dumps(result), ex=HAIKU_CACHE_TTL)
                    except Exception:
                        pass

                logger.debug("Haiku enrichment for %s: risk=%d rec=%s",
                             mint[:8], result.get("risk_score", 50), result.get("recommendation", "?"))
                return result

    except asyncio.TimeoutError:
        logger.debug("Haiku timeout for %s — continuing without enrichment", mint[:8])
        return {}
    except json.JSONDecodeError:
        logger.debug("Haiku JSON parse error for %s", mint[:8])
        return {}
    except Exception as e:
        logger.debug("Haiku enrichment error for %s: %s", mint[:8], e)
        return {}


JITO_TIP_ACCOUNTS = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUC67HyGE6MjnMT63SURT1mX1k68pYCqmRF",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
}


async def _get_jito_bundle_stats(
    session: aiohttp.ClientSession,
    mint: str,
    tx_signatures: list[str] | None = None,
) -> dict:
    """
    Detect Jito bundle activity in first 10 transactions for a token.
    High bundle count = coordinated/bot buying = negative signal.
    """
    if not tx_signatures or not HELIUS_PARSE_TX_URL:
        return {"jito_bundle_count": 0, "jito_tip_lamports": 0}

    sigs = tx_signatures[:10]
    try:
        async with session.post(
            HELIUS_PARSE_TX_URL,
            json={"transactions": sigs},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                return {"jito_bundle_count": 0, "jito_tip_lamports": 0}
            txs = await resp.json()

        if not isinstance(txs, list):
            return {"jito_bundle_count": 0, "jito_tip_lamports": 0}

        bundle_count = 0
        tip_total = 0
        for tx in txs:
            for transfer in tx.get("nativeTransfers", []):
                if transfer.get("toUserAccount") in JITO_TIP_ACCOUNTS:
                    bundle_count += 1
                    tip_total += transfer.get("amount", 0)

        avg_tip = tip_total // max(bundle_count, 1)
        return {"jito_bundle_count": bundle_count, "jito_tip_lamports": avg_tip}

    except Exception as e:
        logger.debug("Jito bundle stats failed for %s: %s", mint[:12], e)
        return {"jito_bundle_count": 0, "jito_tip_lamports": 0}


def _compute_confidence(sources: set[str]) -> int:
    """Multi-source confidence: base 50 + 15 per additional source."""
    return BASE_CONFIDENCE + max(0, (len(sources) - 1)) * PER_SOURCE_BONUS


def _classify_target_personalities(signal: dict, rugcheck: dict) -> list[str]:
    """Determine which personalities this signal should be routed to."""
    targets = []
    age = signal.get("age_seconds", 0)
    sig_type = signal.get("signal_type", "")
    raw = signal.get("raw_data", {})

    # Speed Demon: new tokens, 0-30s (alpha), 30s-3min (confirmation), 5-15min post-grad
    if sig_type in ("new_token", "new_pool") and age <= 180:
        targets.append("speed_demon")
    elif sig_type == "migration" and 300 <= age <= 900:
        targets.append("speed_demon")  # Post-grad dip tier

    # GeckoTerminal trending: confirmed volume + momentum — analyst only
    if sig_type == "trending" or signal.get("source") == "geckoterminal_trending":
        return ["analyst"]

    # Nansen screener: graduated tokens — analyst only (no bonding curve)
    if sig_type == "analyst" or signal.get("source") == "nansen_screener":
        return ["analyst"]

    # Telegram alpha calls: route to analyst with boosted position sizing
    if sig_type == "telegram_call" or signal.get("source") == "telegram_alpha":
        return ["analyst"]

    # Analyst: confirmed tokens, multi-source signals, AND new_token (for bootstrap data collection)
    if sig_type in ("new_token", "new_pool", "token_trade", "sse_event", "migration"):
        targets.append("analyst")

    # Whale Tracker: account trades from tracked wallets + Helius webhook whale signals
    if sig_type in ("account_trade", "whale_trade", "whale_transfer"):
        targets.append("whale_tracker")

    # --- Expanded Helius webhook signal types ---

    # pool_created: strong insider signal → ALL three personalities
    if sig_type == "pool_created":
        targets = ["speed_demon", "analyst", "whale_tracker"]

    # liquidity_add: whale accumulating → whale_tracker
    if sig_type == "liquidity_add":
        if "whale_tracker" not in targets:
            targets.append("whale_tracker")

    # new_token with whale_created: same as regular new_token (already handled above)
    # but ensure it routes to whale_tracker as well
    if sig_type == "new_token" and raw.get("whale_created"):
        if "whale_tracker" not in targets:
            targets.append("whale_tracker")

    # Exit-type signals (whale_transfer, liquidity_remove, token_burn, account_closed)
    # are NOT routed to personalities — they are handled separately as exit alerts
    # in _process_signals() below

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
        liq = raw.get("liquidity_sol", raw.get("vSolInBondingCurve", 0))
        if isinstance(liq, str):
            try:
                liq = float(liq)
            except ValueError:
                liq = 0
        if liq < ANALYST_FILTERS["min_liquidity_sol"]:
            return False, f"liquidity {liq} < {ANALYST_FILTERS['min_liquidity_sol']}"

    # Rugcheck scoring is now handled separately via _score_rugcheck()
    # Only hard rejects (honeypot/blacklist/freeze/scam) block here;
    # soft risks reduce position size via rugcheck_multiplier on the signal.
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


# Direct ML engine reference — all services run in one process,
# so we can score inline without pubsub round-trip.
_ml_engine_instance = None


def _get_ml_engine():
    """Lazy-load the ML engine singleton from ml_model_accelerator."""
    global _ml_engine_instance
    if _ml_engine_instance is None:
        try:
            from services.ml_model_accelerator import AcceleratedMLEngine
            _ml_engine_instance = AcceleratedMLEngine()
            logger.info("ML engine loaded inline: phase=%d, n=%d, trained=%s",
                       _ml_engine_instance.phase, _ml_engine_instance.n_samples,
                       _ml_engine_instance.is_trained)
        except Exception as e:
            logger.warning("Failed to load ML engine inline: %s", e)
    return _ml_engine_instance


async def _request_ml_score(redis_conn: aioredis.Redis, features: dict, timeout: float = 5.0) -> tuple[float, bool]:
    """Score using inline ML engine (same process). Falls back to pubsub if inline fails."""
    engine = _get_ml_engine()
    if engine:
        try:
            score, is_trained = engine.predict(features)
            return score, is_trained
        except Exception as e:
            logger.debug("Inline ML score error: %s", e)

    # Fallback: pubsub (for when services run in separate processes)
    request_id = f"req_{time.time()}"
    request = {"request_id": request_id, "features": features}
    pubsub = redis_conn.pubsub()
    try:
        await pubsub.subscribe("ml:score_response")
        await redis_conn.publish("ml:score_request", json.dumps(request))
        deadline = time.time() + timeout
        async for message in pubsub.listen():
            if time.time() > deadline:
                break
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            if data.get("request_id") == request_id:
                return data.get("ml_score", 50.0), data.get("model_trained", False)
    except Exception as e:
        logger.debug("ML pubsub score error: %s", e)
    finally:
        await pubsub.aclose()

    return 50.0, False


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

                sig_type = signal.get("signal_type", "")
                age_sec = signal.get("age_seconds", 0)

                # Track graduation rate for market_health (FIX 13)
                if sig_type == "migration":
                    try:
                        await redis_conn.incr("market:migration_count_1h")
                        await redis_conn.expire("market:migration_count_1h", 3600)
                        migrations = int(await redis_conn.get("market:migration_count_1h") or 0)
                        new_tokens = int(await redis_conn.get("market:new_token_count_1h") or 1)
                        grad_est = round(migrations / max(new_tokens, 1), 3)
                        await redis_conn.set("market:grad_rate_estimate", str(grad_est), ex=3600)
                    except Exception:
                        pass
                if sig_type == "new_token":
                    try:
                        await redis_conn.incr("market:new_token_count_1h")
                        await redis_conn.expire("market:new_token_count_1h", 3600)
                    except Exception:
                        pass

                # --- Exit-type Helius signals: fast-track to alerts:exit_check ---
                if sig_type in ("whale_transfer", "liquidity_remove", "account_closed"):
                    urgency = "high" if sig_type in ("whale_transfer", "liquidity_remove") else "normal"
                    reason_map = {
                        "whale_transfer": "whale_cex_transfer",
                        "liquidity_remove": "whale_liquidity_remove",
                        "account_closed": "whale_account_closed",
                    }
                    await redis_conn.publish("alerts:exit_check", json.dumps({
                        "mint": mint,
                        "reason": reason_map.get(sig_type, sig_type),
                        "urgency": urgency,
                        "source": "helius_webhook",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                    logger.info("EXIT ALERT: %s %s from %s", sig_type, mint[:12], source)
                    continue  # Don't route exit signals through ML scoring

                # token_burn: only alert if we hold the mint (check bot:status)
                if sig_type == "token_burn":
                    try:
                        bot_raw = await redis_conn.get("bot:status")
                        if bot_raw:
                            bot_status = json.loads(bot_raw)
                            held_mints = {p.get("mint", "") for p in bot_status.get("positions", {}).values()}
                            if mint in held_mints:
                                await redis_conn.publish("alerts:exit_check", json.dumps({
                                    "mint": mint,
                                    "reason": "token_burn_while_held",
                                    "urgency": "high",
                                    "source": "helius_webhook",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                                logger.info("EXIT ALERT: token_burn %s (held position)", mint[:12])
                    except Exception:
                        pass
                    continue

                # --- FIX 15: Token age hard gate ---
                if sig_type == "new_token" and age_sec > 180:
                    logger.debug("Age reject %s: %ds > 180s", mint[:12], age_sec)
                    continue

                # --- FIX 16: Buy/sell ratio hard gate ---
                bsr_raw = signal.get("raw_data", {}).get("buy_sell_ratio_5min", 1.0)
                try:
                    bsr_val = float(bsr_raw)
                except (TypeError, ValueError):
                    bsr_val = 1.0
                if bsr_val < 0.8 and sig_type not in ("whale_entry", "smart_money_inflow", "sm_concentration", "fund_activity", "account_trade", "whale_trade", "liquidity_add", "pool_created", "new_token", "analyst"):
                    logger.debug("BSR reject %s: %.2f < 0.8", mint[:12], bsr_val)
                    continue

                # --- FIX 17: Graduation proximity filter ---
                v_sol = signal.get("raw_data", {}).get("vSolInBondingCurve", 0)
                try:
                    v_sol = float(v_sol)
                except (TypeError, ValueError):
                    v_sol = 0
                graduation_zone = 65 <= v_sol <= 85
                if graduation_zone:
                    signal["graduation_zone"] = True

                # --- FIX 18: Repeated mint guard ---
                already_traded = await redis_conn.sismember("traded:mints", mint)
                if already_traded:
                    logger.debug("Repeated mint reject %s (traded in last 2h)", mint[:12])
                    continue

                # --- Get market mode ---
                market_mode = "NORMAL"
                mode_str = await redis_conn.get("market:mode:current")
                if mode_str:
                    market_mode = mode_str

                if market_mode == "HIBERNATE":
                    logger.debug("HIBERNATE mode — skipping %s", mint[:12])
                    continue

                # --- Enrich with Rugcheck (cached) + token details (concurrent) ---
                rugcheck, token_details = await asyncio.gather(
                    _get_rugcheck_enriched(session, mint, redis_conn),
                    _fetch_token_details(session, mint, redis_conn),
                )

                # Log rugcheck score to Redis for calibration (/api/debug/rugcheck-scores)
                if rugcheck.get("score") is not None:
                    try:
                        await redis_conn.lpush("debug:rugcheck_scores", json.dumps({
                            "mint": mint[:12], "score": rugcheck["score"],
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }))
                        await redis_conn.ltrim("debug:rugcheck_scores", 0, 49)
                    except Exception:
                        pass

                # --- Helius enhanced checks: dev wallet sells + bundle detection ---
                raw_data = signal.get("raw_data", {})
                creator_addr = token_details.get("creator_address", raw_data.get("traderPublicKey", ""))
                early_tx_sigs = [raw_data.get("signature", "")] if raw_data.get("signature") else []
                # Gather additional signatures from PumpPortal trade data if available
                if raw_data.get("tx_signatures"):
                    early_tx_sigs.extend(raw_data["tx_signatures"][:19])

                # Helius enrichment — gated by HELIUS_ENRICHMENT_ENABLED (default true)
                if HELIUS_ENRICHMENT_ENABLED:
                    dev_sell_data, bundle_data, creator_stats, jito_stats = await asyncio.gather(
                        _check_dev_wallet_sells(session, creator_addr, mint),
                        _check_bundle_detection(session, early_tx_sigs),
                        _get_creator_stats(session, creator_addr, redis_conn),
                        _get_jito_bundle_stats(session, mint, early_tx_sigs),
                        return_exceptions=True,
                    )
                else:
                    dev_sell_data, bundle_data, creator_stats, jito_stats = {}, {}, {}, {}
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
                if isinstance(creator_stats, dict):
                    token_details.update(creator_stats)
                if isinstance(jito_stats, dict):
                    token_details.update(jito_stats)

                # --- Classify target personalities ---
                targets = _classify_target_personalities(signal, rugcheck)
                raw_data = signal.get("raw_data", {})
                bc_val = raw_data.get("bondingCurveProgress", raw_data.get("bonding_curve_progress", 0))
                logger.info("TARGETS for %s: %s (type=%s, bc=%.2f, age=%ds, sources=%s)",
                            mint[:12], targets, sig_type, float(bc_val or 0),
                            age_sec, list(_seen_tokens[mint]["sources"]))
                if not targets:
                    continue

                # --- Telegram alpha boost ---
                position_size_multiplier = 1.0
                if signal.get("source") == "telegram_alpha":
                    position_size_multiplier = 1.5
                    logger.info("TELEGRAM CALL: %s — position mult=1.5x", mint[:12])

                # --- Speed Demon pre-filters (before ML scoring) ---
                if "speed_demon" in targets:
                    # Twitter follower lookup (non-blocking, skipped if no API key)
                    tw_url = signal.get("twitter_url", "")
                    if tw_url:
                        followers = await _get_twitter_followers(session, tw_url, redis_conn)
                        signal["twitter_followers"] = followers

                    passes, reason, position_size_multiplier = _apply_speed_demon_prefilters(signal, rugcheck)
                    logger.info(
                        "FILTER: %s %s reason=%s mult=%.2f social=%s followers=%d bundle=%.1f%% mc=$%.0f liq=%.1f",
                        "PASS" if passes else "REJECT", mint[:12], reason or "passed_all",
                        position_size_multiplier, signal.get("has_social", "?"),
                        signal.get("twitter_followers", -1), rugcheck.get("bundle_pct", 0),
                        float(raw_data.get("usdMarketCap", raw_data.get("market_cap_usd", 0)) or 0),
                        float(raw_data.get("vSolInBondingCurve", raw_data.get("liquidity_sol", 0)) or 0),
                    )
                    if not passes:
                        targets = [t for t in targets if t != "speed_demon"]
                        if not targets:
                            continue

                # --- Confidence score ---
                confidence = _compute_confidence(_seen_tokens[mint]["sources"])

                # Apply confidence_boost from Helius webhook raw_data (pool_created=+40, liquidity_add=+20)
                webhook_boost = int(signal.get("raw_data", {}).get("confidence_boost", 0))
                if webhook_boost:
                    confidence = min(100, confidence + webhook_boost)
                    logger.info("Helius boost %s: +%d confidence (now %d)", mint[:12], webhook_boost, confidence)

                # --- Build feature dict for ML scoring (37 features) ---
                raw = signal.get("raw_data", {})
                features = {
                    # === Original 26 features ===
                    "liquidity_sol": float(raw.get("vSolInBondingCurve", raw.get("liquidity_sol", 0))),
                    "liquidity_velocity": float(raw.get("liquidity_velocity", 0)),
                    "bonding_curve_progress": float(raw.get("bondingCurveProgress", raw.get("bonding_curve_progress", 0))) or
                        (float(raw.get("vSolInBondingCurve", 0)) / 85.0 if float(raw.get("vSolInBondingCurve", 0)) > 0 else 0),
                    "buy_sell_ratio_5min": float(raw.get("buy_sell_ratio_5min", 1.0)),
                    "holder_count": int(token_details.get("holder_count", raw.get("holder_count", raw.get("holders", 0)))),
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
                    # === Nansen flow features (P0) — default 0 if Nansen unavailable ===
                    "nansen_sm_inflow_ratio": float(token_details.get("nansen_sm_inflow_ratio", 0)),
                    "nansen_whale_outflow_ratio": float(token_details.get("nansen_whale_outflow_ratio", 0)),
                    "nansen_exchange_flow": float(token_details.get("nansen_exchange_flow", 0)),
                    "nansen_fresh_wallet_flow_ratio": float(token_details.get("nansen_fresh_wallet_flow_ratio", 0)),
                    # === Nansen quant score features (P0) ===
                    "nansen_performance_score": float(token_details.get("nansen_performance_score", 0)),
                    "nansen_risk_score": float(token_details.get("nansen_risk_score", 0)),
                    "nansen_concentration_risk": float(token_details.get("nansen_concentration_risk", 0)),
                    "nansen_sm_count": int(token_details.get("nansen_sm_count", 0)),
                    # === Nansen holder features (P1) ===
                    "nansen_labeled_exchange_holder_pct": float(token_details.get("nansen_labeled_exchange_holder_pct", 0)),
                    # === 7 new features (Section 23) ===
                    "creator_prev_launches": int(token_details.get("creator_prev_launches", 0)),
                    "creator_rug_rate": float(token_details.get("creator_rug_rate", 0.5)),
                    "creator_avg_hold_hours": float(token_details.get("creator_avg_hold_hours", 0)),
                    "jito_bundle_count": int(token_details.get("jito_bundle_count", 0)),
                    "jito_tip_lamports": int(token_details.get("jito_tip_lamports", 0)),
                    "token_freshness_score": math.exp(-float(signal.get("age_seconds", 0)) / 3600.0 / 6.0),
                    # Rugcheck risks array contains "mintAuthority" risk if authority is ACTIVE (not revoked = risky)
                    "mint_authority_revoked": 0.0 if any("mintauthority" in r.lower() for r in rugcheck.get("risk_names", [])) else 1.0,
                    # === Trending / multi-source features ===
                    "volume_1h_usd": float(raw.get("volume_1h_usd", 0)),
                    "trending_strength": float(raw.get("trending_strength", 0)),
                    "source_count": len(_seen_tokens.get(mint, {}).get("sources", set())),
                    # === Speed Demon pre-filter features ===
                    "has_social": int(signal.get("has_social", False)),
                    "twitter_followers": signal.get("twitter_followers", -1),
                    "bundle_pct": rugcheck.get("bundle_pct", 0),
                    "rugcheck_score": rugcheck.get("score", 0),
                    "pre_filter_score": position_size_multiplier,
                }

                # Compute trending_strength if source is trending
                if signal.get("source") == "geckoterminal_trending":
                    v1h = features["volume_1h_usd"]
                    pch = features["price_change_1h_pct"]
                    bsr = features["buy_sell_ratio_5min"]
                    features["trending_strength"] = min(100, int(
                        (min(v1h, 100000) / 100000 * 40) +
                        (min(max(pch, 0), 50) / 50 * 30) +
                        (min(bsr, 3) / 3 * 30)
                    ))

                # Fill in market health data
                health_str = await redis_conn.get("market:health")
                if health_str:
                    health = json.loads(health_str)
                    features["sol_price_usd"] = health.get("sol_price", 0)
                    features["cfgi_score"] = health.get("cfgi", 0)
                    # Derive market_cap_usd from liquidity if not available
                    if features["market_cap_usd"] == 0 and features["liquidity_sol"] > 0:
                        sol_px = features.get("sol_price_usd") or 0
                        features["market_cap_usd"] = features["liquidity_sol"] * 2 * sol_px

                # ML scoring — always runs
                token_name = signal.get("raw_data", {}).get("name", signal.get("raw_data", {}).get("symbol", mint[:12]))
                ml_score, ml_trained = await _request_ml_score(redis_conn, features)

                logger.info("ML SCORE %s: %.1f (trained=%s) targets=%s age=%ds",
                           mint[:12], ml_score, ml_trained, targets, age_sec)

                # Haiku enrichment — lazy, fetched once per signal only after a personality
                # passes hard filters + ML gate. Reused for subsequent personalities.
                haiku_result = {}

                # --- Route to each target personality ---
                bc_progress = features["bonding_curve_progress"]

                for personality in targets:
                    # FIX 15: Speed demon age tightening (60s max)
                    if personality == "speed_demon" and age_sec > 60:
                        logger.info("AGE REJECT %s for speed_demon: %ds > 60s", mint[:12], age_sec)
                        continue

                    # FIX 17: Graduation zone — Speed Demon skips entirely
                    if graduation_zone and personality == "speed_demon":
                        logger.debug("Graduation zone reject %s for speed_demon", mint[:12])
                        continue

                    # Rugcheck risk-adjusted scoring (replaces old hard gate)
                    hard_reject, rc_reason, rc_multiplier, risk_level = _score_rugcheck(rugcheck)
                    if hard_reject:
                        logger.info(
                            "HARD REJECT: %s reason=%s (unrecoverable)",
                            mint[:8], rc_reason,
                        )
                        continue

                    if rc_multiplier < 1.0:
                        logger.info(
                            "RUGCHECK RISK: %s level=%s mult=%.2f "
                            "(still trading with reduced size)",
                            mint[:8], risk_level, rc_multiplier,
                        )

                    # Store multiplier for position sizing downstream
                    signal["rugcheck_multiplier"] = rc_multiplier
                    signal["rugcheck_risk_level"] = risk_level

                    # Hard filters (personality-specific, no longer includes rugcheck)
                    passed, reason = _apply_hard_filters(personality, signal, rugcheck)
                    if not passed:
                        logger.info("HARD REJECT %s for %s: %s", mint[:12], personality, reason)
                        continue

                    # KOTH zone check — disabled in aggressive paper mode
                    if not AGGRESSIVE_PAPER:
                        passed, reason = _check_koth_zone(bc_progress, personality, ml_score)
                        if not passed:
                            logger.info("KOTH reject %s for %s: %s", mint[:12], personality, reason)
                            continue

                    # ML threshold check — use bootstrap thresholds during cold start
                    if ml_trained:
                        threshold = ML_THRESHOLDS.get(personality, 70)
                    else:
                        threshold = ML_BOOTSTRAP_THRESHOLDS.get(personality, 45)

                    if market_mode == "FRENZY":
                        threshold -= 5
                    elif market_mode == "DEFENSIVE" and ml_trained:
                        threshold += 10  # Only raise in DEFENSIVE when model is trained

                    if ml_score < threshold:
                        logger.info("ML reject %s for %s: %.1f < %d (trained=%s)",
                                    mint[:12], personality, ml_score, threshold, ml_trained)
                        continue

                    # Lazy Haiku enrichment — only fires once per mint, after all hard gates
                    if HAIKU_ENABLED and not haiku_result:
                        try:
                            haiku_result = await asyncio.wait_for(
                                _haiku_enrichment(mint, token_name, features, redis_conn),
                                timeout=2.0,
                            )
                        except asyncio.TimeoutError:
                            haiku_result = {}

                    if haiku_result:
                        haiku_risk = haiku_result.get("risk_score", 50)
                        haiku_rec = haiku_result.get("recommendation", "pass")
                        if haiku_rec == "hard_pass":
                            logger.info("HAIKU VETO: %s — risk=%d flags=%s",
                                         mint[:12], haiku_risk, haiku_result.get("red_flags", []))
                            continue
                        elif haiku_rec == "strong_buy" and haiku_risk < 20:
                            ml_score = min(ml_score * 1.15, 95.0)
                        elif haiku_risk > 70:
                            ml_score = ml_score * 0.8
                        logger.info("HAIKU: %s risk=%d rec=%s final_score=%.1f",
                                     mint[:12], haiku_risk, haiku_rec, ml_score)

                    # Source count check for Analyst — relaxed in aggressive paper mode
                    if AGGRESSIVE_PAPER:
                        min_sources_required = 1
                    else:
                        min_sources_required = 1 if not ml_trained else ANALYST_FILTERS.get("min_sources", 2)
                    if personality == "analyst" and len(_seen_tokens[mint]["sources"]) < min_sources_required:
                        logger.info("Analyst source gate: %s has %d/%d sources",
                                    mint[:12], len(_seen_tokens[mint]["sources"]), min_sources_required)
                        continue

                    # --- Nansen smart money confirmation ---
                    # Flow-based confidence boost applies to ALL personalities (data stored for ML)
                    # Who-bought-sold API call only for Analyst + Whale Tracker (Speed Demon uses flow data only)
                    nansen_sm_count = 0

                    # P0: Flow-based confidence (from token_details, already fetched)
                    flow_boost = int(token_details.get("nansen_flow_confidence_boost", 0))
                    flow_signal = int(token_details.get("nansen_flow_signal", 0))
                    if flow_boost != 0:
                        confidence += flow_boost
                        confidence = max(0, min(100, confidence))
                        logger.info("Nansen flow boost for %s/%s: %+d (signal=%d, conf=%d)",
                                     mint[:12], personality, flow_boost, flow_signal, confidence)

                    # Reject on strong bearish flow signal (whale outflow > 3x avg)
                    if flow_signal == -1 and personality != "speed_demon":
                        logger.info("Nansen flow BEARISH for %s — rejecting %s", mint[:12], personality)
                        continue

                    # Who-bought-sold check (Analyst + Whale Tracker only — extra API call)
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
                        # Haiku enrichment (for dashboard display)
                        "haiku_risk": haiku_result.get("risk_score", -1),
                        "haiku_rec": haiku_result.get("recommendation", ""),
                        "haiku_flags": haiku_result.get("red_flags", []),
                        "position_size_multiplier": position_size_multiplier,
                        "rugcheck_multiplier": rc_multiplier,
                        "rugcheck_risk_level": risk_level,
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
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=20)
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
