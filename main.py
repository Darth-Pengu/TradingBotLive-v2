#!/usr/bin/env python3

import os
import sys
import asyncio
import logging
import json
import time
import random
import aiohttp
import websockets
import collections
import sqlite3
import traceback
from telethon import TelegramClient
from telethon.sessions import StringSession
from aiohttp import web
from typing import Set, Dict, Any, Optional, List, Tuple
from functools import lru_cache
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# === PARAMETERS TO EDIT ===
# Speed Demon (Ultra-Early) - Updated per documentation
ULTRA_MIN_LIQ = 5  # Reduced from 8
ULTRA_BUY_AMOUNT = 0.05  # Reduced from 0.07
ULTRA_TP_X = 3.0  # Increased from 2.0
ULTRA_SL_X = 0.5  # More aggressive from 0.7
ULTRA_MIN_RISES = 2
ULTRA_AGE_MAX_S = 300  # Increased from 120 to 5 minutes
ULTRA_MIN_ML_SCORE = 65  # New parameter

# Analyst (Scalper) - Updated per documentation
SCALPER_BUY_AMOUNT = 0.05  # Reduced from 0.10
SCALPER_MIN_LIQ = 10  # Increased from 8
SCALPER_TP_LEVELS = [1.5, 2.5, 5.0]  # Multiple TP levels
SCALPER_SL_X = 0.7
SCALPER_TRAIL = 0.15  # Tighter from 0.2
SCALPER_MAX_POOLAGE = 30 * 60  # 30 minutes
SCALPER_MIN_ML_SCORE = 70

# Whale Tracker (Community) - Updated per documentation
COMMUNITY_BUY_AMOUNT = 0.05  # Increased from 0.04
COMM_HOLDER_THRESHOLD = 100  # Reduced from 250
COMM_MAX_CONC = 0.15  # From 0.10
COMM_TP_LEVELS = [2.0, 5.0, 10.0]  # Multiple levels
COMM_SL_PCT = 0.6
COMM_TRAIL = 0.25  # From 0.4
COMM_HOLD_SECONDS = 3600  # 1 hour minimum
COMM_MIN_SIGNALS = 2

# Risk Management - Critical for live trading
MAX_WALLET_EXPOSURE = 0.5  # 50% max exposure
DAILY_LOSS_LIMIT_PERCENT = 0.5  # 50% daily loss limit
ANTI_SNIPE_DELAY = 2
ML_MIN_SCORE = 60  # Will be overridden by bot-specific scores

# ToxiBot specific
TOXIBOT_COMMAND_DELAY = 2  # Delay between commands

# Performance settings
CACHE_TTL = 5  # seconds
MAX_CONCURRENT_REQUESTS = 10
API_RETRY_COUNT = 3
API_RETRY_DELAY = 1
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT = 60

# === ENV VARS ===
TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]
TELEGRAM_STRING_SESSION = os.environ["TELEGRAM_STRING_SESSION"]
TOXIBOT_USERNAME = os.environ.get("TOXIBOT_USERNAME", "@toxi_solana_bot")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
HELIUS_RPC_URL = os.environ.get("HELIUS_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=0f2e5160-d95a-46d7-a0c4-9a71484ab3d8")
HELIUS_WS_URL = os.environ.get("HELIUS_WS_URL", "wss://mainnet.helius-rpc.com/?api-key=0f2e5160-d95a-46d7-a0c4-9a71484ab3d8")
WALLET_ADDRESS = os.environ.get("WALLET_ADDRESS", "")
BITQUERY_API_KEY = os.environ.get("BITQUERY_API_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))

# Configure logging
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Database configuration - use volume for Railway
if os.environ.get('RAILWAY_ENVIRONMENT'):
    DB_PATH = '/data/toxibot.db'
    LOG_PATH = '/data/toxibot.log'
else:
    DB_PATH = 'toxibot.db'
    LOG_PATH = 'toxibot.log'

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH)
    ]
)
logger = logging.getLogger("toxibot")

# ---------------------
# GLOBAL STATE & STATS
# ---------------------
blacklisted_tokens: Set[str] = set()
blacklisted_devs: Set[str] = set()
positions: Dict[str, Dict[str, Any]] = {}
activity_log: collections.deque = collections.deque(maxlen=1000)

# Stats tracking
ultra_wins = 0
ultra_total = 0
ultra_pl = 0.0
scalper_wins = 0
scalper_total = 0
scalper_pl = 0.0
community_wins = 0
community_total = 0
community_pl = 0.0

# Performance tracking
api_failures: Dict[str, int] = collections.defaultdict(int)
api_circuit_breakers: Dict[str, float] = {}
price_cache: Dict[str, Tuple[float, float]] = {}
session_pool: Optional[aiohttp.ClientSession] = None

# Community voting
community_signal_votes = collections.defaultdict(lambda: {"sources": set(), "first_seen": time.time()})
community_token_queue = asyncio.Queue()
recent_rugdevs = set()

# Wallet tracking
current_wallet_balance = 0.0
daily_loss = 0.0
exposure = 0.0

# Risk management globals
trading_enabled = True
daily_starting_balance = 0.0
daily_trades_count = 0
consecutive_profitable_trades = 0

# Dynamic trade limits
ULTRA_MAX_DAILY_TRADES = 20
SCALPER_MAX_POSITIONS = 20
COMMUNITY_MAX_DAILY = 10

# =====================================
# Database Functions
# =====================================
def init_database():
    """Initialize SQLite database for position persistence"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Positions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            token TEXT PRIMARY KEY,
            data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Trades history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT,
            action TEXT,
            size REAL,
            price REAL,
            pl REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Blacklist table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            address TEXT PRIMARY KEY,
            type TEXT,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_position(token: str, data: Dict[str, Any]):
    """Save position to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO positions (token, data, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (token, json.dumps(data)))
    conn.commit()
    conn.close()

def load_positions():
    """Load all positions from database"""
    global positions
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT token, data FROM positions')
    for row in cursor.fetchall():
        positions[row[0]] = json.loads(row[1])
    conn.close()
    logger.info(f"Loaded {len(positions)} positions from database")

