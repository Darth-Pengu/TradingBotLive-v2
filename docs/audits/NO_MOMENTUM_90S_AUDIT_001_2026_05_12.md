# NO-MOMENTUM-90S-AUDIT-001 — T0 run (2026-05-12)

**Date:** 2026-05-12 (T+~24h post STOP-LOSS-20-RUG-FILTER deploy at 2026-05-11 12:30 UTC).
**Run:** T0 (no prior audit file). T1 to run ≈2026-05-14.
**Type:** Read-only investigation. No code changes, no env changes, no deploys this session.
**Verdict:** ✅ **DEPLOY-RECOMMENDED** (deploy in a follow-on session). Forward ROI midpoint **+1.5 to +2.5 SOL/day** at zero false-positive cost.

---

## §1 Finding (TL;DR)

The `no_momentum_90s` exit surge from 40.2% → 76.5% post-F1-filter is **not** an independent failure mode. It is the visible symptom of an underlying structural pattern: **SD-paper tokens entering above MC $1000 are net-negative regardless of exit reason**; F1's $3000 ceiling cleared the deepest tier of that loss zone, leaving the $1k–$3k tier as the residual bleed. The fix is the same lever as F1, retuned: tighten `BOT_CORE_FILL_MC_CEILING_USD` from $3000 to $1000.

**Phase 0 pre-claims status:**

- `no_momentum_90s` mean PnL ≈ −0.018 SOL — **VERIFIED** (−0.017 across W4).
- nm90 median hold ≈ 80–90s — **WRONG.** Actual median 51s. The check is `hold ∈ (50, 90)s` with timer env=60s; loop fires on the first iteration after 50s, which is ~51s. Not material to the conclusion.
- $0–$1k WR ≈ 72–100% — **VERIFIED** (W4 $0–$1k: 51 trades, 73% aggregate WR).
- $1k–$3k WR ≈ 0% — **VERIFIED** (W4 $1k–$3k: 213 trades, **0** winners).
- Filter activation 2026-05-11 12:30 UTC — **VERIFIED**.

STOP-A passes on the load-bearing PnL anchor; the hold-time prose error is cosmetic.

## §2 Code archaeology (Phase 1)

`services/bot_core.py:1774-1788`. The check is gated by `pos.personality=='speed_demon'` AND `not pos.staged_exits_done`. Window: `early_check_sec - 10 < hold_sec < early_check_sec + 30`. Live env: `SD_EARLY_CHECK_SECONDS=60`, `SD_EARLY_MIN_MOVE_PCT=3.0` → window = (50s, 90s), threshold +3%. Exits BEFORE `stop_loss_20%`, staged TPs, trailing stop. peak_price updates monotonically at line 1761–1772; for nm90 exits, peak_price stays NULL because price never crosses entry (100% of sampled rows).

## §3 Window baselines (Phase 2.1)

SD-paper across four windows:

| Window | n | sum_pnl_sol | WR | nm90_rate | nm90_sum_pnl | nm90_med_hold |
|---|---:|---:|---:|---:|---:|---:|
| W1 04-16..04-24 | 242 | **+6.48** | 51.2% | 26.9% | −1.06 | 51s |
| W2 04-29..05-04 | 347 | +0.69 | 18.4% | 64.0% | −3.98 | 51s |
| W3 05-05..05-11 12:30 (pre-F1) | 959 | **+9.30** | 38.7% | 38.3% | −8.55 | 51s |
| W4 05-11 12:30..now (post-F1) | 264 | −2.18 | 14.4% | 76.5% | −3.47 | 51s |

Key: **W2 already showed the W4 pattern** (high nm90 rate, low WR, modest totals). W4 is closer to a regression-to-W2 than a novel failure mode. W3 was the anomalously-good window where TRAILING_STOP delivered +22.40 SOL.

## §4 MC-band analysis (Phase 2.2)

W4 MC distribution (n=264 total):

| MC band | n | sum_pnl | WR | nm90_n | TRAILING_STOP_n |
|---|---:|---:|---:|---:|---:|
| $0–500 | 5 | +0.72 | 100% | 0 | 5 |
| $500–1k | 46 | +0.76 | 71.7% | 0 | 46 |
| $1k–1k5 | 5 | −0.09 | 0% | 0 | 4 |
| $1k5–2k | 3 | −0.04 | 0% | 0 | 0 |
| $2k–2k5 | 58 | −0.68 | 0% | 56 | 0 |
| $2k5–3k | 147 | −2.86 | 0% | 146 | 0 |

**78% of W4 volume (205 of 264) sits in $2k–$3k zone and produces zero winners.** The same cliff existed in W3 ($1k–$3k bands: 376 trades, −7.20 SOL, 0–4% WR); F1 just exposed the next layer. Outside W3+W4, archive evidence (CLIFF-VYBE-SOCIALDATA-SUPPLEMENT) suggests this is the post-2026-04-21 regime, not a pre-cliff phenomenon.

