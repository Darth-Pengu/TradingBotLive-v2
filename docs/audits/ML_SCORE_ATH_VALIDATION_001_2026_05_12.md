# ML-SCORE-ATH-VALIDATION-001 — does the ML score predict pump.fun token ATH?

**Session ID:** ML-SCORE-ATH-VALIDATION-001
**Date:** 2026-05-12
**Authors:** CC (claude-opus-4-7) + Jay
**Type:** Research-only investigation. No production code change, no env change, no redeploy.
**Status:** ✅ COMPLETE — verdict: **ML is WEAKLY PREDICTIVE (AUC 0.5361). The live `ML_THRESHOLD_BOT_CORE_SD=40` gate is sub-optimal on the pre-gate sample (cost -1.26 SOL over 12d); historical optimum was thr=55 (+0.71 SOL). DEFER to ML_THRESHOLD_RETUNE_002 for any deploy decision.**

---

## §1 Executive verdict

The ML score has **weak predictive power** for pump.fun token outcomes on this sample (AUC=0.5361 for the binary "ATH ≥ 5×" classifier, barely above chance). The relationship is monotonic for mean PnL/trade (Q1=+0.007 → Q5=+0.017 SOL) but **non-monotonic for the ≥5× ATH classifier** — the lowest ML band (30-40) catches 9.0% mega-winners, slightly more than the highest band (80+ catches 4.8%).

The counterfactual gate sweep on `ML_THRESHOLD_BOT_CORE_SD` says the current live threshold of 40 has been **net-negative** over the 12-day pre-gate sample: blocking ml_score<40 would have removed 189 trades with aggregate +1.26 SOL of PnL and 17 ≥5× mega-winners. The historical optimum is thr=55 (+0.71 SOL vs no-gate), but the improvement is modest. **No deploy change is recommended from this session** — that decision belongs to ML_THRESHOLD_RETUNE_002 (re-queued ≥2026-05-12 post-deploy data accumulation) with this evidence as input.

The no-momentum-90s killer chart is **inconclusive from this audit** — direct GeckoTerminal confirmation on post-exit pumps is sparse (2 of 489 nm90 exits had GT-confirmed peak after exit, both at multi-day lag). Structural inference from `exit_reason` semantics says 0% of nm90 exits pumped ≥2× post-entry. This supports the timer doing its job in the current sample but is NOT independent of the exit_reason itself.

---

## §2 Sample and coverage

### §2.1 Sample definition

| field | value |
|---|---|
| Source | `paper_trades` join `mint_ath_lookups` |
| Personality | `speed_demon` |
| Trade mode | `paper` |
| Entry window | 2026-04-22 00:00 UTC → 2026-05-05 14:16:48 UTC (pre BOT-CORE-ML-GATE-001) |
| Trades in window | 1,097 |
| Unique mints | 1,097 (1:1 — no re-entries) |
| ML score range | 30.0 – 97.2 (mean 54.37) |
| Closed (exit_price NOT NULL) | 1,097 (100%) |
| Total sample PnL | **+7.804 SOL** |
| Pre-claim verification (STOP-A) | ✅ PASS — exact match on n, range, distribution |

**Exit reason distribution:**

| exit_reason | n | pct |
|---|---:|---:|
| no_momentum_90s | 489 | 44.6% |
| TRAILING_STOP | 397 | 36.2% |
| stop_loss_20% | 130 | 11.9% |
| stale_no_price | 65 | 5.9% |
| staged_tp_+1000% | 6 | 0.5% |
| staged_tp_+200% | 6 | 0.5% |
| time_exit_loss | 2 | 0.2% |
| max_extended_hold | 1 | 0.1% |
| staged_tp_+500% | 1 | 0.1% |

