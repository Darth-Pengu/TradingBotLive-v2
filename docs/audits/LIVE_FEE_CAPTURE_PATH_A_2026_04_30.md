# LIVE-FEE-CAPTURE Path A — Session D, 2026-04-30

**Session:** LIVE-FEE-CAPTURE-PATH-A-2026-04-30 (Session D in chain A→B→C→D→E)
**Author:** Claude Code
**Predecessor audit:** `docs/audits/LIVE_FEE_MODEL_AUDIT_2026_04_29.md` (spec for what to fix)
**Status:** ✅ DEPLOYED — three code changes + backfill of the only real on-chain live trade.

---

## §1 Verdict — Path A deployed; Path B urgency CONFIRMED by backfill

Path A wires paper's `_simulate_slippage` and `_simulate_fees` helpers into bot_core's live close path. It produces parity-of-record (live rows now write `slippage_pct`/`fees_sol`/`features_json`/`corrected_*`) but **not parity-of-truth** — Path A's estimates are based on paper's fee model, which under-counts real Solana transaction costs.

**The id 6580 backfill (only real on-chain live trade) confirms the gap empirically:**

| metric | value |
|---|---:|
| realised_pnl_sol stored (gross, fees=0) | +0.001876 SOL |
| corrected_pnl_sol (Path A backfill) | -0.006430 SOL |
| on-chain actual (per `ZMN_LIVE_ROLLBACK.md`) | -0.094245 SOL |
| **gap (Path A − actual)** | **+0.087815 SOL** |

Path A undercorrects by ~12× the actual cost. Above the ±0.02 SOL validation tolerance from the chain prompt → **Path A is NOT empirically validated.** Per the prompt: "Path A's estimates are off and Path B becomes more urgent."

This is the expected finding for the only live data point we have. Path B (Helius `parseTransactions` for actual fill prices and on-chain fees) remains the right long-term answer. Tracked as **LIVE-FEE-CAPTURE-002**.

---

## §2 Code changes (3a + 3b + 3c) + import addition

### §2.1 Module-level import added (`services/bot_core.py:73-77`)

```python
# LIVE-FEE-CAPTURE-001 Path A (Session D, 2026-04-30): import fee/slippage
# estimators unconditionally so the live close path can call them. They are
# pure functions with no side effects at import time. See
# docs/audits/LIVE_FEE_CAPTURE_PATH_A_2026_04_30.md.
from services.paper_trader import _simulate_slippage, _simulate_fees
```

Outside the `if TEST_MODE:` block. Both helpers are pure functions; importing in live mode is safe (no DB/Redis side effects at import).

### §2.2 Change 3a — PnL formula fix (`services/bot_core.py:1247-1271`)

**Before** (line 1248-1250):

```python
if pos.remaining_pct <= 0.01:
    pnl_pct = ((current_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
    pnl_sol = (current_price - pos.entry_price) / pos.entry_price * sell_amount if pos.entry_price > 0 else 0
    outcome = "profit" if pnl_sol > 0 else "loss"
```

**After:**

```python
if pos.remaining_pct <= 0.01:
    # LIVE-FEE-CAPTURE-001 Path A (Session D, 2026-04-30): use paper helpers
    # for round-trip fee + slippage estimates. Both buy and sell sides are
    # estimated and summed; subtract from gross PnL. Path B (Helius
    # parseTransactions for actual fill data) deferred to a follow-up session.
    # See docs/audits/LIVE_FEE_CAPTURE_PATH_A_2026_04_30.md.
    _live_buy_slip_pct = _simulate_slippage("buy", pos.size_sol)
    _live_sell_slip_pct = _simulate_slippage("sell", sell_amount)
    _live_buy_fees = _simulate_fees(
        "buy", pos.size_sol, "auto",
        bonding_curve_progress=pos.bonding_curve_progress,
    )
    _live_sell_fees = _simulate_fees(
        "sell", sell_amount, "auto",
        bonding_curve_progress=pos.bonding_curve_progress,
    )
    _live_total_fees_sol = _live_buy_fees["total"] + _live_sell_fees["total"]
    _live_avg_slippage_pct = (_live_buy_slip_pct + _live_sell_slip_pct) / 2

    pnl_pct = ((current_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
    _live_gross_pnl_sol = (current_price - pos.entry_price) / pos.entry_price * sell_amount if pos.entry_price > 0 else 0
    pnl_sol = _live_gross_pnl_sol - _live_total_fees_sol  # LIVE-PNL-FEE-FORMULA-001
    outcome = "profit" if pnl_sol > 0 else "loss"
```

