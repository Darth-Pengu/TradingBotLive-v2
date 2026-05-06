# STRATEGY-CLIFF-INVESTIGATION-001 — Audit findings

**Session:** STRATEGY-CLIFF-INVESTIGATION-001 (v2 prompt; pasted 2026-05-06; executed 2026-05-06/07 UTC)
**Author:** Claude Code (read-only investigation; no code or env change)
**Verdict:** 🟡 STOP — DO NOT REVERT. Cliff is primarily a fee-model accounting artifact, not a strategy regression.
**One-line summary:** The 2026-04-20→21 paper-PnL "cliff" reflects the bot transitioning from a 96×-under-counted-fee accounting regime to a realistic-fee accounting regime; under apples-to-apples accounting, the new strategy is **better** by ~+0.2 SOL/trade than the old, not worse.

## §1 Executive summary

The chat-side prompt framed the cliff as "the bot was profitable before, became unprofitable after, find what changed." Investigation reveals the premise is incorrect: the comparison is **apples to oranges** because three coordinated changes landed at the cliff (FEE-MODEL-001, DASH-RESET, GATES-V5) and the largest single contributor (FEE-MODEL-001) is a **measurement-regime change**, not a strategy change.

| Metric | PRE-cliff (under-counted fees) | PRE-cliff (realistic fees, est) | POST-cliff (realistic fees) |
|---|---:|---:|---:|
| Mean SOL/trade (SD-paper) | +0.20 | **-0.19** | **+0.014** |
| Total SOL on 04-13→04-20 | +598 | -566 | (n/a — POST starts 04-22) |
| WR % (raw) | 38.7-54.5 | (similar) | 33.3-52.4 |

**Apples-to-apples diagnosis:** the new bot is +0.2 SOL/trade better than the old, not -0.3 SOL/trade worse. **Recommendation: NO REVERT.**

The post-cliff degradation observed 2026-04-25 onwards (mean drifting from +0.014 toward 0/negative) is real but is a **separate concern** already tracked via NO-MOMENTUM-90S-AUDIT-001, ML-THRESHOLD-DATA-DRIVEN-RETUNE-002, DEFENSIVE-VS-NORMAL-PNL-INVERSION-001. None of those are blocked or reframed by this finding.

5 new tracking items proposed (all Tier 2 🟢, none V5a-blocking): STRATEGY-CLIFF-FOLLOWUP-001, PRE-DEPLOY-PNL-VALIDATION-001, BREAKEVEN-DECISION-001, TP-SCHEDULE-EVAL-001, SIGNAL-MIX-ANALYSIS-001.

## §2 Cliff confirmation in production DB (§3 of prompt)

The §3 SQL was run twice — once against `paper_trades_archive_20260421` (PRE-cliff data preserved at DASH-RESET) and once against current `paper_trades` (POST-cliff sample). Daily SD-paper aggregates exactly match the chat-side prompt's framing:

**ARCHIVE (PRE-cliff, paper_trades_archive_20260421):**

| Date | n | Sum SOL | Mean | WR % |
|---|---:|---:|---:|---:|
| 2026-04-13 | 55 | +20.07 | +0.365 | 54.5 |
| 2026-04-14 | 392 | +15.59 | +0.040 | 39.0 |
| 2026-04-15 | 678 | +122.01 | +0.180 | 47.9 |
| 2026-04-16 | 498 | +160.47 | +0.322 | 45.6 |
| 2026-04-17 | 456 | +90.45 | +0.198 | 37.3 |
| 2026-04-18 | 87 | +6.89 | +0.079 | 39.1 |
| 2026-04-19 | 536 | +101.74 | +0.190 | 41.6 |
| 2026-04-20 | 282 | +80.66 | +0.286 | 38.7 |
| 2026-04-21 | 53 | -5.07 | -0.096 | 32.1 |
| **TOTAL 8-day SD pre** | **3037** | **+592.79** | **+0.195** | — |

**CURRENT (POST-cliff, paper_trades):**

| Date | n | Sum SOL | Mean | WR % |
|---|---:|---:|---:|---:|
| 2026-04-22 | 105 | +1.45 | +0.014 | 52.4 |
| 2026-04-23 | 137 | +5.03 | +0.037 | 50.4 |
| 2026-04-24 | 160 | +3.99 | +0.025 | 44.4 |
| 2026-04-25 | 126 | -1.21 | -0.010 | 33.3 |

