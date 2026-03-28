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
import redis.asyncio as aioredis
from dotenv import load_dotenv

from services.db import get_pool
from services.constants import CEX_ADDRESSES, SOL_MINT

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("dashboard_api")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
HELIUS_GATEKEEPER_URL = os.getenv("HELIUS_GATEKEEPER_URL", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
HOLDING_WALLET_ADDRESS = os.getenv("HOLDING_WALLET_ADDRESS", "")
DASHBOARD_ALLOWED_IPS = os.getenv("DASHBOARD_ALLOWED_IPS", "").strip()
HELIUS_WEBHOOK_SECRET = os.getenv("HELIUS_WEBHOOK_SECRET", "")
APP_VERSION = os.getenv("APP_VERSION", "v3.1.0")
TREASURY_TRIGGER_SOL = float(os.getenv("TREASURY_TRIGGER_SOL", "30.0"))
TREASURY_TARGET_SOL = float(os.getenv("TREASURY_TARGET_SOL", "25.0"))
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
    """Returns True if the IP is allowed to attempt login (not rate-limited)."""
    now = time.time()
    if ip in _blocked_ips:
        if now < _blocked_ips[ip]:
            return False
        del _blocked_ips[ip]
    # Sliding window: count attempts in last 10 minutes
    if ip in _login_attempts:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < 600]
        if len(_login_attempts[ip]) >= 5:
            _blocked_ips[ip] = now + 3600
            logger.warning("IP %s rate-limited after 5 attempts in 10 minutes", ip)
            return False
    return True


def _record_failed_attempt(ip: str):
    now = time.time()
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(now)
    if len([t for t in _login_attempts[ip] if now - t < 600]) >= 5:
        _blocked_ips[ip] = now + 3600
        logger.warning("IP %s blocked for 1 hour", ip)


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
        logger.warning("Auth disabled — issuing dev token (set DASHBOARD_SECRET for production)")
        return web.json_response({"token": "dev-no-auth", "expires_in": 3600})

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
async def _query_db(query: str, *args) -> list[dict]:
    try:
        pool = await get_pool()
        rows = await pool.fetch(query, *args)
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("DB query error: %s", e)
        return []


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
    status_data["app_version"] = APP_VERSION
    status_data["test_mode"] = TEST_MODE
    return web.json_response(status_data)


async def api_stats(request):
    """Overall performance stats from paper_trades + trades tables."""
    result = {
        "total_trades": 0, "winning_trades": 0, "win_rate": 0.0,
        "total_pnl_sol": 0.0, "total_pnl_pct": 0.0,
        "best_trade_pnl": 0.0, "worst_trade_pnl": 0.0,
        "avg_hold_minutes": 0.0,
        "by_personality": {
            p: {"trades": 0, "wins": 0, "pnl_sol": 0.0}
            for p in ["speed_demon", "analyst", "whale_tracker"]
        },
    }
    try:
        rows = await _query_db(
            """SELECT COUNT(*) as total,
                SUM(CASE WHEN realised_pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(realised_pnl_sol), 0) as pnl,
                COALESCE(MAX(realised_pnl_sol), 0) as best,
                COALESCE(MIN(realised_pnl_sol), 0) as worst,
                COALESCE(AVG(hold_seconds), 0) as avg_hold
            FROM paper_trades WHERE exit_time IS NOT NULL""")
        if rows and rows[0]["total"] > 0:
            r = rows[0]
            result["total_trades"] = r["total"]
            result["winning_trades"] = r["wins"] or 0
            result["win_rate"] = round((r["wins"] or 0) / r["total"] * 100, 1) if r["total"] > 0 else 0
            result["total_pnl_sol"] = round(r["pnl"] or 0, 4)
            starting = float(os.getenv("STARTING_CAPITAL_SOL", "20"))
            result["total_pnl_pct"] = round((r["pnl"] or 0) / starting * 100, 2) if starting > 0 else 0
            result["best_trade_pnl"] = round(r["best"] or 0, 4)
            result["worst_trade_pnl"] = round(r["worst"] or 0, 4)
            result["avg_hold_minutes"] = round((r["avg_hold"] or 0) / 60, 1)

        for p in ["speed_demon", "analyst", "whale_tracker"]:
            prows = await _query_db(
                """SELECT COUNT(*) as trades,
                    SUM(CASE WHEN realised_pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(realised_pnl_sol), 0) as pnl
                FROM paper_trades WHERE exit_time IS NOT NULL AND personality = $1""", p)
            if prows and prows[0]["trades"] > 0:
                result["by_personality"][p] = {
                    "trades": prows[0]["trades"],
                    "wins": prows[0]["wins"] or 0,
                    "pnl_sol": round(prows[0]["pnl"] or 0, 4),
                }
    except Exception as e:
        logger.warning("api_stats error: %s", e)
    return web.json_response(result)


