"""
ZMN Bot Dashboard API -- WebSocket Server
==========================================
Serves the HTML dashboard and provides real-time data via WebSocket + REST API.

Authentication: JWT tokens signed with DASHBOARD_SECRET.
- POST /auth/login  -- authenticate and receive JWT
- GET  /auth/verify -- validate JWT
- All other routes require valid JWT in Authorization header
- WebSocket requires JWT as first message within 5 seconds
"""

import asyncio
import base64
import hashlib
import hmac
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
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
_db_url = os.getenv("DATABASE_URL", "toxibot.db")
DATABASE_PATH = _db_url.replace("sqlite:///", "") if _db_url.startswith("sqlite") else _db_url
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
HOLDING_WALLET_ADDRESS = os.getenv("HOLDING_WALLET_ADDRESS", "")
DASHBOARD_ALLOWED_IPS = os.getenv("DASHBOARD_ALLOWED_IPS", "").strip()
PORT = int(os.getenv("PORT", "8080"))

JWT_EXPIRY_SECONDS = 86400  # 24 hours

DASHBOARD_DIR = Path("dashboard")
_ws_clients: set[web.WebSocketResponse] = set()

# Rate limiting: {ip: [timestamp, timestamp, ...]}
_login_attempts: dict[str, list[float]] = {}
_blocked_ips: dict[str, float] = {}  # ip -> blocked_until


# ---------------------------------------------------------------------------
# JWT helpers (HMAC-SHA256, no external library)
# ---------------------------------------------------------------------------
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _create_jwt(secret: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
        "iat": int(time.time()),
        "sub": "dashboard",
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def _verify_jwt(token: str, secret: str) -> bool:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        signing_input = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        actual_sig = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False
        payload = json.loads(_b64url_decode(parts[1]))
        if time.time() > payload.get("exp", 0):
            return False
        return True
    except Exception:
        return False


def _get_jwt_from_request(request: web.Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


def _get_client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    peername = request.transport.get_extra_info("peername")
    return peername[0] if peername else "unknown"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def _check_rate_limit(ip: str) -> bool:
    """Returns True if the IP is allowed to attempt login."""
    now = time.time()
    # Check block list
    if ip in _blocked_ips:
        if now < _blocked_ips[ip]:
            return False
        del _blocked_ips[ip]

    return True


def _record_failed_attempt(ip: str):
    now = time.time()
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    # Keep only last hour
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < 3600]
    _login_attempts[ip].append(now)
    if len(_login_attempts[ip]) >= 5:
        _blocked_ips[ip] = now + 3600  # Block for 1 hour
        logger.warning("IP %s blocked for 1 hour after 5 failed login attempts", ip)


# ---------------------------------------------------------------------------
# IP whitelist middleware
# ---------------------------------------------------------------------------
@web.middleware
async def ip_whitelist_middleware(request: web.Request, handler):
    if DASHBOARD_ALLOWED_IPS:
        allowed = [ip.strip() for ip in DASHBOARD_ALLOWED_IPS.split(",") if ip.strip()]
        client_ip = _get_client_ip(request)
        if allowed and client_ip not in allowed:
            logger.warning("Request from non-whitelisted IP: %s", client_ip)
            return web.json_response({"error": "forbidden"}, status=403)
    return await handler(request)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------
PUBLIC_PATHS = {"/auth/login", "/api/health", "/helius-webhook", "/login.html"}


@web.middleware
async def auth_middleware(request: web.Request, handler):
    # Public paths skip auth
    if request.path in PUBLIC_PATHS:
        return await handler(request)

    # Static assets for login page
    if request.path.startswith("/css/") or request.path.startswith("/js/") or request.path.startswith("/img/"):
        return await handler(request)

    # Dashboard HTML files served without auth check (JS handles redirect)
    if request.path.startswith("/dashboard/") and request.path.endswith(".html"):
        return await handler(request)

    # Root serves dashboard.html (JS handles redirect)
    if request.path == "/":
        return await handler(request)

    # WebSocket handled separately (token check in handler)
    if request.path == "/ws":
        return await handler(request)

    # No secret configured -- skip auth entirely
    if not DASHBOARD_SECRET:
        return await handler(request)

    # All API routes require valid JWT
    token = _get_jwt_from_request(request)
    if _verify_jwt(token, DASHBOARD_SECRET):
        return await handler(request)

    return web.json_response({"error": "unauthorized"}, status=401)


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
async def auth_login(request):
    """POST /auth/login -- authenticate and return JWT."""
    if not DASHBOARD_SECRET:
        return web.json_response({"error": "DASHBOARD_SECRET not configured"}, status=500)

    ip = _get_client_ip(request)

    if not _check_rate_limit(ip):
        return web.json_response({"error": "too many attempts, try again later"}, status=429)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid request"}, status=400)

    password = body.get("password", "")

    if hmac.compare_digest(password, DASHBOARD_SECRET):
        token = _create_jwt(DASHBOARD_SECRET)
        logger.info("Successful login from %s", ip)
        return web.json_response({"token": token, "expires_in": JWT_EXPIRY_SECONDS})

    _record_failed_attempt(ip)
    logger.warning("Failed login attempt from %s", ip)
    return web.json_response({"error": "invalid credentials"}, status=401)


async def auth_verify(request):
    """GET /auth/verify -- validate JWT token."""
    token = _get_jwt_from_request(request)
    if _verify_jwt(token, DASHBOARD_SECRET):
        return web.json_response({"valid": True})
    return web.json_response({"valid": False}, status=401)


# ---------------------------------------------------------------------------
# Login page (serves login.html)
# ---------------------------------------------------------------------------
async def handle_login_page(request):
    path = DASHBOARD_DIR / "login.html"
    if path.exists():
        return web.FileResponse(path)
    return web.Response(text="Login page not found", status=404)


async def api_health(request):
    """Unauthenticated health check for Railway."""
    return web.json_response({"status": "ok"})


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
    if not address:
        return None
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getBalance",
        "params": [address],
    }
    async with aiohttp.ClientSession() as session:
        for rpc_url in (HELIUS_RPC_URL, HELIUS_GATEKEEPER_URL):
            if not rpc_url:
                continue
            try:
                async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    return result.get("result", {}).get("value", 0) / 1_000_000_000
            except Exception:
                continue
    return None