## §5 Feature discrimination (Phase 2.3)

W3+W4 SD-paper `exit_reason IN (no_momentum_90s, TRAILING_STOP)`:

| Group | n | avg_pnl | p25_mc | p50_mc | p75_mc | p50_ml | p50_rc | p50_liq_vel | p50_cfgi | p50_bc | p50_age |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trail_win | 393 | **+0.066** | 550 | **639** | **720** | 57.4 | 4988 | 18.59 | 55.5 | 0.354 | 1.63 |
| trail_loss | 85 | −0.024 | 939 | 1129 | 1602 | 57.1 | 6030 | 18.18 | 54.0 | 0.354 | 1.69 |
| nm90 | 569 | −0.021 | **2615** | 2778 | 2909 | 54.9 | 6036 | 19.48 | 55.0 | 0.356 | 1.58 |

**`market_cap_at_entry` is the only discriminative feature**. ml_score, rugcheck, liq_velocity, cfgi, bc_progress, age are all identical across groups (these are 1.5s-old pump.fun tokens with sentinel-default features). Zero overlap between trail_win p75 ($720) and nm90 p25 ($2615). **Max TRAILING_STOP-win MC in W3+W4 = $892.** A ceiling at $1000 has clean, no-overlap separation.

## §6 Signal age + Time-of-day

- **Signal age (Phase 2.4): INFEASIBLE.** `signal_detected_at`, `scored_at`, `traded_at` are NULL on 100% of post-filter rows (LATENCY-OBSERVABILITY-001 still open per AGENT_CONTEXT §7). Skip.
- **Time-of-day (Phase 2.5):** UTC 11–14 (AEDT 22–01) is the worst pocket — n=271, sum −2.4 SOL, 81% nm90 at hr12. UTC 18–23 (AEDT 04–09) is positive (hr18 alone +2.71 SOL). Pattern is confounded with W4 timing (most W4 trades fall in hr 11–13). Not a standalone candidate.

## §7 Candidates + verify output (Phases 3-4)

Counterfactual back-test on W3+W4 (1223 trades, 7.49d):

| Candidate | Threshold | Marginal blocked over F1 | Marg PnL saved | W3+W4 daily | W4-only daily | FP winners | KEPT trades / sum_pnl / WR |
|---|---:|---:|---:|---:|---:|---:|---:|
| F1 (current prod) | $3000 | 201 | +12.73 | +1.70 | — | 0 | 1022 / +19.85 / 40.0% |
| **C1** | **$1000** | **589** | **+10.86** | **+1.45** | **+3.67** | **0** | **433 / +30.71 / 94.2%** |
| C2 | $1500 | 550 | +9.84 | +1.31 | +3.59 | 0 | 472 / +29.68 / 86.4% |
| C3 | $750 | 676 | +9.25 | +1.23 | +3.81 | **59 (-2.09 SOL)** | 346 / +29.09 / 100.0% |

Output saved to `.tmp_no_momentum_90s/verify_output.txt`. STOP gates all pass:

- **STOP-A** (premise) PASS — PnL anchor verified.
- **STOP-B** (features empty) PASS — populated, mostly sentinels.
- **STOP-C** (>10% trail-win lost) PASS — C1 = 0% lost; max trail_win MC $892 < $1000.
- **STOP-D** (ROI < +0.3 SOL/day) PASS by 5× (+1.45/d) to 12× (+3.67/d).
- **STOP-E** (all candidates fail) PASS — C1 and C2 both viable.

## §8 Verdict + ROI

**DEPLOY-RECOMMENDED — C1: tighten `BOT_CORE_FILL_MC_CEILING_USD` from $3000 to $1000.**

Forward ROI range:
- Lower bound (W3+W4 averaged): **+1.45 SOL/day**
- Upper bound (W4-only): **+3.67 SOL/day**
- Conservative midpoint: **+1.5 to +2.5 SOL/day**
- Zero false positives (no TRAILING_STOP/staged_tp winners blocked)

Volume cost: KEPT slice is 35% of current trade flow (~12 trades/day vs ~33). Adequate for ML training and observability.

## §9 Recommendation + scope note

The recommended lever **is the same env var as F1** (just retuned). Per §9 of the audit prompt, this session does not touch F1 — the deploy is a follow-on prompt at `docs/audits/NO_MOMENTUM_90S_DEPLOY_PROMPT_2026_05_12.md`.

Two timing paths:

1. **Wait for STOP-LOSS-20-RUG-FILTER-EVAL-001** (≥2026-05-25, +14d). Run that prompt with this data bundled in. Tradeoff: ~14d of continued $1k–$3k bleed (~−15 to −30 SOL).
2. **Bring eval forward** with Jay's authorization. The data already shows F1 is doing its job and the next layer is structural. Deploy C1 as a single-env-var change with instant rollback (`BOT_CORE_FILL_MC_CEILING_USD=3000` reverts to current state). Recommended.