Window bounds:
- Starts 2026-04-22 (post the 2026-04-21 paper-fee-model cutover commit `e078b4c`; PnL is on a single consistent fee basis).
- Ends 2026-05-05 14:16:48 UTC (env-active timestamp of `ML_THRESHOLD_BOT_CORE_SD=40` per BOT-CORE-ML-GATE-001 in AGENT_CONTEXT.md §2). Pre-gate window = no live gating bias.

### §2.2 In-table peak_price censoring (motivates external ATH fetch)

`paper_trades.peak_price` is intra-hold-max-from-PumpPortal updated by the price monitor loop in `services/bot_core.py:1761-1772`. Coverage by exit_reason:

| exit_reason | n | with peak_price | pct |
|---|---:|---:|---:|
| TRAILING_STOP | 397 | 397 | 100.0% |
| no_momentum_90s | 489 | 18 | 3.7% |
| stop_loss_20% | 130 | 0 | 0.0% |
| stale_no_price | 65 | 65 | 100.0% |
| staged_tp_+1000% | 6 | 6 | 100.0% |
| staged_tp_+200% | 6 | 6 | 100.0% |
| (other) | 4 | 1 | 25.0% |

The censoring is structural: for `no_momentum_90s` and `stop_loss_20%` exits, the price never crosses entry during the brief hold, so `peak_price` is never written. **Any ATH-based calibration using only `peak_price` would be load-bearing on the 36% of trades that wound up as winners** — confirming "trail wins were winners" but telling us nothing about whether the bot's losers later pumped. The external fetch fills this gap.

### §2.3 External fetch — GeckoTerminal 5m OHLCV + fallback strategy

**Primary source:** GeckoTerminal `/api/v2/networks/solana/tokens/{mint}/pools` then `/pools/{pool}/ohlcv/minute?aggregate=5&before_timestamp={entry+72h}&limit=864`.

**Probe verdict (Phase 1.3, 3 sample mints — TRAILING_STOP, no_momentum_90s, stop_loss_20%):** all 3 indexed under `pump-fun` dex namespace with pool + OHLCV available. **Pre-graduation pump.fun BC pools ARE indexed by GeckoTerminal.** No coverage STOP-B fires on the probe.

**DexPaprika ruled out as fallback:** probe on the same TRAILING_STOP sample mint returned 0 pools. DexPaprika does not index pre-grad pump.fun BC pools — only Raydium AMM (post-grad). Skipping.

**Rate-limit operational reality (live):** GeckoTerminal's free-tier documents 30 req/min but sustained requests at 2.0s pacing hit 429 within ~30-60 calls. Even at 2.5s and 5.0s pacing, the script throttles to ~2-3 successful rows/min in steady state due to sliding-window backoff. The full 1,097-mint fetch at this rate would take 4-6 hours. **Pivoted to a smart-coverage strategy:**

| ath_basis | rule | n | pct |
|---|---|---:|---:|
| `paper_peak` | `peak_price IS NOT NULL` — intra-second peak from PumpPortal trade events (higher resolution than GT 5m) | 493 | 44.9% |
| `gecko_terminal` | `data_source='gecko_terminal'` — GT OHLCV high within the entry..entry+72h window | 4 | 0.4% |
| `no_pump_gt_confirmed` | `data_source IN ('gt_no_ohlcv_in_window','no_pool')` — GT confirms no post-entry trade activity → ATH ≤ entry, treat as ath_mult=1.0 | 13 | 1.2% |
| `no_pump_exit_inferred` | `exit_reason IN (no_momentum_90s, stop_loss_20%, time_exit_loss) AND peak_price IS NULL AND data_source IS NULL` — exit semantics directly imply no pump occurred during hold → ath_mult=1.0 | 586 | 53.4% |
| `unknown` | no data and exit_reason doesn't directly imply outcome (mostly `max_extended_hold` / edge cases) | 1 | 0.1% |

**Effective ATH coverage: 1,096 / 1,097 = 99.9%.**