# --- REST API routes ---
async def handle_index(request):
    path = DASHBOARD_DIR / "dashboard.html"
    if path.exists():
        return web.FileResponse(path)
    return web.Response(text="Dashboard not found", status=404)


async def handle_static(request):
    filename = request.match_info.get("filename", "")
    path = DASHBOARD_DIR / filename
    if path.exists() and path.is_file():
        return web.FileResponse(path)
    return web.Response(text="Not found", status=404)


async def api_status(request):
    redis_conn = request.app.get("redis")
    status_data = {}
    if redis_conn:
        try:
            t0 = time.time()
            await redis_conn.ping()
            ping_ms = int((time.time() - t0) * 1000)
            status_data["_redis_connected"] = True
            status_data["_redis_ping_ms"] = ping_ms
            raw = await redis_conn.get("bot:status")
            if raw:
                status_data.update(json.loads(raw))
        except Exception as e:
            status_data["_redis_connected"] = False
            status_data["_redis_error"] = str(e)[:100]
    else:
        status_data["_redis_connected"] = False
        status_data["_redis_error"] = request.app.get("_redis_error", "REDIS_URL not set")

    trading_balance = await _get_sol_balance(TRADING_WALLET_ADDRESS)
    holding_balance = await _get_sol_balance(HOLDING_WALLET_ADDRESS)
    status_data["trading_wallet_balance"] = trading_balance
    status_data["holding_wallet_balance"] = holding_balance
    return web.json_response(status_data)


async def api_market_health(request):
    redis_conn = request.app.get("redis")
    if redis_conn:
        try:
            raw = await redis_conn.get("market:health")
            if raw:
                return web.json_response(json.loads(raw))
        except Exception:
            pass
    return web.json_response({"mode": "UNKNOWN"})


