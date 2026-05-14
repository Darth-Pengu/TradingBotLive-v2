# LIVE-MODE-FILTER-PARITY-001 — Audit

**Date:** 2026-05-14
**Type:** Investigation → conditional fix → conditional deploy. **Outcome: STOP-C — SCOPING NEEDED.**
**Trigger:** NO_MOMENTUM_90S_AUDIT_001 §10 open item — *"services/execution.py does not have the F1 gate; if/when live trading resumes the gate must be replicated there."*
**Code changed:** none. **Env changed:** none. **Redis writes:** none. **Deploy:** none.

---

## §1 Verdict

**STOP-C — SCOPING NEEDED.** The live execution path cannot take a clean single-gate port of
the C1 fill-time MC ceiling. Two STOP-C triggers from the session prompt both apply: (1) the
live buy path dispatches to **3 execution routes**; (2) it has **no fill-time price
computation**, so there is no insertion point analogous to `paper_trader.paper_buy` — which
gates on a fill-time `entry_price` it computes itself. A scoping doc is produced
(`.tmp_live_filter_parity/02_design.md`); a follow-up session **LIVE-MODE-FILTER-PARITY-001-V2**
is recommended. **This remains a V5A relaunch blocker.**

STOP-A (gate already present) and STOP-B (routing assumption wrong) both **did not fire** —
investigation confirmed neither.

## §2 Investigation findings

### Routing — confirmed, STOP-B does not fire
`services/execution.py` is the **LIVE path only**.
- `bot_core.py:82-83` — `paper_buy` is imported (exists) only under `if TEST_MODE`.
- `bot_core.py:836` `if TEST_MODE:` → `paper_buy(...)` (L848); `bot_core.py:948` `else:` →
  `execute_trade(...)` (L950-953).
- Every network call in `execution.py` is guarded by `if TEST_MODE: return "TEST_MODE_..._TX"`
  before signing/sending.
Changing `execution.py` does not affect paper trading or the May 27 SD validation.

### Gate presence — none, STOP-A does not fire
`execution.py` (816 lines) read end-to-end. **No market-cap ceiling check anywhere** in the
live buy path. The entry point `execute_trade()` (L666) selects among
`_execute_pumpportal_local` / `_execute_pumpportal` / `_execute_jupiter` inside a retry loop.
`execution.py` reads config via `os.getenv` directly — it *could* read
`BOT_CORE_FILL_MC_CEILING_USD` the same way `paper_trader.py` does.

### The C1 gate being mirrored — `paper_trader.py:247-275`
The paper C1 gate computes `fill_mc = entry_price * 1_000_000_000`, where `entry_price` is the
**fill-time** price (`_get_token_price(mint)` → Jupiter/Gecko, BC fallback, × `(1+slippage/100)`).
If `fill_mc > BOT_CORE_FILL_MC_CEILING_USD` (default `0` = disabled; currently `1000`): logs
`FILL_MC_CEILING reject: ...`, increments Redis `bot:filter:fill_mc_ceiling:rejects:<UTC-date>`
(14d TTL), returns `{"success": False, "error": "fill_mc_ceiling_exceeded"}`.

C1's entire value (per NO_MOMENTUM_90S_AUDIT_001 §1, STOP_LOSS_20_RUG_INVESTIGATION_001) is that
it re-checks MC **at fill time** — catching the in-flight pump that the signal-time SA gate
`SD_MC_CEILING_USD` structurally cannot see (BC reserves in `raw_data` are frozen at
PumpPortal-publish time, ≈$2,400 fresh-mint, always pass).

## §3 Why no clean port exists (the STOP-C reasoning)

The session prompt §4.3 requires **MC-computation parity**: paper and live must gate on the same
MC definition. The paper definition is **fill-time** `entry_price × 1e9`.