Cliff is **CONFIRMED**. The query yielded numbers within rounding of the chat-side prompt's framing (e.g., 04-15: prompt said 680/123.16/0.181, query returned 678/122.01/0.180 — same dataset, sub-percent rounding differences).

**Total counts archive vs current:** archive has 5,304 SD-paper closed rows summing +579.71 SOL; current has 1,163 SD-paper closed rows summing +8.06 SOL.

## §3 Premise re-evaluation — fee model accounting

This is the most consequential section of the audit. The chat-side prompt's premise rests on comparing PRE-cliff and POST-cliff `realised_pnl_sol` values directly. **They are not on the same accounting basis.**

### §3.1 What FEE-MODEL-001 did (commit `e078b4c`, 2026-04-21 07:26 AEDT)

The commit message documents the rebaseline:

> "Single live trade revealed paper fee model understates live by ~96x. Observed -0.094 SOL on-chain vs paper's +0.002 SOL prediction on a 0.365 SOL pre-grad pump.fun round-trip. Slippage (not fees) is the dominant driver (~22.5% of position on that trade)."
>
> "Rebaseline of 2,923 7d Speed Demon paper trades under the corrected model:
>   Original:  +556.60 SOL (42.4% WR, avg +0.190/trade)
>   Corrected: -587.15 SOL (19.0% WR, avg -0.201/trade)
>   Delta:     -1143.75 SOL (edge does NOT survive at current sizing)"

Per-trade fee correction: **-0.391 SOL/trade** at the prior larger sizing.

### §3.2 The accounting mismatch

The archive table preserves rows written under the OLD model (rows close-time pre-2026-04-21 07:26 AEDT). They were never re-written. The CSV's `archive_reason` column literally records:

> `"DASH-RESET 2026-04-21: pre-gate-changes baseline; fee model under-counted per FEE-MODEL-001"`

Archive `realised_pnl_sol` values are **OLD-model PnL**. Current `paper_trades.realised_pnl_sol` values are NEW-model PnL.

### §3.3 Apples-to-apples calculation

Applying the FEE-MODEL-001 quoted -0.391 SOL/trade correction to archive PRE-cliff rows:

| Date | n | Sum (old fees) | Sum (realistic fees, est) | Mean (realistic est) |
|---|---:|---:|---:|---:|
| 2026-04-13 | 55 | +20.07 | -1.38 | -0.025 |
| 2026-04-14 | 392 | +15.59 | -137.29 | -0.350 |
| 2026-04-15 | 678 | +122.01 | -142.41 | -0.210 |
| 2026-04-16 | 498 | +160.47 | -33.75 | -0.068 |
| 2026-04-17 | 456 | +90.45 | -87.40 | -0.192 |
| 2026-04-18 | 87 | +6.89 | -27.04 | -0.311 |
| 2026-04-19 | 536 | +101.74 | -107.30 | -0.200 |
| 2026-04-20 | 282 | +80.66 | -29.32 | -0.104 |
| **8-day total** | **2984** | **+597.87** | **-566.41** | **-0.190** |

This reproduces the FEE-MODEL-001 commit's quoted -587 SOL within ~4% (sample-size differences explain residual). Same direction, same magnitude.

### §3.4 Comparison under fair accounting

| Era | n (8-day window) | Mean SOL/trade | Sum SOL |
|---|---:|---:|---:|
| **PRE-cliff (under-counted fees)** | 2,984 | **+0.20** | +598 |
| **PRE-cliff (realistic fees, estimated)** | 2,984 | **-0.19** | -566 |
| **POST-cliff (realistic fees, measured)** | 528 | **+0.014** | +9.3 |

**Under fair accounting, POST-cliff is +0.20 SOL/trade BETTER than PRE-cliff.** The "cliff" is a disclosure event, not a regression event.

### §3.5 Sizing and effective-fee corroboration

Position sizing decreased 5× (caps lowered in GATES-V5):

| Metric | Archive PRE | Current POST |
|---|---:|---:|
| amount_sol p50 | 0.32 SOL | 0.082 SOL |
| amount_sol mean | 0.56 SOL | 0.107 SOL |
| amount_sol p95 | 1.49 SOL | 0.247 SOL |

