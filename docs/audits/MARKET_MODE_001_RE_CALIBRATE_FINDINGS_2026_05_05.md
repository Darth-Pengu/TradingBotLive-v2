# MARKET-MODE-001-RE-CALIBRATE — Findings (Path C / STOP, no code change)

> **Verdict: STOP per session-prompt §4 Path C.** Investigation revealed
> the prompt's premise (HIBERNATE-cycling, grad_rate-bound) is incorrect
> for the actual data. Patching as written would have actively worsened
> per-trade PnL. Findings filed; deferring code change pending Jay
> re-scoping. NO market_health.py edit. NO deploy. NO env change.

> **Predecessors:** BOT-CORE-ML-GATE-001 (commit `ea0da2f` + docs `77ac459`,
> verdict 🟢 DEPLOYED) ✅ and TIMEZONE-AUDIT-001 (commit `e58b435`,
> market_health.py confirmed 🟢 SAFE) ✅. Both verified per §0.

---

## §1 Executive verdict

**🟡 STOP — emitted finding doc per §4 Path C; no patch.**

Three reasons, in priority order:

1. **The binding constraint is `dex_vol`, not `grad_rate`.** The session
   prompt's §4 Path C explicitly names this exact case as a STOP trigger:
   > "If §3 reveals something unexpected (e.g., **dex_vol is the binding
   > constraint**, or the metric definitions don't match what the code
   > reads), STOP and emit a finding doc. Do not patch into uncertainty."
   The investigation confirms dex_vol is dominant (structural reasoning +
   live snapshot + diurnal pattern). Path A's grad_rate threshold loosen
   (30→15) is a no-op for our data.

2. **NORMAL mode has WORSE per-trade PnL than DEFENSIVE** — the prompt's
   premise was "expand NORMAL to fix throughput", but the data shows:
   - NORMAL: 121 trades, sum **-1.09 SOL**, WR 24.8%
   - DEFENSIVE: 45 trades, sum **+0.25 SOL**, WR 28.9%
   Patching to expand NORMAL would have admitted MORE trades into a mode
   that bleeds more per trade. The session would have done damage.

3. **Pumpfun_vol is structurally degenerate** — `pumpfun_vol_estimate =
   dex_vol * 0.15` (placeholder math at `services/market_health.py:390`).
   This means the AND gate is effectively `(dex_vol AND grad_rate)` —
   pumpfun never independently binds. Recalibrating pumpfun thresholds
   would be inert. Filed as **PUMPFUN-VOL-PLACEHOLDER-001**.

The cleanest path forward is a re-scoped session — see §6 below.

---

## §2 Predecessor verification (both PASS)

| Item | Status |
|---|---|
| BOT-CORE-ML-GATE-001 audit doc | `docs/audits/BOT_CORE_ML_GATE_001_2026_05_05.md` ✅ |
| BOT-CORE-ML-GATE-001 verdict | 🟢 DEPLOYED ✅ |
| `ML_THRESHOLD_BOT_CORE_SD` env | 40 ✅ (active 2026-05-05T14:16:48Z) |
| BOT-CORE-ML-GATE post-deploy SQL | 0 below_40 admissions ✅ |
| TIMEZONE-AUDIT-001 audit doc | `docs/audits/TIMEZONE_AUDIT_2026_05_05.md` ✅ |
| `services/market_health.py` TZ status | 🟢 SAFE (pytz Australia/Sydney throughout) ✅ |

Predecessors clear; the STOP is on substantive grounds, not a verification failure.

---

## §3 Investigation findings

### §3.1 Throughput quantification (§3 Step 1)

| Metric | Value |
|---|---:|
| Total hours (post-Session-2 window 2026-05-01 13:00 → 2026-05-06 ~13:00 UTC) | 120 |
| Zero-trade hours | 55 |
| Pct zero-trade hours | **45.8%** |
| Avg trades per hour | 1.39 |

45.8% > 20% threshold → recalibration is technically warranted, BUT see §3.3 for why a naive recalibration would be harmful.

### §3.2 Mode distribution (§3 Step 2)

From `portfolio_snapshots.market_mode` (n=1,436 5-min snapshots over the window):

| Mode | n | % |
|---|---:|---:|
| NORMAL | 743 | 51.7% |
| DEFENSIVE | 672 | 46.8% |
| HIBERNATE | 18 | 1.3% |
| AGGRESSIVE | 3 | 0.2% |
| FRENZY | 0 | 0.0% |

**The HIBERNATE-cycling framing in the session prompt is incorrect for this data.** HIBERNATE is only 1.3% of snapshots / 1.7% of dominant-mode hours. The throughput problem is **DEFENSIVE-vs-NORMAL**, not HIBERNATE.

### §3.3 PnL by mode — the surprise

From `paper_trades` over the same window:

| Mode | n trades | Sum PnL | Win Rate | Avg PnL/trade |
|---|---:|---:|---:|---:|
| NORMAL | 121 | **-1.09 SOL** | 24.8% | -0.0090 |
| DEFENSIVE | 45 | **+0.25 SOL** | 28.9% | +0.0056 |
| AGGRESSIVE | 1 | (small) | n/a | n/a |

