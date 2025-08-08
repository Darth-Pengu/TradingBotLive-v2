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
from collections import deque
import sqlite3
import numpy as np
import traceback
import statistics
from telethon import TelegramClient
from telethon.sessions import StringSession
from aiohttp import web
from typing import Set, Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from bs4 import BeautifulSoup

# Flask imports for web dashboard
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading

# === CONFIGURATION CONSTANTS ===
MAX_CONCURRENT_REQUESTS = 10
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 300  # 5 minutes
API_RETRY_COUNT = 3
API_RETRY_DELAY = 1
CACHE_TTL = 30  # 30 seconds

# === TRADING PARAMETERS (AGGRESSIVE MODE) ===
# Speed Demon (Ultra-Early) - MORE AGGRESSIVE
ULTRA_MIN_LIQ = 2  # Lowered from 3
ULTRA_BUY_AMOUNT = 0.08  # Increased from 0.05
ULTRA_TP_X = 2.5  # Lowered from 3.0 for faster exits
ULTRA_SL_X = 0.6  # Increased from 0.5 for less aggressive stop loss
ULTRA_AGE_MAX_S = 600  # Increased from 300 (10 minutes)
ULTRA_MIN_ML_SCORE = 50  # Lowered from 60
WATCH_DURATION_SECONDS = 180  # Reduced from 300 (3 minutes)
MARKET_CAP_RISE_THRESHOLD = 1.3  # Lowered from 1.5 (30% rise)
WATCHLIST_POLL_INTERVAL = 10  # Reduced from 20 seconds

# Analyst (Trending/Surge) - MUCH MORE AGGRESSIVE
ANALYST_BUY_AMOUNT = 0.08  # Increased from 0.05
ANALYST_MIN_LIQ = 5  # Lowered from 8
ANALYST_TP_LEVEL_1_PRICE_MULT = 1.8  # Lowered from 2.0 (80% rise)
ANALYST_TP_LEVEL_1_SELL_PCT = 70   # Reduced from 80% for faster profit taking
ANALYST_SL_X = 0.75  # Increased from 0.7
ANALYST_TRAIL = 0.10  # Reduced from 0.15 for tighter trailing
ANALYST_MAX_POOLAGE = 60 * 60  # Increased from 30 minutes to 1 hour
ANALYST_MIN_ML_SCORE = 55  # Lowered from 65

# Whale Tracker (Community) - MORE AGGRESSIVE
COMMUNITY_BUY_AMOUNT = 0.08  # Increased from 0.05
COMM_HOLDER_THRESHOLD = 50  # Lowered from 100
COMM_MAX_CONC = 0.20  # Increased from 0.15
COMM_TP_LEVELS = [1.5, 3.0, 6.0]  # Lowered targets for faster exits
COMM_SL_PCT = 0.7  # Increased from 0.6
COMM_HOLD_SECONDS = 1800  # Reduced from 3600 (30 minutes)
COMM_MIN_SIGNALS = 1  # Reduced from 2

# Watcher Strategy - MORE AGGRESSIVE
WATCH_DURATION_SECONDS = 180  # Reduced from 300 (3 minutes)
MARKET_CAP_RISE_THRESHOLD = 1.3  # Lowered from 1.5 (30% rise)
WATCHLIST_POLL_INTERVAL = 10  # Reduced from 20 seconds

# Risk Management - MORE AGGRESSIVE
MAX_WALLET_EXPOSURE = 0.7  # Increased from 0.5
DAILY_LOSS_LIMIT_PERCENT = 1.0  # Increased from 0.5
ANTI_SNIPE_DELAY = 1  # Reduced from 2

# ToxiBot specific
TOXIBOT_COMMAND_DELAY = 1  # Reduced from 2

# Performance settings - MORE AGGRESSIVE
ULTRA_MAX_DAILY_TRADES = 30  # Increased from 20
ANALYST_MAX_POSITIONS = 30  # Increased from 20
COMMUNITY_MAX_DAILY = 20  # Increased from 10

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

# === SOLSCAN.IO WHALE MONITORING ===
SOLSCAN_API_BASE = "https://api.solscan.io"
WHALE_MIN_BALANCE = 1000  # Minimum SOL balance to be considered a whale
WHALE_MIN_TRANSACTION_VALUE = 50  # Minimum USD value for whale transaction

# === ML SCORING WEIGHTS ===
ML_SCORE_WEIGHTS = {
    'liquidity': 0.20,
    'volume_momentum': 0.25,
    'price_momentum': 0.20,
    'holder_distribution': 0.15,
    'age_factor': 0.10,
    'rug_risk': 0.10
}

# Configure stdout/stderr for Railway
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Initialize Flask app for web dashboard
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('pages/dashboard.html')