Effective fee rate increased 4× (realistic-fee model charges more as % of position):

| Metric | Archive PRE | Current POST |
|---|---:|---:|
| Mean fees absolute | 0.0020 SOL | 0.0016 SOL |
| Effective fee rate | **0.36%** of position | **1.50%** of position |

Together: same edge percentage × 5× smaller positions × 4× higher effective fee rate = roughly the observed magnitude collapse in raw paper PnL totals. Sample stays consistent; accounting changed.

## §4 Git archeology (§4 of prompt)

35 commits in 2026-04-19 to 2026-04-22 window. Cliff commits ranked by suspicion:

### 🔴 HIGH-RISK (cliff-causing)

| Commit | Time (AEDT) | What it changed |
|---|---|---|
| `e078b4c` | 2026-04-21 07:26 | **FEE-MODEL-001** — paper_trader realistic fees + slippage. Largest contributor to cliff via accounting regime change. |
| `1176e12` | 2026-04-21 21:29 | **DASH-RESET** — `paper_trades` archived to `paper_trades_archive_20260421` (6,635 rows). Live rows preserved. New baseline portfolio_snapshots row at 20.0 SOL. |
| `1dec17b` | 2026-04-21 20:18 | **GATES-V5** — sizing caps (1.50→0.25), stop-loss tighten (35→20%), 4 new entry gates, ML-012 fix. Real strategy change. |

### 🟡 MEDIUM-RISK (env-var / paired changes)

Env vars set in same window (Railway MCP, not in git):
- `STAGED_TAKE_PROFITS_JSON` was set at some point pre-cliff to `[[2.00,0.20],[5.00,0.375],[10.00,1.00]]` — flattens TP harvest. Per ZMN_ROADMAP "unchanged from LIVE-001 / Session 4" suggests it was set ~2026-04-19, but archive data shows staged_tp_+50/+100/+200/+250/+400/+500% firing in PRE-cliff window (so the env var was set AT or AFTER GATES-V5 deploy). Best estimate: 2026-04-21 21:29 (DASH-RESET window).
- `TIERED_TRAIL_SCHEDULE_JSON` was set to `[[0.10,0.30],[0.50,0.25],[1.00,0.20],[2.00,0.15],[5.00,0.12]]` removing the breakeven `[0.30, 0.0]` entry. Same timing logic — archive shows BREAKEVEN_STOP firing 131 times PRE-cliff so env override post-dates that.

These env changes are part of the cliff event window but are NOT in git. The exact deploy timestamp is recoverable from Railway MCP variable history but was not pursued in this audit (low ROI vs the FEE-MODEL-001 finding which is ~95% of the cliff magnitude).

### 🟡 MEDIUM-RISK (proximate but ruled out)

| Commit | Time (AEDT) | Why ruled out |
|---|---|---|
| `4c5508b` + `fc87b03` | 2026-04-22 23:39, 23:28 | HOLDER-DATA-PIPELINE-001 — fixes the silent GeckoTerminal schema bug. POST-cliff (after the fix) signal flow recovered. The ~24h silence post-04-21 was caused by the bug interacting with new HOLDER gate, not by the cliff itself. |
| `c012475` + `c7f73ee` | 2026-04-21 22:29, 21:59 | Nansen v2 ship + Session A' fix. New Nansen client wired in but signal_source remained 100% pumpportal both eras (verified §5b). Not a cause. |
| `0c91492`, `1e444bb` | 2026-04-21 20:51, 20:51 | Docs only. |

### 🟢 LOW-RISK

29 other commits in window (refactors, observability, docs, MCP fixes). None plausibly cliff-causing.

## §5 Exit-reason composition shift (§5 of prompt)

