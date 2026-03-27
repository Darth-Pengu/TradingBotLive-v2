"""
ZMN Bot Nansen API Client v2
==============================
Shared client for all Nansen API calls with:
- Redis-based rate limiter (max 1 call per 2 seconds across all services)
- Response time logging for credit monitoring
- Redis caching for wallet PnL data (6-hour TTL)
- Monthly credit counter (tracks usage toward 10k/month budget)
- try/except on all calls — bot continues if Nansen is down

Endpoints (8 new + 4 existing = 12 total):
  Existing: wallet_pnl, smart_money_buyers, smart_money_sellers, screen_new_tokens, smart_money_holdings
  New (P0): get_token_flow_summary, get_token_quant_scores
  New (P1): get_labeled_top_holders, get_smart_money_discovery
  New (P2): get_nansen_top_tokens, get_whale_portfolio, get_token_flows_granular
  New (P3): get_token_pnl_leaderboard
  New (exits): get_smart_money_dex_sells
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import aiohttp
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nansen_client")

NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")
NANSEN_BASE_URL = "https://api.nansen.ai/api/v1"
NANSEN_RATE_LIMIT_KEY = "nansen:rate_limit"
NANSEN_RATE_LIMIT_SECONDS = 2  # Max 1 call per 2 seconds across all services
NANSEN_CREDIT_COUNTER_KEY = "nansen:credits:{month}"  # Monthly credit counter
NANSEN_MONTHLY_BUDGET = 10000


def _is_available() -> bool:
    return bool(NANSEN_API_KEY)


async def _rate_limit(redis_conn: aioredis.Redis | None):
    """Redis-based rate limiter: wait until 2 seconds since last call."""
    if not redis_conn:
        await asyncio.sleep(NANSEN_RATE_LIMIT_SECONDS)
        return
    while True:
        last_call = await redis_conn.get(NANSEN_RATE_LIMIT_KEY)
        if last_call:
            elapsed = time.time() - float(last_call)
            if elapsed < NANSEN_RATE_LIMIT_SECONDS:
                await asyncio.sleep(NANSEN_RATE_LIMIT_SECONDS - elapsed)
                continue
        await redis_conn.set(NANSEN_RATE_LIMIT_KEY, str(time.time()), ex=10)
        return


async def _increment_credit_counter(redis_conn: aioredis.Redis | None):
    """Track monthly Nansen API credit usage."""
    if not redis_conn:
        return
    month_key = NANSEN_CREDIT_COUNTER_KEY.format(
        month=datetime.now(timezone.utc).strftime("%Y-%m")
    )
    try:
        count = await redis_conn.incr(month_key)
        # Set expiry to 35 days on first increment
        if count == 1:
            await redis_conn.expire(month_key, 35 * 86400)
        if count % 500 == 0:
            logger.info("Nansen credit usage this month: %d / %d", count, NANSEN_MONTHLY_BUDGET)
        if count >= NANSEN_MONTHLY_BUDGET * 0.9:
            logger.warning("Nansen credits at %d/%d (%.0f%%) — approaching limit",
                           count, NANSEN_MONTHLY_BUDGET, count / NANSEN_MONTHLY_BUDGET * 100)
    except Exception:
        pass


async def get_credit_usage(redis_conn: aioredis.Redis) -> dict:
    """Get current month's credit usage stats."""
    month_key = NANSEN_CREDIT_COUNTER_KEY.format(
        month=datetime.now(timezone.utc).strftime("%Y-%m")
    )
    try:
        count = int(await redis_conn.get(month_key) or 0)
        return {
            "used": count,
            "budget": NANSEN_MONTHLY_BUDGET,
            "remaining": max(0, NANSEN_MONTHLY_BUDGET - count),
            "pct_used": round(count / NANSEN_MONTHLY_BUDGET * 100, 1),
        }
    except Exception:
        return {"used": 0, "budget": NANSEN_MONTHLY_BUDGET, "remaining": NANSEN_MONTHLY_BUDGET, "pct_used": 0}


