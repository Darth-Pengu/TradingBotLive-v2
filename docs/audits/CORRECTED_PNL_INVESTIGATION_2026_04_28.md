# BUG-022 Investigation — corrected_pnl_sol NULL on all paper_trades rows

**Session:** BUG-022 / 2026-04-28
**Author:** Claude Code (read-only investigation)
**Scope:** Diagnose why `corrected_pnl_sol` is NULL on every row in `paper_trades`. Document findings + recommended fix shape only — **no fix this session.**

---

## §1 Failure mode verdict

**2a — Job not scheduled anywhere.**

Stronger statement: **the writer never existed as committed code.** The only time `corrected_pnl_sol` was ever populated was a one-off uncommitted Python script that ran on **2026-04-13** to backfill the staged-TP bug fix. That script was never committed, never scheduled, and never re-run.

The `migrations/001_add_corrected_pnl_columns.sql` comment is explicit:

> Backfill was applied via Python script (not committed) on 2026-04-13.
> See STAGED_TP_BACKFILL_REPORT.md for details.

Since the DASH-RESET on 2026-04-21 wiped all rows with `id ≤ 3605` (the only rows that had ever been backfilled), the paper_trades table has been **100% NULL on `corrected_pnl_sol`** from id `6575` onward.

The `correction_method` enum has three documented values (`staged_tp_backfill_v1` / `pass_through` / `NULL`). NULL means "not yet processed." All 853 current rows are in that state.

This is **not a runtime/scheduling/Sentry/credentials failure.** It is a **missing component** — the writer was never engineered into the system.

---

## §2 Evidence

### §2.1 DB population stats (queried 2026-04-28 at session time)

```
SELECT COUNT(*), COUNT(*) FILTER (WHERE corrected_pnl_sol IS NOT NULL),
       MIN(correction_applied_at), MAX(correction_applied_at)
FROM paper_trades;
```

| metric | value |
|---|---:|
| total rows | 853 |
| total_closed | 853 |
| corrected_pnl_sol populated | **0** |
| closed but corrected NULL | **853** |
| first correction_applied_at | NULL |
| last correction_applied_at | NULL |

```
SELECT correction_method, COUNT(*) FROM paper_trades GROUP BY correction_method;
```

| correction_method | count |
|---|---:|
| `NULL` | **853** |

```
ID range of NULL closed rows: 6575 → 7484
```

The DASH-RESET on 2026-04-21 (script: `Scripts/dash_reset_20260421.sql`) wiped paper_trades with id < ~6575. Every row created since then has been NULL on the corrected columns.

### §2.2 Code search — no writer exists

Searched all of `services/`, `Scripts/`, and the entire repo for any string that writes to `corrected_pnl_sol`:

```
Grep pattern: 'UPDATE.*corrected_pnl|corrected_pnl_sol\s*=|SET\s+corrected_pnl|INSERT.*corrected_pnl'
Path: services/
Result: No matches found

Grep pattern: same
Path: Scripts/
Result: 1 match — Scripts/rebaseline_paper_edge.py:81 (READS corrected_pnl_sol; does not write)
```

The only file that even mentions `corrected_pnl_sol` in code is `Scripts/rebaseline_paper_edge.py`, and it only reads the column to decide whether to use `corrected_pnl_sol` or fall back to `realised_pnl_sol` for its Monte-Carlo rebaseline analysis. It never executes an `UPDATE` against the column.

There is no scheduled job, no APScheduler entry, no cron, no Railway scheduled service, no event handler, no inline write at trade-close that writes `corrected_pnl_sol`.

### §2.3 FEE-MODEL-001 (commit `e078b4c`) did not add a writer

`session_outputs/ZMN_FEE_MODEL_DONE.md` documents the four files touched by FEE-MODEL-001:

| File | Change |
|---|---|
| `services/paper_trader.py` | New `_simulate_slippage` + `_simulate_fees`; affects `realised_pnl_sol` directly on new trades |
| `services/bot_core.py` | Passes bonding_curve_progress to paper_buy/sell |
| `scripts/rebaseline_paper_edge.py` | New READ-ONLY analysis tool |
| `docs/audits/PAPER_EDGE_REBASELINE_2026_04_20.md` | Audit output |

**None of these write `corrected_pnl_sol`.** The new fee model affects `realised_pnl_sol` directly — for any row created after `e078b4c` (id ≥ ~6280 by date), `realised_pnl_sol` already incorporates the corrected fee/slippage model.