async def api_positions(request):
    """Return currently open positions from Redis bot:status, enriched with live price and P/L."""
    positions = []
    redis_conn = request.app.get("redis")
    if not redis_conn:
        return web.json_response(positions)
    try:
        raw = await redis_conn.get("bot:status")
        if not raw:
            return web.json_response(positions)
        status = json.loads(raw)
        now = time.time()
        for key, pos in status.get("positions", {}).items():
            mint = pos.get("mint", "")
            entry_price = float(pos.get("entry_price", 0) or 0)
            current_price = float(pos.get("current_price", 0) or 0)
            remaining_pct = float(pos.get("remaining_pct", 1.0))
            size_sol = float(pos.get("size_sol", 0))
            entry_time = float(pos.get("entry_time", 0) or 0)

            # Fallback: fetch live price from GeckoTerminal if bot_core hasn't populated it
            if current_price <= 0 and mint and entry_price > 0:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}",
                            headers={"Accept": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=4),
                        ) as r:
                            if r.status == 200:
                                d = await r.json()
                                price_str = d.get("data", {}).get("attributes", {}).get("price_usd")
                                if price_str:
                                    current_price = float(price_str)
                except Exception:
                    pass

            unrealised_pnl_sol = None
            unrealised_pnl_pct = None
            if entry_price > 0 and current_price > 0:
                unrealised_pnl_pct = (current_price - entry_price) / entry_price * 100
                unrealised_pnl_sol = (current_price - entry_price) / entry_price * size_sol * remaining_pct

            hold_seconds = int(now - entry_time) if entry_time > 0 else 0

            positions.append({
                "key": key,
                "mint": mint,
                "mint_short": mint[:6] + "..." + mint[-4:] if len(mint) > 10 else mint,
                "personality": pos.get("personality", ""),
                "size_sol": size_sol,
                "entry_price": entry_price,
                "current_price": current_price,
                "remaining_pct": remaining_pct,
                "entry_time": entry_time,
                "hold_seconds": hold_seconds,
                "unrealised_pnl_sol": round(unrealised_pnl_sol, 6) if unrealised_pnl_sol is not None else None,
                "unrealised_pnl_pct": round(unrealised_pnl_pct, 2) if unrealised_pnl_pct is not None else None,
                "trailing_stop_active": pos.get("trailing_stop_active", False),
                "trailing_stop_price": pos.get("trailing_stop_price"),
                "peak_price": pos.get("peak_price"),
            })
    except Exception as e:
        logger.warning("api_positions error: %s", e)
    return web.json_response(positions)


async def api_market(request):
    """Return current market data from Redis market:health + market:session."""
    result = {
        "mode": "UNKNOWN", "sentiment_score": 0, "sol_price": 0,
        "sol_1h_change": 0, "sol_24h_change": 0, "dex_volume_24h": 0,
        "cfgi": 50, "session": "UNKNOWN", "session_quality": "unknown",
        "timestamp": None,
    }
    redis_conn = request.app.get("redis")
    if redis_conn:
        try:
            raw = await redis_conn.get("market:health")
            if raw:
                result.update(json.loads(raw))
            sess_raw = await redis_conn.get("market:session")
            if sess_raw:
                sess = json.loads(sess_raw)
                result["session"] = sess.get("session", "UNKNOWN")
                result["session_quality"] = sess.get("quality", "unknown")
        except Exception:
            pass
    return web.json_response(result)


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


