"""
ZMN Bot Signal Listener Service
================================
Connects to signal sources and pushes raw signals to Redis:
  1. PumpPortal WebSocket (primary) — subscribeNewToken, subscribeAccountTrade,
     subscribeMigration, subscribeTokenTrade
  2. GeckoTerminal polling (backup) — /networks/solana/new_pools every 60s
  3. DexPaprika SSE stream (tertiary) — streaming.dexpaprika.com/stream
  4. Discord Nansen alerts — polls channel every 15s for whale/smart money signals
  5. Nansen Token Screener — polls every 10 minutes

All signals → Redis LPUSH "signals:raw" as JSON.
Signals always flow to Redis (even in TEST_MODE) for paper trading.
"""

import asyncio
import json
import logging
import os
import re
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
HELIUS_PARSE_HISTORY_URL = os.getenv("HELIUS_PARSE_HISTORY_URL", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
RAILWAY_SERVICE_URL = os.getenv("RAILWAY_STATIC_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_NANSEN_CHANNEL_ID = os.getenv("DISCORD_NANSEN_CHANNEL_ID", "")
DISCORD_OWNER_ID = os.getenv("DISCORD_OWNER_ID", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_POLL_INTERVAL = 15  # seconds

SOLANA_ADDRESS_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")

DISCORD_ALERT_MAP = {
    # Nansen webhook alerts forwarded to Discord channel
    "ToxiBot Whale Entry": {
        "signal_type": "whale_entry",
        "route": "whale_tracker",
        "confidence_boost": 30,
    },
    "ToxiBot Smart Money Inflow": {
        "signal_type": "smart_money_inflow",
        "route": "analyst",
        "confidence_boost": 25,
    },
    "ToxiBot Smart Money Concentration": {
        "signal_type": "sm_concentration",
        "route": "analyst",
        "confidence_boost": 35,
    },
    "ToxiBot Smart Money Sell": {
        "signal_type": "smart_money_exit",
        "publish_channel": "alerts:exit_check",
        "urgency": "high",
    },
    "ToxiBot Fund Activity": {
        "signal_type": "fund_activity",
        "route": "whale_tracker",
        "confidence_boost": 30,
    },
    "ToxiBot Netflow Spike": {
        "signal_type": "netflow_spike",
        "redis_boost_key": "market:netflow_boost",
        "boost_ttl": 7200,
        "position_limit_multiplier": 1.2,
    },
    # Generic Nansen alert patterns (if webhook format differs)
    "whale entry": {"signal_type": "whale_entry", "route": "whale_tracker", "confidence_boost": 25},
    "smart money": {"signal_type": "smart_money_inflow", "route": "analyst", "confidence_boost": 25},
    "fund activity": {"signal_type": "fund_activity", "route": "whale_tracker", "confidence_boost": 30},
    "smart money exit": {"signal_type": "smart_money_exit", "publish_channel": "alerts:exit_check", "urgency": "high"},
}

PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"
GECKO_NEW_POOLS_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
GECKO_TRENDING_URL = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?include=base_token,quote_token,dex"
DEXPAPRIKA_SSE_URL = "https://streaming.dexpaprika.com/stream"

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
    if redis_conn:
        await redis_conn.lpush("signals:raw", json.dumps(signal))
    else:
        logger.debug("No Redis — signal not queued: %s", json.dumps(signal)[:200])


# ---------------------------------------------------------------------------
# 1. PumpPortal WebSocket
# ---------------------------------------------------------------------------
async def _load_whale_wallets() -> list[str]:
    """Load whale tracker wallet addresses from PostgreSQL (source of truth).
    Falls back to whale_wallets.json only if DB is unavailable."""
    try:
        from services.nansen_wallet_fetcher import get_active_wallets
        wallets = await get_active_wallets(personality_route="whale_tracker")
        if wallets:
            addrs = [w["address"] for w in wallets]
            logger.info("Loaded %d whale wallets from PostgreSQL", len(addrs))
            return addrs
    except Exception as e:
        logger.warning("PostgreSQL wallet load failed, trying JSON fallback: %s", e)

    # Fallback to JSON file (cold start before first DB population)
    try:
        with open("data/whale_wallets.json", "r") as f:
            wallets = json.load(f)
        addrs = [w["address"] for w in wallets if isinstance(w, dict) and "address" in w]
        logger.warning("Using JSON fallback — %d whale wallets: %s",
                        len(addrs), [a[:8] for a in addrs[:5]])
        return addrs
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Auto-seed with known active whales if both DB and JSON are empty
    logger.warning("whale_wallets.json not found — seeding from fallback list")
    from pathlib import Path
    whale_path = Path("data/whale_wallets.json")
    whale_path.parent.mkdir(parents=True, exist_ok=True)
    fallback = [
        {"address": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "GUfCR9mK6azb9vcpsxgXyj7XRPAaGa35swRPRRKenTFG", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "CuieVDEDtLo7FypA9SbLM9saXFdb1dsshEkyErMqkRQq", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "ArAQfbzsdwTAeDovfS7M3KFnbQRoBwFHhFzDt4PiABMa", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
        {"address": "Hax9LTgsQkze8VnNSCKdRzMSCBQBYhGPVxFHJQjfMGQe", "score": 75, "label": "Fallback Whale", "source": "fallback", "active": True},
    ]
    whale_path.write_text(json.dumps(fallback, indent=2))
    logger.info("whale_wallets.json seeded with %d fallback wallets", len(fallback))

    # Also insert fallback wallets into watched_wallets DB table
    try:
        from services.db import get_pool
        pool = await get_pool()
        for w in fallback:
            await pool.execute(
                """INSERT INTO watched_wallets
                   (address, label, personality_route, source, qualification_score, is_active)
                   VALUES ($1, $2, 'whale_tracker', 'fallback', 75, TRUE)
                   ON CONFLICT (address) DO UPDATE SET is_active = TRUE""",
                w["address"], w.get("label", "Fallback Whale"),
            )
        logger.info("Inserted %d fallback wallets into watched_wallets DB", len(fallback))
    except Exception as e:
        logger.warning("Failed to insert fallback wallets into DB: %s", e)

    return [w["address"] for w in fallback]


async def _register_helius_webhook(redis_conn: aioredis.Redis | None):
    """Register a Helius enhanced webhook for all active whale wallet addresses.
    Replaces polling with real-time push notifications for whale swap activity.
    Stores webhook ID in Redis key 'helius:webhook_id' for later updates.
    """
    if not HELIUS_API_KEY or not RAILWAY_SERVICE_URL:
        logger.info("HELIUS_API_KEY or RAILWAY_SERVICE_URL not set — webhook registration skipped")
        return

    whale_wallets = await _load_whale_wallets()
    if not whale_wallets:
        logger.info("No whale wallets loaded — webhook registration skipped")
        return

    webhook_url = f"https://{RAILWAY_SERVICE_URL}/helius-webhook" if not RAILWAY_SERVICE_URL.startswith("http") else f"{RAILWAY_SERVICE_URL}/helius-webhook"
    api_url = f"https://api-mainnet.helius-rpc.com/v0/webhooks?api-key={HELIUS_API_KEY}"

    # Check if we already have a webhook registered
    existing_webhook_id = None
    if redis_conn:
        try:
            existing_webhook_id = await redis_conn.get("helius:webhook_id")
        except Exception:
            pass

    try:
        async with aiohttp.ClientSession() as session:
            # If we have an existing webhook, update it instead of creating a new one
            if existing_webhook_id:
                update_url = f"https://api-mainnet.helius-rpc.com/v0/webhooks/{existing_webhook_id}?api-key={HELIUS_API_KEY}"
                payload = {
                    "webhookURL": webhook_url,
                    "transactionTypes": HELIUS_WEBHOOK_TX_TYPES,
                    "accountAddresses": whale_wallets[:100],  # Helius limit
                    "webhookType": "enhanced",
                }
                async with session.put(update_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status in (200, 201):
                        logger.info("Helius webhook updated (HTTP %d): %s (%d wallets, %d tx types)",
                                    resp.status, existing_webhook_id, len(whale_wallets[:100]), len(HELIUS_WEBHOOK_TX_TYPES))
                        return
                    else:
                        logger.warning("Helius webhook update failed (HTTP %d) — creating new one", resp.status)

            # Create new webhook
            payload = {
                "webhookURL": webhook_url,
                "transactionTypes": HELIUS_WEBHOOK_TX_TYPES,
                "accountAddresses": whale_wallets[:100],
                "webhookType": "enhanced",
            }
            async with session.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    webhook_id = data.get("webhookID", "")
                    logger.info("Helius webhook created (HTTP %d): %s → %s (%d wallets)",
                                resp.status, webhook_id, webhook_url, len(whale_wallets[:100]))
                    if redis_conn and webhook_id:
                        await redis_conn.set("helius:webhook_id", webhook_id)
                else:
                    body = await resp.text()
                    logger.warning("Helius webhook creation failed (HTTP %d): %s", resp.status, body[:200])

    except Exception as e:
        logger.warning("Helius webhook registration error: %s", e)


# Track per-token subscriptions for exit pricing
_subscribed_tokens: set[str] = set()
_pumpportal_ws_ref: list = [None]  # Module-level shared WS reference


async def _token_subscribe_listener(redis_conn: aioredis.Redis | None, ws_ref: list = _pumpportal_ws_ref):
    """Listen on Redis pubsub for token:subscribe messages from bot_core.
    Dynamically subscribe/unsubscribe PumpPortal token trade streams."""
    if not redis_conn:
        return

    # On startup, load any existing token subscriptions from Redis
    # (handles case where bot_core published before we started listening)
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_conn.scan(cursor, match="token:subscribed:*", count=100)
            for key in keys:
                mint = key.split(":")[-1] if isinstance(key, str) else key.decode().split(":")[-1]
                _subscribed_tokens.add(mint)
            if cursor == 0:
                break
        if _subscribed_tokens:
            logger.info("Loaded %d existing token subscriptions from Redis", len(_subscribed_tokens))
    except Exception as e:
        logger.debug("Failed to load existing subscriptions: %s", e)

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("token:subscribe")
    logger.info("Token subscribe listener started — waiting for bot_core messages")
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            mint = data.get("mint", "")
            action = data.get("action", "")
            if not mint:
                continue

            ws = ws_ref[0] if ws_ref else None
            if not ws:
                logger.debug("TOKEN_SUB: no active WS connection for %s %s", action, mint[:12])
                continue

            if action == "subscribe" and mint not in _subscribed_tokens:
                await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                _subscribed_tokens.add(mint)
                # Cache price key with placeholder so exit checker knows we're tracking
                if redis_conn:
                    await redis_conn.set(f"token:subscribed:{mint}", "1", ex=7200)
                logger.info("PRICE_TRACK: subscribed to trades for %s", mint[:12])
            elif action == "unsubscribe" and mint in _subscribed_tokens:
                await ws.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [mint]}))
                _subscribed_tokens.discard(mint)
                if redis_conn:
                    await redis_conn.delete(f"token:subscribed:{mint}")
                logger.info("PRICE_TRACK: unsubscribed from %s", mint[:12])
        except Exception as e:
            logger.debug("Token subscribe listener error: %s", e)


async def pumpportal_listener(redis_conn: aioredis.Redis | None):
    backoff = BACKOFF_BASE
    while True:
        try:
            logger.info("Connecting to PumpPortal WebSocket...")
            async with websockets.connect(PUMPPORTAL_WS_URL, ping_interval=20, ping_timeout=10) as ws:
                backoff = BACKOFF_BASE  # reset on successful connect
                _pumpportal_ws_ref[0] = ws  # Share WS ref with token subscribe listener

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

                # Re-subscribe to any previously tracked tokens (after reconnect)
                if _subscribed_tokens:
                    await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(_subscribed_tokens)}))
                    logger.info("Re-subscribed: subscribeTokenTrade for %d held tokens", len(_subscribed_tokens))

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

                    # Track buy/sell for real-time ratio calculation + cache price + publish stats
                    tx_type = data.get("txType", "")
                    if tx_type in ("buy", "sell"):
                        _update_trade_tracker(mint, tx_type)
                        # Track unique buyers
                        buyer = data.get("traderPublicKey", "")
                        if tx_type == "buy" and buyer and mint in _trade_tracker:
                            _trade_tracker[mint].setdefault("unique_buyers", set()).add(buyer)

                        if redis_conn:
                            try:
                                # Cache latest trade price for exit checker
                                sol_amount = float(data.get("solAmount", data.get("sol_amount", 0)) or 0)
                                token_amount = float(data.get("tokenAmount", data.get("token_amount", 0)) or 0)
                                if sol_amount > 0 and token_amount > 0:
                                    trade_price = sol_amount / token_amount
                                    await redis_conn.set(f"token:price:{mint}", str(trade_price), ex=300)
                                    # Also set token:latest_price for exit checker + dashboard
                                    await redis_conn.set(f"token:latest_price:{mint}", str(trade_price), ex=300)

                                # Store bonding curve reserves for exit pricing fallback
                                v_sol_bc = data.get("vSolInBondingCurve") or data.get("vsolInBondingCurve")
                                v_tokens_bc = data.get("vTokensInBondingCurve") or data.get("vtokensInBondingCurve")
                                if v_sol_bc and v_tokens_bc and mint in _subscribed_tokens:
                                    await redis_conn.hset(f"token:reserves:{mint}", mapping={
                                        "vSol": str(v_sol_bc),
                                        "vTokens": str(v_tokens_bc),
                                    })
                                    await redis_conn.expire(f"token:reserves:{mint}", 600)

                                # Publish trade stats to Redis for aggregator feature extraction
                                entry = _trade_tracker.get(mint, {})
                                buys = entry.get("buys", 0)
                                sells = entry.get("sells", 0)
                                unique = len(entry.get("unique_buyers", set()))
                                bsr = round(buys / sells, 2) if sells > 0 else float(buys) if buys > 0 else 0
                                await redis_conn.hset(f"token:stats:{mint}", mapping={
                                    "buys": buys, "sells": sells, "bsr": bsr,
                                    "unique_buyers": unique, "updated": str(time.time()),
                                })
                                await redis_conn.expire(f"token:stats:{mint}", 600)
                            except Exception:
                                pass

                    # Classify signal type
                    if tx_type == "create" or "bondingCurveKey" in data:
                        sig_type = "new_token"
                    elif tx_type in ("buy", "sell"):
                        sig_type = "account_trade"
                    elif "pool" in data or tx_type == "migration":
                        sig_type = "migration"
                    else:
                        sig_type = "token_trade"

                    # Detect platform (Pump.fun vs Bonk.fun/LaunchLab)
                    platform = "pump.fun"
                    data_str = json.dumps(data) if isinstance(data, dict) else str(data)
                    if "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj" in data_str:
                        platform = "launchlab"
                    elif data.get("pool") == "bonk" or "bonk" in data_str.lower().split("pool")[0] if "pool" in data_str.lower() else False:
                        platform = "bonk"
                    elif data.get("pool") == "launchlab":
                        platform = "launchlab"

                    # Calculate age from creation timestamp if available
                    created_ts = data.get("timestamp")
                    age = 0.0
                    if created_ts:
                        try:
                            age = time.time() - (created_ts / 1000 if created_ts > 1e12 else created_ts)
                        except (TypeError, ValueError):
                            pass

                    signal = _build_signal(mint, "pumpportal", sig_type, data, age)
                    signal["platform"] = platform

                    # Extract social metadata from PumpPortal create events
                    if sig_type == "new_token":
                        socials = data.get("social_links", {})
                        signal["has_twitter"] = bool(data.get("twitter") or socials.get("twitter"))
                        signal["has_telegram"] = bool(data.get("telegram") or socials.get("telegram"))
                        signal["has_website"] = bool(data.get("website") or socials.get("website") or data.get("uri"))
                        signal["has_social"] = signal["has_twitter"] or signal["has_telegram"] or signal["has_website"]
                        signal["twitter_url"] = data.get("twitter") or socials.get("twitter", "")
                        if platform != "pump.fun":
                            logger.info("NEW TOKEN [%s]: %s %s", platform, data.get("name", "?"), mint[:12])

                    # Push graduation events to dedicated queue for sniper
                    if sig_type == "migration":
                        grad_data = {
                            "type": "graduation",
                            "mint": mint,
                            "timestamp": time.time(),
                            "pool_type": data.get("pool", "pumpswap"),
                            "platform": platform,
                            "source": "pumpportal_migration",
                        }
                        if redis_conn:
                            await redis_conn.lpush("signals:graduated", json.dumps(grad_data))
                        logger.info("GRADUATION: %s -> %s [%s]", mint[:12], data.get("pool", "?"), platform)

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
# 2b. GeckoTerminal Trending Pools (analyst signal source)
# Polls trending pools every 60s — tokens with confirmed volume + momentum.
# ---------------------------------------------------------------------------
async def gecko_trending_poller(redis_conn: aioredis.Redis | None):
    """Poll GeckoTerminal trending pools for analyst personality signals."""
    backoff = BACKOFF_BASE
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        async with session.get(
                            GECKO_TRENDING_URL,
                            headers={"Accept": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            if resp.status == 200:
                                body = await resp.json()
                                pools = body.get("data", [])
                                pushed = 0
                                for pool in pools:
                                    attrs = pool.get("attributes", {})
                                    rels = pool.get("relationships", {})
                                    base_token = rels.get("base_token", {}).get("data", {}).get("id", "")
                                    mint = base_token.replace("solana_", "") if base_token.startswith("solana_") else ""
                                    pool_addr = attrs.get("address", "")

                                    if not mint or mint in GECKO_SEEN:
                                        continue
                                    # Don't add to GECKO_SEEN — trending tokens can re-appear and should re-signal

                                    vol_1h = float(attrs.get("volume_usd", {}).get("h1", 0) or 0)
                                    vol_24h = float(attrs.get("volume_usd", {}).get("h24", 0) or 0)
                                    txns = attrs.get("transactions", {}).get("h1", {})
                                    buys_1h = int(txns.get("buys", 0) or 0)
                                    sells_1h = int(txns.get("sells", 0) or 0)
                                    price_change_1h = float(attrs.get("price_change_percentage", {}).get("h1", 0) or 0)
                                    mcap = float(attrs.get("market_cap_usd") or attrs.get("fdv_usd") or 0)
                                    liq = float(attrs.get("reserve_in_usd", 0) or 0)

                                    if vol_1h < 10000:
                                        continue

                                    buy_sell_ratio = buys_1h / sells_1h if sells_1h > 0 else float(buys_1h)

                                    signal = _build_signal(mint, "geckoterminal_trending", "trending", {
                                        "pool_address": pool_addr,
                                        "volume_1h_usd": vol_1h,
                                        "volume_24h_usd": vol_24h,
                                        "buy_count_1h": buys_1h,
                                        "sell_count_1h": sells_1h,
                                        "price_change_1h_pct": price_change_1h,
                                        "market_cap_usd": mcap,
                                        "liquidity_usd": liq,
                                        "buy_sell_ratio_5min": buy_sell_ratio,
                                        "name": attrs.get("name", ""),
                                        "base_token_price_usd": attrs.get("base_token_price_usd"),
                                    })
                                    await _push_signal(redis_conn, signal)
                                    pushed += 1

                                if pushed:
                                    logger.info("GeckoTerminal trending: pushed %d/%d pools", pushed, len(pools))
                                backoff = BACKOFF_BASE
                            elif resp.status == 429:
                                logger.warning("GeckoTerminal trending rate limited — backing off")
                                await asyncio.sleep(backoff)
                                backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)
                            else:
                                logger.warning("GeckoTerminal trending HTTP %d", resp.status)
                    except aiohttp.ClientError as e:
                        logger.warning("GeckoTerminal trending request error: %s", e)

                    await asyncio.sleep(60)

        except Exception as e:
            logger.error("GeckoTerminal trending poller error: %s — restarting in %.1fs", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)


# ---------------------------------------------------------------------------
# 3. DexPaprika SSE Stream (tertiary — price monitoring for existing tokens)
# Note: DexPaprika streams price updates, not new token creation events.
# Useful for monitoring price changes on tokens we're already watching.
# ---------------------------------------------------------------------------
async def dexpaprika_listener(redis_conn: aioredis.Redis | None):
    if os.getenv("DEXPAPRIKA_ENABLED", "false").lower() != "true":
        logger.info("DexPaprika disabled — skipping")
        return
    backoff = BACKOFF_BASE
    while True:
        try:
            logger.info("Connecting to DexPaprika SSE stream...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    DEXPAPRIKA_SSE_URL,
                    params={"method": "t_p", "chain": "solana"},
                    headers={"Accept": "text/event-stream"},
                    timeout=aiohttp.ClientTimeout(total=0, sock_read=300),
                ) as resp:
                    if resp.status == 404:
                        logger.warning(
                            "DexPaprika SSE 404 — endpoint may have moved. "
                            "Backing off 10 minutes. Check streaming.dexpaprika.com for updates."
                        )
                        await asyncio.sleep(600)
                        continue
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

                            # DexPaprika uses single-char fields: a=address, p=price, t=timestamp, c=chain
                            mint = data.get("a", "")
                            if not mint:
                                continue

                            signal = _build_signal(mint, "dexpaprika", "sse_event", {
                                "price_usd": data.get("p"),
                                "timestamp": data.get("t"),
                                "chain": data.get("c"),
                            }, 0.0)
                            await _push_signal(redis_conn, signal)

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            logger.warning("DexPaprika SSE error: %s — reconnecting in %.1fs", e, backoff)
        except Exception as e:
            logger.error("DexPaprika unexpected error: %s — reconnecting in %.1fs", e, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX)


# ---------------------------------------------------------------------------
# 4. Discord Nansen Alert Poller (polls every 15 seconds)
# ---------------------------------------------------------------------------

def _parse_discord_alert(content: str) -> tuple[str | None, dict | None]:
    """Match message content to a known Nansen alert type (case-insensitive).
    Returns (alert_name, config) or (None, None) if no match.
    """
    content_lower = content.lower()
    for alert_name, config in DISCORD_ALERT_MAP.items():
        if alert_name.lower() in content_lower:
            return alert_name, config
    return None, None


async def discord_nansen_poller(redis_conn: aioredis.Redis | None):
    """Poll a Discord channel for Nansen alert messages every 15 seconds."""
    if not DISCORD_BOT_TOKEN or not DISCORD_NANSEN_CHANNEL_ID:
        logger.info("DISCORD_BOT_TOKEN or DISCORD_NANSEN_CHANNEL_ID not set — Discord poller disabled")
        return

    url = f"https://discord.com/api/v10/channels/{DISCORD_NANSEN_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

    # Seed last_message_id from Redis if available
    last_message_id: str | None = None
    if redis_conn:
        try:
            last_message_id = await redis_conn.get("discord:last_message_id")
        except Exception:
            pass

    while True:
        try:
            params = {"limit": 10}
            if last_message_id:
                params["after"] = last_message_id

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 404:
                        logger.error("Discord channel not found — check DISCORD_NANSEN_CHANNEL_ID (got 404)")
                        await asyncio.sleep(300)  # Back off 5 minutes on 404
                        continue
                    if resp.status == 403:
                        logger.error("Discord bot lacks permission to read channel (got 403)")
                        await asyncio.sleep(300)
                        continue
                    if resp.status != 200:
                        logger.warning("Discord API HTTP %d", resp.status)
                        await asyncio.sleep(DISCORD_POLL_INTERVAL)
                        continue

                    messages = await resp.json()

            if not messages:
                await asyncio.sleep(DISCORD_POLL_INTERVAL)
                continue

            # Discord returns newest first — process oldest first
            messages.sort(key=lambda m: m["id"])

            for msg in messages:
                msg_id = msg["id"]
                content = msg.get("content", "")

                # Feature 7: Discord two-way commands from owner
                if (content.strip().lower().startswith("!zmn") and
                    DISCORD_OWNER_ID and msg.get("author", {}).get("id") == DISCORD_OWNER_ID):
                    try:
                        from services.governance import handle_discord_command
                        response = await handle_discord_command(content.strip())
                        if response and DISCORD_WEBHOOK_URL:
                            async with aiohttp.ClientSession() as cmd_session:
                                await cmd_session.post(DISCORD_WEBHOOK_URL,
                                    json={"content": response[:2000]},
                                    timeout=aiohttp.ClientTimeout(total=10))
                            logger.info("Discord command: %s -> %s", content.strip(), response[:100])
                    except Exception as e:
                        logger.warning("Discord command error: %s", e)
                    last_message_id = msg_id
                    continue

                alert_name, config = _parse_discord_alert(content)

                if not alert_name or not config:
                    last_message_id = msg_id
                    continue

                signal_type = config["signal_type"]
                token_address = None
                addr_match = SOLANA_ADDRESS_RE.search(content)
                if addr_match:
                    token_address = addr_match.group(0)

                logger.info(
                    "Discord alert: %s | signal=%s | token=%s | msg_id=%s",
                    alert_name, signal_type, token_address or "none", msg_id,
                )

                # --- Netflow Spike: set Redis boost key, no token needed ---
                if signal_type == "netflow_spike":
                    if redis_conn:
                        await redis_conn.set(
                            config["redis_boost_key"],
                            json.dumps({
                                "multiplier": config["position_limit_multiplier"],
                                "set_at": datetime.now(timezone.utc).isoformat(),
                            }),
                            ex=config["boost_ttl"],
                        )
                        logger.info("Netflow boost set: %.1fx for %ds", config["position_limit_multiplier"], config["boost_ttl"])
                    last_message_id = msg_id
                    continue

                # --- Smart Money Exit: publish to exit_check channel ---
                if signal_type == "smart_money_exit":
                    if token_address:
                        exit_payload = json.dumps({
                            "mint": token_address,
                            "reason": "smart_money_exit_alert",
                            "urgency": config.get("urgency", "normal"),
                            "source": "nansen_discord",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        if redis_conn:
                            await redis_conn.publish(config["publish_channel"], exit_payload)
                            logger.info("Published exit check for %s", token_address[:12])
                        else:
                            logger.info("No Redis — exit check not published for %s", token_address[:12] if token_address else "unknown")
                    last_message_id = msg_id
                    continue

                # --- Whale Entry / Smart Money Inflow / Fund Activity: push to signals:raw ---
                if token_address and signal_type in ("whale_entry", "smart_money_inflow", "fund_activity"):
                    signal = _build_signal(token_address, "nansen_discord", signal_type, {
                        "alert_name": alert_name,
                        "confidence_boost": config.get("confidence_boost", 0),
                        "route": config.get("route", ""),
                        "raw_content": content[:500],
                    })
                    await _push_signal(redis_conn, signal)

                last_message_id = msg_id

            # Persist last processed message ID in Redis
            if last_message_id and redis_conn:
                try:
                    await redis_conn.set("discord:last_message_id", last_message_id)
                except Exception:
                    pass

        except Exception as e:
            logger.warning("Discord poller error: %s", e)

        await asyncio.sleep(DISCORD_POLL_INTERVAL)


# ---------------------------------------------------------------------------
# 5. Helius Enhanced Whale Wallet Monitor (polls every 30s)
# ---------------------------------------------------------------------------
# Supplements PumpPortal subscribeAccountTrade with parsed transaction data
# from Helius Enhanced Transactions API — detects buys, sells, CEX transfers.
# Cache per wallet in Redis with 5min TTL to avoid redundant API calls.

WHALE_POLL_INTERVAL = 300  # seconds between full poll cycles (was 30 — too frequent)
WHALE_POLL_BATCH_SIZE = 5  # wallets per batch to stay within rate limits

from services.constants import CEX_ADDRESSES, SOL_MINT, HELIUS_WEBHOOK_TX_TYPES


async def helius_whale_poller(redis_conn: aioredis.Redis | None):
    """Poll tracked whale wallets via Helius Enhanced Transactions API."""
    if os.getenv("HELIUS_POLL_WALLETS", "false").lower() != "true":
        logger.info("Whale wallet polling disabled (HELIUS_POLL_WALLETS=false) — using webhooks only")
        return
    if not HELIUS_PARSE_HISTORY_URL:
        logger.info("HELIUS_PARSE_HISTORY_URL not set — Helius whale poller disabled")
        return

    while True:
        try:
            whale_wallets = await _load_whale_wallets()
            if not whale_wallets:
                await asyncio.sleep(WHALE_POLL_INTERVAL)
                continue

            async with aiohttp.ClientSession() as session:
                for i in range(0, len(whale_wallets), WHALE_POLL_BATCH_SIZE):
                    batch = whale_wallets[i:i + WHALE_POLL_BATCH_SIZE]
                    tasks = [_poll_whale_wallet(session, wallet, redis_conn) for wallet in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.warning("Helius whale poller error: %s", e)

        await asyncio.sleep(WHALE_POLL_INTERVAL)


async def _poll_whale_wallet(session: aiohttp.ClientSession, wallet: str, redis_conn: aioredis.Redis | None):
    """Fetch recent transactions for a single whale wallet via Helius enhanced API."""
    cache_key = f"whale_activity:{wallet}"

    # Check cache (5min TTL)
    if redis_conn:
        try:
            cached = await redis_conn.get(cache_key)
            if cached:
                return  # Already polled recently
        except Exception:
            pass

    t0 = time.time()
    try:
        url = HELIUS_PARSE_HISTORY_URL.replace("{address}", wallet)
        params = {"limit": 10}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed_ms = (time.time() - t0) * 1000
            logger.debug("Helius whale poll %s: %dms (HTTP %d)", wallet[:12], elapsed_ms, resp.status)

            if resp.status != 200:
                return

            txs = await resp.json()
            if not isinstance(txs, list):
                return

        for tx in txs:
            tx_type = tx.get("type", "")
            source = tx.get("source", "")
            timestamp = tx.get("timestamp", 0)

            # Skip old transactions (only care about last 5 minutes)
            if timestamp and (time.time() - timestamp) > 300:
                continue

            token_transfers = tx.get("tokenTransfers", [])
            for transfer in token_transfers:
                mint = transfer.get("mint", "")
                if not mint or mint == "So11111111111111111111111111111111111111112":
                    continue

                from_addr = transfer.get("fromUserAccount", "")
                to_addr = transfer.get("toUserAccount", "")
                amount = float(transfer.get("tokenAmount", 0) or 0)

                # Detect trade direction
                if to_addr == wallet:
                    action = "buy"
                elif from_addr == wallet:
                    # Check if sending to CEX (distribution signal)
                    if to_addr in CEX_ADDRESSES:
                        action = "cex_transfer"
                    else:
                        action = "sell"
                else:
                    continue

                signal_data = {
                    "wallet": wallet,
                    "action": action,
                    "token_amount": amount,
                    "tx_type": tx_type,
                    "source": source,
                    "signature": tx.get("signature", ""),
                    "slot": tx.get("slot", 0),
                    "helius_enhanced": True,
                }

                if action == "cex_transfer":
                    signal_data["cex_destination"] = to_addr

                signal = _build_signal(mint, "helius_whale", "account_trade", signal_data, 0.0)
                signal["raw_data"]["txType"] = "sell" if action in ("sell", "cex_transfer") else "buy"
                await _push_signal(redis_conn, signal)

        # Cache this wallet as polled (5min TTL)
        if redis_conn:
            try:
                await redis_conn.set(cache_key, "1", ex=300)
            except Exception:
                pass

    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        logger.debug("Helius whale poll error for %s (%.0fms): %s", wallet[:12], elapsed_ms, e)


# ---------------------------------------------------------------------------
# 6. Nansen Token Screener (Analyst signal source — polls every 10 minutes)
# ---------------------------------------------------------------------------
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")
NANSEN_SCREENER_SEEN: set[str] = set()


async def nansen_screener_poller(redis_conn: aioredis.Redis | None):
    """Poll Nansen token screener for new high-cap Solana tokens every 10 min."""
    if not NANSEN_API_KEY:
        logger.info("NANSEN_API_KEY not set — screener disabled")
        return

    nansen_disabled = False

    while True:
        if nansen_disabled:
            await asyncio.sleep(3600)  # Sleep long, don't exit (keeps gather alive)
            continue

        try:
            from services.nansen_client import screen_new_tokens
            async with aiohttp.ClientSession() as session:
                tokens = await screen_new_tokens(session, redis_conn)
                # Check for credits exhausted (nansen_client returns None on error)
                if tokens is None:
                    logger.warning("Nansen returned None — possible credits issue, retrying in 10min")
                    await asyncio.sleep(600)
                    continue
                for token in tokens:
                    mint = token.get("token_address", token.get("address", ""))
                    if not mint or mint in NANSEN_SCREENER_SEEN:
                        continue
                    NANSEN_SCREENER_SEEN.add(mint)

                    signal = _build_signal(mint, "nansen_screener", "analyst", {
                        "name": token.get("name", ""),
                        "symbol": token.get("symbol", ""),
                        "market_cap_usd": token.get("market_cap_usd", 0),
                        "smart_money_signal": True,
                    }, 0.0)
                    await _push_signal(redis_conn, signal)

                if tokens:
                    logger.info("Nansen screener: %d new tokens found, %d after dedup",
                                len(tokens), len([t for t in tokens if t.get("token_address", t.get("address", "")) not in NANSEN_SCREENER_SEEN]))

                # Trim seen set
                if len(NANSEN_SCREENER_SEEN) > 2000:
                    NANSEN_SCREENER_SEEN.clear()

        except Exception as e:
            logger.warning("Nansen screener error: %s", e)

        await asyncio.sleep(600)  # 10 minutes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    logger.info("Signal Listener starting (TEST_MODE=%s)", TEST_MODE)

    # Connect Redis always — signals must flow for paper trading too
    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5)
        await redis_conn.ping()
        logger.info("Redis connected: %s", REDIS_URL)
    except Exception as e:
        logger.warning("Redis connection failed: %s — signals will be logged only", e)
        redis_conn = None

    # Ensure watched_wallets table is populated (PostgreSQL is source of truth)
    try:
        from services.nansen_wallet_fetcher import ensure_wallets_populated
        await ensure_wallets_populated()
    except Exception as e:
        logger.warning("Wallet population check failed: %s — will use JSON fallback", e)

    # Register Helius webhook with updated wallet list (after population)
    await _register_helius_webhook(redis_conn)

    # Import telegram listener (separate service file, lazy import to avoid Telethon dep)
    try:
        from services.telegram_listener import telegram_listener
    except ImportError:
        async def telegram_listener(r):
            logger.debug("Telegram listener not available (telethon not installed)")

    await asyncio.gather(
        pumpportal_listener(redis_conn),
        _token_subscribe_listener(redis_conn),
        gecko_poller(redis_conn),
        gecko_trending_poller(redis_conn),
        dexpaprika_listener(redis_conn),
        nansen_screener_poller(redis_conn),
        discord_nansen_poller(redis_conn),
        helius_whale_poller(redis_conn),
        telegram_listener(redis_conn),
    )


if __name__ == "__main__":
    asyncio.run(main())