@app.route('/api/dashboard-data')
def api_dashboard_data():
    # Return mock data for now - will be connected to real data
    return jsonify({
        'current_price': 150.25,
        'balance': 1000.50,
        'bot_status': 'active',
        'recent_trades': []
    })

@socketio.on('start_bot')
def handle_start_bot():
    # Add bot start logic here
    emit('bot_started', {'status': 'Bot started'})

@socketio.on('stop_bot')
def handle_stop_bot():
    # Add bot stop logic here
    emit('bot_stopped', {'status': 'Bot stopped'})

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

# Pump.fun monitoring state
pump_fun_monitoring: Dict[str, Dict[str, Any]] = {}

# Market sentiment tracking
market_sentiment = {
    'recent_performance': deque(maxlen=50),
    'avg_win_rate': 0.5,
    'bull_market': True,
    'volatility_index': 1.0
}

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
    
async def axiom_trending_monitor(callback):
    """Polls axiom.trade/discover to find newly surging tokens by scraping the page."""
    seen_axiom_tokens = collections.deque(maxlen=500)
    # --- UPDATED URL ---
    url = "https://axiom.trade/discover"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    logger.info("📈 Starting Axiom trending monitor for axiom.trade/discover...")
    
    while True:
        try:
            async with get_session() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"Axiom scraper failed with status: {resp.status}")
                        await asyncio.sleep(120)
                        continue
                        
                    html_content = await resp.text()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # --- NEW SCRAPING LOGIC FOR AXIOM.TRADE ---
                    # NOTE: These selectors are based on the typical structure of modern data tables.
                    # They might need to be adjusted if the site's code is unusual.
                    
                    # Find all links that contain a Solana token address
                    token_links = soup.find_all('a', href=lambda href: href and '/token/SOL/' in href)

                    for link in token_links:
                        try:
                            token_address = link['href'].split('/token/SOL/')[1].split('?')[0]
                            if not token_address or token_address in seen_axiom_tokens:
                                continue

                            # Find the parent container of the entire row of data
                            parent_row = link.find_parent(class_=lambda c: c and 'MuiDataGrid-row' in c)
                            if not parent_row: continue
                            
                            # The 5M change is usually the 4th data cell ('data-colindex="3"')
                            price_5m_cell = parent_row.select_one('[data-colindex="3"] p')
                            if not price_5m_cell: continue

                            price_5m_change_text = price_5m_cell.text.strip().replace('%', '').replace('−', '-')
                            price_5m_change = float(price_5m_change_text)

                            # --- THE SURGE FILTER ---
                            if price_5m_change > 25:
                                seen_axiom_tokens.append(token_address)
                                
                                # Get the token name from the same row
                                name_cell = parent_row.select_one('[data-colindex="0"] p')
                                token_name = name_cell.text if name_cell else "Unknown"

                                logger.info(f"🔥 Axiom SURGE detected: {token_name} ({token_address[:8]}) | 5M Change: +{price_5m_change:.2f}%")
                                activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔥 Axiom Surge: {token_name} (+{price_5m_change:.0f}%)")
                                
                                await callback(token_address, "axiom_trending")

                        except (ValueError, IndexError, TypeError, AttributeError):
                            continue # Ignore rows that don't match the expected format
                            
        except Exception as e:
            logger.error(f"Error in axiom_trending_monitor: {e}")
        
        await asyncio.sleep(60)
    
async def ultra_early_handler(token, toxibot_client):
    """
    Performs initial check on new tokens and adds them to the watchlist if they pass.
    """
    # NEW: Log that we are checking this token
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🧐 Checking [Ultra]: {token[:8]}...")

    if token in watchlist or token in positions:
        return # Already watching or own this token

    # 1. Enhanced Rugcheck with detailed logging
    rug_results = await enhanced_rugcheck(token)
    rug_status = rug_results["recommendation"]
    rug_score = rug_results["overall_score"]
    
    # Log detailed rug check results
    if rug_status == "SAFE":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ RUG CHECK PASSED: {token[:8]} (Score: {rug_score}/100)")
    elif rug_status == "CAUTION":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ RUG CHECK CAUTION: {token[:8]} (Score: {rug_score}/100)")
    else:  # RISKY
        risks = ", ".join(rug_results["risks"][:3])
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ RUG CHECK FAILED: {token[:8]} (Score: {rug_score}/100) - {risks}")
        return  # Don't proceed with risky tokens

    # 2. Get Initial Market Cap
    initial_mcap = await fetch_market_cap(token)
    if not initial_mcap or initial_mcap == 0:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Watchlist reject: {token[:8]} (no mcap)")
        return
        
    # 3. Add to Watchlist
    watchlist[token] = {
        "start_time": time.time(),
        "initial_mcap": initial_mcap,
        "rug_score": rug_score,
        "rug_status": rug_status
    }
    logger.info(f"🔎 Added {token[:8]} to watchlist with initial MCAP: ${initial_mcap:,.0f} (Rug Score: {rug_score}/100)")
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔎 Watching {token[:8]} (MCAP: ${initial_mcap:,.0f}, Rug Score: {rug_score}/100)")
    
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