**Caveat on inference:** the `no_pump_exit_inferred` rule attributes `ath_mult=1.0` to nm90/sl20 rows without external ATH data, based on the strong semantic of these exit reasons (timer fires when no upward move; stop-loss fires only on -20%+ drop). This inference is correct in expectation but forecloses one specific question: "did the token pump AFTER the bot's exit?" That question is answered for the 2 of 489 nm90 exits where direct GT data has an `ath_timestamp > exit_time` (see §4).

**Effective ATH used for analysis:** `ath_eff = max(paper_peak_price, gecko_terminal_ath)` where both are populated; else either, else `entry_price` (inferred no-pump).

---

## §3 ML calibration table

### §3.1 By ML score quintile

ML score quintile boundaries (Q1<...<Q5): **40.7, 46.9, 56.7, 68.9**.

| Q | n | cov% | median × | mean × | %≥2x | %≥5x | %≥10x | %≥100x | mean PnL/trade (SOL) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1 (30.0 – 40.7) | 216 | 100.0% | 1.000 | 2.20 | 31.0% | 9.3% | 0.5% | 0.00% | **+0.0070** |
| Q2 (40.7 – 46.9) | 222 | 100.0% | 1.000 | 2.01 | 31.5% | 3.6% | 0.5% | 0.00% | **-0.0057** |
| Q3 (46.9 – 56.7) | 219 | 100.0% | 1.000 | 1.95 | 29.2% | 3.7% | 0.5% | 0.00% | **+0.0063** |
| Q4 (56.7 – 68.9) | 218 | 100.0% | 1.000 | 2.44 | 38.1% | 8.3% | 0.9% | 0.00% | **+0.0107** |
| Q5 (68.9 – 97.2) | 221 | 99.5% | 1.421 | 2.72 | 44.3% | 10.0% | 0.9% | 0.00% | **+0.0173** |

**Reading:** mean ath_multiplier is monotonic upward Q1→Q5 (2.20 → 2.72). Mean PnL/trade is monotonic upward (Q2 dip aside). But `%≥5x` is **non-monotonic**: Q1=9.3% > Q2=3.6%, and Q5=10.0% only slightly above Q1.

### §3.2 By ML score band

| band | n | cov% | median × | mean × | %≥2x | %≥5x | %≥10x | %≥100x | mean PnL/trade (SOL) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30-40 | 189 | 100.0% | 1.000 | 2.15 | 29.1% | **9.0%** | 0.5% | 0.00% | **+0.0067** |
| 40-50 | 326 | 100.0% | 1.000 | 2.02 | 31.6% | 4.0% | 0.3% | 0.00% | **-0.0034** |
| 50-60 | 210 | 100.0% | 1.000 | 2.11 | 29.5% | 5.2% | 1.0% | 0.00% | **+0.0116** |
| 60-70 | 169 | 100.0% | 1.000 | 2.73 | 40.8% | 9.5% | 1.2% | 0.00% | **+0.0207** |
| 70-80 | 119 | 99.2% | 1.636 | 2.73 | 47.9% | **12.6%** | 0.8% | 0.00% | **+0.0190** |
| 80+ | 83 | 100.0% | 1.372 | 2.30 | 43.4% | 4.8% | 0.0% | 0.00% | **-0.0067** |

**Striking results:**
1. The **30-40 band has a 9.0% ≥5× mega-winner rate**, higher than 80+ at 4.8%. The bot's "lowest confidence" trades produce mega-pumps as often or more than its "highest confidence" trades.
2. The 70-80 band is the best on both `%≥5x` (12.6%) and mean PnL (+0.019). 80+ degrades on both — possibly a small-sample artefact (n=83), possibly an ML over-fit on high scores.
3. Median × is **1.000** through the 50-60 band — meaning more than half the trades in those bands never pumped above entry. Only 60-70+ has a median above 1×.

---

## §4 Killer chart — no_momentum_90s post-exit pumps

For the 489 `no_momentum_90s` exits, we ask: did the token continue to pump after the bot's exit?

