# TP Configuration Baseline — 2026-04-15 ~19:40 UTC

## Purpose
Pin the current TP system's behavior as the "before" state for the
TP redesign experiment. Future Claude sessions reference this when
evaluating whether the redesign should be reverted.

## Current TP Configuration
- Triggers: +50%, +100%, +200%, +400%
- Allocation: 25% of remaining at each trigger
- All-out at: +400% (25% of remaining ≈ 10.5% of original)
- Env var: STAGED_TAKE_PROFITS_JSON (unset, using code default)
- Code default: `[[0.50, 0.25], [1.00, 0.25], [2.00, 0.25], [4.00, 0.25]]`
- Semantic: sell_pct is fraction of REMAINING position, not original

## Baseline Metrics (measured from Postgres at session start)
- Post-recovery window: IDs 3631 to 4175
- Total closed trades: 545
- Wins: 221
- Win rate: 40.6%
- Total P/L: +35.6100 SOL
- Avg P/L per trade: +0.0653 SOL

## Per-Personality Breakdown
- Speed Demon: 545 trades (Analyst disabled, Whale Tracker dormant)
- Analyst: disabled via ANALYST_DISABLED=true
- Whale Tracker: dormant

## Staged TP Subset (the edge)
- Staged trades: 213
- Staged WR: 96.7%
- Staged total P/L: +51.19 SOL
- Non-staged trades: 332
- Non-staged WR: 4.5%
- Non-staged total P/L: -15.58 SOL

## Revert Thresholds for TP Redesign
The redesign will be reverted if ANY of these hit after deploy:
1. WR drops >= 5 pp below 40.6% (below 35.6%) over any 100-trade window
2. Avg P/L/trade drops >= 25% below 0.0653 (below 0.049) over any 100-trade window
3. Staged-subset WR drops >= 10 pp below 96.7% (below 86.7%) over any 50-trade staged window
4. Total P/L negative over any rolling 50-trade window (after first 25)
5. Any deploy issue, crash, or trading stoppage

## Success Criteria
If NONE of the revert criteria hit after 48h AND >= 200 post-redesign
trades accumulated, the redesign is considered SUCCESSFUL and this
baseline is superseded by the new one.
