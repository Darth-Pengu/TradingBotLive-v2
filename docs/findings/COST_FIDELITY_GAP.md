# Cost-fidelity gap — the ML trains on optimistic costs and zero-latency fills

**Status:** standing finding. Survivable summary of `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md` — kept here in `docs/findings/` (not in dated `docs/audits/`) so it stays discoverable across sessions.

**One-line:** the ML training corpus is calibrated to a world where round-trip transaction costs are ~17.6× cheaper than reality and fills are instantaneous; the corruption affects label correctness in the band where threshold-tuning operates.

---

## §1 The finding (plain language)

The training pipeline (`services/ml_model_accelerator.py`) trains on `outcome` — a binary win/loss column written from `pnl_sol > 0` (`paper_trader.py:415`; `bot_core.py:1149,1365`). `pnl_sol` is **net of `_simulate_slippage` + `_simulate_fees`** (`paper_trader.py:142-213`), so the simulated cost model **does** flow into the training signal.

Three things are wrong with that signal:

**1. Costs are ~17.6× too cheap.** DB-verified on 2,874 closed paper rows post-C1: paper avg `fees_sol` = 0.00170 SOL on avg 0.116 SOL position = **1.46% round-trip**. The only on-chain truth in the corpus (id 6580, Path B `live_actual_v1`) shows 0.094 SOL on 0.365 SOL = **25.8% round-trip**. The paper sim under-counts by **~17.6×** at average paper sizing. (Source: audit §3.3.)

**2. Latency is not modelled.** Four latency columns exist on `paper_trades` (`signal_detected_at`, `scored_at`, `traded_at`, `total_latency_ms`) but are **100% NULL across all 2,874 closed rows**. Paper fills use the live Jupiter/Gecko quote at `paper_buy` invocation — wall-clock-current but no signal→fill delay simulated, and the in-flight pump that C1's fill-time MC gate exists to backstop is not modelled at all. No feature in `FEATURE_SCHEMA` encodes signal age or expected fill delay. (Source: audit §4.)

**3. The corpus is effectively 100% paper-sim fidelity.** Of ~8,680 ML-eligible rows, 99.97% carry `correction_method='pass_through'` (paper sim), 0 carry Path A (`live_estimated_v1`), and exactly **1** carries Path B (`live_actual_v1`). Live `trade_mode` share is 41/8,680 = 0.47%. Path-B-quality fidelity share is 0.012%. (Source: audit §3.4.)

### The sharper problem — label corruption in the marginal band

This is the part most likely to be forgotten. State it prominently:

> The corruption band — trades within roughly **±0.030 SOL** of zero P&L whose win/loss label would flip under realistic costs — is **wider than the median trade's entire P&L** (DB-verified median `|realised_pnl_sol|` = 0.0257 SOL).

This is not a tail problem. A large fraction of the training corpus may carry mislabeled outcomes — the model learns *"what predicts a marginal **paper**-win"*, which is a different function from *"what predicts a marginal **live**-win"*.

---

## §2 Severity — honest framing

**NOT a current-profitability fire.** Three independent reasons:
- The ML is already weakly predictive (AUC 0.536 per `ML_SCORE_ATH_VALIDATION_001_2026_05_12.md`). A cost-fidelity fix lifts signal-to-noise on a component that is currently near-random anyway.
- SD's current edge is structural — `BOT_CORE_FILL_MC_CEILING_USD=1000` (C1) runs **before** the ML score path materially gates anything. The 8.12d KEPT slice was 523 trades / +32.62 SOL / 91.4% WR with this gap in place.
- No trade is currently losing money because of this gap.

**IT IS material for three future things:**
1. **`ML_THRESHOLD_RETUNE_002`** — a threshold sweep is *specifically* a marginal-trade optimization, and the marginal band is *exactly* where labels are corrupted. Running the retune on this corpus optimizes on partially-fictional labels. (See §3 below on re-sequencing.)
2. **Analyst Phase 0 (June)** — ML-driven on mature features at higher position sizing than SD. The gap transfers into a new personality where it bites harder. (See `ANALYST-POST-GRAD-001` for the gate.)
3. **Any future paper→live edge claim.** Paper results are hypotheses until validated against live data per CLAUDE.md "Operating Principles" — the cost gap is the main reason.