Inside `execute_trade`, the only MC value reachable is `token.liquidity_usd`
(= `features["market_cap_usd"]` set at `bot_core.py:827`) — a **signal-time** value computed
upstream at signal_aggregator. `execution.py` **never computes a price for buys**: it receives
unsigned tx bytes from PumpPortal/Jupiter and returns a signature; bot_core fetches the price
*after* execution (`bot_core.py:956`).

Therefore a gate placed inside `execute_trade` on `token.liquidity_usd` would:
- **not** mirror C1 (signal-time ≠ fill-time MC definition — fails §4.3);
- be largely **redundant** with the SA `SD_MC_CEILING_USD` gate, which already runs in live mode
  and is also signal-time — it would add a second signal-time gate, not the missing fill-time one;
- be a "half-applied fix wearing C1's name" — precisely what STOP-C instructs not to force.

A 5-line insertion is *physically* possible; **parity** is not achievable inside `execution.py`
without adding a price-fetch dependency the live path does not currently have.

## §4 Implementation + verify output

No implementation this session — STOP-C precludes it. `verify_execution_gate.py` was **not**
written: per the multi-loop test pattern and STOP-D, an unvalidated/half-applied gate must not
be produced. The development loop was not entered because Phase 2 design terminated at STOP-C
before any code path was selected.

## §5 Deploy record

None. No code change, no env change, no redeploy. Bot remains `TEST_MODE=true`,
`BOT_CORE_FILL_MC_CEILING_USD=1000` on bot_core (unchanged from C1 deploy 2026-05-13).

## §6 Verification standard note

This session is read-only investigation; the verification standard is **code-level**:
`execution.py` was read in full and confirmed to contain no MC gate; routing was traced through
`bot_core.py` import/branch structure. No production behaviour was observed or changed. Because
no gate was implemented, there is nothing to validate against live or paper traffic.

## §7 V5A relaunch implications

**This is a V5A relaunch blocker and remains open.** When V5A flips `TEST_MODE=false` on
bot_core, the live buy path (`execution.py`) has **no fill-time MC ceiling**. The SA
`SD_MC_CEILING_USD` gate ($3,000, signal-time) still runs, but it is exactly the gate C1 was
built to backstop — it cannot see the 1-15s in-flight pump that pushes a $2,400 fresh-mint
fill into the $1k-$3k (or higher) dead zone. A live relaunch today reintroduces the $1k-$3k
fill-time bleed C1 just eliminated on the paper path, amplified by the live position-size
factor (`MAX_POSITION_SOL` up to 0.25 vs paper's same — but on real SOL).

**Recommended follow-up: LIVE-MODE-FILTER-PARITY-001-V2**, scoped to **Option A** (see
`.tmp_live_filter_parity/02_design.md`): gate in the `bot_core.py` live buy branch *before*
`execute_trade`, using the existing `self._get_token_price(mint)` helper to compute a
fill-time `fill_mc = price * 1e9`, mirroring `paper_buy`'s env var, reject-log, and Redis-counter
pattern exactly. This is the only option delivering true fill-time parity, reuses an existing
helper, and keeps one env var (`BOT_CORE_FILL_MC_CEILING_USD`) governing paper and live.
It requires explicit authorization to touch the `bot_core.py` live branch (this session was
scoped to `execution.py` only). V2 should be added as a V5A precondition.

Options B (price fetch inside execution.py) and C (signal-time gate as insurance only) are
documented in the scoping doc as inferior alternatives.

## §8 Open questions

1. **Does V2 get authorization to edit `bot_core.py`'s live branch?** Option A is the clean
   mirror but is outside this session's `execution.py`-only scope. Jay decision.
2. **V5A sequencing** — V2 should land before any `TEST_MODE=false` flip. Add to §6 V5a
   preconditions in AGENT_CONTEXT?
3. **Other paper/live parity gaps** — this session did not audit for *other* gates present in
   the paper path but absent in live. A dedicated parity sweep (paper_trader vs execution.py +
   bot_core live branch) may be worthwhile as a separate read-only session. Not done here per
   scope discipline (§8 of the prompt).
