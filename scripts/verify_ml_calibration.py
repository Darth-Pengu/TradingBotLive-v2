"""verify_ml_calibration.py — counterfactual ML gate-threshold evaluator.

Research artefact. Companion to ML-SCORE-ATH-VALIDATION-001.
NOT consumed by production. Reads paper_trades + mint_ath_lookups.

Usage:
    python scripts/verify_ml_calibration.py             # full sweep
    python scripts/verify_ml_calibration.py 55          # single threshold

For each ml_score threshold, reports:
  - n_blocked, %_blocked
  - sum PnL of blocked rows (positive = bleed avoided; we want this NEGATIVE)
  - big winners (ATH>=5x) blocked
  - counterfactual sample PnL (actual - blocked)
  - delta vs actual

Window fixed to ML-SCORE-ATH-VALIDATION-001 sample:
  personality=speed_demon AND trade_mode=paper
  AND entry_time in [2026-04-22 00:00 UTC, 2026-05-05 14:16:48 UTC)  (pre BOT-CORE-ML-GATE).
"""
import os, sys, asyncio, asyncpg

DB = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB:
    print("ERR: set DATABASE_PUBLIC_URL/DATABASE_URL", file=sys.stderr); sys.exit(2)

W_START = 1776816000.0
W_END   = 1777990608.0

async def main():
    arg_thr = None
    if len(sys.argv) > 1:
        try: arg_thr = float(sys.argv[1])
        except ValueError:
            print(f"usage: {sys.argv[0]} [threshold]", file=sys.stderr); sys.exit(2)

    pool = await asyncpg.create_pool(DB, min_size=1, max_size=2)
    try:
        async with pool.acquire() as c:
            rows = await c.fetch("""
                SELECT p.ml_score, p.corrected_pnl_sol, p.peak_price, p.entry_price,
                       m.ath_price_usd
                FROM paper_trades p
                LEFT JOIN mint_ath_lookups m USING(mint)
                WHERE p.personality='speed_demon'
                  AND p.trade_mode='paper'
                  AND p.entry_time >= $1
                  AND p.entry_time <  $2
            """, W_START, W_END)
    finally:
        await pool.close()

    n_total = len(rows)
    scored = [r for r in rows if r["ml_score"] is not None]
    total_pnl = sum(float(r["corrected_pnl_sol"] or 0) for r in rows)
    print(f"sample: n={n_total}  with_ml_score={len(scored)}  actual_PnL={total_pnl:+.3f} SOL\n")

    def is_5x(r):
        ep = float(r["entry_price"] or 0)
        gt = r["ath_price_usd"]; gt = float(gt) if gt is not None else None
        pk = r["peak_price"]; pk = float(pk) if pk is not None else None
        ath = None
        if gt is not None and pk is not None: ath = max(gt, pk)
        elif gt is not None: ath = gt
        elif pk is not None: ath = pk
        if ath is None or ep <= 0: return False
        return (ath / ep) >= 5

    thrs = [arg_thr] if arg_thr is not None else [30,35,40,45,50,55,60,65,70,75]
    print(f"{'thr':>4} {'n_blk':>6} {'%_blk':>7} {'sum_blk_PnL':>14} {'5x_blocked':>11} {'cfact_PnL':>12} {'delta':>10}")
    best = None
    for thr in thrs:
        blocked = [r for r in scored if float(r["ml_score"]) < thr]
        blk_pnl = sum(float(r["corrected_pnl_sol"] or 0) for r in blocked)
        blk_big = sum(1 for r in blocked if is_5x(r))
        cfact = total_pnl - blk_pnl
        delta = -blk_pnl
        print(f"{thr:>4} {len(blocked):>6} {100*len(blocked)/max(len(scored),1):>6.1f}% {blk_pnl:>+14.3f} {blk_big:>11} {cfact:>+12.3f} {delta:>+10.3f}")
        if best is None or cfact > best[1]:
            best = (thr, cfact)
    if arg_thr is None and best:
        print(f"\nBest threshold (max counterfactual PnL): thr={best[0]}  PnL={best[1]:+.3f} SOL")

asyncio.run(main())