This is the load-bearing observation for the recommended fix shape (§4).

### §2.4 The CLAUDE.md "always use corrected_pnl_sol" rule is now stale

CLAUDE.md "Trade P/L Analysis Rule":

> When analyzing trade performance from paper_trades, ALWAYS use the
> `corrected_pnl_sol` and `corrected_pnl_pct` columns, NOT `realised_pnl_sol`...

This rule was correct as written (2026-04-13) for the staged-TP-bug era. After the bug-fix commit `5b92226` and the FEE-MODEL-001 commit `e078b4c`, **`realised_pnl_sol` is already correct** on all post-`e078b4c` rows. The corrected column would, by design, simply be a `pass_through` copy on these rows — same value, different column name.

Concretely: in the 4-day audit (`PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md`), all PnL numbers fell back to `realised_pnl_sol`. The directional findings are robust regardless of fee correction (TRAILING_STOP +11.31 SOL vs stop_loss_20% -5.71 SOL is not flipped by fee bias). Absolute magnitudes carry the FEE-MODEL bias caveat for **pre**-`e078b4c` rows only — for current rows they don't.

### §2.5 Historical confirmations

Two prior session audits already noted this gap:

- `STATE_AUDIT_2026_04_14.md` line 228:
  > The 30 trades from the Apr 13 burst (IDs 3601-3630) all have `corrected_pnl_sol = NULL`. The backfill session only populated corrected columns for trades up to ID ~3605... Trades entered AFTER the backfill (3606-3630) don't have corrected values yet.

- `docs/audits/ML_BYPASS_INVESTIGATION_2026_04_20.md` line 199:
  > `corrected_pnl_sol=NULL` on row id=6580 means the post-fix correction pipeline hasn't run for this live row yet (correction applies to historical paper trades). Separate concern, low priority.

Both observations were correct. Neither resulted in a writer being added.

---

## §3 Impact

### §3.1 Spot-check on 3 recent closed rows (manual verification)

Selected 3 simple-exit rows (no staged TPs) where the formula is unambiguous:
`pnl = (exit/entry - 1) * amount_sol - fees_sol`

| id | mint | amt (SOL) | entry | exit | fees_sol | realised_pnl | computed (formula) | match |
|---:|---|---:|---|---|---:|---:|---:|---|
| 7483 | c2bsamTg | 0.0828 | 2.591e-6 | 2.164e-6 | 0.00134 | -0.014978 | -0.01499 | ✅ |
| 7482 | 8jZbz6jZ | 0.1086 | 2.734e-6 | 2.158e-6 | 0.00160 | -0.024472 | -0.02447 | ✅ |
| 7480 | GrdSku6J | 0.0918 | 2.780e-6 | 2.221e-6 | 0.00143 | -0.019896 | -0.01990 | ✅ |

Each row's `realised_pnl_sol` matches the closed-form formula to ≤ 5e-5 SOL (rounding noise). **`fees_sol` is the FEE-MODEL-001 corrected round-trip cost — already populated, already used in `realised_pnl_sol`.**

For these 3 rows, **`corrected_pnl_sol` SHOULD equal `realised_pnl_sol`** under the `pass_through` method documented in the migration. Delta if backfilled: 0 SOL on each row (pass-through is identity).

### §3.2 features_json fee components — not populated

`session_outputs/ZMN_FEE_MODEL_DONE.md` "Leftover concern #3" flagged that the per-component fee_breakdown returned by `paper_buy`/`paper_sell` is NOT merged into `features_json`. Verified on the same 3 rows:

- Only fee/slippage-shaped keys present in features_json: `jito_bundle_count`, `jito_tip_lamports` (both =0).
- No `platform_fee`, `lp_fee`, `priority_fee`, `slippage_buy`, `slippage_sell`, etc.

**This is a separate gap (separate concern from BUG-022)**, but it constrains how rich a corrected-pnl recompute could be. For the simple `pass_through` fix shape (recommended below), per-component fees aren't needed — `fees_sol` aggregate is sufficient.

### §3.3 Aggregate impact — small for current rows, large in principle

If we backfilled all 853 current rows with `corrected_pnl_sol = realised_pnl_sol` (pass_through), aggregate analyses would change as follows:

