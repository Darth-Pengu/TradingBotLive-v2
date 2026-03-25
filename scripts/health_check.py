"""
ZMN Bot Health Check -- tests every API and integration.

Usage:
    python scripts/health_check.py

Loads credentials from .env automatically. No arguments needed.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

load_dotenv()

# -- Env vars --
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_STAKED_URL = os.getenv("HELIUS_STAKED_URL", "")
HELIUS_PARSE_TX_URL = os.getenv("HELIUS_PARSE_TX_URL", "")
HELIUS_PARSE_HISTORY_URL = os.getenv("HELIUS_PARSE_HISTORY_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
JITO_ENDPOINT = os.getenv("JITO_ENDPOINT", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
HOLDING_WALLET_ADDRESS = os.getenv("HOLDING_WALLET_ADDRESS", "")
VYBE_API_KEY = os.getenv("VYBE_API_KEY", "").strip()
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
REDIS_URL = os.getenv("REDIS_URL", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_WEBHOOK_TREASURY = os.getenv("DISCORD_WEBHOOK_TREASURY", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_NANSEN_CHANNEL_ID = os.getenv("DISCORD_NANSEN_CHANNEL_ID", "").strip()
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

# Strip channel ID from full Discord URL if pasted
if DISCORD_NANSEN_CHANNEL_ID and "/" in DISCORD_NANSEN_CHANNEL_ID:
    DISCORD_NANSEN_CHANNEL_ID = DISCORD_NANSEN_CHANNEL_ID.rstrip("/").split("/")[-1]

LAMPORTS_PER_SOL = 1_000_000_000

# -- Results --
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"
results: list[tuple[str, str, str, str]] = []


def record(section, name, status, detail):
    results.append((section, name, status, detail))


# -- Helpers --
async def http_get(session, url, headers=None, params=None):
    t0 = time.time()
    async with session.get(url, headers=headers or {}, params=params or {},
                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
        ms = int((time.time() - t0) * 1000)
        try:
            body = await resp.json()
        except Exception:
            body = await resp.text()
        return resp.status, body, ms


async def http_post(session, url, json_body=None, headers=None):
    t0 = time.time()
    async with session.post(url, json=json_body or {}, headers=headers or {},
                            timeout=aiohttp.ClientTimeout(total=15)) as resp:
        ms = int((time.time() - t0) * 1000)
        try:
            body = await resp.json()
        except Exception:
            body = await resp.text()
        return resp.status, body, ms


async def rpc_getslot(session, url, headers=None):
    """JSON-RPC getSlot, returns (slot, ms) or raises."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": []}
    t0 = time.time()
    async with session.post(url, json=payload, headers=headers or {},
                            timeout=aiohttp.ClientTimeout(total=10)) as resp:
        ms = int((time.time() - t0) * 1000)
        ct = resp.headers.get("content-type", "")
        if "text/html" in ct:
            raise Exception(f"HTTP {resp.status} -- endpoint returned HTML (unreachable)")
        data = await resp.json()
        if "error" in data:
            raise Exception(str(data["error"])[:80])
        return data.get("result"), ms


# ===== BLOCKCHAIN =====

async def test_helius_rpc(session):
    if not HELIUS_RPC_URL:
        record("BLOCKCHAIN", "Helius RPC", SKIP, "not configured"); return
    try:
        slot, ms = await rpc_getslot(session, HELIUS_RPC_URL)
        record("BLOCKCHAIN", "Helius RPC", PASS if ms <= 500 else WARN, f"{ms}ms (slot: {slot})")
    except Exception as e:
        record("BLOCKCHAIN", "Helius RPC", FAIL, str(e)[:80])


async def test_helius_staked(session):
    if not HELIUS_STAKED_URL:
        record("BLOCKCHAIN", "Helius Staked", SKIP, "not configured"); return
    try:
        # Named RPCs use Bearer auth, strip ?api-key= if present in URL
        url = HELIUS_STAKED_URL.split("?")[0] if "?api-key=" in HELIUS_STAKED_URL else HELIUS_STAKED_URL
        headers = {"Authorization": f"Bearer {HELIUS_API_KEY}"} if HELIUS_API_KEY else {}
        slot, ms = await rpc_getslot(session, url, headers=headers)
        record("BLOCKCHAIN", "Helius Staked", PASS if ms <= 500 else WARN, f"{ms}ms (slot: {slot})")
    except Exception as e:
        record("BLOCKCHAIN", "Helius Staked", FAIL, str(e)[:80])