# === ENHANCED RUG CHECKING WITH MULTIPLE APIS ===
async def enhanced_rugcheck(token_addr: str) -> Dict[str, Any]:
    """Enhanced rug checking using multiple APIs for better accuracy."""
    results = {
        "rugcheck_xyz": {},
        "dexscreener": {},
        "solscan": {},
        "overall_score": 0,
        "risks": [],
        "recommendation": "UNKNOWN"
    }
    
    # 1. Rugcheck.xyz (existing)
    try:
        async with get_session() as session:
            async with session.get(f"https://api.rugcheck.xyz/api/check/{token_addr}") as resp:
                if resp.status == 200:
                    results["rugcheck_xyz"] = await resp.json()
    except Exception as e:
        logger.error(f"Rugcheck.xyz error: {e}")
    
    # 2. DexScreener liquidity analysis
    try:
        async with get_session() as session:
            async with session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("pairs"):
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                liquidity = float(pair.get("liquidity", {}).get("usd", 0))
                                results["dexscreener"] = {
                                    "liquidity": liquidity,
                                    "price": float(pair.get("priceUsd", 0)),
                                    "volume_24h": float(pair.get("volume", {}).get("h24", 0))
                                }
                                break
    except Exception as e:
        logger.error(f"DexScreener rug check error: {e}")
    
    # 3. Solscan.io token analysis
    try:
        token_info = await fetch_solscan_token_info(token_addr)
        if token_info:
            results["solscan"] = {
                "holder_count": token_info.get("holder", 0),
                "supply": token_info.get("supply", 0),
                "decimals": token_info.get("decimals", 0)
            }
    except Exception as e:
        logger.error(f"Solscan rug check error: {e}")
    
    # Calculate overall score and recommendation
    score = 50  # Start with neutral score
    
    # Rugcheck.xyz analysis
    if results["rugcheck_xyz"].get("risks"):
        for risk in results["rugcheck_xyz"]["risks"]:
            if risk.get("level") == "danger":
                score -= 30
                results["risks"].append(f"Rugcheck: {risk.get('name')}")
            elif risk.get("level") == "warning":
                score -= 15
                results["risks"].append(f"Rugcheck: {risk.get('name')}")
    
    # Liquidity analysis
    liquidity = results["dexscreener"].get("liquidity", 0)
    if liquidity < 5000:
        score -= 20
        results["risks"].append("Low liquidity (<$5k)")
    elif liquidity < 10000:
        score -= 10
        results["risks"].append("Moderate liquidity (<$10k)")
    
    # Holder analysis
    holder_count = results["solscan"].get("holder_count", 0)
    if holder_count < 50:
        score -= 15
        results["risks"].append("Low holder count")
    
    # Volume analysis
    volume_24h = results["dexscreener"].get("volume_24h", 0)
    if volume_24h < 1000:
        score -= 10
        results["risks"].append("Low 24h volume")
    
    # Set recommendation
    if score >= 70:
        results["recommendation"] = "SAFE"
    elif score >= 40:
        results["recommendation"] = "CAUTION"
    else:
        results["recommendation"] = "RISKY"
    
    results["overall_score"] = max(0, min(100, score))
    
    return results

async def update_market_sentiment():
    """Update market sentiment based on recent performance."""
    while True:
        try:
            if len(market_sentiment['recent_performance']) >= 10:
                # Calculate average win rate
                wins = sum(1 for p in market_sentiment['recent_performance'] if p > 0)
                market_sentiment['avg_win_rate'] = wins / len(market_sentiment['recent_performance'])
                
                # Determine market condition
                avg_performance = statistics.mean(market_sentiment['recent_performance'])
                market_sentiment['bull_market'] = avg_performance > 0.1  # 10% average profit
                
                # Calculate volatility
                if len(market_sentiment['recent_performance']) >= 5:
                    market_sentiment['volatility_index'] = statistics.stdev(market_sentiment['recent_performance'])
                
                logger.info(f"Market sentiment updated: Bull={market_sentiment['bull_market']}, Win rate={market_sentiment['avg_win_rate']:.2f}, Volatility={market_sentiment['volatility_index']:.4f}")
            
        except Exception as e:
            logger.error(f"Market sentiment update error: {e}")
        
        await asyncio.sleep(300)  # Update every 5 minutes

