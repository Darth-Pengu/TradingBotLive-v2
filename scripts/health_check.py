"""
ToxiBot Health Check — tests every API and integration.

Usage:
    python scripts/health_check.py

Loads credentials from .env automatically. No arguments needed.
"""

import asyncio
import json
import os
import sys
import time

import aiohttp
from dotenv import load_dotenv

load_dotenv()

# ── Env vars ──────────────────────────────────────────────────────────────────
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_STAKED_URL = os.getenv("HELIUS_STAKED_URL", "")
HELIUS_PARSE_TX_URL = os.getenv("HELIUS_PARSE_TX_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")
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
GOVERNANCE_MODEL = os.getenv("GOVERNANCE_MODEL", "claude-sonnet-4-6")

# Strip channel ID from URL if user pasted a full Discord URL
if DISCORD_NANSEN_CHANNEL_ID and "/" in DISCORD_NANSEN_CHANNEL_ID:
    DISCORD_NANSEN_CHANNEL_ID = DISCORD_NANSEN_CHANNEL_ID.rstrip("/").split("/")[-1]

LAMPORTS_PER_SOL = 1_000_000_000

# ── Results storage ───────────────────────────────────────────────────────────
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"

results: list[tuple[str, str, str, str]] = []  # (section, name, status, detail)


def record(section: str, name: str, status: str, detail: str):
    results.append((section, name, status, detail))