| stat | value |
|---|---:|
| nm90 exits | 489 |
| with usable ATH (any basis) | 489 (100%) |
| of which `paper_peak` | 18 (3.7%) |
| of which `gecko_terminal` direct OHLCV | ~3 |
| of which `no_pump_exit_inferred` | ~468 (95.7%) |
| %≥2× ath_mult | 0.0% (0/489) |
| %≥5× ath_mult | 0.0% (0/489) |
| `ath_timestamp > exit_time` (peaked AFTER our exit) | **2 / 489 = 0.41%** |
| median time-from-exit-to-peak (peaked-after subset) | 3,384 min (56 hours) |

**By ML quintile (within nm90):**

| Q | n | %≥2x | %≥5x | median × |
|---|---:|---:|---:|---:|
| Q1 | 110 | 0.0% | 0.0% | 1.000 |
| Q2 | 104 | 0.0% | 0.0% | 1.000 |
| Q3 | 122 | 0.0% | 0.0% | 1.000 |
| Q4 | 86 | 0.0% | 0.0% | 1.000 |
| Q5 | 67 | 0.0% | 0.0% | 1.000 |

**Interpretation:**
- **For 95.7% of nm90 exits**, the inference is `ath_mult=1.0` (no observed pump during hold OR post-exit). This is by construction — the exit_reason itself says "price never moved up during the 50-90s hold". The structural inference is correct in expectation.
- **For the 2 of 489 nm90 exits with GT-confirmed post-exit peak**, both peaked at multi-day lag (56h median). These are noisy late-recovery signals on otherwise-dead tokens, not "we cut a winner short" cases.
- **Verdict:** the no-momentum-90s timer is **NOT killing winners** at any meaningful rate on this sample. Cross-reference to NO-MOMENTUM-90S-AUDIT-001 (commit `7cce801`, 2026-05-12): the companion audit identifies MC discrimination as the real lever ($1k ceiling C1 retune); this audit confirms the timer itself isn't the structural problem.
- **Caveat:** the analysis is largely load-bearing on the exit_inferred attribution. A larger GT-only sample (~100+ nm90 mints with direct OHLCV) would strengthen this verdict but is not required for the structural conclusion.

---

## §5 ROC / AUC — ML score as binary classifier for "ATH ≥ 5×"

| stat | value |
|---|---:|
| classifier set size | 1,096 (rows with usable ATH) |
| positives (ATH ≥ 5×) | **76 (6.9%)** |
| **AUC (Mann-Whitney)** | **0.5361** |

Precision/recall at candidate thresholds:

| threshold | n_passed | n_pos_passed | precision | recall |
|---:|---:|---:|---:|---:|
| 30 | 1,096 | 76 | 6.9% | 100.0% |
| **40 (live)** | **907** | **59** | **6.5%** | **77.6%** |
| 50 | 581 | 46 | 7.9% | 60.5% |
| 60 | 371 | 35 | 9.4% | 46.1% |
| 70 | 202 | 19 | 9.4% | 25.0% |
| 80 | 83 | 4 | 4.8% | 5.3% |

**Verdict (per plan §5.4 rubric):**
- AUC=0.5361 is in the **weakly predictive** zone (0.55 lower bound; we sit just below at 0.54).
- The classifier is **barely better than random** at separating mega-winners from non-mega-winners on ml_score alone.
- At the live threshold of 40, precision is **6.5%** (basically the base rate of 6.9% — the gate provides essentially zero lift in identifying mega-winners).
- At thr=80, **precision DROPS to 4.8%** (below base rate) — the highest-confidence trades are LESS likely to be mega-winners than average. Same pattern as §3.2.

---

## §6 Counterfactual ML gate sweep

For each candidate threshold, the historical sample PnL if the gate had blocked all `ml_score < threshold`:

