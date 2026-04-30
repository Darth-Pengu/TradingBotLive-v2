# Fee/Latency Realism Audit — 2026-04-30

**Session:** FEE-LATENCY-REALISM-2026-04-30
**Author:** Claude Code
**Predecessor audits:**
- `docs/audits/LIVE_FEE_MODEL_AUDIT_2026_04_29.md` (spec for what was wrong)
- `docs/audits/LIVE_FEE_CAPTURE_PATH_A_2026_04_30.md` (Session D — Path A wired)
**Patch path chosen:** **A** — plumb tier through `Position` dataclass.
**Status:** Code change applied, compile-checked, pre-deploy verified.
Deploy verification post-push.

---

## §1 Verified findings (with code refs)

### H1 — Paper has zero latency simulation written to DB

**Confirmed.** All four columns exist in `paper_trades` schema; **0 of 1182
rows have any of them populated**.

```
columns in schema:
  scored_at           timestamp without time zone
  signal_detected_at  timestamp without time zone
  total_latency_ms    integer
  traded_at           timestamp without time zone

Population check:
  signal_detected_at NOT NULL: 0 / 1182
  scored_at          NOT NULL: 0 / 1182
  traded_at          NOT NULL: 0 / 1182
  total_latency_ms   NOT NULL: 0 / 1182

Most recent 5 closed rows: all four cols None across the board.
```

**Code search across `services/`:** zero matches for any of the four column
names. No INSERT/UPDATE statement writes them. No timestamp capture code
references them.

The columns exist as DDL-only artifacts; no plumbing exists end-to-end to
populate them. Filling them requires:
1. `signal_listener.py` capturing `signal_detected_at` when PumpPortal sends
   a `createEvent` (currently no timestamp written to the Redis payload at
   that point).
2. `signal_aggregator.py` capturing `scored_at` after ML scoring completes
   and pushing it onto the `signals:scored` payload.
3. `paper_trader.paper_buy` extending its INSERT (currently 15 columns) to
   include `signal_detected_at`, `scored_at`, `traded_at`, `total_latency_ms`.
4. `bot_core.py` live entry INSERT (currently 16 columns post-Session-D)
   doing the same.

**Verdict per Step-3 scope (latency stretch goal):** **STOPPED.** Touches
4 files across 3 services and threads timestamps through Redis service-
to-service payloads. Above the "1-2 file change" stretch-goal cap.
Documented as follow-up work — see §3.

### H2 — Pre-grad fee undercount (paper vs live reality)

**Partially confirmed; fee gap is small relative to slippage gap.**