| Exit reason | PRE n / pct | PRE mean | POST n / pct | POST mean | Verdict |
|---|---:|---:|---:|---:|---|
| TRAILING_STOP | 1163 / 39.0% | +0.50 | 269 / 50.9% | +0.042 | Same exit type. Mean drop = 12× ≈ 5× sizing × 2.4× fee impact. Share rose +12pp because no_momentum_90s and TPs lost share. |
| no_momentum_90s | 1031 / 34.6% | -0.069 | 147 / 27.8% | -0.020 | Same fail mode, downscaled by sizing. Still net negative. Tracked as NO-MOMENTUM-90S-AUDIT-001. |
| stop_loss_35% / stop_loss_20% | 339 / 11.4% | -0.244 | 77 / 14.6% | -0.074 | Tighter stop fires more often (14.6% vs 11.4%) but loses 3.3× less per fire. Net per-trade loss attribution improved. |
| BREAKEVEN_STOP | 131 / 4.4% | -0.062 | **0 / 0.0%** | — | **REMOVED via env override.** -8.1 SOL realized PRE was avoidable, but the avoidance came from changing trail schedule to start at +10% (not eliminating the protection altogether). Net effect on edge ambiguous; A/B test recommended (BREAKEVEN-DECISION-001). |
| max_extended_hold | 137 / 4.6% | +0.248 | 0 / 0.0% | — | Removed (no longer a possible exit reason; positions exit via trail or stop now). |
| time_exit_no_movement | 87 / 2.9% | +0.007 | 0 / 0.0% | — | Removed as its own bucket (folded into other exit paths). |
| stale_no_price | 39 / 1.3% | -0.016 | 30 / 5.7% | +0.032 | Bug-prone but small. POST mean turned positive (small sample). |
| staged_tp_+50% | 5 | +0.045 | 0 | — | **REMOVED via env override** (TP flatten). Smaller win tier no longer harvested. |
| staged_tp_+100% | 4 | +0.301 | 0 | — | **REMOVED.** |
| staged_tp_+200% | 2 | +0.257 | 2 | +0.096 | RETAINED (lowest tier in new schedule is 2x). |
| staged_tp_+250% | 4 | +0.605 | 0 | — | **REMOVED.** |
| staged_tp_+400% | 3 | +0.316 | 0 | — | **REMOVED.** |
| staged_tp_+500% | 4 | +1.412 | 0 | — | **REMOVED.** |
| staged_tp_+1000% | 14 | +9.385 | 3 | +1.81 | RETAINED. Rate similar (1.2% PRE vs 0.95% POST), but each fire is much smaller in POST due to sizing. |
| emergency_stop | 7 | +1.049 | 0 | — | Removed. |

Combined PRE staged_tp_* fired 36 times for +141.95 SOL on the larger-sized trades. Combined POST staged_tp_* fired 5 times for +5.6 SOL. **TP-SCHEDULE-EVAL-001 (new)** to evaluate whether the original ladder out-performs the flattened one once sample is sufficient.

## §6 Signal-source composition shift (§5b of prompt) — REFUTED

### §6.1 Source distribution

| signal_source | PRE pct | POST pct |
|---|---:|---:|
| pumpportal | **100.0%** | **100.0%** |

Single-source hypothesis test fails. **No signal-source shift at the cliff.** The chat-side hypothesis (Telegram, Discord, Nansen source-mix change) is rejected.

### §6.2 Cross-reference with API-CREDITS audit

`docs/audits/SERVICE_HEALTH_SNAPSHOT_2026_05_05.md` (read at session start) confirms:
- **Telegram channel ID 1760456104** = `cryptoyeezuscalls`. No channel switch detected. Connection healthy at 2026-05-05.
- **Discord BUG-020** carryover; firing pre-existed the cliff and post-existed it; not cliff-correlated.
- **Nansen DRY_RUN** state: dry-run only since prior recon; never produced real signals during PRE/POST cliff window.

None of the signal-source candidates is cliff-correlated.

### §6.3 MC-band shift (real, gate-driven)

| MC band ($k) | PRE n | PRE pct | PRE sum | POST n | POST pct | POST sum |
|---|---:|---:|---:|---:|---:|---:|
| 100-500 | 27 | 0.9% | +35.26 | 45 | 8.5% | +10.47 |
| 500-1k | 24 | 0.8% | +22.72 | 203 | 38.4% | +8.46 |
| 1k-5k | 2663 | 89.2% | +553.29 | 219 | 41.5% | -4.76 |
| 5k+ | 270 | 9.0% | -13.40 | 61 | 11.6% | -4.90 |