**DEFENSIVE has both higher win rate AND positive sum PnL, while NORMAL bleeds.** This is the opposite of what the prompt assumed. Expanding NORMAL's mode share — which is the design intent of "loosen NORMAL threshold" — would have been net-negative for PnL.

Hypothesis (untested): the SD personality's sizing multipliers under DEFENSIVE may already filter out the lower-quality entries that NORMAL passes through. Or the gate-active sample under BOT-CORE-ML-GATE-001 may show different PnL by mode (only 1 trade post-gate so far). Both are plausible — neither is yet supported by data. **Investigation deferred — out of scope for this session.**

### §3.4 Binding constraint (§3 Step 3) — dex_vol, not grad_rate

Live snapshot:
- `dex_volume_24h` = $1.51B (clears NORMAL@$1B, fails AGGRESSIVE@$2B)
- `migration_count_1h` = 215/hr (clears NORMAL@30, AGGRESSIVE@100, fails FRENZY@200 by margin)
- `pumpfun_vol_estimate` = $226M (clears NORMAL@$100M, AGGRESSIVE@$200M)

Structural finding: pumpfun = 0.15 × dex_vol means pumpfun NEVER independently binds the gate (verified algebraically — see `.tmp_market_mode_recal/binding_constraint_findings.md` §1). Effective gate is `(dex_vol AND grad_rate)`.

Inferential finding: grad_rate at 215 is ~7× the NORMAL threshold of 30. Off-peak Solana grad_rate rarely drops below 60-100/hr. dex_vol on DefiLlama fluctuates between ~$800M (off-peak) and ~$2.5B (peak), with the $1B NORMAL threshold sitting right in the off-peak band. **Therefore: dex_vol is the dominant binding metric.** When mode drops to DEFENSIVE, it is overwhelmingly because dex_vol < $1B, not because grad_rate < 30/hr.

This finding triggers the prompt's explicit Path C STOP condition.

### §3.5 Why pumpfun is degenerate (PUMPFUN-VOL-PLACEHOLDER-001)

`services/market_health.py:390`:
```python
pumpfun_vol_estimate = dex_vol * 0.15
```

This is a placeholder, not an independent measurement. The note in the codebase says it's pending PUMPPORTAL-STATS-API-001 (out of scope per the prompt §12). Until pumpfun_vol becomes an independent metric, the AND gate is effectively a 2-metric gate `(dex_vol AND grad_rate)` and no recalibration of pumpfun thresholds will change behavior. Wiring real pumpfun data is a prerequisite for any future "Path B" (majority vote) approach.

---

## §4 What Path A would have done (and why we're glad we didn't)

The session prompt §4 Path A recommended:
1. Lower NORMAL grad_rate 30 → 15
2. Lower DEFENSIVE grad_rate 10 → 5
3. Add 3-cycle hysteresis on mode downgrades

Effect on our data:
- (1) and (2) are **no-ops** — grad_rate at 215 already clears the OLD threshold of 30 by 7×. Lowering to 15 changes nothing.
- (3) hysteresis IS universally beneficial, but solo it would only delay DEFENSIVE-bound transitions by 15 minutes (3 cycles × 5 min). It wouldn't address the 46.8% DEFENSIVE share — that's a structural threshold issue (dex_vol $1B), not a brittleness issue.

The subagent's "hybrid Path A" adaptation (additionally lower NORMAL dex_vol $1B → $750M) WOULD have moved the needle — but in the wrong direction. With NORMAL bleeding -1.09 SOL on 121 trades vs DEFENSIVE +0.25 SOL on 45, expanding NORMAL share by ~46% (the off-peak DEFENSIVE hours that would now qualify as NORMAL) is a **PnL-negative** lever in the current data regime.

The prompt's premise — "more trades is better" — held when the previous measurement (Bitfoot 2025 era) was the reference. In the post-Session-2 regime with the new gates and personality config, NORMAL is now the bleed mode. The prompt's recipe is **backwards** for this data.

---

## §5 New roadmap items proposed (Tier 1)

| Item | Tier | Description |
|---|---|---|
| **DEFENSIVE-VS-NORMAL-PNL-INVERSION-001** | 🟡 Tier 1 | NORMAL has WORSE per-trade PnL than DEFENSIVE in post-Session-2 sample. Investigate. Hypotheses: (a) SD personality's NORMAL-mode sizing multipliers admit lower-quality entries; (b) DEFENSIVE-mode entries are already filtered by some other path; (c) BOT-CORE-ML-GATE active-sample will change the picture (need 7d post-gate data). Required reading before any market-mode threshold change. |
| **PUMPFUN-VOL-PLACEHOLDER-001** | 🟢 Tier 2 | `pumpfun_vol_estimate = dex_vol * 0.15` at `market_health.py:390` is co-linear with dex_vol → pumpfun never independently binds the AND gate. Wiring real PumpPortal stats API call is a prerequisite for any Path B (majority-vote) refinement. |
| **MARKET-MODE-001-RE-CALIBRATE-V2** | 🟡 Tier 1 | Re-scope the recalibration session with the correct binding metric (dex_vol) and the PnL-inversion finding. See §6 below for proposed structure. Should NOT run until DEFENSIVE-VS-NORMAL-PNL-INVERSION-001 is at least diagnosed (even if not fixed). |

