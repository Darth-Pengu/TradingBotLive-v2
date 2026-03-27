"""
ZMN Bot Nansen API Client
===========================
Shared client for all Nansen API calls with:
- Redis-based rate limiter (max 1 call per 2 seconds across all services)
- Response time logging for credit monitoring
- Redis caching for wallet PnL data (6-hour TTL)
- try/except on all calls — bot continues if Nansen is down
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
        start = time.time()

        async with session.post(url, json=body, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed_ms = (time.time() - start) * 1000
            logger.info("Nansen %s — %d (%.0fms)", endpoint, resp.status, elapsed_ms)

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


# ---------------------------------------------------------------------------
# High-level helpers
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
