#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import json
import time
import aiohttp
import websockets
import collections
import sqlite3
import traceback
from telethon import TelegramClient
from telethon.sessions import StringSession
from aiohttp import web
from typing import Set, Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# === CONFIGURATION CONSTANTS ===
MAX_CONCURRENT_REQUESTS = 10
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 300  # 5 minutes
API_RETRY_COUNT = 3
API_RETRY_DELAY = 1
CACHE_TTL = 30  # 30 seconds

# === TRADING PARAMETERS (ADJUSTED FOR MORE ACTIVITY) ===
# Speed Demon (Ultra-Early)
ULTRA_MIN_LIQ = 3
ULTRA_BUY_AMOUNT = 0.05
ULTRA_TP_X = 3.0
ULTRA_SL_X = 0.5
ULTRA_AGE_MAX_S = 300
ULTRA_MIN_ML_SCORE = 60
WATCH_DURATION_SECONDS = 300  # 5 minutes
MARKET_CAP_RISE_THRESHOLD = 1.5  # 1.5x = 50% rise
WATCHLIST_POLL_INTERVAL = 20  # Check the watchlist every 20 seconds

# Analyst (Trending/Surge) - MODIFIED STRATEGY
ANALYST_BUY_AMOUNT = 0.05
ANALYST_MIN_LIQ = 8
ANALYST_TP_LEVEL_1_PRICE_MULT = 2.0  # Sell at 2x (100% rise)
ANALYST_TP_LEVEL_1_SELL_PCT = 80   # Sell 80% of the position
ANALYST_SL_X = 0.7
ANALYST_TRAIL = 0.15
ANALYST_MAX_POOLAGE = 30 * 60
ANALYST_MIN_ML_SCORE = 65

# Whale Tracker (Community)
COMMUNITY_BUY_AMOUNT = 0.05
COMM_HOLDER_THRESHOLD = 100
COMM_MAX_CONC = 0.15
COMM_TP_LEVELS = [2.0, 5.0, 10.0]
COMM_SL_PCT = 0.6
COMM_HOLD_SECONDS = 3600
COMM_MIN_SIGNALS = 2

# Watcher Strategy
WATCH_DURATION_SECONDS = 300  # 5 minutes
MARKET_CAP_RISE_THRESHOLD = 1.5  # 1.5x = 50% rise
WATCHLIST_POLL_INTERVAL = 20  # Check the watchlist every 20 seconds

# Risk Management
MAX_WALLET_EXPOSURE = 0.5
DAILY_LOSS_LIMIT_PERCENT = 0.5
ANTI_SNIPE_DELAY = 2

# ToxiBot specific
TOXIBOT_COMMAND_DELAY = 2

# Performance settings
ULTRA_MAX_DAILY_TRADES = 20
ANALYST_MAX_POSITIONS = 20
COMMUNITY_MAX_DAILY = 10

# === WHALE WALLETS TO MONITOR ===
WHALE_WALLETS = [
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "GUfCR9mK6azb9vcpsxgXyj7XRPAKJd4KMHTTVvtncGgp",
]
ADDITIONAL_WHALES = os.environ.get("WHALE_WALLETS", "").split(",")
if ADDITIONAL_WHALES and ADDITIONAL_WHALES[0]: WHALE_WALLETS.extend(ADDITIONAL_WHALES)

# === ENVIRONMENT VARIABLES ===
TELEGRAM_API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TELEGRAM_STRING_SESSION = os.environ.get("TELEGRAM_STRING_SESSION", "")
TOXIBOT_USERNAME = os.environ.get("TOXIBOT_USERNAME", "@toxi_solana_bot")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
HELIUS_RPC_URL = os.environ.get("HELIUS_RPC_URL", f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}")
WALLET_ADDRESS = os.environ.get("WALLET_ADDRESS", "")
BITQUERY_API_KEY = os.environ.get("BITQUERY_API_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))

# Configure stdout/stderr for Railway
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Database configuration - use volume for Railway
if os.environ.get('RAILWAY_ENVIRONMENT'):
    data_dir = '/data'
    os.makedirs(data_dir, exist_ok=True)
    DB_PATH = os.path.join(data_dir, 'toxibot.db')
    LOG_PATH = os.path.join(data_dir, 'toxibot.log')
else:
    DB_PATH = 'toxibot.db'
    LOG_PATH = 'toxibot.log'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH)
    ]
)
logger = logging.getLogger("toxibot")

# === GLOBAL STATE ===
positions: Dict[str, Dict[str, Any]] = {}
watchlist: Dict[str, Dict[str, Any]] = {} 
activity_log = collections.deque(maxlen=1000)
tokens_checked_count = 0
ultra_wins, ultra_total, ultra_pl = 0, 0, 0.0
analyst_wins, analyst_total, analyst_pl = 0, 0, 0.0
community_wins, community_total, community_pl = 0, 0, 0.0
api_failures = collections.defaultdict(int)
api_circuit_breakers = {}
price_cache: Dict[str, Tuple[float, float]] = {}
session_pool: Optional[aiohttp.ClientSession] = None
community_signal_votes = collections.defaultdict(lambda: {"sources": set(), "first_seen": time.time()})
community_token_queue = asyncio.Queue()
current_wallet_balance, daily_loss, exposure = 0.0, 0.0, 0.0
trading_enabled = True
daily_starting_balance = 0.0
toxibot = None
startup_time = time.time()
watcher_processed_today = 0
watcher_hits_today = 0