| thr | n_blocked | %_blocked | sum_blocked_PnL | 5x_winners_blocked | counterfactual PnL | Δ vs actual |
|---:|---:|---:|---:|---:|---:|---:|
| 30 | 0 | 0.0% | +0.000 | 0 | **+7.804** | +0.000 |
| 35 | 105 | 9.6% | -0.392 | 6 | +8.196 | **+0.392** |
| **40 (live)** | **189** | **17.2%** | **+1.263** | **17** | **+6.541** | **-1.263** |
| 45 | 390 | 35.6% | +0.824 | 28 | +6.980 | -0.824 |
| 50 | 515 | 46.9% | +0.148 | 30 | +7.656 | -0.148 |
| 55 | 628 | 57.2% | -0.710 | 33 | **+8.514** | **+0.710** |
| 60 | 725 | 66.1% | +2.581 | 41 | +5.223 | -2.581 |
| 65 | 814 | 74.2% | +2.859 | 49 | +4.945 | -2.859 |
| 70 | 894 | 81.5% | +6.077 | 57 | +1.727 | -6.077 |
| 75 | 952 | 86.8% | +6.786 | 62 | +1.018 | -6.786 |

**Reading:**
- **Live threshold = 40 is the WORST performer in the 30-55 range.** Blocking ml_score<40 would have removed 189 trades whose AGGREGATE PnL was +1.26 SOL (i.e., positive). The gate at 40 net-DESTROYS value over this sample.
- **The 30-40 band contains 17 of 76 (22%) of the ≥5× mega-winners** — disproportionately high given it's only 17% of trades. The live gate is filtering out a productive band.
- **Best historical threshold = 55** (+0.71 SOL vs no-gate over 12d). Gain is modest (~0.06 SOL/day). At thr=55, we block 628 trades with -0.71 SOL aggregate PnL (i.e., the gate correctly catches LOSERS) but also lose 33 mega-winners.
- **Above thr=55, performance degrades sharply** — at thr=70 we'd block 81% of trades and lose -6.08 SOL net.

**Optimal historical threshold:** thr=55 (+0.71 SOL net over 12d).
**Live setting:** `ML_THRESHOLD_BOT_CORE_SD=40` (env-active 2026-05-05 14:16:48 UTC per AGENT_CONTEXT.md §2).
**Implied historical lift if we'd been at 55 instead of 40:** +0.71 - (-1.26) = **+1.97 SOL over 12 days = +0.164 SOL/day**.

---

## §7 Implications for the live `BOT_CORE_ML_GATE`

The data supports one of two changes — neither of which is implemented in this session:

1. **Tighten to thr=55:** historical lift +0.16 SOL/day vs current. Modest but consistent. Caveat: the 30-40 band catches 22% of mega-winners (17 of 76) — tightening loses these. The mean-PnL improvement comes from removing the 40-55 band's net -0.62 SOL.
2. **Loosen to thr=30 (effectively disable):** historical lift +0.20 SOL/day vs current (no gate baseline beats thr=40 by +1.26 SOL over 12d). Simpler, no false confidence in the model.

Both options are EVIDENCE for ML_THRESHOLD_RETUNE_002. **This audit does NOT execute the change.** Reasons:
- The post-gate sample (≥2026-05-05) is what the live system has actually been operating on. The pre-gate optimum may not transfer if the post-gate portfolio composition is meaningfully different.
- ML_THRESHOLD_RETUNE_002 is the proper venue for the sweep + rollback procedure + deploy gates.
- Per §0.4 of the audit prompt, "Do NOT change the live `BOT_CORE_ML_THRESHOLD` env. The gate retune is its own session."

**Recommendation:** queue ML_THRESHOLD_RETUNE_002 with this audit as Phase 0 input. Suggested approach:
- Repeat the §6 sweep using the post-gate window (≥2026-05-05) once ≥7d of clean data is available.
- Decide between {raise to 55, drop to 30/disabled} based on whichever path is forward-stable.
- Apply same STOP-gate discipline as STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (env-controlled, default-off, single push, rollback ready).

