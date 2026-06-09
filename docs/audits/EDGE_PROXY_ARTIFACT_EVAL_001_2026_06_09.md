# EDGE-PROXY-ARTIFACT-EVAL-001 — is the sub-$1k 91% WR a real edge, or a PnL artifact?

**Session:** EDGE-PROXY-ARTIFACT-EVAL-001
**Type:** READ-ONLY data forensics + code trace. **No code/env/Redis/DB write. No deploy. No flip.** Only writes = this doc + canonical updates.
**Executed:** 2026-06-09. Author: Claude Code (Opus 4.8) + multi-agent verification workflow (`wf_90482e8c-082`: DB-decisive + live-path + 3 adversarial verifiers). Parent: `docs/audits/LIVE_MC_CEILING_VERIFY_001_2026_06_08.md`.
**Bot state at session:** `TEST_MODE=true` (paper), wallet 5.064 SOL, 0 SOL at risk. Read-only — state untouched.

---

## VERDICT — 🔴 EDGE-INVALID (ARTIFACT)

> **The sub-$1k 91% WR / +189.79 SOL is essentially 100% a paper-only artifact.** It is manufactured by a ~10× **entry-oracle deflation** that, fed through the **staged-TP** mechanism, banks fabricated wins. It is **structurally absent in live** and provides **zero positive evidence** of a real trading edge. The V5A live thesis must not rest on it.

The mechanism is **not** the cross-oracle "buy-low/sell-true" hypothesis from the parent finding — it is sharper and worse:

1. **Paper buys at a deflated oracle.** Paper entry price comes from `paper_trader._get_token_price` (Jupiter v3 → GeckoTerminal, **no Redis**), which prices fresh pre-grad pump.fun tokens at **~12% of their true market cap** (`mc_entry/true_mc median = 0.121`). **100% of sub-$1k winners (2657/2657) have `entry_price < 3e-6`** — *below the physical pump.fun bonding-curve floor* (~$4–5k MC ≈ `entry_price ~4e-6`), i.e. **physically impossible as real fills.**
2. **The deflated denominator fabricates a peak multiple.** PnL = `(exit/entry − 1)·amount − fees` (`paper_trader.py:410`). With `entry_price` deflated ~10×, a *normal* intra-hold wiggle in the (equally-low but moving) PumpPortal-stream exit oracle reads as **`peak/entry median ≈ 3.9×`**. That ~3.9× mechanically trips the **+200% staged take-profit** (`bot_core.py:2152-2170` fires when `current/entry − 1 ≥ at_gain`), banking a fabricated +200–400% partial.
3. **The win is banked at the fake peak, not at a real exit.** The **final** exit is actually **below** entry (`exit/entry median = 0.863`); **98.4% of winners (2615/2657) close below their entry price** yet are booked as wins. The single-exit PnL identity `(exit/entry−1)·amt−fee == realised_pnl` **breaks on 2656/2657 winners** — the booked PnL comes from banked staged partials, not the closing leg.
4. **De-artifacted WR = 0–1%.** In *every* honestly-priced subset, the bot **never wins**: `entry≥1e-6` → 0.19% WR (n=1578, −43.35 SOL); `entry≥3e-6` (physical floor) → **0.00%** (n=343, −21.71 SOL); rows where the entry oracle is ~correct (`mc_entry/true ∈ [0.7,1.5]`) → **0/96 wins**. There is **no slice where the entry oracle is correct and the bot wins.**

---

## §0 Flag register

| Flag | Fires? | Detail |
|---|---|---|
| 🔴 **EDGE-INVALID** | **YES** | The sub-$1k 91% WR is confirmed an entry-oracle-deflation + staged-TP artifact with **no true-MC-axis edge**. De-artifacted WR 0–1%. Re-frames the V5A go decision: the live thesis cannot rest on the 91%. |
| 🟠 **SENTINEL-CONTAMINATION** | **YES (reframed)** | NOT a 1e-6 sentinel cluster (only 0.21% near 1e-6; the old live 1e-6 sentinel at `bot_core.py:1181-1209` is a separate, fixed bug). The contamination is a **broad ~10× entry-oracle deflation** across the whole sub-$1k paper corpus — **and it propagates into the `trades` ML-training table** (paper `pnl_sol`/`outcome` written at `bot_core.py:1476-1480`). The model is trained on the artifact. |
| 🟠 **PARTIAL-EDGE** | **NO** | No real edge survives de-artifacting. Every oracle-correct / above-floor subset has 0 wins. ML gate adds zero independent value (every de-artifacted ml_score band 0–0.84% WR). |
| 🟢 **STOP-Scope** | not tripped | Read-only honored. Only doc writes. |