async def test_helius_parse_tx(session):
    if not HELIUS_PARSE_TX_URL:
        record("BLOCKCHAIN", "Helius Parse TX", SKIP, "not configured"); return
    try:
        # POST with invalid tx -- expect 400 (reachable) or 200
        status, body, ms = await http_post(session, HELIUS_PARSE_TX_URL,
            json_body={"transactions": ["test"]})
        if status in (200, 400):
            record("BLOCKCHAIN", "Helius Parse TX", PASS, f"reachable ({ms}ms)")
        else:
            record("BLOCKCHAIN", "Helius Parse TX", FAIL, f"HTTP {status}")
    except Exception as e:
        record("BLOCKCHAIN", "Helius Parse TX", FAIL, str(e)[:80])


async def test_helius_parse_history(session):
    if not HELIUS_PARSE_HISTORY_URL or not TRADING_WALLET_ADDRESS:
        record("BLOCKCHAIN", "Helius History", SKIP, "not configured"); return
    try:
        url = HELIUS_PARSE_HISTORY_URL.replace("{address}", TRADING_WALLET_ADDRESS)
        status, body, ms = await http_get(session, url, params={"limit": 1})
        if status == 200:
            record("BLOCKCHAIN", "Helius History", PASS, f"{ms}ms")
        else:
            record("BLOCKCHAIN", "Helius History", FAIL, f"HTTP {status}")
    except Exception as e:
        record("BLOCKCHAIN", "Helius History", FAIL, str(e)[:80])


async def test_helius_gatekeeper(session):
    if not HELIUS_GATEKEEPER_URL:
        record("BLOCKCHAIN", "Helius Gatekeeper", SKIP, "not configured"); return
    try:
        slot, ms = await rpc_getslot(session, HELIUS_GATEKEEPER_URL)
        record("BLOCKCHAIN", "Helius Gatekeeper", PASS if ms <= 500 else WARN, f"{ms}ms (slot: {slot})")
    except Exception as e:
        record("BLOCKCHAIN", "Helius Gatekeeper", FAIL, str(e)[:80])


async def test_wallet_balance(session, name, address):
    if not address or not HELIUS_RPC_URL:
        record("BLOCKCHAIN", name, SKIP, "not configured"); return
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]}
        t0 = time.time()
        async with session.post(HELIUS_RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            ms = int((time.time() - t0) * 1000)
        val = data.get("result", {})
        sol = (val.get("value", val) if isinstance(val, dict) else val or 0) / LAMPORTS_PER_SOL
        status = PASS if sol > 0 else WARN
        detail = f"{sol:.4f} SOL"
        if sol == 0 and name == "Trading Wallet":
            detail += " (empty!)"
            status = WARN
        record("BLOCKCHAIN", name, status, detail)
    except Exception as e:
        record("BLOCKCHAIN", name, FAIL, str(e)[:80])


async def test_jito(session):
    if not JITO_ENDPOINT:
        record("BLOCKCHAIN", "Jito Endpoint", SKIP, "not configured"); return
    try:
        status, body, ms = await http_post(session, JITO_ENDPOINT,
            json_body={"jsonrpc": "2.0", "id": 1, "method": "sendBundle", "params": [[]]})
        if status in (200, 400):
            record("BLOCKCHAIN", "Jito Endpoint", PASS, f"reachable ({ms}ms)")
        else:
            record("BLOCKCHAIN", "Jito Endpoint", WARN, f"HTTP {status}")
    except Exception as e:
        record("BLOCKCHAIN", "Jito Endpoint", FAIL, str(e)[:80])


# ===== EXECUTION =====

async def test_pumpportal_ws():
    try:
        import websockets
        msg_count = 0
        t0 = time.time()
        async with websockets.connect("wss://pumpportal.fun/api/data",
                                       ping_interval=10, ping_timeout=5, close_timeout=3) as ws:
            await ws.send(json.dumps({"method": "subscribeNewToken"}))
            try:
                async for msg in ws:
                    msg_count += 1
                    if time.time() - t0 > 15:
                        break
            except asyncio.TimeoutError:
                pass
            await ws.close()
        if msg_count > 0:
            record("EXECUTION", "PumpPortal WS", PASS, f"{msg_count} messages in 15s")
        else:
            record("EXECUTION", "PumpPortal WS", WARN, "0 messages in 15s")
    except Exception as e:
        record("EXECUTION", "PumpPortal WS", FAIL, str(e)[:80])


async def test_jupiter(session):
    try:
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": 100000000,
            "slippageBps": 50,
        }
        status, body, ms = await http_get(session, "https://api.jup.ag/swap/v1/quote", params=params)
        if status == 200 and isinstance(body, dict) and "outAmount" in body:
            record("EXECUTION", "Jupiter Ultra", PASS, f"{ms}ms")
        else:
            record("EXECUTION", "Jupiter Ultra", FAIL, f"HTTP {status}")
    except Exception as e:
        record("EXECUTION", "Jupiter Ultra", FAIL, str(e)[:80])