def record_trade(token: str, action: str, size: float, price: float, pl: float = 0.0):
    """Record trade in history"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (token, action, size, price, pl)
        VALUES (?, ?, ?, ?, ?)
    ''', (token, action, size, price, pl))
    conn.commit()
    conn.close()

# =====================================
# HTTP Session Management
# =====================================
@asynccontextmanager
async def get_session():
    """Get or create aiohttp session with connection pooling"""
    global session_pool
    if session_pool is None or session_pool.closed:
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
        session_pool = aiohttp.ClientSession(timeout=timeout, connector=connector)
    try:
        yield session_pool
    except Exception as e:
        logger.error(f"Session error: {e}")
        raise

# =====================================
# Circuit Breaker Pattern
# =====================================
def is_circuit_broken(service: str) -> bool:
    """Check if circuit breaker is active for a service"""
    if service in api_circuit_breakers:
        if time.time() < api_circuit_breakers[service]:
            return True
        else:
            del api_circuit_breakers[service]
            api_failures[service] = 0
    return False

def trip_circuit_breaker(service: str):
    """Trip the circuit breaker for a service"""
    api_failures[service] += 1
    if api_failures[service] >= CIRCUIT_BREAKER_THRESHOLD:
        api_circuit_breakers[service] = time.time() + CIRCUIT_BREAKER_TIMEOUT
        logger.warning(f"Circuit breaker tripped for {service}")

# =====================================
# Retry Logic
# =====================================
async def retry_with_backoff(func, max_retries=API_RETRY_COUNT):
    """Execute function with exponential backoff retry"""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = API_RETRY_DELAY * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
            await asyncio.sleep(wait_time)

# =====================================
# Cache Management
# =====================================
def get_cached_price(token: str) -> Optional[float]:
    """Get cached price if still valid"""
    if token in price_cache:
        price, timestamp = price_cache[token]
        if time.time() - timestamp < CACHE_TTL:
            return price
    return None

def cache_price(token: str, price: float):
    """Cache token price"""
    price_cache[token] = (price, time.time())

# =====================================
# Helius RPC Functions (Using your paid API)
# =====================================
async def fetch_wallet_balance() -> Optional[float]:
    """Fetch SOL balance using Helius RPC"""
    if not WALLET_ADDRESS or is_circuit_broken("helius"):
        return None
    
    try:
        async with get_session() as session:
            async def _fetch():
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [WALLET_ADDRESS]
                }
                async with session.post(HELIUS_RPC_URL, json=payload) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    data = await resp.json()
                    if "result" in data and "value" in data["result"]:
                        return data["result"]["value"] / 1e9  # Convert lamports to SOL
                    return None
            
            return await retry_with_backoff(_fetch)
    except Exception as e:
        logger.error(f"Failed to fetch wallet balance: {e}")
        trip_circuit_breaker("helius")
        return None

async def monitor_wallet_with_helius():
    """Use Helius to monitor actual on-chain trades"""
    if not HELIUS_API_KEY or not WALLET_ADDRESS:
        return
    
    while True:
        try:
            async with get_session() as session:
                # Get recent transactions
                url = f"https://api.helius.xyz/v0/addresses/{WALLET_ADDRESS}/transactions?api-key={HELIUS_API_KEY}"
                
                async with session.get(url) as resp:
                    if resp.status == 200:
                        txs = await resp.json()
                        
                        for tx in txs:
                            # Check if it's a swap transaction
                            if tx.get("type") == "SWAP":
                                # Extract details
                                token_in = tx.get("tokenInputs", [{}])[0]
                                token_out = tx.get("tokenOutputs", [{}])[0]
                                
                                # Match with our positions
                                for token, pos in positions.items():
                                    if token in [token_in.get("mint"), token_out.get("mint")]:
                                        # Log actual execution details
                                        logger.info(f"Helius confirmed trade: {tx.get('signature')[:8]}...")
                                        
                                        # Calculate actual slippage
                                        if "expected_price" in pos:
                                            actual_price = token_out.get("amount", 0) / token_in.get("amount", 1)
                                            slippage = abs(actual_price - pos["expected_price"]) / pos["expected_price"]
                                            logger.info(f"Actual slippage: {slippage:.2%}")
                        
        except Exception as e:
            logger.error(f"Helius monitoring error: {e}")
        
        await asyncio.sleep(60)  # Check every minute

# =====================================
# DexScreener API Functions (Primary price source)
# =====================================
async def fetch_token_price(token: str) -> Optional[float]:
    """Fetch token price from DexScreener (primary) with Jupiter v6 fallback"""
    # Check cache first
    cached = get_cached_price(token)
    if cached:
        return cached
    
    # Try DexScreener first
    if not is_circuit_broken("dexscreener"):
        try:
            async with get_session() as session:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "pairs" in data and data["pairs"]:
                            # Find SOL pair
                            for pair in data["pairs"]:
                                if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                    price = float(pair.get("priceUsd", 0))
                                    if price > 0:
                                        cache_price(token, price)
                                        return price
        except Exception as e:
            logger.error(f"DexScreener price error for {token}: {e}")
            trip_circuit_breaker("dexscreener")
    
    # Fallback to Jupiter v6 (FIXED FROM v3!)
    if not is_circuit_broken("jupiter"):
        try:
            async with get_session() as session:
                # CORRECT v6 ENDPOINT
                url = f"https://price.jup.ag/v6/price?ids={token}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "data" in data and token in data["data"]:
                            price = float(data["data"][token].get("price", 0))
                            if price > 0:
                                cache_price(token, price)
                                return price
        except Exception as e:
            logger.error(f"Jupiter v6 price error for {token}: {e}")
            trip_circuit_breaker("jupiter")
    
    return None

async def fetch_liquidity_and_buyers(token: str) -> Dict[str, Any]:
    """Fetch liquidity and buyer data from DexScreener"""
    if is_circuit_broken("dexscreener"):
        return {"liq": 0, "buyers": 0}
    
    try:
        async with get_session() as session:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "pairs" in data and data["pairs"]:
                        # Get the main SOL pair
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                return {
                                    "liq": float(pair.get("liquidity", {}).get("usd", 0)) / 1000,  # Convert to K
                                    "buyers": int(pair.get("txns", {}).get("h24", {}).get("buys", 0))
                                }
                    return {"liq": 0, "buyers": 0}
    except Exception as e:
        logger.error(f"DexScreener liquidity error: {e}")
        trip_circuit_breaker("dexscreener")
    
    return {"liq": 0, "buyers": 0}

async def fetch_volumes(token: str) -> Dict[str, Any]:
    """Fetch volume data from DexScreener"""
    if is_circuit_broken("dexscreener"):
        return {"liq": 0, "vol_1h": 0, "vol_6h": 0, "base_liq": 0}
    
    try:
        async with get_session() as session:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "pairs" in data and data["pairs"]:
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                volume_h24 = float(pair.get("volume", {}).get("h24", 0))
                                return {
                                    "liq": float(pair.get("liquidity", {}).get("usd", 0)) / 1000,
                                    "vol_1h": volume_h24 / 24,  # Estimate
                                    "vol_6h": volume_h24 / 4,   # Estimate
                                    "base_liq": float(pair.get("liquidity", {}).get("base", 0))
                                }
    except Exception as e:
        logger.error(f"DexScreener volume error: {e}")
        trip_circuit_breaker("dexscreener")
    
    return {"liq": 0, "vol_1h": 0, "vol_6h": 0, "base_liq": 0}

async def fetch_pool_age(token: str) -> Optional[int]:
    """Fetch pool age from DexScreener"""
    if is_circuit_broken("dexscreener"):
        return None
    
    try:
        async with get_session() as session:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "pairs" in data and data["pairs"]:
                        for pair in data["pairs"]:
                            if pair.get("quoteToken", {}).get("symbol") == "SOL":
                                created_at = pair.get("pairCreatedAt", 0) / 1000  # Convert ms to s
                                if created_at > 0:
                                    return int(time.time() - created_at)
    except Exception as e:
        logger.error(f"DexScreener pool age error: {e}")
        trip_circuit_breaker("dexscreener")
    
    return None

async def fetch_holders_and_conc(token: str) -> Dict[str, Any]:
    """Fetch holder data using Helius DAS API"""
    if is_circuit_broken("helius"):
        return {"holders": 0, "max_holder_pct": 100}
    
    try:
        async with get_session() as session:
            url = f"https://api.helius.xyz/v0/token-metadata?api-key={HELIUS_API_KEY}"
            payload = {"mintAccounts": [token]}
            
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # This is a simplified version - you'd need to implement
                    # proper holder analysis using getTokenAccounts
                    return {"holders": 100, "max_holder_pct": 10}  # Defaults
    except Exception as e:
        logger.error(f"Helius holder data error: {e}")
        trip_circuit_breaker("helius")
    
    return {"holders": 0, "max_holder_pct": 100}

# =====================================
# Utility Functions
# =====================================
def get_total_pl():
    return sum([pos.get("pl", 0) for pos in positions.values()]) + ultra_pl + scalper_pl + community_pl

def calc_winrate():
    total = ultra_total + scalper_total + community_total
    wins = ultra_wins + scalper_wins + community_wins
    return (100.0 * wins / total) if total else 0.0

def estimate_short_vs_long_volume(vol_1h: float, vol_6h: float) -> bool:
    """Estimate if short-term volume is increasing"""
    if vol_6h == 0:
        return False
    hourly_avg = vol_6h / 6
    return vol_1h > hourly_avg * 1.2  # 20% above average

# =====================================
# Data Feeds - ENHANCED with PumpPortal
# =====================================
async def pumpportal_newtoken_feed(callback):
    """WebSocket feed for new Pump.fun tokens via PumpPortal - FASTEST detection"""
    uri = "wss://pumpportal.fun/api/data"
    retry_count = 0
    max_retries = 10
    
    while retry_count < max_retries:
        try:
            async with websockets.connect(uri) as ws:
                # Subscribe to new tokens
                payload = {"method": "subscribeNewToken"}
                await ws.send(json.dumps(payload))
                
                # Also subscribe to trades for our positions
                if positions:
                    payload = {
                        "method": "subscribeTokenTrade",
                        "keys": list(positions.keys())[:50]  # Max 50 tokens
                    }
                    await ws.send(json.dumps(payload))
                
                retry_count = 0
                logger.info("Connected to PumpPortal WebSocket")
                
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        
                        # New token event
                        if "mint" in data.get("params", {}):
                            token = data["params"]["mint"]
                            await callback(token, "pumpportal")
                            
                        # Trade event for monitoring
                        elif "signature" in data.get("params", {}):
                            trade = data["params"]
                            token = trade.get("mint")
                            if token in positions:
                                # Update position with real-time trade data
                                positions[token]["last_trade"] = {
                                    "price": float(trade.get("vSolInBondingCurve", 0)),
                                    "timestamp": time.time()
                                }
                                
                    except asyncio.TimeoutError:
                        await ws.ping()
                        
        except Exception as e:
            retry_count += 1
            wait_time = min(60, 2 ** retry_count)
            logger.error(f"PumpPortal WS error (retry {retry_count}/{max_retries}): {e}")
            await asyncio.sleep(wait_time)

async def bitquery_polling_feed(callback):
    """Bitquery V2 REST API polling for trending tokens (free tier compatible)"""
    if not BITQUERY_API_KEY or BITQUERY_API_KEY == "disabled":
        logger.warning("Bitquery feed disabled - set BITQUERY_API_KEY='disabled' to silence this")
        return

    # Use the standard V2 endpoint (not streaming/EAP)
    url = "https://graphql.bitquery.io/ide"  # Standard GraphQL endpoint for free tier
    
    # Free tier compatible query - no Solana EAP access
    # Using Ethereum DEX trades as an example (adjust based on your needs)
    query = """
    query {
        ethereum(network: ethereum) {
            dexTrades(
                options: {limit: 20, desc: "block.timestamp.time"}
                smartContractAddress: {is: "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"}
            ) {
                transaction {
                    hash
                }
                block {
                    timestamp {
                        time(format: "%Y-%m-%d %H:%M:%S")
                    }
                }
                buyAmount
                buyAmountInUsd: buyAmount(in: USD)
                buyCurrency {
                    address
                    symbol
                    name
                }
                sellAmount
                sellAmountInUsd: sellAmount(in: USD)
                sellCurrency {
                    address
                    symbol
                    name
                }
            }
        }
    }
    """
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": BITQUERY_API_KEY  # Note: Free tier uses X-API-KEY header
    }
    
    seen_tokens = set()
    
    while True:
        try:
            async with get_session() as session:
                async def _fetch():
                    async with session.post(url, json={"query": query}, headers=headers) as resp:
                        if resp.status == 401:
                            logger.error("Bitquery authentication failed. Check your API key")
                            trip_circuit_breaker("bitquery")
                            return
                        
                        if resp.status == 429:
                            logger.warning("Bitquery rate limit reached")
                            await asyncio.sleep(60)  # Wait a minute
                            return
                            
                        if resp.status != 200:
                            text = await resp.text()
                            logger.error(f"Bitquery HTTP {resp.status}: {text}")
                            return
                        
                        data = await resp.json()
                        
                        if "errors" in data:
                            logger.error(f"Bitquery GraphQL errors: {data['errors']}")
                            # Check if it's a Solana access error
                            error_msg = str(data['errors'])
                            if "Solana" in error_msg or "EAP" in error_msg:
                                logger.error("Solana access not available on free tier. Disabling Bitquery.")
                                trip_circuit_breaker("bitquery")
                                return
                            await asyncio.sleep(60)
                            return
                        
                        # Process Ethereum DEX trades (since Solana isn't available on free tier)
                        trades = data.get("data", {}).get("ethereum", {}).get("dexTrades", [])
                        
                        if trades:
                            logger.info(f"Bitquery: Found {len(trades)} Ethereum DEX trades")
                            
                            # Note: This won't work for Solana tokens on free tier
                            # You'll need to either:
                            # 1. Upgrade to paid tier for Solana access
                            # 2. Disable Bitquery for your Solana bot
                            # 3. Use alternative data sources
                            
                            for trade in trades:
                                buy_currency = trade.get("buyCurrency", {})
                                token_address = buy_currency.get("address")
                                
                                if token_address and token_address not in seen_tokens:
                                    seen_tokens.add(token_address)
                                    # This would only work for Ethereum tokens
                                    logger.warning("Bitquery free tier doesn't support Solana - skipping token callback")
                
                await retry_with_backoff(_fetch)
                
        except Exception as e:
            logger.error(f"Bitquery API error: {e}")
            trip_circuit_breaker("bitquery")
        
        # Poll every 60 seconds for free tier (be respectful)
        await asyncio.sleep(60)

# Alternative: Test Bitquery access level
async def test_bitquery_solana_access():
    """Test if your Bitquery account has Solana access"""
    
    if not BITQUERY_API_KEY or BITQUERY_API_KEY == "disabled":
        return False
    
    url = "https://graphql.bitquery.io/ide"
    
    # Try a simple Solana query
    query = """
    query {
        solana {
            blocks(limit: 1) {
                height
                timestamp {
                    time
                }
            }
        }
    }
    """
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": BITQUERY_API_KEY
    }
    
    try:
        async with get_session() as session:
            async with session.post(url, json={"query": query}, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if "errors" in data:
                        error_msg = str(data['errors'])
                        if "subscription" in error_msg.lower() or "upgrade" in error_msg.lower():
                            logger.error("❌ Solana access requires paid subscription")
                            return False
                        else:
                            logger.error(f"❌ Solana query error: {error_msg}")
                            return False
                    
                    if "data" in data and "solana" in data["data"]:
                        logger.info("✅ You have Solana access on Bitquery!")
                        return True
                else:
                    logger.error(f"❌ HTTP {resp.status} - No Solana access")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Error testing Solana access: {e}")
        return False

# Recommended: Disable Bitquery for Solana bot
async def bitquery_polling_feed_disabled(callback):
    """Disabled Bitquery feed for free tier users"""
    logger.info("Bitquery feed disabled - free tier doesn't support Solana")
    logger.info("Consider using PumpPortal WebSocket or DexScreener REST API instead")
    
    # Don't run the polling loop
    while False:
        await asyncio.sleep(3600)

# =====================================
# Community Vote Aggregator
# =====================================
async def community_candidate_callback(token, src, info=None):
    """Aggregate community signals from multiple sources"""
    now = time.time()
    if src and token:
        rec = community_signal_votes[token]
        rec["sources"].add(src)
        if "first_seen" not in rec:
            rec["first_seen"] = now
        
        voted = len(rec["sources"])
        logger.info(f"[CommunityBot] {token} in {rec['sources']} ({voted}/{COMM_MIN_SIGNALS})")
        
        if voted >= COMM_MIN_SIGNALS:
            await community_token_queue.put(token)

# =====================================
# ToxiBot Client - ENHANCED with monitoring
# =====================================
class ToxiBotClient:
    def __init__(self, api_id, api_hash, session_id, username):
        self._client = TelegramClient(StringSession(session_id), api_id, api_hash, connection_retries=5)
        self.bot_username = username
        self.send_lock = asyncio.Lock()
    
    async def connect(self):
        await self._client.start()
        logger.info("Connected to ToxiBot (Telegram).")
    
    async def send_buy(self, mint: str, amount: float):
        """Send buy command to ToxiBot - NO price limits as they're not documented"""
        async with self.send_lock:
            # Format amount with 4 decimals max
            amount_str = f"{amount:.4f}"
            cmd = f"/buy {mint} {amount_str}".strip()
            logger.info(f"Sending to ToxiBot: {cmd}")
            
            try:
                # Send command
                msg = await self._client.send_message(self.bot_username, cmd)
                
                # Wait for response
                await asyncio.sleep(3)
                
                # Check for success/failure
                messages = await self._client.get_messages(self.bot_username, limit=5)
                
                for response in messages:
                    if response.id > msg.id:  # Response after our command
                        response_text = response.text.lower()
                        
                        if "success" in response_text or "bought" in response_text:
                            logger.info(f"ToxiBot confirmed buy: {response.text[:100]}")
                            return True
                        elif "error" in response_text or "failed" in response_text:
                            logger.error(f"ToxiBot buy failed: {response.text[:100]}")
                            return False
                
                logger.warning("No clear response from ToxiBot")
                return True  # Assume success if no error
                
            except Exception as e:
                logger.error(f"Failed to send buy command: {e}")
                return False
            finally:
                # Rate limit protection
                await asyncio.sleep(TOXIBOT_COMMAND_DELAY)
    
    async def send_sell(self, mint: str, perc: int = 100):
        """Send sell command - may need portfolio access per docs"""
        async with self.send_lock:
            cmd = f"/sell {mint} {perc}%"
            logger.info(f"Sending to ToxiBot: {cmd}")
            
            try:
                msg = await self._client.send_message(self.bot_username, cmd)
                
                # Wait for response
                await asyncio.sleep(3)
                
                # Check response
                messages = await self._client.get_messages(self.bot_username, limit=5)
                
                for response in messages:
                    if response.id > msg.id:
                        response_text = response.text.lower()
                        
                        if "sold" in response_text or "success" in response_text:
                            logger.info(f"ToxiBot confirmed sell: {response.text[:100]}")
                            return True
                        elif "error" in response_text or "failed" in response_text:
                            logger.error(f"ToxiBot sell failed: {response.text[:100]}")
                            return False
                
                return True  # Assume success
                
            except Exception as e:
                logger.error(f"Failed to send sell command: {e}")
                return False
            finally:
                await asyncio.sleep(TOXIBOT_COMMAND_DELAY)

