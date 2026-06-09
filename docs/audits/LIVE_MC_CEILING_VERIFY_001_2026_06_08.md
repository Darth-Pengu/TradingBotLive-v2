# LIVE-MC-CEILING-VERIFY-001 — does the live MC fill-ceiling admit the same sub-$1k population paper measured at ~91% WR?

**Session:** LIVE-MC-CEILING-VERIFY-001
**Type:** READ-ONLY code + config + DB verification. **No code/env/Redis/DB write. No deploy. No flip.** Only writes = this doc + the four canonical doc updates.
**Executed:** 2026-06-09 (queued 2026-06-08). Author: Claude Code (Opus 4.8) + 6-agent verification workflow (`wf_09a737b8-a35`).
**Bot state at session:** `TEST_MODE=true` (paper), RUNNING, wallet 5.064 SOL on-chain, 0 SOL at risk. Read-only — state untouched.

---

## TL;DR (the one-line question, answered)

> *When paper says a trade was a sub-$1k entry (91% of which won), will the live path put that **same** trade on-chain — or could its fill-time MC math admit/reject a different set?*

**Verdict: NOT a clean 1:1 transfer. The mapping is SHIFTED-BY-DRIFT and, more importantly, PROXY-BOUNDED.**

1. **Formula = identical** across all three gates and both logged columns: `price × 1e9 supply`, USD. No denomination bug. ✅
2. **Gate quantity == band quantity**: paper's `market_cap_at_entry` (the column the 91% was measured on) is *exactly* `entry_price × 1e9` — the same quantity the fill gate tests. So the gate operates on the same *kind* of number the band was measured on. ✅
3. **But the price INPUT differs** between paper and live: paper prices Jupiter-v3→Gecko, falling back to **signal-time** BC reserves, then applies a slippage bump; live prices the **fill-time** Redis PumpPortal stream first, with **no** slippage on the gate. Different pipeline, different lifecycle anchor → the live-admitted set is the paper band **± un-measurable signal→fill drift**, and that drift lands exactly on the **$1000 cliff** where WR collapses. 🟠
4. **The deeper finding (unanticipated by the prompt):** the "sub-$1k" band is a **price-proxy**, not a true market cap (true full-supply MC of these tokens is ~8× larger, median **~$5,172**). WR is a near-vertical step-function of the proxy (`<$500` = 99.85% WR → `$800–1000` craters to 26.72% → `≥$1000` ≈ 0%). The 91% is the **gate selecting the winning side of its own proxy** — an entry-price-selection artifact, **not a validated small-MC edge**. Whether it transfers depends on live reproducing paper's low entry *prices*, which the fill-time stream pipeline may not. 🟠

**Bottom line for the flip:** the live MC gate is *safe* (fails CLOSED, formula-clean, binding cap $1000, stable across the flip). But the **91% sub-$1k WR is a paper-model hypothesis bounded by a fill-ceiling artifact, not a confirmed live edge** — treat it as such in any sizing/go decision. The gap is **not closeable pre-flip** from static analysis or the DB; it needs live fill-price-vs-paper-anchor instrumentation (consistent with `COST_FIDELITY_GAP` / FEE-MODEL-001 / SLIPPAGE-CALIBRATION-001).

---

## §0 Flag register