---

## PART 1 — PnL identity + entry/exit price provenance (code, file:line)

**PnL identity** (`paper_trader.py:408-415`):
```python
pnl_pct = ((exit_price - entry_price) / entry_price) * 100
pnl_sol = (exit_price - entry_price) / entry_price * sell_amount - fees
outcome = "win" if pnl_sol > 0 else "loss"
```
`realised_pnl_sol` = this value. **WR ≈ (exit_price > entry_price).** The denominator is `entry_price`, and `market_cap_at_entry = entry_price × 1e9` (`:287`) is the *same* `entry_price` — so the band-defining quantity and the PnL denominator are one term.

**Entry-price source** (`paper_trader.py:96-139, 234-245`): `paper_trader._get_token_price` = **Jupiter v3 → GeckoTerminal (no Redis)**; on `≤0`, paper_buy falls back to the **signal-time** `bonding_curve_price`; then `entry_price = price × (1 + slippage/100)`. **This Jupiter/Gecko price is the deflated oracle** (~12% of true MC for fresh pre-grad tokens).

**Exit-price source** (`bot_core.py:2036-2061` → `:1387` → `paper_trader.py:368-401`): the exit checker `_check_exits` prices via `_get_token_prices_batch` = **Redis `token:latest_price` (PumpPortal last-trade stream) FIRST** → BC reserves → Jupiter → Gecko; passed as `exit_price_override`; `exit_price = current_price × (1 − slippage/100)`.

→ Paper **buys at the Jupiter/Gecko oracle and sells/peak-tracks at the PumpPortal-stream oracle.** Both turn out to sit ~10× below true MC, but the *entry* one defines the denominator and the *stream* one drives the staged-TP peak detection.

---

## PART 2 — The decisive tests

### 2.1 Oracle gap (the crux) — both oracles ~10× low; final exit below entry
| Metric (sub-$1k SD paper) | Median | Reading |
|---|---:|---|
| `mc_entry / true_mc` (true = `features_json.market_cap_usd`) | **0.121** | entry priced at ~12% of true MC |
| `mc_exit / true_mc` | **0.101** | exit oracle *also* ~10× low |
| `exit_price / entry_price` | **0.863** (p10 0.71, p90 0.93) | **final exit BELOW entry** |
| `peak_price / entry_price` | **~3.9×** | the deflation-driven fake peak that trips the +200% TP |

So this is **not** a buy-vs-sell cross-oracle gap (entry and exit *agree*, both deflated). It is an **entry-denominator + peak-spike** artifact.

### 2.2 WR vs entry_price (a pure step-function of the denominator)
| entry_price band | n | WR | avg PnL/trade (SOL) |
|---|---:|---:|---:|
| 1e-7–3e-7 | 49 | 100% | +0.529 |
| 3e-7–5e-7 | 601 | 99.83% | +0.123 |
| 5e-7–7e-7 | 1395 | 99.64% | +0.053 |
| 7e-7–1e-6 | 845 | 73.02% | +0.017 |
| **1e-6–3e-6** | 1235 | **0.24%** | −0.018 |
| 3e-6–1e-5 | 256 | 0% | −0.051 |
| 1e-5–3e-5 | 57 | 0% | −0.098 |
| 3e-5–1e-4 | 23 | 0% | −0.111 |

