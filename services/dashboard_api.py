"""
ToxiBot Dashboard API — WebSocket Server
==========================================
Serves the HTML dashboard and provides real-time data via WebSocket + REST API.
Feeds live data to dashboard pages:
- Bot status, portfolio, positions
- Market health and mode
- Trade history
- Treasury sweep data
- Governance notes
- ML model stats
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web
import aiosqlite
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("dashboard_api")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_PATH = os.getenv("DATABASE_PATH", "toxibot.db")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
HOLDING_WALLET_ADDRESS = os.getenv("HOLDING_WALLET_ADDRESS", "")
PORT = int(os.getenv("PORT", "8080"))

# Dashboard static files directory
DASHBOARD_DIR = Path("dashboard")

# Active WebSocket connections
_ws_clients: set[web.WebSocketResponse] = set()


# --- Database helpers ---
async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def _query_db(query: str, params: tuple = ()) -> list[dict]:
    db = await _get_db()
    try:
        cursor = await db.execute(query, params)
        cols = [d[0] for d in cursor.description] if cursor.description else []
        rows = await cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        logger.warning("DB query error: %s", e)
        return []
    finally:
        await db.close()


# --- Wallet balance helper ---
async def _get_sol_balance(address: str) -> float | None:
    if not HELIUS_RPC_URL or not address:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getBalance",
                "params": [address],
            }
            async with session.post(HELIUS_RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
                return result.get("result", {}).get("value", 0) / 1_000_000_000
    except Exception:
        return None


# --- REST API routes ---
async def handle_index(request):
    """Serve main dashboard page."""
    path = DASHBOARD_DIR / "dashboard.html"
    if path.exists():
        return web.FileResponse(path)
    return web.Response(text="Dashboard not found", status=404)


async def handle_static(request):
    """Serve static dashboard files."""
    filename = request.match_info.get("filename", "")
    path = DASHBOARD_DIR / filename
    if path.exists() and path.is_file():
        return web.FileResponse(path)
    return web.Response(text="Not found", status=404)


async def api_status(request):
    """Bot status overview."""
    redis_conn = request.app.get("redis")
    status_data = {}

    if redis_conn:
        try:
            raw = await redis_conn.get("bot:status")
            if raw:
                status_data = json.loads(raw)
        except Exception:
            pass

    # Get wallet balances
    trading_balance = await _get_sol_balance(TRADING_WALLET_ADDRESS)
    holding_balance = await _get_sol_balance(HOLDING_WALLET_ADDRESS)

    status_data["trading_wallet_balance"] = trading_balance
    status_data["holding_wallet_balance"] = holding_balance

    return web.json_response(status_data)


async def api_market_health(request):
    """Current market health data."""
    redis_conn = request.app.get("redis")
    if redis_conn:
        try:
            raw = await redis_conn.get("market:health")
            if raw:
                return web.json_response(json.loads(raw))
        except Exception:
            pass
    return web.json_response({"mode": "UNKNOWN", "error": "No market data available"})


async def api_trades(request):
    """Recent trades (last 50)."""
    limit = int(request.query.get("limit", "50"))
    trades = await _query_db(
        "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    return web.json_response(trades)


async def api_trades_active(request):
    """Active (open) trades."""
    trades = await _query_db(
        "SELECT * FROM trades WHERE closed_at IS NULL ORDER BY created_at DESC"
    )
    return web.json_response(trades)


async def api_personality_stats(request):
    """Per-personality performance stats."""
    stats = {}
    for personality in ["speed_demon", "analyst", "whale_tracker"]:
        rows = await _query_db(
            """SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN outcome='profit' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(pnl_sol), 0) as total_pnl_sol,
                COALESCE(AVG(pnl_pct), 0) as avg_pnl_pct,
                COALESCE(MAX(pnl_sol), 0) as best_trade_sol,
                COALESCE(MIN(pnl_sol), 0) as worst_trade_sol
            FROM trades WHERE personality = ? AND outcome IS NOT NULL""",
            (personality,),
        )
        if rows:
            row = rows[0]
            total = row.get("total_trades", 0)
            wins = row.get("wins", 0)
            stats[personality] = {
                **row,
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            }
        else:
            stats[personality] = {"total_trades": 0, "wins": 0, "losses": 0, "total_pnl_sol": 0}

    return web.json_response(stats)


async def api_treasury(request):
    """Treasury sweep data."""
    sweeps = await _query_db(
        "SELECT * FROM treasury_sweeps ORDER BY id DESC LIMIT 10"
    )
    total_swept = await _query_db(
        "SELECT COALESCE(SUM(amount_sol), 0) as total FROM treasury_sweeps WHERE status='success'"
    )

    trading_balance = await _get_sol_balance(TRADING_WALLET_ADDRESS)
    holding_balance = await _get_sol_balance(HOLDING_WALLET_ADDRESS)

    return web.json_response({
        "sweeps": sweeps,
        "total_swept_sol": total_swept[0]["total"] if total_swept else 0,
        "trading_wallet_balance": trading_balance,
        "holding_wallet_balance": holding_balance,
        "trigger_threshold": 30.0,
        "target_balance": 25.0,
    })


async def api_governance(request):
    """Latest governance notes."""
    notes_path = Path("data/governance_notes.md")
    content = ""
    if notes_path.exists():
        content = notes_path.read_text()

    # Check for pending whale wallet review
    pending_exists = Path("data/whale_wallets_pending.json").exists()

    return web.json_response({
        "notes": content,
        "pending_whale_review": pending_exists,
    })


async def api_portfolio_history(request):
    """Portfolio value over time."""
    snapshots = await _query_db(
        "SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 288"  # ~24h at 5-min intervals
    )
    return web.json_response(list(reversed(snapshots)))


async def api_emergency_stop(request):
    """Trigger EMERGENCY_STOP from dashboard."""
    redis_conn = request.app.get("redis")
    if redis_conn:
        await redis_conn.publish("alerts:emergency", json.dumps({
            "reason": "Manual EMERGENCY_STOP from dashboard",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        return web.json_response({"status": "emergency_stop_triggered"})
    return web.json_response({"error": "Redis not available"}, status=503)


# --- WebSocket handler ---
async def ws_handler(request):
    """WebSocket endpoint for real-time dashboard updates."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _ws_clients.add(ws)
    logger.info("WebSocket client connected (total: %d)", len(_ws_clients))

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Handle client messages (e.g., subscribe to specific channels)
                try:
                    data = json.loads(msg.data)
                    if data.get("action") == "ping":
                        await ws.send_json({"action": "pong"})
                except json.JSONDecodeError:
                    pass
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    finally:
        _ws_clients.discard(ws)
        logger.info("WebSocket client disconnected (total: %d)", len(_ws_clients))

    return ws