def enhanced_rug_gate(rug_results: Dict[str, Any]) -> Optional[str]:
    """Enhanced rug gate with detailed analysis."""
    if rug_results["recommendation"] == "RISKY":
        risks = ", ".join(rug_results["risks"][:3])  # Show top 3 risks
        return f"Rug check failed: {risks}"
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
                async with get_session() as session, session.get(url) as resp:
                    if resp.status == 200:
                        for tx in await resp.json():
                            if time.time() - tx.get("timestamp", 0) > 300: continue
                            for transfer in tx.get("tokenTransfers", []):
                                if transfer.get("toUserAccount") == whale:
                                    token = transfer.get("mint")
                                    if token and token != "So11111111111111111111111111111111111111112":
                                        logger.info(f"🐋 Whale {whale[:6]}... bought {token[:6]}...")
                                        # NEW: Log whale buys to the dashboard activity log
                                        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🐋 Whale {whale[:6]} bought {token[:8]}...")
                                        await community_token_queue.put(token)
                    elif resp.status == 400:
                        logger.error(f"Whale monitoring HTTP error for {whale[:6]}: Status=400. Check if this is a valid Solana address.")
                    else:
                        logger.warning(f"Whale monitoring HTTP warning for {whale[:6]}: Status={resp.status}")

            except Exception as e:
                logger.error(f"Whale monitoring exception for {whale[:6]}: {e}"); trip_circuit_breaker("helius_whale")
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

# === ENHANCED WHALE MONITORING WITH SOLSCAN.IO ===
async def fetch_solscan_whale_transactions(whale_address: str) -> List[Dict[str, Any]]:
    """Fetch recent transactions from Solscan.io for whale monitoring."""
    if is_circuit_breaker("solscan"): return []
    try:
        async with get_session() as session:
            # Get recent transactions
            url = f"{SOLSCAN_API_BASE}/account/transactions"
            params = {
                "address": whale_address,
                "limit": 20,
                "offset": 0
            }
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
    except Exception as e:
        logger.error(f"Solscan whale transaction error: {e}")
        trip_circuit_breaker("solscan")
    return []

async def fetch_solscan_token_info(token_address: str) -> Optional[Dict[str, Any]]:
    """Fetch token information from Solscan.io."""
    if is_circuit_breaker("solscan"): return None
    try:
        async with get_session() as session:
            url = f"{SOLSCAN_API_BASE}/token/meta"
            params = {"tokenAddress": token_address}
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Solscan token info error: {e}")
        trip_circuit_breaker("solscan")
    return None

async def enhanced_whale_monitoring():
    """Enhanced whale monitoring using both Helius and Solscan.io APIs."""
    if not WHALE_WALLETS: 
        return logger.warning("Whale monitoring disabled - no whale wallets configured.")
    
    logger.info(f"🐋 Starting enhanced whale monitoring for {len(WHALE_WALLETS)} wallets...")
    whale_transaction_cache = {}  # Cache to avoid duplicate processing
    
    while True:
        for whale in WHALE_WALLETS:
            try:
                # Get transactions from both APIs for redundancy
                transactions = []
                
                # Helius API (existing)
                if HELIUS_API_KEY and not is_circuit_breaker("helius_whale"):
                    try:
                        url = f"https://api.helius.xyz/v0/addresses/{whale}/transactions?api-key={HELIUS_API_KEY}&limit=10&type=SWAP"
                        async with get_session() as session:
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    transactions.extend(await resp.json())
                    except Exception as e:
                        logger.error(f"Helius whale monitoring error: {e}")
                        trip_circuit_breaker("helius_whale")
                
                # Solscan.io API (new)
                solscan_txs = await fetch_solscan_whale_transactions(whale)
                transactions.extend(solscan_txs)
                
                # Process transactions
                for tx in transactions:
                    tx_hash = tx.get("signature") or tx.get("txHash")
                    if not tx_hash or tx_hash in whale_transaction_cache:
                        continue
                    
                    whale_transaction_cache[tx_hash] = time.time()
                    
                    # Extract token purchases
                    token_transfers = tx.get("tokenTransfers", [])
                    if not token_transfers:
                        # Try alternative field names
                        token_transfers = tx.get("transfers", [])
                    
                    for transfer in token_transfers:
                        if transfer.get("toUserAccount") == whale or transfer.get("to") == whale:
                            token = transfer.get("mint") or transfer.get("token")
                            if token and token != "So11111111111111111111111111111111111111112":
                                # Get transaction value
                                amount_usd = transfer.get("amountUsd", 0)
                                if amount_usd and amount_usd < WHALE_MIN_TRANSACTION_VALUE:
                                    continue
                                
                                # Get token info
                                token_info = await fetch_solscan_token_info(token)
                                token_symbol = token_info.get("symbol", "Unknown") if token_info else "Unknown"
                                
                                logger.info(f"🐋 Whale {whale[:6]}... bought {token_symbol} ({token[:8]}) - ${amount_usd:.2f}")
                                activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🐋 Whale {whale[:6]} bought {token_symbol} ({token[:8]}) - ${amount_usd:.2f}")
                                
                                # Add to community queue for analysis
                                await community_token_queue.put(token)
                
                # Clean old cache entries (older than 1 hour)
                current_time = time.time()
                whale_transaction_cache = {k: v for k, v in whale_transaction_cache.items() 
                                        if current_time - v < 3600}
                
            except Exception as e:
                logger.error(f"Enhanced whale monitoring error for {whale[:6]}: {e}")
        
        await asyncio.sleep(30)  # Check every 30 seconds