The breakpoint is at `entry_price ≈ 1e-6` (= proxy MC $1000 = the parent finding's cliff). Above it, the deflation shrinks, the fake peak no longer clears +200%, and WR → 0. **A real outcome cannot depend on whether the fill price was 7e-7 vs 1e-6.**

### 2.3 WR vs TRUE MC (no clean relationship — the edge is the deflation, not the token)
| true MC (`features.market_cap_usd`) | n | WR | rows w/ entry<1e-6 | oracle-ok AND win |
|---|---:|---:|---:|---:|
| <$3k | 771 | 35.0% | — | — |
| $3–5k | 602 | 86.2% | 566 | **0** |
| $5–10k | 3094 | 60.4% | 2007 | **0** |
| $10–30k | 2 | 100% | — | — |

WR does **not** stratify cleanly on true MC, and in the apparently-"edged" bands **zero** rows win once the entry oracle is honest. The true-MC "edge" *is* the entry-oracle deflation.

### 2.4 entry_price distribution + ML
- `entry_price`: min 7.1e-8, p25 5.1e-7, **median 6.2e-7**, p75 7.1e-7. **100% of sub-$1k winners below the 3e-6 physical floor.** Only **0.21%** cluster near 1e-6 → **not** a sentinel constant; a broad ~10× scaling.
- **ML gate = zero independent value.** Full-slice WR rises with `ml_score` (27.5 / 44.0 / 55.6 / 69.4 / 85.3%) — looks like skill. De-artifacted (`entry≥1e-6`), **every** ml band collapses to **0–0.84% WR**, negative PnL. The apparent ML skill is `ml_score` correlating with oracle deflation.

---

## PART 3 — Exit decomposition + PnL concentration

- **Exit reasons (sub-$1k winners):** `TRAILING_STOP` n=2733, WR 92.72%, **hold ~601s** (the dominant path — banks the +200% partial then trails the residual); `staged_tp_+200%` n=26 (100% WR, **hold ~1.1s**); `staged_tp_+1000%` n=11 (hold ~0.9s) — instant fabricated spikes. `stop_loss_20%` n=50 at 40% WR.
- **PnL concentration:** top-1% of winners = only **14.16%** of the total; top-10% = 42.73%; **median winner +0.043 SOL** across 2657 rows. **Broadly distributed → pervasive systematic mispricing, not a few outliers.** Trimming the tail would *not* rescue the edge — which makes the artifact **more** damning, not less.
- **Cost survival:** moot — there is no positive de-artifacted edge for the FEE-MODEL costs (1.46% paper / 25.8% live round-trip per `COST_FIDELITY_GAP`) to erode. Honestly priced, the rows are net-negative before costs.

---

## PART 4 — Live extrapolation: the artifact does NOT reproduce

**Two independent structural reasons (verified in code):**

1. **No deflated-entry-vs-stream mismatch in live.** Live entry (`bot_core.py:1179`) and live exit (`:1594`, `:2045`) **both** use `bot_core._get_token_price` → `_get_token_prices_batch` = **Redis-stream-first** (`:485-647`). The live entry is priced on the **same stream** the exit/peak-tracking uses — *not* the deflated Jupiter oracle paper uses. So `peak/entry` reflects **real** price movement; there is no fabricated ~3.9× multiple, so the staged TPs don't trip on phantom gains. The `entry_price=0.0` live sentinel (`:1196-1209`, replacing the old 1e-6) produces the **opposite** distortion — a small conservative *loss* — never a fabricated win.
2. **Live PnL is on-chain truth, not the entry ratio.** Path-B (`bot_core.py:1680-1726`) sums the real wallet `nativeBalanceChange` across the entry sig and every exit sig (`helius_parser.py:94-98`); `_booked_pnl = _path_b_pnl_sol if not None else pnl_sol` drives the balance + `DAILY_LOSS_LIMIT` kill-switch (`:1739-1741`); `corrected_pnl_sol = live_actual_v1`. Anchored: id 6580 Path-B −0.094 SOL == on-chain. **Real lamports cannot be inflated by any oracle mispricing.** (Caveat: `realised_pnl_sol` on live rows is the Path-A *estimate* when a Helius parse misses — conservative, never the paper upward artifact; `corrected_pnl_sol` is authoritative.)

**De-artifacted WR estimate:** ~**0.5%** (band 0–2%) under honest paper pricing. **This is a floor under a still-mis-priced sim, NOT a calibrated live projection** — those rows are mostly dead/declining tokens once priced honestly. **The true live token-quality WR is genuinely UNKNOWN** (only ~1 real on-chain SD trade exists). The honest statement: **paper provides zero positive evidence of an edge; live data is the only validator.**

---

## PART 5 — Synthesis (critic role — authored directly; the critic subagent failed to spawn, see §7)

| Field | Finding |
|---|---|
| **Final verdict** | **ARTIFACT** (🔴 EDGE-INVALID). Unanimous across DB-decisive, live-path, and all three adversarial verifiers (v1 confirms-artifact/refutes-original-mechanism; v2 confirms-non-transfer; v3 refutes-the-steelman). |
| **De-artifacted WR** | ~**0.5%** (0–2%). A floor under the paper sim, not a live projection. |
| **Live WR expectation** | Will **NOT** reproduce 91%. The artifact is structurally absent live. True live WR is **unknown** — paper gives no positive edge signal in either direction. |
| **Biggest residual risk** | **Symmetry of overconfidence:** just as "paper = 91% winner" was a fabrication, "live = certain 0% loser" would be *equally* an over-read of an artifacted paper sim. The de-artifacted 0–1% reflects honestly-repriced *dead paper tokens*, not a measured live edge. **Only Path-B live data resolves the true edge — up or down.** |
| **Gaps** | (a) Only ~1 real on-chain SD trade → live WR unobserved. (b) The **root cause of the ~10× Jupiter/Gecko deflation** (decimals / supply-scaling / pre-grad mis-pricing) was not traced to a specific bug. (c) `true_mc = features_json.market_cap_usd` is an unre-verified anchor — but the **physical-BC-floor** de-artifact (entry < 3e-6 impossible) is independent of it and agrees. (d) **ML-corpus contamination not yet quantified/remediated.** |
| **Follow-ups** | 1. **Root-cause fix** (file, don't implement): `paper_buy` should use the **BC-reserves price as PRIMARY** for pre-grad tokens (it is computed *correctly* at `bot_core.py:1028-1033` and only used as a `≤0` fallback today). 2. Root-cause *why* Jupiter/Gecko returns ~12% of true MC. 3. **ML-corpus de-contamination + retrain** (the `trades` table is poisoned by paper `pnl_sol`). 4. OBS-011 live fill-price-vs-anchor delta tracker. 5. Smallest-possible **supervised live probe** to measure the real edge. |
| **V5A implication** | The sub-$1k confinement (`BOT_CORE_FILL_MC_CEILING_USD=1000`) remains **mechanically safe and stable across the flip** (per `LIVE_MC_CEILING_VERIFY_001`) — but its **EDGE justification is gone.** What the gate gates is not a validated edge. This is a **re-framing, not necessarily a hard flip-blocker** (the gate doesn't lose money), but it converts the flip from "deploy a measured 91% edge" into "**run a genuine experiment with unknown edge**" — mandating the smallest viable position sizing, strict loss caps, and active observation. Binds `COST_FIDELITY_GAP`: the gap closes only with Path-B live data. |

**One-line verdict:** the sub-$1k 91% WR is ~100% a paper artifact (entry-oracle deflation → fabricated staged-TP peaks); it does not exist in live and is not a validated edge — the V5A flip is an experiment, not the deployment of a known edge.

---

## §6 Root cause (for the follow-up fix — NOT implemented here)

`paper_buy` (`paper_trader.py:233-245`) calls `paper_trader._get_token_price` (Jupiter→Gecko) **first** and only falls back to the **signal-time `bonding_curve_price`** when that returns `≤0`. The BC-reserves price *is computed correctly* in the caller (`bot_core.py:1028-1033`: `(vSol/vTokens) × sol_price`) and matches the true MC used by the SA gate and `features_json.market_cap_usd`. So **paper systematically prefers a wrong (~10×-low) Jupiter price over an available correct BC price.** Making the BC-reserves price the **primary** for pre-grad fills would de-fabricate the paper corpus. (Why Jupiter is ~10× low for these mints — decimals/supply/pre-grad routing — is itself an open root-cause item.)

## §7 Method / provenance
- Code trace (direct reads): `paper_trader.py:38-61, 96-139, 233-301, 345-420`; `bot_core.py:485-647, 1023-1080, 1152-1209, 1330-1664, 1680-1726, 2036-2170`; `helius_parser.py:33-133`.
- DB: read-only asyncpg over `DATABASE_PUBLIC_URL` (SELECT-only). Slice = SD paper closed (`realised_pnl_sol IS NOT NULL`), n=4468; sub-$1k n=2890. Each load-bearing query was **independently re-run by the steelman verifier** and replicated to the decimal.
- Workflow `wf_90482e8c-082` (6 agents): DB-decisive, live-path, and **3 adversarial verifiers** (artifact / non-transfer / steelman-edge) — all consistent. The **final-critic agent failed to spawn** (3 retries, each returned empty in <25ms with 0 tokens — a transient platform-side agent-spawn issue, not a content failure); §5 was therefore synthesized directly from the verified DB + live + verifier outputs.
