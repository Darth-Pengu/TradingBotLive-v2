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
from typing import Set, Dict, Any, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# === CONFIGURATION CONSTANTS ===
MAX_CONCURRENT_REQUESTS = 10
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 300  # 5 minutes
API_RETRY_COUNT = 3
API_RETRY_DELAY = 1
CACHE_TTL = 30  # 30 seconds

# === TRADING PARAMETERS ===
# Speed Demon (Ultra-Early)
ULTRA_MIN_LIQ = 5
ULTRA_BUY_AMOUNT = 0.05
ULTRA_TP_X = 3.0
ULTRA_SL_X = 0.5
ULTRA_MIN_RISES = 2
ULTRA_AGE_MAX_S = 300
ULTRA_MIN_ML_SCORE = 65

# Analyst (Trending/Surge) - MODIFIED STRATEGY
ANALYST_BUY_AMOUNT = 0.05
ANALYST_MIN_LIQ = 10
ANALYST_TP_LEVEL_1_PRICE_MULT = 2.0  # Sell at 2x (100% rise)
ANALYST_TP_LEVEL_1_SELL_PCT = 80   # Sell 80% of the position
ANALYST_SL_X = 0.7
ANALYST_TRAIL = 0.15
ANALYST_MAX_POOLAGE = 30 * 60
ANALYST_MIN_ML_SCORE = 70

# Whale Tracker (Community)
COMMUNITY_BUY_AMOUNT = 0.05
COMM_HOLDER_THRESHOLD = 100
COMM_MAX_CONC = 0.15
COMM_TP_LEVELS = [2.0, 5.0, 10.0]
COMM_SL_PCT = 0.6
COMM_TRAIL = 0.25
COMM_HOLD_SECONDS = 3600
COMM_MIN_SIGNALS = 2

# Risk Management
MAX_WALLET_EXPOSURE = 0.5
DAILY_LOSS_LIMIT_PERCENT = 0.5
ANTI_SNIPE_DELAY = 2
ML_MIN_SCORE = 60

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
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
WALLET_ADDRESS = os.environ.get("WALLET_ADDRESS", "")
BITQUERY_API_KEY = os.environ.get("BITQUERY_API_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))

# Basic setup
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
if os.environ.get('RAILWAY_ENVIRONMENT'):
    data_dir = '/data'
    os.makedirs(data_dir, exist_ok=True)
    DB_PATH = os.path.join(data_dir, 'toxibot.db')
    LOG_PATH = os.path.join(data_dir, 'toxibot.log')
else:
    DB_PATH, LOG_PATH = 'toxibot.db', 'toxibot.log'

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_PATH)])
logger = logging.getLogger("toxibot")

# === GLOBAL STATE ===
blacklisted_tokens: Set[str] = set()
blacklisted_devs: Set[str] = set()
positions: Dict[str, Dict[str, Any]] = {}
activity_log = collections.deque(maxlen=1000)
tokens_checked_count = 0
ultra_wins, ultra_total, ultra_pl = 0, 0, 0.0
analyst_wins, analyst_total, analyst_pl = 0, 0, 0.0
community_wins, community_total, community_pl = 0, 0, 0.0
api_failures = collections.defaultdict(int)
api_circuit_breakers = {}
price_cache = {}
session_pool: Optional[aiohttp.ClientSession] = None
community_signal_votes = collections.defaultdict(lambda: {"sources": set(), "first_seen": time.time()})
community_token_queue = asyncio.Queue()
recent_rugdevs = set()
current_wallet_balance, daily_loss, exposure = 0.0, 0.0, 0.0
trading_enabled, selling_enabled = True, True
daily_starting_balance, daily_trades_count, consecutive_profitable_trades = 0.0, 0, 0
whale_performance = collections.defaultdict(lambda: {"trades": 0, "success": 0, "total_pl": 0.0})
whale_recent_tokens = collections.defaultdict(list)
toxibot = None # Will be initialized in main
startup_time = time.time()

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
        logger.error(f"Failed to initialize database: {e}")
        raise

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
        logger.error(f"Session error: {e}")
        raise

def is_circuit_broken(service: str) -> bool:
    if service in api_circuit_breakers and time.time() < api_circuit_breakers[service]:
        return True
    if service in api_circuit_breakers:
        del api_circuit_breakers[service]; api_failures[service] = 0
    return False

