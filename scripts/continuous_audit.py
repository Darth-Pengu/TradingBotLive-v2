"""
ZMN Bot Continuous Audit Daemon
=================================
Lightweight monitoring loop — runs every 5 minutes.
Reads Redis + PostgreSQL only. Zero API cost. No Anthropic calls.

Checks: signal pipeline, bot_core liveness, market mode, stuck positions,
        ML sample growth, Redis memory.

Output: logs/continuous_audit.log (structured) + logs/audit_snapshot.json
Discord alerts: ALERT level only, rate-limited to 1 per check per 30 minutes.

Deploy as Railway worker: python scripts/continuous_audit.py
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
CYCLE_SECONDS = 300  # 5 minutes
ALERT_COOLDOWN_SECONDS = 1800  # 30 min per check

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = LOG_DIR / "continuous_audit.log"
SNAPSHOT_PATH = LOG_DIR / "audit_snapshot.json"

# Structured logger
audit_logger = logging.getLogger("continuous_audit")
audit_logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(AUDIT_LOG, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
audit_logger.addHandler(fh)
sh = logging.StreamHandler()
sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
audit_logger.addHandler(sh)

# State tracking between cycles
_last_ml_samples = 0
_last_scored_ts = 0.0


def _get_dsn() -> str:
    for url in [os.getenv("DATABASE_URL", ""), os.getenv("DATABASE_PRIVATE_URL", ""),
                os.getenv("DATABASE_PUBLIC_URL", ""), os.getenv("POSTGRES_URL", "")]:
        if not url:
            continue
        if url.startswith("sqlite"):
            continue
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return url
    return ""


async def _send_discord_alert(message: str, redis_conn, check_name: str):
    """Send Discord alert with rate limiting (1 per check per 30 min)."""
    if not DISCORD_WEBHOOK_URL:
        return

    # Rate limit check
    if redis_conn:
        try:
            cooldown_key = f"audit:last_alert:{check_name}"
            last = await redis_conn.get(cooldown_key)
            if last:
                return  # Still in cooldown
            await redis_conn.set(cooldown_key, "1", ex=ALERT_COOLDOWN_SECONDS)
        except Exception:
            pass

    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                DISCORD_WEBHOOK_URL,
                json={"content": f"[ZMN Audit] {message}"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        audit_logger.warning("Discord alert send failed: %s", e)


async def run_cycle(redis_conn, pg_dsn: str):
    """Run one audit cycle. Returns snapshot dict."""
    global _last_ml_samples, _last_scored_ts
    now = time.time()
    alerts = []
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ml_samples": 0,
        "ml_status": "UNTRAINED",
        "open_positions": 0,
        "stuck_positions": 0,
        "signals_last_hour": 0,
        "market_mode": "UNKNOWN",
        "personalities_active": [],
        "alerts": [],
    }

    # ── Redis checks ──────────────────────────────────────────────────────

    if redis_conn:
        try:
            await redis_conn.ping()
        except Exception as e:
            msg = f"Redis unreachable: {e}"
            audit_logger.error("[REDIS] %s", msg)
            alerts.append(msg)
            await _send_discord_alert(msg, None, "redis_down")
            snapshot["alerts"] = alerts
            return snapshot

        # 1. signals:scored queue depth
        try:
            scored_len = await redis_conn.llen("signals:scored")
            audit_logger.info("[QUEUE] signals:scored depth: %d", scored_len)
            if scored_len > 50:
                audit_logger.warning("[QUEUE] signals:scored backlog: %d", scored_len)

            # Check last scored timestamp for staleness
            last_scored = await redis_conn.lindex("signals:scored", 0)
            if last_scored:
                try:
                    sig = json.loads(last_scored)
                    ts = sig.get("timestamp", "")
                    if ts:
                        sig_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        age = (datetime.now(timezone.utc) - sig_time).total_seconds()
                        _last_scored_ts = sig_time.timestamp()
                        if age > 600:  # 10 min
                            msg = f"Signal pipeline stalled: last scored signal {int(age/60)}min ago"
                            audit_logger.error("[PIPELINE] %s", msg)
                            alerts.append(msg)
                            await _send_discord_alert(msg, redis_conn, "pipeline_stalled")
                        else:
                            audit_logger.info("[PIPELINE] Last scored signal: %ds ago", int(age))
                except Exception:
                    pass
            elif scored_len == 0:
                # Check if pipeline has ever had signals
                raw_len = await redis_conn.llen("signals:raw")
                if raw_len == 0 and _last_scored_ts > 0 and now - _last_scored_ts > 600:
                    msg = "Signal pipeline empty: no raw or scored signals for >10min"
                    audit_logger.error("[PIPELINE] %s", msg)
                    alerts.append(msg)
                    await _send_discord_alert(msg, redis_conn, "pipeline_empty")
        except Exception as e:
            audit_logger.warning("[QUEUE] Check failed: %s", e)

        # 2. bot:status liveness
        try:
            bot_exists = await redis_conn.exists("bot:status")
            if not bot_exists:
                msg = "bot:status key missing — bot_core may not be running"
                audit_logger.error("[BOT_CORE] %s", msg)
                alerts.append(msg)
                await _send_discord_alert(msg, redis_conn, "bot_core_dead")
            else:
                raw = await redis_conn.get("bot:status")
                if raw:
                    bs = json.loads(raw)
                    snapshot["open_positions"] = bs.get("open_positions", 0)
                    snapshot["market_mode"] = bs.get("market_mode", "UNKNOWN")
                    audit_logger.info("[BOT_CORE] status=%s positions=%d mode=%s",
                                      bs.get("status"), bs.get("open_positions", 0),
                                      bs.get("market_mode"))
        except Exception as e:
            audit_logger.warning("[BOT_CORE] Check failed: %s", e)

        # 3. market:health mode duration
        try:
            mh_raw = await redis_conn.get("market:health")
            if mh_raw:
                mh = json.loads(mh_raw)
                mode = mh.get("mode", "UNKNOWN")
                snapshot["market_mode"] = mode
                if mode in ("HIBERNATE", "DEFENSIVE"):
                    # Check how long we've been in this mode
                    mode_key = f"audit:mode_since:{mode}"
                    mode_since = await redis_conn.get(mode_key)
                    if mode_since:
                        duration_min = int((now - float(mode_since)) / 60)
                        if duration_min > 30:
                            audit_logger.warning("[MARKET] %s mode for %dmin", mode, duration_min)
                    else:
                        await redis_conn.set(mode_key, str(now), ex=7200)
                else:
                    # Clear mode trackers for non-defensive modes
                    for m in ("HIBERNATE", "DEFENSIVE"):
                        await redis_conn.delete(f"audit:mode_since:{m}")
        except Exception as e:
            audit_logger.warning("[MARKET] Check failed: %s", e)

        # 4. Redis memory
        try:
            info = await redis_conn.info("memory")
            used = info.get("used_memory", 0)
            peak = info.get("used_memory_peak", 1)
            pct = round(used / peak * 100, 1) if peak > 0 else 0
            audit_logger.info("[REDIS] Memory: %.1f%% of peak (%dMB)", pct, used // (1024 * 1024))
            if pct > 80:
                audit_logger.warning("[REDIS] Memory usage high: %.1f%%", pct)
        except Exception:
            pass

    # ── PostgreSQL checks ─────────────────────────────────────────────────

    if pg_dsn:
        import asyncpg
        try:
            conn = await asyncpg.connect(pg_dsn)
        except Exception as e:
            msg = f"PostgreSQL unreachable: {e}"
            audit_logger.error("[DB] %s", msg)
            alerts.append(msg)
            await _send_discord_alert(msg, redis_conn, "db_down")
            snapshot["alerts"] = alerts
            return snapshot

        try:
            # 5. Stuck positions (open > 120min)
            stuck = await conn.fetchval(
                """SELECT COUNT(*) FROM paper_trades
                   WHERE exit_time IS NULL
                   AND entry_time < $1""",
                now - 7200,  # 120 min ago
            )
            snapshot["stuck_positions"] = stuck or 0
            if stuck and stuck > 0:
                msg = f"{stuck} stuck paper position(s) held >120min — exits may not be firing"
                audit_logger.error("[POSITIONS] %s", msg)
                alerts.append(msg)
                await _send_discord_alert(msg, redis_conn, "stuck_positions")
            else:
                open_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NULL"
                )
                audit_logger.info("[POSITIONS] Open: %d, Stuck (>120min): 0", open_count or 0)

            # 6. Completed trades last hour
            recent = await conn.fetchval(
                "SELECT COUNT(*) FROM paper_trades WHERE exit_time > $1",
                now - 3600,
            )
            snapshot["signals_last_hour"] = recent or 0
            audit_logger.info("[ACTIVITY] Paper trades completed in last hour: %d", recent or 0)

            # 7. ML sample growth
            ml_samples = await conn.fetchval(
                "SELECT COUNT(*) FROM trades WHERE features_json IS NOT NULL AND outcome IS NOT NULL"
            ) or 0
            snapshot["ml_samples"] = ml_samples
            growth = ml_samples - _last_ml_samples if _last_ml_samples > 0 else 0
            _last_ml_samples = ml_samples

            if ml_samples >= 200:
                snapshot["ml_status"] = "TRAINED"
            elif ml_samples >= 15:
                snapshot["ml_status"] = "BOOTSTRAP"
            else:
                snapshot["ml_status"] = "UNTRAINED"

            audit_logger.info("[ML] Samples: %d (%s) | Growth: +%d this cycle",
                              ml_samples, snapshot["ml_status"], growth)

            # 8. Active personalities
            pers_rows = await conn.fetch(
                "SELECT DISTINCT personality FROM paper_trades"
            )
            snapshot["personalities_active"] = [r["personality"] for r in pers_rows]
            audit_logger.info("[PERSONALITIES] Active: %s", snapshot["personalities_active"])

        except Exception as e:
            audit_logger.warning("[DB] Query error: %s", e)
        finally:
            await conn.aclose()

    snapshot["alerts"] = alerts

    # ── Write snapshot ────────────────────────────────────────────────────

    try:
        SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, default=str))
    except Exception as e:
        audit_logger.warning("Snapshot write failed: %s", e)

    # ── Summary line ──────────────────────────────────────────────────────

    alert_count = len(alerts)
    if alert_count > 0:
        audit_logger.error("[SUMMARY] %d ALERT(s): %s", alert_count, "; ".join(alerts))
    else:
        audit_logger.info("[SUMMARY] All checks passed | ML=%s (%d samples) | Mode=%s | Open=%d",
                          snapshot["ml_status"], snapshot["ml_samples"],
                          snapshot["market_mode"], snapshot["open_positions"])

    return snapshot


async def main():
    audit_logger.info("=" * 60)
    audit_logger.info("Continuous audit daemon starting (cycle=%ds)", CYCLE_SECONDS)
    audit_logger.info("=" * 60)

    # Connect Redis
    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_conn.ping()
        audit_logger.info("Redis: CONNECTED")
    except Exception as e:
        audit_logger.warning("Redis: FAILED (%s) — will retry each cycle", e)
        redis_conn = None

    pg_dsn = _get_dsn()
    if pg_dsn:
        audit_logger.info("PostgreSQL: DSN found")
    else:
        audit_logger.warning("PostgreSQL: NO DSN — DB checks disabled")

    while True:
        try:
            # Reconnect Redis if needed
            if redis_conn:
                try:
                    await redis_conn.ping()
                except Exception:
                    try:
                        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
                        await redis_conn.ping()
                    except Exception:
                        redis_conn = None

            await run_cycle(redis_conn, pg_dsn)
        except Exception as e:
            audit_logger.error("Cycle failed: %s", e)

        await asyncio.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