async def _broadcast_ws(data: dict):
    """Broadcast data to all connected WebSocket clients."""
    if not _ws_clients:
        return
    msg = json.dumps(data)
    closed = set()
    for ws in _ws_clients:
        try:
            await ws.send_str(msg)
        except Exception:
            closed.add(ws)
    _ws_clients.difference_update(closed)


# --- Redis subscriber for real-time broadcasts ---
async def _redis_broadcaster(app: web.Application):
    """Subscribe to Redis channels and broadcast to WebSocket clients."""
    redis_conn = app.get("redis")
    if not redis_conn:
        return

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("bot:status", "market:mode", "alerts:emergency")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            data["_channel"] = message["channel"]
            await _broadcast_ws(data)
        except Exception:
            pass


# --- Periodic data push ---
async def _periodic_push(app: web.Application):
    """Push periodic updates to WebSocket clients."""
    while True:
        try:
            redis_conn = app.get("redis")

            # Get current status
            status = {}
            if redis_conn:
                raw = await redis_conn.get("bot:status")
                if raw:
                    status = json.loads(raw)

            # Get market health
            health = {}
            if redis_conn:
                raw = await redis_conn.get("market:health")
                if raw:
                    health = json.loads(raw)

            await _broadcast_ws({
                "_type": "periodic_update",
                "status": status,
                "market_health": health,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.debug("Periodic push error: %s", e)

        await asyncio.sleep(5)


# --- App lifecycle ---
async def on_startup(app: web.Application):
    """Initialize Redis and start background tasks."""
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_conn.ping()
        app["redis"] = redis_conn
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s — running without real-time data", e)
        app["redis"] = None

    app["bg_tasks"] = []
    app["bg_tasks"].append(asyncio.create_task(_redis_broadcaster(app)))
    app["bg_tasks"].append(asyncio.create_task(_periodic_push(app)))


async def on_cleanup(app: web.Application):
    for task in app.get("bg_tasks", []):
        task.cancel()
    redis_conn = app.get("redis")
    if redis_conn:
        await redis_conn.close()


def create_app() -> web.Application:
    app = web.Application()

    # API routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/market-health", api_market_health)
    app.router.add_get("/api/trades", api_trades)
    app.router.add_get("/api/trades/active", api_trades_active)
    app.router.add_get("/api/personality-stats", api_personality_stats)
    app.router.add_get("/api/treasury", api_treasury)
    app.router.add_get("/api/governance", api_governance)
    app.router.add_get("/api/portfolio-history", api_portfolio_history)
    app.router.add_post("/api/emergency-stop", api_emergency_stop)
    app.router.add_get("/ws", ws_handler)

    # Static dashboard files
    app.router.add_get("/dashboard/{filename}", handle_static)

    # Serve CSS/JS/img from project root directories
    for static_dir in ["css", "js", "img", "svg", "static"]:
        dir_path = Path(static_dir)
        if dir_path.exists():
            app.router.add_static(f"/{static_dir}", dir_path)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


if __name__ == "__main__":
    logger.info("Dashboard API starting on port %d", PORT)
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