# =====================================
# ML Scoring & Trading Logic
# =====================================
async def ml_score_token(meta: Dict[str, Any]) -> float:
    """Legacy ML scoring - kept for backward compatibility."""
    score = 50.0
    liq = meta.get("liq", 0)
    if liq > 50: score += 20
    elif liq > 10: score += 10
    vol_1h = meta.get('vol_1h', 0); vol_6h = meta.get('vol_6h', 0)
    if vol_6h > 0 and vol_1h > (vol_6h / 6 * 1.5): score += 15
    if meta.get('age', 9999) < 300: score += 10
    return min(95, max(5, score))

async def advanced_ml_score_token(token: str, meta: Dict[str, Any], rug_results: Dict[str, Any]) -> Dict[str, Any]:
    """Advanced ML scoring with multiple factors and market sentiment."""
    score_components = {}
    
    # 1. Liquidity Analysis (20% weight) - MORE AGGRESSIVE
    liq = meta.get("liq", 0)
    if liq > 50: score_components['liquidity'] = 95  # Lowered from 100
    elif liq > 20: score_components['liquidity'] = 85  # Lowered from 50
    elif liq > 10: score_components['liquidity'] = 70  # Lowered from 20
    elif liq > 5: score_components['liquidity'] = 50  # Lowered from 10
    else: score_components['liquidity'] = 30  # Increased from 20
    
    # 2. Volume Momentum (25% weight) - MORE AGGRESSIVE
    vol_1h = meta.get('vol_1h', 0)
    vol_6h = meta.get('vol_6h', 0)
    if vol_6h > 0:
        momentum_ratio = vol_1h / (vol_6h / 6)
        if momentum_ratio > 2: score_components['volume_momentum'] = 95  # Lowered from 3
        elif momentum_ratio > 1.5: score_components['volume_momentum'] = 80  # Lowered from 2
        elif momentum_ratio > 1.2: score_components['volume_momentum'] = 65  # Lowered from 1.5
        else: score_components['volume_momentum'] = 45  # Increased from 40
    else:
        score_components['volume_momentum'] = 35  # Increased from 30
    
    # 3. Price Momentum (20% weight) - MORE AGGRESSIVE
    price_change_5m = meta.get('price_change_5m', 0)
    if price_change_5m > 30: score_components['price_momentum'] = 95  # Lowered from 50
    elif price_change_5m > 20: score_components['price_momentum'] = 80  # Lowered from 30
    elif price_change_5m > 10: score_components['price_momentum'] = 65  # Lowered from 15
    elif price_change_5m > 3: score_components['price_momentum'] = 50  # Lowered from 5
    else: score_components['price_momentum'] = 35  # Increased from 30
    
    # 4. Holder Distribution (15% weight) - MORE AGGRESSIVE
    holder_count = rug_results.get("solscan", {}).get("holder_count", 0)
    if holder_count > 200: score_components['holder_distribution'] = 95  # Lowered from 500
    elif holder_count > 100: score_components['holder_distribution'] = 80  # Lowered from 200
    elif holder_count > 50: score_components['holder_distribution'] = 65  # Lowered from 100
    elif holder_count > 25: score_components['holder_distribution'] = 50  # Lowered from 50
    else: score_components['holder_distribution'] = 35  # Increased from 30
    
    # 5. Age Factor (10% weight) - MORE AGGRESSIVE
    age = meta.get('age', 9999)
    if age < 600: score_components['age_factor'] = 90  # Increased from 300 (10 minutes)
    elif age < 3600: score_components['age_factor'] = 75  # Increased from 1800 (1 hour)
    elif age < 7200: score_components['age_factor'] = 60  # Increased from 3600 (2 hours)
    else: score_components['age_factor'] = 45  # Increased from 40
    
    # 6. Rug Risk (15% weight) - Inverse scoring
    rug_score = rug_results.get("overall_score", 50)
    score_components['rug_risk'] = rug_score  # Higher rug score = lower risk
    
    # Calculate weighted score
    total_score = 0
    for component, weight in ML_SCORE_WEIGHTS.items():
        if component in score_components:
            total_score += score_components[component] * weight
    
    # Market sentiment adjustment
    if market_sentiment['bull_market']:
        total_score *= 1.1  # 10% boost in bull market
    elif market_sentiment['avg_win_rate'] < 0.4:
        total_score *= 0.9  # 10% reduction in bear market
    
    # Volatility adjustment
    total_score *= market_sentiment['volatility_index']
    
    return {
        'overall_score': min(95, max(5, total_score)),
        'components': score_components,
        'market_adjustment': {
            'bull_market': market_sentiment['bull_market'],
            'win_rate': market_sentiment['avg_win_rate'],
            'volatility': market_sentiment['volatility_index']
        }
    }