# =====================================
# Rugcheck Integration
# =====================================
async def rugcheck(token_addr: str) -> Dict[str, Any]:
    """Check token safety using Rugcheck API"""
    if is_circuit_broken("rugcheck"):
        return {}
    
    url = f"https://rugcheck.xyz/api/check/{token_addr}"
    
    try:
        async with get_session() as session:
            async def _fetch():
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    if resp.headers.get('content-type', '').startswith('application/json'):
                        data = await resp.json()
                    else:
                        logger.warning(f"Rugcheck returned HTML for {token_addr}")
                        data = {}
                    logger.info(f"Rugcheck {token_addr}: {data}")
                    return data
            
            return await retry_with_backoff(_fetch)
    except Exception as e:
        logger.error(f"Rugcheck error for {token_addr}: {e}")
        trip_circuit_breaker("rugcheck")
        return {}

def rug_gate(rug: Dict[str, Any]) -> Optional[str]:
    """Check if token passes rug safety checks"""
    if rug.get("label") != "Good":
        return "rugcheck not Good"
    
    if "bundled" in rug.get("supply_type", "").lower():
        if rug.get("mint"):
            blacklisted_tokens.add(rug["mint"])
        if rug.get("authority"):
            blacklisted_devs.add(rug["authority"])
        return "supply bundled"
    
    if rug.get("max_holder_pct", 0) > 25:
        return "too concentrated"
    
    return None

def is_blacklisted(token: str, dev: str = "") -> bool:
    """Check if token or developer is blacklisted"""
    return token in blacklisted_tokens or (dev and dev in blacklisted_devs)

# =====================================
# ML Scoring - REAL implementation for ToxiBot
# =====================================
async def ml_score_token(meta: Dict[str, Any]) -> float:
    """ML scoring adjusted for ToxiBot execution realities"""
    score = 50.0  # Base score
    
    # Liquidity scoring (0-25 points) - MORE IMPORTANT for ToxiBot
    liq = meta.get("liq", 0)
    if liq > 100:  # Very liquid
        score += 25
    elif liq > 50:
        score += 20
    elif liq > 25:
        score += 15
    elif liq > 10:
        score += 10
    elif liq > 5:
        score += 5
    
    # Volume acceleration (0-15 points)
    vol_1h = meta.get("vol_1h", 0)
    vol_6h = meta.get("vol_6h", 0)
    if vol_6h > 0:
        vol_accel = vol_1h / (vol_6h / 6)
        if vol_accel > 2:
            score += 15
        elif vol_accel > 1.5:
            score += 10
        elif vol_accel > 1.2:
            score += 5
    
    # ToxiBot execution factors (0-20 points)
    if vol_1h > 50000:  # High volume for good execution
        score += 20
    elif vol_1h > 20000:
        score += 15
    elif vol_1h > 10000:
        score += 10
    elif vol_1h > 5000:
        score += 5
    
    # Holder distribution (0-10 points)
    holders = meta.get("holders", 0)
    max_holder_pct = meta.get("max_holder_pct", 100)
    if holders > 500 and max_holder_pct < 10:
        score += 10
    elif holders > 250 and max_holder_pct < 20:
        score += 7
    elif holders > 100 and max_holder_pct < 30:
        score += 4
    
    # Age bonus for fresh tokens
    age = meta.get("age", 0)
    if age < 300:  # Less than 5 minutes
        score += 10
    elif age < 900:  # Less than 15 minutes
        score += 5
    elif age > 3600:  # Penalty for old tokens
        score -= 10
    
    # Source bonus
    if meta.get("src") == "pumpfun" and age < 300:
        score += 5  # Fresh pump.fun tokens
    
    return min(95, max(5, score))