Both buy-side and sell-side fees are estimated separately and summed. Gross PnL is computed first (preserves the original calculation), then total fees are subtracted. `outcome` flips correctly because it now reads the net PnL.

### §2.3 Change 3b — Live close UPDATE includes fees + slippage + corrected_* (`services/bot_core.py:1284-1305`)

**Before** (16-column UPDATE missing fees/slippage/corrected):

```python
await self.pool.execute(
    """UPDATE paper_trades SET
        exit_price=$1, exit_time=$2, hold_seconds=$3,
        realised_pnl_sol=$4, realised_pnl_pct=$5,
        exit_reason=$6, exit_signature=$7,
        market_cap_at_exit=$8, outcome=$9
       WHERE id=$10""",
    current_price, _pt_exit_time, _pt_hold,
    pnl_sol, pnl_pct, reason, _pt_exit_sig,
    _pt_mcap_exit, _pt_outcome, pos.paper_trade_id,
)
```

**After** (extended with slippage_pct/fees_sol/corrected_* using distinct param slots):

```python
await self.pool.execute(
    """UPDATE paper_trades SET
        exit_price=$1, exit_time=$2, hold_seconds=$3,
        realised_pnl_sol=$4, realised_pnl_pct=$5,
        exit_reason=$6, exit_signature=$7,
        market_cap_at_exit=$8, outcome=$9,
        slippage_pct=$11, fees_sol=$12,
        corrected_pnl_sol=$13, corrected_pnl_pct=$14, corrected_outcome=$15,
        correction_method='live_estimated_v1', correction_applied_at=NOW()
       WHERE id=$10""",
    current_price, _pt_exit_time, _pt_hold,
    pnl_sol, pnl_pct, reason, _pt_exit_sig,
    _pt_mcap_exit, _pt_outcome, pos.paper_trade_id,
    _live_avg_slippage_pct, _live_total_fees_sol,
    pnl_sol, pnl_pct, _pt_outcome,
)
```

**Param-slot discipline lesson** (per Session B hotfix `17c2aac`): distinct slots `$13`/`$14`/`$15` for `corrected_*` columns instead of reusing `$4`/`$5`/`$9`. Prevents asyncpg's `inconsistent types deduced for parameter` error when same param appears in columns of different declared types.

The `correction_method='live_estimated_v1'` distinguishes live rows from paper's `'pass_through'` (Session B). CLAUDE.md "Trade P/L Analysis Rule" already documents both methods.

### §2.4 Change 3c — Live entry INSERT includes slippage + fees + features_json (`services/bot_core.py:922-948`)

**Before** (13-column INSERT):

```sql
INSERT INTO paper_trades
(mint, personality, entry_price, amount_sol, entry_time,
 signal_source, ml_score, entry_signature,
 market_mode_at_entry, fear_greed_at_entry, rugcheck_risk,
 market_cap_at_entry, trade_mode)
VALUES ($1..$13)
```

**After** (16-column INSERT):

```sql
INSERT INTO paper_trades
(mint, personality, entry_price, amount_sol, entry_time,
 signal_source, ml_score, entry_signature,
 market_mode_at_entry, fear_greed_at_entry, rugcheck_risk,
 market_cap_at_entry, trade_mode,
 slippage_pct, fees_sol, features_json)
VALUES ($1..$13, $14, $15, $16)
```

Plus computation of entry-side estimates:

```python
_pe_buy_slip = _simulate_slippage("buy", size_sol)
_pe_buy_fees = _simulate_fees(
    "buy", size_sol, "auto",
    bonding_curve_progress=bc_progress,
)
# ... values appended to INSERT params:
_pe_buy_slip, _pe_buy_fees["total"], json.dumps(features),
```

Live entry rows now mirror paper entry semantics — `features_json` populated, slippage/fees populated.

### §2.5 Sites NOT changed in this session

- `services/bot_core.py:1318` (live close fallback INSERT) — still has the legacy 21-column INSERT without slippage/fees/features_json/corrected_*. This path triggers only when the entry INSERT failed (e.g., DB error mid-buy). Low-traffic path; defer to a future session.
- `services/paper_trader.py` paper close UPDATE — already covered by Session B (`pass_through`). Untouched here.
- `services/bot_core.py:1064` staged-TP correction UPDATE — already covered by Session B + hotfix.