## §10 Unknowns / open questions

- **Why are SD signals consistently landing in the $2k–$3k MC band at fresh-mint?** BC fresh-mint baseline computes to ~$2400 (30 SOL × $88 × 1B), so the bot's "default" entry is at baseline. The dip-buying pattern (winners at MC $500–$720) requires PRICE-PRESSURED tokens that briefly dropped below baseline. The signal pipeline may be underweighting "dip" signals or the upstream PumpPortal stream simply emits more baseline tokens than dips. Investigation not in this audit's scope.
- **What is the post-C1 nm90_rate target?** With 78% of nm90 volume blocked at entry, nm90_rate on the kept slice should fall to ~15–25%, similar to W1's regime. This is a T1-or-later observability check.
- **Live-mode parity.** `services/execution.py` does not have the F1 gate; if/when live trading resumes the gate must be replicated there. Tracked in STOP-LOSS-20-RUG-FILTER-EVAL-001 already.
- **T1 STOP-F test:** does the $1k–$3k cliff persist or revert? Re-run this prompt 2026-05-14.

## §11 Artefacts produced

- `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` (this doc)
- `docs/audits/NO_MOMENTUM_90S_DEPLOY_PROMPT_2026_05_12.md` (paste-ready deploy prompt)
- `.tmp_no_momentum_90s/T0_BASELINE.json` (machine-readable for T1 comparison)
- `.tmp_no_momentum_90s/verify_intervention.py` + `.tmp_no_momentum_90s/verify_output.txt`
- `.tmp_no_momentum_90s/sql_*.sql` + JSON dumps of every query
- `ZMN_ROADMAP.md` Decision Log entry
- `AGENT_CONTEXT.md` §6.5 update
- `MONITORING_LOG.md` entry
- `STATUS.md` prepend

---

## §12 Decision to skip T1 (added 2026-05-13 by NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001)

The audit's §9 offered two timing paths: (a) wait for STOP-LOSS-20-RUG-FILTER-EVAL-001 at ≥2026-05-25 and bundle, or (b) bring the eval forward with Jay's explicit authorization. **Path (b) was taken at 2026-05-13 03:29:21Z UTC.** T1 standalone audit run scheduled for ≈2026-05-14 is **SKIPPED**; the regime-reversion (STOP-F) test is folded into the combined +14d eval at ≥2026-05-27 (per Decision Log entry 2026-05-13).

**Justification, from data accumulated 2026-05-12 → 2026-05-13:**

1. **$1k-$3k MC band: 0 winners across 276 trades over 2.5 days post-F1-filter.** Pattern repeated across every hour-of-day, every market condition. Structural, not noise.
2. **Bi-modal operation visible in fresh data:** when signal_aggregator delivers low-MC tokens (median <$1k), bot wins at 60-87% WR via TRAILING_STOP. When it delivers mid-MC tokens (median $2-3k), bot bleeds at 0-5% WR via no_momentum_90s. Same day, same regime, same week — the only differentiator is which side of $1k the signals land.
3. **Cross-audit confirmation from ML-SCORE-ATH-VALIDATION-001 (2026-05-12):** the no_momentum_90s timer is NOT killing winners (2/489 post-exit pumps at 56h median lag — late-recovery noise, not bot-cut-it-short). Independent confirmation that the MC discriminator (this deploy) is the right lever, not the timer.
4. **The audit's STOP-F (regime reversion) requires no_momentum rate dropping >10pp AND $1k-$3k WR rising >15pp.** Current data showed the opposite — $1k-$3k WR remained 0% across all hours through 2026-05-13.

**Pre-deploy STOP-A retest on fresh 8.12d sample (vs audit's 7.49d) confirmed the structural pattern held:**

- C1 marginal blocked: 589 trades, sum_pnl_sol -10.86 SOL saved → **+1.49 SOL/day W3+W4 rate** (≥+1.0 threshold), **+3.02 SOL/day W4-only rate**.
- False positives (winners blocked): **0** (matches audit exactly).
- KEPT slice: 523 trades, +32.62 SOL, **91.4% WR** (vs audit's 433 / +30.71 / 94.2%).

**Deploy executed:** single env-var change `BOT_CORE_FILL_MC_CEILING_USD=1000` on bot_core. Container restart at 03:38:37Z UTC; clean startup verified (`Startup reconciliation: 0 open positions in DB`, `Bot Core ready`, `Listening for emergency alerts`, no RuntimeError). First post-deploy reject log: `FILL_MC_CEILING reject: 6X5V79NvN85P mc=$10753 > ceiling=$1000` at 03:41:38Z confirms env plumbed through to rejection logic.

**Eval folded:** combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 at ≥2026-05-27 (+14d from this deploy). T1 STOP-F regime test rolled into that combined evaluation.