async def calculate_position_size(bot_type: str, ml_score: float) -> float:
    global exposure, current_wallet_balance
    if not trading_enabled: return 0
    available_capital = (current_wallet_balance * MAX_WALLET_EXPOSURE) - exposure
    if available_capital <= 0.01: return 0
    base = ANALYST_BUY_AMOUNT if bot_type == "analyst" else ULTRA_BUY_AMOUNT
    # MORE AGGRESSIVE: Lower minimum score requirement and higher multiplier
    ml_multiplier = 0.6 + ((ml_score - 40) / 80)  # Changed from 0.75 + ((ml_score - 50) / 100)
    return min(base * ml_multiplier, available_capital, 0.15)  # Increased max from 0.1 to 0.15

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

    # 1. Enhanced Rugcheck with detailed logging
    rug_results = await enhanced_rugcheck(token)
    rug_status = rug_results["recommendation"]
    rug_score = rug_results["overall_score"]
    
    # Log detailed rug check results
    if rug_status == "SAFE":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ RUG CHECK PASSED: {token[:8]} (Score: {rug_score}/100)")
    elif rug_status == "CAUTION":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ RUG CHECK CAUTION: {token[:8]} (Score: {rug_score}/100)")
    else:  # RISKY
        risks = ", ".join(rug_results["risks"][:3])
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ RUG CHECK FAILED: {token[:8]} (Score: {rug_score}/100) - {risks}")
        return  # Don't proceed with risky tokens

    # 2. Get Initial Market Cap
    initial_mcap = await fetch_market_cap(token)
    if not initial_mcap or initial_mcap == 0:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Watchlist reject: {token[:8]} (no mcap)")
        return
        
    # 3. Add to Watchlist
    watchlist[token] = {
        "start_time": time.time(),
        "initial_mcap": initial_mcap,
        "rug_score": rug_score,
        "rug_status": rug_status
    }
    logger.info(f"🔎 Added {token[:8]} to watchlist with initial MCAP: ${initial_mcap:,.0f} (Rug Score: {rug_score}/100)")
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔎 Watching {token[:8]} (MCAP: ${initial_mcap:,.0f}, Rug Score: {rug_score}/100)")

async def analyst_handler(token, src, toxibot_client):
    global analyst_total, exposure

    # NEW: Log that we are checking this token
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🧐 Checking [Analyst]: {token[:8]}...")

    if not trading_enabled or len([p for p in positions.values() if 'pump' not in p.get('src','')]) >= ANALYST_MAX_POSITIONS or token in positions: return
    
    # Enhanced rug check
    rug_results = await enhanced_rugcheck(token)
    if enhanced_rug_gate(rug_results): 
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Analyst reject: {token[:8]} (rug check failed)")
        return

    stats = await fetch_volumes(token); age = await fetch_pool_age(token)
    if not stats or age is None or stats['liq'] < ANALYST_MIN_LIQ or age > ANALYST_MAX_POOLAGE: return
    
    # Use advanced ML scoring with rug results
    ml_results = await advanced_ml_score_token(token, {'liq': stats['liq'], 'age': age, 'vol_1h': stats['vol_1h'], 'vol_6h': stats['vol_6h']}, rug_results)
    ml_score = ml_results['overall_score']
    if ml_score < ANALYST_MIN_ML_SCORE: return
    
    size = await calculate_position_size("analyst", ml_score)
    if size > 0 and await toxibot_client.send_buy(token, size):
        price = await fetch_token_price(token) or 1e-9; analyst_total += 1; exposure += size * price
        positions[token] = {"src": src, "buy_time": time.time(), "size": size, "entry_price": price, "total_sold_percent": 0, "local_high": price}
        save_position(token, positions[token]); record_trade(token, "BUY", size, price)
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ BUY {token[:8]} @ ${price:.6f} (Analyst) - Rug Score: {rug_results['overall_score']}/100")

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
    elif src in ("bitquery", "dexscreener_trending", "community", "watchlist_hit", "axiom_trending"):
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
        
        # Update market sentiment with trade performance
        market_sentiment['recent_performance'].append(pl)
        
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