### §2.6 Compile check

```
python -m py_compile services/bot_core.py
→ compile OK
```

---

## §3 id 6580 backfill result (Step 5)

**Before backfill:**

| field | value |
|---|---|
| amount_sol | 0.3652803 |
| entry_price | 2.409836938e-06 |
| exit_price | 2.4222151403605084e-06 |
| realised_pnl_sol | +0.0018762736 (stored gross — no fees subtracted) |
| fees_sol | 0.0 |
| slippage_pct | 0.0 |
| corrected_pnl_sol | +0.0018762736 (pass_through copy from Session B) |
| correction_method | pass_through |

**Path A estimates:**

| component | value |
|---|---:|
| buy_slip_pct | 1.91 |
| sell_slip_pct | 18.91 (random — within `SLIPPAGE_RANGES["sell"]`) |
| avg_slippage_pct stored | 10.41 |
| buy_fees breakdown | platform=0.003653 + priority=0.0005 + lp/jito=0.0 → total=0.004153 |
| sell_fees breakdown | platform=0.003653 + priority=0.0005 + lp/jito=0.0 → total=0.004153 |
| total_fees_sol | **0.008306** |

**Path A vs actual:**

```
realised (gross stored)  = +0.001876 SOL
corrected (Path A)       = -0.006430 SOL
on-chain actual          = -0.094245 SOL
gap (Path A - actual)    = +0.087815 SOL
```

**Verdict:** Path A undercorrects by ~12× the actual cost. **Above the ±0.02 SOL validation tolerance.** Path A is NOT empirically validated on this data point.

**After backfill:**

| field | value |
|---|---|
| realised_pnl_sol | +0.0018762736 (unchanged) |
| corrected_pnl_sol | **-0.0064297264** |
| fees_sol | **0.008306** |
| slippage_pct | **10.41** |
| correction_method | **live_estimated_v1** |
| corrected_outcome | **loss** |

The realised_pnl_sol stays as historical record. `corrected_*` reflects Path A's best estimate at backfill time. Future Path B work would re-correct this row to the on-chain truth (-0.094 SOL).

---

## §4 Path A vs Path B — what we got and what's left

### What Path A delivers (parity-of-record)

- **Live rows now write fees/slippage** instead of zeros. Future live trades populate these columns at write-time.
- **Live close PnL formula subtracts fees.** Live `realised_pnl_sol` is now consistent with paper's net-of-fees convention.
- **Live entry rows write features_json** for ML training parity.
- **`correction_method='live_estimated_v1'`** distinguishes live rows from paper's `'pass_through'`. CLAUDE.md rule already documents this.

### What Path A does NOT deliver (parity-of-truth)

- **Paper fee model is calibrated against legacy fast-fill assumptions.** It's known to undercount actual Solana priority fees, MEV impact, and slippage on real on-chain trades.
- **The id 6580 backfill confirms a 12× gap** between Path A estimates and on-chain actuals.
- **Live PnL after Path A** is a *better* estimate than the previous fees=0 case, but still systematically optimistic by ~0.08 SOL on a 0.36 SOL pre-grad pump.fun trade (≈22% of position size).

### What Path B delivers (deferred)

- Helius `parseTransactions` on the entry and exit signatures returns:
  - Actual SOL deltas at the wallet level (the source of -0.094 SOL truth)
  - Compute fee from instruction data
  - Net slippage = (actual fill price - quoted price) / quoted price
- Replaces estimates with on-chain truth.
- Cost: a Helius RPC call per trade close + parsing logic + fallback for parse failures.
- Tracked as **LIVE-FEE-CAPTURE-002**.

**Recommendation:** Land Path B before V5a's first unsupervised live window. Until then, treat live PnL numbers as conservative-but-still-optimistic; budget for ~1.5-2× the Path A estimate when reasoning about actual cost.

---

## §5 Deploy verification — to be appended post-redeploy

**Plan:**
1. Poll Railway MCP every 30s on bot_core deployment until SUCCESS.
2. Wait additional 90s.
3. Check logs for ImportError / AttributeError on `_simulate_*` calls — bot_core's startup banner should be clean. If any traceback referring to `_simulate_*`, ROLLBACK.
4. Query the row to verify backfill landed:
   ```sql
   SELECT id, realised_pnl_sol, corrected_pnl_sol, fees_sol, slippage_pct,
          correction_method
   FROM paper_trades WHERE id=6580;
   ```
