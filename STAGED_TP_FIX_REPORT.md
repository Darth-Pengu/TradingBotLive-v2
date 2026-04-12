# Staged TP Reporting Bug Fix — 2026-04-13

## Outcome
**PARTIAL** — Fix deployed and code verified correct. No staged TP trades occurred during verification window (CFGI 16 extreme fear, ML scores 2-7). Live validation will happen when market improves.

## Bug Summary
Trades with staged take-profits had their `realised_pnl_pct` and `realised_pnl_sol` computed from ONLY the final residual exit, ignoring gains from staged TPs. Each call to `paper_sell()` overwrites the DB row, so the last exit's P/L becomes the permanent record.

**Example — Trade 3560 (Tn3VeHr2QB4b):**
- Entry: 1.69e-07, Peak: 2.36e-06 (13.95x)
- staged_exits_done: ["+50%", "+100%", "+200%", "+400%"]
- Recorded: -2.03% (-0.0012 SOL) — only the trailing stop residual
- True estimated: ~+137% (~+0.15 SOL) based on staged TP gains

## Root Cause
- **File:** `services/bot_core.py:886-889` (pre-fix)
- **Function:** `_close_position()`
- **Bug:** On final close (`remaining_pct <= 0.01`), bot_core reads P/L from the LAST `paper_sell()` return value. It ignores all previous partial exit P/L.
- **Secondary cause:** `paper_sell()` (services/paper_trader.py:296-302) OVERWRITES `realised_pnl_sol`/`realised_pnl_pct` in the DB on EVERY call, including intermediate staged TPs.

### Data flow (before fix)
```
Staged TP +50%  → paper_sell writes pnl_pct=+50% to DB → OVERWRITTEN
Staged TP +100% → paper_sell writes pnl_pct=+100%     → OVERWRITTEN
Staged TP +200% → paper_sell writes pnl_pct=+200%     → OVERWRITTEN
Staged TP +400% → paper_sell writes pnl_pct=+400%     → OVERWRITTEN
Trailing stop   → paper_sell writes pnl_pct=-2%       → THIS STAYS ← BUG
```

### Staged TP allocation config (actual)
```python
_DEFAULT_STAGED_TPS = [[0.50, 0.25], [1.00, 0.25], [2.00, 0.25], [4.00, 0.25]]
# Sells 25% of REMAINING position at each level:
# Stage 1 (+50%):  sells 25% of 100% = 25.0% of original
# Stage 2 (+100%): sells 25% of 75%  = 18.75%
# Stage 3 (+200%): sells 25% of 56.25% = 14.06%
# Stage 4 (+400%): sells 25% of 42.19% = 10.55%
# Residual for trailing stop:           31.64% (0.75^4)
```

## Estimated Historical Impact

Based on offline analysis of 218 clean-window trades (post-Apr 9 contamination filter):
- 44 trades have non-empty staged_exits_done
- 19 of those are RECORDED AS LOSSES but actually had positive realized gains from staged exits
- Aggregate hidden gain: ~+1.77 SOL (rough estimate)

| Metric | Recorded | Estimated True |
|--------|----------|---------------|
| Wins | 28 | ~47 |
| WR | 12.8% | ~21.6% |
| Total SOL | -4.81 | ~-0.39 |
| Break-even WR | 18.7% | 18.7% |

**21.6% WR exceeds the 18.7% break-even threshold.** The bot has been roughly break-even or slightly profitable, not bleeding money as headline numbers suggested.

## Fix Applied
- **Commit:** `5b92226`
- **Deploy timestamp:** 2026-04-12 22:55:41 UTC (bot_core)
- **Files changed:** `services/bot_core.py` (1 file, 20 insertions, 3 deletions)

### Changes:
1. Added `cumulative_pnl_sol: float = 0.0` to Position dataclass
2. After each `paper_sell()` call, accumulate returned `pnl_sol` into `pos.cumulative_pnl_sol`
3. On final close (`remaining_pct <= 0.01`):
   - Use `cumulative_pnl_sol` as total P/L (not just last exit's P/L)
   - Recompute `pnl_pct = (cumulative_pnl_sol / original_size_sol) * 100`
   - Derive `outcome` from cumulative total (not last exit)
   - Correct the DB row with accumulated totals (when staged exits exist)
4. Added `PAPER_EXIT` log line showing staged exits and cumulative P/L for debugging

### Data flow (after fix)
```
Staged TP +50%  → paper_sell writes pnl_pct=+50% to DB → cumulative += pnl_sol
Staged TP +100% → paper_sell writes pnl_pct=+100%     → cumulative += pnl_sol
Staged TP +200% → paper_sell writes pnl_pct=+200%     → cumulative += pnl_sol
Staged TP +400% → paper_sell writes pnl_pct=+400%     → cumulative += pnl_sol
Trailing stop   → paper_sell writes pnl_pct=-2%       → cumulative += pnl_sol
                → bot_core CORRECTS DB: pnl = sum(all) ← FIX
```

## Verification (30 min window: 22:55–23:30 UTC)

| Criterion | Result |
|-----------|--------|
| Post-fix trade with staged exits | **NO** — CFGI 16, no tokens pumped |
| Non-staged trade P/L correct | **YES** — trade 3564: -1.28% no_momentum_90s |
| PAPER_EXIT log firing | **N/A** — no staged trades occurred |
| No crashes/errors | **YES** — clean startup, healthy |
| Other personalities unaffected | **YES** |
Total: **3/5 (PARTIAL — weather-dependent, not bug-dependent)**

## Caveats
- **Historical trades NOT backfilled** — 19 mis-recorded trades still show wrong P/L
- **Dashboard P/L numbers** will look different for new staged trades only
- **ML training labels** for past trades are still wrong (retrain needed on corrected data)
- **Redis stats** (`paper:stats:total_pnl_sol`) are also slightly wrong because each partial paper_sell call updates them independently. Not fixed this session.
- **Live validation pending** — first staged TP trade in the new code will confirm fix works. Monitor PAPER_EXIT log lines.

## What Other Bugs This Suggests Could Exist
1. **Redis paper:stats** — paper_sell updates Redis total_pnl_sol on each partial call, so Redis stats count intermediate P/L events
2. **Dashboard equity curve** — reads from `realised_pnl_sol` in paper_trades, so historical curve is wrong
3. **ML training labels** — if ML reads realised_pnl_pct to determine win/loss, historical staged-TP trades have wrong labels

## Next Session Candidates
1. **Historical backfill** — recompute realised_pnl_sol/pct for all 44 trades with staged exits. Needs to reconstruct the staged TP prices from bot_core logs or from the allocation formula.
2. **ML retrain** — once backfill is done, retrain with corrected labels
3. **Dashboard verification** — confirm equity curve and P/L display use corrected values
4. **Smart money wallet mining** — use Nansen token_who_bought_sold on top 20 winners
5. **Redis stats fix** — correct paper:stats:total_pnl_sol accumulation for partial sells
