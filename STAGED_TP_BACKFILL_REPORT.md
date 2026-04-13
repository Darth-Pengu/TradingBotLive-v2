# Staged TP Backfill Report -- 2026-04-13

## Outcome
SUCCESS

## Summary
Corrected historical P/L for 44 pre-fix staged trades. Added
corrected_pnl columns to paper_trades schema. Audited Redis sister
bug (confirmed overcounting), deferred code fix (low impact -- dashboard
reads from Postgres, not Redis).

## Headline Correction

### Before backfill (using realised_pnl_sol)
- Total clean trades: 259
- Wins: 49 (18.9% WR)
- Total SOL: +13.8330
- Pre-fix subset (id <= 3564): 218 trades, 27 wins (12.4% WR), -4.8125 SOL
- Post-fix subset (id > 3564): 41 trades, 22 wins (53.7% WR), +18.6455 SOL

### After backfill (using corrected_pnl_sol)
- Total clean trades: 259
- Wins: 68 (26.3% WR)
- Total SOL: +17.7345
- Pre-fix subset corrected: 46 wins (21.1% WR), -0.9110 SOL
- Delta on pre-fix: +19 wins recovered, +3.9015 SOL correction

## Top Corrections (trades where recorded vs corrected differs most)

| ID | Recorded pnl_sol | Corrected pnl_sol | Delta | Staged |
|----|-----------------|-------------------|-------|--------|
| 3347 | +0.0802 | +0.3739 | +0.2937 | +50%, +100%, +200% |
| 3433 | +0.0772 | +0.3022 | +0.2250 | +50%, +100% |
| 3556 | -0.0084 | +0.2140 | +0.2223 | +50%, +100%, +200% |
| 3542 | -0.0008 | +0.1889 | +0.1898 | +50%, +100%, +200%, +400% |
| 3393 | +0.0570 | +0.2415 | +0.1845 | +50%, +100% |

## Outcome Flips (19 trades reclassified)

All 19 flips were loss -> win. No win -> loss flips occurred. These trades
hit staged TPs but the residual exited below entry, causing the old code to
record a loss despite net-positive cumulative P/L.

## Redis Sister-Bug Audit

- **Finding:** `paper_sell()` updates Redis `paper:stats` on EVERY call
  including partial sells. For staged TPs, this means `winning_trades`
  gets incremented once per profitable partial (up to 5x per trade).
- **Redis state:** winning_trades=417, total_trades=3605, total_pnl_sol=-11.99
- **Postgres truth:** winning_trades=229 (old column), total_trades=3605
- **Impact:** LOW -- dashboard reads from Postgres, not Redis paper:stats
- **Action:** Deferred. Fix requires changes to both paper_sell and bot_core
  (pass cumulative P/L for final Redis update). Queued for future session.

## Dashboard Audit

- Reads P/L from: **Postgres `realised_pnl_sol`** (line 1081+ in dashboard_api.py)
- Redis paper:stats NOT used for display (good)
- Status: **needs update** -- should read `corrected_pnl_sol` instead
- Queued for next session: yes

## Approximation Notes

The backfill assumes each staged TP filled EXACTLY at the trigger
price (1.5x, 2.0x, 3.0x, 5.0x entry). Real fills likely had +/- 2-5%
slippage. Corrected numbers are therefore within ~5% of true P/L,
not exact.

Staged TP allocation (25% of remaining at each stage):
- Stage 1 (+50%):  25.00% of original at 1.5x entry
- Stage 2 (+100%): 18.75% of original at 2.0x entry
- Stage 3 (+200%): 14.06% of original at 3.0x entry
- Stage 4 (+400%): 10.55% of original at 5.0x entry
- Residual: 31.64% of original (0.75^4) at actual exit_price

## Caveats

- ML training code still reads realised_pnl_sol. Update queued for
  separate session.
- Dashboard still reads realised_pnl_sol. Update queued for separate session.
- Full ML retrain still requires 500+ samples. At current rate, ~7-14
  days away.
- Post-fix trades (id > 3564) are unchanged -- their corrected values
  were already correct from commit 5b92226.

## Files Changed
- paper_trades schema (+5 columns)
- migrations/001_add_corrected_pnl_columns.sql (new)
- MONITORING_LOG.md
- ZMN_ROADMAP.md
- AGENT_CONTEXT.md
- CLAUDE.md
- STAGED_TP_BACKFILL_REPORT.md (new)

## Commits
- [see git log after push]

## Next Session Candidates (from roadmap)
1. TP redesign (30/30/20/10/10 allocation, option B2 triggers)
2. ML training code update to read corrected_pnl_sol
3. Dashboard P/L source update
4. Social filter deployment (prompt already written)
5. Helius budget enforcement (hard deadline April 23-24)