def _safe_isoformat(val) -> str | None:
    """Convert a timestamp to ISO string. Handles datetime objects, unix floats/ints, and None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    try:
        return datetime.fromtimestamp(float(val), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(val) if val else None


async def api_trades(request):
    """Return last N closed paper trades with formatted fields."""
    limit = int(request.query.get("limit", "50"))
    rows = await _query_db(
        "SELECT * FROM paper_trades WHERE exit_time IS NOT NULL ORDER BY exit_time DESC LIMIT $1", limit)
    trades = []
    for r in rows:
        mint = r.get("mint", "")
        trades.append({
            "id": r.get("id"),
            "mint": mint,
            "mint_short": mint[:6] + "..." if len(mint) > 6 else mint,
            "personality": r.get("personality", ""),
            "entry_price": float(r.get("entry_price", 0) or 0),
            "exit_price": float(r.get("exit_price", 0) or 0),
            "amount_sol": float(r.get("amount_sol", 0) or 0),
            "pnl_sol": float(r.get("realised_pnl_sol", 0) or 0),
            "pnl_pct": float(r.get("realised_pnl_pct", 0) or 0),
            "exit_reason": r.get("exit_reason", ""),
            "hold_seconds": float(r.get("hold_seconds", 0) or 0),
            "ml_score": float(r.get("ml_score", 0) or 0),
            "signal_source": r.get("signal_source", ""),
            "entry_time": _safe_isoformat(r.get("entry_time")),
            "exit_time": _safe_isoformat(r.get("exit_time")),
        })
    return web.json_response(trades)


async def api_trades_active(request):
    """Return currently open trades with explicit field mapping."""
    # Try paper_trades first (paper mode), fall back to trades
    rows = await _query_db("SELECT * FROM paper_trades WHERE exit_time IS NULL ORDER BY entry_time DESC")
    using_paper = bool(rows)
    if not rows:
        rows = await _query_db("SELECT * FROM trades WHERE closed_at IS NULL ORDER BY created_at DESC")
    trades = []
    for r in rows:
        mint = r.get("mint", "")
        # Field names differ between paper_trades (realised_pnl_sol) and trades (pnl_sol)
        if using_paper:
            pnl_sol = float(r.get("realised_pnl_sol", 0) or 0)
            pnl_pct = float(r.get("realised_pnl_pct", 0) or 0)
            created_at = _safe_isoformat(r.get("entry_time"))
        else:
            pnl_sol = float(r.get("pnl_sol", 0) or 0)
            pnl_pct = float(r.get("pnl_pct", 0) or 0)
            created_at = _safe_isoformat(r.get("created_at"))
        trades.append({
            "id": r.get("id"),
            "mint": mint,
            "mint_short": mint[:6] + "..." if len(mint) > 6 else mint,
            "personality": r.get("personality", ""),
            "entry_price": float(r.get("entry_price", 0) or 0),
            "amount_sol": float(r.get("amount_sol", 0) or 0),
            "pnl_sol": pnl_sol,
            "pnl_pct": pnl_pct,
            "ml_score": float(r.get("ml_score", r.get("ml_score_at_entry", 0)) or 0),
            "signal_source": r.get("signal_source", ""),
            "created_at": created_at,
            "is_open": True,
            # Trailing stop state from PostgreSQL
            "peak_price": float(r.get("peak_price", 0) or 0),
            "trailing_stop_active": bool(r.get("trailing_stop_active", False)),
            "trailing_stop_price": float(r.get("trailing_stop_price", 0) or 0),
            "trailing_stop_pct": float(r.get("trailing_stop_pct", 0) or 0),
        })
    return web.json_response(trades)


async def api_personality_stats(request):
    """Per-personality stats — queries paper_trades first, falls back to trades table."""
    stats = {}
    for personality in ["speed_demon", "analyst", "whale_tracker"]:
        # Try paper_trades first (primary in paper mode)
        rows = await _query_db(
            """SELECT COUNT(*) as total_trades,
                SUM(CASE WHEN realised_pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realised_pnl_sol <= 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(realised_pnl_sol), 0) as total_pnl_sol
            FROM paper_trades WHERE exit_time IS NOT NULL AND personality = $1""",
            personality,
        )
        if rows and rows[0].get("total_trades", 0) > 0:
            row = rows[0]
            total = row["total_trades"]
            wins = row.get("wins", 0) or 0
            stats[personality] = {
                "total_trades": total,
                "wins": wins,
                "losses": row.get("losses", 0) or 0,
                "total_pnl_sol": float(row.get("total_pnl_sol", 0) or 0),
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            }
            continue
        # Fallback to trades table
        rows = await _query_db(
            """SELECT COUNT(*) as total_trades,
                SUM(CASE WHEN outcome='profit' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(pnl_sol), 0) as total_pnl_sol
            FROM trades WHERE personality = $1 AND outcome IS NOT NULL""",
            personality,
        )
        if rows and rows[0].get("total_trades", 0) > 0:
            row = rows[0]
            total = row["total_trades"]
            wins = row.get("wins", 0) or 0
            stats[personality] = {
                "total_trades": total,
                "wins": wins,
                "losses": row.get("losses", 0) or 0,
                "total_pnl_sol": float(row.get("total_pnl_sol", 0) or 0),
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            }
        else:
            stats[personality] = {"total_trades": 0, "wins": 0, "losses": 0, "total_pnl_sol": 0, "win_rate": 0}
    return web.json_response(stats)


async def api_treasury(request):
    sweeps = await _query_db("SELECT * FROM treasury_sweeps ORDER BY id DESC LIMIT 10")
    total_swept = await _query_db("SELECT COALESCE(SUM(amount_sol), 0) as total FROM treasury_sweeps WHERE status='success'")
    trading_balance = await _get_sol_balance(TRADING_WALLET_ADDRESS)
    holding_balance = await _get_sol_balance(HOLDING_WALLET_ADDRESS)
    last_sweep = sweeps[0] if sweeps else None
    return web.json_response({
        "trading_balance": trading_balance,
        "holding_balance": holding_balance,
        "trigger_threshold": TREASURY_TRIGGER_SOL,
        "target_balance": TREASURY_TARGET_SOL,
        "total_swept": total_swept[0]["total"] if total_swept else 0,
        "last_sweep": last_sweep,
        "sweeps": sweeps,
    })


async def api_governance(request):
    """Governance status — reads from PostgreSQL first, file fallback."""
    result = {"notes": "", "pending_whale_review": False, "recent_decisions": [], "notes_length": 0}
    try:
        rows = await _query_db(
            "SELECT content, appended_at FROM governance_notes_log ORDER BY appended_at DESC LIMIT 50"
        )
        if rows:
            combined = "\n".join(r["content"] for r in reversed(rows))
            result["notes"] = combined[-2000:]
            result["notes_length"] = len(combined)
        decisions = await _query_db(
            """SELECT decision, reason, created_at, triggered_by
               FROM governance_state ORDER BY created_at DESC LIMIT 5"""
        )
        result["recent_decisions"] = [
            {k: (str(v) if v else v) for k, v in d.items()} for d in decisions
        ]
    except Exception as e:
        logger.warning("api_governance DB read failed: %s — trying file", e)
        notes_path = Path("data/governance_notes.md")
        if notes_path.exists():
            content = notes_path.read_text()
            result["notes"] = content[-2000:]
            result["notes_length"] = len(content)
    result["pending_whale_review"] = Path("data/whale_wallets_pending.json").exists()
    return web.json_response(result)


async def api_ml_status(request):
    """ML model status — PostgreSQL primary, file fallback."""
    result = {
        "trained": False, "sample_count": 0, "last_train_time": None,
        "accuracy_last_100": None, "features": [], "bootstrap_mode": True,
        "labelled_samples_for_training": 0, "samples_needed_for_first_train": 50,
        "cold_start_progress_pct": 0,
    }
    # PRIMARY: PostgreSQL ml_models table
    try:
        pool = await get_pool()
        row = await pool.fetchrow(
            """SELECT meta_json, trained_at, sample_count, accuracy
               FROM ml_models WHERE is_active = TRUE
               ORDER BY trained_at DESC LIMIT 1"""
        )
        if row:
            meta = json.loads(row["meta_json"] or "{}")
            sc = row["sample_count"] or 0
            result["trained"] = sc >= 50
            result["bootstrap_mode"] = sc < 200
            result["sample_count"] = sc
            result["last_train_time"] = row["trained_at"].isoformat() if row["trained_at"] else None
            result["accuracy_last_100"] = float(row["accuracy"] or 0) or meta.get("accuracy_last_100")
            fi = meta.get("feature_importance", {})
            result["features"] = fi if isinstance(fi, dict) and fi else meta.get("features", [])
    except Exception as e:
        logger.debug("api_ml_status DB read: %s — trying file", e)
        # FALLBACK: meta file
        meta_path = Path("data/models/model_meta.json")
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    data = json.load(f)
                sc = data.get("sample_count", 0)
                result["trained"] = sc >= 50
                result["bootstrap_mode"] = sc < 200
                result["sample_count"] = sc
                result["last_train_time"] = data.get("last_train_time", data.get("last_trained"))
                result["accuracy_last_100"] = data.get("accuracy_last_100")
                fi = data.get("feature_importance", {})
                result["features"] = fi if isinstance(fi, dict) and fi else data.get("features", [])
            except Exception:
                pass
    # Count labelled samples ready for training (cold-start progress)
    try:
        rows = await _query_db(
            "SELECT COUNT(*) as cnt FROM trades WHERE features_json IS NOT NULL AND outcome IS NOT NULL"
        )
        if rows:
            labelled = rows[0].get("cnt", 0) or 0
            result["labelled_samples_for_training"] = labelled
            result["sample_count"] = max(result["sample_count"], labelled)
            result["cold_start_progress_pct"] = min(100, round(labelled / 50 * 100, 1))
    except Exception:
        pass
    return web.json_response(result)


async def api_portfolio_history(request):
    """Portfolio snapshots with explicit field mapping to avoid serialisation crashes."""
    rows = await _query_db("SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 288")
    result = []
    for r in rows:
        result.append({
            "id": r.get("id"),
            "timestamp": str(r.get("timestamp", "")),
            "total_balance_sol": float(r.get("total_balance_sol", 0) or 0),
            "open_positions": int(r.get("open_positions", 0) or 0),
            "daily_pnl_sol": float(r.get("daily_pnl_sol", 0) or 0),
            "market_mode": r.get("market_mode", "NORMAL"),
        })
    return web.json_response(list(reversed(result)))


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
    # Also check PostgreSQL paper_trades table
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


async def api_service_health(request):
    """Return health status of all services from Redis cache or live checks."""
    result = {}
    redis_conn = request.app.get("redis")
    if redis_conn:
        try:
            cached = await redis_conn.get("service:health")
            if cached:
                return web.json_response(json.loads(cached))
        except Exception:
            pass
    # If no cache, return basic status
    redis_ok = False
    redis_ms = None
    if redis_conn:
        try:
            t0 = time.time()
            await redis_conn.ping()
            redis_ms = int((time.time() - t0) * 1000)
            redis_ok = True
        except Exception:
            pass
    result["redis"] = {"status": "ok" if redis_ok else "down", "latency_ms": redis_ms, "detail": "connected" if redis_ok else "disconnected"}
    # Check if PumpPortal is live via recent signals
    pp_status = "down"
    if redis_conn:
        try:
            sigs = await redis_conn.lrange("signals:raw", 0, 0)
            if sigs:
                sig = json.loads(sigs[0])
                ts = sig.get("timestamp", "")
                if ts:
                    from datetime import datetime as dt
                    sig_time = dt.fromisoformat(ts.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - sig_time).total_seconds()
                    pp_status = "live" if age < 120 else "warn"
        except Exception:
            pass
    result["pumpportal"] = {"status": pp_status, "latency_ms": None, "detail": "websocket stream"}
    # Market health age check
    mh_status = "down"
    if redis_conn:
        try:
            raw = await redis_conn.get("market:health")
            if raw:
                mh = json.loads(raw)
                ts = mh.get("timestamp", "")
                if ts:
                    mh_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - mh_time).total_seconds()
                    mh_status = "ok" if age < 300 else "warn"
        except Exception:
            pass
    for svc in ["gecko", "defillama", "dexpaprika"]:
        result[svc] = {"status": mh_status, "latency_ms": None, "detail": "via market_health"}
    # Services without cached data — show unknown (real checks run in background task)
    for svc in ["jupiter", "jito", "helius_rpc", "helius_parse", "helius_gatekeeper",
                 "rugcheck", "vybe", "nansen", "anthropic", "discord_webhook", "discord_bot"]:
        if svc not in result:
            result[svc] = {"status": "unknown", "latency_ms": None, "detail": "waiting for health check"}
    return web.json_response(result)


async def api_whale_activity(request):
    """Return recent whale/smart money signals from Redis."""
    result = []
    redis_conn = request.app.get("redis")
    if redis_conn:
        try:
            sigs = await redis_conn.lrange("signals:raw", 0, 49)
            for raw in sigs:
                try:
                    sig = json.loads(raw)
                    source = sig.get("source", "")
                    sig_type = sig.get("signal_type", "")
                    is_whale = (source in ("helius_webhook", "helius_whale", "nansen_discord") or
                                sig_type in ("whale_entry", "account_trade", "whale_trade"))
                    if not is_whale:
                        continue
                    rd = sig.get("raw_data", {})
                    result.append({
                        "wallet": rd.get("wallet", rd.get("traderPublicKey", "")),
                        "wallet_short": rd.get("wallet", rd.get("traderPublicKey", ""))[:12],
                        "action": rd.get("action", rd.get("txType", "unknown")),
                        "mint": sig.get("mint", "")[:12],
                        "signal_type": sig_type,
                        "source": source,
                        "timestamp": sig.get("timestamp", ""),
                        "token_amount": rd.get("token_amount", 0),
                    })
                    if len(result) >= 20:
                        break
                except Exception:
                    continue
        except Exception:
            pass
    return web.json_response(result)


async def api_wallets(request):
    """Return all active wallets from PostgreSQL grouped by personality_route."""
    try:
        from services.nansen_wallet_fetcher import get_active_wallets
        all_wallets = await get_active_wallets()
        grouped = {"whale_tracker": [], "analyst": [], "both": []}
        for w in all_wallets:
            route = w.get("personality_route", "whale_tracker")
            if route in grouped:
                grouped[route].append(w)
            else:
                grouped["whale_tracker"].append(w)
        last_refresh = await _query_db("SELECT MAX(refreshed_at) as ts FROM wallet_refresh_log")
        return web.json_response({
            **grouped,
            "total": len(all_wallets),
            "last_refresh": str(last_refresh[0]["ts"]) if last_refresh and last_refresh[0].get("ts") else None,
        })
    except Exception as e:
        logger.warning("api_wallets error: %s", e)
        return web.json_response({"whale_tracker": [], "analyst": [], "both": [], "total": 0, "last_refresh": None})


async def api_wallets_refresh_log(request):
    """Return last 10 wallet refresh log entries."""
    rows = await _query_db("SELECT * FROM wallet_refresh_log ORDER BY refreshed_at DESC LIMIT 10")
    result = []
    for r in rows:
        result.append({
            "id": r.get("id"),
            "refreshed_at": str(r.get("refreshed_at", "")),
            "wallets_added": r.get("wallets_added", 0),
            "wallets_removed": r.get("wallets_removed", 0),
            "wallets_total": r.get("wallets_total", 0),
            "trigger": r.get("trigger", ""),
            "notes": r.get("notes", ""),
        })
    return web.json_response(result)


async def api_wallets_refresh(request):
    """Trigger immediate wallet refresh (manual override)."""
    try:
        from services.nansen_wallet_fetcher import fetch_and_upsert_wallets
        result = await fetch_and_upsert_wallets(trigger="manual")
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_wallets_delete(request):
    """Mark a wallet as permanently excluded (manual_exclusion)."""
    address = request.match_info.get("address", "")
    if not address:
        return web.json_response({"error": "address required"}, status=400)
    try:
        pool = await get_pool()
        await pool.execute(
            """UPDATE watched_wallets SET
               is_active = FALSE,
               deactivated_reason = 'manual_exclusion'
               WHERE address = $1""",
            address,
        )
        return web.json_response({"status": "excluded", "address": address})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_market_mode_override(request):
    """POST /api/market-mode-override — set or clear manual market mode override."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)
    mode = str(body.get("mode", "")).upper()
    redis_conn = request.app.get("redis")
    if not redis_conn:
        return web.json_response({"error": "Redis not available"}, status=503)
    if mode == "CLEAR":
        await redis_conn.delete("market:mode:override")
        logger.info("Market mode override CLEARED")
        return web.json_response({"status": "cleared"})
    valid = ["HIBERNATE", "DEFENSIVE", "NORMAL", "AGGRESSIVE", "FRENZY"]
    if mode not in valid:
        return web.json_response({"error": f"must be one of {valid} or CLEAR"}, status=400)
    await redis_conn.set("market:mode:override", mode, ex=86400)
    logger.info("Market mode override SET: %s (24h TTL)", mode)
    return web.json_response({"status": "override set", "mode": mode, "expires_in": 86400})