---

## §6 Recommended re-prompt structure (MARKET-MODE-001-RE-CALIBRATE-V2)

For the next chat-side session author, here is the corrected framing:

### Premise (corrected)

The bot's HIBERNATE-cycling problem is largely a non-problem (1.7% of hours). The actual throughput issue is DEFENSIVE-cycling (46.8% of hours, 32 zero-trade hours of those 55 DEFENSIVE-no-trade combinations). But expanding NORMAL share is **PnL-negative** in the current data regime: NORMAL bleeds -1.09 SOL on 121 trades while DEFENSIVE returns +0.25 SOL on 45.

### Key questions to resolve BEFORE recalibrating

1. **Why does NORMAL bleed and DEFENSIVE not?** Investigate sizing multipliers, signal quality differences, mode-conditional filters in signal_aggregator and bot_core.
2. **Does the BOT-CORE-ML-GATE active sample change the picture?** Wait for ≥7 days of post-2026-05-05T14:16:48Z paper data. Re-quantify mode-by-mode PnL.
3. **Is the goal "more trades" or "more profitable trades"?** The prompt assumed more = better; the data refutes this for the current regime.

### Then (and only then) consider recalibration

If post-gate data confirms NORMAL bleed, the right lever is NOT to expand NORMAL. It might be:
- Tighten NORMAL thresholds (raise dex_vol $1B → $1.25B?) to keep low-quality off-peak signals out
- Restrict SD personality firing in NORMAL specifically (mode-conditional sizing)
- Shift to a regime-specific exit policy

These are very different fixes from the original prompt's Path A/B/C.

### What stays from the original prompt

- Hysteresis (3-cycle sustained-drop) is universally beneficial — independent of which threshold is right. This piece of the patch could land standalone, in a small follow-up session. Filed as **MM-HYSTERESIS-ONLY-001** (Tier 2 🟢).
- TIMEZONE-AUDIT-001 confirmed market_health.py is clean — TZ-fix-bundling concern resolved.

---

## §7 What this session does NOT change

- `services/market_health.py` — UNCHANGED (no commit).
- Railway env on market_health — UNCHANGED.
- `MARKET_MODES` thresholds — UNCHANGED (FRENZY 400e6/200/4e9, AGGRESSIVE 200e6/100/2e9, NORMAL 100e6/30/1e9, DEFENSIVE 50e6/10/500e6).
- Hysteresis — STILL ABSENT (mode flips on every 5-min cycle).
- bot_core consumption of `market:mode:current` — UNCHANGED.

The only artifact this session produces is documentation: this finding doc + Decision Log + STATUS/MONITORING_LOG entries.

---

## §8 Decision Log entry (paste into ZMN_ROADMAP.md)

```
2026-05-06 MARKET-MODE-001-RE-CALIBRATE 🟡 STOP / Path C — emit finding doc, no code change. Investigation per §3 revealed the session prompt's premise is incorrect for the actual data: (a) binding constraint is `dex_vol` not `grad_rate` (matches §4 Path C explicit STOP example); (b) HIBERNATE is only 1.3% of snapshots — actual problem is DEFENSIVE-vs-NORMAL not HIBERNATE-vs-NORMAL; (c) NORMAL has WORSE per-trade PnL than DEFENSIVE (-1.09 SOL on 121 vs +0.25 SOL on 45) so expanding NORMAL share would have been actively harmful. New roadmap items filed (Tier 1): DEFENSIVE-VS-NORMAL-PNL-INVERSION-001, MARKET-MODE-001-RE-CALIBRATE-V2 (re-scoped with corrected premise; gated on PnL inversion investigation). Tier 2: PUMPFUN-VOL-PLACEHOLDER-001 (`pumpfun_vol = 0.15 × dex_vol` makes the AND gate effectively 2-metric), MM-HYSTERESIS-ONLY-001 (hysteresis still beneficial standalone). NO market_health.py edit, NO deploy, NO env change. Audit: `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`.
```

---

## §9 Files

- `services/market_health.py` — UNCHANGED.
- `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md` — this doc.
- `.tmp_market_mode_recal/state_summary.md` — §1 context.
- `.tmp_market_mode_recal/throughput_quantification.txt` — §3 Step 1 raw SQL.
- `.tmp_market_mode_recal/metric_distributions.md` — §3 Step 2 distributions + diurnal.
- `.tmp_market_mode_recal/binding_constraint_findings.md` — §3 Step 3 dex_vol identification.
- `.tmp_market_mode_recal/patch_decision.md` — subagent's "hybrid Path A" recommendation (overridden in favor of Path C per the prompt's own STOP trigger).

---

**Session outcome:** Path C / STOP. The prompt was authored on a hypothesis that the data refutes; honoring the prompt's own §4 Path C trigger preserves capital and surfaces the new finding (NORMAL PnL inversion) for separate investigation. Re-scoped follow-ups filed.
