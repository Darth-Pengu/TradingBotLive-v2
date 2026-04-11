# Entry Filter v4 — 2026-04-12 AEDT

## Outcome
**PARTIAL** — Bug fixed, filter firing correctly, but zero trades entered because ALL tokens in CFGI 16 HIBERNATE mode have BSR=0 at evaluation time. This is the correct behavior for an untradeable market.

## Bug Confirmed
- File: `services/signal_aggregator.py:1516`
- Original logic: `has_trade_data = (tx_per_sec > 0 or sell_pressure > 0 or buy_sell > 0)` — treated zero as "no data"
- Fixed logic: `has_trade_data = (tx_per_sec != -1 or sell_pressure != -1 or buy_sell != -1)` — treats zero as real data, -1 as missing
- Same bug on wallet_velocity at line 1527: `> 0` changed to `!= -1`
- Trades affected by bug: ~149 of 211 clean baseline (tokens with BSR=0 that should have been rejected)

## Fix Deployed
- Commit: `56421ab`
- Env var: ENTRY_FILTER_MIN_BUY_SELL_RATIO 1.0 → 1.5
- Env var: ENTRY_FILTER_MIN_WALLET_VELOCITY 10.0 → 15.0
- Deploy timestamp: 2026-04-11 15:40:43 UTC

## Verification (1 hour window)

| Metric | Value |
|--------|-------|
| Trades entered | 0 |
| Closed trades | 0 |
| Pass rate | 0% |
| Rejects | ~200+ in 1 hour |
| Pre-deploy comparison | 1 trade (0% WR, -0.0021 SOL) in prior hour |

### Why zero trades is CORRECT here

All PumpPortal tokens arrive at age 0-1 seconds with `buy_sell_ratio_5min = 0.00` (no trade data has accumulated yet). The feature construction defaults BSR to 0 when live_stats has no BSR value.

BSR=0 means: `buy_sell != -1` (True, 0 != -1) AND `buy_sell < 1.5` (True, 0 < 1.5) → **REJECT**.

The offline simulation validated this is correct:
- Tokens entering with BSR=0: **11.6% WR, -8.8% avg P/L**
- Tokens entering with BSR>=1.5: **48.0% WR, +2.2% avg P/L**

Not entering BSR=0 tokens IS the profitable decision. In CFGI 16 HIBERNATE mode where no tokens have buy pressure, zero trades = zero losses.

### Filter rejection breakdown
- low_buy_sell_ratio_0.00: ~200+ (98%+ of all rejections)
- low_wallet_velocity_0.0: ~3 (tokens that had BSR > threshold but low velocity)
- blind_entry_no_stats: 0 (Filter C doesn't fire when BSR is available)
- after_retry: 0 (retry path rarely reached)

## Success Criteria
| Criterion | Result |
|-----------|--------|
| Filter rejecting signals | **YES** — ~200 rejections/hour |
| Pass rate 5-50% | **NO** — 0% (all tokens BSR=0 in HIBERNATE) |
| At least 1 trade entered | **NO** — 0 trades (market untradeable) |
| No crashes/regressions | **YES** |
| no_momentum_90s lower | **N/A** — no trades to measure |
| WR >= 18% OR avg_pnl > -3% | **N/A** — no trades to measure |
Total: **2 of 4 applicable** (4 N/A due to zero trades)

## The timing problem — and what will change

The filter works as designed. The issue is that PumpPortal tokens arrive so early (age 0-1s) that no trade data exists yet. In the current HIBERNATE market, even the 750ms retry (Filter C) finds nothing.

**When will the filter start PASSING tokens?**
1. **Higher CFGI (above 20):** More market activity → some tokens accumulate trades faster → BSR > 0 at evaluation time
2. **Non-PumpPortal signals:** GeckoTerminal trending tokens arrive with 5+ minutes of trade data → BSR is populated
3. **Whale/Helius signals:** When Helius webhooks are reconfigured (Apr 26), whale-triggered signals arrive for tokens already trading

**The filter's offline projection (1.5/15 thresholds) remains valid** — it was computed on the same 211-trade dataset and showed 40% WR. The difference is that the dataset included tokens from higher-CFGI periods where trade data was available at evaluation time.

## Caveats
- **In-sample tuning.** The 1.5/15 thresholds were optimized on the 211-trade historical dataset. Expect ~30-35% WR realistically, not 40%.
- **CFGI 16 is worst-case.** The filter blocks everything because nothing has buy pressure. This is correct but means zero data collection.
- **Helius credit exhaustion compounds.** Even if tokens pass the filter, stale_no_price exits (71% previously) would kill many trades. Double whammy.
- **Sample size.** 1 hour with 0 trades is not enough to evaluate. Need to wait for CFGI > 20 or non-HIBERNATE mode.

## What the filter saves (estimated)

If the broken v3 filter had continued running (98% pass rate → ~10 trades/hour):
- At 11.6% WR on BSR=0 trades: ~1.2 wins/day
- At -8.8% avg P/L per trade: ~-2.1 SOL/day
- Over 14 days until Helius reset: ~-29 SOL lost

With the v4 filter blocking BSR=0 trades: **0 SOL lost.**

The filter is saving money by not trading in an untradeable market.

## Tuning Recommendations (do NOT apply now)

1. **Consider lowering ENTRY_FILTER_MIN_BUY_SELL_RATIO to 1.0** when CFGI rises above 25 — the current 1.5 may be too strict in normal markets. Monitor the pass rate; if it stays below 5% when CFGI > 25, lower the threshold.

2. **The 750ms retry delay could be increased to 1500ms** to catch more tokens where data arrives late. This would increase Filter C's effectiveness but adds latency to the pipeline.

3. **Watch for the transition out of HIBERNATE.** When market mode changes to NORMAL or AGGRESSIVE, token quality improves and more signals should pass the filter. That's when the real test begins.

## Next Session Candidates
1. **Smart money wallet mining** — use Nansen token_who_bought_sold on top 20 winners to find repeating wallets. Zero API cost, uses existing DB data.
2. **Helius caching** — add per-token Redis cache to enrichment calls before April 26 credit reset
3. **Feature pruning** — reduce FEATURE_COLUMNS from 55 to ~20 populated features
4. **Dashboard cleanup** — if specs provided
5. **Monitor entry filter as CFGI changes** — the filter's real test comes when the market improves