# === PUMP.FUN TOKEN MONITORING ===
PUMP_FUN_MONITOR_DURATION = 3600  # 1 hour monitoring
PUMP_FUN_UPDATE_INTERVAL = 30  # 30-second updates
PUMP_FUN_MC_SPIKE_THRESHOLD = 2.0  # 2x market cap spike for profit taking

async def pump_fun_token_monitor():
    """Monitor new Pump.fun tokens with immediate rug checking and MC spike detection."""
    monitored_tokens = {}  # token_address -> monitoring_data
    
    logger.info("🎯 Starting Pump.fun token monitor with enhanced rug checking...")
    
    while True:
        try:
            # Get new tokens from PumpPortal feed
            # This would integrate with your existing pumpportal_newtoken_feed
            # For now, we'll simulate the monitoring logic
            
            # Check monitored tokens for MC spikes
            current_time = time.time()
            tokens_to_remove = []
            
            for token_addr, monitor_data in monitored_tokens.items():
                elapsed_time = current_time - monitor_data["start_time"]
                
                # Stop monitoring after 1 hour
                if elapsed_time > PUMP_FUN_MONITOR_DURATION:
                    logger.info(f"⏰ Stopped monitoring {token_addr[:8]} (1 hour elapsed)")
                    tokens_to_remove.append(token_addr)
                    continue
                
                # Check for MC spike every 30 seconds
                if elapsed_time % PUMP_FUN_UPDATE_INTERVAL < 1:  # Every 30 seconds
                    current_mcap = await fetch_market_cap(token_addr)
                    if current_mcap and monitor_data["initial_mcap"]:
                        mcap_ratio = current_mcap / monitor_data["initial_mcap"]
                        
                        if mcap_ratio >= PUMP_FUN_MC_SPIKE_THRESHOLD:
                            # MASSIVE MC SPIKE DETECTED!
                            logger.info(f"🚀 MASSIVE MC SPIKE! {token_addr[:8]} surged {mcap_ratio:.2f}x!")
                            activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 MC SPIKE: {token_addr[:8]} {mcap_ratio:.2f}x (${monitor_data['initial_mcap']:,.0f} → ${current_mcap:,.0f})")
                            
                            # Trigger immediate profit taking
                            await process_token(token_addr, "pump_fun_spike")
                            tokens_to_remove.append(token_addr)
                        else:
                            # Log progress
                            if mcap_ratio > 1.5:  # Significant but not spike level
                                activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 📈 {token_addr[:8]} MC: {mcap_ratio:.2f}x (${current_mcap:,.0f})")
            
            # Remove finished tokens
            for token in tokens_to_remove:
                del monitored_tokens[token]
            
        except Exception as e:
            logger.error(f"Pump.fun monitor error: {e}")
        
        await asyncio.sleep(1)  # Check every second

async def process_pump_fun_token(token_addr: str):
    """Process new Pump.fun token with immediate rug checking."""
    logger.info(f"🎯 Processing new Pump.fun token: {token_addr[:8]}")
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 New Pump.fun token: {token_addr[:8]}")
    
    # IMMEDIATE RUG CHECK
    rug_results = await enhanced_rugcheck(token_addr)
    rug_status = rug_results["recommendation"]
    rug_score = rug_results["overall_score"]
    
    # Log rug check result immediately
    if rug_status == "SAFE":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ RUG CHECK PASSED: {token_addr[:8]} (Score: {rug_score}/100)")
        logger.info(f"✅ Rug check PASSED for {token_addr[:8]} (Score: {rug_score}/100)")
    elif rug_status == "CAUTION":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ RUG CHECK CAUTION: {token_addr[:8]} (Score: {rug_score}/100)")
        logger.info(f"⚠️ Rug check CAUTION for {token_addr[:8]} (Score: {rug_score}/100)")
    else:  # RISKY
        risks = ", ".join(rug_results["risks"][:3])
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ RUG CHECK FAILED: {token_addr[:8]} (Score: {rug_score}/100) - {risks}")
        logger.info(f"❌ Rug check FAILED for {token_addr[:8]} (Score: {rug_score}/100) - {risks}")
        return  # Don't proceed with risky tokens
    
    # Get initial market cap
    initial_mcap = await fetch_market_cap(token_addr)
    if not initial_mcap:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ No market cap data for {token_addr[:8]}")
        return
    
    # Add to monitoring if passed rug check
    monitored_tokens[token_addr] = {
        "start_time": time.time(),
        "initial_mcap": initial_mcap,
        "rug_score": rug_score,
        "rug_status": rug_status
    }
    
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Monitoring {token_addr[:8]} for MC spikes (Initial: ${initial_mcap:,.0f})")
    logger.info(f"🔍 Added {token_addr[:8]} to Pump.fun monitoring (MC: ${initial_mcap:,.0f})")