async def api_audit_snapshot(request):
    """Return latest continuous audit snapshot from logs/audit_snapshot.json."""
    try:
        snap_path = Path("logs/audit_snapshot.json")
        if snap_path.exists():
            return web.json_response(json.loads(snap_path.read_text()))
        return web.json_response({"error": "no audit snapshot yet — continuous_audit may not be running"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_debug_rugcheck(request):
    """Return last 50 Rugcheck scores for threshold calibration."""
    redis_conn = request.app.get("redis")
    if not redis_conn:
        return web.json_response([])
    try:
        items = await redis_conn.lrange("debug:rugcheck_scores", 0, 49)
        return web.json_response([json.loads(i) for i in items])
    except Exception:
        return web.json_response([])


async def api_emergency_stop(request):
    redis_conn = request.app.get("redis")
    now_iso = datetime.now(timezone.utc).isoformat()
    if redis_conn:
        await redis_conn.publish("alerts:emergency", json.dumps({
            "reason": "Manual EMERGENCY_STOP from dashboard",
            "timestamp": now_iso,
        }))
        await redis_conn.set("bot:emergency_stop", "1", ex=3600)
    # Also persist to PostgreSQL
    try:
        from services.db import set_bot_state
        await set_bot_state("last_emergency_stop", now_iso)
    except Exception:
        pass
    return web.json_response({
        "status": "emergency_stop_triggered",
        "timestamp": now_iso,
        "note": "Bot will halt new entries. Open positions will be managed to exit.",
    })


async def api_approve_parameter(request):
    """POST /approve-parameter -- approve a pending parameter change (PostgreSQL-backed)."""
    try:
        body = await request.json()
        param_index = body.get("index", -1)

        pool = await get_pool()
        pending_raw = await pool.fetchval("SELECT value_text FROM bot_state WHERE key = 'pending_parameters'")
        active_raw = await pool.fetchval("SELECT value_text FROM bot_state WHERE key = 'active_parameters'")

        pending = json.loads(pending_raw) if pending_raw else []
        active = json.loads(active_raw) if active_raw else []

        if not pending:
            return web.json_response({"error": "no pending parameters"}, status=404)
        if param_index < 0 or param_index >= len(pending):
            return web.json_response({"error": "invalid index"}, status=400)

        item = pending.pop(param_index)
        item["status"] = "approved"
        item["approved_at"] = datetime.now(timezone.utc).isoformat()
        active.append(item)

        await pool.execute(
            """INSERT INTO bot_state (key, value_text, updated_at) VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value_text = $2, updated_at = NOW()""",
            "pending_parameters", json.dumps(pending),
        )
        await pool.execute(
            """INSERT INTO bot_state (key, value_text, updated_at) VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value_text = $2, updated_at = NOW()""",
            "active_parameters", json.dumps(active),
        )
        logger.info("Parameter approved (PostgreSQL): %s = %s", item["parameter"], item["proposed_value"])
        return web.json_response({"status": "approved", "parameter": item})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_sol_price(request):
    """SOL price -- Binance primary (no auth), Jupiter V3 fallback (per AGENT_CONTEXT Section 21)."""
    jupiter_api_key = os.getenv("JUPITER_API_KEY", "")
    jup_headers = {"x-api-key": jupiter_api_key} if jupiter_api_key else {}
    sources = [
        ("https://api.binance.com/api/v3/ticker/price", {"symbol": "SOLUSDT"}, {}, lambda d: float(d.get("price", 0)) or None),
        ("https://api.jup.ag/price/v3", {"ids": "So11111111111111111111111111111111111111112"}, jup_headers, lambda d: d.get("data", {}).get("So11111111111111111111111111111111111111112", {}).get("usdPrice")),
    ]
    async with aiohttp.ClientSession() as session:
        for url, params, headers, extract in sources:
            try:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = extract(data)
                        if price and float(price) > 0:
                            return web.json_response({"price": float(price)})
            except Exception:
                continue
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

def _classify_helius_tx(tx: dict) -> dict | None:
    """
    Classify a Helius enhanced webhook transaction into a signal dict.
    Returns None if not actionable.
    Each returned dict follows the signals:raw format consumed by signal_aggregator.
    """
    tx_type = tx.get("type", "UNKNOWN")
    fee_payer = tx.get("feePayer", "")
    signature = tx.get("signature", "")

    def first_token_mint():
        for transfer in tx.get("tokenTransfers", []):
            mint = transfer.get("mint", "")
            if mint and mint != SOL_MINT:
                return mint, transfer
        return None, None

    # ── SWAP ──
    if tx_type == "SWAP":
        mint, transfer = first_token_mint()
        if not mint:
            return None
        to_addr = transfer.get("toUserAccount", "")
        action = "buy" if to_addr == fee_payer else "sell"
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "whale_trade",
            "raw_data": {
                "wallet": fee_payer, "action": action,
                "token_amount": float(transfer.get("tokenAmount", 0) or 0),
                "signature": signature, "txType": action,
                "helius_webhook": True, "tx_type": "SWAP",
            },
        }

    # ── TRANSFER ──
    if tx_type == "TRANSFER":
        mint, transfer = first_token_mint()
        if not mint:
            return None
        to_addr = transfer.get("toUserAccount", "")
        from_addr = transfer.get("fromUserAccount", "")
        is_cex = to_addr in CEX_ADDRESSES
        if from_addr != fee_payer:
            return None
        action = "cex_transfer" if is_cex else "send"
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "whale_transfer",
            "raw_data": {
                "wallet": fee_payer, "action": action,
                "to": to_addr, "from": from_addr,
                "token_amount": float(transfer.get("tokenAmount", 0) or 0),
                "is_cex_transfer": is_cex,
                "signature": signature,
                "txType": "sell",
                "helius_webhook": True, "tx_type": "TRANSFER",
            },
        }

    # ── TOKEN_MINT ──
    if tx_type == "TOKEN_MINT":
        mint, transfer = first_token_mint()
        if not mint:
            return None
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "new_token",
            "raw_data": {
                "wallet": fee_payer, "action": "mint",
                "token_amount": float(transfer.get("tokenAmount", 0) or 0) if transfer else 0,
                "signature": signature,
                "helius_webhook": True, "tx_type": "TOKEN_MINT",
                "whale_created": True,
            },
        }

    # ── ADD_LIQUIDITY ──
    if tx_type == "ADD_LIQUIDITY":
        mint, transfer = first_token_mint()
        if not mint:
            return None
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "liquidity_add",
            "raw_data": {
                "wallet": fee_payer, "action": "add_liquidity",
                "token_amount": float(transfer.get("tokenAmount", 0) or 0),
                "signature": signature,
                "helius_webhook": True, "tx_type": "ADD_LIQUIDITY",
                "confidence_boost": 20,
            },
        }

    # ── WITHDRAW_LIQUIDITY ──
    if tx_type == "WITHDRAW_LIQUIDITY":
        mint, transfer = first_token_mint()
        if not mint:
            return None
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "liquidity_remove",
            "raw_data": {
                "wallet": fee_payer, "action": "withdraw_liquidity",
                "token_amount": float(transfer.get("tokenAmount", 0) or 0),
                "signature": signature,
                "helius_webhook": True, "tx_type": "WITHDRAW_LIQUIDITY",
                "txType": "sell",
            },
        }

    # ── CREATE_POOL ──
    if tx_type == "CREATE_POOL":
        mint, transfer = first_token_mint()
        if not mint:
            logger.info("CREATE_POOL from %s — no token mint found in transfers", fee_payer[:12])
            return None
        logger.info("CREATE_POOL detected — wallet=%s mint=%s sig=%s",
                     fee_payer[:12], mint[:12], signature[:16])
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "pool_created",
            "raw_data": {
                "wallet": fee_payer, "action": "create_pool",
                "signature": signature,
                "helius_webhook": True, "tx_type": "CREATE_POOL",
                "confidence_boost": 40,
            },
        }

    # ── BURN ──
    if tx_type == "BURN":
        mint, transfer = first_token_mint()
        if not mint:
            return None
        return {
            "mint": mint, "source": "helius_webhook",
            "signal_type": "token_burn",
            "raw_data": {
                "wallet": fee_payer, "action": "burn",
                "token_amount": float(transfer.get("tokenAmount", 0) or 0),
                "signature": signature,
                "helius_webhook": True, "tx_type": "BURN",
                "txType": "sell",
            },
        }

    # ── CLOSE_ACCOUNT ──
    if tx_type == "CLOSE_ACCOUNT":
        for account in tx.get("accountData", []):
            mint = account.get("mint", "")
            if mint and mint != SOL_MINT:
                return {
                    "mint": mint, "source": "helius_webhook",
                    "signal_type": "account_closed",
                    "raw_data": {
                        "wallet": fee_payer, "action": "close_account",
                        "signature": signature,
                        "helius_webhook": True, "tx_type": "CLOSE_ACCOUNT",
                        "txType": "sell",
                    },
                }
        return None

    return None


