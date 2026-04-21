-- DASH-RESET 2026-04-21 — paper PnL dashboard reset
--
-- Rationale: the +500-SOL paper PnL visible on dashboard was computed under
-- the pre-FEE-MODEL-001 fee model. Post-rebaseline (commit e078b4c) that same
-- window produced -587 SOL under realistic costs. The old aggregates were
-- actively misleading daily ops. This script captures the exact operations
-- used to archive and reset the paper_trades table while preserving live rows.
--
-- Safe to re-run: PHASE 1 CREATE IF NOT EXISTS + INSERT is idempotence-guarded
-- in the session python wrapper (empty-archive precondition). PHASE 3 DELETE
-- is safe after archive is populated. PHASE 4b baseline insert is one-shot.
--
-- Applied: 2026-04-21 via bundled python wrapper. This SQL file is the audit
-- trail.

-- ========== PHASE 1 — ARCHIVE ==========

CREATE TABLE IF NOT EXISTS paper_trades_archive_20260421 (
    LIKE paper_trades INCLUDING ALL
);

ALTER TABLE paper_trades_archive_20260421
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS archive_reason TEXT DEFAULT
        'DASH-RESET 2026-04-21: pre-gate-changes baseline; fee model under-counted per FEE-MODEL-001';

-- Copy ALL rows (live + paper) into archive. archived_at + archive_reason
-- populated by column defaults.
-- The python wrapper builds the explicit column list at runtime so schema
-- drift won't break this (no `SELECT *` across the column shape difference).
-- INSERT INTO paper_trades_archive_20260421 (<explicit cols>)
--     SELECT <explicit cols> FROM paper_trades;
-- Result from session run: INSERT 0 6635 (all rows copied).
-- Verify: original = archived.

-- ========== PHASE 3 — DELETE PAPER ROWS ==========

-- Wrapped in implicit transaction in the python session runner.
-- DELETE FROM paper_trades WHERE trade_mode='paper';
-- Result from session run: DELETE 6629 paper rows; 6 live rows preserved.
-- Verify post-delete: SELECT trade_mode, COUNT(*) FROM paper_trades GROUP BY 1;
--   expected: only 'live' with N=6.

-- ========== PHASE 4b — BASELINE PORTFOLIO_SNAPSHOT ==========

-- Without this, bot_core's _load_state reads the most recent pre-reset row
-- (at the inflated balance) and carries that in-memory state forward —
-- defeating the reset. With this baseline row + a bot_core restart, the
-- bot reloads at the baseline.
--
-- Insert a fresh baseline after deleting any post-reset stale snapshots
-- that were written while bot_core still held inflated in-memory state:
--
-- DELETE FROM portfolio_snapshots
--   WHERE id > <baseline_id> AND total_balance_sol > 100;
-- INSERT INTO portfolio_snapshots
--   (timestamp, total_balance_sol, open_positions, daily_pnl_sol, market_mode)
--   VALUES (NOW()::text, 20.0, 0, 0.0, 'NORMAL_RESET_20260421_v2');
--
-- Session run result: baseline row id=39038 @ 2026-04-21T11:12:33Z, then
-- id=39034 also at 20.0 SOL. After bot_core restart, subsequent snapshots
-- write at total_balance_sol=20.0.

-- ========== PHASE 5 — REDIS CACHE INVALIDATION ==========

-- Outside SQL scope. Executed via Redis MCP:
--   DEL bot:portfolio:balance
--   DEL bot:status
-- Both keys are rewritten by bot_core on its next heartbeat — this is a
-- transient clear that the restart makes durable (bot_core reloads from
-- the baseline portfolio_snapshots row).

-- ========== ROLLBACK (emergency) ==========
-- If the reset breaks something, restore paper rows from archive. Build
-- column list explicitly (archive has 2 extra columns — archived_at,
-- archive_reason — which are NOT in paper_trades).

-- INSERT INTO paper_trades (<live paper_trades column list>)
--     SELECT <same column list> FROM paper_trades_archive_20260421
--     WHERE trade_mode='paper';

-- DO NOT use SELECT * — the archive has 2 extra columns that would fail
-- the INSERT column count.

-- ========== OBSERVATIONS ==========

-- 1. _portfolio_snapshot_task (bot_core.py:1963-1987) computes
--    `daily_pnl_sol` as SUM(realised_pnl_sol) across ALL paper_trades
--    rows where exit_time IS NOT NULL, WITHOUT trade_mode filter. With
--    6 live rows remaining post-reset, this sum = -3.205 SOL.
--    Therefore post-reset snapshots show daily_pnl_sol=-3.205 indefinitely
--    (or until more trades close, at which point the sum updates).
--    This is a pre-existing code semantic — the snapshot-task is mislabelled
--    and its query does not reflect "daily" PnL in any real sense. Not
--    attributable to this reset; documented here for future bug tracking.
