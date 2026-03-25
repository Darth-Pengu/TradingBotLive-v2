"""
ZMN Bot Paper Trading Summary Report

Usage:
    python scripts/paper_summary.py

Reads from SQLite paper_trades table and prints performance report.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

_db_url = os.getenv("DATABASE_URL", "toxibot.db")
DATABASE_PATH = _db_url.replace("sqlite:///", "") if _db_url.startswith("sqlite") else _db_url


def main():
    db_path = os.path.join(os.path.dirname(__file__), "..", DATABASE_PATH)
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check table exists
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'").fetchone()
    if not tables:
        print("No paper_trades table found. Run the bot in TEST_MODE first.")
        sys.exit(0)

    trades = [dict(r) for r in conn.execute(
        "SELECT * FROM paper_trades WHERE exit_time IS NOT NULL ORDER BY exit_time DESC"
    ).fetchall()]

    open_trades = [dict(r) for r in conn.execute(
        "SELECT * FROM paper_trades WHERE exit_time IS NULL ORDER BY entry_time DESC"
    ).fetchall()]

    conn.close()

    if not trades and not open_trades:
        print("No paper trades recorded yet.")
        sys.exit(0)

    # Calculate stats
    total = len(trades)
    wins = sum(1 for t in trades if (t.get("realised_pnl_sol") or 0) > 0)
    losses = total - wins
    total_pnl = sum(t.get("realised_pnl_sol") or 0 for t in trades)
    total_fees = sum(t.get("fees_sol") or 0 for t in trades)
    # Also add entry fees for all trades
    all_trades_raw = [dict(r) for r in sqlite3.connect(db_path).execute(
        "SELECT * FROM paper_trades").fetchall()]
    total_fees = sum(t.get("fees_sol") or 0 for t in all_trades_raw)

    hold_times = [t.get("hold_seconds") or 0 for t in trades if t.get("hold_seconds")]
    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0

    # Date range
    entry_times = [t.get("entry_time") or 0 for t in trades + open_trades if t.get("entry_time")]
    if entry_times:
        first = datetime.fromtimestamp(min(entry_times), tz=timezone.utc).strftime("%Y-%m-%d")
        last = datetime.fromtimestamp(max(entry_times), tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        first = last = "N/A"

    # Best/worst
    best = max(trades, key=lambda t: t.get("realised_pnl_sol") or -999) if trades else None
    worst = min(trades, key=lambda t: t.get("realised_pnl_sol") or 999) if trades else None

    # Starting capital
    starting = float(os.getenv("STARTING_CAPITAL_SOL", "20"))

    print(f"\n{'='*50}")
    print(f"  ZMN Bot Paper Trading Report")
    print(f"{'='*50}")
    print(f"  Period: {first} to {last}")
    print(f"  Open positions: {len(open_trades)}")
    print()
    print(f"  OVERALL:")
    print(f"  Total Trades:     {total}")
    wr = (wins / total * 100) if total > 0 else 0
    print(f"  Win Rate:         {wr:.1f}% ({wins} wins / {losses} losses)")
    print(f"  Total P/L:        {'+' if total_pnl>=0 else ''}{total_pnl:.4f} SOL ({total_pnl/starting*100:+.1f}%)")
    if best:
        print(f"  Best Trade:       +{best['realised_pnl_sol']:.4f} SOL ({best['personality']}, {best['mint'][:12]}...)")
    if worst:
        print(f"  Worst Trade:      {worst['realised_pnl_sol']:.4f} SOL ({worst['personality']}, {worst['mint'][:12]}...)")
    m, s = divmod(int(avg_hold), 60)
    print(f"  Avg Hold Time:    {m}m {s:02d}s")
    print(f"  Total Fees:       {total_fees:.4f} SOL")
    print(f"  Net P/L (fees):   {'+' if (total_pnl-total_fees)>=0 else ''}{total_pnl-total_fees:.4f} SOL")

    # By personality
    print(f"\n  BY PERSONALITY:")
    for p in ["speed_demon", "analyst", "whale_tracker"]:
        pt = [t for t in trades if t.get("personality") == p]
        pw = sum(1 for t in pt if (t.get("realised_pnl_sol") or 0) > 0)
        pp = sum(t.get("realised_pnl_sol") or 0 for t in pt)
        pwr = (pw / len(pt) * 100) if pt else 0
        label = {"speed_demon": "Speed Demon", "analyst": "Analyst", "whale_tracker": "Whale Tracker"}[p]
        print(f"  {label:15s} {len(pt):3d} trades | {pwr:4.0f}% win | {'+' if pp>=0 else ''}{pp:.4f} SOL")

    # By signal source
    print(f"\n  BY SIGNAL SOURCE:")
    sources = {}
    for t in trades:
        src = t.get("signal_source") or "unknown"
        if src not in sources:
            sources[src] = {"trades": 0, "wins": 0, "pnl": 0.0}
        sources[src]["trades"] += 1
        sources[src]["pnl"] += t.get("realised_pnl_sol") or 0
        if (t.get("realised_pnl_sol") or 0) > 0:
            sources[src]["wins"] += 1

    for src, d in sorted(sources.items(), key=lambda x: -x[1]["trades"]):
        swr = (d["wins"] / d["trades"] * 100) if d["trades"] > 0 else 0
        print(f"  {src:20s} {d['trades']:3d} trades | {swr:4.0f}% win | {'+' if d['pnl']>=0 else ''}{d['pnl']:.4f} SOL")

    # By market mode
    print(f"\n  MARKET CONDITIONS:")
    modes = {}
    for t in trades:
        mm = t.get("market_mode_at_entry") or "UNKNOWN"
        modes[mm] = modes.get(mm, 0) + 1
    for mm, cnt in sorted(modes.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100 if total > 0 else 0
        print(f"  {mm:15s} {cnt:3d} trades ({pct:.0f}%)")

    # Top 5 wins
    sorted_by_pnl = sorted(trades, key=lambda t: t.get("realised_pnl_sol") or 0, reverse=True)
    top_wins = [t for t in sorted_by_pnl if (t.get("realised_pnl_sol") or 0) > 0][:5]
    if top_wins:
        print(f"\n  TOP {len(top_wins)} WINS:")
        for i, t in enumerate(top_wins, 1):
            hs = t.get("hold_seconds") or 0
            m, s = divmod(int(hs), 60)
            print(f"  {i}. +{t['realised_pnl_sol']:.4f} SOL | {t['mint'][:12]}... | {t['personality']} | {m}m {s:02d}s")

    # Top 5 losses
    top_losses = [t for t in reversed(sorted_by_pnl) if (t.get("realised_pnl_sol") or 0) < 0][:5]
    if top_losses:
        print(f"\n  TOP {len(top_losses)} LOSSES:")
        for i, t in enumerate(top_losses, 1):
            hs = t.get("hold_seconds") or 0
            m, s = divmod(int(hs), 60)
            print(f"  {i}. {t['realised_pnl_sol']:.4f} SOL | {t['mint'][:12]}... | {t['personality']} | {m}m {s:02d}s")

    print(f"\n{'='*50}\n")


if __name__ == "__main__":
    main()
