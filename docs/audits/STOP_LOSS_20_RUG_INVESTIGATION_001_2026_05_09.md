# STOP-LOSS-20-RUG-INVESTIGATION-001 — Findings & Filter Recommendation

**Date:** 2026-05-09
**Mode:** Read-only investigation. NO code changes, NO env changes, NO redeploys.
**Verdict:** 🟢 **DEPLOY-RECOMMENDED.** Filter F1 designed and validated; follow-on deploy prompt at `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`.

## §1 Finding

`stop_loss_20%` is the largest single SD-paper bleed since 2026-05-02 (n=65, sum −6.03 SOL, 0% WR, mean −0.093/trade). Hold time is 0.10-2.02s (median 0.99s); median observed entry-to-exit drop is −74.0%; peak_price is NULL on 100% of rows (no observed up-tick before exit). The label is structurally a misnomer — these trades didn't drift to −20%, they rugged sub-second and were caught at the next 2-second exit-check tick. The label is the static f-string `f"stop_loss_{0.20:.0%}"` (`bot_core.py:1822-1823`); any drop ≥20% triggers it.

## §2 Verification of pre-claims

All STOP gates pass. STOP-A pre-claims (hold time, observed drop, 0% WR, n≈61) match DB exactly (n=65, sum −6.03 SOL, hold median 0.99s, drop median −74.03%). STOP-B: SD_MC_CEILING_002 gate intact at `signal_aggregator.py:1846-1881`; Railway env `SD_MC_CEILING_USD=3000` confirmed live. STOP-C: features_json populated on 186/186 (100%) rows. STOP-D: sample size adequate (65/128/186 across windows). STOP-E and STOP-F evaluated against filter — both pass with margin. STOP-G: no concurrent session conflict.

## §3 Hypothesis test results

**Smoking gun**: `market_cap_at_entry` cleanly separates RUG from WIN with **zero overlap** at the existing $3K threshold:

| metric | RUG (n=65) | WIN (n=208) |
|---:|---:|---:|
| min | $3,181 | $321 |
| median | $7,881 | $623 |
| max | $181,519 | $832 |
| % > $3,000 | **100.0%** | **0.0%** |

**Why the SA SD_MC_CEILING_002 gate doesn't catch this:** the SA gate (signal_aggregator.py:1846-1881) computes MC from `vSolInBondingCurve / vTokensInBondingCurve` *carried in raw_data at PumpPortal-publish time*. For fresh pump.fun tokens, raw_data carries the seed values (vSol≈30, vTokens≈1.073e9), so SA-computed MC ≈ $2,400 — always under $3K. Between signal-publish and bot_core fill (1-15s), Jupiter / GeckoTerminal indexes the token and returns a *current* USD price reflecting in-flight sniper buys. `paper_buy._get_token_price(mint)` (paper_trader.py:96-139) prefers Jupiter's live price over the BC fallback. The DB column `market_cap_at_entry = entry_price * 1B` reflects this fill-time price. The gate is structurally inert against this failure mode because it gates on signal-time data while the failure mode is fill-time price divergence.

**Other features tested — all fail discrimination.** features_json fields all default to sentinels for fresh tokens age <30s (HOLDER-DATA-PIPELINE-001 era data-availability bypass): `holder_count`, `buy_sell_ratio_5min`, `unique_wallet_velocity` all sentinel; `bonding_curve_progress` cluster at 0.354 (pump.fun fresh-mint constant) for 100% of rugs and 99.5% of wins; `token_age_seconds` 100% <5s on both; `ml_score`, `slippage_pct`, `market_mode_at_entry`, `cfgi_score`, `rugcheck_score`, `hour_of_day` all show ratios in [0.82, 1.21]. Position sizing is 1.7× larger on rugs (median 0.159 vs 0.094 SOL), driven by ML+confidence multipliers preferentially boosting on snipers' favorite signals — amplifies but does not cause.

## §4 Candidate filter F1 outcomes

**F1 — fill-time MC ceiling.** Reject the trade if `entry_price * 1_000_000_000 > BOT_CORE_FILL_MC_CEILING_USD` (default 0/disabled, recommend $3,000).

| window | threshold $3k blocked | NET LIFT | per-day | FP winners |
|---|---:|---:|---:|---|
| 7d (since 2026-05-02) | 69 / 473 | +6.20 SOL | **+0.93 SOL** | 0 / 211 (0%) |
| 14d (since 2026-04-25) | 139 / 1,091 | +11.00 SOL | **+0.80 SOL** | 0 / 349 (0%) |
| 17d POST-cliff (2026-04-22+) | 203 / 1,493 | +14.65 SOL | **+0.88 SOL** | 0 / 544 (0%) |