# =====================================
# Risk Management - CRITICAL for live trading
# =====================================
async def calculate_position_size(bot_type: str, ml_score: float) -> float:
    """Calculate position size with hard exposure limits"""
    global current_wallet_balance, exposure, trading_enabled, daily_trades_count
    
    # Check if trading is enabled
    if not trading_enabled:
        logger.error("Trading is disabled due to risk limits!")
        return 0
    
    # Check current exposure
    max_allowed_exposure = current_wallet_balance * MAX_WALLET_EXPOSURE
    available_capital = max_allowed_exposure - exposure
    
    if available_capital <= 0.01:
        logger.warning(f"Max exposure reached: {exposure:.3f}/{max_allowed_exposure:.3f}")
        return 0
    
    # Base amounts by bot type
    base_amounts = {
        "ultra": ULTRA_BUY_AMOUNT,
        "scalper": SCALPER_BUY_AMOUNT,
        "community": COMMUNITY_BUY_AMOUNT
    }
    
    base = base_amounts.get(bot_type, 0.05)
    
    # Adjust by ML score (0.5x to 1.5x)
    ml_multiplier = 0.5 + (ml_score / 100)
    
    # Dynamic sizing based on daily performance
    daily_pl = current_wallet_balance - daily_starting_balance
    if daily_pl > 0.3:  # Profitable day
        performance_multiplier = min(1.5, 1 + (daily_pl / 2))  # Up to 50% larger
        logger.info(f"Profitable day! Increasing position sizes by {(performance_multiplier-1)*100:.0f}%")
    else:
        performance_multiplier = 1.0
    
    position_size = base * ml_multiplier * performance_multiplier
    
    # Ensure we don't exceed available capital
    position_size = min(position_size, available_capital)
    
    # Final bounds
    position_size = max(0.01, min(0.1, position_size))
    
    logger.info(f"Position size for {bot_type}: {position_size:.3f} SOL (ML: {ml_score:.0f}, Available: {available_capital:.3f})")
    
    return position_size

async def risk_management_monitor():
    """Monitor risk limits and kill switch"""
    global trading_enabled, daily_starting_balance, current_wallet_balance
    
    while True:
        try:
            # Get current balance
            current_balance = await fetch_wallet_balance()
            if current_balance:
                current_wallet_balance = current_balance
                
                # Set starting balance if not set
                if daily_starting_balance == 0:
                    daily_starting_balance = current_balance
                    logger.info(f"Daily starting balance: {daily_starting_balance} SOL")
                
                # Check daily loss limit
                daily_loss = daily_starting_balance - current_balance
                daily_loss_percent = daily_loss / daily_starting_balance if daily_starting_balance > 0 else 0
                
                if daily_loss_percent >= DAILY_LOSS_LIMIT_PERCENT:
                    trading_enabled = False
                    logger.critical(f"TRADING HALTED: Daily loss limit reached! Lost {daily_loss:.2f} SOL ({daily_loss_percent:.1%})")
                    
                    # Close all positions
                    for token in list(positions.keys()):
                        if positions[token].get('size', 0) > 0:
                            await toxibot.send_sell(token, 100)
                            logger.warning(f"Emergency sold {token}")
                    
                    # Send alert
                    activity_log.append(f"[EMERGENCY] Trading halted - 50% daily loss reached")
                
                # Log current risk metrics
                logger.info(f"Risk Monitor - Balance: {current_balance:.3f}, Daily P/L: {-daily_loss:.3f} ({-daily_loss_percent:.1%}), Exposure: {exposure:.3f}/{current_balance * MAX_WALLET_EXPOSURE:.3f}")
                
        except Exception as e:
            logger.error(f"Risk monitor error: {e}")
        
        await asyncio.sleep(30)  # Check every 30 seconds

async def update_trading_parameters():
    """Dynamically adjust trading based on performance"""
    global daily_trades_count, trading_enabled, consecutive_profitable_trades
    global ULTRA_MAX_DAILY_TRADES, SCALPER_MAX_POSITIONS, COMMUNITY_MAX_DAILY
    
    while True:
        try:
            if not trading_enabled:
                await asyncio.sleep(300)  # Check every 5 minutes if disabled
                continue
            
            # Calculate daily performance
            daily_pl = current_wallet_balance - daily_starting_balance
            daily_pl_percent = daily_pl / daily_starting_balance if daily_starting_balance > 0 else 0
            
            # Base limits
            base_trade_limit = 50
            current_limit = base_trade_limit
            
            # Adjust based on performance
            if daily_pl_percent > 0.2:  # 20% profit
                current_limit = base_trade_limit * 2  # Double trades
                logger.info(f"Excellent day! Increasing trade limit to {current_limit}")
            elif daily_pl_percent > 0.1:  # 10% profit
                current_limit = int(base_trade_limit * 1.5)
                logger.info(f"Good day! Increasing trade limit to {current_limit}")
            elif daily_pl_percent < -0.2:  # 20% loss
                current_limit = int(base_trade_limit * 0.5)  # Half trades
                logger.warning(f"Rough day. Reducing trade limit to {current_limit}")
            
            # Winning streak bonus
            if consecutive_profitable_trades >= 5:
                current_limit = int(current_limit * 1.2)
                logger.info(f"Hot streak! Extra trades allowed: {current_limit}")
            
            # Update global limits
            ULTRA_MAX_DAILY_TRADES = int(current_limit * 0.4)  # 40% to Speed Demon
            SCALPER_MAX_POSITIONS = int(current_limit * 0.4)  # 40% to Analyst
            COMMUNITY_MAX_DAILY = int(current_limit * 0.2)  # 20% to Whale Tracker
            
            await asyncio.sleep(300)  # Update every 5 minutes
            
        except Exception as e:
            logger.error(f"Parameter update error: {e}")
            await asyncio.sleep(60)

# =====================================
# Trading Strategies - ENHANCED
# =====================================
async def ultra_early_handler(token, toxibot):
    """Ultra-early discovery strategy for new tokens"""
    global ultra_total, trading_enabled, daily_trades_count, exposure
    
    if not trading_enabled:
        return
        
    if ultra_total >= ULTRA_MAX_DAILY_TRADES:
        logger.info(f"Ultra-early daily limit reached: {ultra_total}")
        return
    
    if is_blacklisted(token):
        return
    
    rug = await rugcheck(token)
    if rug_gate(rug):
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} UltraEarly: Rug gated.")
        return
    
    if token in positions:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} UltraEarly: Already traded, skipping.")
        return
    
    # Monitor liquidity rises
    rises, last_liq, last_buyers = 0, 0, 0
    for i in range(3):
        stats = await fetch_liquidity_and_buyers(token)
        if stats['liq'] >= ULTRA_MIN_LIQ and stats['liq'] > last_liq:
            rises += 1
        last_liq, last_buyers = stats['liq'], stats['buyers']
        await asyncio.sleep(2)
    
    if rises < ULTRA_MIN_RISES:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} UltraEarly: Liquidity not rapidly rising, skipping.")
        return
    
    # Get pool age
    pool_age = await fetch_pool_age(token) or 9999
    if pool_age > ULTRA_AGE_MAX_S:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} UltraEarly: Too old ({pool_age}s), skipping.")
        return
    
    # ML scoring
    token_data = {
        'liq': last_liq,
        'buyers': last_buyers,
        'age': pool_age,
        'src': 'pumpfun',
        'vol_1h': 0,  # Too new for volume
        'vol_6h': 0
    }
    ml_score = await ml_score_token(token_data)
    
    if ml_score < ULTRA_MIN_ML_SCORE:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} UltraEarly: ML score too low ({ml_score:.1f})")
        return
    
    # Calculate position size
    position_size = await calculate_position_size("ultra", ml_score)
    if position_size == 0:
        return
    
    entry_price = await fetch_token_price(token) or 0.01
    
    try:
        # Use anti-snipe delay
        await asyncio.sleep(ANTI_SNIPE_DELAY)
        
        # Execute with ToxiBot
        success = await toxibot.send_buy(token, position_size)
        
        if success:
            ultra_total += 1
            daily_trades_count += 1
            exposure += position_size * entry_price
            
            positions[token] = {
                "src": "pumpfun",
                "buy_time": time.time(),
                "size": position_size,
                "ml_score": ml_score,
                "entry_price": entry_price,
                "last_price": entry_price,
                "phase": "filled",
                "pl": 0.0,
                "local_high": entry_price,
                "hard_sl": entry_price * ULTRA_SL_X,
                "dev": rug.get("authority"),
                "total_sold_percent": 0
            }
            
            save_position(token, positions[token])
            record_trade(token, "BUY", position_size, entry_price)
            activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} UltraEarly: BUY {position_size:.3f} @ {entry_price:.5f} (ML: {ml_score:.0f})")
        else:
            logger.error(f"ToxiBot buy failed for {token}")
            
    except Exception as e:
        logger.error(f"Failed to execute UltraEarly buy: {e}")