# ── Helpers ───────────────────────────────────────────────────────────────────
async def rpc_call(session: aiohttp.ClientSession, url: str, method: str, params: list = None):
    """Make a JSON-RPC call and return (result, elapsed_ms)."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    t0 = time.time()
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await resp.json()
        elapsed = int((time.time() - t0) * 1000)
        if "error" in data:
            raise Exception(data["error"])
        return data.get("result"), elapsed


async def http_get(session: aiohttp.ClientSession, url: str, headers: dict = None, params: dict = None):
    """GET request, return (status, body_json_or_text, elapsed_ms)."""
    t0 = time.time()
    async with session.get(url, headers=headers or {}, params=params or {},
                           timeout=aiohttp.ClientTimeout(total=15)) as resp:
        elapsed = int((time.time() - t0) * 1000)
        try:
            body = await resp.json()
        except Exception:
            body = await resp.text()
        return resp.status, body, elapsed


async def http_post(session: aiohttp.ClientSession, url: str, json_body: dict = None, headers: dict = None):
    """POST request, return (status, body, elapsed_ms)."""
    t0 = time.time()
    async with session.post(url, json=json_body or {}, headers=headers or {},
                            timeout=aiohttp.ClientTimeout(total=15)) as resp:
        elapsed = int((time.time() - t0) * 1000)
        try:
            body = await resp.json()
        except Exception:
            body = await resp.text()
        return resp.status, body, elapsed


# ── Test functions ────────────────────────────────────────────────────────────
async def test_helius_rpc(session: aiohttp.ClientSession, name: str, url: str):
    if not url:
        record("BLOCKCHAIN", name, SKIP, "not configured")
        return
    try:
        result, ms = await rpc_call(session, url, "getSlot")
        if ms > 500:
            record("BLOCKCHAIN", name, WARN, f"{ms}ms (>500ms)")
        else:
            record("BLOCKCHAIN", name, PASS, f"{ms}ms")
    except Exception as e:
        record("BLOCKCHAIN", name, FAIL, str(e)[:80])


async def test_helius_parse_tx(session: aiohttp.ClientSession):
    if not HELIUS_PARSE_TX_URL:
        record("BLOCKCHAIN", "Helius Parse TX", SKIP, "not configured")
        return
    try:
        # Use a known historical SOL transfer signature
        t0 = time.time()
        status, body, ms = await http_post(session, HELIUS_PARSE_TX_URL,
            json_body={"transactions": ["5wHu1qwD7q5ifaN5nwdcDqNFo53GJqa8aLXMNmbtDvMHMPLizhNRTbJrCa8ogMvsLDTLyoWisvMBXCHpt1NT3Fr3"]})
        if status == 200:
            record("BLOCKCHAIN", "Helius Parse TX", PASS, f"{ms}ms")
        else:
            record("BLOCKCHAIN", "Helius Parse TX", FAIL, f"HTTP {status}")
    except Exception as e:
        record("BLOCKCHAIN", "Helius Parse TX", FAIL, str(e)[:80])


async def test_wallet_balance(session: aiohttp.ClientSession, name: str, address: str):
    if not address or not HELIUS_RPC_URL:
        record("BLOCKCHAIN", name, SKIP, "not configured")
        return
    try:
        result, ms = await rpc_call(session, HELIUS_RPC_URL, "getBalance", [address])
        if isinstance(result, dict):
            sol = result.get("value", 0) / LAMPORTS_PER_SOL
        else:
            sol = (result or 0) / LAMPORTS_PER_SOL
        record("BLOCKCHAIN", name, PASS, f"{sol:.4f} SOL")
    except Exception as e:
        record("BLOCKCHAIN", name, FAIL, str(e)[:80])


async def test_jito(session: aiohttp.ClientSession):
    if not JITO_ENDPOINT:
        record("BLOCKCHAIN", "Jito Endpoint", SKIP, "not configured")
        return
    try:
        status, body, ms = await http_post(session, JITO_ENDPOINT,
            json_body={"jsonrpc": "2.0", "id": 1, "method": "sendBundle", "params": [[]]})
        # Expect 400 or 200 with error — means endpoint is reachable
        if status in (200, 400):
            record("BLOCKCHAIN", "Jito Endpoint", PASS, f"reachable ({ms}ms)")
        else:
            record("BLOCKCHAIN", "Jito Endpoint", WARN, f"HTTP {status}")
    except Exception as e:
        record("BLOCKCHAIN", "Jito Endpoint", FAIL, str(e)[:80])


async def test_pumpportal_rest(session: aiohttp.ClientSession):
    try:
        status, body, ms = await http_get(session, "https://pumpportal.fun/api/data")
        if status in (200, 101, 426):
            record("EXECUTION", "PumpPortal REST", PASS, f"{ms}ms")
        else:
            record("EXECUTION", "PumpPortal REST", WARN, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("EXECUTION", "PumpPortal REST", FAIL, str(e)[:80])


async def test_pumpportal_ws():
    try:
        import websockets
        msg_count = 0
        t0 = time.time()
        async with websockets.connect("wss://pumpportal.fun/api/data",
                                       ping_interval=10, ping_timeout=5,
                                       close_timeout=3) as ws:
            await ws.send(json.dumps({"method": "subscribeNewToken"}))
            try:
                async for msg in ws:
                    msg_count += 1
                    if time.time() - t0 > 10:
                        break
            except asyncio.TimeoutError:
                pass
            await ws.close()
        if msg_count > 0:
            record("EXECUTION", "PumpPortal WS", PASS, f"{msg_count} messages in 10s")
        else:
            record("EXECUTION", "PumpPortal WS", WARN, "0 messages in 10s")
    except Exception as e:
        record("EXECUTION", "PumpPortal WS", FAIL, str(e)[:80])


async def test_jupiter(session: aiohttp.ClientSession):
    try:
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "amount": 100000000,  # 0.1 SOL
            "slippageBps": 50,
        }
        status, body, ms = await http_get(session, "https://lite-api.jup.ag/swap/v1/quote", params=params)
        if status == 200 and isinstance(body, dict) and "outAmount" in body:
            record("EXECUTION", "Jupiter Ultra", PASS, f"{ms}ms")
        else:
            record("EXECUTION", "Jupiter Ultra", FAIL, f"HTTP {status}")
    except Exception as e:
        record("EXECUTION", "Jupiter Ultra", FAIL, str(e)[:80])


async def test_gecko(session: aiohttp.ClientSession):
    try:
        status, body, ms = await http_get(session,
            "https://api.geckoterminal.com/api/v2/networks/solana/new_pools",
            headers={"Accept": "application/json"})
        if status == 200:
            record("DATA FEEDS", "GeckoTerminal", PASS, f"{ms}ms")
        else:
            record("DATA FEEDS", "GeckoTerminal", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DATA FEEDS", "GeckoTerminal", FAIL, str(e)[:80])


async def test_dexpaprika(session: aiohttp.ClientSession):
    try:
        status, body, ms = await http_get(session, "https://api.dexpaprika.com/v1/solana/tokens")
        if status == 200:
            record("DATA FEEDS", "DexPaprika", PASS, f"{ms}ms")
        else:
            record("DATA FEEDS", "DexPaprika", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DATA FEEDS", "DexPaprika", FAIL, str(e)[:80])


async def test_defillama(session: aiohttp.ClientSession):
    try:
        status, body, ms = await http_get(session,
            "https://api.llama.fi/overview/dexs", params={"chain": "solana"})
        if status == 200:
            record("DATA FEEDS", "DefiLlama", PASS, f"{ms}ms")
        else:
            record("DATA FEEDS", "DefiLlama", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DATA FEEDS", "DefiLlama", FAIL, str(e)[:80])


async def test_cfgi(session: aiohttp.ClientSession):
    try:
        status, body, ms = await http_get(session,
            "https://cfgi.io/api/solana-fear-greed-index/1d")
        if status == 200:
            value = ""
            if isinstance(body, dict):
                value = body.get("value", body.get("score", ""))
            elif isinstance(body, list) and body:
                value = body[0].get("value", "")
            record("DATA FEEDS", "CFGI Fear/Greed", PASS, f"value: {value} ({ms}ms)")
        else:
            record("DATA FEEDS", "CFGI Fear/Greed", WARN, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("DATA FEEDS", "CFGI Fear/Greed", FAIL, str(e)[:80])


async def test_rugcheck(session: aiohttp.ClientSession):
    try:
        status, body, ms = await http_get(session,
            "https://api.rugcheck.xyz/v1/tokens/So11111111111111111111111111111111111111112/report")
        if status == 200:
            record("DATA FEEDS", "Rugcheck", PASS, f"{ms}ms")
        else:
            record("DATA FEEDS", "Rugcheck", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DATA FEEDS", "Rugcheck", FAIL, str(e)[:80])


async def test_vybe(session: aiohttp.ClientSession):
    if not VYBE_API_KEY:
        record("DATA FEEDS", "Vybe Network", SKIP, "VYBE_API_KEY not set")
        return
    try:
        status, body, ms = await http_get(session,
            "https://api.vybenetwork.xyz/v4/wallets/top-traders",
            headers={"X-API-KEY": VYBE_API_KEY}, params={"limit": 1})
        if status == 200:
            record("DATA FEEDS", "Vybe Network", PASS, f"{ms}ms")
        else:
            record("DATA FEEDS", "Vybe Network", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DATA FEEDS", "Vybe Network", FAIL, str(e)[:80])


async def test_nansen(session: aiohttp.ClientSession):
    if not NANSEN_API_KEY:
        record("DATA FEEDS", "Nansen API", SKIP, "NANSEN_API_KEY not set")
        return
    try:
        status, body, ms = await http_post(session,
            "https://api.nansen.ai/api/v1/smart-money/holdings",
            json_body={"chains": ["solana"], "pagination": {"page": 1, "per_page": 1}},
            headers={"Authorization": f"Bearer {NANSEN_API_KEY}", "Content-Type": "application/json"})
        if status == 200:
            record("DATA FEEDS", "Nansen API", PASS, f"{ms}ms")
        elif status == 402:
            record("DATA FEEDS", "Nansen API", WARN, f"402 Payment Required — plan upgrade needed")
        elif status == 401:
            record("DATA FEEDS", "Nansen API", FAIL, "401 Unauthorized — bad API key")
        else:
            record("DATA FEEDS", "Nansen API", WARN, f"HTTP {status} ({ms}ms)")
    except Exception as e:
        record("DATA FEEDS", "Nansen API", FAIL, str(e)[:80])


async def test_redis():
    if not REDIS_URL:
        record("INFRA", "Redis", SKIP, "REDIS_URL not set")
        return
    try:
        import redis.asyncio as aioredis
        t0 = time.time()
        conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await conn.ping()
        await conn.set("healthcheck:test", "ok", ex=10)
        val = await conn.get("healthcheck:test")
        await conn.close()
        ms = int((time.time() - t0) * 1000)
        if val == "ok":
            record("INFRA", "Redis", PASS, f"{ms}ms")
        else:
            record("INFRA", "Redis", FAIL, "SET/GET mismatch")
    except ImportError:
        record("INFRA", "Redis", SKIP, "redis package not installed")
    except Exception as e:
        record("INFRA", "Redis", FAIL, str(e)[:80])


async def test_anthropic(session: aiohttp.ClientSession):
    if not ANTHROPIC_API_KEY:
        record("INFRA", "Anthropic API", SKIP, "ANTHROPIC_API_KEY not set")
        return
    try:
        t0 = time.time()
        status, body, ms = await http_post(session,
            "https://api.anthropic.com/v1/messages",
            json_body={
                "model": GOVERNANCE_MODEL,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Reply with OK"}],
            },
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            })
        elapsed = (time.time() - t0)
        if status == 200 and isinstance(body, dict):
            usage = body.get("usage", {})
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            # Approximate cost: Sonnet ~$3/M input, $15/M output
            cost = (input_t * 3 + output_t * 15) / 1_000_000
            record("INFRA", "Anthropic API", PASS, f"{elapsed:.1f}s, ~${cost:.4f}")
        elif status == 401:
            record("INFRA", "Anthropic API", FAIL, "401 — bad API key")
        else:
            record("INFRA", "Anthropic API", FAIL, f"HTTP {status}")
    except Exception as e:
        record("INFRA", "Anthropic API", FAIL, str(e)[:80])


async def test_discord_webhook(session: aiohttp.ClientSession, name: str, url: str):
    if not url:
        record("DISCORD", name, SKIP, "not configured")
        return
    try:
        status, body, ms = await http_post(session, url,
            json_body={"content": "ToxiBot health check - ignore"})
        if status == 204:
            record("DISCORD", name, PASS, "sent")
        elif status in (200, 201):
            record("DISCORD", name, PASS, f"sent (HTTP {status})")
        else:
            record("DISCORD", name, FAIL, f"HTTP {status}")
    except Exception as e:
        record("DISCORD", name, FAIL, str(e)[:80])


async def test_discord_bot(session: aiohttp.ClientSession):
    if not DISCORD_BOT_TOKEN:
        record("DISCORD", "Bot Token", SKIP, "not configured")
        return
    try:
        status, body, ms = await http_get(session,
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"})
        if status == 200 and isinstance(body, dict):
            username = body.get("username", "unknown")
            record("DISCORD", "Bot Token", PASS, username)
        else:
            record("DISCORD", "Bot Token", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DISCORD", "Bot Token", FAIL, str(e)[:80])


async def test_discord_channel(session: aiohttp.ClientSession):
    if not DISCORD_BOT_TOKEN or not DISCORD_NANSEN_CHANNEL_ID:
        record("DISCORD", "Channel Read", SKIP, "not configured")
        return
    try:
        status, body, ms = await http_get(session,
            f"https://discord.com/api/v10/channels/{DISCORD_NANSEN_CHANNEL_ID}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
            params={"limit": 1})
        if status == 200:
            record("DISCORD", "Channel Read", PASS, "connected")
        else:
            record("DISCORD", "Channel Read", FAIL, f"HTTP {status}")
    except Exception as e:
        record("DISCORD", "Channel Read", FAIL, str(e)[:80])


def test_files():
    # whale_wallets.json
    path = os.path.join(os.path.dirname(__file__), "..", "data", "whale_wallets.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                wallets = json.load(f)
            if isinstance(wallets, list) and len(wallets) > 0:
                record("FILES", "whale_wallets.json", PASS, f"{len(wallets)} wallets")
            else:
                record("FILES", "whale_wallets.json", WARN, "empty file")
        except Exception as e:
            record("FILES", "whale_wallets.json", FAIL, str(e)[:60])
    else:
        record("FILES", "whale_wallets.json", FAIL, "not found — run scripts/seed_wallets.py")

    # governance_notes.md
    path = os.path.join(os.path.dirname(__file__), "..", "data", "governance_notes.md")
    if os.path.exists(path):
        record("FILES", "governance_notes.md", PASS, "exists")
    else:
        record("FILES", "governance_notes.md", WARN, "not found")

    # whale_wallets_pending.json
    path = os.path.join(os.path.dirname(__file__), "..", "data", "whale_wallets_pending.json")
    if os.path.exists(path):
        record("FILES", "wallets_pending.json", WARN, "exists — needs review")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print("\nRunning ToxiBot health checks...\n")

    async with aiohttp.ClientSession() as session:
        # BLOCKCHAIN — run concurrently
        await asyncio.gather(
            test_helius_rpc(session, "Helius RPC", HELIUS_RPC_URL),
            test_helius_rpc(session, "Helius Staked", HELIUS_STAKED_URL),
            test_helius_parse_tx(session),
            test_helius_rpc(session, "Helius Gatekeeper", HELIUS_GATEKEEPER_URL),
            test_wallet_balance(session, "Trading Wallet", TRADING_WALLET_ADDRESS),
            test_wallet_balance(session, "Holding Wallet", HOLDING_WALLET_ADDRESS),
            test_jito(session),
            return_exceptions=True,
        )

        # EXECUTION — PumpPortal WS is standalone
        await asyncio.gather(
            test_pumpportal_rest(session),
            test_jupiter(session),
            return_exceptions=True,
        )

    # PumpPortal WS needs its own connection (not inside ClientSession context)
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

    # ── Print results ─────────────────────────────────────────────────────────
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    DIM = "\033[90m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    icons = {PASS: f"{GREEN}[OK]", FAIL: f"{RED}[XX]", WARN: f"{YELLOW}[!!]", SKIP: f"{DIM}[--]"}
    colors = {PASS: GREEN, FAIL: RED, WARN: YELLOW, SKIP: DIM}

    print(f"\n{BOLD}=== TOXIBOT HEALTH CHECK ==={RESET}\n")

    pass_count = 0
    fail_count = 0
    warn_count = 0
    skip_count = 0
    current_section = ""

    for section, name, status, detail in results:
        if section != current_section:
            print(f"{BOLD}{section}{RESET}")
            current_section = section

        icon = icons.get(status, "")
        color = colors.get(status, "")
        pad_name = name.ljust(20)
        pad_status = status.ljust(4)
        print(f"  {icon} {color}{pad_name} {pad_status}{RESET}  {DIM}({detail}){RESET}")

        if status == PASS:
            pass_count += 1
        elif status == FAIL:
            fail_count += 1
        elif status == WARN:
            warn_count += 1
        else:
            skip_count += 1

    total = pass_count + fail_count + warn_count
    print(f"\n{BOLD}=== RESULT: {pass_count}/{total} PASS", end="")
    if warn_count:
        print(f", {warn_count} WARN", end="")
    if skip_count:
        print(f", {skip_count} SKIP", end="")
    print(f" ==={RESET}")

    if fail_count > 0:
        print(f"{RED}{BOLD}NOT READY -- fix {fail_count} issue(s) above{RESET}\n")
        sys.exit(1)
    elif TEST_MODE:
        print(f"{GREEN}{BOLD}Ready to run in TEST_MODE{RESET}\n")
    else:
        print(f"{YELLOW}{BOLD}Ready for LIVE TRADING (!!){RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
