# ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 — Audit (2026-05-01)

> Session 4 of 6 in chained-prompt sequence. **STOP triggered per §8** — see §5 below.
> Threshold sweep analysis completed for informational purposes; **no env-var change
> made this session.** Also includes a correction to Session 3's POST-GRAD finding.

## §1 Pre-fix state

**Threshold drift across services (per ENV_AUDIT_2026_04_29 + Railway MCP env list 2026-05-01):**
- `signal_aggregator.ML_THRESHOLD_SPEED_DEMON = 65` (env)
- `bot_core.ML_THRESHOLD_SPEED_DEMON = 40` (env)
- `web.ML_THRESHOLD_SPEED_DEMON = 45` (env, display only)

**BUT: effective threshold on paper rows is 30**, not any of the above. Per `services/signal_aggregator.py:158-160`:
```python
if AGGRESSIVE_PAPER and TEST_MODE:
    ML_THRESHOLDS = {"speed_demon": 30, "analyst": 30, "whale_tracker": 20}
elif AGGRESSIVE_PAPER and not TEST_MODE:
    # Use env ML_THRESHOLD_* values (no override)
```

Both `AGGRESSIVE_PAPER_TRADING=true` and `TEST_MODE=true` are set on signal_aggregator, so the override is active. The env value of 65 is a no-op for current paper traffic.

**bot_core.py has NO ML threshold filter.** `grep "ml_score|ML_THRESHOLD"` returns 0 matches in bot_core. The 3 references to `AGGRESSIVE_PAPER_TRADING` in bot_core (lines 639, 1185, 1490) are for CFGI gating and consecutive-loss handling, not ML threshold gating. No fallback gate exists at the bot_core layer.

## §2 Threshold sweep results (last run 2026-05-01 ~12:35 UTC, SD-paper)

### 14d FULL-SAMPLE sweep (n=994 SD-paper trades)

| threshold | n_admitted | sum_admitted (SOL) | mean (SOL) | WR % | n_rejected | sum_rejected |
|---:|---:|---:|---:|---:|---:|---:|
| 40 | 838 | +7.4740 | +0.0089 | 34.0 | 156 | +1.6288 |
| 45 | 655 | +7.7524 | +0.0118 | 34.7 | 339 | +1.3504 |
| 50 | 546 | +8.1987 | +0.0150 | 35.9 | 448 | +0.9041 |
| **55** | **448** | **+8.7071** | **+0.0194** | **37.5** | 546 | +0.3958 |
| 60 | 362 | +5.2761 | +0.0146 | 39.0 | 632 | +3.8268 |
| 65 | 276 | +4.9968 | +0.0181 | 39.1 | 718 | +4.1060 |
| 70 | 197 | +1.6979 | +0.0086 | 39.6 | 797 | +7.4050 |

### 7d FULL-SAMPLE sweep (n=684 SD-paper trades)

| threshold | n_admitted | sum_admitted (SOL) | mean (SOL) | WR % | n_rejected | sum_rejected |
|---:|---:|---:|---:|---:|---:|---:|
| 40 | 572 | -1.4794 | -0.0026 | 26.2 | 112 | +0.4861 |
| 45 | 446 | -0.1288 | -0.0003 | 26.7 | 238 | -0.8645 |
| 50 | 370 | +0.4185 | +0.0011 | 28.1 | 314 | -1.4118 |
| **55** | **293** | **+1.4831** | **+0.0051** | **30.4** | 391 | -2.4764 |
| 60 | 238 | +0.5842 | +0.0025 | 31.5 | 446 | -1.5775 |
| 65 | 183 | +1.0890 | +0.0060 | 31.7 | 501 | -2.0822 |
| 70 | 132 | +1.2846 | +0.0097 | 33.3 | 552 | -2.2778 |

