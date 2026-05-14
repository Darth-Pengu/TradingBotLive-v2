# ML-TRAINING-COST-FIDELITY-AUDIT-001 — does the ML train on realistic costs and latency?

**Session:** ML-TRAINING-COST-FIDELITY-AUDIT-001
**Date:** 2026-05-14 (AEDT)
**Type:** Read-only investigation. NO code, NO env, NO Redis writes, NO deploy.
**HEAD at session start:** `b28bdbe`
**Trigger:** LIVE-TRADES-LOGGING-AUDIT-001 §8/§9 raised the larger question: does the ML train on realistic transaction costs and latency, or on an optimistic simulation?

---

## §1 Verdict (one paragraph)

**Sim-to-real gap CONFIRMED.** The ML training target is the `outcome` string column (binary `win`/`loss`, derived from `pnl_sol > 0` at `paper_trader.py:415` and `bot_core.py:1149,1365`). `pnl_sol` is NET of both `_simulate_slippage` and `_simulate_fees` — so the cost model **does** reach the training signal. The cost model itself (`paper_trader.py:142-213`, FEE-MODEL-001) materially under-counts real Solana costs: empirically observed paper fees average **0.00170 SOL on a 0.116 SOL avg position = 1.46% round-trip**, vs Path B reality on id 6580 (the only `live_actual_v1` row in the corpus) of **0.094 SOL on 0.365 SOL = 25.8%** — a **~17.6× under-count at average paper sizing**. Latency is not modelled at all: 4 latency columns exist on `paper_trades` but are 100% NULL across 2,874 closed rows; no signal→fill delay is simulated; the paper fill price is the Jupiter/Gecko price at the moment `paper_buy` runs, which is wall-clock-current but does NOT model the systematic in-flight pump that C1's fill-time MC gate exists to backstop. Of 8,680 ML-eligible rows, only **1 row** carries Path B (real on-chain) fidelity; 41 are `trade_mode='live'` (mostly Path A `live_estimated_v1` — same optimistic sim). The training corpus is effectively 100% paper-fidelity; the live-vs-paper distinction the LIVE-TRADES-LOGGING-AUDIT-001 §9 question contemplated is statistically negligible for current training. **Severity:** the ML is already known weakly-predictive (AUC 0.536 per ML_SCORE_ATH_VALIDATION_001) and SD's current profitability is structural-filter-driven (C1 MC ceiling, independent of ML), so the gap does NOT degrade current SD profitability today. It **does** materially affect (a) the post-eval `ML_THRESHOLD_RETUNE_002` — a retune calibrated on a 17.6×-optimistic fee world optimizes against a fiction; and (b) Analyst Phase 0 (June) — ML-driven on mature features, the gap would transfer into a new personality at higher sizing.

---

## §2 Training pipeline (where, what, how)

Entry point: **`services/ml_model_accelerator.py`** (confirmed sole runtime pipeline — `services/ml_engine.py` is the original ml_engine; current Railway env on ml_engine service is `ML_ENGINE=accelerated` per AGENT_CONTEXT §2, so accelerated is the active engine).

### §2.1 Tables read

`ml_model_accelerator.AcceleratedMLEngine.train` reads BOTH `trades` and `paper_trades`:

- `ml_model_accelerator.py:351-359` — `SELECT features_json, outcome FROM trades WHERE created_at > $1 AND features_json IS NOT NULL AND outcome IS NOT NULL AND NOT (closed_at < $2 AND exit_price BETWEEN entry_price * 0.97 AND entry_price * 1.03)`
- `ml_model_accelerator.py:365-374` — same shape on `paper_trades` with `entry_time` / `exit_time` columns and a softer contamination filter (the no-momentum/time-exit/stale carve-out).
- `:375` — `rows = list(rows) + list(paper_rows)` — the two are **concatenated with no source label**.

### §2.2 Training TARGET (the label)

The target is the `outcome` string column. Binary classification: positive class = `outcome IN ('profit','win')`, negative = anything else.

- `ml_model_accelerator.py:391` — `labels.append("win" if row["outcome"] in ("profit", "win") else "loss")`
- `ml_model_accelerator.py:214` — `y = y.map(lambda v: 1 if v == "win" or v == "profit" or v == 1 else 0)`