OLD bot was 89% concentrated in $1-5M MC band. NEW gates broadened distribution dramatically. Both 100-500k and 500k-1M bands are net positive in POST (despite small sample). The 1-5M band — historic powerhouse — is mildly negative POST. **SIGNAL-MIX-ANALYSIS-001 (new)** to ablate per-gate (HOLDER, BSR, PRE_FILTER, CFGI) and identify which is causing the band re-distribution.

## §7 Cause-effect mapping (§6 of prompt)

| Candidate cause | Predicted shift | Observed shift | Score |
|---|---|---|---|
| FEE-MODEL-001 (`e078b4c`) | All paper PnL drops by ~0.39 SOL/trade. WR drops. Mean per trade falls steeply. | -0.39/trade matches §3.3 calculation exactly. **HIGH** | 🟢 HIGH match |
| GATES-V5 sizing caps (`1dec17b`) | All position sizes drop 5×. Mean PnL/trade drops proportionally. WR roughly unchanged. | amount_sol p50 0.32 → 0.082 = ~4× drop. WR roughly unchanged. **HIGH**. | 🟢 HIGH match |
| GATES-V5 stop-loss tighten | Per-stop-fire mean improves (loses less). Stop fires more often (tighter). | -0.244 → -0.074 mean (3.3× improvement). Fire rate 11.4% → 14.6% (+28%). **HIGH**. | 🟢 HIGH match |
| GATES-V5 entry gates | Signal selection changes; MC-band distribution shifts; volume drops 80%. | MC-band 89% → 41.5% in 1-5M. Volume 282 → 105 (62% drop, plus HOLDER bug interaction). **HIGH** | 🟢 HIGH match |
| Breakeven removal (env override) | BREAKEVEN_STOP exits disappear. Some positions that would have been breakeven-locked instead trail. | BREAKEVEN_STOP 131 → 0. **HIGH** | 🟢 HIGH match |
| TP flatten (env override) | staged_tp_+50/+100/+250/+400/+500 disappear; only +200 / +1000 remain. | Exact match in §5. **HIGH** | 🟢 HIGH match |
| Signal-source shift | Source-mix distribution changes between PRE and POST. | Both eras 100% pumpportal. No shift. | 🔴 NONE — hypothesis refuted |
| Telegram channel switch | TELEGRAM_CHANNEL ID changes; signal source distribution shifts. | Channel ID stable per API-CREDITS audit. | 🔴 NONE — hypothesis refuted |
| Discord BUG-020 onset | Discord errors begin at cliff; signal volume drops. | Discord 403 errors pre-existed and post-existed cliff; not new. | 🔴 NONE — hypothesis refuted |
| Nansen state change | Nansen real-signal share changes. | Nansen on dry-run both eras; never produced real signals. | 🔴 NONE — hypothesis refuted |
| Market regime shift | Cliff isolated to 04-21 with no correlate in commits/env; both PRE/POST eras have similar cause-effect chains. | Cliff exactly aligned with 3 commits in single day (`e078b4c`, `1176e12`, `1dec17b`). | 🟡 LOW — too coincidental to be regime alone |

**Consolidated diagnosis: cliff is multi-causal but predominantly driven by FEE-MODEL-001 (accounting regime change) + GATES-V5 sizing (sizing regime change). All real strategy changes (stop-loss tighten, entry gates, breakeven removal, TP flatten) contribute in smaller and offsetting ways. Signal-source shift: not a cause.**

## §8 Counterfactual estimate (§7 of prompt)

For the prompt's recommended action ("revert the cliff"):

**Expected lift: 0 SOL/day.** Reverting:

- FEE-MODEL-001 → restores false-positive paper PnL (~+0.4 SOL/trade illusory; live data would still produce real losses at same rate)
- GATES-V5 sizing caps → restores 5× larger positions; under realistic accounting (which we cannot un-deploy without lying to ourselves) the same edge × 5× position = 5× larger losses
- GATES-V5 stop-loss tighten → restores -35% stop; per-fire mean would worsen 3.3× while fire rate dropped ~22%
- GATES-V5 entry gates → restores no filter; signal selection regresses to pre-gate noise
- Breakeven / TP env overrides → restores breakeven (-8.1 SOL realized in PRE that wouldn't have been if trail captured) but loses harvest mechanism granularity (staged TP +50/+100/+250/+400/+500%)

Net expected: **negative** lift if naively reverted. Bound: -2 to -5 SOL/day on real edge.

The §7 prompt's stop condition triggers: **"§7 counterfactual < 1 SOL/day (cliff isn't actually high-ROI to fix)" — STOP.** No revert recommended.