| Flag | Fires? | Detail |
|---|---|---|
| 🔴 **FAIL-OPEN** (gate proceeds when MC can't be computed) | **NO** | Live gate **fails CLOSED** — `fill_price<=0` → `logger.warning("FILL_MC_CEILING fail-CLOSED (live)")` → `return` (skip buy), `bot_core.py:1155-1157`. Confirmed by adversarial verifier + direct read. |
| 🔴 **MC-MISMATCH** (different formula/source than paper's column) | **PARTIAL** | **Formula** identical (`price×1e9`, USD). **Source/pipeline** genuinely **differs** (live=Redis fill-time stream-first; paper=Jupiter/Gecko→signal-time-BC). Fires on the *source* clause only, not the formula clause. |
| 🟠 **TIMING-DRIFT** (live fill-time vs paper signal-time) | **YES** | Paper falls back to **signal-time** BC reserves (common for fresh pre-grad, where Jupiter/Gecko miss); live reads **fill-time** PumpPortal stream. Plus a paper-only slippage inflation. 800–1000 fringe = **9.07%** of the sub-$1k band and is **already a loss zone** (26.72% WR). Direction two-sided; magnitude **not bounded from the DB**. |
| 🟠 **PROXY-ARTIFACT / EDGE-NOT-VALIDATED** (NEW — not in the prompt's register) | **YES** | `market_cap_at_entry` is `entry_price×1e9` (a price proxy ~8× below true MC); WR is a near-vertical cliff in the proxy; the 91% is gate proxy-selection, not a validated small-MC edge. |
| 🟢 **STOP-Scope** (any write/change) | not tripped | Read-only honored. Only doc writes. |
| 🟢 **STOP-A** (Railway not logged in) | not tripped | `railway whoami` = `jay@rzconsulting.co`; env read live. |

---

## PART 1 — Deployed ceiling values (complete signal→fill MC-gate set)

Three — and only three — market-cap gates exist on the signal→fill path (verified complete by an exhaustive `services/` sweep for `market_cap`/`mcap`/`liquidity_usd`/`MC_CEILING`/`usdMarketCap`/`fdv`/KOTH-zone numeric comparisons; no other gate *blocks a buy* on an MC-like quantity — other hits are stored/logged only).

| # | Gate | Service · file:line | Var | Deployed | When it fires | Fail mode |
|---|---|---|---|---|---|---|
| 1 | `SD_MC_CEILING_002` | signal_aggregator · `:56` (decl), `:1855-1879` (gate) | `SD_MC_CEILING_USD` | **3000** | **Signal-time**, SD-only, before ML prefilters | **fail-OPEN** (`mc_at_eval_usd=None` on any missing reserve/sol_price → does **not** reject, `:1871`) |
| 2 | Paper fill ceiling | paper_trader · `:253-275` | `BOT_CORE_FILL_MC_CEILING_USD` | **1000** | **Fill-time**, paper (`TEST_MODE=true`) | fails **closed** (closes *upstream* at `:238-240`: price≤0 → `paper_buy` returns `price_fetch_failed` before the gate runs) |
| 3 | Live fill ceiling | bot_core · `:1152-1172` | `BOT_CORE_FILL_MC_CEILING_USD` | **1000** | **Fill-time**, live (`not TEST_MODE`), in the `else` branch *before* `execute_trade` (`:1173`) | fails **closed** (`fill_price<=0` → log + `return`, `:1155-1157`) |

**Effective binding cap on a live buy = $1000** (Gate 3). A 1k–3k signal that passes Gate 1's fail-open ($3000) is caught by Gate 3's fill-time $1000 ceiling before execution — the backstop works. (Gate 1's purpose is to short-circuit *before* ML scoring / the SocialData call; Gate 3 is the line that actually bounds the buy.)

**Stable across the flip — confirmed.** The §6 flip-config (`FLIP_READINESS_REVIEW_001`) changes only `MAX_POSITION_SOL 0.25→0.10`, `DAILY_LOSS_LIMIT_SOL 4.0→1.5`, `AGGRESSIVE_PAPER_TRADING→false`, concurrency `10→5`. It touches **neither** MC ceiling. Both `BOT_CORE_FILL_MC_CEILING_USD=1000` and `SD_MC_CEILING_USD=3000` carry through the flip unchanged. (Deployed env read live via `railway variables`; secrets redacted.)

---

## PART 2 — Enforcement on the LIVE buy path + fail-CLOSED proof

The gate is in the live (`not TEST_MODE`) branch of `_open_position`, the first substantive block, strictly **before** the real on-chain `execute_trade`:

```python
# services/bot_core.py
1023  if TEST_MODE:                       # paper branch → paper_buy() (its own gate)
...
1138  else:                               # LIVE branch (not TEST_MODE)
...
1152      fill_mc_ceiling = float(os.getenv("BOT_CORE_FILL_MC_CEILING_USD", "0"))
1153      if fill_mc_ceiling > 0:
1154          fill_price = await self._get_token_price(mint)
1155          if fill_price <= 0:
1156              logger.warning("FILL_MC_CEILING fail-CLOSED (live): %s — no fill price, skipping buy", mint[:12])
1157              return                   # ← FAIL CLOSED: skip the buy entirely
1158          fill_mc = fill_price * 1_000_000_000
1159          if fill_mc > fill_mc_ceiling:
1160              logger.info("FILL_MC_CEILING reject (live): ...")   # ← reject path
1172              return
1173      result = await execute_trade("buy", token, size_sol, ...)   # ← only reached if gate passes
```

**Fail-CLOSED is real.** `_get_token_price` (`:485-488`) → `_get_token_prices_batch` (`:490-647`) initialises `result={m:0.0}` and only overwrites with *truthy positive* prices (`v_sol>0 and v_tokens>0` `:543`; `if p` `:569`; `if ps` `:629`). Every external call is `try/except…pass` (`:504/515/530/545/575/590/599/632`), so an all-sources-fail mint returns **exactly 0.0** → hits the fail-closed `return`. A propagating exception would abort `_open_position` (no buy) = also closed. The post-fill logged-MC at `:1249` (`_pe_market_cap = price*1e9`) is accounting only — it runs *after* the buy and gates nothing.

This **confirms** `session_outputs/ZMN_LIVE_UNBLOCK_PREP_2026_06_08.md:77` verbatim: *"`BOT_CORE_FILL_MC_CEILING_USD=1000` is active and now fails CLOSED (safety-positive — some live buys skip with a `FILL_MC_CEILING fail-CLOSED` log)."*

**Doc-corpus reconciliation (the "fails CLOSED" claim has a time axis — all docs are consistent once dated):**

- **Born fail-OPEN:** `LIVE_MODE_FILTER_PARITY_001_V2` (2026-05-19) shipped the live gate *without* the `price<=0` short-circuit; its §8/§4 explicitly document live as fail-OPEN and file follow-up `LIVE-PARITY-FAIL-CLOSED-001`.
- **Audited fail-OPEN:** `FULL_CODE_AUDIT_001` **D08-F7** (2026-06-02) correctly flagged "live fill-MC-ceiling gate fails open on a zero price → admits an unbounded-MC live buy." (This is the *only* fill-ceiling finding in the audit; there is **no** D02/D07 MC-gate finding — D02 is live exec/accounting, unrelated.)
- **Patched fail-CLOSED:** `REMEDIATION_PHASE_0_1` §2 #13, commit **`c70aba1`** (2026-06-03) added `if fill_price <= 0: log + return`. The inline comment at `bot_core.py:1148-1150` cites "FIX-SIZING-CAPS (#13, D08-F7): this gate now FAILS CLOSED."
- **Current = fail-CLOSED.** The 2026-06-08 unblock-prep and `FLIP_READINESS` (2026-06-03) descriptions are accurate as-of-now. D08-F7's fail-open call is *historically correct, currently superseded*.

**One doc error worth recording:** `LIVE_MODE_FILTER_PARITY_001_V2` §8 row-136 describes the live pipeline as "Jupiter primary, Redis-cached fallback." The code is the **reverse** — `_get_token_prices_batch` is **Redis-first** (STEP1 `token:latest_price` PumpPortal stream → STEP2 Redis BC reserves → STEP3 Jupiter → STEP5 Gecko). The doc's "pipelines diverge" conclusion is right but its ordering is inverted and its lifecycle-anchor divergence (paper signal-time BC vs live fill-time stream) is understated.

The SA Gate 1 fails **OPEN** by design (`SD_MC_CEILING_002_DEPLOY` §3.2/§3.3); the bot_core fill ceiling is precisely the fill-time backstop for the in-flight pump Gate 1's signal-time view cannot see (`paper_trader.py:247-252` comment). A 1k–3k signal passing Gate 1 is reliably caught by Gate 3.

---

## PART 3 — THE CRUX: does the live fill-ceiling MC equal paper's `market_cap_at_entry`?

### 3.1 Formula — **MATCH** (no denomination bug)

| Site | Code | Supply | Denomination |
|---|---|---|---|
| Paper logged column | `market_cap = entry_price * 1_000_000_000` (`paper_trader.py:287`) | 1e9 | USD |
| Paper gate | `fill_mc = entry_price * 1_000_000_000` (`:255`) | 1e9 | USD |
| Live gate | `fill_mc = fill_price * 1_000_000_000` (`bot_core.py:1158`) | 1e9 | USD |
| Live logged column | `_pe_market_cap = price * 1_000_000_000` (`:1249`) | 1e9 | USD |

Both pipelines yield **USD per token**: paper's `_get_token_price` returns Jupiter `usdPrice`/Gecko `price_usd` (already USD), BC fallback `bonding_curve_price` is `bc_price_usd` (already `×sol_price`); live's `_get_token_prices_batch` reads `token:latest_price` as **SOL/token** and converts to USD at **STEP 4** (`result = sol_price_per_token * sol_usd`, `:603-614`) using `market:sol_price`. So `fill_mc` is a genuine USD market cap vs the USD ceiling. **Same supply constant, same denomination, no rounding in the compare path.** ✅

**Critically, paper's `market_cap_at_entry` IS the gate quantity.** The DB verified `market_cap_at_entry == entry_price × 1e9` *exactly* (to <0.01 on every sampled row). So the column the 91% was measured on is the identical formula the gate enforces — the gate is not testing some unrelated number.

### 3.2 Price source — **DIVERGES** (different pipeline, different lifecycle anchor)

| | Paper (`paper_trader._get_token_price`, `:96-139`) | Live (`bot_core._get_token_prices_batch`, `:485-647`) |
|---|---|---|
| Primary | **Jupiter v3** (USD) | **Redis `token:latest_price`** = PumpPortal **fill-time** stream (SOL→USD) |
| 2nd | GeckoTerminal (USD) | Redis `token:reserves` BC (fill-time) |
| 3rd / fallback | **signal-time `bonding_curve_price`** (from `raw.vSolInBondingCurve` at discovery, `bot_core.py:1028-1033`) | Jupiter → Gecko |
| Redis read? | **No** | **Yes, first** |
| Slippage on gate input? | **Yes** — `entry_price = price*(1+slippage/100)` (`:245`) feeds both gate & logged column | **No** — gate uses raw `fill_price`; real slippage happens later in `execute_trade` |

For the **sub-$1k population** (all fresh pre-grad, `bonding_curve_progress ≈ 0.36` per probe), Jupiter/Gecko frequently have no route, so **paper's primary misses and it falls back to the signal-time BC anchor**, while **live reads the fill-time PumpPortal stream**. These are different prices for the same token at different moments — the divergence the live gate was *designed* to exploit (catch the in-flight pump), now operating *against* clean paper→live comparability.

**Slippage asymmetry (quantified):** SD tiers (`SLIPPAGE_RANGES`): alpha_snipe `(3,12,0.7)`, confirmation `(2,8,0.7)`, `REF=0.1 SOL`. At flip sizing 0.10 SOL, `size_factor=1.0` → base slippage 3–12% / 2–8%. Paper's gate uses the inflated price; live's uses raw. So at the boundary, **live is slightly *more permissive*** — it admits tokens whose **raw** MC ∈ `[1000/(1+s/100), 1000]` (≈ **$893–1000** at alpha_snipe max, **$926–1000** at confirmation max) that paper's inflated-price gate rejects. **Note:** the prompt's hypothesised "drift admits 1k–3k losers via the fill gate" is **not** the mechanism — *both* fill gates hard-reject all raw MC > $1000; the 1k–3k zone is only Gate-1 (SA) territory. The real exposure is the thin **just-under-$1000** slice, which sits **inside the already-losing 800–1000 fringe**.

### 3.3 Lifecycle timing — paper signal-time-anchored (for the dominant case), live fill-time

Both gates fire at "fill" in their own runtime, **but** the *price each consumes* anchors differently: live's primary is the continuously-updated fill-time stream; paper's effective anchor for fresh pre-grad tokens is the **signal-time** BC reserve snapshot (Jupiter/Gecko miss → fallback). The gate's own comment (`bot_core.py:1142-1143`) — "catches the in-flight pump the signal-time SA gate structurally cannot see" — encodes the designers' belief that **fill-time MC > signal-time MC** on average for these tokens, i.e. live will tend to **reject** marginal tokens paper's signal-time anchor admitted (conservative lean). But the retrace path also exists: a token whose signal-time anchor was elevated and whose fill-time stream has dipped below $1000 would be **admitted** by live where paper rejected — and `$1000–3000` is ≈0% WR, so the down-drift path pulls in near-certain losers. **Drift is two-sided.**

### 3.4 The DB band distribution — reproduces 91%, exposes the cliff

SD paper, closed (`personality='speed_demon' AND trade_mode='paper' AND realised_pnl_sol IS NOT NULL`), n=4468 all-time:

| Proxy-MC band (`market_cap_at_entry`) | n | WR | Total PnL (SOL) |
|---|---:|---:|---:|
| `<$500` | 650 | **99.85%** | +101.62 |
| `$500–800` | 1978 | **97.93%** | +94.14 |
| `$800–1000` (fringe) | 262 | **26.72%** | −5.97 |
| `$1000–1500` | 75 | 0.00% | −1.72 |
| `$1500–3000` | 1160 | 0.26% | −19.92 |
| `>$3000` | 343 | 0.00% | −21.71 |
| `(null/0)` | 0 | — | 0 |

- **Reproduces the 91% claim:** sub-$1k aggregate **n=2890, WR 91.90%, +189.79 SOL** ✅. The cited `<1k AND ML≥65 = 92.3%` reproduces as **n=1724, 92.58%** (`ml_score == ml_score_at_entry` on this slice, so the column choice is moot).
- **800–1000 fringe = 262 rows = 9.07% of the sub-$1k band, and is ALREADY a loss zone (26.72% WR, −5.97 SOL).** This is the band the $1000 ceiling straddles and the zone maximally exposed to signal→fill drift.
- **The cliff:** WR is a near-vertical step in the proxy — 99.85% → 97.93% → **26.72% → ~0%**. The collapse coincides with `entry_price` crossing ~`1e-6` (proxy MC ~$1000). The `≥$1500` mass (1503 rows ≈ 0% WR) is **historical** — booked before `BOT_CORE_FILL_MC_CEILING_USD=1000` confined the population.
- **Paper is currently confined to <$1k:** **0** SD paper rows with `market_cap_at_entry ≥ 1000` in the last 14d (and 7d) — paper reads the *same* `BOT_CORE_FILL_MC_CEILING_USD` env, so paper's current population *is* what paper currently books. (369 over-$1k rows exist in the 30d window but are all >14d old.)

### 3.5 The proxy-vs-true-MC scale finding (why "sub-$1k" is misleading)

`market_cap_at_entry` (≈ $500 typical) is **not** the token's true market cap. `features_json.market_cap_usd` — the signal-time enrichment MC — is a **structurally different, ~8.25× larger** number (median **$5,172**; 100% of "sub-$1k-logged" rows have a true MC > $3,000). They differ by construction (a within-$50 comparison yields 0%), so the DB **cannot** measure gate-quantity drift on the same scale, and **paper's per-row fill-price source / BC-fallback price is not logged** — so the live-vs-paper price drift **cannot be empirically bounded from the DB alone**.

The consequence is the load-bearing one: **the 91% sub-$1k WR is the fill ceiling selecting the *winning side of its own price proxy*.** Because `market_cap_at_entry = entry_price × 1e9` and `realised_pnl_sol ≈ (exit/entry − 1)×amount − fees`, a *low* `entry_price` (low proxy MC) makes "exit > entry" near-trivial → near-100% WR, and a *high* `entry_price` makes it near-impossible → ~0% WR. The band is **mechanically correlated with WR through the shared `entry_price` term**. That is an entry-*price*-selection effect, **not** evidence that genuinely-small-MC tokens win. Whether it transfers to live therefore hinges on **live reproducing paper's low entry prices** — and live's fill-time stream pipeline (which sees in-flight pumps paper's signal-time anchor misses) may systematically enter *higher*, degrading both the admit-set and the per-trade outcome.

---

## PART 4 — Reconcile to the measured edge

**Does "live rejects MC ≥ 1000" map onto "paper's `market_cap_at_entry` < 1000 = the 91% band"?**

- **Formula + gate-quantity identity:** YES. Live's gate tests the same `price×1e9` quantity that defines paper's band. The $1000 ceiling means the same *kind* of boundary in both. ✅
- **Population identity:** **NO — shifted by drift.** The price *input* to that identical formula comes from divergent pipelines (live=fill-time Redis stream; paper=Jupiter/Gecko→signal-time-BC) plus a paper-only slippage inflation. So the live-admitted set = the paper band ± signal→fill drift, with the divergence concentrated at the $1000 cliff (the 9.07% fringe that is *already* a loss zone). Drift direction is two-sided and **not bounded from the DB**. The deep-`<$500` core (99.85% WR) is far enough below the ceiling that plausible drift can't span the gap, so *that subset's population* transfers — but its WR is still entry-price-conditioned.
- **Edge identity:** **NO — proxy-bounded.** The 91% is a gate proxy-selection artifact tied to the `entry_price` term, not a validated small-MC edge. It transfers only insofar as live reproduces paper's low entry prices, which is exactly what the pipeline divergence puts at risk.

**Characterisation:** the live population is the 91% band **shifted by the signal→fill drift and re-weighted by whatever entry-price regime the live fill-time pipeline produces.** Lean is *probably* conservative on the admit/reject axis (fill-time pumps push marginal tokens above $1000 → live rejects paper-winners) but *adverse* on the per-trade-outcome axis (higher live entries erode the entry-price selection that the 91% rests on). The net is **not predictable from paper or static analysis** — it is the canonical paper→live edge-retention question that only live data resolves.

---

## §5 What this does and does not clear for the flip

**Cleared (gate is safe):** live MC gate fails CLOSED on unpriceable tokens; formula is clean (no denomination/supply bug); effective binding cap is $1000; the gate is the in-flight-pump backstop for SA's fail-open; both ceilings are stable across the §6 flip-config. There is **no SOL-leak path** through the MC gate.

**Not cleared (edge is a hypothesis):** the 91% sub-$1k WR is **bounded by a fill-ceiling proxy-selection artifact and an un-measurable paper→live price drift**, concentrated at a near-vertical WR cliff whose admit/reject boundary sits inside an already-losing fringe. **Do not treat the 91% as a confirmed live edge** in any sizing or go/no-go decision. This is consistent with — and a concrete instance of — `docs/findings/COST_FIDELITY_GAP.md`: the gap can only be closed with Path-B live data.

## §6 Residual risks & recommended follow-ups (no action taken — read-only)

1. **🟠 ENV-DISABLE hole (config fail-open).** `bot_core.py:1153` `if fill_mc_ceiling > 0:` — setting `BOT_CORE_FILL_MC_CEILING_USD=0` (the advertised no-redeploy rollback) silently disables the *entire* gate, re-opening the unbounded-MC live-buy path with no fail-closed protection. Currently 1000 (safe) and untouched by the flip-config, but nothing self-protects against a 0. *Follow-up: treat zeroing this var as a guarded operation; consider a startup assert in any live-only hardening pass.*
2. **🟠 No lower price-sanity bound.** A tiny-but-positive garbage price (e.g. `sol_usd` flooring to 80.0 at `:593` × a stale micro stream price) sails under the $1000 ceiling and is admitted as a legit micro-cap. Not a ceiling-gate defect, but a distinct admit-garbage risk with no floor. *Follow-up: optional price-sanity floor.*
3. **🟠 Drift is un-instrumented.** `features_json` logs true MC + `bonding_curve_progress` but **not** paper's per-row fill-price source or the BC-fallback `bc_price_usd`, so the paper→live gate-quantity drift cannot be bounded. *Follow-up (the high-value one): log **both** the live `fill_price` (gate quantity) and the signal-time BC anchor per live trade — ties into OBS-011 / SLIPPAGE-CALIBRATION-001 — to empirically bound drift once live data accrues.*
4. **🟠 Edge-validation owed.** A dedicated session should test whether the WR-vs-proxy cliff is a genuine entry-timing edge or a `entry_price`-denominator PnL artifact (note the cliff coincides with the historical `1e-6` sentinel territory called out in `bot_core.py:1181-1209` / CLAUDE.md). *Follow-up: `ML-/EDGE-PROXY-ARTIFACT-EVAL-001`.*

## §7 Method / verification provenance

- Static trace: direct reads of `paper_trader.py:38-310`, `bot_core.py:485-647, 880-1000, 1000-1300, 1152-1172`, `signal_aggregator.py:50-56, 1845-1879`.
- Deployed env: `railway variables -s bot_core / signal_aggregator / Postgres` (live, this session).
- DB: read-only asyncpg over `DATABASE_PUBLIC_URL` (SELECT-only; n=4468 closed SD paper rows; bands sum exactly).
- 6-agent verification workflow `wf_09a737b8-a35` (Empirics → adversarial Verify → Critic): DB band/fringe/drift agent; code-gate-completeness (Explore) agent; prior-doc-claims agent; three adversarial verifiers (fail-closed = *confirmed*; formula-match = *partial*; source-timing-drift = *partial*). The completeness-critic agent returned empty (no result) — its role is covered by §6 above.
- Verifier nuances incorporated: the prompt's hypothesised drift direction (admit 1k–3k losers via the fill gate) was **corrected** — both fill gates hard-reject raw MC > $1000; the real margin is the just-under-$1000 slip slice. The proxy-vs-true-MC scale finding (§3.5) was surfaced by the DB agent and is the most consequential output.