async def scalper_handler(token, src, toxibot):
    """Scalper strategy for trending tokens"""
    global scalper_total, trading_enabled, daily_trades_count, exposure
    
    if not trading_enabled:
        return
        
    active_scalper_positions = sum(1 for p in positions.values() if p.get("src") in ("bitquery",))
    if active_scalper_positions >= SCALPER_MAX_POSITIONS:
        logger.info(f"Scalper position limit reached: {active_scalper_positions}")
        return
    
    if is_blacklisted(token):
        return
    
    if token in positions:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Scalper] Already traded. Skipping.")
        return
    
    pool_stats = await fetch_volumes(token)
    pool_age = await fetch_pool_age(token) or 9999
    
    liq_ok = pool_stats["liq"] >= SCALPER_MIN_LIQ
    vol_ok = estimate_short_vs_long_volume(pool_stats["vol_1h"], pool_stats["vol_6h"])
    age_ok = 0 <= pool_age < SCALPER_MAX_POOLAGE
    
    if not (liq_ok and age_ok and vol_ok):
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Scalper] Entry FAIL: Liq:{liq_ok}, Age:{age_ok}, Vol:{vol_ok}")
        return
    
    rug = await rugcheck(token)
    if rug_gate(rug):
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Scalper] Rug gated.")
        return
    
    # ML scoring
    token_data = {
        'liq': pool_stats["liq"],
        'vol_1h': pool_stats["vol_1h"],
        'vol_6h': pool_stats["vol_6h"],
        'age': pool_age,
        'src': src,
        'buyers': 0  # Would need to fetch
    }
    ml_score = await ml_score_token(token_data)
    
    if ml_score < SCALPER_MIN_ML_SCORE:
        activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Scalper] ML score too low ({ml_score:.1f})")
        return
    
    # Calculate position size
    position_size = await calculate_position_size("scalper", ml_score)
    if position_size == 0:
        return
    
    entry_price = await fetch_token_price(token) or 0.01
    
    try:
        success = await toxibot.send_buy(token, position_size)
        
        if success:
            scalper_total += 1
            daily_trades_count += 1
            exposure += position_size * entry_price
            
            positions[token] = {
                "src": src,
                "buy_time": time.time(),
                "size": position_size,
                "ml_score": ml_score,
                "entry_price": entry_price,
                "last_price": entry_price,
                "phase": "filled",
                "pl": 0.0,
                "local_high": entry_price,
                "hard_sl": entry_price * SCALPER_SL_X,
                "liq_ref": pool_stats["base_liq"],
                "dev": rug.get("authority"),
                "total_sold_percent": 0
            }
            
            save_position(token, positions[token])
            record_trade(token, "BUY", position_size, entry_price)
            activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} Scalper: BUY {position_size:.3f} @ {entry_price:.5f} (ML: {ml_score:.0f})")
        else:
            logger.error(f"ToxiBot buy failed for {token}")
            
    except Exception as e:
        logger.error(f"Failed to execute Scalper buy: {e}")

async def community_trade_manager(toxibot):
    """Community consensus trading strategy"""
    global community_total, trading_enabled, daily_trades_count, exposure
    
    while True:
        try:
            if not trading_enabled:
                await asyncio.sleep(60)
                continue
                
            if community_total >= COMMUNITY_MAX_DAILY:
                await asyncio.sleep(300)
                continue
            
            token = await community_token_queue.get()
            
            if is_blacklisted(token):
                continue
            
            rug = await rugcheck(token)
            dev = rug.get("authority")
            
            if rug_gate(rug) or (dev and dev in recent_rugdevs):
                activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Community] rejected: Ruggate or rugdev.")
                continue
            
            holders_data = await fetch_holders_and_conc(token)
            if holders_data["holders"] < COMM_HOLDER_THRESHOLD or holders_data["max_holder_pct"] > COMM_MAX_CONC * 100:
                activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Community] fails holder/distribution screen.")
                continue
            
            if token in positions:
                activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Community] position open. No averaging down.")
                continue
            
            # Get liquidity
            stats = await fetch_liquidity_and_buyers(token)
            if stats['liq'] < 25:  # Minimum liquidity for whale trades
                continue
            
            # ML scoring
            token_data = {
                'liq': stats['liq'],
                'holders': holders_data["holders"],
                'max_holder_pct': holders_data["max_holder_pct"],
                'age': 0,  # Unknown
                'src': 'community',
                'vol_1h': 0,
                'vol_6h': 0
            }
            ml_score = await ml_score_token(token_data)
            
            if ml_score < 70:  # Higher threshold for community
                continue
            
            # Calculate position size
            position_size = await calculate_position_size("community", ml_score)
            if position_size == 0:
                continue
            
            entry_price = await fetch_token_price(token) or 0.01
            
            try:
                # Delay after whale entry
                await asyncio.sleep(5)
                
                success = await toxibot.send_buy(token, position_size)
                
                if success:
                    community_total += 1
                    daily_trades_count += 1
                    exposure += position_size * entry_price
                    
                    now = time.time()
                    positions[token] = {
                        "src": "community",
                        "buy_time": now,
                        "size": position_size,
                        "ml_score": ml_score,
                        "entry_price": entry_price,
                        "last_price": entry_price,
                        "phase": "filled",
                        "pl": 0.0,
                        "local_high": entry_price,
                        "hard_sl": entry_price * COMM_SL_PCT,
                        "dev": dev,
                        "hold_until": now + COMM_HOLD_SECONDS,
                        "total_sold_percent": 0
                    }
                    
                    save_position(token, positions[token])
                    record_trade(token, "BUY", position_size, entry_price)
                    activity_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {token} [Community] BUY {position_size:.3f} @ {entry_price:.6f} (ML: {ml_score:.0f})")
                    
            except Exception as e:
                logger.error(f"Failed to execute Community buy: {e}")
                
        except Exception as e:
            logger.error(f"Community trade manager error: {e}")
            await asyncio.sleep(5)

# =====================================
# Process Token
# =====================================
async def process_token(token, src):
    """Route token to appropriate strategy"""
    if src in ("pumpfun", "pumpportal"):
        await ultra_early_handler(token, toxibot)
    elif src in ("bitquery",):
        await scalper_handler(token, src, toxibot)

# =====================================
# Position Management - ENHANCED with ToxiBot awareness
# =====================================
async def update_position_prices_and_wallet():
    """Update position prices and handle exits"""
    global positions, current_wallet_balance, daily_loss, exposure
    
    while True:
        try:
            active_tokens = [token for token, pos in positions.items() if pos.get('size', 0) > 0]
            
            # Update prices in batches
            price_tasks = [fetch_token_price(token) for token in active_tokens]
            prices = await asyncio.gather(*price_tasks, return_exceptions=True)
            
            for token, price in zip(active_tokens, prices):
                if isinstance(price, Exception):
                    logger.warning(f"Price update failed for {token}: {price}")
                    continue
                
                if price and token in positions:
                    pos = positions[token]
                    pos['last_price'] = price
                    pos['local_high'] = max(pos.get("local_high", price), price)
                    pl = (price - pos['entry_price']) * pos['size']
                    pos['pl'] = pl
                    
                    # Handle position exit
                    await handle_position_exit(token, pos, price, toxibot)
            
            # Clean up closed positions
            to_remove = [k for k, v in positions.items() if v.get('size', 0) == 0]
            for k in to_remove:
                daily_loss += positions[k].get('pl', 0)
                del positions[k]
            
            # Update wallet balance
            bal = await fetch_wallet_balance()
            if bal:
                current_wallet_balance = bal
            
            # Calculate exposure
            exposure = sum(pos.get('size', 0) * pos.get('last_price', 0) for pos in positions.values())
            
            await asyncio.sleep(15)
        except Exception as e:
            logger.error(f"Position update error: {e}")
            await asyncio.sleep(30)