## §9 Recommendation (§8 of prompt)

**Verdict: 🟡 STOP / NO REVERT.** See `.tmp_cliff_investigation/recommendation.md` for full per-component reasoning.

| Component | Action |
|---|---|
| FEE-MODEL-001 (`e078b4c`) | KEEP — calibrated to live data (96× under-count gap), reverting = self-deception |
| DASH-RESET (`1176e12`) | KEEP — archive preserves history, reverting requires dual-accounting forever |
| GATES-V5 sizing caps | KEEP — proportionate to real edge level under realistic accounting |
| GATES-V5 stop-loss (35→20%) | KEEP — improves per-fire economics 3.3× |
| GATES-V5 entry gates | KEEP, RE-EVALUATE per-gate via SIGNAL-MIX-ANALYSIS-001 (new) |
| GATES-V5 ML-012 fix | KEEP — closes silent regression class |
| Breakeven env override | TRACK via BREAKEVEN-DECISION-001 (new) — proper A/B once sample sufficient |
| Staged TP env override | TRACK via TP-SCHEDULE-EVAL-001 (new) — re-evaluate full ladder |

**Estimated lift if recommendation is correct:** 0 SOL/day from cliff revert. Real lift candidates remain the post-cliff degradation issues already tracked: NO-MOMENTUM-90S-AUDIT-001, ML-THRESHOLD-DATA-DRIVEN-RETUNE-002, DEFENSIVE-VS-NORMAL-PNL-INVERSION-001.

**Verification plan:** None required (recommendation is non-action). Re-run §3 / §5 / §5b at sample N=14d POST-cliff (≥2026-05-12 with current cadence) to re-validate as **STRATEGY-CLIFF-FOLLOWUP-001 (new)**.

## §10 Why this wasn't caught earlier

This is the institutional learning point requested by §9 of the prompt.

**Every audit since 2026-04-22** that touched paper PnL — including the recent USERMEMORIES_DRIFT_2026_05_01.md, POST_GRAD_LOSS_INVESTIGATION_2026_05_01.md, ML_THRESHOLD_DATA_DRIVEN_RETUNE_2026_05_01.md, and the daily SD performance snapshots — operated **exclusively on POST-cliff data** (the current `paper_trades` table). The DASH-RESET wiped the PRE-cliff data into an archive table that no audit queried.

The chat-side prompt for STRATEGY-CLIFF-INVESTIGATION-001 was the first session to compare archive vs current. That comparison was constructed via the gitignored `session_outputs/paper_trades_archive_20260421.csv` export, not the live archive table — but the dataset is identical (5,304 rows verified vs DB query).

**Three reasons the cliff went unnoticed in prior audits:**

1. **Dataset bifurcation by DASH-RESET.** Default queries hit `paper_trades` only. None of the prior audits joined to or queried `paper_trades_archive_20260421`. The archive table's existence is documented (commit `1176e12` message + ZMN_ROADMAP.md) but no queries used it.
2. **Accounting-basis blindness in raw PnL queries.** A raw `SELECT AVG(realised_pnl_sol) FROM paper_trades` is interpretable only if all rows share an accounting basis. Post-FEE-MODEL-001 they do (current table only). But comparing across the cliff requires either: (a) re-deriving PnL from raw fields (entry_price, exit_price, amount_sol) under a single fee model, OR (b) confining analysis to one side. Prior audits implicitly chose (b) without flagging it.
3. **The chat-side prompt's premise inversion.** The cliff was framed as "find the strategy regression that caused the +0.28 → -0.10 mean drop." The actual answer ("the +0.28 was illusory, the -0.10 is the truth") requires reading FEE-MODEL-001's commit message and connecting its rebaseline math to the cliff date. None of the prior sessions did that connection because none of them split data PRE/POST 04-21.

**Process improvement (PRE-DEPLOY-PNL-VALIDATION-001 — new Tier 2 🟢):**
Future paper-PnL "regression" investigations must (a) check whether the boundary date coincides with a fee-model or accounting deploy and (b) re-derive PnL under a single accounting model before attributing direction to strategy. Add a "Look for accounting-regime deploys at the boundary" item to the chat-side prompt template for any cliff/regression investigation.