# =====================================
# Database Functions
# =====================================
def init_database():
    try:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir: os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS positions (token TEXT PRIMARY KEY, data JSON, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT, action TEXT, size REAL, price REAL, pl REAL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}"); raise

def save_position(token: str, data: Dict[str, Any]):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO positions (token, data, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)', (token, json.dumps(data)))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to save position for {token}: {e}")

def load_positions():
    global positions
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT token, data FROM positions')
        for row in cursor.fetchall(): positions[row[0]] = json.loads(row[1])
        conn.close()
        logger.info(f"Loaded {len(positions)} positions from database")
    except Exception as e:
        logger.error(f"Failed to load positions: {e}")

def record_trade(token: str, action: str, size: float, price: float, pl: float = 0.0):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO trades (token, action, size, price, pl) VALUES (?, ?, ?, ?, ?)', (token, action, size, price, pl))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to record trade for {token}: {e}")

# =====================================
# HTTP Session and API Wrappers
# =====================================
@asynccontextmanager
async def get_session():
    global session_pool
    if session_pool is None or session_pool.closed:
        timeout = aiohttp.ClientTimeout(total=10)
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
        session_pool = aiohttp.ClientSession(timeout=timeout, connector=connector)
    try:
        yield session_pool
    except Exception as e:
        logger.error(f"Session error: {e}"); raise

def is_circuit_broken(service: str) -> bool:
    if service in api_circuit_breakers and time.time() < api_circuit_breakers[service]: return True
    if service in api_circuit_breakers: del api_circuit_breakers[service]; api_failures[service] = 0
    return False

def trip_circuit_breaker(service: str):
    api_failures[service] += 1
    if api_failures[service] >= CIRCUIT_BREAKER_THRESHOLD:
        api_circuit_breakers[service] = time.time() + CIRCUIT_BREAKER_TIMEOUT
        logger.warning(f"Circuit breaker tripped for {service}")

async def fetch_wallet_balance() -> Optional[float]:
    if not WALLET_ADDRESS or is_circuit_broken("helius"): return None
    try:
        async with get_session() as session:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [WALLET_ADDRESS]}
            async with session.post(HELIUS_RPC_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "result" in data and "value" in data["result"]: return data["result"]["value"] / 1e9
    except Exception as e:
        logger.error(f"Failed to fetch wallet balance: {e}"); trip_circuit_breaker("helius")
    return None

async def fetch_token_price(token: str) -> Optional[float]:
    if token in price_cache and time.time() - price_cache[token][1] < CACHE_TTL: return price_cache[token][0]
    if not is_circuit_broken("dexscreener"):
        try:
            async with get_session() as session, session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("pairs"):
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                price = float(pair.get("priceUsd", 0))
                                if price > 0: price_cache[token] = (price, time.time()); return price
        except Exception as e:
            logger.error(f"DexScreener price error for {token}: {e}"); trip_circuit_breaker("dexscreener")
    return None
    
async def ultra_early_handler(token, toxibot_client):
    global watcher_processed_today
    """
    Performs initial check on new tokens and adds them to the watchlist if they pass.
    """
    if token in watchlist or token in positions:
        return # Already watching or own this token

    # 1. Initial Rugcheck
    rug_info = await rugcheck(token)
    if rug_gate(rug_info):
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] watchlist reject: {token[:8]} (rugcheck fail)")
        return

    # 2. Get Initial Market Cap
    initial_mcap = await fetch_market_cap(token)
    if not initial_mcap or initial_mcap == 0:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] watchlist reject: {token[:8]} (no mcap)")
        return
        
    # 3. Add to Watchlist
    watcher_processed_today += 1
    watchlist[token] = {
        "start_time": time.time(),
        "initial_mcap": initial_mcap
    }
    logger.info(f"🔎 Added {token[:8]} to watchlist with initial MCAP: ${initial_mcap:,.0f}")
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔎 Watching {token[:8]} (MCAP: ${initial_mcap:,.0f})")
    

async def fetch_volumes(token: str) -> Dict[str, Any]:
    if is_circuit_broken("dexscreener"): return {"liq": 0, "vol_1h": 0, "vol_6h": 0}
    try:
        async with get_session() as session, session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}") as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("pairs"):
                    for pair in data["pairs"]:
                        if pair.get("quoteToken", {}).get("symbol") == "SOL":
                            volume_h24 = float(pair.get("volume", {}).get("h24", 0))
                            return {"liq": float(pair.get("liquidity", {}).get("usd", 0)) / 1000, "vol_1h": volume_h24 / 24, "vol_6h": volume_h24 / 4}
    except Exception as e:
        logger.error(f"DexScreener volume error: {e}"); trip_circuit_breaker("dexscreener")
    return {"liq": 0, "vol_1h": 0, "vol_6h": 0}