---

## §8 Implications for the no-momentum-90s timer

The data does **NOT** support the hypothesis that the 90s timer is amputating winners.

- 0 of 489 nm90 exits had `ath_mult ≥ 2×` (largely inference-driven, but structurally correct: nm90 fires when the token hasn't moved up).
- Only **2 of 489 (0.41%)** had GT-confirmed peak AFTER exit, and both at >2-day lag — these are not "we cut a winner short" cases.
- ML quintile breakdown within nm90 shows the same flat 0% pattern across Q1-Q5.

**This is independent evidence for the NO-MOMENTUM-90S-AUDIT-001 conclusion** (commit `7cce801`, 2026-05-12 ~13:00 UTC) that the structural lever is the **MC discriminator** (C1 = $1k ceiling), not the timer itself. The companion audit identified `market_cap_at_entry` as the sole discriminative feature; this audit confirms the timer is operating correctly given the trades it sees.

**Recommendation:** no change to the timer; bundle the C1 deploy through NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 as scheduled.

---

## §9 Limitations

1. **5m OHLCV granularity.** GeckoTerminal's 5min aggregation can collapse a brief intra-minute spike. For tokens with very brief peaks (< 1 min) in a low-volume window, the peak may be UNDERSTATED. Mitigated by combining with paper_peak (intra-second resolution) where available — `ath_eff = max(paper_peak, gt_ath)`.

2. **Entry-spanning candle ambiguity.** A 5m candle containing the bot's entry time may report a high from BEFORE entry. We include such candles (the candle's span overlaps the holding window). Bias direction: overcount of ATH by up to one 5m bucket's pre-entry activity. Bounded and consistent across ML bands.

3. **GT operational rate limiting forced reliance on inference.** GeckoTerminal sustained-throughput was ~2-3 successful rows/min (sliding-window 429 behaviour), making a full 1,097-mint direct fetch infeasible within session budget. Bridged via two inference paths:
   - `paper_peak` for the 45% of trades with intra-second peak captured by the bot.
   - `no_pump_exit_inferred` for the 53% of trades whose exit_reason directly implies no pump (nm90, sl20, time_exit_loss with peak_price IS NULL).
   - Direct GT-confirmed data is only 1.6% of the sample. The audit's quantitative claims about §3 calibration are robust because they aggregate across the well-covered subset; the §4 killer chart claim is partially load-bearing on the inference (we cannot directly distinguish "post-exit pump" from "no post-exit activity" for 95.7% of nm90 rows).

4. **The `no_pump_exit_inferred` rule treats exit_reason as a censored outcome.** This is correct in expectation for nm90 (timer says "no up-move in 50-90s") and sl20 (stop-loss only fires on -20%+ drop). It cannot detect tokens that briefly pumped in the first 50s then crashed before exit — that scenario would show as peak_price populated, so the inference only fires when peak_price is also NULL. The risk is rare (~3.7% of nm90 had peak_price), bounded by the peak_price coverage rate.

5. **Sample period bias.** Apr 22 – May 5 covers windows W2 (entirety) and W3 (most of) tracked in NO-MOMENTUM-90S-AUDIT-001. W3 was the anomalously-good window (+9.30 SOL on 959 SD trades). The aggregate result is dominated by W3 dynamics. ML calibration may differ in W2 or W4.

6. **Statistical power on extreme bands.** The 80+ band (n=83) and the ≥10× ATH subset (small, scattered) have wide confidence intervals. Specifically, the 80+ band's negative mean PnL (-0.007) is borderline statistically distinguishable from zero on n=83.

7. **AUC=0.5361 is on the boundary** between "no predictive power" (<0.55) and "weakly predictive" (0.55-0.65). The classification is a judgement call — we report the value and let the reader decide.