# ===== DATA FEEDS =====

async def test_gecko(session):
    try:
        status, body, ms = await http_get(session,
            "https://api.geckoterminal.com/api/v2/networks/solana/new_pools",
            headers={"Accept": "application/json"})
        record("DATA FEEDS", "GeckoTerminal", PASS if status == 200 else FAIL, f"{ms}ms")
    except Exception as e:
        record("DATA FEEDS", "GeckoTerminal", FAIL, str(e)[:80])


async def test_dexpaprika(session):
    try:
        status, body, ms = await http_get(session, "https://api.dexpaprika.com/v1/solana/tokens")
        record("DATA FEEDS", "DexPaprika", PASS if status == 200 else WARN, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("DATA FEEDS", "DexPaprika", WARN, str(e)[:60])


async def test_defillama(session):
    try:
        status, body, ms = await http_get(session,
            "https://api.llama.fi/overview/dexs/Solana")
        record("DATA FEEDS", "DefiLlama", PASS if status == 200 else FAIL, f"{ms}ms")
    except Exception as e:
        record("DATA FEEDS", "DefiLlama", FAIL, str(e)[:80])


async def test_cfgi(session):
    try:
        status, body, ms = await http_get(session, "https://cfgi.io/api/solana-fear-greed-index/1d")
        if status == 200:
            val = ""
            if isinstance(body, dict):
                val = body.get("value", body.get("score", ""))
            elif isinstance(body, list) and body:
                val = body[0].get("value", "")
            record("DATA FEEDS", "CFGI Fear/Greed", PASS, f"value: {val} ({ms}ms)")
        else:
            record("DATA FEEDS", "CFGI Fear/Greed", WARN, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("DATA FEEDS", "CFGI Fear/Greed", WARN, str(e)[:60])


async def test_rugcheck(session):
    try:
        status, body, ms = await http_get(session,
            "https://api.rugcheck.xyz/v1/tokens/So11111111111111111111111111111111111111112/report")
        record("DATA FEEDS", "Rugcheck", PASS if status == 200 else FAIL, f"{ms}ms")
    except Exception as e:
        record("DATA FEEDS", "Rugcheck", FAIL, str(e)[:80])


async def test_vybe(session):
    if not VYBE_API_KEY:
        record("DATA FEEDS", "Vybe Network", SKIP, "VYBE_API_KEY not set"); return
    try:
        status, body, ms = await http_get(session,
            "https://api.vybenetwork.com/v4/wallets/top-traders",
            headers={"X-API-Key": VYBE_API_KEY}, params={"limit": 1})
        record("DATA FEEDS", "Vybe Network", PASS if status == 200 else FAIL, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("DATA FEEDS", "Vybe Network", FAIL, str(e)[:80])


async def test_nansen(session):
    if not NANSEN_API_KEY:
        record("DATA FEEDS", "Nansen API", SKIP, "NANSEN_API_KEY not set"); return
    try:
        status, body, ms = await http_post(session,
            "https://api.nansen.ai/api/v1/token-screener",
            json_body={
                "chains": ["solana"],
                "timeframe": "1h",
                "pagination": {"page": 1, "per_page": 5},
            },
            headers={"apikey": NANSEN_API_KEY, "Content-Type": "application/json"})
        if status == 200:
            record("DATA FEEDS", "Nansen API", PASS, f"{ms}ms")
        elif status == 402:
            record("DATA FEEDS", "Nansen API", WARN, "Pro subscription required -- visit nansen.ai")
        elif status == 401:
            record("DATA FEEDS", "Nansen API", FAIL, "401 Unauthorized -- bad API key")
        else:
            record("DATA FEEDS", "Nansen API", WARN, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("DATA FEEDS", "Nansen API", FAIL, str(e)[:80])


# ===== INFRASTRUCTURE =====

async def test_redis():
    if not REDIS_URL:
        record("INFRA", "Redis", WARN, "REDIS_URL not set -- configure for production")
        return
    try:
        import redis.asyncio as aioredis
    except ImportError:
        record("INFRA", "Redis", SKIP, "redis package not installed"); return

    # Try external URL
    for label, url in [("external", REDIS_URL), ("internal", "redis://redis.railway.internal:6379")]:
        try:
            t0 = time.time()
            conn = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=5)
            await conn.ping()
            await conn.set("healthcheck:test", "ok", ex=10)
            val = await conn.get("healthcheck:test")
            await conn.delete("healthcheck:test")
            await conn.close()
            ms = int((time.time() - t0) * 1000)
            if val == "ok":
                record("INFRA", f"Redis ({label})", PASS, f"{ms}ms")
                return
        except Exception as e:
            err = str(e)
            if "Connection refused" in err:
                record("INFRA", f"Redis ({label})", WARN, "connection refused")
            elif "Name or service not known" in err or "getaddrinfo" in err:
                record("INFRA", f"Redis ({label})", WARN, "DNS resolution failed")
            elif "timed out" in err.lower():
                record("INFRA", f"Redis ({label})", WARN, "connection timeout")
            else:
                record("INFRA", f"Redis ({label})", FAIL, err[:60])


async def test_anthropic(session):
    if not ANTHROPIC_API_KEY:
        record("INFRA", "Anthropic API", SKIP, "ANTHROPIC_API_KEY not set"); return
    try:
        t0 = time.time()
        status, body, ms = await http_post(session,
            "https://api.anthropic.com/v1/messages",
            json_body={
                "model": "claude-sonnet-4-6",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "reply with just the word ONLINE"}],
            },
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            })
        elapsed = time.time() - t0
        if status == 200 and isinstance(body, dict):
            usage = body.get("usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            model = body.get("model", "?")
            text = ""
            for block in body.get("content", []):
                if isinstance(block, dict) and block.get("text"):
                    text = block["text"]
            cost = (inp * 3 + out * 15) / 1_000_000
            detail = f"{elapsed:.1f}s, model={model}, {inp}+{out} tokens, ~${cost:.4f}"
            if "ONLINE" in text.upper():
                record("INFRA", "Anthropic API", PASS, detail)
            else:
                record("INFRA", "Anthropic API", WARN, f"unexpected response: {text[:30]}")
        elif status == 401:
            record("INFRA", "Anthropic API", FAIL, "401 -- bad API key")
        else:
            record("INFRA", "Anthropic API", FAIL, f"HTTP {status}")
    except Exception as e:
        record("INFRA", "Anthropic API", FAIL, str(e)[:80])


# ===== DISCORD =====

async def test_discord_webhook(session, name, url):
    if not url:
        record("DISCORD", name, SKIP, "not configured"); return
    try:
        status, body, ms = await http_post(session, url,
            json_body={"content": "ZMN Bot health check - ignore"})
        if status in (200, 201, 204):
            record("DISCORD", name, PASS, f"sent ({ms}ms)")
        else:
            record("DISCORD", name, FAIL, f"HTTP {status}")
    except Exception as e:
        record("DISCORD", name, FAIL, str(e)[:80])


async def test_discord_bot(session):
    if not DISCORD_BOT_TOKEN:
        record("DISCORD", "Bot Token", SKIP, "not configured"); return
    try:
        status, body, ms = await http_get(session,
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"})
        if status == 200 and isinstance(body, dict):
            record("DISCORD", "Bot Token", PASS, body.get("username", "?"))
        else:
            record("DISCORD", "Bot Token", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DISCORD", "Bot Token", FAIL, str(e)[:80])


async def test_discord_channel(session):
    if not DISCORD_BOT_TOKEN or not DISCORD_NANSEN_CHANNEL_ID:
        record("DISCORD", "Channel Read", SKIP, "not configured"); return
    try:
        status, body, ms = await http_get(session,
            f"https://discord.com/api/v10/channels/{DISCORD_NANSEN_CHANNEL_ID}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
            params={"limit": 1})
        if status == 200:
            record("DISCORD", "Channel Read", PASS, f"connected ({ms}ms)")
        elif status == 403:
            record("DISCORD", "Channel Read", FAIL, "403 -- bot lacks Read Message History permission")
        else:
            record("DISCORD", "Channel Read", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DISCORD", "Channel Read", FAIL, str(e)[:80])


# ===== FILES =====

def test_files():
    base = os.path.join(os.path.dirname(__file__), "..")

    path = os.path.join(base, "data", "whale_wallets.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                w = json.load(f)
            if isinstance(w, list) and len(w) > 0:
                record("FILES", "whale_wallets.json", PASS, f"{len(w)} wallets")
            else:
                record("FILES", "whale_wallets.json", WARN, "empty")
        except Exception as e:
            record("FILES", "whale_wallets.json", FAIL, str(e)[:60])
    else:
        record("FILES", "whale_wallets.json", FAIL, "not found -- run scripts/seed_wallets.py")

    path = os.path.join(base, "data", "governance_notes.md")
    record("FILES", "governance_notes.md", PASS if os.path.exists(path) else WARN,
           "exists" if os.path.exists(path) else "not found")

    path = os.path.join(base, "data", "whale_wallets_pending.json")
    if os.path.exists(path):
        record("FILES", "wallets_pending", WARN, "exists -- needs review")


# ===== MAIN =====

async def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\nZMN Bot Health Check -- {now}\n")

    async with aiohttp.ClientSession() as session:
        # BLOCKCHAIN
        await asyncio.gather(
            test_helius_rpc(session),
            test_helius_staked(session),
            test_helius_parse_tx(session),
            test_helius_parse_history(session),
            test_helius_gatekeeper(session),
            test_wallet_balance(session, "Trading Wallet", TRADING_WALLET_ADDRESS),
            test_wallet_balance(session, "Holding Wallet", HOLDING_WALLET_ADDRESS),
            test_jito(session),
            return_exceptions=True,
        )

        # EXECUTION (WS separate)
        await test_jupiter(session)

    await test_pumpportal_ws()

    async with aiohttp.ClientSession() as session:
        # DATA FEEDS
        await asyncio.gather(
            test_gecko(session),
            test_dexpaprika(session),
            test_defillama(session),
            test_cfgi(session),
            test_rugcheck(session),
            test_vybe(session),
            test_nansen(session),
            return_exceptions=True,
        )

        # INFRA
        await test_redis()
        await test_anthropic(session)

        # DISCORD
        await asyncio.gather(
            test_discord_webhook(session, "Webhook Alerts", DISCORD_WEBHOOK_URL),
            test_discord_webhook(session, "Webhook Treasury", DISCORD_WEBHOOK_TREASURY),
            test_discord_bot(session),
            test_discord_channel(session),
            return_exceptions=True,
        )

    # FILES
    test_files()

    # -- Print results --
    R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"; D = "\033[90m"; X = "\033[0m"; B = "\033[1m"
    icons = {PASS: f"{G}[OK]", FAIL: f"{R}[XX]", WARN: f"{Y}[!!]", SKIP: f"{D}[--]"}
    colors = {PASS: G, FAIL: R, WARN: Y, SKIP: D}

    print(f"\n{B}=== ZMN BOT HEALTH CHECK ==={X}\n")

    pc = fc = wc = sc = 0
    cur = ""
    for section, name, st, detail in results:
        if section != cur:
            print(f"{B}{section}{X}")
            cur = section
        print(f"  {icons[st]} {colors[st]}{name:22s} {st:4s}{X}  {D}({detail}){X}")
        if st == PASS: pc += 1
        elif st == FAIL: fc += 1
        elif st == WARN: wc += 1
        else: sc += 1

    total = pc + fc + wc
    print(f"\n{B}=== RESULT: {pc}/{total} PASS", end="")
    if wc: print(f", {wc} WARN", end="")
    if sc: print(f", {sc} SKIP", end="")
    print(f" ==={X}")

    if fc > 0:
        print(f"{R}{B}NOT READY -- fix {fc} issue(s) above{X}\n")
        sys.exit(1)
    elif TEST_MODE:
        print(f"{G}{B}Ready to run in TEST_MODE{X}\n")
    else:
        print(f"{Y}{B}Ready for LIVE TRADING{X}\n")


if __name__ == "__main__":
    asyncio.run(main())
