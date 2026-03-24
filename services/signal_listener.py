"""
ToxiBot Signal Listener Service
================================
Connects to three signal sources and pushes raw signals to Redis:
  1. PumpPortal WebSocket (primary) — subscribeNewToken, subscribeAccountTrade,
     subscribeMigration, subscribeTokenTrade
  2. GeckoTerminal polling (backup) — /networks/solana/new_pools every 60s
  3. DexPaprika SSE stream (tertiary) — /v1/solana/events/stream

All signals → Redis LPUSH "signals:raw" as JSON.
TEST_MODE=true: log signals, do NOT push to Redis.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
import redis.asyncio as aioredis
import websockets
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("signal_listener")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"
GECKO_NEW_POOLS_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
DEXPAPRIKA_SSE_URL = "https://api.dexpaprika.com/v1/solana/events/stream"

# Reconnect config: exponential backoff 1s base, x2 each attempt, 60s max
BACKOFF_BASE = 1.0
BACKOFF_FACTOR = 2.0
BACKOFF_MAX = 60.0

# --- Real-time buy/sell ratio tracker (replaces BitQuery volume data) ---
# Tracks buys and sells per mint from PumpPortal subscribeTokenTrade stream
# Keyed by mint → {buys: int, sells: int, last_update: float}
_trade_tracker: dict[str, dict] = {}
TRADE_TRACKER_WINDOW = 300  # 5-minute rolling window
TRADE_TRACKER_MAX = 2000    # Max tokens to track


def _update_trade_tracker(mint: str, tx_type: str):
    """Track buy/sell counts per token from the PumpPortal trade stream."""
    now = time.time()
    if mint not in _trade_tracker:
        if len(_trade_tracker) >= TRADE_TRACKER_MAX:
            # Evict oldest entries
            oldest = sorted(_trade_tracker, key=lambda m: _trade_tracker[m]["last_update"])
            for old_mint in oldest[:TRADE_TRACKER_MAX // 2]:
                del _trade_tracker[old_mint]
        _trade_tracker[mint] = {"buys": 0, "sells": 0, "last_update": now, "unique_buyers": set()}

    entry = _trade_tracker[mint]
    entry["last_update"] = now
    if tx_type == "buy":
        entry["buys"] += 1
    elif tx_type == "sell":
        entry["sells"] += 1


def _get_buy_sell_ratio(mint: str) -> float:
    """Get the buy/sell ratio for a token. Returns 1.0 if no data."""
    entry = _trade_tracker.get(mint)
    if not entry or entry["sells"] == 0:
        return entry["buys"] if entry and entry["buys"] > 0 else 1.0
    return round(entry["buys"] / entry["sells"], 2)


def _build_signal(mint: str, source: str, signal_type: str, raw_data: dict, age_seconds: float = 0.0) -> dict:
    # Enrich with real-time buy/sell ratio from trade tracker
    if mint in _trade_tracker:
        raw_data["buy_sell_ratio_5min"] = _get_buy_sell_ratio(mint)
        raw_data["buys_5min"] = _trade_tracker[mint]["buys"]
        raw_data["sells_5min"] = _trade_tracker[mint]["sells"]

    return {
        "mint": mint,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "age_seconds": round(age_seconds, 2),
        "raw_data": raw_data,
        "signal_type": signal_type,
    }


async def _push_signal(redis_conn: aioredis.Redis | None, signal: dict):
    logger.info("Signal [%s/%s]: %s", signal["source"], signal["signal_type"], signal["mint"])
    if TEST_MODE:
        logger.debug("TEST_MODE — not pushing to Redis: %s", json.dumps(signal)[:200])
        return
    if redis_conn:
        await redis_conn.lpush("signals:raw", json.dumps(signal))


# ---------------------------------------------------------------------------
# 1. PumpPortal WebSocket
# ---------------------------------------------------------------------------
async def _load_whale_wallets() -> list[str]:
    try:
        with open("data/whale_wallets.json", "r") as f:
            wallets = json.load(f)
        return [w["address"] for w in wallets if isinstance(w, dict) and "address" in w]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        logger.warning("No valid whale_wallets.json found — skipping subscribeAccountTrade")
        return []


async def pumpportal_listener(redis_conn: aioredis.Redis | None):
    backoff = BACKOFF_BASE
    while True:
        try:
            logger.info("Connecting to PumpPortal WebSocket...")
            async with websockets.connect(PUMPPORTAL_WS_URL, ping_interval=20, ping_timeout=10) as ws:
                backoff = BACKOFF_BASE  # reset on successful connect

                # Subscribe to new tokens
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                logger.info("Subscribed: subscribeNewToken")

                # Subscribe to migrations (graduation events)
                await ws.send(json.dumps({"method": "subscribeMigration"}))
                logger.info("Subscribed: subscribeMigration")

                # Subscribe to whale wallet trades
                whale_wallets = await _load_whale_wallets()
                if whale_wallets:
                    await ws.send(json.dumps({
                        "method": "subscribeAccountTrade",
                        "keys": whale_wallets,
                    }))
                    logger.info("Subscribed: subscribeAccountTrade for %d wallets", len(whale_wallets))

                # Subscribe to token trades (for real-time price/volume on held tokens)
                await ws.send(json.dumps({"method": "subscribeTokenTrade"}))
                logger.info("Subscribed: subscribeTokenTrade")

                async for raw_msg in ws:
                    try:
                        data = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue

                    # Determine signal type from message content
                    if "mint" not in data and "token" not in data:
                        continue

                    mint = data.get("mint") or data.get("token", "")
                    if not mint:
                        continue

                    # Track buy/sell for real-time ratio calculation
                    tx_type = data.get("txType", "")
                    if tx_type in ("buy", "sell"):
                        _update_trade_tracker(mint, tx_type)

                    # Classify signal type
                    if tx_type == "create" or "bondingCurveKey" in data:
                        sig_type = "new_token"
                    elif tx_type in ("buy", "sell"):
                        sig_type = "account_trade"
                    elif "pool" in data or tx_type == "migration":
                        sig_type = "migration"
                    else:
                        sig_type = "token_trade"

                    # Calculate age from creation timestamp if available
                    created_ts = data.get("timestamp")
                    age = 0.0
                    if created_ts:
                        try:
                            age = time.time() - (created_ts / 1000 if created_ts > 1e12 else created_ts)
                        except (TypeError, ValueError):
                            pass

                    signal = _build_signal(mint, "pumpportal", sig_type, data, age)
                    await _push_signal(redis_conn, signal)

        except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
            logger.warning("PumpPortal WS disconnected: %s — reconnecting in %.1fs", e, backoff)
        except Exception as e:
            logger.error("PumpPortal unexpected error: %s — reconnecting in %.1fs", e, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)


# ---------------------------------------------------------------------------
# 2. GeckoTerminal Polling (backup — every 60s)
# ---------------------------------------------------------------------------
GECKO_SEEN: set[str] = set()
GECKO_SEEN_MAX = 5000


async def gecko_poller(redis_conn: aioredis.Redis | None):
    backoff = BACKOFF_BASE
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        async with session.get(
                            GECKO_NEW_POOLS_URL,
                            headers={"Accept": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as resp:
                            if resp.status == 200:
                                body = await resp.json()
                                pools = body.get("data", [])
                                for pool in pools:
                                    attrs = pool.get("attributes", {})
                                    addr = attrs.get("address", "")
                                    # Extract token mint from pool relationships
                                    rels = pool.get("relationships", {})
                                    base_token = rels.get("base_token", {}).get("data", {}).get("id", "")
                                    # GeckoTerminal IDs are like "solana_<address>"
                                    mint = base_token.replace("solana_", "") if base_token.startswith("solana_") else addr

                                    if not mint or mint in GECKO_SEEN:
                                        continue
                                    GECKO_SEEN.add(mint)

                                    # Trim seen set to prevent unbounded growth
                                    if len(GECKO_SEEN) > GECKO_SEEN_MAX:
                                        to_remove = list(GECKO_SEEN)[:GECKO_SEEN_MAX // 2]
                                        for r in to_remove:
                                            GECKO_SEEN.discard(r)

                                    created_at = attrs.get("pool_created_at", "")
                                    age = 0.0
                                    if created_at:
                                        try:
                                            ct = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                                            age = (datetime.now(timezone.utc) - ct).total_seconds()
                                        except (ValueError, TypeError):
                                            pass

                                    signal = _build_signal(mint, "geckoterminal", "new_pool", {
                                        "pool_address": addr,
                                        "name": attrs.get("name", ""),
                                        "base_token_price_usd": attrs.get("base_token_price_usd"),
                                        "reserve_in_usd": attrs.get("reserve_in_usd"),
                                    }, age)
                                    await _push_signal(redis_conn, signal)

                                backoff = BACKOFF_BASE
                            elif resp.status == 429:
                                logger.warning("GeckoTerminal rate limited — backing off")
                                await asyncio.sleep(backoff)
                                backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
                            else:
                                logger.warning("GeckoTerminal HTTP %d", resp.status)
                    except aiohttp.ClientError as e:
                        logger.warning("GeckoTerminal request error: %s", e)

                    await asyncio.sleep(60)

        except Exception as e:
            logger.error("GeckoTerminal poller error: %s — restarting in %.1fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)


# ---------------------------------------------------------------------------
# 3. DexPaprika SSE Stream (tertiary)
# ---------------------------------------------------------------------------
async def dexpaprika_listener(redis_conn: aioredis.Redis | None):
    backoff = BACKOFF_BASE
    while True:
        try:
            logger.info("Connecting to DexPaprika SSE stream...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    DEXPAPRIKA_SSE_URL,
                    headers={"Accept": "text/event-stream"},
                    timeout=aiohttp.ClientTimeout(total=0, sock_read=300),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("DexPaprika SSE HTTP %d", resp.status)
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
                        continue

                    backoff = BACKOFF_BASE
                    buffer = ""
                    async for chunk in resp.content:
                        buffer += chunk.decode("utf-8", errors="replace")
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            # Parse SSE format
                            data_line = ""
                            for line in event_str.split("\n"):
                                if line.startswith("data:"):
                                    data_line = line[5:].strip()

                            if not data_line:
                                continue

                            try:
                                data = json.loads(data_line)
                            except json.JSONDecodeError:
                                continue

                            mint = data.get("token_address") or data.get("mint") or data.get("address", "")
                            if not mint:
                                continue

                            signal = _build_signal(mint, "dexpaprika", "sse_event", data, 0.0)
                            await _push_signal(redis_conn, signal)

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            logger.warning("DexPaprika SSE error: %s — reconnecting in %.1fs", e, backoff)
        except Exception as e:
            logger.error("DexPaprika unexpected error: %s — reconnecting in %.1fs", e, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    logger.info("Signal Listener starting (TEST_MODE=%s)", TEST_MODE)

    redis_conn = None
    if not TEST_MODE:
        try:
            redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
            await redis_conn.ping()
            logger.info("Redis connected: %s", REDIS_URL)
        except Exception as e:
            logger.error("Redis connection failed: %s — signals will be logged only", e)
            redis_conn = None

    await asyncio.gather(
        pumpportal_listener(redis_conn),
        gecko_poller(redis_conn),
        dexpaprika_listener(redis_conn),
    )


if __name__ == "__main__":
    asyncio.run(main())
