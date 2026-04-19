"""
ZMN Bot — Telegram Auth Script
================================
Run this interactively to authenticate with Telegram
and get a StringSession for the TELEGRAM_SESSION env var.

Usage:
    python scripts/telegram_auth.py

You will be prompted for an SMS code sent to your phone.
Copy the session string output and add it to Railway as
TELEGRAM_SESSION env var.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")

if not API_ID or not API_HASH or not PHONE:
    print("ERROR: Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE in .env")
    sys.exit(1)


async def auth():
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), int(API_ID), API_HASH)
    await client.start(phone=PHONE)

    me = await client.get_me()
    print(f"\nAuth successful! Logged in as: {me.first_name}")
    print(f"\n{'='*60}")
    print("TELEGRAM_SESSION string (add to Railway env vars):")
    print(f"{'='*60}")
    print(client.session.save())
    print(f"{'='*60}")
    print("\nCopy the string above and set it as TELEGRAM_SESSION in Railway.")
    print("Do NOT share this string — it grants full account access.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(auth())