def trip_circuit_breaker(service: str):
    api_failures[service] += 1
    if api_failures[service] >= CIRCUIT_BREAKER_THRESHOLD:
        api_circuit_breakers[service] = time.time() + CIRCUIT_BREAKER_TIMEOUT
        logger.warning(f"Circuit breaker tripped for {service}")

async def fetch_token_price(token: str) -> Optional[float]:
    if token in price_cache and time.time() - price_cache[token][1] < CACHE_TTL:
        return price_cache[token][0]
    if not is_circuit_broken("dexscreener"):
        try:
            async with get_session() as session, session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("pairs"):
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                price = float(pair.get("priceUsd", 0))
                                if price > 0:
                                    price_cache[token] = (price, time.time()); return price
        except Exception as e:
            logger.error(f"DexScreener price error for {token}: {e}"); trip_circuit_breaker("dexscreener")
    return None

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
            if resp.status == 200 and 'application/json' in resp.headers.get('content-type', ''):
                return await resp.json()
    except Exception as e:
        logger.error(f"Rugcheck error for {token_addr}: {e}"); trip_circuit_breaker("rugcheck")
    return {}

def rug_gate(rug: Dict[str, Any]) -> Optional[str]:
    if rug.get("risks"):
        for risk in rug["risks"]:
            if risk.get("level") == "danger": return f"Rugcheck danger: {risk.get('name')}"
    return None

# =====================================
# Data Feeds (PumpPortal, BitQuery, Trending)
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
                    if "mint" in data and data.get("txType") == "create":
                        await callback(data["mint"], "pumpportal")
        except Exception as e:
            logger.error(f"PumpPortal WS error: {e}, retrying in 15s...")
            await asyncio.sleep(15)

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
                                if mint and mint not in seen_tokens:
                                    seen_tokens.add(mint); await callback(mint, "bitquery")
        except Exception as e:
            logger.error(f"BitQuery WS error: {e}, retrying in 30s..."); await asyncio.sleep(30)

async def dexscreener_trending_monitor(callback):
    seen_trending_tokens = collections.deque(maxlen=500)
    logger.info("📈 Starting DexScreener trending monitor...")
    while True:
        try:
            query = "SOL h1 buys > 50, h1 price change > 20, liquidity > 10000, liquidity < 250000"
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

# =====================================
# ML Scoring & Trading Logic
# =====================================
async def ml_score_token(meta: Dict[str, Any]) -> float:
    score = 50.0
    if meta.get('liq', 0) > 50: score += 20
    elif meta.get('liq', 0) > 10: score += 10
    if meta.get('vol_1h', 0) > meta.get('vol_6h', 0) / 6 * 1.5: score += 15
    if meta.get('age', 9999) < 300: score += 10
    return min(95, max(5, score))

async def calculate_position_size(bot_type: str, ml_score: float) -> float:
    global exposure, current_wallet_balance
    if not trading_enabled: return 0
    available_capital = (current_wallet_balance * MAX_WALLET_EXPOSURE) - exposure
    if available_capital <= 0.01: return 0
    base = ANALYST_BUY_AMOUNT if bot_type == "analyst" else ULTRA_BUY_AMOUNT
    ml_multiplier = 0.75 + ((ml_score - 50) / 100) # Scale from 0.75x to 1.25x
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
    global ultra_total, exposure
    if not trading_enabled or ultra_total >= ULTRA_MAX_DAILY_TRADES or token in positions: return
    
    rug_info = await rugcheck(token)
    if rug_gate(rug_info): return logger.warning(f"Rug check failed for {token[:8]}")
    
    stats = await fetch_volumes(token); age = await fetch_pool_age(token)
    if not stats or age is None or stats['liq'] < ULTRA_MIN_LIQ or age > ULTRA_AGE_MAX_S: return
    
    ml_score = await ml_score_token({'liq': stats['liq'], 'age': age, 'vol_1h': stats['vol_1h'], 'vol_6h': stats['vol_6h']})
    if ml_score < ULTRA_MIN_ML_SCORE: return
    
    size = await calculate_position_size("ultra", ml_score)
    if size > 0 and await toxibot_client.send_buy(token, size):
        price = await fetch_token_price(token) or 1e-9; ultra_total += 1; exposure += size * price
        positions[token] = {"src": "pumpportal", "buy_time": time.time(), "size": size, "entry_price": price, "total_sold_percent": 0, "local_high": price}
        save_position(token, positions[token]); record_trade(token, "BUY", size, price)
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ BUY {token[:8]} @ ${price:.6f}")