Where `outcome` is written:
- `paper_trader.py:415` — `outcome = "win" if pnl_sol > 0 else "loss"`
- `bot_core.py:1149` — `outcome = "win" if pnl_sol > 0 else "loss"` (paper-mode close inside bot_core)
- `bot_core.py:1365` — `outcome = "profit" if pnl_sol > 0 else "loss"` (live-mode close inside bot_core)

In all three writers, `pnl_sol` is computed AFTER simulated slippage + fees are deducted (`paper_trader.py:410`: `pnl_sol = (exit_price - entry_price) / entry_price * sell_amount - fees`). **The cost simulation is therefore in the training signal at the threshold zero.**

### §2.3 Features

`FEATURE_SCHEMA` (`ml_model_accelerator.py:54-81`) lists 25 features. **None are cost- or latency-derived.** All are pre-trade observables (liquidity, BSR, holders, BC progress, dev-wallet, age, MC, CFGI, SOL price, Nansen signals, etc.). The model has no feature awareness of post-fill cost outcomes — the cost effect reaches it only via the label.

### §2.4 Filters applied

- **Contamination filter:** narrow exit-price-near-entry-price + (for paper) exit-reason carve-out, controlled by `ML_TRAINING_CONTAMINATION_CUTOFF` env var (default `1775767260.0` = 2026-04-09 20:41 UTC). Excludes the broken pre-9b880e1 exit-pricing rows. NOT a cost-fidelity filter.
- **30-day rolling window:** `created_at > now() - 30*86400` (`ml_model_accelerator.py:343,358,367`).
- **NO `trade_mode` filter** — confirms LIVE-TRADES-LOGGING-AUDIT-001 §9.
- **NO `correction_method` filter** — paper-sim (`pass_through`), Path A optimistic estimate (`live_estimated_v1`), and Path B on-chain truth (`live_actual_v1`) are all blended with no distinction.

---

## §3 Cost simulation — what's modelled, at what fidelity

`paper_trader.py:142-213` defines `_simulate_slippage` and `_simulate_fees`. Both are called per-side at buy/sell.

### §3.1 Slippage (`_simulate_slippage`, `paper_trader.py:142-158`)

Per-tier 3-tuples `(low_pct, high_pct, size_impact_exp)` in `SLIPPAGE_RANGES`:

- Pre-grad BC buy (`alpha_snipe`, `confirmation`): 3-12% / 2-8%, exp 0.7
- Pre-grad BC sell: 3-15%, exp 0.7
- Post-grad AMM buy / sell: 0.5-2% / 0.5-2.5%, exp 0.3

Applied: `slippage = random.uniform(low,high) * (amount_sol / 0.1) ** exp`. **What this captures:** the bid/ask spread on pump.fun BC pools at the position size. **What it MISSES:** MEV sandwich attacks, in-flight price pump between signal-time and fill-time, validator-side priority skew. The post-grad band (0.5-2%) is roughly aligned with observed Jupiter slippage; the pre-grad band (3-15%) is plausible for spread but doesn't include MEV.

### §3.2 Fees (`_simulate_fees`, `paper_trader.py:161-213`)

Per-side components:

- **Platform fee:** 1% (pump.fun pre-grad, `PAPER_FEE_PUMPFUN_PCT=0.01`) / 0.25% (Raydium) / 0.6% (Jupiter-bundled).
- **LP fee:** 0% on pump.fun BC; 0.25% on Raydium AMM; bundled into Jupiter.
- **Priority fee:** 0.0005 SOL per side pre-grad / 0.0010 SOL per side post-grad (half of round-trip envs).
- **Jito tip:** 0.0 pre-grad (`PAPER_JITO_TIP_PREGRAD_SOL=0.0`, comment notes "until EXEC-005 lands"); 0.0005 SOL per side post-grad.

For a typical SD pre-grad trade at 0.1 SOL:
- platform 0.1 × 1% = 0.001 SOL
- priority 0.0005 SOL
- jito 0.0
- **per-side total ≈ 0.0015 SOL ⇒ round-trip ≈ 0.003 SOL** = 3% round-trip cost.