async def fetch_pool_age(token: str) -> Optional[int]:
    if is_circuit_broken("dexscreener"): return None
    try:
        async with get_session() as session, session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}") as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("pairs"):
                    for pair in data["pairs"]:
                        if pair.get("quoteToken", {}).get("symbol") == "SOL":
                            created_at = pair.get("pairCreatedAt", 0) / 1000
                            if created_at > 0: return int(time.time() - created_at)
    except Exception as e:
        logger.error(f"DexScreener pool age error: {e}"); trip_circuit_breaker("dexscreener")
    return None

async def rugcheck(token_addr: str) -> Dict[str, Any]:
    if is_circuit_broken("rugcheck"): return {}
    try:
        async with get_session() as session, session.get(f"https://api.rugcheck.xyz/api/check/{token_addr}") as resp:
            if resp.status == 200 and 'application/json' in resp.headers.get('content-type', ''): return await resp.json()
    except Exception as e:
        logger.error(f"Rugcheck error for {token_addr}: {e}"); trip_circuit_breaker("rugcheck")
    return {}

def rug_gate(rug: Dict[str, Any]) -> Optional[str]:
    if rug.get("risks"):
        for risk in rug["risks"]:
            if risk.get("level") == "danger": return f"Rugcheck danger: {risk.get('name')}"
    return None

# =====================================
# Data Feeds (PumpPortal, BitQuery, Trending, Whales)
# =====================================
async def pumpportal_newtoken_feed(callback):
    uri = "wss://pumpportal.fun/api/data"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                logger.info("Connected to PumpPortal WebSocket")
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(msg)
                    if "mint" in data and data.get("txType") == "create": await callback(data["mint"], "pumpportal")
        except Exception as e:
            logger.error(f"PumpPortal WS error: {e}, retrying in 15s..."); await asyncio.sleep(15)

async def bitquery_streaming_feed(callback):
    if not BITQUERY_API_KEY or BITQUERY_API_KEY == "disabled": return
    ws_url = f"wss://streaming.bitquery.io/eap?token={BITQUERY_API_KEY}"
    while True:
        try:
            async with websockets.connect(ws_url, subprotocols=["graphql-ws"]) as ws:
                await ws.send(json.dumps({"type": "connection_init"}))
                if json.loads(await ws.recv()).get("type") == "connection_ack":
                    logger.info("✅ BitQuery WebSocket connected!")
                    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
                    query = f'''subscription {{ Solana {{ DEXTradeByTokens( where: {{ Trade: {{ Currency: {{ MintAddress: {{not: "So11111111111111111111111111111111111111112"}}, CreationTime: {{since: "{one_hour_ago}"}} }}, Dex: {{ ProgramAddress: {{in: ["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8","whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc","6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"]}} }}, AmountInUSD: {{gt: "100"}} }} }} ) {{ Trade {{ Currency {{ MintAddress }} }} }} }} }}'''
                    await ws.send(json.dumps({"id": "1", "type": "start", "payload": {"query": query}}))
                    seen_tokens = set()
                    while True:
                        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                        if data.get("type") == "data":
                            for trade in data.get("payload", {}).get("data", {}).get("Solana", {}).get("DEXTradeByTokens", []):
                                mint = trade.get("Trade", {}).get("Currency", {}).get("MintAddress")
                                if mint and mint not in seen_tokens: seen_tokens.add(mint); await callback(mint, "bitquery")
        except Exception as e:
            logger.error(f"BitQuery WS error: {e}, retrying in 30s..."); await asyncio.sleep(30)

async def dexscreener_trending_monitor(callback):
    seen_trending_tokens = collections.deque(maxlen=500)
    logger.info("📈 Starting DexScreener trending monitor...")
    while True:
        try:
            query = "SOL h1 buys > 50, h1 price change > 20, liquidity > 8000, liquidity < 250000"
            async with get_session() as session, session.get(f"https://api.dexscreener.com/latest/dex/search?q={query}") as resp:
                if resp.status == 200:
                    pairs = sorted((await resp.json()).get("pairs", []), key=lambda p: p.get("priceChange", {}).get("h1", 0), reverse=True)
                    for pair in pairs[:5]:
                        token = pair.get("baseToken", {}).get("address")
                        if token and token not in seen_trending_tokens:
                            seen_trending_tokens.append(token)
                            activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 Trending: {pair.get('baseToken', {}).get('symbol', 'Unknown')} (+{pair.get('priceChange', {}).get('h1', 0):.0f}%)")
                            await callback(token, "dexscreener_trending")
        except Exception as e:
            logger.error(f"Error in dexscreener_trending_monitor: {e}")
        await asyncio.sleep(90)

