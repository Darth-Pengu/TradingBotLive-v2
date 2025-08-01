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
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ToxiBot v2 | Dashboard</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto+Mono:wght@400;700&display=swap');
        :root { --color-bg: #111827; --color-bg-secondary: #1F2937; --color-border: #374151; --color-text-primary: #F9FAFB; --color-text-secondary: #9CA3AF; --color-accent: #3B82F6; --color-success: #10B981; --color-danger: #EF4444; --color-warning: #F59E0B; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background-color: var(--color-bg); color: var(--color-text-primary); font-family: 'Inter', sans-serif; font-size: 14px; }
        .container { max-width: 1600px; margin: 0 auto; padding: 24px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        h1 { font-size: 1.5em; font-weight: 700; letter-spacing: -0.025em; }
        .status-badge { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 9999px; font-weight: 500; font-size: 0.875em; }
        .status-badge .dot { width: 8px; height: 8px; border-radius: 50%; }
        .status-badge.active { background-color: rgba(16, 185, 129, 0.1); color: var(--color-success); } .status-badge.active .dot { background-color: var(--color-success); }
        .status-badge.limited { background-color: rgba(245, 158, 11, 0.1); color: var(--color-warning); } .status-badge.limited .dot { background-color: var(--color-warning); }
        .status-badge.disconnected { background-color: rgba(239, 68, 68, 0.1); color: var(--color-danger); } .status-badge.disconnected .dot { background-color: var(--color-danger); }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .metric-card { background-color: var(--color-bg-secondary); border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; }
        .metric-label { font-size: 0.875em; color: var(--color-text-secondary); margin-bottom: 8px; }
        .metric-value { font-size: 1.5em; font-weight: 600; font-family: 'Roboto Mono', monospace; }
        .positive { color: var(--color-success); } .negative { color: var(--color-danger); }
        .content-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        .section-card { background-color: var(--color-bg-secondary); border: 1px solid var(--color-border); border-radius: 8px; padding: 20px; display: flex; flex-direction: column; }
        .section-title { font-size: 1.125em; font-weight: 600; margin-bottom: 16px; }
        .positions-table { width: 100%; border-collapse: collapse; flex-grow: 1; }
        .positions-table th, .positions-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--color-border); font-family: 'Roboto Mono', monospace; }
        .positions-table th { color: var(--color-text-secondary); font-family: 'Inter', sans-serif; font-weight: 500; font-size: 0.75em; text-transform: uppercase; }
        .positions-table tr:last-child td { border-bottom: none; }
        .log-container { flex-grow: 1; overflow-y: auto; font-family: 'Roboto Mono', monospace; font-size: 0.875em; background-color: var(--color-bg); padding: 12px; border-radius: 6px; }
        .log-entry.info { color: #A5B4FC; } .log-entry.success { color: var(--color-success); } .log-entry.error { color: var(--color-danger); } .log-entry.warning { color: var(--color-warning); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>ToxiBot v2 Dashboard</h1><div id="status" class="status-badge active"><div class="dot"></div><span id="status-text">Connecting...</span></div></div>
        <div class="metrics-grid"><div class="metric-card"><div class="metric-label">Wallet Balance</div><div class="metric-value positive" id="wallet">0.00 SOL</div></div><div class="metric-card"><div class="metric-label">Total P/L</div><div class="metric-value" id="total-pl">+0.000</div></div><div class="metric-card"><div class="metric-label">Win Rate</div><div class="metric-value" id="winrate">0.0%</div></div><div class="metric-card"><div class="metric-label">Exposure</div><div class="metric-value" id="exposure">0.000 SOL</div></div><div class="metric-card"><div class="metric-label">Active Pos.</div><div class="metric-value" id="positions-count">0</div></div><div class="metric-card"><div class="metric-label">Tokens Checked</div><div class="metric-value" id="tokens-checked">0</div></div></div>
        <div class="content-grid"><div class="section-card"><h2 class="section-title">Active Positions</h2><div style="overflow-x: auto; flex-grow: 1;"><table class="positions-table"><thead><tr><th>Token</th><th>Source</th><th>Size</th><th>Entry</th><th>P/L</th><th>P/L %</th></tr></thead><tbody id="positions-tbody"></tbody></table></div></div><div class="section-card"><h2 class="section-title">System Activity Log</h2><div class="log-container" id="log-container"></div></div></div>
    </div>
    <script>
        const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
        ws.onopen = () => console.log('WebSocket connected!');
        ws.onerror = (e) => console.error('WebSocket error:', e);
        ws.onclose = () => { document.getElementById('status').className = 'status-badge disconnected'; document.getElementById('status-text').textContent = 'Disconnected'; };
        function formatNumber(n, d = 3, s = false) { const v = parseFloat(n || 0); return (s && v > 0 ? '+' : '') + v.toFixed(d); }
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            const statusBadge = document.getElementById('status'), statusText = document.getElementById('status-text');
            if (!data.trading_enabled) { statusBadge.className = 'status-badge limited'; statusText.textContent = 'Selling Only'; }
            else { statusBadge.className = 'status-badge active'; statusText.textContent = 'System Active'; }
            document.getElementById('wallet').textContent = `${formatNumber(data.wallet_balance, 2)} SOL`;
            const totalPL = parseFloat(data.pl || 0);
            document.getElementById('total-pl').textContent = formatNumber(totalPL, 4, true);
            document.getElementById('total-pl').className = `metric-value ${totalPL >= 0 ? 'positive' : 'negative'}`;
            document.getElementById('winrate').textContent = `${formatNumber(data.winrate, 1)}%`;
            document.getElementById('exposure').textContent = `${formatNumber(data.exposure)} SOL`;
            const posCount = Object.keys(data.positions || {}).length;
            document.getElementById('positions-count').textContent = posCount;
            document.getElementById('tokens-checked').textContent = data.tokens_checked || 0;
            const tbody = document.getElementById('positions-tbody');
            tbody.innerHTML = '';
            if (posCount > 0) {
                Object.entries(data.positions).forEach(([token, pos]) => {
                    const entry = parseFloat(pos.entry_price || 0), last = parseFloat(pos.last_price || entry), size = parseFloat(pos.size || 0);
                    const pl = (last - entry) * size, plPct = entry ? (100 * (last - entry) / entry) : 0;
                    const row = tbody.insertRow();
                    row.innerHTML = `<td><a href="https://solscan.io/token/${token}" target="_blank" style="color:var(--color-accent);text-decoration:none;">${token.slice(0,6)}...${token.slice(-4)}</a></td><td>${pos.src||''}</td><td>${formatNumber(size,2)}</td><td>${formatNumber(entry,6)}</td><td class="${pl>=0?'positive':'negative'}">${formatNumber(pl,4,true)}</td><td class="${plPct>=0?'positive':'negative'}">${formatNumber(plPct,2,true)}%</td>`;
                });
            } else { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--color-text-secondary);padding:20px;">No active positions.</td></tr>'; }
            const logContainer = document.getElementById('log-container');
            logContainer.innerHTML = (data.log || []).map(entry => { let c='info'; if(entry.includes('✅')||entry.includes('BUY'))c='success';else if(entry.includes('❌')||entry.includes('failed'))c='error';else if(entry.includes('⚠️'))c='warning'; return `<div class="log-entry ${c}">${entry.replace(/^\[[0-9:]{8}\]\s/,'')}</div>`; }).join('');
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