---

## §3 The structural reality — this gap cannot be closed before V5A relaunch

This is the part most likely to confuse a future session, so state it explicitly:

> **The cost-fidelity gap cannot be closed pre-relaunch — only after.** Calibrating the paper cost model requires Path B (real on-chain) cost data. The corpus currently has exactly **1** Path B row. Accumulating more requires live trading. V5A relaunch therefore necessarily happens *with this gap still open* — that's how the data to close it gets produced.

This is **not a blocker**. It cannot be — closing it depends on relaunching. It is a **condition to acknowledge consciously**, which is why `AGENT_CONTEXT.md` §6 carries it under "Known conditions at relaunch (acknowledged, not blocking)" rather than as a precondition checkbox.

The staged V5A structure (v5a→v5b→v5c→v5d) and small position sizing (`MAX_POSITION_SOL=0.10`, `MAX_SD_POSITIONS=5` for the first 24h per V5A-GO-NO-GO 2026-05-01 PC8) exist precisely because the paper model is not yet trusted. The cost-fidelity gap is one of the reasons that caution is correct.

---

## §4 Follow-up sessions (pointers, not re-derivation)

The audit recommends four scoped follow-ups. They live in `ZMN_ROADMAP.md`:

| Item | Tier | Gating | Purpose |
|---|---|---|---|
| `PAPER-FEE-MODEL-CALIBRATION-001` | Tier 2 🟡 | **≥10 Path B rows** (currently 1) | Env-only recalibration of `PAPER_FEE_*` knobs to Path-B truth. Highest-leverage fix. |
| `PAPER-LATENCY-MODEL-001` | Tier 3 🟢 | `LATENCY-OBSERVABILITY-001` (column backfill) | Synthetic signal→fill delay + refetch in `paper_buy`. |
| `PAPER-MEV-SLIPPAGE-MODEL-001` | Tier 3 🟢 | Path B sample size + `PAPER-FEE-MODEL-CALIBRATION-001` baseline | Structural slippage component for MEV/sandwich/in-flight pump. |
| `ML-CONTAMINATION-FILTER-BIAS-001` | Tier 3 🟢 | none | Does the existing `exit/entry 0.97-1.03` filter disproportionately remove sim-cost-flipped marginal-win rows? (Audit §9.3 unresolved.) |

**Re-scoped to hygiene only** (originally raised by `LIVE_TRADES_LOGGING_AUDIT_001` §9.1):
- `ML-TRAINING-MODE-FILTER-001` — Tier 3 🟢. With 0.47% live share, mode-filtering is a rounding error on the training signal. The fidelity problem lives in the paper sim, not the paper/live blend. Land for clarity, not as a V5A or retune prerequisite.

**Re-prioritized:**
- `ML_THRESHOLD_RETUNE_002` — moved **behind `PAPER-FEE-MODEL-CALIBRATION-001`**. No longer "run post-eval with a caveat" — "not worth running until the cost model is calibrated." Two independent reasons to wait: (a) C1's structural edge makes the retune non-urgent regardless; (b) the audit confirms it would optimize on corrupted labels.

---

## §5 Source

- Primary evidence: **`docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md`** (the full derivation; cite §1 verdict, §2 pipeline, §3 cost simulation, §4 latency, §5 sim-to-real gap synthesis, §6 severity in context, §7 recommendations, §9 unresolved questions).
- Cross-referenced: `LIVE_TRADES_LOGGING_AUDIT_001_2026_05_14.md` §8/§9 (trigger); `ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` (ML weakness baseline); `LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md` (Path B implementation; id 6580 anchor); `STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md` (historical accounting-regime boundary).
- DB queries supporting the §1 numbers: `.tmp_ml_cost_fidelity/query.py` (gitignored; raw output captured at session time).

This findings doc is the survivable summary. The audit doc is the full derivation. If they disagree, the audit doc is canonical and this doc is wrong.