async def analyst_handler(token, src, toxibot_client):
    global analyst_total, exposure
    if not trading_enabled or len([p for p in positions.values() if 'pump' not in p['src']]) >= ANALYST_MAX_POSITIONS or token in positions: return
    
    rug_info = await rugcheck(token)
    if rug_gate(rug_info): return logger.warning(f"Rug check failed for {token[:8]}")

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

# =====================================
# Main Event Loop and Position Management
# =====================================
async def process_token(token, src):
    global tokens_checked_count
    tokens_checked_count += 1
    if src in ("pumpfun", "pumpportal"): await ultra_early_handler(token, toxibot)
    elif src in ("bitquery", "dexscreener_trending"): await analyst_handler(token, src, toxibot)

async def handle_position_exit(token, pos, last_price, toxibot_client):
    global exposure, analyst_wins, ultra_wins
    pl_ratio = last_price / pos['entry_price'] if pos['entry_price'] > 0 else 0
    sell_percent, reason = 0, ""

    if pos['src'] == 'pumpportal':
        if pl_ratio >= ULTRA_TP_X: sell_percent, reason = 100, f"{ULTRA_TP_X}x TP"
        elif pl_ratio <= ULTRA_SL_X: sell_percent, reason = 100, "Stop Loss"
    else:
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
        record_trade(token, "SELL", sold_amt, last_price, pl); save_position(token, pos)
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 💰 SELL {token[:8]} for {reason}, P/L: {pl:+.4f}")

async def update_positions():
    global exposure, current_wallet_balance
    while True:
        current_wallet_balance = await fetch_wallet_balance() or current_wallet_balance
        active_tokens = list(positions.keys())
        temp_exposure = 0
        for token in active_tokens:
            pos = positions.get(token)
            if not pos: continue
            last_price = await fetch_token_price(token)
            if last_price:
                pos['local_high'] = max(pos.get('local_high', last_price), last_price)
                temp_exposure += pos.get('size', 0) * last_price
                if pos.get('size', 0) > 1e-6:
                    await handle_position_exit(token, pos, last_price, toxibot)
                else:
                    del positions[token]; save_position(token, {}) # Mark for deletion or remove
            else:
                logger.warning(f"Could not fetch price for active position {token}")
        exposure = temp_exposure
        await asyncio.sleep(15)