async def handle_position_exit(token: str, pos: Dict[str, Any], last_price: float, toxibot):
    """ToxiBot-aware exit handler with multi-level TP"""
    global exposure, consecutive_profitable_trades
    
    try:
        buy_time = pos.get("buy_time", time.time())
        age = time.time() - buy_time
        entry_price = pos["entry_price"]
        src = pos.get("src", "")
        current_size = pos.get("size", 0)
        
        if current_size <= 0:
            return
        
        # Track what we've already sold
        if "total_sold_percent" not in pos:
            pos["total_sold_percent"] = 0
        
        remaining_percent = 100 - pos["total_sold_percent"]
        if remaining_percent <= 0:
            return
        
        should_sell = False
        sell_percent = 0
        reason = ""
        
        # Calculate P/L ratio
        pl_ratio = last_price / entry_price
        
        # Strategy-specific exits
        if src in ("pumpfun", "pumpportal"):  # Speed Demon
            if pl_ratio >= ULTRA_TP_X:  # 3x
                should_sell = True
                sell_percent = 100  # Take it all at 3x
                reason = "3x target hit!"
            elif pl_ratio <= ULTRA_SL_X:  # 0.5x
                should_sell = True
                sell_percent = 100
                reason = "Stop loss"
            elif age > ULTRA_AGE_MAX_S:
                should_sell = True
                sell_percent = 100
                reason = "Age limit"
                
        elif src in ("bitquery",):  # Analyst
            # Multiple TP levels
            if pl_ratio >= SCALPER_TP_LEVELS[2]:  # 5x
                should_sell = True
                sell_percent = remaining_percent
                reason = "5x mega target!"
            elif pl_ratio >= SCALPER_TP_LEVELS[1] and pos["total_sold_percent"] < 60:  # 2.5x
                should_sell = True
                sell_percent = 60 - pos["total_sold_percent"]
                reason = "2.5x target"
            elif pl_ratio >= SCALPER_TP_LEVELS[0] and pos["total_sold_percent"] < 30:  # 1.5x
                should_sell = True
                sell_percent = 30 - pos["total_sold_percent"]
                reason = "1.5x target"
            elif pl_ratio <= SCALPER_SL_X:  # 0.7x
                should_sell = True
                sell_percent = remaining_percent
                reason = "Stop loss"
            # Trailing stop
            elif pos["local_high"] > entry_price * 1.5:
                trail_stop = pos["local_high"] * (1 - SCALPER_TRAIL)
                if last_price <= trail_stop:
                    should_sell = True
                    sell_percent = remaining_percent
                    reason = "Trailing stop"
                
        elif src == "community":  # Whale Tracker
            # Time-based hold + targets
            if age < COMM_HOLD_SECONDS and pl_ratio > COMM_SL_PCT:
                return  # Don't sell yet unless stop loss hit
                
            if pl_ratio >= COMM_TP_LEVELS[2]:  # 10x
                should_sell = True
                sell_percent = remaining_percent
                reason = "10x moon shot!"
            elif pl_ratio >= COMM_TP_LEVELS[1] and pos["total_sold_percent"] < 70:  # 5x
                should_sell = True
                sell_percent = 70 - pos["total_sold_percent"]
                reason = "5x whale target"
            elif pl_ratio >= COMM_TP_LEVELS[0] and pos["total_sold_percent"] < 30:  # 2x
                should_sell = True
                sell_percent = 30 - pos["total_sold_percent"]
                reason = "2x target"
            elif pl_ratio <= COMM_SL_PCT:  # 0.6x
                should_sell = True
                sell_percent = remaining_percent
                reason = "Stop loss"
        
        # Execute sell through ToxiBot
        if should_sell and sell_percent > 0:
            actual_sell_percent = min(sell_percent, remaining_percent)
            
            logger.info(f"Attempting to sell {actual_sell_percent}% of {token} ({reason})")
            
            # Send sell command to ToxiBot
            success = await toxibot.send_sell(token, int(actual_sell_percent))
            
            if success:
                # Update position tracking
                pos["total_sold_percent"] += actual_sell_percent
                
                # Calculate actual SOL sold
                sol_amount = current_size * (actual_sell_percent / 100)
                pl = (last_price - entry_price) * sol_amount
                
                # Update position size
                pos["size"] = current_size * (1 - actual_sell_percent / 100)
                
                # Update global tracking
                exposure -= sol_amount * last_price
                
                if pl > 0:
                    consecutive_profitable_trades += 1
                else:
                    consecutive_profitable_trades = 0
                
                # Log the trade
                activity_log.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] {token} "
                    f"Sold {actual_sell_percent}% @ {last_price:.6f} ({reason}), "
                    f"P/L: {pl:+.3f} SOL ({pl_ratio:.1f}x)"
                )
                
                # Update stats
                if src in ("pumpfun", "pumpportal"):
                    global ultra_wins, ultra_pl
                    if pl > 0:
                        ultra_wins += 1
                    ultra_pl += pl
                elif src in ("bitquery",):
                    global scalper_wins, scalper_pl
                    if pl > 0:
                        scalper_wins += 1
                    scalper_pl += pl
                elif src == "community":
                    global community_wins, community_pl
                    if pl > 0:
                        community_wins += 1
                    community_pl += pl
                
                # Record in database
                record_trade(token, "SELL", sol_amount, last_price, pl)
                save_position(token, pos)
                
                # Track rug devs if significant loss
                if pl < -0.05 and pos.get("dev"):
                    recent_rugdevs.add(pos["dev"])
                
            else:
                logger.error(f"ToxiBot sell command failed for {token}")
                
    except Exception as e:
        logger.error(f"Position exit handler error for {token}: {e}")