async def monitor_whale_wallets():
    if not HELIUS_API_KEY or not WHALE_WALLETS: return logger.warning("Whale monitoring disabled.")
    logger.info(f"Monitoring {len(WHALE_WALLETS)} whale wallets...")
    while True:
        for whale in WHALE_WALLETS:
            try:
                if is_circuit_broken("helius_whale"): await asyncio.sleep(10); continue
                url = f"https://api.helius.xyz/v0/addresses/{whale}/transactions?api-key={HELIUS_API_KEY}&limit=10&type=SWAP"
                async with get_session() as session:
                    async with session.get(url) as resp:
                        resp.raise_for_status() # Raises an error for bad status codes (4xx or 5xx)
                        for tx in await resp.json():
                            if time.time() - tx.get("timestamp", 0) > 300: continue
                            for transfer in tx.get("tokenTransfers", []):
                                if transfer.get("toUserAccount") == whale:
                                    token = transfer.get("mint")
                                    if token and token != "So11111111111111111111111111111111111111112":
                                        logger.info(f"🐋 Whale {whale[:6]}... bought {token[:6]}...")
                                        await community_token_queue.put(token)
            except aiohttp.ClientResponseError as e:
                logger.error(f"Whale monitoring HTTP error for {whale[:6]}: Status={e.status}, Message='{e.message}'")
                trip_circuit_breaker("helius_whale")
            except Exception as e:
                logger.error(f"Unexpected whale monitoring error for {whale[:6]}: {e}")
                trip_circuit_breaker("helius_whale")
        await asyncio.sleep(30)

async def fetch_market_cap(token: str) -> Optional[float]:
    """Fetch market cap data from DexScreener."""
    if is_circuit_broken("dexscreener"): return None
    try:
        async with get_session() as session:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("pairs"):
                        # Find the SOL pair for the most accurate market cap
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                return float(pair.get("fdv", 0)) # FDV is often used as market cap
    except Exception as e:
        logger.error(f"DexScreener market cap error: {e}")
        trip_circuit_breaker("dexscreener")
    return None
    
# =====================================
# ML Scoring & Trading Logic
# =====================================
async def ml_score_token(meta: Dict[str, Any]) -> float:
    score = 50.0
    liq = meta.get("liq", 0)
    if liq > 50: score += 20
    elif liq > 10: score += 10
    vol_1h = meta.get('vol_1h', 0); vol_6h = meta.get('vol_6h', 0)
    if vol_6h > 0 and vol_1h > (vol_6h / 6 * 1.5): score += 15
    if meta.get('age', 9999) < 300: score += 10
    return min(95, max(5, score))

async def calculate_position_size(bot_type: str, ml_score: float) -> float:
    global exposure, current_wallet_balance
    if not trading_enabled: return 0
    available_capital = (current_wallet_balance * MAX_WALLET_EXPOSURE) - exposure
    if available_capital <= 0.01: return 0
    base = ANALYST_BUY_AMOUNT if bot_type == "analyst" else ULTRA_BUY_AMOUNT
    ml_multiplier = 0.75 + ((ml_score - 50) / 100)
    return min(base * ml_multiplier, available_capital, 0.1)

class ToxiBotClient:
    def __init__(self, api_id, api_hash, session_id, username):
        self._client = TelegramClient(StringSession(session_id), api_id, api_hash, connection_retries=5)
        self.bot_username = username
        self.send_lock = asyncio.Lock()
    async def connect(self): await self._client.start(); logger.info("Connected to ToxiBot (Telegram).")
    async def send_command(self, cmd: str) -> bool:
        async with self.send_lock:
            try:
                await self._client.send_message(self.bot_username, cmd); await asyncio.sleep(3); return True
            except Exception as e:
                logger.error(f"Failed to send command '{cmd}': {e}"); return False
            finally:
                await asyncio.sleep(TOXIBOT_COMMAND_DELAY)
    async def send_buy(self, mint: str, amount: float): return await self.send_command(f"/buy {mint} {amount:.4f}")
    async def send_sell(self, mint: str, perc: int): return await self.send_command(f"/sell {mint} {perc}%")

# =====================================
# Trading Strategy Handlers
# =====================================
async def ultra_early_handler(token, toxibot_client):
    """
    Performs initial check on new tokens and adds them to the watchlist if they pass.
    """
    if token in watchlist or token in positions:
        return # Already watching or own this token

    # 1. Initial Rugcheck
    rug_info = await rugcheck(token)
    if rug_gate(rug_info):
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}]  watchlist reject: {token[:8]} (rugcheck fail)")
        return

    # 2. Get Initial Market Cap
    initial_mcap = await fetch_market_cap(token)
    if not initial_mcap or initial_mcap == 0:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] watchlist reject: {token[:8]} (no mcap)")
        return
        
    # 3. Add to Watchlist
    watchlist[token] = {
        "start_time": time.time(),
        "initial_mcap": initial_mcap
    }
    logger.info(f"🔎 Added {token[:8]} to watchlist with initial MCAP: ${initial_mcap:,.0f}")
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔎 Watching {token[:8]} (MCAP: ${initial_mcap:,.0f})")

async def analyst_handler(token, src, toxibot_client):
    global analyst_total, exposure
    if not trading_enabled or len([p for p in positions.values() if 'pump' not in p['src']]) >= ANALYST_MAX_POSITIONS or token in positions: return
    rug_info = await rugcheck(token)
    if rug_gate(rug_info): return
    stats = await fetch_volumes(token); age = await fetch_pool_age(token)
    if not stats or age is None or stats['liq'] < ANALYST_MIN_LIQ or age > ANALYST_MAX_POOLAGE: return
    ml_score = await ml_score_token({'liq': stats['liq'], 'age': age, 'vol_1h': stats['vol_1h'], 'vol_6h': stats['vol_6h']})
    if ml_score < ANALYST_MIN_ML_SCORE: return
    size = await calculate_position_size("analyst", ml_score)
    if size > 0 and await toxibot_client.send_buy(token, size):
        price = await fetch_token_price(token) or 1e-9; analyst_total += 1; exposure += size * price
        positions[token] = {"src": src, "buy_time": time.time(), "size": size, "entry_price": price, "total_sold_percent": 0, "local_high": price}
        save_position(token, positions[token]); record_trade(token, "BUY", size, price)
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ BUY {token[:8]} @ ${price:.6f} (Analyst)")