# Dashboard and Server
DASHBOARD_HTML = """
<!doctype html>
<html lang="en" data-bs-theme="dark">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <meta name="description" content="A fully featured admin theme which can be used to build CRM, CMS, etc.">

  <style>
    /* --- CONTENT OF main.css --- */
    :root,
    [data-bs-theme=light] {
      --x-blue: #0d6efd;
      --x-indigo: #6610f2;
      --x-purple: #6f42c1;
      --x-pink: #d63384;
      --x-red: #dc3545;
      --x-orange: #fd7e14;
      --x-yellow: #ffc107;
      --x-green: #198754;
      --x-teal: #20c997;
      --x-cyan: #0dcaf0;
      --x-black: #000;
      --x-white: #fff;
      --x-gray: #6c757d;
      --x-gray-dark: #343a40;
      --x-gray-100: #f8f9fa;
      --x-gray-200: #e9ecef;
      --x-gray-300: #dee2e6;
      --x-gray-400: #ced4da;
      --x-gray-500: #adb5bd;
      --x-gray-600: #6c757d;
      --x-gray-700: #495057;
      --x-gray-800: #343a40;
      --x-gray-900: #212529;
      --x-primary: #0d6efd;
      --x-secondary: #6c757d;
      --x-success: #198754;
      --x-info: #0dcaf0;
      --x-warning: #ffc107;
      --x-danger: #dc3545;
      --x-light: #f8f9fa;
      --x-dark: #212529;
      --x-primary-rgb: 13, 110, 253;
      --x-secondary-rgb: 108, 117, 125;
      --x-success-rgb: 25, 135, 84;
      --x-info-rgb: 13, 202, 240;
      --x-warning-rgb: 255, 193, 7;
      --x-danger-rgb: 220, 53, 69;
      --x-light-rgb: 248, 249, 250;
      --x-dark-rgb: 33, 37, 41;
      --x-white-rgb: 255, 255, 255;
      --x-black-rgb: 0, 0, 0;
      --x-body-color-rgb: 33, 37, 41;
      --x-body-bg-rgb: 255, 255, 255;
      --x-font-sans-serif: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans", "Liberation Sans", Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";
      --x-font-monospace: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --x-gradient: linear-gradient(180deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0));
      --x-body-font-family: var(--x-font-sans-serif);
      --x-body-font-size: 1rem;
      --x-body-font-weight: 400;
      --x-body-line-height: 1.5;
      --x-body-color: #212529;
      --x-body-bg: #fff;
      --x-border-width: 1px;
      --x-border-style: solid;
      --x-border-color: #dee2e6;
      --x-border-color-translucent: rgba(0, 0, 0, 0.175);
      --x-border-radius: 0.375rem;
      --x-border-radius-sm: 0.25rem;
      --x-border-radius-lg: 0.5rem;
      --x-border-radius-xl: 1rem;
      --x-border-radius-2xl: 2rem;
      --x-border-radius-pill: 50rem;
      --x-link-color: #0d6efd;
      --x-link-hover-color: #0a58ca;
      --x-code-color: #d63384;
      --x-highlight-bg: #fff3cd;
    }

    [data-bs-theme=dark] {
      color-scheme: dark;
      --x-body-color: #dee2e6;
      --x-body-bg: #212529;
      --x-secondary-color: rgba(222, 226, 230, 0.75);
      --x-secondary-bg: #343a40;
      --x-tertiary-color: rgba(222, 226, 230, 0.5);
      --x-tertiary-bg: #2b3035;
      --x-emphasis-color: #fff;
      --x-primary-text-emphasis: #6ea8fe;
      --x-secondary-text-emphasis: #a7acb1;
      --x-success-text-emphasis: #75b798;
      --x-info-text-emphasis: #6edff6;
      --x-warning-text-emphasis: #ffda6a;
      --x-danger-text-emphasis: #ea868f;
      --x-light-text-emphasis: #f8f9fa;
      --x-dark-text-emphasis: #dee2e6;
      --x-primary-bg-subtle: #031633;
      --x-secondary-bg-subtle: #161719;
      --x-success-bg-subtle: #051b11;
      --x-info-bg-subtle: #032830;
      --x-warning-bg-subtle: #332701;
      --x-danger-bg-subtle: #2c0b0e;
      --x-light-bg-subtle: #343a40;
      --x-dark-bg-subtle: #1a1d20;
      --x-primary-border-subtle: #084298;
      --x-secondary-border-subtle: #495057;
      --x-success-border-subtle: #0f5132;
      --x-info-border-subtle: #087990;
      --x-warning-border-subtle: #997404;
      --x-danger-border-subtle: #842029;
      --x-light-border-subtle: #495057;
      --x-dark-border-subtle: #343a40;
      --x-border-color: #495057;
      --x-border-color-translucent: rgba(255, 255, 255, 0.15);
      --x-link-color: #6ea8fe;
      --x-link-hover-color: #8bb9fe;
      --x-code-color: #e685b5;
      --x-highlight-bg: #332701;
      --x-form-control-color: var(--x-body-color);
      --x-form-control-bg: var(--x-body-bg);
      --x-form-control-border-color: var(--x-border-color);
      --x-form-control-placeholder-color: #6c757d;
      --x-form-control-disabled-bg: var(--x-secondary-bg);
      --x-form-select-indicator-color: var(--x-body-color);
    }
    
    /* --- CONTENT OF utility.css --- */
    .fade { transition: opacity 0.15s linear; }
    .collapse:not(.show) { display: none; }
    .collapsing { height: 0; overflow: hidden; transition: height 0.35s ease; }
    .text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .vr { display: inline-block; align-self: stretch; width: 1px; min-height: 1em; background-color: currentcolor; opacity: 0.25; }
    .d-none { display: none !important; }
    .d-inline { display: inline !important; }
    .d-inline-block { display: inline-block !important; }
    .d-block { display: block !important; }
    .d-grid { display: grid !important; }
    .d-table { display: table !important; }
    .d-table-row { display: table-row !important; }
    .d-table-cell { display: table-cell !important; }
    .d-flex { display: flex !important; }
    .d-inline-flex { display: inline-flex !important; }
    .flex-fill { flex: 1 1 auto !important; }
    .flex-row { flex-direction: row !important; }
    .flex-column { flex-direction: column !important; }
    .justify-content-start { justify-content: flex-start !important; }
    .justify-content-end { justify-content: flex-end !important; }
    .justify-content-center { justify-content: center !important; }
    .justify-content-between { justify-content: space-between !important; }
    .align-items-start { align-items: flex-start !important; }
    .align-items-end { align-items: flex-end !important; }
    .align-items-center { align-items: center !important; }
    .align-items-baseline { align-items: baseline !important; }
    .align-items-stretch { align-items: stretch !important; }
    .order-first { order: -1 !important; }
    .order-0 { order: 0 !important; }
    .m-0 { margin: 0 !important; }
    .m-1 { margin: 0.25rem !important; }
    .mt-auto { margin-top: auto !important; }
    .ms-auto { margin-left: auto !important; }
    .p-2 { padding: 0.5rem !important; }
    .pt-2 { padding-top: 0.5rem !important; }
    .pe-3 { padding-right: 1rem !important; }
    .pb-2 { padding-bottom: 0.5rem !important; }
    .text-start { text-align: left !important; }
    .text-end { text-align: right !important; }
    .text-center { text-align: center !important; }
    .w-100 { width: 100% !important; }
    .h-100 { height: 100% !important; }
    .text-decoration-none { text-decoration: none !important; }
    .text-uppercase { text-transform: uppercase !important; }
    .text-white { color: #fff !important; }
    .text-primary { color: #0d6efd !important; }
    .text-body-secondary { color: #6c757d !important; }
    .bg-transparent { background-color: transparent !important; }
    .rounded-4 { border-radius: 0.5rem !important; }
    .rounded-circle { border-radius: 50% !important; }
    .border-0 { border: 0 !important; }
    .border-top { border-top: 1px solid #dee2e6 !important; }

  </style>

  <link rel="icon" href="favicon.ico" type="image/x-icon">

  <title>Satoshi – DeFi and Crypto Exchange Theme</title>
</head>

<body>
  <main>
    <div class="main-content">
      <div class="header">
        <div class="container-fluid">
          <div class="header-body">
            <div class="row align-items-end">
              <div class="col">
                <h6 class="header-pretitle">
                  Overview
                </h6>
                <h1 class="header-title">
                  Dashboard
                </h1>
              </div>
            </div> </div> </div>
      </div> <div class="container-fluid">
        <div class="row">
            <div class="col-12 col-lg-6 col-xl">
                <div class="card">
                    <div class="card-body">
                        <div class="row align-items-center gx-0">
                            <div class="col">
                                <h6 class="text-uppercase text-body-secondary mb-2">Wallet Balance</h6>
                                <span class="h2 mb-0" id="wallet">0.00 SOL</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-12 col-lg-6 col-xl">
                <div class="card">
                    <div class="card-body">
                        <div class="row align-items-center gx-0">
                            <div class="col">
                                <h6 class="text-uppercase text-body-secondary mb-2">Total P/L</h6>
                                <span class="h2 mb-0" id="total-pl">+0.000</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-12 col-lg-6 col-xl">
                <div class="card">
                    <div class="card-body">
                        <div class="row align-items-center gx-0">
                            <div class="col">
                                <h6 class="text-uppercase text-body-secondary mb-2">Win Rate</h6>
                                <span class="h2 mb-0" id="winrate">0.0%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-12 col-lg-6 col-xl">
                <div class="card">
                    <div class="card-body">
                        <div class="row align-items-center gx-0">
                            <div class="col">
                                <h6 class="text-uppercase text-body-secondary mb-2">Active Positions</h6>
                                <span class="h2 mb-0" id="positions-count">0</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div> <div class="card">
            <div class="card-header">
                <h4 class="card-header-title">Active Positions</h4>
            </div>
            <div class="table-responsive">
                <table class="table table-sm card-table">
                    <thead>
                        <tr>
                            <th>Token</th>
                            <th>Source</th>
                            <th>Size</th>
                            <th>Entry</th>
                            <th>P/L</th>
                            <th>P/L %</th>
                        </tr>
                    </thead>
                    <tbody id="positions-tbody">
                        </tbody>
                </table>
            </div>
        </div>

      </div>
    </div> </main> <script>
    // --- CONTENT OF main.js ---
    "use strict";
    const theme = {
        init: function() {
            this.charts.init(), this.header.init(), this.maps.init(), this.navbar.init(), this.tables.init()
        },
        charts: {
            init: function() {
                this.defaults(), this.sparkline(), this.doughnut(), this.bar(), this.line(), this.area(), this.candlestick(), this.scatter(), this.pie()
            },
            defaults: function() {
                window.Apex = {
                    colors: ["#2C7BE5", "#6E84A3", "#A1D5E7", "#A6C5F7", "#D2DDEC"],
                    chart: {
                        toolbar: {
                            show: !1
                        },
                        zoom: {
                            enabled: !1
                        }
                    },
                    dataLabels: {
                        enabled: !1
                    },
                    grid: {
                        borderColor: "#D2DDEC",
                        strokeDashArray: 4,
                        xaxis: {
                            lines: {
                                show: !0
                            }
                        }
                    },
                    legend: {
                        show: !1
                    },
                    markers: {
                        size: 0,
                        strokeColor: "#fff",
                        strokeWidth: 2,
                        hover: {
                            size: 7
                        }
                    },
                    stroke: {
                        width: 2
                    },
                    tooltip: {
                        theme: "light",
                        x: {
                            show: !1
                        }
                    },
                    xaxis: {
                        axisBorder: {
                            show: !1
                        },
                        axisTicks: {
                            show: !1
                        },
                        labels: {
                            style: {
                                colors: "#6E84A3",
                                fontSize: "13px",
                                fontFamily: "inherit",
                                fontWeight: 400
                            }
                        },
                        tooltip: {
                            enabled: !1
                        }
                    },
                    yaxis: {
                        labels: {
                            offsetX: -10,
                            style: {
                                colors: "#6E84A3",
                                fontSize: "13px",
                                fontFamily: "inherit",
                                fontWeight: 400
                            }
                        }
                    }
                }
            },
            sparkline: function() {
                document.querySelectorAll("[data-sparkline]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.sparkline)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            doughnut: function() {
                document.querySelectorAll("[data-doughnut]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.doughnut)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            bar: function() {
                document.querySelectorAll("[data-bar]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.bar)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            line: function() {
                document.querySelectorAll("[data-line]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.line)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            area: function() {
                document.querySelectorAll("[data-area]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.area)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            candlestick: function() {
                document.querySelectorAll("[data-candlestick]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.candlestick)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            scatter: function() {
                document.querySelectorAll("[data-scatter]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.scatter)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            },
            pie: function() {
                document.querySelectorAll("[data-pie]").forEach((function(e) {
                    const t = { ...JSON.parse(e.dataset.pie)
                        },
                        o = new ApexCharts(e, t);
                    o.render()
                }))
            }
        },
        header: {
            init: function() {
                this.dropdowns()
            },
            dropdowns: function() {
                document.querySelectorAll(".header-nav .dropdown-toggle").forEach((function(e) {
                    e.addEventListener("click", (function(e) {
                        e.preventDefault();
                        const t = this.closest(".dropdown");
                        t.classList.add("show"), t.closest(".header-nav").querySelectorAll(".dropdown").forEach((function(e) {
                            e != t && e.classList.remove("show")
                        }))
                    }))
                })), document.addEventListener("click", (function(e) {
                    e.target.closest(".header-nav") || document.querySelectorAll(".header-nav .dropdown").forEach((function(e) {
                        e.classList.remove("show")
                    }))
                }))
            }
        },
        maps: {
            init: function() {
                document.querySelectorAll("[data-map]").forEach((function(e) {
                    new jsVectorMap({
                        selector: e,
                        ...JSON.parse(e.dataset.map)
                    })
                }))
            }
        },
        navbar: {
            init: function() {
                this.pin(), this.tooltips(), this.collapses()
            },
            pin: function() {
                const e = document.querySelector(".navbar-vertical"),
                    t = document.querySelector("[data-toggle='navbar-vertical-pin']"),
                    o = "navbar.pinned";
                e && t && (t.addEventListener("click", (function() {
                    localStorage.setItem(o, (function() {
                        const t = e.classList.toggle("navbar-vertical-pinned");
                        return JSON.stringify(t)
                    })())
                })), JSON.parse(localStorage.getItem(o)) && e.classList.add("navbar-vertical-pinned"))
            },
            tooltips: function() {
                document.querySelectorAll(".navbar-vertical .nav-link:not(.nav-link- γνωσ)").forEach((function(e) {
                    new bootstrap.Tooltip(e)
                }))
            },
            collapses: function() {
                document.querySelectorAll(".navbar-vertical .collapse").forEach((function(e) {
                    e.addEventListener("show.bs.collapse", (function() {
                        this.closest(".navbar-vertical").querySelectorAll(".collapse.show").forEach((e => {
                            const t = bootstrap.Collapse.getInstance(e);
                            t.hide()
                        }))
                    }))
                }))
            }
        },
        tables: {
            init: function() {
                this.select(), this.sort()
            },
            select: function() {
                const e = document.querySelectorAll("[data-select-all]");
                e.forEach((function(e) {
                    e.addEventListener("change", (function() {
                        document.querySelectorAll(e.dataset.selectAll).forEach((function(t) {
                            t.checked = e.checked
                        }))
                    }))
                }))
            },
            sort: function() {
                document.querySelectorAll("[data-list]").forEach((function(e) {
                    new List(e, {
                        valueNames: e.dataset.list.split(","),
                        listClass: "list"
                    })
                }))
            }
        }
    };
    theme.init();

    // --- YOUR BOT'S WEBSOCKET LOGIC ---
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
    ws.onopen = () => console.log('WebSocket connected!');
    ws.onerror = (e) => console.error('WebSocket error:', e);

    function formatNumber(n, d = 3, s = false) {
      const v = parseFloat(n || 0);
      return (s && v > 0 ? '+' : '') + v.toFixed(d);
    }

    ws.onmessage = function(event) {
      const data = JSON.parse(event.data);

      const walletEl = document.getElementById('wallet');
      if (walletEl) walletEl.textContent = `${formatNumber(data.wallet_balance, 2)} SOL`;

      const totalPlEl = document.getElementById('total-pl');
      if (totalPlEl) {
          const totalPL = parseFloat(data.pl || 0);
          totalPlEl.textContent = formatNumber(totalPL, 4, true);
          totalPlEl.className = `h2 mb-0 ${totalPL >= 0 ? 'text-success' : 'text-danger'}`;
      }
      
      const winrateEl = document.getElementById('winrate');
      if(winrateEl) winrateEl.textContent = `${formatNumber(data.winrate, 1)}%`;
      
      const posCountEl = document.getElementById('positions-count');
      const posCount = Object.keys(data.positions || {}).length;
      if(posCountEl) posCountEl.textContent = posCount;

      const tbody = document.getElementById('positions-tbody');
      if (tbody) {
        tbody.innerHTML = '';
        if (posCount > 0) {
          Object.entries(data.positions).forEach(([token, pos]) => {
            const entry = parseFloat(pos.entry_price || 0);
            const last = parseFloat(pos.last_price || entry);
            const size = parseFloat(pos.size || 0);
            const pl = (last - entry) * size;
            const plPct = entry ? (100 * (last - entry) / entry) : 0;
            const row = tbody.insertRow();
            row.innerHTML = `
              <td><a href="https://solscan.io/token/${token}" target="_blank">${token.slice(0,6)}...${token.slice(-4)}</a></td>
              <td>${pos.src || ''}</td>
              <td>${formatNumber(size, 2)}</td>
              <td>${formatNumber(entry, 6)}</td>
              <td class="${pl >= 0 ? 'text-success' : 'text-danger'}">${formatNumber(pl, 4, true)}</td>
              <td class="${plPct >= 0 ? 'text-success' : 'text-danger'}">${formatNumber(plPct, 2, true)}%</td>
            `;
          });
        } else {
          tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-5">No active positions.</td></tr>';
        }
      }
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
            total_pl = ultra_pl + analyst_pl + community_pl
            total_trades = ultra_total + analyst_total + community_total
            total_wins = ultra_wins + analyst_wins + community_wins
            winrate = (total_wins / total_trades * 100) if total_trades > 0 else 0
            
            data = {"wallet_balance": current_wallet_balance, "pl": total_pl, "winrate": winrate, "positions": positions, "exposure": exposure, "log": list(activity_log), "tokens_checked": tokens_checked_count, "trading_enabled": trading_enabled}
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
    
    tasks = [update_positions(), pumpportal_newtoken_feed(feed_callback), dexscreener_trending_monitor(feed_callback)]
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