### §3.3 Verified against the corpus

DB query 2026-05-14 against 2,874 closed paper_trades rows post-C1 (entry_time > C1 deploy floor):

- `avg(fees_sol) = 0.00170 SOL`, `median(fees_sol) = 0.00144 SOL`
- `avg(amount_sol) = 0.116 SOL`
- ⇒ **paper round-trip fees = 1.46% of avg position size**

The single Path B `live_actual_v1` row (id 6580, FEE-MODEL-001 anchor) shows **0.094 SOL on 0.365 SOL = 25.8% round-trip**. Re-projecting to the corpus's avg sizing (0.116 SOL) at the same per-trade Path B rate → expected real cost ≈ **0.030 SOL**. Paper sim says 0.00170 SOL.

**Per-trade under-count factor: 0.030 / 0.00170 ≈ 17.6× optimistic** at current avg paper sizing. The prompt's "~12×" prior anchor was on a single trade at 0.365 SOL where the percentage gap is similar (sim ~0.008 SOL vs actual 0.094 SOL = 11.8×).

### §3.4 Fidelity-tier distribution in the corpus

DB query against `paper_trades` (closed rows, `outcome IS NOT NULL`):

| `correction_method` | n | share |
|---|---:|---:|
| `pass_through` (paper sim — `_simulate_fees`/`_simulate_slippage`) | 2,873 | **99.97%** |
| `live_estimated_v1` (Path A — same optimistic sim, just tagged at live close) | 0 | 0.00% |
| `live_actual_v1` (Path B — real on-chain via Helius parseTx) | 1 | 0.03% |
| NULL | 0 | 0.00% |

By `trade_mode` on paper_trades closed: 2,868 paper / 6 live (1 Path B + 5 reconcile-residuals tagged `pass_through`).

ML-training corpus (combined `trades` + `paper_trades`, 30d window, contamination filter applied) ≈ **8,680 ML-eligible rows**, of which **41 are `trade_mode='live'` on `trades`** (paper_trades contributes essentially zero live; the 35 v3/v4 trial trades were never mirrored into `paper_trades` per LIVE-TRADES-LOGGING-AUDIT-001 §9.2). **Live-row share of training corpus = ~0.47%.** Path-B-quality fidelity share = 1 in 8,680 = **0.012%**.

**Interpretation:** the corpus is effectively 100% paper-sim fidelity. Filtering or weighting live rows differently from paper rows in training would shift well under 1% of the signal — not a meaningful intervention by itself. The fidelity problem lives in the paper sim, not in the paper/live blend.

---

## §4 Latency — modelled or not?

### §4.1 Columns exist but are 100% NULL