- Sum `corrected_pnl_sol` over all closed paper rows: shifts from `NULL`-effective-zero to **same value as sum(realised_pnl_sol)** = current bot's reported aggregate PnL.
- Per-row delta: 0 SOL on every row (pass-through is identity).
- WR: unchanged (sign of pnl is preserved).
- ML training labels (per CLAUDE.md "ML retraining: use corrected_pnl_sol"): currently using NULL → likely falls back to a default WHERE filter that drops the row. Post-backfill: all 853 rows usable for training.

**For pre-DASH-RESET rows (id 1..3605):** those are gone from the DB (DASH-RESET wiped them). The historical CSVs in `session_outputs/` preserve them. They were the rows where `corrected_pnl_sol ≠ realised_pnl_sol` (staged-TP bug). Restoring them is out of scope for this session.

### §3.4 Conclusion on impact

**For current operational decisions:** the impact of BUG-022 is **near-zero on directional findings** because `realised_pnl_sol` is already correct on post-`e078b4c` rows. The CLAUDE.md rule that prefers `corrected_pnl_sol` over `realised_pnl_sol` is a defensive habit pointing at a column that has never been populated for any current row.

**For ML retraining:** if/when ML training resumes (per CLAUDE.md "ML retrain blocked on 500+ clean samples"), the absence of `corrected_pnl_sol` will cause every row to be excluded if the training query filters on `corrected_pnl_sol IS NOT NULL`. The query needs to be checked — if it falls back to `realised_pnl_sol` (per the rebaseline_paper_edge.py pattern), no impact. If it strictly filters, all 853 rows are dropped.

**For BUG-022 reporting:** the bug is real (column is NULL) but the urgency is structural-cleanup, not data-correctness. Quoted PnL numbers using `realised_pnl_sol` are not silently wrong on current data.

---

## §4 Recommended fix shape

Three viable fix shapes, in increasing scope:

### Option A — 5-min one-time SQL backfill + close-time inline write

**Two-part fix:**

1. One-time SQL to backfill all current 853 NULL rows:
   ```sql
   UPDATE paper_trades
   SET corrected_pnl_sol = realised_pnl_sol,
       corrected_pnl_pct = realised_pnl_pct,
       corrected_outcome = outcome,
       correction_method = 'pass_through',
       correction_applied_at = NOW()
   WHERE corrected_pnl_sol IS NULL
     AND exit_time IS NOT NULL;
   ```

2. Add the same write inline at `services/paper_trader.py` close-time, OR at `services/bot_core.py:_close_position` paper-branch INSERT, so future rows get populated automatically. ~5-10 lines of code.

**Why this works:** post-`e078b4c`, `realised_pnl_sol` already incorporates the corrected fee/slippage model. `pass_through` is the correct method per the migration's documented enum. No re-computation is required because the bias the corrected column was designed to fix is already addressed at write-time by FEE-MODEL-001.

**Effort:** ~30 minutes total (5 min SQL + 10 min code + 15 min verification + 5 min commit + STATUS update).

**Risk:** very low. SQL is idempotent (`WHERE corrected_pnl_sol IS NULL`). Code change is a 1-statement INSERT/UPDATE addition; no logic change to PnL computation.

### Option B — 30-min cron correction job

Add a service or scheduled Railway job that periodically runs the SQL above (e.g., every 15 minutes) over any rows that newly enter the NULL-state. Re-engineers the original "correction pipeline" idea from the migration comment.

**Why probably overkill:** Option A's inline write at close-time guarantees no row ever reaches the steady state with NULL corrected. A cron only matters if writes can fail and need retry. The current architecture has no such failure mode — the close-time INSERT is a single atomic transaction. A cron would be running a no-op every 15 minutes.

**Use this only if:** there's a future requirement for re-correction (e.g., re-running the model on existing rows with new constants). For BUG-022 specifically, Option A is sufficient.

### Option C — 60-min code refactor: deprecate corrected_pnl_sol

Stop pretending the column has independent semantics. Treat it as an alias for `realised_pnl_sol` on post-`e078b4c` rows. Update CLAUDE.md, the dashboard, ML training query, and any other reader to use `COALESCE(corrected_pnl_sol, realised_pnl_sol)` and stop maintaining the column going forward.

**Trade-off:** preserves the historical pre-`e078b4c` corrected_pnl_sol values (the rows with `correction_method='staged_tp_backfill_v1'`) for the audit-trail use cases that motivated the migration in the first place — but those rows no longer exist in the DB after DASH-RESET. So the audit-trail use case is already moot.

**Why probably right long-term:** the "two PnL columns" design was a 2026-04-13 patch for a specific bug (staged-TP). FEE-MODEL-001 made `realised_pnl_sol` authoritative. Maintaining a parallel "corrected" column adds engineering surface for no current value.