**Both windows agree directionally: threshold=55 is the optimum** for `sum_admitted` (the chat-side prompt's correct decision criterion — total weekly P&L given throughput, not mean P&L per trade). At threshold=55: 14d +8.71 SOL on 448 trades, 7d +1.48 SOL on 293 trades. §3 hard rule (n_admitted >= 50 in 14d sample) ✓.

## §3 Cross-check against POST-GRAD investigation (Session 3)

**Pre-grad-only filter (`exit_reason NOT LIKE 'graduation_%'`) returns IDENTICAL numbers to full sweep on SD-paper.** Personality breakdown:

```
personality='analyst' exit_reason='graduation_stop_loss' count=145 sum_sol=-12.8862
personality='analyst' exit_reason='graduation_time_exit' count=79  sum_sol=-2.1593
personality='analyst' exit_reason='graduation_tp_30pct'  count=56  sum_sol=+0.4479
```

**ALL 280 graduation_* exits in 14d are from `analyst` personality, NOT speed_demon.** SD-paper has ZERO graduation_* exits. This is a MAJOR correction to the Session 3 H2 finding interpretation:

- Session 3 H2 framed the post-grad bleed as a structural issue requiring `POST-GRAD-ENTRY-GATE-001` to gate SD signals.
- Reality: SD already doesn't enter post-grad tokens (likely due to `bonding_curve_progress >= 0.95` filter elsewhere or alpha-only signal source).
- The 280 post-grad-ENTRY trades are all from `analyst`, which has been disabled since 2026-04-28 13:02 UTC (via ANALYST-DISABLE-002). No new analyst trades in last 3+ days.
- **Bleed has ALREADY STOPPED.** -14.60 SOL/14d figure is HISTORICAL (analyst's last week of activity), will not continue forward unless analyst is re-enabled.

**Implication for `POST-GRAD-ENTRY-GATE-001`:**
- Current ROI: **~0 SOL/week** (bleed already stopped via ANALYST_DISABLED env)
- Insurance value: meaningful (would prevent recurrence if analyst is ever re-enabled, or if the SD signal source changes)
- Should be re-scoped to apply to ALL personalities, not just SD; OR explicitly limited to analyst as a code-level safeguard layered atop the env-var disable

## §4 Decision

**Per §8, do NOT change the env var this session.** The threshold sweep is informative but not actionable in current state:

```
Chosen threshold: 55  (14d optimum AND 7d optimum agree)
14d sum_admitted at 55: +8.71 SOL on 448 trades
7d sum_admitted at 55:  +1.48 SOL on 293 trades
Mean per trade: +0.019 (14d) / +0.005 (7d)
WR: 37.5% (14d) / 30.4% (7d)
Throughput vs current 30 effective: 448/838 = 53% reduction in trade volume
Pre-grad-only optimal: 55 (identical — SD has 0 post-grad trades)
Justification: 14d sum_admitted maximizes at 55 (+8.71); 7d sum_admitted also maximizes at 55 (+1.48). Direction confirmed.
Risks (deployment): (a) AGGRESSIVE_PAPER+TEST_MODE override sets effective paper threshold to 30 — env change to 55 has ZERO effect on paper sample. (b) bot_core has no second ML threshold gate, so even if SA env is changed, paper rows pass through. (c) Sample selection bias — current admitted trades all had ml_score >= 30; can't directly counterfactual at threshold=55 since the trade flow would have differed.
Risks (decision): the trend is fragile — 7d optimum is +1.48 SOL with high variance; one bad week could revert.
Rollback trigger: 48h post-deploy sum_pnl_post < -0.5 SOL OR n_admitted < 30.
```

## §5 STOP per §8

**Two §8 STOP conditions tripped:**

1. **AGGRESSIVE_PAPER_TRADING bypass cannot be reconciled.** `signal_aggregator.py:158` overrides ML threshold to 30 when AGGRESSIVE_PAPER+TEST_MODE both true. The env value (currently 65) is a no-op for the paper sample.
2. **bot_core threshold filtering code cannot be located.** `grep ml_score|ML_THRESHOLD` returns 0 matches in `services/bot_core.py`. There is NO secondary gate at the bot_core layer to make env-var changes take effect on paper data.

**Outcome:** No env-var change. Threshold sweep documented for future use. STOP_REASON.md captures the gap.

## §6 Recommended path forward

(See `.tmp_ml_retune/STOP_REASON.md` Options A-D for detail. Summary:)

- **Option A (preferred): Add bot_core ML threshold gate.** Single code change in `services/bot_core.py` — read `ML_THRESHOLD_SPEED_DEMON` env, reject scored signals with `ml_score < threshold` in `_process_scored_signal`. Cost S. Independent of AGGRESSIVE_PAPER. Tracked as `BOT-CORE-ML-GATE-001` (NEW Tier 1 🟡 in roadmap).

- **Option B (broader-impact): Disable AGGRESSIVE_PAPER_TRADING.** Env change only. Activates env value (currently 65). Risk: may reduce ML-training sample volume; needs separate evaluation. Tracked as `AGGRESSIVE-PAPER-DISABLE-001` (NEW Tier 2 🟢 in roadmap, evaluation-required).

- **Option C: Wait for V5a flip.** When TEST_MODE=false, AGGRESSIVE_PAPER override doesn't apply and env values take effect. Pre-position now by setting env to 55 (zero-effect paper, activates on flip).

## §7 48h verification window — N/A this session

No env change made. Verification window not applicable.

## §8 Rollback procedure — N/A this session

No deploy. Nothing to rollback.

## §9 Decision Log entry (mirrored to ZMN_ROADMAP.md)

```
2026-05-01 ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 ⏸ STOP per §8 — Env-var change to
ML_THRESHOLD_SPEED_DEMON has ZERO effect on paper sample due to
AGGRESSIVE_PAPER+TEST_MODE override (signal_aggregator.py:158 sets effective
SD threshold = 30 regardless of env value). bot_core has no second ML gate. Sweep
analysis complete: 14d AND 7d both show optimum threshold = 55 (sum_admitted +8.71
on 448 / +1.48 on 293; WR 37.5%/30.4%). New roadmap items: BOT-CORE-ML-GATE-001
(Tier 1 🟡 — implement second gate at bot_core), AGGRESSIVE-PAPER-DISABLE-001
(Tier 2 🟢 — evaluate disabling override). Major correction to Session 3:
280 graduation_* exits all from `analyst` (disabled 2026-04-28); SD has 0
post-grad entries; POST-GRAD-ENTRY-GATE-001 actual current ROI is ~0 (insurance
value only — bleed already stopped via ANALYST_DISABLED).
```