async def community_trade_manager(toxibot_client):
    while True:
        token = await community_token_queue.get()
        logger.info(f"COMMUNITY TOKEN DETECTED: {token[:8]}, passing to Analyst handler.")
        await process_token(token, "community")

# =====================================
# Main Loop, Position & Risk Management
# =====================================
async def process_token(token, src):
    global tokens_checked_count
    tokens_checked_count += 1
    if src in ("pumpfun", "pumpportal"):
        await ultra_early_handler(token, toxibot)
    # Add "watchlist_hit" to this line
    elif src in ("bitquery", "dexscreener_trending", "community", "watchlist_hit"):
        await analyst_handler(token, src, toxibot)

async def handle_position_exit(token, pos, last_price, toxibot_client):
    global exposure, analyst_wins, ultra_wins, analyst_pl, ultra_pl
    pl_ratio = last_price / pos['entry_price'] if pos['entry_price'] > 0 else 0
    sell_percent, reason = 0, ""
    if pos['src'] == 'pumpportal':
        if pl_ratio >= ULTRA_TP_X: sell_percent, reason = 100, f"{ULTRA_TP_X}x TP"
        elif pl_ratio <= ULTRA_SL_X: sell_percent, reason = 100, "Stop Loss"
    else: # Analyst & Community
        if pl_ratio >= ANALYST_TP_LEVEL_1_PRICE_MULT and pos['total_sold_percent'] == 0:
            sell_percent, reason = ANALYST_TP_LEVEL_1_SELL_PCT, f"{ANALYST_TP_LEVEL_1_PRICE_MULT}x TP"
        elif pl_ratio <= ANALYST_SL_X: sell_percent, reason = 100 - pos['total_sold_percent'], "Stop Loss"
        elif pos.get('local_high', 0) > pos['entry_price'] * 1.5 and last_price < pos['local_high'] * (1 - ANALYST_TRAIL):
            sell_percent, reason = 100 - pos['total_sold_percent'], "Trailing SL"
    
    if sell_percent > 0 and await toxibot_client.send_sell(token, int(sell_percent)):
        sold_amt = pos['size'] * (sell_percent / 100.0); pl = (last_price - pos['entry_price']) * sold_amt
        exposure -= sold_amt * last_price; pos['size'] -= sold_amt; pos['total_sold_percent'] += sell_percent
        if pl > 0:
            if pos['src'] == 'pumpportal': ultra_wins += 1
            else: analyst_wins += 1
        if pos['src'] == 'pumpportal': ultra_pl += pl
        else: analyst_pl += pl
        record_trade(token, "SELL", sold_amt, last_price, pl); save_position(token, pos)
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 SELL {token[:8]} for {reason}, P/L: {pl:+.4f}")

async def update_positions_and_risk():
    global exposure, current_wallet_balance, trading_enabled, daily_starting_balance, daily_loss
    while True:
        balance = await fetch_wallet_balance()
        if balance is not None:
            current_wallet_balance = balance
            if daily_starting_balance == 0: daily_starting_balance = balance

        daily_loss = daily_starting_balance - current_wallet_balance
        if daily_starting_balance > 0 and (daily_loss / daily_starting_balance) >= DAILY_LOSS_LIMIT_PERCENT:
            if trading_enabled: logger.critical(f"BUYING DISABLED: Daily loss limit reached!"); trading_enabled = False
        else:
            if not trading_enabled: logger.info("Trading re-enabled."); trading_enabled = True

        active_tokens = list(positions.keys())
        temp_exposure = 0
        for token in active_tokens:
            pos = positions.get(token)
            if not pos: continue
            last_price = await fetch_token_price(token)
            if last_price:
                pos['last_price'] = last_price
                pos['local_high'] = max(pos.get('local_high', last_price), last_price)
                temp_exposure += pos.get('size', 0) * last_price
                if pos.get('size', 0) > 1e-6:
                    await handle_position_exit(token, pos, last_price, toxibot)
                else:
                    del positions[token]; save_position(token, {})
            else:
                logger.warning(f"Could not fetch price for active position {token}")
        exposure = temp_exposure
        await asyncio.sleep(15)