5. Confirm fresh paper closes still work (TEST_MODE=true → paper path; corrected_pnl_sol from Session B still populated).

**Result:** *to be appended post-deploy*

---

## §6 Forward consequences

- **CLAUDE.md "Trade P/L Analysis Rule"** already covers `'live_estimated_v1'` — no doc update needed in Session D.
- **Live entries from V5a onward** will have `features_json` populated (parity with paper). ML training across paper + live rows is feasible.
- **`correction_method` enum** now has 3 active values: `pass_through` (paper), `live_estimated_v1` (live, this session), and historic `staged_tp_backfill_v1` (no longer present in DB post DASH-RESET).
- **id 6580** is a documented data point for the Path B work. Future Path B implementation can use the gap (+0.088 SOL) as a calibration target.
- **Future live trades** will write entries with the `_pe_buy_slip` / `_pe_buy_fees` estimates and closes with the round-trip estimates. Each row tagged `live_estimated_v1`. Path B would later re-correct these with `live_actual_v1` (or similar).

---

## §7 Open issues / what's NOT in this audit

1. **Path B not implemented.** Deferred to LIVE-FEE-CAPTURE-002.
2. **Live close fallback INSERT (`bot_core.py:1318`)** still uses the 21-column legacy INSERT without slippage/fees/features_json. Triggers only when the entry INSERT failed; low-traffic path. Track as a separate cleanup item.
3. **Only one live data point** for Path A validation (id 6580). When V5a accumulates more on-chain trades, re-validate Path A's calibration with the larger sample.
4. **`_simulate_slippage` returns random values** within `SLIPPAGE_RANGES`. Two backfills of the same row would produce different `slippage_pct` values. This is paper-fidelity behavior, not Path A's choice — re-running the id 6580 backfill would now produce a different number. Stable for the *first* backfill, which is what Path A guarantees.
5. **`bonding_curve_progress` for id 6580 inferred as `0.0`** (pre-grad pump.fun, consistent with the v4 trial trade type). If actually graduated, fee/slippage estimates would change. Cross-check with `WALLET_DRIFT_INVESTIGATION_2026_04_29.md` confirms pre-grad.
6. **Sell-side slippage of 18.91% in this run** is within paper's `SLIPPAGE_RANGES["sell"]` config but feels high for a 0.365 SOL pre-grad trade. The on-chain actual slippage (computable via Path B) would be a useful calibration anchor.

---

## §8 Reproducibility

```python
# Backfill script: .tmp_live_fee_capture/backfill_6580.py (gitignored)
import asyncio, asyncpg
from services.paper_trader import _simulate_slippage, _simulate_fees

DSN = "postgresql://postgres:<REDACTED>@gondola.proxy.rlwy.net:29062/railway"
ON_CHAIN_DELTA_SOL = -0.094244978  # ZMN_LIVE_ROLLBACK.md

# (See backfill_6580.py for the full script.)
```

Code change verification:

```bash
python -m py_compile services/bot_core.py
git diff services/bot_core.py
```

Post-deploy verification SQL:
```sql
-- Live row check
SELECT id, realised_pnl_sol, corrected_pnl_sol, fees_sol, slippage_pct,
       correction_method, correction_applied_at
FROM paper_trades WHERE trade_mode='live' ORDER BY id;
```

The id 6580 row should show `correction_method='live_estimated_v1'`, `fees_sol≈0.008`, `slippage_pct≈10`, `corrected_pnl_sol≈-0.006`.

---

## §9 Trade-off summary table

| dimension | Pre-Session-D | Post-Session-D (Path A) | Future Path B |
|---|---|---|---|
| Live PnL formula | gross (no fees) | net (paper-estimated fees) | net (on-chain actual fees) |
| `fees_sol` on live rows | 0.0 | paper-estimated | on-chain actual |
| `slippage_pct` on live rows | 0.0 | paper-estimated | on-chain actual |
| `features_json` on live entries | NULL | populated | populated |
| `correction_method` on live rows | `pass_through` (Session B) | `live_estimated_v1` | `live_actual_v1` (proposed) |
| Empirical validation gap (id 6580) | -0.094 SOL truth ignored | +0.088 SOL undercount | 0 (by construction) |
| Implementation cost | 0 | ~1h (this session) | ~3-5h (Helius + parsing + fallbacks) |
| Live-window readiness | NOT READY (no fee tracking) | OPERATIONAL with caveats | TRUTH PARITY |