async def handle_helius_webhook(request):
    # Verify Helius HMAC signature if secret is configured
    if HELIUS_WEBHOOK_SECRET:
        sig_header = request.headers.get("authorization", "")
        body = await request.read()
        expected = hmac.new(
            HELIUS_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            logger.warning("Helius webhook signature mismatch — rejected")
            return web.json_response({"error": "invalid signature"}, status=401)
        try:
            payload = json.loads(body)
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
    else:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

    txs = payload if isinstance(payload, list) else [payload]
    redis_conn = request.app.get("redis")
    processed = 0

    for tx in txs:
        try:
            signal = _classify_helius_tx(tx)
            if signal:
                signal["timestamp"] = datetime.now(timezone.utc).isoformat()
                signal["age_seconds"] = 0.0
                if redis_conn:
                    await redis_conn.lpush("signals:raw", json.dumps(signal))
                    if TEST_MODE:
                        logger.info(
                            "Helius webhook [%s→Redis]: %s %s",
                            tx.get("type", "?"),
                            signal["signal_type"],
                            signal["mint"][:12],
                        )
                processed += 1
        except Exception as e:
            logger.warning("Helius webhook parse error [%s]: %s", tx.get("type", "?"), e)

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
                "sol_price": health.get("sol_price"),
                "market_mode": health.get("mode", "UNKNOWN"),
                "open_positions": status.get("open_positions", 0),
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


async def _service_health_checker(app: web.Application):
    """Background task: check service health every 60s, cache in Redis."""
    while True:
        try:
            redis_conn = app.get("redis")
            if not redis_conn:
                await asyncio.sleep(60)
                continue
            health = {}
            # Redis ping
            try:
                t0 = time.time()
                await redis_conn.ping()
                ms = int((time.time() - t0) * 1000)
                health["redis"] = {"status": "ok", "latency_ms": ms, "detail": "connected"}
            except Exception:
                health["redis"] = {"status": "down", "latency_ms": None, "detail": "disconnected"}
            # Binance connectivity proxy
            try:
                async with aiohttp.ClientSession() as session:
                    t0 = time.time()
                    async with session.get("https://api.binance.com/api/v3/ping", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        ms = int((time.time() - t0) * 1000)
                        health["binance"] = {"status": "ok" if resp.status == 200 else "warn", "latency_ms": ms, "detail": "ping"}
            except Exception:
                health["binance"] = {"status": "down", "latency_ms": None, "detail": "unreachable"}
            # PumpPortal — check last signal age
            try:
                sigs = await redis_conn.lrange("signals:raw", 0, 0)
                if sigs:
                    sig = json.loads(sigs[0])
                    ts = sig.get("timestamp", "")
                    if ts:
                        sig_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        age = (datetime.now(timezone.utc) - sig_time).total_seconds()
                        health["pumpportal"] = {"status": "live" if age < 120 else "warn", "latency_ms": None, "detail": f"last signal {int(age)}s ago"}
                    else:
                        health["pumpportal"] = {"status": "warn", "latency_ms": None, "detail": "no timestamp"}
                else:
                    health["pumpportal"] = {"status": "warn", "latency_ms": None, "detail": "no signals"}
            except Exception:
                health["pumpportal"] = {"status": "down", "latency_ms": None, "detail": "check failed"}
            # Market health — recent timestamp means data feeds are ok
            mh_status = "down"
            mh_detail = "no data"
            try:
                raw = await redis_conn.get("market:health")
                if raw:
                    mh = json.loads(raw)
                    ts = mh.get("timestamp", "")
                    if ts:
                        mh_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        age = (datetime.now(timezone.utc) - mh_time).total_seconds()
                        mh_status = "ok" if age < 300 else "warn"
                        mh_detail = f"updated {int(age)}s ago"
            except Exception:
                pass
            for svc in ["gecko", "defillama", "dexpaprika", "rugcheck", "vybe"]:
                health[svc] = {"status": mh_status, "latency_ms": None, "detail": mh_detail}
            # Real service checks (run concurrently with 5s timeouts)
            async def _check_url(name, url, method="get", json_body=None, headers=None, ok_codes=(200,)):
                try:
                    async with aiohttp.ClientSession() as s:
                        t0 = time.time()
                        kw = {"timeout": aiohttp.ClientTimeout(total=5)}
                        if headers:
                            kw["headers"] = headers
                        if method == "post" and json_body:
                            async with s.post(url, json=json_body, **kw) as resp:
                                ms = int((time.time() - t0) * 1000)
                                health[name] = {"status": "ok" if resp.status in ok_codes else "warn",
                                                "latency_ms": ms, "detail": f"HTTP {resp.status}"}
                        else:
                            async with s.get(url, **kw) as resp:
                                ms = int((time.time() - t0) * 1000)
                                health[name] = {"status": "ok" if resp.status in ok_codes else "warn",
                                                "latency_ms": ms, "detail": f"HTTP {resp.status}"}
                except Exception as e:
                    health[name] = {"status": "down", "latency_ms": None, "detail": str(e)[:40]}

            jup_key = os.getenv("JUPITER_API_KEY", "")
            helius_rpc = HELIUS_RPC_URL
            helius_gk = HELIUS_GATEKEEPER_URL
            helius_parse = os.getenv("HELIUS_PARSE_TX_URL", "")

            checks = [
                _check_url("jupiter", "https://api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112",
                           headers={"x-api-key": jup_key} if jup_key else None),
                _check_url("jito", "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
                           ok_codes=(200, 404, 405)),
            ]
            # Helius: check every 5th cycle (~5min) to avoid 429 rate limits
            helius_cycle = getattr(app, "_helius_health_cycle", 0)
            app._helius_health_cycle = helius_cycle + 1
            if helius_cycle % 5 == 0:
                if helius_rpc:
                    checks.append(_check_url("helius_rpc", helius_rpc, method="post",
                                             json_body={"jsonrpc": "2.0", "id": 1, "method": "getSlot"}))
                if helius_gk:
                    checks.append(_check_url("helius_gatekeeper", helius_gk, method="post",
                                             json_body={"jsonrpc": "2.0", "id": 1, "method": "getSlot"}))
                if helius_parse:
                    checks.append(_check_url("helius_parse", helius_parse, ok_codes=(200, 400, 404, 405)))
            else:
                # Reuse last known status from previous cycle (already in Redis cache)
                for svc in ("helius_rpc", "helius_gatekeeper", "helius_parse"):
                    if svc not in health:
                        health[svc] = {"status": "ok", "latency_ms": None, "detail": "cached (rate limit protection)"}

            nansen_key = os.getenv("NANSEN_API_KEY", "")
            if nansen_key:
                checks.append(_check_url("nansen", "https://api.nansen.ai/api/v1/token-screener",
                                         headers={"apikey": nansen_key}))
            else:
                health["nansen"] = {"status": "warn", "latency_ms": None, "detail": "API key not set"}

            await asyncio.gather(*checks, return_exceptions=True)

            # Config-only checks (no live ping)
            health["anthropic"] = {"status": "ok" if os.getenv("ANTHROPIC_API_KEY") else "warn",
                                   "latency_ms": None, "detail": "key configured" if os.getenv("ANTHROPIC_API_KEY") else "not set"}
            health["discord_webhook"] = {"status": "ok" if os.getenv("DISCORD_WEBHOOK_URL") else "warn",
                                         "latency_ms": None, "detail": "configured" if os.getenv("DISCORD_WEBHOOK_URL") else "not set"}
            health["discord_bot"] = {"status": "ok" if os.getenv("DISCORD_BOT_TOKEN") else "warn",
                                     "latency_ms": None, "detail": "configured" if os.getenv("DISCORD_BOT_TOKEN") else "not set"}

            await redis_conn.set("service:health", json.dumps(health), ex=120)
        except Exception as e:
            logger.debug("Service health check error: %s", e)
        await asyncio.sleep(60)


async def on_startup(app: web.Application):
    # Initialize PostgreSQL pool (shared with all services)
    try:
        pool = await get_pool()
        logger.info("PostgreSQL pool ready")
    except Exception as e:
        logger.error("PostgreSQL connection failed: %s", e)

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
        asyncio.create_task(_service_health_checker(app)),
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
    app.router.add_get("/api/stats", api_stats)
    app.router.add_get("/api/market", api_market)
    app.router.add_get("/api/market-health", api_market_health)
    app.router.add_get("/api/trades", api_trades)
    app.router.add_get("/api/trades/active", api_trades_active)
    app.router.add_get("/api/positions", api_positions)
    app.router.add_get("/api/personality-stats", api_personality_stats)
    app.router.add_get("/api/treasury", api_treasury)
    app.router.add_get("/api/governance", api_governance)
    app.router.add_get("/api/portfolio-history", api_portfolio_history)
    app.router.add_get("/api/ml-status", api_ml_status)
    app.router.add_get("/api/paper-stats", api_paper_stats)
    app.router.add_post("/api/emergency-stop", api_emergency_stop)
    app.router.add_post("/api/approve-parameter", api_approve_parameter)
    app.router.add_get("/api/sol-price", api_sol_price)
    app.router.add_get("/api/service-health", api_service_health)
    app.router.add_get("/api/debug/rugcheck-scores", api_debug_rugcheck)
    app.router.add_get("/api/audit-snapshot", api_audit_snapshot)
    app.router.add_post("/api/market-mode-override", api_market_mode_override)
    app.router.add_get("/api/whale-activity", api_whale_activity)
    app.router.add_get("/api/wallets", api_wallets)
    app.router.add_get("/api/wallets/refresh-log", api_wallets_refresh_log)
    app.router.add_post("/api/wallets/refresh", api_wallets_refresh)
    app.router.add_delete("/api/wallets/{address}", api_wallets_delete)
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