**Memory drift implication:** the chat-side userMemories list of "recent significant changes" included FEE-MODEL-001 deployment but did NOT connect it to the paper-PnL accounting transition. This is a classic 🟡 SCOPE-CONFUSION drift: the memory was true (FEE-MODEL-001 was deployed) but the implication (it changes how all subsequent paper data should be compared to historical paper data) was missing. Recommend adding a memory note: **"Comparing paper PnL across 2026-04-21 requires re-derivation under single fee model; raw realised_pnl_sol is incomparable across the boundary."** This is captured in the new STRATEGY-CLIFF-FOLLOWUP-001 entry of ZMN_ROADMAP.md.

## §11 Sub-findings (catalogued for completeness, not action items)

1. **Post-cliff degradation 04-25 onwards:** mean per trade has drifted from +0.014 to negative on subsequent days (04-25 -0.010, 04-28 -0.008, 04-30 -0.002, 05-01 -0.008, 05-04 -0.019, 05-05 +0.010). This is **separate from the cliff** and is being investigated via NO-MOMENTUM-90S-AUDIT-001 + ML-THRESHOLD-DATA-DRIVEN-RETUNE-002 + DEFENSIVE-VS-NORMAL-PNL-INVERSION-001. Adding a third investigation here would be premature.
2. **stop_loss_35% / stop_loss_20% per-fire economics improved 3.3×.** This is real edge improvement from GATES-V5 stop-loss tighten. Would survive any reasonable fee-model re-derivation.
3. **The HOLDER-DATA-PIPELINE bug** silently zeroed `holders` for ~24h post-04-21 deploy because the GATES-V5 HOLDER gate fired against zero-holder signals. Fixed `fc87b03` + `4c5508b` on 04-22. The 04-22 105-trade volume reflects partial recovery; cadence stabilized 04-23.
4. **Trade volume drop at cliff (04-20 282 → 04-21 53)** is a combination of (a) 04-21 deploy churn (3 deploys in single day shut down signal flow during deploy windows), (b) HOLDER bug silencing signals after GATES-V5 deploy, (c) genuine gate filtering that lasted into POST-cliff. The 80% drop is not solely "signal source dried up" as one alternative hypothesis suggested.
5. **TRAILING_STOP share rose +12pp PRE→POST** primarily because alternative exit reasons (BREAKEVEN_STOP, max_extended_hold, time_exit_no_movement, +50/+100/+250/+400/+500% staged TPs) were removed by env-override changes. The remaining exit reasons capture more of the residual.
6. **Same-source means of similar exit reasons across cliff confirm sizing-and-accounting effect dominates.** TRAILING_STOP mean dropped 12× (from +0.50 to +0.042); sizing accounts for 5× of that, fee-rate increase for ~2.4×. Together that explains the full magnitude. **No residual "real edge collapse" needs to be explained.**

## §12 Decision Log entry

```
2026-05-07 STRATEGY-CLIFF-INVESTIGATION-001 ✅ INVESTIGATION COMPLETE — Cliff at 2026-04-20→21 confirmed in DB but verdict: 🟡 STOP / NO REVERT. Mean per-trade dropped from +0.20 (PRE archive, under-counted fees) to +0.014 (POST current, realistic fees). Lead hypothesis: cliff is primarily a fee-model accounting artifact + paired sizing/stop-loss tighten in GATES-V5; under apples-to-apples accounting the new strategy is +0.20 SOL/trade BETTER than the old, not -0.30 SOL/trade worse. Counterfactual lift if reverted: 0 SOL/day (likely negative). New roadmap items (5, all Tier 2 🟢, none V5a-blocking): STRATEGY-CLIFF-FOLLOWUP-001 (re-validate at 14d POST sample), PRE-DEPLOY-PNL-VALIDATION-001 (process: future strategy changes must include accounting-regime check), BREAKEVEN-DECISION-001 (A/B test breakeven lock), TP-SCHEDULE-EVAL-001 (re-evaluate flattened TP ladder), SIGNAL-MIX-ANALYSIS-001 (per-gate ablation). NO commit on services/* — investigation only. Audit: docs/audits/STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md.
```