async def monitor_watchlist():
    """Monitors tokens for a sharp market cap rise and hands them off for buying."""
    while True:
        try:
            # Create a copy of keys to avoid issues with modifying dict during iteration
            tokens_to_check = list(watchlist.keys())
            
            for token in tokens_to_check:
                if token not in watchlist: continue # Might have been processed already

                watch_data = watchlist[token]
                elapsed_time = time.time() - watch_data["start_time"]

                # Remove stale tokens from watchlist
                if elapsed_time > WATCH_DURATION_SECONDS:
                    logger.info(f"Token {token[:8]} expired from watchlist.")
                    del watchlist[token]
                    continue

                # Fetch current market cap
                current_mcap = await fetch_market_cap(token)
                if not current_mcap:
                    continue
                
                initial_mcap = watch_data["initial_mcap"]
                
                # THE TRIGGER: Check for a sharp rise
                if current_mcap >= initial_mcap * MARKET_CAP_RISE_THRESHOLD:
                    watcher_hits_today += 1
                    logger.info(f"🔥 WATCHLIST TRIGGER! {token[:8]} surged from ${initial_mcap:,.0f} to ${current_mcap:,.0f}")
                    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔥 WATCHLIST HIT on {token[:8]}!")
                    
                    # Hand off to the Analyst bot to perform final checks and buy
                    await process_token(token, "watchlist_hit") 
                    
                    # Remove from watchlist once triggered
                    del watchlist[token]

        except Exception as e:
            logger.error(f"Error in monitor_watchlist: {e}")
        
        await asyncio.sleep(WATCHLIST_POLL_INTERVAL)