# =====================================
# Dashboard HTML/JS (unchanged)
# =====================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TOXIBOT v2 | TRON INTERFACE</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            background: #000; 
            color: #00ffff; 
            font-family: 'Orbitron', monospace; 
            overflow-x: hidden; 
            position: relative; 
        }
        
        body::before { 
            content: ""; 
            position: fixed; 
            top: 0; 
            left: 0; 
            width: 100%; 
            height: 100%;
            background-image: 
                linear-gradient(rgba(0, 255, 255, 0.1) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 255, 255, 0.1) 1px, transparent 1px);
            background-size: 50px 50px; 
            z-index: -2; 
        }
        
        body::after { 
            content: ""; 
            position: fixed; 
            top: 0; 
            left: 0; 
            width: 100%; 
            height: 100%;
            background: repeating-linear-gradient(
                0deg, transparent, transparent 2px, rgba(0, 255, 255, 0.03) 2px, rgba(0, 255, 255, 0.03) 4px
            ); 
            pointer-events: none; 
            z-index: 1; 
        }
        
        .container { 
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 20px; 
            position: relative; 
            z-index: 2; 
        }
        
        .header { 
            text-align: center; 
            margin-bottom: 30px; 
            position: relative; 
            padding: 30px 0; 
        }
        
        .header::before { 
            content: ""; 
            position: absolute; 
            top: 0; 
            left: -50%; 
            right: -50%; 
            height: 1px;
            background: linear-gradient(90deg, transparent, #00ffff, transparent); 
            animation: scan 3s linear infinite; 
        }
        
        @keyframes scan { 
            0% { transform: translateX(-100%); } 
            100% { transform: translateX(100%); } 
        }
        
        h1 { 
            font-size: 4em; 
            font-weight: 900; 
            text-transform: uppercase; 
            letter-spacing: 0.1em;
            text-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff, 0 0 30px #00ffff, 0 0 40px #0088ff;
            animation: pulse-glow 2s ease-in-out infinite; 
        }
        
        @keyframes pulse-glow { 
            0%, 100% { opacity: 1; } 
            50% { opacity: 0.8; } 
        }
        
        .status-indicator { 
            display: inline-block; 
            padding: 10px 30px; 
            margin-top: 20px; 
            border: 2px solid #00ff00;
            background: rgba(0, 255, 0, 0.1); 
            font-weight: 700; 
            text-transform: uppercase; 
            position: relative; 
            overflow: hidden; 
        }
        
        .status-indicator.active { 
            color: #00ff00; 
            text-shadow: 0 0 10px #00ff00; 
        }
        
        .status-indicator.inactive { 
            border-color: #ff0066; 
            background: rgba(255, 0, 102, 0.1);
            color: #ff0066; 
            text-shadow: 0 0 10px #ff0066; 
        }
        
        .status-indicator::before { 
            content: ""; 
            position: absolute; 
            top: 0; 
            left: -100%; 
            width: 100%; 
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent); 
            animation: sweep 3s linear infinite; 
        }
        
        @keyframes sweep { 
            0% { left: -100%; } 
            100% { left: 100%; } 
        }
        
        .metrics-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
            gap: 20px; 
            margin-bottom: 30px; 
        }
        
        .metric-card { 
            background: rgba(0, 20, 40, 0.8); 
            border: 1px solid #00ffff; 
            padding: 20px; 
            position: relative; 
            overflow: hidden; 
            transition: all 0.3s ease; 
        }
        
        .metric-card::before { 
            content: ""; 
            position: absolute; 
            top: 0; 
            left: 0; 
            right: 0; 
            height: 2px;
            background: linear-gradient(90deg, transparent, #00ffff, transparent); 
            animation: slide 2s linear infinite; 
        }
        
        .metric-card:hover { 
            transform: translateY(-5px); 
            box-shadow: 0 10px 30px rgba(0,255,255,0.3); 
            border-color: #00ff00; 
        }
        
        .metric-label { 
            font-size: 0.9em; 
            color: #0088ff; 
            text-transform: uppercase; 
            letter-spacing: 0.1em; 
        }
        
        .metric-value { 
            font-size: 1.8em; 
            font-weight: 700; 
            margin-top: 10px; 
            font-family: 'Share Tech Mono', monospace; 
        }
        
        .metric-value.positive { color: #00ff00; }
        .metric-value.negative { color: #ff0066; }
        
        .bots-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .bot-card {
            background: rgba(0, 40, 80, 0.6);
            border: 2px solid #0088ff;
            padding: 20px;
            position: relative;
        }
        
        .bot-name {
            font-size: 1.2em;
            font-weight: 700;
            color: #00ffff;
            margin-bottom: 15px;
            text-transform: uppercase;
        }
        
        .bot-stats {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        
        .stat-row {
            display: flex;
            justify-content: space-between;
            font-family: 'Share Tech Mono', monospace;
        }
        
        .stat-row span:first-child {
            color: #0088ff;
        }
        
        .stat-row span:last-child {
            color: #00ffff;
            font-weight: 700;
        }
        
        .positions-section {
            margin-bottom: 30px;
        }
        
        .section-title {
            font-size: 1.5em;
            font-weight: 700;
            color: #00ffff;
            margin-bottom: 20px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }
        
        .positions-table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(0, 20, 40, 0.6);
        }
        
        .positions-table th,
        .positions-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(0, 255, 255, 0.2);
        }
        
        .positions-table th {
            background: rgba(0, 40, 80, 0.8);
            color: #0088ff;
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.9em;
        }
        
        .positions-table td {
            font-family: 'Share Tech Mono', monospace;
        }
        
        .positions-table tr:hover {
            background: rgba(0, 255, 255, 0.05);
        }
        
        .positive { color: #00ff00; }
        .negative { color: #ff0066; }
        
        /* Position alerts */
        .alert-profit {
            animation: blink-green 1s infinite;
        }
        
        .alert-loss {
            animation: blink-red 1s infinite;
        }
        
        .alert-old {
            animation: blink-yellow 1s infinite;
        }
        
        @keyframes blink-green {
            0%, 50% { background: rgba(0, 255, 0, 0.1); }
            51%, 100% { background: transparent; }
        }
        
        @keyframes blink-red {
            0%, 50% { background: rgba(255, 0, 102, 0.1); }
            51%, 100% { background: transparent; }
        }
        
        @keyframes blink-yellow {
            0%, 50% { background: rgba(255, 170, 0, 0.1); }
            51%, 100% { background: transparent; }
        }
        
        /* Quick stats bar */
        .quick-stats {
            display: flex;
            justify-content: space-around;
            padding: 15px;
            margin-bottom: 20px;
            background: rgba(0, 20, 40, 0.6);
            border: 1px solid #0088ff;
            font-family: 'Share Tech Mono', monospace;
        }
        
        .quick-stats span {
            color: #0088ff;
        }
        
        .quick-stats span span {
            color: #00ffff;
            font-weight: 700;
        }
        
        /* Connection status */
        .connection-status {
            position: absolute;
            top: 10px;
            right: 20px;
            font-size: 0.9em;
            font-family: 'Share Tech Mono', monospace;
        }
        
        .connection-status.connected {
            color: #00ff00;
        }
        
        .connection-status.disconnected {
            color: #ff0066;
            animation: pulse 1s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        /* Log filters */
        .log-filters {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .log-filters button {
            padding: 8px 16px;
            background: rgba(0, 40, 80, 0.8);
            border: 1px solid #0088ff;
            color: #00ffff;
            font-family: 'Orbitron', monospace;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            font-size: 0.8em;
        }
        
        .log-filters button:hover {
            background: rgba(0, 80, 160, 0.8);
            border-color: #00ffff;
            transform: translateY(-2px);
        }
        
        .log-filters button.active {
            background: rgba(0, 255, 255, 0.2);
            border-color: #00ff00;
        }
        
        .log-section {
            margin-top: 40px;
        }
        
        .log-container {
            background: rgba(0, 10, 20, 0.9);
            border: 1px solid #0088ff;
            padding: 20px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.9em;
        }
        
        .log-entry {
            margin-bottom: 8px;
            padding: 4px 8px;
            border-left: 3px solid #0088ff;
        }
        
        .log-entry.success {
            border-left-color: #00ff00;
            color: #00ff00;
        }
        
        .log-entry.error {
            border-left-color: #ff0066;
            color: #ff0066;
        }
        
        .log-entry.warning {
            border-left-color: #ffaa00;
            color: #ffaa00;
        }
        
        ::-webkit-scrollbar {
            width: 12px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(0, 20, 40, 0.8);
            border: 1px solid #0088ff;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #0088ff;
            border: 1px solid #00ffff;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #00ffff;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>TOXIBOT v2.0</h1>
            <div id="status" class="status-indicator active">SYSTEM ACTIVE</div>
            <div class="connection-status connected" id="connection-status">● Connected</div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Wallet Balance</div>
                <div class="metric-value positive" id="wallet">0.00 SOL</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total P/L</div>
                <div class="metric-value" id="total-pl">+0.000</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value" id="winrate">0.0%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Active Positions</div>
                <div class="metric-value" id="positions-count">0</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Exposure</div>
                <div class="metric-value" id="exposure">0.000 SOL</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Daily Loss</div>
                <div class="metric-value negative" id="daily-loss">0.000 SOL</div>
            </div>
        </div>
        
        <div class="quick-stats">
            <span>🔥 Best Trade: <span id="best-trade">+0.000</span></span>
            <span>💀 Worst Trade: <span id="worst-trade">-0.000</span></span>
            <span>📊 Today's Trades: <span id="todays-trades">0</span></span>
            <span>⚡ Active Feeds: <span id="active-feeds">3</span></span>
        </div>
        
        <div class="bots-section">
            <div class="bot-card">
                <div class="bot-name">Ultra-Early Discovery</div>
                <div class="bot-stats">
                    <div class="stat-row">
                        <span>Trades</span>
                        <span id="ultra-trades">0/0</span>
                    </div>
                    <div class="stat-row">
                        <span>Win Rate</span>
                        <span id="ultra-winrate">0%</span>
                    </div>
                    <div class="stat-row">
                        <span>P/L</span>
                        <span id="ultra-pl">+0.000</span>
                    </div>
                </div>
            </div>
            
            <div class="bot-card">
                <div class="bot-name">2-Minute Scalper</div>
                <div class="bot-stats">
                    <div class="stat-row">
                        <span>Trades</span>
                        <span id="scalper-trades">0/0</span>
                    </div>
                    <div class="stat-row">
                        <span>Win Rate</span>
                        <span id="scalper-winrate">0%</span>
                    </div>
                    <div class="stat-row">
                        <span>P/L</span>
                        <span id="scalper-pl">+0.000</span>
                    </div>
                </div>
            </div>
            
            <div class="bot-card">
                <div class="bot-name">Community/Whale</div>
                <div class="bot-stats">
                    <div class="stat-row">
                        <span>Trades</span>
                        <span id="community-trades">0/0</span>
                    </div>
                    <div class="stat-row">
                        <span>Win Rate</span>
                        <span id="community-winrate">0%</span>
                    </div>
                    <div class="stat-row">
                        <span>P/L</span>
                        <span id="community-pl">+0.000</span>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="positions-section">
            <h2 class="section-title">Active Positions</h2>
            <table class="positions-table">
                <thead>
                    <tr>
                        <th>Token</th>
                        <th>Source</th>
                        <th>Size</th>
                        <th>Entry</th>
                        <th>Current</th>
                        <th>P/L</th>
                        <th>P/L %</th>
                        <th>Phase</th>
                        <th>Age</th>
                    </tr>
                </thead>
                <tbody id="positions-tbody"></tbody>
            </table>
        </div>
        
        <div class="log-section">
            <h2 class="section-title">System Activity</h2>
            <div class="log-filters">
                <button class="active" onclick="filterLog('all')">All</button>
                <button onclick="filterLog('buys')">Buys</button>
                <button onclick="filterLog('sells')">Sells</button>
                <button onclick="filterLog('errors')">Errors</button>
                <button onclick="filterLog('skipped')">Skipped</button>
            </div>
            <div class="log-container" id="log-container"></div>
        </div>
    </div>
    
    <script>
        // Fix WebSocket URL for Railway deployment
        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${location.host}/ws`;
        console.log('Connecting to WebSocket:', wsUrl);
        const ws = new WebSocket(wsUrl);
        
        let lastUpdate = Date.now();
        let allLogs = [];
        let currentFilter = 'all';
        let bestTrade = 0;
        let worstTrade = 0;
        let todaysTrades = 0;
        
        ws.onopen = function() {
            console.log('WebSocket connected!');
            document.getElementById('connection-status').className = 'connection-status connected';
            document.getElementById('connection-status').textContent = '● Connected';
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            document.getElementById('connection-status').className = 'connection-status disconnected';
            document.getElementById('connection-status').textContent = '● Connection Error';
        };
        
        function formatNumber(num, decimals = 3) {
            return parseFloat(num || 0).toFixed(decimals);
        }
        
        function formatAge(seconds) {
            if (!seconds) return '';
            const d = Math.floor(seconds / 86400);
            const h = Math.floor((seconds % 86400) / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            
            const parts = [];
            if (d) parts.push(`${d}d`);
            if (h) parts.push(`${h}h`);
            if (m) parts.push(`${m}m`);
            if (s && !d && !h) parts.push(`${s}s`);
            
            return parts.join(' ') || '0s';
        }
        
        function filterLog(filter) {
            currentFilter = filter;
            document.querySelectorAll('.log-filters button').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            updateLogDisplay();
        }
        
        function updateLogDisplay() {
            const logContainer = document.getElementById('log-container');
            let filtered = allLogs;
            
            if (currentFilter !== 'all') {
                filtered = allLogs.filter(entry => {
                    if (currentFilter === 'buys') return entry.includes('BUY');
                    if (currentFilter === 'sells') return entry.includes('Sold');
                    if (currentFilter === 'errors') return entry.includes('SL') || entry.includes('blacklist') || entry.includes('rejected');
                    if (currentFilter === 'skipped') return entry.includes('skipping') || entry.includes('FAIL');
                    return true;
                });
            }
            
            logContainer.innerHTML = filtered.map(entry => {
                let className = 'log-entry';
                if (entry.includes('BUY') || entry.includes('Sold')) className += ' success';
                else if (entry.includes('SL') || entry.includes('blacklist')) className += ' error';
                else if (entry.includes('skipping') || entry.includes('FAIL')) className += ' warning';
                return `<div class="${className}">${entry}</div>`;
            }).join('');
            logContainer.scrollTop = logContainer.scrollHeight;
        }
        
        // Connection status monitor
        setInterval(() => {
            const timeSinceUpdate = Date.now() - lastUpdate;
            const indicator = document.getElementById('connection-status');
            if (timeSinceUpdate > 5000) {
                indicator.className = 'connection-status disconnected';
                indicator.textContent = '● Disconnected';
            } else {
                indicator.className = 'connection-status connected';
                indicator.textContent = '● Connected';
            }
        }, 1000);
        
        ws.onmessage = function(event) {
            lastUpdate = Date.now();
            const data = JSON.parse(event.data);
            
            // Update status
            const statusEl = document.getElementById('status');
            const isActive = data.status && data.status.toLowerCase().includes('active');
            statusEl.className = `status-indicator ${isActive ? 'active' : 'inactive'}`;
            statusEl.textContent = isActive ? 'SYSTEM ACTIVE' : 'SYSTEM OFFLINE';
            
            // Update metrics
            document.getElementById('wallet').textContent = `${formatNumber(data.wallet_balance, 2)} SOL`;
            document.getElementById('total-pl').textContent = `${data.pl >= 0 ? '+' : ''}${formatNumber(data.pl)}`;
            document.getElementById('total-pl').className = `metric-value ${data.pl >= 0 ? 'positive' : 'negative'}`;
            document.getElementById('winrate').textContent = `${formatNumber(data.winrate, 1)}%`;
            document.getElementById('positions-count').textContent = Object.keys(data.positions || {}).length;
            document.getElementById('exposure').textContent = `${formatNumber(data.exposure)} SOL`;
            document.getElementById('daily-loss').textContent = `${formatNumber(data.daily_loss)} SOL`;
            
            // Update bot stats
            document.getElementById('ultra-trades').textContent = `${data.ultra_wins}/${data.ultra_total}`;
            document.getElementById('ultra-winrate').textContent = 
                `${data.ultra_total ? formatNumber(100 * data.ultra_wins / data.ultra_total, 1) : 0}%`;
            document.getElementById('ultra-pl').textContent = `${data.ultra_pl >= 0 ? '+' : ''}${formatNumber(data.ultra_pl)}`;
            document.getElementById('ultra-pl').className = data.ultra_pl >= 0 ? 'positive' : 'negative';
            
            document.getElementById('scalper-trades').textContent = `${data.scalper_wins}/${data.scalper_total}`;
            document.getElementById('scalper-winrate').textContent = 
                `${data.scalper_total ? formatNumber(100 * data.scalper_wins / data.scalper_total, 1) : 0}%`;
            document.getElementById('scalper-pl').textContent = `${data.scalper_pl >= 0 ? '+' : ''}${formatNumber(data.scalper_pl)}`;
            document.getElementById('scalper-pl').className = data.scalper_pl >= 0 ? 'positive' : 'negative';
            
            document.getElementById('community-trades').textContent = `${data.community_wins}/${data.community_total}`;
            document.getElementById('community-winrate').textContent = 
                `${data.community_total ? formatNumber(100 * data.community_wins / data.community_total, 1) : 0}%`;
            document.getElementById('community-pl').textContent = 
                `${data.community_pl >= 0 ? '+' : ''}${formatNumber(data.community_pl)}`;
            document.getElementById('community-pl').className = data.community_pl >= 0 ? 'positive' : 'negative';
            
            // Update quick stats
            todaysTrades = data.ultra_total + data.scalper_total + data.community_total;
            document.getElementById('todays-trades').textContent = todaysTrades;
            
            // Calculate best/worst trades from positions
            Object.values(data.positions || {}).forEach(pos => {
                const pl = pos.pl || 0;
                if (pl > bestTrade) bestTrade = pl;
                if (pl < worstTrade) worstTrade = pl;
            });
            
            document.getElementById('best-trade').textContent = `${bestTrade >= 0 ? '+' : ''}${formatNumber(bestTrade)}`;
            document.getElementById('best-trade').className = bestTrade >= 0 ? 'positive' : 'negative';
            document.getElementById('worst-trade').textContent = `${worstTrade >= 0 ? '+' : ''}${formatNumber(worstTrade)}`;
            document.getElementById('worst-trade').className = worstTrade >= 0 ? 'positive' : 'negative';
            
            // Update positions table with alerts
            const tbody = document.getElementById('positions-tbody');
            tbody.innerHTML = '';
            const now = Date.now() / 1000;
            
            Object.entries(data.positions || {}).forEach(([token, pos]) => {
                const entry = parseFloat(pos.entry_price || 0);
                const last = parseFloat(pos.last_price || entry);
                const size = parseFloat(pos.size || 0);
                const pl = (last - entry) * size;
                const plPct = entry ? 100 * (last - entry) / entry : 0;
                const age = now - (pos.buy_time || now);
                
                const row = tbody.insertRow();
                
                // Add alert classes
                if (plPct >= 50) row.classList.add('alert-profit');
                else if (plPct <= -20) row.classList.add('alert-loss');
                else if (age > 3600) row.classList.add('alert-old');
                
                row.innerHTML = `
                    <td style="color: #00ffff">${token.slice(0, 6)}...${token.slice(-4)}</td>
                    <td>${pos.src || ''}</td>
                    <td>${formatNumber(size)}</td>
                    <td>${formatNumber(entry, 6)}</td>
                    <td>${formatNumber(last, 6)}</td>
                    <td class="${pl >= 0 ? 'positive' : 'negative'}">${formatNumber(pl, 4)}</td>
                    <td class="${plPct >= 0 ? 'positive' : 'negative'}">${formatNumber(plPct, 2)}%</td>
                    <td>${pos.phase || ''}</td>
                    <td>${formatAge(age)}</td>
                `;
            });
            
            // Update activity log
            allLogs = data.log || [];
            updateLogDisplay();
        };
        
        ws.onclose = function() {
            setTimeout(() => { location.reload(); }, 5000);
        };
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'r' && e.ctrlKey) {
                e.preventDefault();
                location.reload();
            }
            if (e.key === 'c' && e.ctrlKey) {
                e.preventDefault();
                allLogs = [];
                updateLogDisplay();
            }
        });
    </script>
</body>
</html>
"""

# =====================================
# Dashboard HTTP and WebSocket
# =====================================
async def html_handler(request):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info("WebSocket client connected!")
    
    while True:
        try:
            data = {
                "status": "active",
                "wallet_balance": current_wallet_balance,
                "pl": get_total_pl(),
                "winrate": calc_winrate(),
                "positions": positions,
                "exposure": exposure,
                "daily_loss": daily_loss,
                "log": list(activity_log)[-40:],
                "ultra_wins": ultra_wins,
                "ultra_total": ultra_total,
                "ultra_pl": ultra_pl,
                "scalper_wins": scalper_wins,
                "scalper_total": scalper_total,
                "scalper_pl": scalper_pl,
                "community_wins": community_wins,
                "community_total": community_total,
                "community_pl": community_pl,
            }
            
            await ws.send_str(json.dumps(data))
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"WS send error: {e}")
            break
    
    return ws

async def health_handler(request):
    """Health check endpoint for monitoring"""
    health_data = {
        "status": "healthy",
        "uptime": time.time() - startup_time,
        "active_positions": len(positions),
        "total_pl": get_total_pl(),
        "wallet_balance": current_wallet_balance,
        "circuit_breakers": list(api_circuit_breakers.keys())
    }
    return web.json_response(health_data)

async def run_dashboard_server():
    app = web.Application()
    app.router.add_get('/', html_handler)
    app.router.add_get('/ws', ws_handler)
    app.router.add_get('/health', health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=PORT)
    await site.start()
    logger.info(f"Dashboard up at http://0.0.0.0:{PORT}")
    
    while True:
        await asyncio.sleep(3600)  # Keep running

# =====================================
# Main Bot Event Loop - FIXED
# =====================================
async def bot_main():
    global toxibot
    
    # Initialize database
    init_database()
    load_positions()
    
    # Connect to ToxiBot
    toxibot = ToxiBotClient(
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_STRING_SESSION,
        TOXIBOT_USERNAME
    )
    await toxibot.connect()
    
    # Start all feeds and managers - FIXED to use asyncio.create_task
    feeds = [
        # Position management
        update_position_prices_and_wallet(),
        
        # Risk management
        risk_management_monitor(),
        update_trading_parameters(),
        
        # Helius monitoring
        monitor_wallet_with_helius(),
        
        # Community trading
        community_trade_manager(toxibot),
    ]
    
    # Start data feeds as tasks - FIXED
    asyncio.create_task(pumpportal_newtoken_feed(
        lambda token, src: asyncio.create_task(process_token(token, src))
    ))
    
    asyncio.create_task(bitquery_polling_feed(
        lambda token, src, info=None: asyncio.create_task(process_token(token, src))
    ))
    
    # Add community signal aggregation - FIXED
    asyncio.create_task(bitquery_polling_feed(community_candidate_callback))
    
    await asyncio.gather(*feeds)

# =====================================
# Cleanup on Exit
# =====================================
async def cleanup():
    """Clean up resources on exit"""
    global session_pool
    
    logger.info("Shutting down...")
    
    # Close HTTP session
    if session_pool and not session_pool.closed:
        await session_pool.close()
    
    # Save final positions
    for token, pos in positions.items():
        save_position(token, pos)
    
    logger.info("Cleanup complete")

# =====================================
# Entry Point
# =====================================
startup_time = time.time()

async def main():
    # Set up signal handlers for graceful shutdown
    import signal
    signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(cleanup()))
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(cleanup()))
    
    task_dashboard = asyncio.create_task(run_dashboard_server())
    task_bot = asyncio.create_task(bot_main())
    
    try:
        await asyncio.gather(task_dashboard, task_bot)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        traceback.print_exc()
