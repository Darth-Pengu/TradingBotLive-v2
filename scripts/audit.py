"""
ZMN Bot System Audit Script
=============================
Reads Redis + PostgreSQL to diagnose signal pipeline, ML training,
whale monitoring, personality routing, and service connectivity.

No external API calls. No Anthropic usage. Standalone runnable.
Usage: python scripts/audit.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ── Helpers ────────────────────────────────────────────────────────────────

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


def _ts(val) -> str:
    """Convert unix timestamp to readable string."""
    if not val:
        return "N/A"
    try:
        return datetime.fromtimestamp(float(val), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError):
        return str(val)[:25]


def _mins_ago(val) -> str:
    if not val:
        return "?"
    try:
        delta = datetime.now(timezone.utc) - datetime.fromtimestamp(float(val), tz=timezone.utc)
        mins = int(delta.total_seconds() / 60)
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h {mins % 60}m ago"
    except Exception:
        return "?"


CRITICAL_ISSUES = []


def banner(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── Section 1: Signal Pipeline Health ──────────────────────────────────────

async def section_signal_pipeline():
    banner("SECTION 1: Signal Pipeline Health")
    import redis.asyncio as aioredis
    try:
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        await r.ping()
        print("  Redis: CONNECTED")
    except Exception as e:
        print(f"  Redis: FAILED — {e}")
        CRITICAL_ISSUES.append("Redis not reachable")
        return None

    # Queue lengths
    raw_len = await r.llen("signals:raw")
    scored_len = await r.llen("signals:scored")
    print(f"\n  signals:raw  queue length: {raw_len}")
    print(f"  signals:scored queue length: {scored_len}")

    # Last 10 scored signals
    print(f"\n  Last 10 scored signals:")
    scored = await r.lrange("signals:scored", 0, 9)
    if scored:
        for i, s in enumerate(scored):
            try:
                d = json.loads(s)
                mint = d.get("mint", "?")[:12]
                pers = d.get("personality", "?")
                ml = d.get("ml_score", "?")
                mode = d.get("market_mode", "?")
                ts = d.get("timestamp", "?")
                print(f"    [{i+1}] {mint}... | {pers:14s} | ML:{ml:>5} | {mode:10s} | {ts}")
            except Exception:
                print(f"    [{i+1}] (parse error)")
    else:
        print("    (empty)")

    # bot:status
    print(f"\n  bot:status:")
    bot_raw = await r.get("bot:status")
    if bot_raw:
        bs = json.loads(bot_raw)
        print(f"    status:      {bs.get('status', '?')}")
        print(f"    market_mode: {bs.get('market_mode', '?')}")
        print(f"    balance:     {bs.get('portfolio_balance', '?')}")
        print(f"    open_pos:    {bs.get('open_positions', '?')}")
        print(f"    consec_loss: {bs.get('consecutive_losses', 0)}")
        print(f"    test_mode:   {bs.get('test_mode', '?')}")
        positions = bs.get("positions", {})
        if positions:
            print(f"    positions ({len(positions)}):")
            for k, v in positions.items():
                mint = v.get("mint", "?")[:12]
                pers = v.get("personality", "?")
                entry = v.get("entry_price", 0)
                cur = v.get("current_price", 0)
                pnl = v.get("unrealised_pnl_pct")
                trail = "ACTIVE" if v.get("trailing_stop_active") else "off"
                print(f"      {k}: {mint}... {pers} entry=${entry:.8f} cur=${cur:.8f} pnl={pnl or '--'}% trail={trail}")
        else:
            print("    positions: (none)")
    else:
        print("    (not set — bot_core may not be running)")
        CRITICAL_ISSUES.append("bot:status missing — bot_core not running?")

    # market:health
    print(f"\n  market:health:")
    mh_raw = await r.get("market:health")
    if mh_raw:
        mh = json.loads(mh_raw)
        print(f"    mode:      {mh.get('mode', '?')}")
        print(f"    sol_price: ${mh.get('sol_price', '?')}")
        print(f"    cfgi:      {mh.get('cfgi', '?')}")
        print(f"    timestamp: {mh.get('timestamp', '?')}")
    else:
        print("    (not set — market_health not running)")
        CRITICAL_ISSUES.append("market:health missing — market_health not running?")

    # market:mode:current
    mode_cur = await r.get("market:mode:current")
    print(f"\n  market:mode:current: {mode_cur or '(not set)'}")

    # Haiku cache
    haiku_keys = []
    async for key in r.scan_iter("haiku:*"):
        haiku_keys.append(key)
    print(f"\n  Haiku cached results: {len(haiku_keys)} mints")

    # traded:mints
    traded = await r.smembers("traded:mints")
    print(f"  traded:mints cooldown set: {len(traded)} mints")
    if traded:
        for m in list(traded)[:10]:
            print(f"    {m[:12]}...")

    return r


# ── Section 2: ML Training Data Status ─────────────────────────────────────

async def section_ml_training():
    banner("SECTION 2: ML Training Data Status")
    dsn = _get_dsn()
    if not dsn:
        print("  PostgreSQL: NOT CONFIGURED")
        CRITICAL_ISSUES.append("No PostgreSQL DSN found")
        return None

    import asyncpg
    try:
        conn = await asyncpg.connect(dsn)
        print("  PostgreSQL: CONNECTED")
    except Exception as e:
        print(f"  PostgreSQL: FAILED — {e}")
        CRITICAL_ISSUES.append(f"PostgreSQL connection failed: {e}")
        return None

    # trades table (ML training samples)
    trades_count = await conn.fetchval("SELECT COUNT(*) FROM trades") or 0
    trades_with_features = await conn.fetchval(
        "SELECT COUNT(*) FROM trades WHERE features_json IS NOT NULL") or 0
    trades_with_outcome = await conn.fetchval(
        "SELECT COUNT(*) FROM trades WHERE outcome IS NOT NULL") or 0
    trades_ready = await conn.fetchval(
        "SELECT COUNT(*) FROM trades WHERE features_json IS NOT NULL AND outcome IS NOT NULL") or 0
    print(f"\n  trades table (ML training):")
    print(f"    total rows:        {trades_count}")
    print(f"    has features_json: {trades_with_features}")
    print(f"    has outcome:       {trades_with_outcome}")
    print(f"    READY for training: {trades_ready}")

    if trades_count > 0:
        oldest = await conn.fetchval("SELECT MIN(created_at) FROM trades")
        newest = await conn.fetchval("SELECT MAX(created_at) FROM trades")
        print(f"    oldest entry:      {_ts(oldest)}")
        print(f"    newest entry:      {_ts(newest)}")

    if trades_ready < 50:
        CRITICAL_ISSUES.append(f"Only {trades_ready}/50 labelled training samples — ML cannot train yet")

    # paper_trades
    pt_closed = await conn.fetchval(
        "SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NOT NULL") or 0
    pt_open = await conn.fetchval(
        "SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NULL") or 0
    print(f"\n  paper_trades:")
    print(f"    closed (completed): {pt_closed}")
    print(f"    open (stuck?):      {pt_open}")

    # Open/stuck positions detail
    if pt_open > 0:
        print(f"\n    Open paper positions:")
        rows = await conn.fetch(
            "SELECT mint, personality, entry_time FROM paper_trades WHERE exit_time IS NULL ORDER BY entry_time ASC"
        )
        now = datetime.now(timezone.utc).timestamp()
        for row in rows[:20]:
            mint = (row["mint"] or "")[:12]
            pers = row["personality"] or "?"
            et = row["entry_time"]
            hold_min = int((now - float(et)) / 60) if et else 0
            print(f"      {mint}... | {pers:14s} | entered {_ts(et)} | hold: {hold_min}min")

    # Breakdown by personality + source
    print(f"\n  Completed trades by personality:")
    pers_rows = await conn.fetch(
        """SELECT personality, COUNT(*) as cnt,
           SUM(CASE WHEN realised_pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
           ROUND(AVG(realised_pnl_sol)::numeric, 4) as avg_pnl,
           ROUND(AVG(realised_pnl_pct)::numeric, 1) as avg_pnl_pct
           FROM paper_trades WHERE exit_time IS NOT NULL
           GROUP BY personality ORDER BY cnt DESC"""
    )
    for row in pers_rows:
        pers = row["personality"]
        cnt = row["cnt"]
        wins = row["wins"] or 0
        wr = round(wins / cnt * 100, 1) if cnt > 0 else 0
        avg_pnl = row["avg_pnl"] or 0
        avg_pct = row["avg_pnl_pct"] or 0
        print(f"    {pers:14s}: {cnt:4d} trades | WR: {wr:5.1f}% | avg PnL: {avg_pnl:+.4f} SOL ({avg_pct:+.1f}%)")

    print(f"\n  Signal source breakdown:")
    src_rows = await conn.fetch(
        """SELECT COALESCE(signal_source, 'unknown') as src, COUNT(*) as cnt
           FROM paper_trades GROUP BY signal_source ORDER BY cnt DESC"""
    )
    for row in src_rows:
        print(f"    {row['src']:20s}: {row['cnt']} trades")

    # features_json NULL check
    pt_features_null = await conn.fetchval(
        "SELECT COUNT(*) FROM paper_trades WHERE features_json IS NULL") or 0
    pt_features_ok = await conn.fetchval(
        "SELECT COUNT(*) FROM paper_trades WHERE features_json IS NOT NULL") or 0
    print(f"\n  paper_trades features_json: {pt_features_ok} non-null, {pt_features_null} null")
    if pt_features_ok == 0 and pt_closed > 0:
        CRITICAL_ISSUES.append("All paper_trades have NULL features_json — ML has no feature data")

    await conn.aclose()
    return {"trades_ready": trades_ready, "pt_closed": pt_closed, "pt_open": pt_open}


# ── Section 3: Whale/Wallet Monitoring ──────────────────────────────────────

async def section_whale_monitoring():
    banner("SECTION 3: Whale/Wallet Monitoring")
    dsn = _get_dsn()
    if not dsn:
        print("  (skipped — no PostgreSQL)")
        return

    import asyncpg
    try:
        conn = await asyncpg.connect(dsn)
    except Exception:
        print("  (PostgreSQL connection failed)")
        return

    # watched_wallets
    try:
        ww_total = await conn.fetchval("SELECT COUNT(*) FROM watched_wallets") or 0
        ww_active = await conn.fetchval("SELECT COUNT(*) FROM watched_wallets WHERE is_active = TRUE") or 0
        ww_inactive = ww_total - ww_active
        print(f"\n  watched_wallets table: {ww_total} total ({ww_active} active, {ww_inactive} inactive)")

        routes = await conn.fetch(
            "SELECT personality_route, COUNT(*) as cnt FROM watched_wallets WHERE is_active = TRUE GROUP BY personality_route"
        )
        for row in routes:
            print(f"    {row['personality_route']:14s}: {row['cnt']} wallets")
    except Exception:
        print("  watched_wallets table: MISSING")
        CRITICAL_ISSUES.append("watched_wallets table does not exist")

    # JSON file fallback
    whale_path = Path("data/whale_wallets.json")
    if whale_path.exists():
        try:
            wallets = json.loads(whale_path.read_text())
            print(f"\n  whale_wallets.json: {len(wallets)} wallets")
        except Exception:
            print(f"\n  whale_wallets.json: exists but unreadable")
    else:
        print(f"\n  whale_wallets.json: NOT FOUND")

    # wallet_refresh_log
    try:
        last_refresh = await conn.fetchrow(
            "SELECT refreshed_at, wallets_added, wallets_removed, wallets_total, trigger "
            "FROM wallet_refresh_log ORDER BY refreshed_at DESC LIMIT 1"
        )
        if last_refresh:
            print(f"\n  Last wallet refresh: {last_refresh['refreshed_at']}")
            print(f"    +{last_refresh['wallets_added']} -{last_refresh['wallets_removed']} total={last_refresh['wallets_total']} trigger={last_refresh['trigger']}")
        else:
            print(f"\n  wallet_refresh_log: no entries")
    except Exception:
        print(f"\n  wallet_refresh_log: table missing")

    await conn.aclose()


# ── Section 4: Personality Routing Analysis ─────────────────────────────────

async def section_personality_routing():
    banner("SECTION 4: Personality Routing Analysis")
    dsn = _get_dsn()
    if not dsn:
        print("  (skipped — no PostgreSQL)")
        return {}

    import asyncpg
    try:
        conn = await asyncpg.connect(dsn)
    except Exception:
        print("  (PostgreSQL connection failed)")
        return {}

    pers_counts = {}
    rows = await conn.fetch(
        "SELECT personality, COUNT(*) as cnt FROM paper_trades GROUP BY personality ORDER BY cnt DESC"
    )
    print(f"\n  Paper trades by personality (all, including open):")
    for row in rows:
        pers = row["personality"]
        cnt = row["cnt"]
        pers_counts[pers] = cnt
        print(f"    {pers:14s}: {cnt}")

    if "analyst" not in pers_counts:
        print("    analyst:         0 — NO SIGNALS REACHED ANALYST")
        CRITICAL_ISSUES.append("Analyst personality has received ZERO signals")
    if "whale_tracker" not in pers_counts:
        print("    whale_tracker:   0 — NO SIGNALS REACHED WHALE TRACKER")
        CRITICAL_ISSUES.append("Whale Tracker personality has received ZERO signals")

    await conn.aclose()
    return pers_counts


# ── Section 5: Architecture Connectivity ────────────────────────────────────

async def section_connectivity(redis_conn):
    banner("SECTION 5: Architecture Connectivity")
    if not redis_conn:
        print("  (skipped — no Redis)")
        return

    # service:health
    sh_raw = await redis_conn.get("service:health")
    if sh_raw:
        sh = json.loads(sh_raw)
        print(f"\n  Service health ({len(sh)} services):")
        for svc, data in sorted(sh.items()):
            status = data.get("status", "?")
            ms = data.get("latency_ms")
            detail = data.get("detail", "")
            icon = "✓" if status in ("ok", "live") else "⚠" if status == "warn" else "✗" if status == "down" else "?"
            ms_str = f"{ms}ms" if ms is not None else "--"
            print(f"    {icon} {svc:20s} {status:8s} {ms_str:>6s}  {detail}")
    else:
        print("\n  service:health: NOT SET — dashboard_api health checker not running")

    # market:mode:current
    mode = await redis_conn.get("market:mode:current")
    print(f"\n  market:mode:current: {mode or 'NOT SET'}")
    if not mode:
        CRITICAL_ISSUES.append("market:mode:current not set — market_health service not publishing")

    # bot:status TTL
    bot_ttl = await redis_conn.ttl("bot:status")
    print(f"  bot:status TTL: {bot_ttl}s {'(OK)' if bot_ttl > 0 else '(no TTL — uses SET not SETEX)'}")
    bot_exists = await redis_conn.exists("bot:status")
    if not bot_exists:
        CRITICAL_ISSUES.append("bot:status key missing — bot_core not running")

    # Recent signal flow
    scored = await redis_conn.lrange("signals:scored", 0, 0)
    if scored:
        try:
            last = json.loads(scored[0])
            ts = last.get("timestamp", "")
            if ts:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
                print(f"  Last scored signal: {int(age)}s ago {'(FLOWING)' if age < 120 else '(STALLED)' if age < 600 else '(DEAD)'}")
                if age > 600:
                    CRITICAL_ISSUES.append(f"No scored signals in {int(age/60)} minutes")
            else:
                print(f"  Last scored signal: no timestamp")
        except Exception:
            print(f"  Last scored signal: (parse error)")
    else:
        print(f"  Last scored signal: NONE — pipeline empty")


# ── Summary ─────────────────────────────────────────────────────────────────

def print_summary(ml_data, pers_counts):
    banner("SUMMARY")

    # ML status
    trades_ready = ml_data.get("trades_ready", 0) if ml_data else 0
    if trades_ready >= 200:
        ml_status = "TRAINED (production)"
    elif trades_ready >= 50:
        ml_status = "BOOTSTRAP"
    else:
        ml_status = f"UNTRAINED ({trades_ready}/50 samples)"
    print(f"\n  ML TRAINING:     {ml_status}")

    # Personalities
    for pers, label in [("speed_demon", "SPEED DEMON"), ("analyst", "ANALYST"), ("whale_tracker", "WHALE TRACKER")]:
        cnt = pers_counts.get(pers, 0)
        active = "ACTIVE" if cnt > 0 else "INACTIVE"
        extra = ""
        if pers == "whale_tracker":
            whale_path = Path("data/whale_wallets.json")
            extra = f", whale_wallets {'FOUND' if whale_path.exists() else 'MISSING'}"
        print(f"  {label:14s}:   {active} — {cnt} paper trades{extra}")

    # Signal pipeline
    print(f"\n  SIGNAL PIPELINE: (check Section 5 above for flow status)")

    # Critical issues
    if CRITICAL_ISSUES:
        print(f"\n  🔴 CRITICAL ISSUES ({len(CRITICAL_ISSUES)}):")
        for issue in CRITICAL_ISSUES:
            print(f"    • {issue}")
    else:
        print(f"\n  ✅ No critical issues detected")

    print()


# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    print("\n" + "=" * 60)
    print("  ZMN Bot System Audit")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    redis_conn = await section_signal_pipeline()
    ml_data = await section_ml_training()
    await section_whale_monitoring()
    pers_counts = await section_personality_routing()
    await section_connectivity(redis_conn)
    print_summary(ml_data, pers_counts)

    if redis_conn:
        await redis_conn.aclose()


if __name__ == "__main__":
    asyncio.run(main())