DB query confirms `paper_trades` has columns `signal_detected_at`, `scored_at`, `traded_at`, `total_latency_ms` (4 of 4). Population across 2,874 closed rows: **0/2874 on every one**. AGENT_CONTEXT §7 LATENCY-OBSERVABILITY-001 status reaffirmed (the doc's "NULL on 1,182 rows" was an earlier snapshot; current count is 2,874).

### §4.2 Latency is not modelled into the fill price

Read `paper_trader.paper_buy` (`paper_trader.py:216-345`). The flow:

1. `:234` — `price = await _get_token_price(mint)` → real-time Jupiter V3 / GeckoTerminal lookup at the moment `paper_buy` runs.
2. `:244-245` — `slippage = _simulate_slippage(...)` → applied as a +pct bump on top of `price`.
3. No simulated wait. No "if signal_time < now - X then re-fetch price at signal_time + X". The paper fill price is **the live Jupiter quote at fill-clock-time**, plus a synthetic slippage on top.

What this captures: any wall-clock delay between signal emission and `paper_buy` invocation is implicit (~1s typical pipeline pass-through). What it MISSES: real on-chain submit→land delay (priority-fee queueing, Jito bundle inclusion, RPC routing), and — critically — the **in-flight pump** during that delay. Live SD fills land 1-15s after signal; pump.fun tokens routinely move 50-200% in those windows. C1's fill-time MC ceiling exists precisely because signal-time and fill-time MC diverge by enough to materially shift the trade's outcome distribution.

### §4.3 Latency-feature absence

No feature in FEATURE_SCHEMA encodes signal age, fetch latency, or expected fill delay. The model cannot learn "trades where the pipeline was congested perform worse." This is an opportunity surface (if latency columns were populated and added as features) but not the topic of this audit.

### §4.4 Net latency fidelity

Paper trades enter at a **systematically more advantageous price than real live trades** because:
- The Jupiter quote at `paper_buy` time approximates an instantaneous fill.
- Real live fills carry 1-15s of in-flight slippage on top of the modelled `_simulate_slippage` band.
- The 3-15% pre-grad sell slippage band roughly covers static spread + sandwich risk, but it does NOT cover signal-to-fill pump (which can be +100% on a hot mint).

**Latency fidelity assessment: zero-latency optimistic.** The paper model treats the signal-time price as the fill-time price modulo a static slippage range. Real fills are anchored to the on-chain price at submit-land moment, which is materially worse on the entry side.

---

## §5 Sim-to-real gap synthesis

Combining §2-§4:

| Dimension | What the ML trains on | What live looks like | Gap |
|---|---|---|---|
| Cost (fees + slippage) | sim ~1.5% round-trip on avg 0.116 SOL position | Path B id 6580: 25.8% round-trip | **~17.6× optimistic** |
| Latency / fill timing | zero modelled delay; Jupiter quote at `paper_buy` time | 1-15s submit-land + in-flight pump | **systematically optimistic entry price** |
| Mode blending | paper + live undifferentiated; 0.47% live in corpus | — | negligible by share, but tag exists |
| Fidelity tier (correction_method) | 99.97% `pass_through` (sim) + 0.03% Path B | — | corpus is sim-only in practice |

**Net assessment:** the ML's notion of "profitable entry" is calibrated to a world where round-trip costs are ~17× cheaper and fills are instantaneous. Marginal trades (the band where outcome ∈ ±0.030 SOL of zero — that band exists at median |realised_pnl_sol| = 0.0257 SOL, so a large fraction of the corpus) have their `win`/`loss` labels corrupted by the gap: they're labelled `win` under the sim and would be `loss` under live cost reality. The model therefore learns "features that predict marginal-paper-win" rather than "features that predict marginal-live-win."

---

## §6 Severity in context

Honest framing:

1. **The ML is already weakly-predictive** — AUC = 0.536 on the ATH≥5× classifier per `ML_SCORE_ATH_VALIDATION_001`. The cost-fidelity gap degrades a component already known to be near-random. A fidelity fix could lift signal-to-noise, but won't transform AUC 0.536 into 0.7.
2. **C1 is doing the work, not the ML.** SD's current profitability is driven by `BOT_CORE_FILL_MC_CEILING_USD=1000` — a hard structural-feature gate that runs **before** the ML scoring path even matters in paper mode. Per `BOT-CORE-ML-GATE-001` 2026-05-05, the bot_core ML gate at threshold 40 is the only paper-effective ML filter, and per `ML_SCORE_ATH_VALIDATION_001`, that threshold is sub-optimal vs no-gate (would have cost -1.26 SOL over 12d). The ML is currently a minor input.
3. **NOT a current-profitability fire.** Even with the gap, SD is +1.49 SOL/day W3+W4 / +3.02 W4-only on the 8.12d C1-counterfactual sample. The gap is not the reason any trade is currently losing money.

But the gap materially affects three future things:

1. **`ML_THRESHOLD_RETUNE_002` (≥2026-05-19).** The retune re-derives the optimum ML threshold on post-`BOT_CORE_ML_GATE` clean data. If the labels are corrupted by ~17× optimistic costs, the sweep finds an optimum that **maximizes sim-profit, not live-profit**. The 2026-05-12 ML_SCORE_ATH_VALIDATION_001 finding (historical optimum thr=55 worth +0.16 SOL/day) was derived from the same sim-cost labels — its "live lift" projection inherits the optimism.
2. **Analyst Phase 0 (June).** Analyst is ML-driven on mature features at higher position sizing. The gap **transfers** into a new personality at a sizing factor where it matters more. ROADMAP `ANALYST-POST-GRAD-001` Phase-1 design implicitly assumes ML-derived signal quality.
3. **Any future paper-to-live edge claim.** Paper results "are hypotheses until validated against live data" per CLAUDE.md "Operating Principles" — the first live data point (Session 5 v4, mint `yh3n441…`) showed paper overstating PnL by ~96× at that single point. The cost gap is the main reason.

---

## §7 Recommendation + scoped follow-up sessions

### §7.1 Should live rows be filtered/weighted in paper-model training?

**No, not as the primary fix.** With 41 live rows in an 8,680-row corpus (~0.47%), any mode-filter is a rounding error on the training signal. The LIVE-TRADES-LOGGING-AUDIT-001 §9 follow-up `ML-TRAINING-MODE-FILTER-001` should still land for hygiene/clarity (it's cheap), but it is **not the lever** here. Re-scope `ML-TRAINING-MODE-FILTER-001` to Tier 3 🟢 (hygiene) and drop it as a V5A or retune prerequisite.

### §7.2 Should the paper cost model be improved before the ML retune?

**Yes** — this is the highest-leverage intervention. Two non-overlapping options:

**Option A: Re-tune the existing env-driven knobs.** `paper_trader.py` exposes `PAPER_FEE_PUMPFUN_PCT`, `PAPER_PRIORITY_FEE_PREGRAD_SOL`, `PAPER_JITO_TIP_PREGRAD_SOL`, etc. as Railway env vars. Recalibrating these to Path B truth requires no code change — just env writes. The Path B anchor is id 6580 (single point), but `LIVE-PATH-B-SLIPPAGE-DERIVATION-001` (existing roadmap item) is the right scope to accumulate more Path B samples and re-derive the params. Cost: a 30-min env-only deploy after enough Path B rows accumulate. **Scope as `PAPER-FEE-MODEL-CALIBRATION-001` Tier 2 🟡 — gated on ≥10 Path B rows (currently 1).**

**Option B: Add a tiered slippage uplift specifically for pre-grad in-flight pump.** A separate "MEV/sandwich/pump" slippage component that's NOT modelled today. This is structural — not just a knob tweak. Cost: ~1h code change + calibration window. **Scope as `PAPER-MEV-SLIPPAGE-MODEL-001` Tier 3 🟢 — defer until Path B sample size supports calibration.**

**Pragmatic intermediate option (don't fix the model, label-weight instead):** weight `live_actual_v1` rows higher in training. With 1 such row, useless today; revisit when ≥10 accumulate.

### §7.3 Should a latency penalty be added to paper fill simulation?

**Yes, eventually — but lower priority than §7.2.** The cost gap (17.6×) dominates the latency gap (zero modelled but covered partially by `_simulate_slippage` band). Adding latency-aware fill requires either:
- Backfilling the 4 latency columns (currently 0% populated) — that's `LATENCY-OBSERVABILITY-001`, already on the roadmap.
- A synthetic delay-and-refetch step in `paper_buy` that re-queries Jupiter after a simulated `signal→fill_delay_seconds` wait. Cost: medium; expensive in API budget.

**Scope as `PAPER-LATENCY-MODEL-001` Tier 3 🟢 — gated on `LATENCY-OBSERVABILITY-001` so it can be calibrated against observed latency.**

### §7.4 Sequencing — what must happen before what?

1. **Before `ML_THRESHOLD_RETUNE_002` (≥2026-05-19)** — at minimum, **annotate the retune's verdict with a "calibrated against sim costs" caveat** so a future audit doesn't take the optimal threshold at face value. Cost: 1 sentence in the retune prompt. No actual fix required to run the retune.
2. **Before `PAPER-FEE-MODEL-CALIBRATION-001` can deploy** — need ≥10 Path B rows (currently 1). Accumulating those requires the V5A relaunch (gated by V5A preconditions including PC3 `LIVE-MODE-FILTER-PARITY-001-V2`).
3. **Before `ANALYST-POST-GRAD-001` ships** — `PAPER-FEE-MODEL-CALIBRATION-001` should be deployed AND ≥7 days of post-calibration paper data should accumulate so the Analyst sample is on the recalibrated fee model. June Analyst Phase 0 currently has no such gate; this audit recommends adding it.

### §7.5 What this session does NOT do

- Does NOT change any code, env, Redis key, or DB row.
- Does NOT retrain the ML.
- Does NOT recalibrate any fee/slippage param.
- Does NOT decide the retune verdict.

---

## §8 References

- `services/ml_model_accelerator.py` — training pipeline (verified read 2026-05-14; sole runtime engine per `ML_ENGINE=accelerated` env on ml_engine service)
- `services/paper_trader.py:142-213` — `_simulate_slippage` + `_simulate_fees`
- `services/paper_trader.py:216-345,353-471` — `paper_buy` + `paper_sell` (`pnl_sol` derivation)
- `services/bot_core.py:1149,1365` — paper + live `outcome` writers
- `services/db.py:114-138,181-190` — `paper_trades` + `trades` schema; `trade_mode` discriminator landed by LIVE-TRADES-LOGGING-AUDIT-001
- `docs/audits/LIVE_TRADES_LOGGING_AUDIT_001_2026_05_14.md` §8/§9 — trigger
- `docs/audits/ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` — ML AUC 0.536
- `docs/audits/STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md` — historical accounting-regime boundary
- `docs/audits/LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md` — Path B implementation
- AGENT_CONTEXT §7 — LATENCY-OBSERVABILITY-001

DB queries (raw output): `.tmp_ml_cost_fidelity/query.py` and stdout captured in `.tmp_ml_cost_fidelity/PROGRESS.md`.

---

## §9 Unresolved questions

1. **The Path B sample size is 1.** All quantitative claims about "real live cost = 25.8% round-trip" rest on one row (id 6580). The ~17.6× under-count factor is therefore an estimate, not a confidence interval. Closing this requires accumulating Path B rows, which requires V5A relaunch + post-relaunch parseTx pipeline reliability. Pre-V5A there is no path to more data.
2. **MEV / sandwich-attack quantification.** Whether the dominant under-count is fees-proper, MEV/bribe, or in-flight pump is not separable from the single Path B row. The recommendation (§7.2) treats them as a single bucket; a more sophisticated model would separate them. Out of scope for this audit.
3. **Does the contamination filter accidentally bias toward sim-flattering rows?** The filter (`ml_model_accelerator.py:354-356, 368-372`) excludes rows where `exit_price BETWEEN entry_price * 0.97 AND entry_price * 1.03` (with exit-reason carve-outs on paper). It is plausible that this disproportionately removes rows where the sim cost flipped a marginal outcome from `win` to `loss` near zero PnL. Not investigated this session; flagged as `ML-CONTAMINATION-FILTER-BIAS-001` Tier 3 🟢 for a future targeted look.
4. **Is `outcome='breakeven'` or other non-binary values used anywhere?** `outcome` is written as `"win"`/`"loss"` (or `"profit"`/`"loss"` on live close); the training only accepts `"win"|"profit"` as positive. Other values would be implicitly negative. No row in the verified corpus has a third value, but the schema doesn't enforce it.

---

## §10 Verdict

✅ **AUDIT COMPLETE — sim-to-real gap CONFIRMED.** ML trains on paper-fidelity labels that under-count real round-trip cost by ~17.6× and assume zero fill latency. Gap is not a current-profitability fire (ML is weak; C1 is structural), but is material for ML_THRESHOLD_RETUNE_002 and for Analyst Phase 0. Three new follow-up sessions recommended (`PAPER-FEE-MODEL-CALIBRATION-001` Tier 2; `PAPER-LATENCY-MODEL-001` Tier 3; `PAPER-MEV-SLIPPAGE-MODEL-001` Tier 3). Existing `ML-TRAINING-MODE-FILTER-001` recommendation re-scoped to Tier 3 🟢 hygiene. `ML_THRESHOLD_RETUNE_002` should ship with a "calibrated against sim costs" caveat in its verdict statement; not blocked by this audit.