**Use this if:** Jay wants to de-clutter the schema. Lower priority than Option A — the inline-write fix unblocks the immediate "all rows NULL" problem.

### Recommendation

**Land Option A in the BUG-022 fix session.** It is the smallest, lowest-risk change that restores the CLAUDE.md "always use corrected_pnl_sol" rule to a working state. Defer Option C as a TUNE/cleanup item.

---

## §5 Backfill needed for existing 215 NULL rows? — yes, all 853

The session prompt mentions "215 NULL rows" — that figure is stale. **As of investigation time, all 853 closed paper_trades rows have NULL `corrected_pnl_sol`.**

Backfill recipe under Option A:

```sql
UPDATE paper_trades
SET corrected_pnl_sol = realised_pnl_sol,
    corrected_pnl_pct = realised_pnl_pct,
    corrected_outcome = outcome,
    correction_method = 'pass_through',
    correction_applied_at = NOW()
WHERE corrected_pnl_sol IS NULL
  AND exit_time IS NOT NULL;
```

**Idempotent.** Re-running has no effect (the WHERE clause excludes already-corrected rows).

**Single transaction.** 853 rows fit comfortably in one UPDATE; no batching needed.

**Verification post-backfill:**

```sql
SELECT correction_method, COUNT(*) FROM paper_trades GROUP BY correction_method;
-- Expected: pass_through=853, NULL=0
SELECT COUNT(*) FROM paper_trades WHERE corrected_pnl_sol IS NULL AND exit_time IS NOT NULL;
-- Expected: 0
SELECT MAX(corrected_pnl_sol - realised_pnl_sol) FROM paper_trades WHERE correction_method='pass_through';
-- Expected: 0.0 (pass-through is identity)
```

**Caveat for ML training:** if the historical pre-`e078b4c` rows from the CSVs in `session_outputs/` are ever restored to the DB, they need the `staged_tp_backfill_v1` method, NOT `pass_through`. The recommended SQL above is safe for current rows because they're all post-`e078b4c`. If pre-`e078b4c` rows are restored later, the SQL above would mark them `pass_through` incorrectly. **Don't run the backfill SQL against any restored historical rows without the staged-TP recompute logic.**

---

## §6 Out of scope (per session prompt)

- Implementing the fix (Option A, B, or C) — separate session.
- Backfilling rows that no longer exist in DB (the pre-DASH-RESET id 1..3605 rows are CSV-only).
- Updating CLAUDE.md "Trade P/L Analysis Rule" — defer to fix session.
- Updating the dashboard or ML training query to use COALESCE.
- Investigating why DASH-RESET wiped pre-correction rows in the first place.
- Investigating the `features_json` per-component fee gap (separate concern).

---

## §7 ZMN_ROADMAP.md update marker

This investigation marks BUG-022 as **🟡 INVESTIGATED** (verdict + recommended fix shape documented; fix deferred). The roadmap entry update is part of the docs commit landing this audit, per the session prompt's allowance of "ZMN_ROADMAP.md updates beyond marking BUG-022 as 🟡 INVESTIGATED" being out of scope (i.e., only the marker itself is in scope; broader roadmap edits are not).

---

## Reproducibility

Queries:

```bash
# Population stats
asyncpg.connect($DATABASE_PUBLIC_URL).fetch("""
  SELECT COUNT(*), COUNT(*) FILTER (WHERE corrected_pnl_sol IS NOT NULL),
         MIN(correction_applied_at), MAX(correction_applied_at)
  FROM paper_trades
""")

# Method breakdown
... fetch("SELECT correction_method, COUNT(*) FROM paper_trades GROUP BY 1")

# Sample 5 rows (last 5 by id desc)
... fetch("""SELECT id, mint, amount_sol, entry_price, exit_price, fees_sol,
                    realised_pnl_sol, corrected_pnl_sol, correction_method,
                    features_json FROM paper_trades
             WHERE exit_time IS NOT NULL ORDER BY id DESC LIMIT 5""")
```

Code search:

```
Grep -r 'UPDATE.*corrected_pnl|corrected_pnl_sol\s*=' services/ Scripts/ migrations/
→ services/: 0 matches
→ Scripts/: 1 read-only match in rebaseline_paper_edge.py:81
→ migrations/: 1 match in 001_add_corrected_pnl_columns.sql (column DDL only)
```
