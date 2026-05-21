# ORPHAN-PAPER-CLOSURE-INVESTIGATION-001 — 2026-05-21

**Session:** V5A-FIXES-001 (Phase 1)
**Purpose:** answer four targeted questions about how 14 paper-orphan rows reached the V5A-FLIP-001-V2 live container's `self.positions` despite the audit query at 09:55:28Z returning 0 open positions.

---

## §1 Verdict

The audit's puzzle is resolved.

**Root cause:** the V5A-FLIP-001-V2 audit's "0 open positions" query at 09:55:28Z (`SELECT COUNT(*) FROM paper_trades WHERE entry_time IS NOT NULL AND exit_time IS NULL`) was on the **wrong table** for verifying live-mode reconciliation. The live container reads `trades`, not `paper_trades`. At 09:55:28Z, `trades WHERE closed_at IS NULL` would have returned 14 (the same 14 mints later loaded by the reconciler at 10:04:11Z).

The 14 phantom paper_trades rows (ids 9940-9953) were **NEW INSERTs by the live container's defensive close path**, not pre-existing rows that had their `trade_mode` flipped. Original paper_trades rows for the same mints existed earlier with lower IDs (correctly tagged `trade_mode='paper'`, properly closed in paper mode with `exit_time` set). The phantoms are a separate row set documenting the live-container's in-memory close events.

---

## §2 The four questions, answered

### Q1 — What query does `bot_core._reconcile_positions` use to identify positions to restore?

**Two reconcile paths in `services/bot_core.py`:**
1. `_reconcile_positions` (line 243-258) — startup log only, doesn't load positions into `self.positions`.
2. `_load_state` (line 296-358) — actually loads positions into `self.positions`.

**Both paths use the same query logic (pre-fix):**

```python
table = "paper_trades" if TEST_MODE else "trades"
exit_col = "exit_time" if TEST_MODE else "closed_at"
current_mode = "paper" if TEST_MODE else "live"
mode_clause = f" AND trade_mode = '{current_mode}'" if table == "paper_trades" else ""
SELECT ... FROM {table} WHERE {exit_col} IS NULL{mode_clause}
```

In **live mode** (`TEST_MODE=false`):
- `table = "trades"` (the paper+live combined ML corpus per `LIVE-TRADES-LOGGING-AUDIT-001` commit `83a13ad`)
- `exit_col = "closed_at"`
- `current_mode = "live"`
- `mode_clause = ""` ← **the bug: filter only applied if `table == "paper_trades"`**

The live-mode SQL executed by the V5A-FLIP-001-V2 container at 10:04:11Z:
```sql
SELECT * FROM trades WHERE closed_at IS NULL ORDER BY id ASC
```

This returned 14 rows — pre-existing open paper trades whose `paper_trades.exit_time` was set (closed in paper mode) but whose `trades.closed_at` was never updated (per Q3 below).

### Q2 — Pre-incident state of the 14 known orphans

Cross-checked via DB query at session time (2026-05-21):
- All 14 paper_trades rows (ids 9940-9953) had `entry_time` spanning 2026-05-12 to 2026-05-19. 
- All 14 are NEW INSERTs at exit_time 1779271461-1779271559 (2026-05-20 10:04-10:05 UTC — when the live container closed them).
- 14 matching `trades` rows exist by mint (t_ids 6654, 6885, 7497, 7500, 7762, 7764, 7782, 8422, 9414, 9415, 9926, 9927, 9929, 9930). Pre-incident, all 14 trades rows had `closed_at=NULL` and `trade_mode='paper'`. The live container's `_close_position:1416-1420` UPDATEd each one to set `closed_at` at the in-memory close.

The original paper_trades rows for these 14 mints existed earlier with lower IDs (correctly written with `trade_mode='paper'` and properly closed with `exit_time` set by the paper bot at the actual close time). Those rows are unaffected by the incident.

**The 14 phantom paper_trades rows (9940-9953) are NEW INSERTs from the live container's defensive close path at line 1530+ (`bot_core.py`). They are NOT the original paper_trades rows for those mints — they are a parallel record of the live container's in-memory close events.**

### Q3 — Paper close path: how does it write exit_time?

**`paper_trader.paper_sell:422-443`** UPDATEs `paper_trades.exit_time` consistently. Paper bot's `paper_trades` rows always get exit_time set on close.

**`bot_core._close_position:1247-1257`** is the ML-corpus update path:

```python
# Write ML outcome to trades table using trades_ml_id
if pos.trades_ml_id:
    try:
        await self.pool.execute(
            """UPDATE trades SET exit_price=$1, pnl_sol=$2, pnl_pct=$3,
               outcome=$4, closed_at=$5 WHERE id=$6""",
            ...
```

**The `trades.closed_at` UPDATE is conditional on `pos.trades_ml_id` being truthy.** When `trades_ml_id == 0` (the default value when not properly set during position creation), the UPDATE doesn't run and the trades row stays "open" forever.

