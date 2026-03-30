"""
ZMN Bot — Telegram Alpha Signal Listener
==========================================
Connects to t.me/cryptoyeezuscalls via Telethon and
ingests Solana memecoin calls as trading signals.

Signal flow:
  Telegram message → extract mint/ticker → dedup via Redis
  → LPUSH signals:raw → signal_aggregator routes to analyst

Requires:
  TELEGRAM_ENABLED=true
  TELEGRAM_API_ID, TELEGRAM_API_HASH
  TELEGRAM_SESSION (StringSession from scripts/telegram_auth.py)

Disabled by default. Set TELEGRAM_ENABLED=true in Railway to activate.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("telegram_listener")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")

# Channel to monitor — Solana alpha calls
CHANNEL_USERNAME = "cryptoyeezuscalls"

# Solana mint address pattern: 32-44 char base58
MINT_PATTERN = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

# Ticker pattern: $SYMBOL (1-10 uppercase letters)
TICKER_PATTERN = re.compile(r"\$([A-Z]{1,10})\b")

# Dedup TTL: ignore repeat calls for same mint within 2 hours
DEDUP_TTL = 7200


async def _extract_mint_and_ticker(text: str) -> tuple[str, str]:
    """Extract Solana mint address and/or ticker from message text."""
    mint = ""
    ticker = ""

    # Look for Solana mint addresses (base58, 32-44 chars)
    candidates = MINT_PATTERN.findall(text)
    for candidate in candidates:
        # Filter out common false positives (short words, known non-mints)
        if len(candidate) >= 32 and not candidate.startswith("http"):
            mint = candidate
            break

    # Look for $TICKER symbols
    ticker_match = TICKER_PATTERN.search(text)
    if ticker_match:
        ticker = ticker_match.group(1)

    return mint, ticker


async def telegram_listener(redis_conn: aioredis.Redis | None):
    """Listen to Telegram channel and publish signals to Redis."""
    if not TELEGRAM_ENABLED:
        logger.info("Telegram listener disabled (TELEGRAM_ENABLED=false)")
        return

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH or not TELEGRAM_SESSION:
        logger.warning(
            "Telegram credentials missing — set TELEGRAM_API_ID, "
            "TELEGRAM_API_HASH, TELEGRAM_SESSION"
        )
        return

    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
    except ImportError:
        logger.warning("Telethon not installed — pip install telethon")
        return

    backoff = 5
    while True:
        try:
            client = TelegramClient(
                StringSession(TELEGRAM_SESSION),
                int(TELEGRAM_API_ID),
                TELEGRAM_API_HASH,
            )
            await client.connect()

            if not await client.is_user_authorized():
                logger.error(
                    "Telegram session expired — re-run scripts/telegram_auth.py "
                    "and update TELEGRAM_SESSION env var"
                )
                return

            me = await client.get_me()
            logger.info("Telegram connected as: %s", me.first_name)

            # Resolve channel
            try:
                channel = await client.get_entity(CHANNEL_USERNAME)
                logger.info(
                    "Monitoring channel: %s (id=%s)",
                    CHANNEL_USERNAME, channel.id,
                )
            except Exception as e:
                logger.error("Cannot find channel %s: %s", CHANNEL_USERNAME, e)
                return

            @client.on(events.NewMessage(chats=channel))
            async def handler(event):
                text = event.message.text or ""
                if not text.strip():
                    return

                mint, ticker = await _extract_mint_and_ticker(text)

                if not mint and not ticker:
                    logger.debug("No mint/ticker in message: %s", text[:80])
                    return

                # Dedup check
                dedup_key = mint or f"ticker:{ticker}"
                if redis_conn:
                    is_new = await redis_conn.sadd("telegram:seen:mints", dedup_key)
                    await redis_conn.expire("telegram:seen:mints", DEDUP_TTL)
                    if not is_new:
                        logger.debug("Repeat call: %s", dedup_key[:20])
                        return

                signal = {
                    "mint": mint,
                    "ticker": ticker,
                    "source": "telegram_alpha",
                    "channel": CHANNEL_USERNAME,
                    "message": text[:200],
                    "first_call": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "signal_type": "telegram_call",
                    "age_seconds": 0,
                    "raw_data": {
                        "telegram_message": text[:500],
                        "channel": CHANNEL_USERNAME,
                        "message_id": event.message.id,
                    },
                }

                logger.info(
                    "TELEGRAM CALL: %s %s from %s",
                    ticker or "no-ticker",
                    mint[:12] + "..." if mint else "no-mint",
                    CHANNEL_USERNAME,
                )

                if redis_conn:
                    await redis_conn.lpush("signals:raw", json.dumps(signal))

            logger.info("Telegram listener active — waiting for messages")
            backoff = 5  # Reset on successful connect
            await client.run_until_disconnected()

        except Exception as e:
            logger.warning(
                "Telegram error: %s — reconnecting in %ds", e, backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)


async def main():
    logger.info("Telegram Listener starting (ENABLED=%s)", TELEGRAM_ENABLED)

    redis_conn = None
    try:
        redis_conn = aioredis.from_url(
            REDIS_URL, decode_responses=True, max_connections=3
        )
        await redis_conn.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)

    await telegram_listener(redis_conn)


if __name__ == "__main__":
    asyncio.run(main())