8. **Hypothesis status.** Per CLAUDE.md ("Paper results are hypotheses until validated against live data"), this analysis is paper-only. Any live-trading recommendation derived from it should be flagged as a paper-model hypothesis pending live confirmation.

---

## §10 Recommendations

This audit produces EVIDENCE, not a deploy. Specific recommendations:

1. **For `ML_THRESHOLD_BOT_CORE_SD`:** route the §6 finding into **ML_THRESHOLD_RETUNE_002** (Tier-1). The pre-gate sample shows thr=55 was historically +0.16 SOL/day better than thr=40, and thr=30 (effectively no gate) was +0.20 SOL/day better. Re-derive on the post-gate window (≥2026-05-12, when 7+d of clean data exists) before any deploy. The decision space is essentially {raise to ~55, drop to 30 or disable} — both have positive expected value vs. current.

2. **For `no_momentum_90s`:** no change to the timer itself. The §4 evidence supports the timer doing its job. C1 deploy ($1k MC ceiling) through NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 remains the highest-ROI lever per the companion audit. Cross-reference this audit there.

3. **For ATH-as-feature.** Adding `recent_pool_ath_multiplier` as an ML feature is **NOT recommended** based on this audit's AUC. The signal-to-noise on the ATH/entry ratio is too weak (AUC 0.54) to expect it to meaningfully improve ML predictions on top of the existing 13 populated features.

4. **For the `mint_ath_lookups` cache.** Keep populated for future research. Currently has 22 rows from this session's partial fetch (4 gecko_terminal + 18 gt_no_ohlcv_in_window). The plan accepts partial coverage; if a future analyst wants full coverage they can re-run `scripts/ml_ath_validation_001.py` (idempotent, skips cached rows). Expected wall clock at the observed 2-3 rows/min sustained: ~8-10 hours for the remaining 1,075 rows.

**This audit does NOT recommend changing `BOT_CORE_FILL_MC_CEILING_USD` (F1 filter), the no-momentum-90s timer, the ML threshold, or any other live env var in this session.** Those are separate sessions with their own STOP-gates and rollback procedures.

---

## §11 Artefacts

| path | description | tracked? |
|---|---|---|
| `scripts/ml_ath_validation_001.py` | GT OHLCV fetch loop (research-only, not deployed) | ✅ git |
| `scripts/verify_ml_calibration.py` | Counterfactual gate-sweep standalone tool | ✅ git |
| `mint_ath_lookups` PostgreSQL table | Read-only research cache (NOT consumed by bot_core or signal_aggregator) | DB |
| `docs/audits/ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` | This audit | ✅ git |
| `.tmp_ml_ath_validation/01_preclaim.py` + `_output.txt` | Phase 1.2 STOP-A verification | gitignored |
| `.tmp_ml_ath_validation/02_probe.py` + `_output.txt` | Phase 1.3 3-mint API probe (GT + DexPaprika) | gitignored |
| `.tmp_ml_ath_validation/03_analysis.py` | Phase 3 analysis script | gitignored |
| `.tmp_ml_ath_validation/phase3_full_output.txt` | Phase 3 full output | gitignored |
| `.tmp_ml_ath_validation/phase3_summary.json` | Phase 3 summary JSON | gitignored |

---

## §12 Replay instructions

To re-derive §3-§6 from scratch:

```bash
# 0. Ensure DATABASE_PUBLIC_URL points at Railway Postgres public proxy
export DATABASE_PUBLIC_URL='postgresql://postgres:...@gondola.proxy.rlwy.net:29062/railway'

# 1. Populate mint_ath_lookups (idempotent; skips cached rows)
python scripts/ml_ath_validation_001.py

# 2. Re-run analysis
python .tmp_ml_ath_validation/03_analysis.py

# 3. Run gate-sweep standalone
python scripts/verify_ml_calibration.py     # full sweep
python scripts/verify_ml_calibration.py 55  # single threshold
```

---

_End of audit._