This is a data-hygiene side-effect, not a structural design bug. The Bug 1 reconcile-filter fix (Phase 3) addresses the symptom (live reconciler shouldn't load paper rows from trades). A separate, future fix could harden `_close_position` to always update `trades.closed_at` regardless of `trades_ml_id`, but it's not required for V5A-FLIP-002 safety post-Bug-1.

**STOP-INV2 evaluated:** does NOT fire. The paper close-path issue is a minor data hygiene concern; the structural fix is at the reconciler level.

### Q4 — Population of orphans matching the reconciler's exact criteria RIGHT NOW

```
[paper-mode reconciler] paper_trades WHERE exit_time IS NULL AND trade_mode='paper': 0 rows
[live-mode reconciler PRE-FIX] trades WHERE closed_at IS NULL: 1 row
[live-mode reconciler POST-FIX] trades WHERE closed_at IS NULL AND trade_mode='live': 0 rows
```

The 1 row in `trades`-table pre-fix was `id=10083, mint=GEeWmtv2giXb..., trade_mode='paper'` at the time of investigation. By the time the verify script ran (~30 min later), it had shifted to `id=10089, mint=2fT8NSPCPcGW...` — confirming the bug is ONGOING (new paper orphans accumulate in `trades` as the paper bot continues operating).

**STOP-INV1 evaluated:** `Q4 paper_trades reconciler result = 0` → does NOT fire. The 1 ongoing `trades`-table orphan is a non-blocking finding; the Bug 1 fix prevents it from re-contaminating live mode.

### STOP evaluation summary

| STOP | Condition | Result |
|---|---|---|
| STOP-INV1 | Q4 paper_trades orphans > 0 | 0 — does NOT fire |
| STOP-INV2 | Q3 reveals design-decision-needed close-path bug | Q3 reveals conditional `trades.closed_at`; data hygiene, not design — does NOT fire |
| STOP-INV3 | Q1 reveals reconciler query is opaque | Q1 fully decoded — does NOT fire |

---

## §3 Data evidence

**Schema verification (at session time):**
- `trades` table columns include: `id`, `mint`, `personality`, `closed_at`, `created_at`, `trade_mode` (added 2026-05-14 by `LIVE-TRADES-LOGGING-AUDIT-001`).
- `paper_trades` table columns include: `id`, `mint`, `personality`, `entry_time`, `exit_time`, `trade_mode`, `correction_method`, `correction_applied_at`.

**trade_mode distribution at session time:**
| Table | trade_mode | count |
|---|---|---:|
| trades | paper | 10,040 |
| trades | live | 41 |
| paper_trades | paper | 3,428 |
| paper_trades | live | 20 |

**paper_trades trade_mode='live' breakdown:**
- 5 historical v3/v4 trial residuals (ids 6575-6579, `correction_method=pass_through`, NULL signatures)
- 1 real on-chain live trade (id 6580, `correction_method=live_actual_v1`, sigs populated, +0.0019 SOL)
- 14 V5A-FLIP-001-V2 phantoms (ids 9940-9953, **NOW tagged `correction_method=paper_orphan_at_flip_v5a_001`** by Phase 2 of this session)

---

## §4 Recommendations downstream

1. **V5A-FLIP-RECONCILE-FILTER-001 (Phase 3)** — DEPLOYED 2026-05-21 ~14:42 UTC (commit `f3591eb`). Fixes the structural root cause.
2. **V5A-FLIP-CONTAMINATION-CLEANUP-001 (Phase 2)** — DONE. 14 rows tagged.
3. **V5A-FLIP-CLOSE-TRADE-MODE-001 / Bug 2 (Phase 6)** — DEPLOYED 2026-05-21 (commit `3c50520`). Defense-in-depth so any future Bug 1 regression won't write contaminated rows.
4. **BOT-CORE-EMERGENCY-STOP-LIVENESS-001 (Bug 3)** — closed as non-bug. Per-decision check already at `bot_core.py:604-609`.
5. **PORTFOLIO-SNAPSHOT-MODE-FILTER-001** (Tier 3, NEW) — `_portfolio_snapshot_task:2188` counts closed rows from the table mode without trade_mode filter; live-mode snapshots may aggregate paper closures. Filed for future cleanup; not V5A-blocking.
6. **LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001** (Tier 3, NEW) — `pos.entry_signature` is never set on Position; Path B Helius parse skips entry side. Filed for future cleanup; not V5A-blocking.
7. **HEARTBEAT-EMERGENCY-STOP-REFLECTION-001** (Tier 3, NEW) — heartbeat reflects in-memory `self.emergency_stopped`, not the Redis `bot:emergency_stop` flag. Operator confusion possible. Filed for observability improvement; not V5A-blocking.
8. **PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001** (Tier 3, NEW) — close path's `trades.closed_at` UPDATE is conditional on `pos.trades_ml_id`. Should be unconditional or have a fallback for paper trades with default trades_ml_id=0. Filed for future cleanup; not V5A-blocking post-Bug-1.

---

End of investigation.