Estimates converge around **+0.80-0.93 SOL/day** with **zero winner false positives** across all three windows. STOP-F (≥+0.30 SOL/day) cleared by 2.7-3.1×. STOP-E (≤10% winner-SOL loss) cleared at 0%.

Tighter thresholds ($1k, $2k) lift another +0.6 SOL/day but at the cost of much larger blast radius (61% of trades blocked at $2k; minor winner false positives at $1k). Recommend $3k for parity with the existing SA gate, conservative blast radius (14% blocked), zero FP cost. Tightening can follow as a separate post-deploy sweep.

## §5 Verdict + ROI

🟢 **DEPLOY-RECOMMENDED at $3,000.**

- **Forward ROI:** +0.80-0.93 SOL/day on this sample (well above STOP-F floor of +0.30).
- **Blast radius:** ~25 trades/day blocked (14% of SD-paper rate).
- **Winner false positives:** 0% across all windows.
- **Reversibility:** env-var control `BOT_CORE_FILL_MC_CEILING_USD=0` disables instantly.
- **Risk class:** paper-only at flip (TEST_MODE=true unchanged). No live wallet impact.

## §6 Recommendations

1. **Deploy F1 at $3,000 via the follow-on prompt** (`docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`). Single env var on bot_core service. Code change in `paper_trader.paper_buy` with default-disabled fallback.
2. **Observability:** add Redis counter `bot:filter:fill_mc_ceiling:rejects:{date}` (INCR + EX 86400) for per-day rejection visibility.
3. **Re-evaluate at +14d POST-deploy** with a `STOP-LOSS-20-RUG-FILTER-EVAL-001` audit. Decide: keep at $3k / tighten to $2k / loosen to $5k. Track in roadmap.
4. **Open companion items (do NOT block deploy):**
   - **PAPER-ENTRY-PRICE-DENOMINATION-001** (Tier 3 🟢) — investigate why TRAILING_STOP winners cluster at $321-832 MC (well below the BC fresh-mint baseline ~$2,400). Likely Jupiter v3 returning sub-baseline prices for fresh pump.fun pools. Doesn't affect F1 but explaining it could surface a separate observability issue.
   - **OBS-INTRA-HOLD-DRAWDOWN-001** (already proposed Tier 2 🟢) — peak_price NULL on 100% of rugs prevents direct measurement of "did stop_loss_20% amputate winners". Add `min_price_during_hold` column. Independent of F1.
   - **NO-MOMENTUM-90S-AUDIT-001** (already in roadmap, Tier 1) — separate bleed channel; F1 incidentally blocks ~12 of 134 no_momentum_90s rows in the 7d window (about 9%) because some no-momentum tokens are also high-MC sniper plays. This is positive incidental coverage, not the main lever for that bleed.

## §7 Unknowns / open questions

1. **The May 8 spike** (40 of 65 rugs in the 7d window). Could be a pump.fun ecosystem shift, market-mode spillover, or transient cluster. F1 is forward-protective regardless of cause; no need to investigate before deploy.
2. **Why the SA gate's fail-open path may also be a contributor.** When `vSolInBondingCurve` / `vTokensInBondingCurve` is missing OR `market:sol_price` Redis key is empty, the SA gate passes the signal through. F1 doesn't depend on this — it's a fill-time filter — but tightening the SA gate's fail-open behavior (e.g., reject if BC reserves data is missing on SD signals) is a complementary lever.
3. **Live-mode parity.** F1 design is paper-only at this stage. The live-mode equivalent (in `services/execution.py` after price quote, before swap submission) is straightforward but should be a separate session if/when V5a flip is approved.

The deploy follow-on is bounded, reversible, env-controlled, and data-supported. No live-wallet exposure. Single-lever session ready.

---

**Investigation evidence trail:**
- Code archaeology: `.tmp_stop_loss_20_rug/01_exit_logic.md`, `02_entry_path.md`, `04_gate_verification.md`
- Field sample: `.tmp_stop_loss_20_rug/03_field_sample.md` (+ `03_field_sample.txt` raw)
- Data analysis: `.tmp_stop_loss_20_rug/05_signal_vs_fill.md`, `06_discriminative_features.md`, `07_sizing.md`, `08_temporal.md` (+ `phase2_output.txt`)
- Filter design + counterfactual: `.tmp_stop_loss_20_rug/09_candidate_F1.md` (+ `verify_output.txt`)
- Deploy prompt: `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md` (NEW, this session)
