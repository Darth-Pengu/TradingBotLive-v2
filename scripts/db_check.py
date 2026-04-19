"""Phase 0.4 — Database state check."""
import asyncio
import os
import json

async def main():
    import asyncpg
    # Get DSN from Railway
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        print("DATABASE_URL not set")
        return

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)

    # Personality breakdown
    print("=" * 60)
    print("PERSONALITY STATS")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT personality, COUNT(*) t,
            COUNT(CASE WHEN realised_pnl_sol > 0 THEN 1 END) w,
            ROUND(COALESCE(SUM(realised_pnl_sol),0)::numeric, 4) pnl
        FROM paper_trades WHERE exit_time IS NOT NULL GROUP BY personality
    """)
    for r in rows:
        wr = round(r["w"] / r["t"] * 100, 1) if r["t"] > 0 else 0
        print("  %s: %d trades, %d wins (%.1f%%), PnL: %s SOL" % (
            r["personality"], r["t"], r["w"], wr, r["pnl"]))

    # Exit reasons
    print("\n" + "=" * 60)
    print("EXIT REASONS")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT exit_reason, COUNT(*) c,
            ROUND(AVG(realised_pnl_sol)::numeric, 4) avg_pnl,
            COUNT(CASE WHEN realised_pnl_sol > 0 THEN 1 END) wins
        FROM paper_trades WHERE exit_time IS NOT NULL
        GROUP BY exit_reason ORDER BY c DESC
    """)
    for r in rows:
        print("  %-30s %4d trades  avg_pnl=%s  wins=%d" % (
            r["exit_reason"] or "null", r["c"], r["avg_pnl"], r["wins"]))

    # Big winners
    print("\n" + "=" * 60)
    print("TOP 10 WINNERS")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT mint, personality, entry_price, exit_price,
            realised_pnl_sol, realised_pnl_pct, exit_reason, staged_exits_done,
            peak_price, (exit_time - entry_time)/60 as hold_min
        FROM paper_trades WHERE realised_pnl_pct > 50
        ORDER BY realised_pnl_pct DESC LIMIT 10
    """)
    for r in rows:
        print("  %s %s: +%.4f SOL (+%.1f%%) exit=%s staged=%s hold=%.1fm" % (
            r["personality"], r["mint"][:12],
            float(r["realised_pnl_sol"] or 0),
            float(r["realised_pnl_pct"] or 0),
            r["exit_reason"],
            r["staged_exits_done"],
            float(r["hold_min"] or 0)))

    # Entry/exit price format check
    print("\n" + "=" * 60)
    print("PRICE FORMAT CHECK (last 10 trades)")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT entry_price, exit_price, realised_pnl_pct, exit_reason,
            CASE WHEN entry_price > 1 THEN 'likely_USD'
                 WHEN entry_price > 0.001 THEN 'maybe_USD'
                 WHEN entry_price < 0.001 THEN 'likely_SOL_per_token'
                 ELSE 'unknown' END as price_format
        FROM paper_trades WHERE exit_time IS NOT NULL
        ORDER BY exit_time DESC LIMIT 10
    """)
    for r in rows:
        print("  entry=$%.10f  exit=$%.10f  pnl=%.1f%%  format=%s" % (
            float(r["entry_price"] or 0), float(r["exit_price"] or 0),
            float(r["realised_pnl_pct"] or 0), r["price_format"]))

    # Open positions
    print("\n" + "=" * 60)
    print("OPEN POSITIONS")
    print("=" * 60)
    rows = await pool.fetch("""
        SELECT mint, personality, entry_price, amount_sol, entry_time,
            peak_price, staged_exits_done, trailing_stop_active
        FROM paper_trades WHERE exit_time IS NULL ORDER BY entry_time DESC
    """)
    if rows:
        for r in rows:
            print("  %s %s entry=$%.8f size=%.4f SOL peak=$%.8f" % (
                r["personality"], r["mint"][:12],
                float(r["entry_price"] or 0), float(r["amount_sol"] or 0),
                float(r["peak_price"] or 0)))
    else:
        print("  No open positions")

    # Total trade count
    total = await pool.fetchval("SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NOT NULL")
    open_count = await pool.fetchval("SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NULL")
    print("\nTotal closed: %d | Open: %d" % (total, open_count))

    await pool.close()

asyncio.run(main())