`services/paper_trader.py:70` — `PAPER_FEE_PUMPFUN_PCT = 0.01` (1% per side,
matches pump.fun's documented platform fee).

Paper's pre-grad fee structure (per `_simulate_fees`):
- Platform: `amount * 0.01` per side (= 0.01 round-trip)
- Priority: `0.0010 / 2 = 0.0005` per side (= 0.001 round-trip)
- Jito tip: **0.0** per side (`PAPER_JITO_TIP_PREGRAD_SOL = 0.0`)
- LP: 0.0 (BC has no separate LP)

For id 6580 (0.3653 SOL pre-grad): paper round-trip = `2 × 0.01 × 0.3653
+ 2 × 0.0005 = 0.007306 + 0.001 = 0.008306 SOL`. Matches Session D's
`fees_sol=0.008306` exactly.

Real pre-grad cost (per `LIVE_FEE_MODEL_AUDIT_2026_04_29.md` §3 + execution.py):
- pump.fun 1% per side ≈ paper match
- Priority 0.0005 SOL per side (paper match)
- **Jito tip 0.001 SOL ROUND-TRIP — paper says 0.0; gap ≈ +0.001 SOL/trade**
- Helius transaction fee ~5000 lamports (negligible)

So fee model gap on id 6580 ≈ **+0.001 SOL** (Jito tip on pre-grad PumpPortal
trades). Total Path A gap on id 6580 was **+0.088 SOL undercount**. Fees
account for ~1% of the gap. **Slippage is the dominant gap.**

This session does NOT change `PAPER_JITO_TIP_PREGRAD_SOL`. Doing so would
shift every paper-mode row's `fees_sol` by ~0.0005 SOL, perturbing the
post-FEE-MODEL-001 baseline mid-run. Better landed alongside Path B
(LIVE-FEE-CAPTURE-002) when we have on-chain truth to calibrate against.

### H3 — `_simulate_slippage("buy", ...)` falls back to default

**Confirmed in code AND empirically via id 6580 backfill.**

`services/paper_trader.py:51-61`:
```python
SLIPPAGE_RANGES = {
    "alpha_snipe":   (3.0, 12.0, 0.7),
    "confirmation":  (2.0, 8.0, 0.7),
    "post_grad_dip": (0.5, 2.0, 0.3),
    "sell":          (3.0, 15.0, 0.7),
    "sell_postgrad": (0.5, 2.5, 0.3),
}
```

`services/paper_trader.py:149`:
```python
entry = SLIPPAGE_RANGES.get(tier, (0.5, 2.0, 0.3))
```

`"buy"` is **not** a key. Calling `_simulate_slippage("buy", ...)` falls back
to `(0.5, 2.0, 0.3)` — same range as `post_grad_dip`. This understates pre-
grad BC slippage by 6-10× vs the appropriate `alpha_snipe` / `confirmation`
tier.

**Call site grep across services/:**

| file:line | call | first arg | in SLIPPAGE_RANGES? |
|---|---|---|---|
| paper_trader.py:244 | `paper_buy` slippage | `slippage_tier` (param) | YES (caller passes tier) |
| paper_trader.py:370 | `paper_sell` slippage | `sell_tier` (computed) | YES (`sell` or `sell_postgrad`) |
| bot_core.py:932 | Path A live entry INSERT | `"buy"` | **NO — falls back** |
| bot_core.py:1271 | Path A live close buy-side | `"buy"` | **NO — falls back** |
| bot_core.py:1272 | Path A live close sell-side | `"sell"` | YES |

**Empirical confirmation from id 6580 backfill** (Session D):
- buy_slip_pct = 1.91% — matches `(0.5, 2.0, 0.3)` × size_factor 1.43 = 0.7-2.9% range
- sell_slip_pct = 18.91% — matches `sell (3.0, 15.0, 0.7)` × size_factor 2.59 = 7.8-38.9% range
- avg_slippage_pct stored = 10.41% (mean of buy 1.91 + sell 18.91)

Per Session D's own §7.4: "Two backfills of the same row would produce
different `slippage_pct` values" — true for the random component, but the
RANGE is bug-fixed not random-fixed. Fix in this session changes the
RANGE for buy-side from default to the entry tier.

### H4 — Path A undercorrects id 6580 by ~12×

**Confirmed via predecessor audit; not re-verified empirically (not needed).**

Per `LIVE_FEE_CAPTURE_PATH_A_2026_04_30.md` §3:
| metric | value |
|---|---:|
| realised_pnl_sol stored (gross) | +0.001876 SOL |
| corrected_pnl_sol (Path A backfill) | -0.006430 SOL |
| on-chain actual | -0.094245 SOL |
| **gap (Path A − actual)** | **+0.087815 SOL** |

This session's slippage-tier fix narrows the gap (see §4 V5a delta below)
but does NOT close it. Path B (Helius `parseTransactions`) remains the
right answer for parity-of-truth. Tracked as **LIVE-FEE-CAPTURE-002**.

### H5 — Path B feasibility

Helius infrastructure already wired in env (`HELIUS_PARSE_TX_URL`,
`HELIUS_PARSE_HISTORY_URL` per Railway bot_core variables snapshot).
Path B implementation requires:
- Async helper: `helius_parse_signature(sig) -> {token_amount, sol_delta, fee_lamports}`
- Call after `execute_trade` returns success on entry/exit
- Compute actual fill price: `(received_token_amount, paid_sol)` ratio
- Fallback on parse failure — keep Path A estimate

Estimated 3-5h of focused work. **Out of scope this session.** Tracked as
**LIVE-FEE-CAPTURE-002**.

### H6 — Tier provenance: where it lives, where it dies

**Tier IS computed in bot_core.** `services/bot_core.py:741-751`:
```python
age = scored_signal.get("signal", {}).get("age_seconds", 0)
if personality == "speed_demon":
    if age <= 30:
        slippage_tier = "alpha_snipe"
    elif age <= 180:
        slippage_tier = "confirmation"
    else:
        slippage_tier = "post_grad_dip"
else:
    slippage_tier = "confirmation"
```

The tier is NOT pre-computed by `signal_aggregator.py` and NOT carried on
the `signals:scored` Redis payload. It's a bot_core-local decision based on
`signal.age_seconds + personality`. So:

- **At entry time (line 932 — live entry INSERT):** `slippage_tier` is in
  scope as a local variable. Trivial fix — pass directly.
- **At close time (line 1271 — live close buy-side recovery):** `_close_position`
  doesn't see `slippage_tier`. Position carries `personality` and
  `bonding_curve_progress` but NOT the entry-time `age_seconds`, so we can't
  re-derive the tier. **Need to plumb `entry_slippage_tier` through Position.**

This is the basis for choosing Patch Path A.

---

## §2 Changes made (diff snippets)

### §2.1 Position dataclass — new field (`services/bot_core.py:172-180`)

**Before:**
```python
rugcheck_risk_level: str = "unknown"
signal_type: str = "standard"  # "standard" or "graduation"
cumulative_pnl_sol: float = 0.0  # Accumulated P/L across all staged exits
```

**After:**
```python
rugcheck_risk_level: str = "unknown"
signal_type: str = "standard"  # "standard" or "graduation"
cumulative_pnl_sol: float = 0.0  # Accumulated P/L across all staged exits
# FEE-LATENCY-REALISM-2026-04-30: entry-time slippage tier (alpha_snipe /
# confirmation / post_grad_dip), set by _handle_signal at entry time. Used
# at close to recover the buy-side _simulate_slippage tier — prior code
# passed literal "buy" which is NOT a SLIPPAGE_RANGES key, falling back to
# the (0.5, 2.0, 0.3) default and undercounting pre-grad BC slippage.
entry_slippage_tier: str = "confirmation"
```

Default `"confirmation"` is the safe fallback matching the non-Speed-Demon
default in `_handle_signal`. If a Position is constructed without
`entry_slippage_tier` set (e.g., in code paths this session didn't touch),
behavior is no worse than the prior code.

### §2.2 Paper entry — Position construction (`services/bot_core.py:840-846`)

**Before:**
```python
pos = Position(
    mint=mint, personality=personality,
    entry_price=paper_result["entry_price"],
    ...
    rugcheck_risk_level=scored_signal.get("rugcheck_risk_level", "unknown"),
    signal_type=scored_signal.get("signal_type", "standard"),
)
```

**After:**
```python
pos = Position(
    mint=mint, personality=personality,
    entry_price=paper_result["entry_price"],
    ...
    rugcheck_risk_level=scored_signal.get("rugcheck_risk_level", "unknown"),
    signal_type=scored_signal.get("signal_type", "standard"),
    entry_slippage_tier=slippage_tier,
)
```

`slippage_tier` already in scope at this site (computed at line 745).
Paper-mode positions can also benefit from this when staged-TP correction
fires close-time logic, even though paper's primary close path
(paper_sell) computes `sell_tier` itself and doesn't need this field.
Setting it for consistency.

### §2.3 Live entry — Position construction (`services/bot_core.py:907-913`)

**Before:**
```python
pos = Position(
    mint=mint, personality=personality,
    entry_price=price, entry_time=time.time(),
    size_sol=size_sol, peak_price=price,
    ml_score=ml_score, signal_source=signal_source,
    bonding_curve_progress=bc_progress,
)
```

**After:**
```python
pos = Position(
    mint=mint, personality=personality,
    entry_price=price, entry_time=time.time(),
    size_sol=size_sol, peak_price=price,
    ml_score=ml_score, signal_source=signal_source,
    bonding_curve_progress=bc_progress,
    entry_slippage_tier=slippage_tier,
)
```

Same logic — `slippage_tier` in scope at this site.

### §2.4 Live entry INSERT slippage call (`services/bot_core.py:935-940`)

**Before:**
```python
# LIVE-FEE-CAPTURE-001 Path A (Session D, 2026-04-30): write
# entry-side slippage + fees estimates from paper helpers, plus
# features_json for live entry parity with paper.
_pe_buy_slip = _simulate_slippage("buy", size_sol)
```

**After:**
```python
# LIVE-FEE-CAPTURE-001 Path A (Session D, 2026-04-30): write
# entry-side slippage + fees estimates from paper helpers, plus
# features_json for live entry parity with paper.
# FEE-LATENCY-REALISM-2026-04-30: pass slippage_tier (computed
# at L745-751 by personality+age) so _simulate_slippage hits
# the correct SLIPPAGE_RANGES key. Prior code passed "buy"
# which fell back to the (0.5, 2.0, 0.3) default range.
_pe_buy_slip = _simulate_slippage(slippage_tier, size_sol)
```

### §2.5 Live close buy-side slippage call (`services/bot_core.py:1278-1287`)

**Before:**
```python
# LIVE-FEE-CAPTURE-001 Path A (Session D, 2026-04-30): use paper helpers
# for round-trip fee + slippage estimates.
_live_buy_slip_pct = _simulate_slippage("buy", pos.size_sol)
_live_sell_slip_pct = _simulate_slippage("sell", sell_amount)
```

**After:**
```python
# LIVE-FEE-CAPTURE-001 Path A (Session D, 2026-04-30): use paper helpers
# for round-trip fee + slippage estimates.
# FEE-LATENCY-REALISM-2026-04-30: use pos.entry_slippage_tier for the
# buy-side recovery so _simulate_slippage hits the correct
# SLIPPAGE_RANGES key (alpha_snipe / confirmation / post_grad_dip).
# Prior code passed "buy" which fell back to (0.5, 2.0, 0.3) default
# -- undercounted pre-grad BC slippage on every live close.
_live_buy_slip_pct = _simulate_slippage(pos.entry_slippage_tier, pos.size_sol)
_live_sell_slip_pct = _simulate_slippage("sell", sell_amount)
```

### §2.6 Compile check

```
python -m py_compile services/bot_core.py
-> COMPILE OK
```

### §2.7 Demonstrate-fix-actually-changes-behavior (`verify_slippage_fix.py`)

Script: `.tmp_fee_latency_audit/verify_slippage_fix.py` (gitignored scratch dir).

Output (2000 samples per tier, `random.seed(42)`):

| tier | min | max | avg | p50 | p95 |
|---|---:|---:|---:|---:|---:|
| **buy (default fallback)** | 0.74 | 2.95 | **1.86** | 1.87 | 2.84 |
| alpha_snipe (NEW) | 7.44 | 29.72 | **18.70** | 18.87 | 28.61 |
| confirmation (NEW) | 4.96 | 19.81 | **12.47** | 12.58 | 19.07 |
| post_grad_dip (NEW) | 0.74 | 2.95 | **1.86** | 1.87 | 2.84 |
| sell (already-correct) | 7.44 | 37.15 | 22.46 | 22.68 | 35.66 |
| sell_postgrad | 0.74 | 3.69 | 2.23 | 2.25 | 3.54 |

Behavior change:
- `alpha_snipe` avg vs old default: **+16.85% (10.0×)**
- `confirmation` avg vs old default: **+10.61% (6.7×)**
- `post_grad_dip` avg vs old default: 0.00% (post_grad_dip range IS the
  default-fallback range, so behavior matches by coincidence — this is
  expected and not a bug)

Round-trip estimate for id 6580 (confirmation tier, 0.3653 SOL pre-grad):
- OLD round-trip avg: 16.29% (buy 2.61% + sell 29.96%) / 2
- NEW round-trip avg: 23.73% (buy 17.50% + sell 29.96%) / 2

Delta: **+7.44 percentage points on the round-trip slippage estimate.**

On id 6580's 0.3653 SOL position, that's roughly an additional 0.027 SOL of
captured slippage cost — **closes ~30% of the +0.088 SOL Path A gap**. Not
a complete closure (Path B remains the right answer for the remaining 70%),
but a meaningful improvement to Path A's calibration.

---

## §3 What remains untrusted

This session does NOT fix:

1. **Pre-grad fee undercount (H2 partial).** `PAPER_JITO_TIP_PREGRAD_SOL = 0.0`
   doesn't model the 0.001 SOL Jito tip that PumpPortal sends on every trade
   per `execution.py:139-143`. Gap ≈ +0.0005 SOL per side. Cosmetic on its own;
   bundle with Path B calibration. Tracked informally as part of LIVE-FEE-CAPTURE-002.

2. **`_simulate_slippage` random non-reproducibility (Session D §7 #4).**
   Backfills are not deterministic. Re-running id 6580's backfill produces a
   different `slippage_pct`. This session does not seed the RNG, doesn't
   change. Path B replaces estimates with truth, so this becomes moot when B
   lands.

3. **id 6580 backfill is NOT re-run.** The row's existing
   `correction_method='live_estimated_v1'` carries the OLD-default
   `buy_slip_pct=1.91`. New live trades will write the corrected tier-aware
   slippage; id 6580 stays as a historical record of the pre-fix estimate.
   Re-running the backfill would change it but produces a different random
   number anyway. Path B will eventually re-correct it as
   `live_actual_v1` once that lands.

4. **Path B (LIVE-FEE-CAPTURE-002) still required for V5a parity-of-truth.**
   This session's fix is calibration improvement, not closure. Live PnL
   recordings remain optimistic by ~70% of the original Path A gap on
   pre-grad BC trades.

5. **Latency observability (H1).** All four columns
   (`signal_detected_at`, `scored_at`, `traded_at`, `total_latency_ms`)
   remain NULL on every paper_trades row. Implementing them is a 4-file
   refactor across `signal_listener` + `signal_aggregator` + `paper_trader`
   + `bot_core` + Redis-payload schema changes. Out of stretch-goal scope.
   Tracked as a new follow-up: **LATENCY-OBSERVABILITY-001**.

6. **Cross-service `_simulate_slippage` semantic inconsistency.** The function
   serves dual roles: stochastic monte-carlo cost estimate (paper) and
   reconstruction estimate (live close path A). The names overlap. No issue
   today but if a future session adds a third caller with a different
   semantic intent, refactor consideration. Not blocking.

7. **Live close FALLBACK INSERT path (`bot_core.py:1330` legacy 21-col INSERT).**
   The session-D-noted untouched code path. Triggers only when the entry
   INSERT failed. Not exercised in the V5a happy path. Tracked as
   LIVE-CLOSE-FALLBACK-INSERT-001 from Session D — unchanged.

---

## §4 V5a readiness delta

**Direction:** Forward.

**What this session moves forward:**
- Live close PnL formula (Path A) now estimates buy-side slippage in the
  correct distribution per entry tier.
- For Speed Demon trades < 30s old (alpha_snipe), Path A buy-side slippage
  jumps from ~1.86% avg to ~18.70% avg — order-of-magnitude correction.
- For Speed Demon trades 30-180s old (confirmation), Path A buy-side
  slippage jumps from ~1.86% avg to ~12.47% avg — 6.7× correction.
- Live entry rows written from V5a forward will have correctly-tiered
  `slippage_pct` at write time.

**What it does NOT move forward (V5a precondition list):**
- Wallet top-up (~3 SOL) — Jay action, unchanged.
- Path B (LIVE-FEE-CAPTURE-002) — still V5a-blocking-but-degradable.
- 24-48h paper observation since last meaningful change — clock continues.
- TIME_PRIME-CONTRADICTION-001 — unchanged.
- Renew Redis daily TTLs — unchanged.

**New blockers discovered:** none. All findings are within Tier-1 carry list.

**New follow-ups created:**
- **LATENCY-OBSERVABILITY-001** — populate `signal_detected_at`, `scored_at`,
  `traded_at`, `total_latency_ms` end-to-end. 4-file refactor; design first.

---

## §5 Reproducibility

```bash
# Compile check
python -m py_compile services/bot_core.py

# Hypothesis verification (DB queries)
python .tmp_fee_latency_audit/h1_h2_db_check.py

# Demonstrate-fix-changes-behavior
python .tmp_fee_latency_audit/verify_slippage_fix.py
```

```bash
# Code change inspection
git diff services/bot_core.py
```

Post-deploy verification SQL (run ~10-15 min after deploy when fresh
HIBERNATE-mode signals don't materialize, or after market_mode flips
back to NORMAL):

```sql
-- Check fresh paper closes have non-default slippage_pct
SELECT id, personality, slippage_pct, fees_sol, exit_reason
FROM paper_trades
WHERE entry_time > extract(epoch from NOW() - INTERVAL '1 hour')
  AND exit_time IS NOT NULL
ORDER BY id DESC LIMIT 10;

-- Distribution of slippage_pct on most recent 50 closes — should NOT
-- be concentrated in (0.5-3) range; should reflect tier mixture
SELECT
  CASE
    WHEN slippage_pct < 3 THEN '0-3'
    WHEN slippage_pct < 7 THEN '3-7'
    WHEN slippage_pct < 15 THEN '7-15'
    ELSE '15+'
  END AS bucket,
  COUNT(*) AS n
FROM paper_trades
WHERE exit_time IS NOT NULL
ORDER BY id DESC
LIMIT 50;
```

Note: this fix does NOT touch the paper-mode `paper_buy` slippage-tier
plumbing (which was already correct). Existing paper close behavior
unchanged. The visible changes will be on **live close path A** for
future live trades.

---

## §6 Trade-off summary table

| dimension | Pre-Session-D | Post-Session-D Path A | **Post Session FEE-LATENCY-REALISM** | Future Path B |
|---|---|---|---|---|
| Live PnL formula | gross (no fees) | net (paper-estimated fees) | net (paper-estimated, **tier-corrected**) | net (on-chain actual) |
| `slippage_pct` on live rows | 0.0 | paper-estimated (`"buy"` literal → default fallback) | **paper-estimated, tier-aware** | on-chain actual |
| `fees_sol` on live rows | 0.0 | paper-estimated | paper-estimated (unchanged) | on-chain actual |
| Path A id 6580 gap | -0.094 SOL truth ignored | +0.088 SOL undercount | **~+0.061 SOL undercount** (~30% closed) | 0 by construction |
| `entry_slippage_tier` on Position | n/a (field doesn't exist) | n/a | **plumbed through Position** | n/a |
| Implementation cost (this session) | 0 | ~1h | ~30min | ~3-5h (TBD) |
| V5a-blocking | N/A | partial (Path B still required) | partial (Path B still required) | unblocks parity-of-truth |

---

## §7 Open issues / what's NOT in this audit

1. **Path B not implemented** (LIVE-FEE-CAPTURE-002).
2. **Latency columns unpopulated** (LATENCY-OBSERVABILITY-001 — NEW from this session).
3. **`PAPER_JITO_TIP_PREGRAD_SOL = 0.0` undercount** — ~0.001 SOL/trade in
   real cost not in paper model. Bundle with B's calibration.
4. **id 6580 backfill not re-run** — historical record of pre-fix
   estimate retained. Re-correction expected via Path B.
5. **`_simulate_slippage` non-determinism** — out of scope; addressed by Path B.
6. **Live close fallback INSERT** (`bot_core.py:1330`) — Session D carry,
   unchanged here.
7. **Cross-service tier semantics** — `_simulate_slippage` serves stochastic
   estimation (paper) AND reconstruction estimation (live close). Names
   overlap; refactor candidate but not blocking.

---

## §8 Carry to next session

After this commit lands and bot_core auto-redeploys:

1. Wait for fresh paper-mode close (likely needs market_mode != HIBERNATE
   for new signals; current market mode HIBERNATE per Redis snapshot at
   12:53 UTC). When fresh closes accumulate, sample 10-20 rows and confirm
   `slippage_pct` distributions reflect the tier mixture (not a single
   default-range cluster).

2. **LIVE-FEE-CAPTURE-002 (Path B)** is the next V5a-blocking session.

3. **LATENCY-OBSERVABILITY-001** can be queued or deferred. Not V5a-blocking;
   useful for SLIPPAGE-CALIBRATION-001 calibration analysis later.