# =====================================
# Dashboard and Server
# =====================================
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ToxiBot Trading Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/moment@2.29.4/moment.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; background: #0a0e1a; color: #e0e0e0; line-height: 1.6; }
        .dashboard { padding: 20px; max-width: 1600px; margin: 0 auto; }
        h1 { font-size: 2.5rem; margin-bottom: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: linear-gradient(135deg, #1a1f2e 0%, #1e243a 100%); padding: 25px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); position: relative; overflow: hidden; transition: transform 0.3s ease, box-shadow 0.3s ease; }
        .stat-card:hover { transform: translateY(-5px); box-shadow: 0 15px 40px rgba(0,0,0,0.4); }
        .stat-card::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 3px; background: linear-gradient(90deg, #667eea, #764ba2); }
        .stat-label { font-size: 0.9rem; color: #9ca3af; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
        .stat-value { font-size: 2rem; font-weight: 700; color: #fff; margin-bottom: 5px; }
        .positive { color: #10b981; } .negative { color: #ef4444; } .neutral { color: #6b7280; }
        .bot-personalities { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .bot-card { background: #1a1f2e; border-radius: 15px; padding: 25px; position: relative; overflow: hidden; }
        .bot-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .bot-name { font-size: 1.5rem; font-weight: 600; }
        .bot-status { padding: 5px 15px; border-radius: 20px; font-size: 0.85rem; font-weight: 500; }
        .status-active { background: rgba(16, 185, 129, 0.2); color: #10b981; }
        .bot-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }
        .bot-stat { background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px; }
        .bot-stat-label { font-size: 0.8rem; color: #9ca3af; margin-bottom: 5px; }
        .bot-stat-value { font-size: 1.2rem; font-weight: 600; }
        .charts-section { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 30px; }
        .chart-container { background: #1a1f2e; padding: 25px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
        .chart-title { font-size: 1.3rem; margin-bottom: 20px; color: #e0e0e0; }
        .recent-trades { background: #1a1f2e; padding: 25px; border-radius: 15px; margin-bottom: 30px; }
        .trades-table { width: 100%; border-collapse: collapse; }
        .trades-table th { text-align: left; padding: 12px; border-bottom: 2px solid #2d3748; color: #9ca3af; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; }
        .trades-table td { padding: 12px; border-bottom: 1px solid rgba(45, 55, 72, 0.5); }
        .trade-token a { font-weight: 600; color: #667eea; text-decoration: none; }
        .trade-token a:hover { text-decoration: underline; }
        .alert { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; padding: 15px 20px; border-radius: 10px; margin-bottom: 20px; display: none; align-items: center; gap: 10px; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .live-indicator { display: inline-block; width: 8px; height: 8px; background: #10b981; border-radius: 50%; margin-left: 10px; animation: pulse 2s infinite; }
        .live-indicator.disconnected { background: #ef4444; animation: none; }
        @media (max-width: 768px) { .stats-grid, .charts-section, .bot-personalities { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="dashboard">
        <h1>ToxiBot Trading Dashboard <span id="liveIndicator" class="live-indicator"></span></h1>
        
        <div id="alertSection" class="alert">
            <span>⚠️</span>
            <span id="alertText"></span>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-label">Total P&L (SOL)</div><div class="stat-value" id="totalPL">+0.00</div></div>
            <div class="stat-card"><div class="stat-label">Active Positions</div><div class="stat-value" id="activePositions">0</div></div>
            <div class="stat-card"><div class="stat-label">Win Rate</div><div class="stat-value" id="winRate">0.0%</div></div>
            <div class="stat-card"><div class="stat-label">Tokens Checked</div><div class="stat-value" id="tokensChecked">0</div></div>
            <div class="stat-card"><div class="stat-label">Wallet Balance (SOL)</div><div class="stat-value" id="walletBalance">0.00</div></div>
            <div class="stat-card"><div class="stat-label">Exposure (SOL)</div><div class="stat-value" id="exposure">0.00</div></div>
        </div>

        <div class="bot-personalities">
            <div class="bot-card">
                <div class="bot-header"><div class="bot-name">🔭 Watcher</div><div class="bot-status status-active">Active</div></div>
                <div class="bot-stats">
                    <div class="bot-stat"><div class="bot-stat-label">Currently Watching</div><div class="bot-stat-value" id="watcherWatching">0</div></div>
                    <div class="bot-stat"><div class="bot-stat-label">Processed Today</div><div class="bot-stat-value" id="watcherProcessed">0</div></div>
                    <div class="bot-stat"><div class="bot-stat-label">Successful Hits</div><div class="bot-stat-value" id="watcherHits">0</div></div>
                </div>
            </div>
            <div class="bot-card">
                <div class="bot-header"><div class="bot-name">📊 Analyst</div><div class="bot-status status-active">Active</div></div>
                <div class="bot-stats">
                    <div class="bot-stat"><div class="bot-stat-label">Trades</div><div class="bot-stat-value" id="analystTrades">0</div></div>
                    <div class="bot-stat"><div class="bot-stat-label">Win Rate</div><div class="bot-stat-value" id="analystWinRate">0%</div></div>
                    <div class="bot-stat"><div class="bot-stat-label">P&L (SOL)</div><div class="bot-stat-value" id="analystPL">0.00</div></div>
                </div>
            </div>
            <div class="bot-card">
                <div class="bot-header"><div class="bot-name">🐋 Whale Tracker</div><div class="bot-status status-active">Active</div></div>
                <div class="bot-stats">
                    <div class="bot-stat"><div class="bot-stat-label">Trades</div><div class="bot-stat-value" id="communityTrades">0</div></div>
                    <div class="bot-stat"><div class="bot-stat-label">Win Rate</div><div class="bot-stat-value" id="communityWinRate">0%</div></div>
                    <div class="bot-stat"><div class="bot-stat-label">P&L (SOL)</div><div class="bot-stat-value" id="communityPL">0.00</div></div>
                </div>
            </div>
        </div>
        
        <div class="charts-section">
            <div class="chart-container"><h3 class="chart-title">P&L Performance (Last 7 Days)</h3><canvas id="plChart"></canvas></div>
            <div class="chart-container"><h3 class="chart-title">Trade Volume by Bot</h3><canvas id="volumeChart"></canvas></div>
        </div>
        
        <div class="recent-trades">
            <h2 style="font-size: 1.8rem; margin-bottom: 20px;">Activity Log</h2>
            <div id="logContainer" style="height: 300px; overflow-y: auto; background: #111624; border-radius: 10px; padding: 15px; font-family: 'Roboto Mono', monospace;"></div>
        </div>
    </div>
    
    <script>
        // --- FIX: Cleaned up all indentation in this script for readability ---
        let plChart, volumeChart;

        function initializeCharts() {
            const chartOptions = {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false, labels: { color: '#9ca3af' } } },
                scales: {
                    y: { grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#9ca3af' } },
                    x: { grid: { display: false }, ticks: { color: '#9ca3af' } }
                }
            };

            const plCtx = document.getElementById('plChart').getContext('2d');
            plChart = new Chart(plCtx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'Daily P&L (SOL)', data: [], borderColor: '#667eea', backgroundColor: 'rgba(102, 126, 234, 0.1)', tension: 0.4, fill: true }] },
                options: chartOptions
            });

            const volumeCtx = document.getElementById('volumeChart').getContext('2d');
            volumeChart = new Chart(volumeCtx, {
                type: 'doughnut',
                data: { labels: ['Watcher Processed', 'Analyst', 'Community'], datasets: [{ data: [0, 0, 0], backgroundColor: ['#667eea', '#764ba2', '#f093fb'], borderWidth: 0 }] },
                options: { ...chartOptions, plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af', padding: 20 } } } }
            });
        }

        document.addEventListener('DOMContentLoaded', initializeCharts);

        const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
        ws.onopen = () => document.getElementById('liveIndicator').classList.remove('disconnected');
        ws.onerror = () => document.getElementById('liveIndicator').classList.add('disconnected');
        ws.onclose = () => document.getElementById('liveIndicator').classList.add('disconnected');

        function formatNumber(n, d = 3, s = false) { const v = parseFloat(n || 0); return (s && v > 0 ? '+' : '') + v.toFixed(d); }

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // Stats
            const totalPL = parseFloat(data.pl || 0);
            const totalPlEl = document.getElementById('totalPL');
            totalPlEl.textContent = formatNumber(totalPL, 4, true);
            totalPlEl.className = `stat-value ${totalPL >= 0 ? 'positive' : 'negative'}`;
            
            document.getElementById('activePositions').textContent = Object.keys(data.positions || {}).length;
            document.getElementById('winRate').textContent = `${formatNumber(data.winrate, 1)}%`;
            document.getElementById('tokensChecked').textContent = data.tokens_checked || 0;
            document.getElementById('walletBalance').textContent = formatNumber(data.wallet_balance, 2);
            document.getElementById('exposure').textContent = formatNumber(data.exposure, 3);

            // Bot Personalities
            // Update Watcher Stats
            const watcherStats = data.watcher_stats || {watching: 0, processed: 0, hits: 0};
            document.getElementById('watcherWatching').textContent = watcherStats.watching;
            document.getElementById('watcherProcessed').textContent = watcherStats.processed;
            document.getElementById('watcherHits').textContent = watcherStats.hits;

            // Update Analyst and Community Stats
            ['analyst', 'community'].forEach(bot => {
                const stats = data[`${bot}_stats`] || {trades: 0, wins: 0, pl: 0};
                document.getElementById(`${bot}Trades`).textContent = stats.trades;
                document.getElementById(`${bot}WinRate`).textContent = `${stats.trades > 0 ? formatNumber(stats.wins / stats.trades * 100, 1) : '0'}%`;
                const plEl = document.getElementById(`${bot}PL`);
                plEl.textContent = formatNumber(stats.pl, 4, true);
                plEl.className = `bot-stat-value ${stats.pl >= 0 ? 'positive' : 'negative'}`;
            });
            // --- FIX: Removed duplicated code block that was here ---

            // Alert
            const alertSection = document.getElementById('alertSection');
            if (!data.trading_enabled) {
                alertSection.style.display = 'flex';
                document.getElementById('alertText').textContent = 'Warning: Trading is disabled due to risk limits.';
            } else {
                alertSection.style.display = 'none';
            }

            // Charts
            if (plChart && data.historical_pl) {
                const labels = data.historical_pl.map(d => moment(d[0]).format('MMM D'));
                const values = data.historical_pl.map(d => d[1]);
                plChart.data.labels = labels;
                plChart.data.datasets[0].data = values;
                plChart.update();
            }
            if (volumeChart) {
                // --- FIX: Updated volume chart to use watcher and other stats ---
                const watcherData = data.watcher_stats || {processed: 0};
                const analystData = data.analyst_stats || {trades: 0};
                const communityData = data.community_stats || {trades: 0};
                volumeChart.data.datasets[0].data = [watcherData.processed, analystData.trades, communityData.trades];
                volumeChart.update();
            }

            // Log
            const logContainer = document.getElementById('logContainer');
            logContainer.innerHTML = (data.log || []).map(entry => {
                let color = '#9ca3af';
                if (entry.includes('✅') || entry.includes('BUY')) color = '#10b981';
                else if (entry.includes('❌') || entry.includes('failed')) color = '#ef4444';
                else if (entry.includes('💰') || entry.includes('SELL')) color = '#667eea';
                return `<div style="color: ${color};">${entry.replace(/^\[[0-9:]{8}\]\s/, '')}</div>`;
            }).join('');
            logContainer.scrollTop = logContainer.scrollHeight;
        };
    </script>
</body>
</html>
"""

async def html_handler(request): return web.Response(text=DASHBOARD_HTML, content_type="text/html")
async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    while True:
        try:
            # --- NEW: Fetch historical P&L for the chart ---
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            # Get daily P&L for the last 7 days
            cursor.execute("""
                SELECT strftime('%Y-%m-%d', timestamp), SUM(pl)
                FROM trades
                WHERE timestamp >= date('now', '-7 days')
                GROUP BY 1
                ORDER BY 1;
            """)
            historical_pl = cursor.fetchall()
            conn.close()
            # --- END NEW ---
            
            total_pl = ultra_pl + analyst_pl + community_pl
            total_trades = ultra_total + analyst_total + community_total
            total_wins = ultra_wins + analyst_wins + community_wins
            winrate = (total_wins / total_trades * 100) if total_trades > 0 else 0
            
            data = {
                "wallet_balance": current_wallet_balance,
                "pl": total_pl,
                "winrate": winrate,
                "positions": positions,
                "exposure": exposure,
                "log": list(activity_log),
                "tokens_checked": tokens_checked_count,
                "trading_enabled": trading_enabled,
                # Bot specific stats
                "watcher_stats": {"watching": len(watchlist), "processed": watcher_processed_today, "hits": watcher_hits_today},
                "analyst_stats": {"trades": analyst_total, "wins": analyst_wins, "pl": analyst_pl},
                "community_stats": {"trades": community_total, "wins": community_wins, "pl": community_pl},
                # Historical data for chart
                "historical_pl": historical_pl
            }
            await ws.send_str(json.dumps(data, default=str))
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"WS send error: {e}"); break
    return ws

async def run_server():
    app = web.Application()
    app.router.add_get('/', html_handler)
    app.router.add_get('/ws', ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Dashboard up at http://0.0.0.0:{PORT}")
    await asyncio.Event().wait()

async def bot_main():
    global toxibot
    if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_STRING_SESSION]):
        return logger.error("Missing Telegram credentials!")
    init_database(); load_positions()
    toxibot = ToxiBotClient(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_STRING_SESSION, TOXIBOT_USERNAME)
    await toxibot.connect()
    
    async def feed_callback(token, src): await process_token(token, src)
    
    tasks = [
        update_positions_and_risk(),
        pumpportal_newtoken_feed(feed_callback),
        dexscreener_trending_monitor(feed_callback),
        monitor_whale_wallets(),
        community_trade_manager(toxibot),
        monitor_watchlist()
    ]
    if BITQUERY_API_KEY and BITQUERY_API_KEY != "disabled":
        tasks.append(bitquery_streaming_feed(feed_callback))
    
    await asyncio.gather(*tasks)

async def main():
    await asyncio.gather(run_server(), bot_main())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Top-level error: {e}"); traceback.print_exc()