async def nansen_post(
    session: aiohttp.ClientSession,
    endpoint: str,
    body: dict,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Make a rate-limited POST to the Nansen API.
    Returns response dict or None on failure. Never raises.
    """
    if not _is_available():
        return None

    url = f"{NANSEN_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {
        "apikey": NANSEN_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        await _rate_limit(redis_conn)
        await _increment_credit_counter(redis_conn)
        start = time.time()

        async with session.post(url, json=body, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed_ms = (time.time() - start) * 1000
            logger.info("Nansen POST %s — %d (%.0fms)", endpoint, resp.status, elapsed_ms)

            if resp.status == 200:
                return await resp.json()
            elif resp.status == 403:
                body_text = await resp.text()
                if "credit" in body_text.lower() or "insufficient" in body_text.lower():
                    logger.error("Nansen credits exhausted — screener disabled until restart")
                else:
                    logger.error("Nansen %s forbidden (403): %s", endpoint, body_text[:200])
            elif resp.status == 429:
                logger.warning("Nansen rate limited on %s — backing off", endpoint)
                await asyncio.sleep(5)
            else:
                body_text = await resp.text()
                logger.warning("Nansen %s HTTP %d: %s", endpoint, resp.status, body_text[:200])
    except Exception as e:
        logger.warning("Nansen %s error: %s", endpoint, e)
    return None


async def nansen_get(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: dict | None = None,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Make a rate-limited GET to the Nansen API.
    Returns response dict or None on failure. Never raises.
    """
    if not _is_available():
        return None

    url = f"{NANSEN_BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"apikey": NANSEN_API_KEY}

    try:
        await _rate_limit(redis_conn)
        await _increment_credit_counter(redis_conn)
        start = time.time()

        async with session.get(url, params=params, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed_ms = (time.time() - start) * 1000
            logger.info("Nansen GET %s — %d (%.0fms)", endpoint, resp.status, elapsed_ms)

            if resp.status == 200:
                return await resp.json()
            elif resp.status == 429:
                logger.warning("Nansen rate limited on %s — backing off", endpoint)
                await asyncio.sleep(5)
            else:
                body_text = await resp.text()
                logger.warning("Nansen %s HTTP %d: %s", endpoint, resp.status, body_text[:200])
    except Exception as e:
        logger.warning("Nansen %s error: %s", endpoint, e)
    return None


# ---------------------------------------------------------------------------
# Existing helpers (unchanged API contracts)
# ---------------------------------------------------------------------------
async def get_wallet_pnl(
    session: aiohttp.ClientSession,
    wallet_address: str,
    days: int = 30,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Get wallet PnL summary from Nansen profiler.
    Cached in Redis for 6 hours.
    """
    cache_key = f"nansen:wallet:{wallet_address}"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = now.strftime("%Y-%m-%dT23:59:59Z")

    result = await nansen_post(session, "/profiler/address/pnl-summary", {
        "address": wallet_address,
        "chain": "solana",
        "date": {"from": from_date, "to": to_date},
    }, redis_conn)

    if result and redis_conn:
        await redis_conn.set(cache_key, json.dumps(result), ex=21600)  # 6-hour TTL

    return result


async def get_smart_money_buyers(
    session: aiohttp.ClientSession,
    mint: str,
    hours_back: int = 1,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Check who bought/sold a token recently — filtered to smart money labels.
    Used as a confirmation signal for Analyst and Whale Tracker.
    """
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    return await nansen_post(session, "/tgm/who-bought-sold", {
        "chain": "solana",
        "token_address": mint,
        "buy_or_sell": "BUY",
        "date": {"from": from_date, "to": to_date},
        "filters": {
            "include_smart_money_labels": ["Fund", "Smart Trader", "30D Smart Trader"],
        },
    }, redis_conn)


async def get_smart_money_sellers(
    session: aiohttp.ClientSession,
    mint: str,
    hours_back: int = 1,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """Check if smart money is selling a token we hold."""
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    return await nansen_post(session, "/tgm/who-bought-sold", {
        "chain": "solana",
        "token_address": mint,
        "buy_or_sell": "SELL",
        "date": {"from": from_date, "to": to_date},
        "filters": {
            "include_smart_money_labels": ["Fund", "Smart Trader", "30D Smart Trader"],
        },
    }, redis_conn)


async def screen_new_tokens(
    session: aiohttp.ClientSession,
    redis_conn: aioredis.Redis | None = None,
) -> list[dict]:
    """
    Screen for new high-cap Solana tokens.
    Returns top 20 tokens by market cap, max 1 day old.
    """
    result = await nansen_post(session, "/token-screener", {
        "chains": ["solana"],
        "timeframe": "1h",
        "filters": {"token_age_days": {"max": 1}},
        "order_by": [{"field": "market_cap_usd", "direction": "DESC"}],
        "pagination": {"page": 1, "per_page": 20},
    }, redis_conn)

    if result and "data" in result:
        return result["data"]
    if result and isinstance(result, list):
        return result
    return []


async def get_smart_money_holdings(
    session: aiohttp.ClientSession,
    redis_conn: aioredis.Redis | None = None,
) -> list[dict]:
    """
    Get top 50 smart money holdings on Solana.
    Used by governance for weekly analysis.
    """
    result = await nansen_post(session, "/smart-money/holdings", {
        "chains": ["solana"],
        "filters": {
            "include_smart_money_labels": ["Fund", "Smart Trader"],
        },
        "order_by": [{"field": "value_usd", "direction": "DESC"}],
        "pagination": {"page": 1, "per_page": 50},
    }, redis_conn)

    if result and "data" in result:
        return result["data"]
    if result and isinstance(result, list):
        return result
    return []


# ---------------------------------------------------------------------------
# NEW: P0 — Smart Money Flow Confirmation
# ---------------------------------------------------------------------------
async def get_token_flow_summary(
    session: aiohttp.ClientSession,
    mint: str,
    lookback: str = "1h",
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Get aggregated token flows across 6 segments:
    Smart Traders, Whales, Exchanges, Public Figures, Top PnL Traders, Fresh Wallets.

    Returns flow data with magnitude vs average for each segment.
    Cached in Redis for 5 minutes (short TTL — flow data is time-sensitive).

    Budget: ~80 calls/day (all signals including Speed Demon for ML data)
    """
    cache_key = f"nansen:flows:{mint}:{lookback}"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await nansen_post(session, "/tgm/token-recent-flows-summary", {
        "chain": "solana",
        "tokenAddress": mint,
        "lookbackPeriod": lookback,
    }, redis_conn)

    if result and redis_conn:
        await redis_conn.set(cache_key, json.dumps(result), ex=300)  # 5-min TTL

    return result


def parse_flow_summary(raw: dict | None) -> dict:
    """
    Parse flow summary into ML-ready features + trading signals.
    Returns dict with:
      - nansen_sm_inflow_ratio: smart money flow / average (>1 = bullish)
      - nansen_whale_outflow_ratio: whale outflow / average (>1 = bearish)
      - nansen_exchange_flow: exchange net flow (positive = selling to exchange)
      - nansen_fresh_wallet_flow_ratio: fresh wallet activity / average (>5 = suspicious)
      - nansen_flow_signal: +1 (bullish), 0 (neutral), -1 (bearish)
    """
    defaults = {
        "nansen_sm_inflow_ratio": 0.0,
        "nansen_whale_outflow_ratio": 0.0,
        "nansen_exchange_flow": 0.0,
        "nansen_fresh_wallet_flow_ratio": 0.0,
        "nansen_flow_signal": 0,
        "nansen_flow_confidence_boost": 0,
    }
    if not raw:
        return defaults

    segments = {}
    # Parse the response — Nansen returns segments with flow amounts and ratios
    data = raw.get("data", raw)
    if isinstance(data, list):
        for seg in data:
            name = seg.get("segment", seg.get("name", "")).lower()
            segments[name] = {
                "flow_usd": float(seg.get("flow_usd", seg.get("flowUsd", 0)) or 0),
                "ratio": float(seg.get("ratio", seg.get("flowRatio", 0)) or 0),
                "wallets": int(seg.get("wallets", seg.get("walletCount", 0)) or 0),
            }
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, dict):
                segments[key.lower()] = {
                    "flow_usd": float(val.get("flow_usd", val.get("flowUsd", 0)) or 0),
                    "ratio": float(val.get("ratio", val.get("flowRatio", 0)) or 0),
                    "wallets": int(val.get("wallets", val.get("walletCount", 0)) or 0),
                }

    if not segments:
        return defaults

    # Extract per-segment signals
    sm = segments.get("smart traders", segments.get("smart_traders", segments.get("smart money", {})))
    whale = segments.get("whales", segments.get("whale", {}))
    exchange = segments.get("exchanges", segments.get("exchange", {}))
    fresh = segments.get("fresh wallets", segments.get("fresh_wallets", {}))

    sm_ratio = sm.get("ratio", 0)
    whale_ratio = whale.get("ratio", 0)
    exchange_flow = exchange.get("flow_usd", 0)
    fresh_ratio = fresh.get("ratio", 0)

    # Compute composite signal
    signal = 0
    confidence_boost = 0

    # Bullish: smart money inflow > 2x average AND exchange outflow (negative)
    if sm_ratio > 2.0 and exchange_flow < 0:
        signal = 1
        confidence_boost = 25
    # Very bullish: smart money > 3x AND whale accumulation
    elif sm_ratio > 3.0 and whale.get("flow_usd", 0) > 0:
        signal = 1
        confidence_boost = 30

    # Bearish: whale outflow > 3x average
    if whale_ratio > 3.0 and whale.get("flow_usd", 0) < 0:
        signal = -1
        confidence_boost = -20

    # Suspicious: fresh wallet > 5x average (likely botted)
    if fresh_ratio > 5.0:
        confidence_boost -= 15

    return {
        "nansen_sm_inflow_ratio": round(sm_ratio, 2),
        "nansen_whale_outflow_ratio": round(whale_ratio, 2),
        "nansen_exchange_flow": round(exchange_flow, 2),
        "nansen_fresh_wallet_flow_ratio": round(fresh_ratio, 2),
        "nansen_flow_signal": signal,
        "nansen_flow_confidence_boost": confidence_boost,
    }


# ---------------------------------------------------------------------------
# NEW: P0 — Token Quant Scores (ML feature enrichment)
# ---------------------------------------------------------------------------
async def get_token_quant_scores(
    session: aiohttp.ClientSession,
    mint: str,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Get Nansen quantitative risk/reward indicators for a token.
    Includes: price momentum, liquidity risk, concentration risk, BTC reflexivity.

    Cached in Redis for 1 hour (scores update in batches, not real-time).
    Budget: ~50 calls/day (all signals that pass initial hard filters)
    """
    cache_key = f"nansen:quant:{mint}"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await nansen_post(session, "/nansen-scores/token", {
        "chain": "solana",
        "tokenAddress": mint,
    }, redis_conn)

    if result and redis_conn:
        await redis_conn.set(cache_key, json.dumps(result), ex=3600)  # 1-hour TTL

    return result


def parse_quant_scores(raw: dict | None) -> dict:
    """
    Parse quant scores into ML-ready features.
    Returns dict with normalized scores for the ML feature vector.
    """
    defaults = {
        "nansen_performance_score": 0.0,
        "nansen_risk_score": 0.0,
        "nansen_price_momentum": 0.0,
        "nansen_liquidity_risk": 0.0,
        "nansen_concentration_risk": 0.0,
        "nansen_btc_reflexivity": 0.0,
    }
    if not raw:
        return defaults

    data = raw.get("data", raw)
    if isinstance(data, list) and data:
        data = data[0]

    if not isinstance(data, dict):
        return defaults

    # Performance score: -60 to +75 → normalize to 0-1
    perf = float(data.get("performanceScore", data.get("performance_score", 0)) or 0)
    risk = float(data.get("riskScore", data.get("risk_score", 0)) or 0)

    # Extract individual indicators
    indicators = data.get("indicators", data.get("reward_indicators", {}))
    risk_indicators = data.get("risk_indicators", {})
    if isinstance(indicators, list):
        ind_dict = {}
        for ind in indicators:
            name = ind.get("name", ind.get("indicator", ""))
            ind_dict[name] = ind
        indicators = ind_dict
    if isinstance(risk_indicators, list):
        ri_dict = {}
        for ind in risk_indicators:
            name = ind.get("name", ind.get("indicator", ""))
            ri_dict[name] = ind
        risk_indicators = ri_dict

    def _get_score(indicator_dict: dict, name: str) -> float:
        ind = indicator_dict.get(name, {})
        if isinstance(ind, dict):
            # Score mapping: bullish=1, neutral=0, bearish=-1 / low=0, medium=0.5, high=1
            score_str = str(ind.get("score", "")).lower()
            if score_str in ("bullish", "low"):
                return 1.0
            elif score_str in ("neutral", "medium"):
                return 0.0
            elif score_str in ("bearish", "high"):
                return -1.0
            # Try numeric percentile
            pct = ind.get("percentile", None)
            if pct is not None:
                return float(pct) / 100.0
        return 0.0

    return {
        "nansen_performance_score": round(perf / 75.0, 3) if perf != 0 else 0.0,  # Normalize to ~[-0.8, 1.0]
        "nansen_risk_score": round(risk / 80.0, 3) if risk != 0 else 0.0,
        "nansen_price_momentum": _get_score(indicators, "price-momentum"),
        "nansen_liquidity_risk": _get_score(risk_indicators, "liquidity-risk"),
        "nansen_concentration_risk": _get_score(risk_indicators, "concentration-risk"),
        "nansen_btc_reflexivity": _get_score(risk_indicators, "btc-reflexivity"),
    }


# ---------------------------------------------------------------------------
# NEW: P1 — Labeled Top Holders (replaces Helius getTokenLargestAccounts)
# ---------------------------------------------------------------------------
async def get_labeled_top_holders(
    session: aiohttp.ClientSession,
    mint: str,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Get top 25 token holders with Nansen labels (whale, exchange, smart money, fund)
    and 24h/7d/30d balance changes.

    Cached in Redis for 15 minutes.
    Budget: ~50 calls/day
    """
    cache_key = f"nansen:holders:{mint}"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await nansen_post(session, "/tgm/token-current-top-holders", {
        "chain": "solana",
        "tokenAddress": mint,
        "labelType": "top_100_holders",
        "order_by": "amount",
        "order_by_direction": "desc",
    }, redis_conn)

    if result and redis_conn:
        await redis_conn.set(cache_key, json.dumps(result), ex=900)  # 15-min TTL

    return result


def parse_labeled_holders(raw: dict | None) -> dict:
    """
    Parse labeled holder data into ML features + trading signals.
    Returns:
      - nansen_labeled_exchange_holder_pct: % held by exchange deposit addresses
      - nansen_smart_money_holder_count: count of smart money in top holders
      - nansen_top_holder_24h_change: net 24h change direction of top 10
      - top10_holder_pct: replacement for Helius version (now with labels)
    """
    defaults = {
        "nansen_labeled_exchange_holder_pct": 0.0,
        "nansen_smart_money_holder_count": 0,
        "nansen_top_holder_24h_change": 0.0,
        "top10_holder_pct": 0.0,
        "holder_count": 0,
    }
    if not raw:
        return defaults

    holders = raw.get("data", raw.get("result", []))
    if isinstance(holders, dict) and "rows" in holders:
        holders = holders["rows"]
    if not isinstance(holders, list) or not holders:
        return defaults

    total_balance = 0.0
    top10_balance = 0.0
    exchange_balance = 0.0
    sm_count = 0
    net_24h_change = 0.0

    for i, holder in enumerate(holders[:25]):
        balance = float(holder.get("balance", holder.get("amount", 0)) or 0)
        label = str(holder.get("label", holder.get("fullName", ""))).lower()
        change_24h = float(holder.get("balance_change_24h", holder.get("balanceChange24h", 0)) or 0)

        total_balance += balance
        if i < 10:
            top10_balance += balance
            net_24h_change += change_24h

        if any(x in label for x in ("exchange", "binance", "coinbase", "kraken", "okx", "bybit", "cex")):
            exchange_balance += balance
        if any(x in label for x in ("smart", "fund", "trader")):
            sm_count += 1

    top10_pct = (top10_balance / total_balance * 100) if total_balance > 0 else 0
    exchange_pct = (exchange_balance / total_balance * 100) if total_balance > 0 else 0

    return {
        "nansen_labeled_exchange_holder_pct": round(exchange_pct, 1),
        "nansen_smart_money_holder_count": sm_count,
        "nansen_top_holder_24h_change": round(net_24h_change, 2),
        "top10_holder_pct": round(top10_pct, 1),
        "holder_count": len(holders),
    }


# ---------------------------------------------------------------------------
# NEW: P1 — Smart Money Discovery Scan (proactive signal generation)
# ---------------------------------------------------------------------------
async def get_smart_money_discovery(
    session: aiohttp.ClientSession,
    redis_conn: aioredis.Redis | None = None,
) -> list[dict]:
    """
    Scan what smart money is accumulating on Solana right now.
    Filters: exclude stablecoins and native tokens, Solana only.
    Returns tokens with positive 24h change in smart money holdings.

    Budget: 6 calls/day (every 4 hours)
    """
    result = await nansen_post(session, "/smart-money/token-balances", {
        "chains": ["solana"],
        "includeStablecoin": False,
        "includeNativeTokens": False,
    }, redis_conn)

    if not result:
        return []

    data = result.get("data", result.get("result", []))
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list):
        return []

    # Filter to tokens with positive 24h change (accumulation)
    accumulating = []
    for token in data:
        change_24h = float(token.get("change24h", token.get("balance_change_24h", 0)) or 0)
        if change_24h > 0:
            accumulating.append({
                "mint": token.get("tokenAddress", token.get("token_address", "")),
                "symbol": token.get("symbol", token.get("tokenSymbol", "")),
                "balance_usd": float(token.get("balanceUsd", token.get("balance_usd", 0)) or 0),
                "change_24h": change_24h,
                "chain": "solana",
                "source": "nansen_discovery",
            })

    logger.info("Nansen discovery: %d tokens with smart money accumulation", len(accumulating))
    return accumulating


# ---------------------------------------------------------------------------
# NEW: P2 — Nansen Score Top Tokens (governance weekly)
# ---------------------------------------------------------------------------
async def get_nansen_top_tokens(
    session: aiohttp.ClientSession,
    market_cap_group: str | None = None,
    redis_conn: aioredis.Redis | None = None,
) -> list[dict]:
    """
    Get pre-scored buy recommendations (Performance Score >= 15).
    Backtested alpha indicators: price momentum, chain fees, protocol fees.

    Budget: 2-4 calls/week (lowcap + midcap scans for governance)
    """
    body: dict = {}
    if market_cap_group:
        body["marketCapGroup"] = market_cap_group

    result = await nansen_post(session, "/nansen-scores/top-tokens", body, redis_conn)

    if not result:
        return []

    data = result.get("data", result.get("result", []))
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list):
        return []
    return data


# ---------------------------------------------------------------------------
# NEW: P2 — Whale Wallet Portfolio Check (governance weekly rescoring)
# ---------------------------------------------------------------------------
async def get_whale_portfolio(
    session: aiohttp.ClientSession,
    wallet_address: str,
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Get full portfolio overview for a whale wallet.
    Shows all token holdings, DeFi positions, conviction levels.

    Cached in Redis for 6 hours (aligned with wallet_pnl cache).
    Budget: ~50 calls/week (top 50 whale wallets)
    """
    cache_key = f"nansen:portfolio:{wallet_address}"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await nansen_post(session, "/address/portfolio", {
        "walletAddress": wallet_address,
        "chain": "solana",
        "mode": "wallet_balances",
    }, redis_conn)

    if result and redis_conn:
        await redis_conn.set(cache_key, json.dumps(result), ex=21600)  # 6-hour TTL

    return result


# ---------------------------------------------------------------------------
# NEW: P2 — Granular Token Flows (Analyst pre-entry deep dive)
# ---------------------------------------------------------------------------
async def get_token_flows_granular(
    session: aiohttp.ClientSession,
    mint: str,
    hours_back: int = 24,
    segment: str = "smart_money",
    redis_conn: aioredis.Redis | None = None,
) -> dict | None:
    """
    Get hourly granular flows for a specific segment over a date range.
    Used by Analyst personality before entry — checks if smart money
    has been steadily accumulating over 12-24h.

    Budget: ~15 calls/day (only Analyst candidates after other filters pass)
    """
    cache_key = f"nansen:granflows:{mint}:{segment}:{hours_back}h"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = await nansen_post(session, "/tgm/token-flows", {
        "chain": "solana",
        "tokenAddress": mint,
        "holder_segment": segment,
        "dateRange": {"from": from_date, "to": to_date},
    }, redis_conn)

    if result and redis_conn:
        await redis_conn.set(cache_key, json.dumps(result), ex=900)  # 15-min TTL

    return result


def parse_granular_flows(raw: dict | None) -> dict:
    """
    Parse hourly flow data to detect accumulation/distribution patterns.
    Returns:
      - nansen_accumulation_hours: count of hours with net inflow (out of last 24)
      - nansen_accumulation_trend: 1 if >60% inflow hours, -1 if >60% outflow, 0 otherwise
    """
    defaults = {
        "nansen_accumulation_hours": 0,
        "nansen_accumulation_trend": 0,
    }
    if not raw:
        return defaults

    data = raw.get("data", raw.get("result", []))
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list) or not data:
        return defaults

    inflow_hours = 0
    total_hours = len(data)
    for row in data:
        inflows = float(row.get("inflows", row.get("longs", 0)) or 0)
        outflows = abs(float(row.get("outflows", row.get("shorts", 0)) or 0))
        if inflows > outflows:
            inflow_hours += 1

    trend = 0
    if total_hours > 0:
        ratio = inflow_hours / total_hours
        if ratio > 0.6:
            trend = 1
        elif ratio < 0.4:
            trend = -1

    return {
        "nansen_accumulation_hours": inflow_hours,
        "nansen_accumulation_trend": trend,
    }


# ---------------------------------------------------------------------------
# NEW: P3 — Token PnL Leaderboard (governance whale discovery)
# ---------------------------------------------------------------------------
async def get_token_pnl_leaderboard(
    session: aiohttp.ClientSession,
    mint: str,
    days: int = 7,
    redis_conn: aioredis.Redis | None = None,
) -> list[dict]:
    """
    Get top traders by PnL for a specific token.
    Used to discover profitable wallets for whale_wallets.json.

    Budget: ~5 calls/week (top 5 performing tokens)
    """
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = await nansen_post(session, "/tgm/token-pnl-leaderboard", {
        "chain": "solana",
        "tokenAddress": mint,
        "dateRange": {"from": from_date, "to": to_date},
        "order_by": "pnlUsdTotal",
        "order_by_direction": "desc",
    }, redis_conn)

    if not result:
        return []

    data = result.get("data", result.get("result", []))
    if isinstance(data, dict) and "rows" in data:
        data = data["rows"]
    if not isinstance(data, list):
        return []
    return data


# ---------------------------------------------------------------------------
# NEW: Smart Money DEX Sells (exit monitoring)
# ---------------------------------------------------------------------------
async def get_smart_money_dex_sells(
    session: aiohttp.ClientSession,
    mint: str,
    redis_conn: aioredis.Redis | None = None,
) -> list[dict]:
    """
    Get recent DEX sell trades by smart money on a specific token.
    Used for exit monitoring — if funds/top traders start selling, trigger exit.

    Budget: ~30 calls/day (one per open position check cycle)
    """
    cache_key = f"nansen:sm_sells:{mint}"
    if redis_conn:
        cached = await redis_conn.get(cache_key)
        if cached:
            return json.loads(cached)

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = await nansen_post(session, "/tgm/token-dex-trades", {
        "chain": "solana",
        "tokenAddress": mint,
        "action": "sell",
        "dateRange": {"from": from_date, "to": to_date},
        "includeSmartMoneyLabels": ["Fund", "All Time Smart Trader", "90D Smart Trader"],
        "order_by": "valueUsd",
        "order_by_direction": "desc",
    }, redis_conn)

    sells = []
    if result:
        data = result.get("data", result.get("result", []))
        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]
        if isinstance(data, list):
            sells = data

        if redis_conn:
            await redis_conn.set(cache_key, json.dumps(sells), ex=120)  # 2-min TTL (time-sensitive)

    return sells
