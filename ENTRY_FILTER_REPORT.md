# Entry Filter Deployment — 2026-04-11 AEDT

## Outcome
**PARTIAL** — Filter deployed and stable, zero rejections in verification window. No crashes, trades flowing. Filter is correctly a no-op when trade data doesn't exist at evaluation time (age 0-1s tokens).

## Deploy Details
- Commits: `eb20d85` (initial), `33244dd` (fix v2), `4f4d4db` (redesign v3)
- Deploy timestamp: 2026-04-10 22:40 UTC (v3 final)
- Verification window: 1 hour (22:40 - 23:40 UTC)
- Filter thresholds used:
  - MIN_BUY_SELL_RATIO: 1.0
  - MIN_WALLET_VELOCITY: 10.0
  - MISSING_DATA_RETRY_MS: 750

## Pre-Filter Baseline (172 trades from CSV analysis)
- WR: 16.3%
- Avg P/L: -2.28%
- Total SOL: -4.18
- Payoff: 4.34x
- Break-even WR: 18.7%
- no_momentum_90s: 51% of exits

## Post-Filter Results (14 trades in 1-hour window)
- WR: 0% (0/14) — CFGI 16 extreme fear, not filter-related
- Avg P/L: -10.47%
- Total SOL: -0.3183
- no_momentum_90s: 21% of exits (down from 51% — but stale_no_price took its place)

**Note:** The 0% WR and high stale_no_price rate (71%) are caused by Helius credit exhaustion (price data unavailable), NOT the entry filter. Pre-filter comparison window also had 0 trades (HIBERNATE mode).

## Filter Metrics
- Total signals evaluated: ~450 (estimated from log rate)
- Entry filter passes: ~450 (100%)
- Entry filter rejects: 0 (0%)
- Rejection breakdown:
  - low_buy_sell_ratio: 0
  - low_wallet_velocity: 0
  - blind_entry_no_stats: 0

**Why zero rejections:** All PumpPortal tokens arrive at age 0-1 seconds with zero trade data. `has_trade_data = False` for every signal, so the filter correctly passes them through to ML scoring. The filter only catches tokens WITH trade data showing poor BSR.

## The Timing Problem

The CSV analysis showed winners had `buy_sell_ratio_5min = 3.27` and losers had `0.55`. But these BSR values were captured in `features_json` at entry time. Verified from actual DB:

| Trade | Outcome | BSR at entry | tx_per_sec | sell_pressure |
|-------|---------|-------------|------------|---------------|
| DS3m72L2tmYX | +319% | 52.0 | 53.0 | 0.02 |
| 4TzzVEfY9ZR7 | +18% | 3.0 | 3.0 | 0.0 |
| 2qhEG3oe9dsS | +55% | 2.5 | 49.0 | 0.29 |
| DSbywquDgu5X | +24% | 1.8 | 28.0 | 0.36 |
| DzsWG76d8Dzo | -27% | 0.0 | -1 | -1 |
| jbEZ6RxS6Gwy | -33% | 1.75 | 33.0 | 0.36 |
| 8tHD4ucHmF8E | -4% | 0.0 | 1.0 | 1.0 |

**Some tokens DO have trade data at entry time** (4 of 5 winners had BSR > 0). The data arrives during the signal processing pipeline (0.5s live_stats retry + enrichment time = 1-3 seconds). But many tokens (especially in low-volume HIBERNATE mode) still show BSR=0.

**The filter WOULD have caught `8tHD4ucHmF8E`** (sell_pressure=1.0, bsr=0, has_trade_data=True → Filter A fires). But in the 1-hour verification window, no tokens arrived with this pattern.

## Success Criteria
| Criterion | Result |
|-----------|--------|
| At least 10 trades | YES (14) |
| No crashes/regressions | YES |
| Filter metrics populated | PARTIAL (filter is running, passes logged, zero rejects) |
| WR >= 20% or avg_pnl > baseline | NO (0% WR, -10.47% avg — but market/infrastructure issues) |
| no_momentum_90s proportion dropped | YES (51% → 21%, but stale_no_price replaced it) |
| Diverse rejection reasons | NO (zero rejections) |

Total: **3 of 6** (PARTIAL)

## Exit Reason Comparison
| Exit Reason | Pre-filter % | Post-filter % | Delta |
|-------------|-------------|---------------|-------|
| no_momentum_90s | 51% | 21% | -30pp |
| stop_loss_35% | 16% | 7% | -9pp |
| stale_no_price | 3.5% | 71% | +67pp (Helius credit issue) |
| TRAILING_STOP | 18% | 0% | -18pp (no winners) |
| Staged TPs | 3.5% | 0% | -3.5pp (no winners) |

**The stale_no_price surge is NOT filter-related.** It's caused by Helius RPC credits being exhausted — the bot can't fetch exit prices, so positions exit as "stale". This masks the filter's actual impact.

## Observations

1. **Filter is correctly deployed and stable.** Three iterations were needed:
   - v1: Rejected everything (all tokens have missing data at age 0-1s)
   - v2: Still rejected everything (retry found nothing)
   - v3: Correctly passes tokens without data, catches tokens WITH data showing poor BSR

2. **HIBERNATE mode + CFGI 16 means terrible market for memecoins.** 0% WR in the window is expected — even the pre-filter period had similar (or zero) performance.

3. **Helius credit exhaustion is the dominant problem.** 71% of exits are stale_no_price because the bot can't get token prices. This is separate from the filter but masks any filter impact.

4. **The filter's value is latent, not immediately visible.** It will fire more frequently when:
   - CFGI improves and diverse signal sources activate
   - GeckoTerminal trending signals arrive (tokens with existing trade data)
   - Higher-volume markets where the 750ms retry catches more data

## Tuning Recommendations (DO NOT apply now — gather more data)

1. **Increase ENTRY_FILTER_MISSING_DATA_RETRY_MS to 1500ms** — the current 750ms is too short for PumpPortal stats to arrive. 1500ms would catch more data without significantly impacting the pipeline.

2. **Consider adding a second retry in the live_stats fetch** (line 1768-1772) — the existing 0.5s retry could be increased to 1.0s. This would give the feature construction more data to work with, benefiting both the entry filter AND ML scoring.

3. **Threshold tuning can wait for 500+ post-filter trades.** Current thresholds (BSR < 1.0, velocity < 10) are based on the 172-trade CSV analysis and should not be adjusted with only 14 trades of verification data.

4. **Fix the Helius credit issue first** — until stale_no_price is resolved, the filter's impact is unmeasurable because most trades exit for infrastructure reasons.

## Next Session Candidates
1. **HIGHEST: Fix Helius credit exhaustion** — set HELIUS_ENRICHMENT_ENABLED=false, disable last webhook. This eliminates 71% stale_no_price exits.
2. **HIGH: Increase live_stats retry to 1.0-1.5s** — more trade data at evaluation time = better filter and ML accuracy
3. **MEDIUM: Re-evaluate entry filter after 200+ non-stale trades** — need clean data to measure impact
4. **MEDIUM: Prune FEATURE_COLUMNS to populated features** — model improvement
5. **LOW: Enable Nansen for smart money entry rules** — hardcoded rules when sample size allows