# =====================================
# Dashboard and Server
# =====================================
async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    while True:
        try:
            # --- Fetch recent trade history for the new panel ---
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row # Allows accessing columns by name
            cursor = conn.cursor()
            
            # --- QUERY IS CORRECTED HERE ---
            cursor.execute("""
                SELECT 
                    t.timestamp, 
                    p.data, 
                    t.action, 
                    t.size, 
                    t.pl,
                    t.token -- ADDED the missing token column
                FROM trades t
                LEFT JOIN positions p ON t.token = p.token -- CHANGED to LEFT JOIN for robustness
                ORDER BY t.timestamp DESC
                LIMIT 30;
            """)
            trade_history_rows = cursor.fetchall()
            conn.close()

            # Format trade history for sending
            trade_history = []
            for row in trade_history_rows:
                # Use a try-except block for extra safety with potentially missing data
                try:
                    pos_data = json.loads(row['data']) if row['data'] else {}
                    token_address = row['token']
                    trade_history.append({
                        "timestamp": row['timestamp'],
                        "token": pos_data.get('symbol', token_address[:8]),
                        "token_address": token_address,
                        "bot_source": pos_data.get('src', 'Unknown'),
                        "action": row['action'],
                        "size": row['size'],
                        "pl": row['pl']
                    })
                except Exception as e:
                    logger.error(f"Error processing trade history row: {e}")

            total_pl = ultra_pl + analyst_pl + community_pl
            total_trades = ultra_total + analyst_total + community_total
            total_wins = ultra_wins + analyst_wins + community_wins
            winrate = (total_wins / total_trades * 100) if total_trades > 0 else 0
            
            data = {
                "wallet_balance": current_wallet_balance,
                "pl": total_pl,
                "winrate": winrate,
                "exposure": exposure,
                "log": list(activity_log),
                "tokens_checked": tokens_checked_count,
                "trading_enabled": trading_enabled,
                "watcher_stats": {"watching": len(watchlist), "processed": watcher_processed_today, "hits": watcher_hits_today},
                "analyst_stats": {"trades": analyst_total, "wins": analyst_wins, "pl": analyst_pl},
                "community_stats": {"trades": community_total, "wins": community_wins, "pl": community_pl},
                "trade_history": trade_history
            }
            await ws.send_str(json.dumps(data, default=str))
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"WS send error: {e}"); break
    return ws

async def run_server():
    app = web.Application()
    app.router.add_get('/ws', ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"WebSocket server up at ws://0.0.0.0:{PORT}/ws")
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
        enhanced_whale_monitoring(),  # Use enhanced whale monitoring
        community_trade_manager(toxibot),
        monitor_watchlist(),
        axiom_trending_monitor(feed_callback),
        pump_fun_token_monitor(), # Add the new pump.fun monitor task
        update_market_sentiment(), # Add market sentiment updates
    ]
    if BITQUERY_API_KEY and BITQUERY_API_KEY != "disabled":
        tasks.append(bitquery_streaming_feed(feed_callback))
    
    await asyncio.gather(*tasks)

def run_flask():
    """Run Flask server in a separate thread"""
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)

async def main():
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run the existing aiohttp server and bot
    await asyncio.gather(run_server(), bot_main())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Top-level error: {e}"); traceback.print_exc()

# === ENHANCED DASHBOARD LOGGING ===
def log_rug_check_result(token: str, rug_results: Dict[str, Any], source: str):
    """Log detailed rug check results to dashboard."""
    rug_status = rug_results["recommendation"]
    rug_score = rug_results["overall_score"]
    
    if rug_status == "SAFE":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {source} RUG CHECK PASSED: {token[:8]} (Score: {rug_score}/100)")
    elif rug_status == "CAUTION":
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ {source} RUG CHECK CAUTION: {token[:8]} (Score: {rug_score}/100)")
    else:  # RISKY
        risks = ", ".join(rug_results["risks"][:3])
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ {source} RUG CHECK FAILED: {token[:8]} (Score: {rug_score}/100) - {risks}")

def log_whale_activity(whale_address: str, token_symbol: str, token_address: str, amount_usd: float):
    """Log whale activity to dashboard."""
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🐋 Whale {whale_address[:6]} bought {token_symbol} ({token_address[:8]}) - ${amount_usd:.2f}")

def log_mc_spike(token_address: str, initial_mcap: float, current_mcap: float, ratio: float):
    """Log market cap spike to dashboard."""
    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 MC SPIKE: {token_address[:8]} {ratio:.2f}x (${initial_mcap:,.0f} → ${current_mcap:,.0f})")