async def api_trades(request):
    limit = int(request.query.get("limit", "50"))
    trades = await _query_db("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,))
    return web.json_response(trades)


async def api_trades_active(request):
    trades = await _query_db("SELECT * FROM trades WHERE closed_at IS NULL ORDER BY created_at DESC")
    return web.json_response(trades)


async def api_personality_stats(request):
    stats = {}
    for personality in ["speed_demon", "analyst", "whale_tracker"]:
        rows = await _query_db(
            """SELECT COUNT(*) as total_trades,
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
            stats[personality] = {**row, "win_rate": round(wins / total * 100, 1) if total > 0 else 0}
        else:
            stats[personality] = {"total_trades": 0, "wins": 0, "losses": 0, "total_pnl_sol": 0}
    return web.json_response(stats)


async def api_treasury(request):
    sweeps = await _query_db("SELECT * FROM treasury_sweeps ORDER BY id DESC LIMIT 10")
    total_swept = await _query_db("SELECT COALESCE(SUM(amount_sol), 0) as total FROM treasury_sweeps WHERE status='success'")
    trading_balance = await _get_sol_balance(TRADING_WALLET_ADDRESS)
    holding_balance = await _get_sol_balance(HOLDING_WALLET_ADDRESS)
    return web.json_response({
        "sweeps": sweeps,
        "total_swept_sol": total_swept[0]["total"] if total_swept else 0,
        "trading_wallet_balance": trading_balance,
        "holding_wallet_balance": holding_balance,
    })


async def api_governance(request):
    notes_path = Path("data/governance_notes.md")
    content = notes_path.read_text() if notes_path.exists() else ""
    pending_exists = Path("data/whale_wallets_pending.json").exists()
    return web.json_response({"notes": content, "pending_whale_review": pending_exists})


async def api_ml_status(request):
    """ML model status from model_meta.json."""
    meta_path = Path("data/models/model_meta.json")
    result = {"trained": False, "sample_count": 0, "last_train_time": None, "accuracy_last_100": 0}
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                data = json.load(f)
            result["trained"] = True
            result["sample_count"] = data.get("sample_count", data.get("training_samples", 0))
            result["last_train_time"] = data.get("last_trained", data.get("trained_at", None))
            result["accuracy_last_100"] = data.get("accuracy", data.get("accuracy_last_100", 0))
            result["features"] = data.get("feature_importance", data.get("features", {}))
        except Exception:
            pass
    return web.json_response(result)


async def api_portfolio_history(request):
    snapshots = await _query_db("SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 288")
    return web.json_response(list(reversed(snapshots)))


async def api_paper_stats(request):
    """Paper trading stats from Redis."""
    redis_conn = request.app.get("redis")
    stats = {"total_trades": 0, "winning_trades": 0, "total_pnl_sol": 0, "win_rate": 0, "by_personality": {}}
    if redis_conn:
        try:
            raw = await redis_conn.hgetall("paper:stats")
            if raw:
                stats["total_trades"] = int(raw.get("total_trades", 0))
                stats["winning_trades"] = int(raw.get("winning_trades", 0))
                stats["total_pnl_sol"] = float(raw.get("total_pnl_sol", 0))
                if stats["total_trades"] > 0:
                    stats["win_rate"] = round(stats["winning_trades"] / stats["total_trades"] * 100, 1)
            for p in ["speed_demon", "analyst", "whale_tracker"]:
                praw = await redis_conn.hgetall(f"paper:stats:personality:{p}")
                stats["by_personality"][p] = {
                    "trades": int(praw.get("trades", 0)),
                    "pnl": float(praw.get("pnl", 0)),
                } if praw else {"trades": 0, "pnl": 0}
        except Exception:
            pass
    # Also check SQLite paper_trades table
    if stats["total_trades"] == 0:
        try:
            rows = await _query_db("SELECT COUNT(*) as cnt, COALESCE(SUM(realised_pnl_sol),0) as pnl, SUM(CASE WHEN realised_pnl_sol>0 THEN 1 ELSE 0 END) as wins FROM paper_trades WHERE exit_time IS NOT NULL")
            if rows and rows[0].get("cnt", 0) > 0:
                stats["total_trades"] = rows[0]["cnt"]
                stats["winning_trades"] = rows[0].get("wins", 0) or 0
                stats["total_pnl_sol"] = rows[0].get("pnl", 0) or 0
                stats["win_rate"] = round(stats["winning_trades"] / stats["total_trades"] * 100, 1) if stats["total_trades"] > 0 else 0
        except Exception:
            pass
    return web.json_response(stats)


async def api_emergency_stop(request):
    redis_conn = request.app.get("redis")
    if redis_conn:
        await redis_conn.publish("alerts:emergency", json.dumps({
            "reason": "Manual EMERGENCY_STOP from dashboard",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))
        return web.json_response({"status": "emergency_stop_triggered"})
    return web.json_response({"error": "Redis not available"}, status=503)


async def api_approve_parameter(request):
    """POST /approve-parameter -- approve a pending parameter change."""
    try:
        body = await request.json()
        param_index = body.get("index", -1)

        pending_path = Path("data/pending_parameters.json")
        active_path = Path("data/active_parameters.json")

        if not pending_path.exists():
            return web.json_response({"error": "no pending parameters"}, status=404)

        with open(pending_path) as f:
            pending = json.load(f)
        with open(active_path) as f:
            active = json.load(f) if active_path.exists() else []

        if param_index < 0 or param_index >= len(pending):
            return web.json_response({"error": "invalid index"}, status=400)

        item = pending.pop(param_index)
        item["status"] = "approved"
        item["approved_at"] = datetime.now(timezone.utc).isoformat()
        active.append(item)

        with open(pending_path, "w") as f:
            json.dump(pending, f, indent=2)
        with open(active_path, "w") as f:
            json.dump(active, f, indent=2)

        logger.info("Parameter approved: %s = %s", item["parameter"], item["proposed_value"])
        return web.json_response({"status": "approved", "parameter": item})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_sol_price(request):
    """SOL price — Binance primary (no auth), Jupiter V3 fallback."""
    # Binance — no auth needed
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ticker/price",
                                   params={"symbol": "SOLUSDT"},
                                   timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = float(data.get("price", 0))
                    if price > 0:
                        return web.json_response({"price": price})
    except Exception:
        pass
    # Jupiter V3 fallback
    try:
        jup_key = os.getenv("JUPITER_API_KEY", "").strip()
        headers = {"x-api-key": jup_key} if jup_key else {}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.jup.ag/price/v3",
                                   params={"ids": "So11111111111111111111111111111111111111112"},
                                   headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sol = data.get("data", {}).get("So11111111111111111111111111111111111111112", {})
                    price = sol.get("usdPrice") or sol.get("price", 0)
                    return web.json_response({"price": float(price) if price else 0})
    except Exception:
        pass
    return web.json_response({"price": 0})


async def api_trigger_health_check(request):
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "scripts/health_check.py",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=str(Path(__file__).parent.parent),
        )
        output_lines = []
        async for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(text)
            await _broadcast_ws({"_type": "health_check_line", "line": text})
        await proc.wait()
        await _broadcast_ws({"_type": "health_check_done", "exit_code": proc.returncode})
        return web.json_response({"status": "completed", "exit_code": proc.returncode})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


# --- Helius Webhook Receiver (no auth -- Helius calls directly) ---
async def handle_helius_webhook(request):
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    txs = payload if isinstance(payload, list) else [payload]
    redis_conn = request.app.get("redis")
    processed = 0

    for tx in txs:
        try:
            fee_payer = tx.get("feePayer", "")
            for transfer in tx.get("tokenTransfers", []):
                mint = transfer.get("mint", "")
                if not mint or mint == "So11111111111111111111111111111111111111112":
                    continue
                to_addr = transfer.get("toUserAccount", "")
                from_addr = transfer.get("fromUserAccount", "")
                action = "buy" if to_addr == fee_payer else "sell"
                signal = {
                    "mint": mint, "source": "helius_webhook",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "age_seconds": 0.0, "signal_type": "whale_trade",
                    "raw_data": {"wallet": fee_payer, "action": action,
                                 "token_amount": float(transfer.get("tokenAmount", 0) or 0),
                                 "signature": tx.get("signature", ""),
                                 "txType": action, "helius_webhook": True},
                }
                if TEST_MODE:
                    logger.info("Helius webhook [TEST]: %s %s", action, mint[:12])
                elif redis_conn:
                    await redis_conn.lpush("signals:raw", json.dumps(signal))
                processed += 1
        except Exception as e:
            logger.warning("Helius webhook parse error: %s", e)

    return web.json_response({"processed": processed})


# --- WebSocket handler with JWT auth ---
async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Require JWT as first message within 5 seconds
    if DASHBOARD_SECRET:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                token = data.get("token", "")
                if not _verify_jwt(token, DASHBOARD_SECRET):
                    await ws.send_json({"error": "unauthorized"})
                    await ws.close()
                    return ws
                await ws.send_json({"auth": "ok"})
            else:
                await ws.close()
                return ws
        except asyncio.TimeoutError:
            logger.warning("WebSocket auth timeout from %s", _get_client_ip(request))
            await ws.close()
            return ws
        except Exception:
            await ws.close()
            return ws

    _ws_clients.add(ws)
    logger.info("WebSocket authenticated (total: %d)", len(_ws_clients))

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
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
        logger.info("WebSocket disconnected (total: %d)", len(_ws_clients))

    return ws


async def _broadcast_ws(data: dict):
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


async def _redis_broadcaster(app: web.Application):
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


async def _periodic_push(app: web.Application):
    tick = 0
    while True:
        try:
            redis_conn = app.get("redis")
            status = {}
            if redis_conn:
                raw = await redis_conn.get("bot:status")
                if raw:
                    status = json.loads(raw)
            health = {}
            if redis_conn:
                raw = await redis_conn.get("market:health")
                if raw:
                    health = json.loads(raw)
            payload = {
                "_type": "periodic_update", "status": status,
                "market_health": health, "test_mode": TEST_MODE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if tick % 5 == 0:
                payload["trading_balance"] = await _get_sol_balance(TRADING_WALLET_ADDRESS)
                payload["holding_balance"] = await _get_sol_balance(HOLDING_WALLET_ADDRESS)

            # Paper stats + signals every 3rd tick (~6s)
            if redis_conn and tick % 3 == 0:
                try:
                    ps = await redis_conn.hgetall("paper:stats")
                    total = int(ps.get("total_trades", 0))
                    wins = int(ps.get("winning_trades", 0))
                    payload["paper_stats"] = {
                        "total_trades": total,
                        "winning_trades": wins,
                        "total_pnl_sol": float(ps.get("total_pnl_sol", 0)),
                        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
                    }
                except Exception:
                    pass
                try:
                    sigs = await redis_conn.lrange("signals:raw", 0, 9)
                    payload["recent_signals"] = [json.loads(s) for s in sigs if s]
                except Exception:
                    pass

            await _broadcast_ws(payload)
        except Exception as e:
            logger.debug("Periodic push error: %s", e)
        tick += 1
        await asyncio.sleep(2)


async def on_startup(app: web.Application):
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_conn.ping()
        app["redis"] = redis_conn
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)
        app["redis"] = None
        app["_redis_error"] = str(e)[:100]

    if DASHBOARD_SECRET:
        logger.info("Dashboard auth ENABLED (JWT)")
    else:
        logger.warning("Dashboard auth DISABLED -- set DASHBOARD_SECRET to enable")

    if DASHBOARD_ALLOWED_IPS:
        logger.info("IP whitelist active: %s", DASHBOARD_ALLOWED_IPS)

    app["bg_tasks"] = [
        asyncio.create_task(_redis_broadcaster(app)),
        asyncio.create_task(_periodic_push(app)),
    ]


async def on_cleanup(app: web.Application):
    for task in app.get("bg_tasks", []):
        task.cancel()
    redis_conn = app.get("redis")
    if redis_conn:
        await redis_conn.close()


def create_app() -> web.Application:
    app = web.Application(middlewares=[ip_whitelist_middleware, auth_middleware])

    # Public routes
    app.router.add_post("/auth/login", auth_login)
    app.router.add_get("/auth/verify", auth_verify)
    app.router.add_get("/login.html", handle_login_page)
    app.router.add_get("/api/health", api_health)
    app.router.add_post("/helius-webhook", handle_helius_webhook)

    # Dashboard routes (JWT checked by middleware for API, JS redirect for HTML)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/market-health", api_market_health)
    app.router.add_get("/api/trades", api_trades)
    app.router.add_get("/api/trades/active", api_trades_active)
    app.router.add_get("/api/personality-stats", api_personality_stats)
    app.router.add_get("/api/treasury", api_treasury)
    app.router.add_get("/api/governance", api_governance)
    app.router.add_get("/api/portfolio-history", api_portfolio_history)
    app.router.add_get("/api/ml-status", api_ml_status)
    app.router.add_get("/api/paper-stats", api_paper_stats)
    app.router.add_post("/api/emergency-stop", api_emergency_stop)
    app.router.add_post("/api/approve-parameter", api_approve_parameter)
    app.router.add_get("/api/sol-price", api_sol_price)
    app.router.add_post("/api/trigger-health-check", api_trigger_health_check)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/dashboard/{filename}", handle_static)

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
