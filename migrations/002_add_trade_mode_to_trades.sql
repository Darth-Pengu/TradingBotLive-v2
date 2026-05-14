-- Migration: Add trade_mode discriminator to the `trades` table
-- Date: 2026-05-14
-- Context: LIVE-TRADES-LOGGING-AUDIT-001. The `trades` table is the ML-training
--   corpus and is written in BOTH paper mode (bot_core.py paper branch) and live
--   mode (bot_core.py live branch) — by design. It had no trade_mode column, so
--   paper and live rows were indistinguishable within it. (There is no separate
--   `live_trades` table; a chat-side export of `trades` was mislabelled as such.)
--   `paper_trades` already has trade_mode and remains the correctly-separated
--   source of truth. This migration adds the same discriminator to `trades` and
--   backfills it from the authoritative tables. No rows are deleted.
--
-- Classification basis (see docs/audits/LIVE_TRADES_LOGGING_AUDIT_001_2026_05_14.md):
--   paper: 9,480  (6,612 archive-matched + 2,868 current-matched)
--   live:     41  (35 genuine on-chain v3/v4 trial + 1 on-chain round-trip
--                  [trades.id 6596] + 5 reconcile-residual rows that are
--                  trade_mode='live' in paper_trades)
--   The 35 trial rows sum to -3.36 SOL, cross-validating the ~3.4 SOL on-chain
--   wallet drawdown in CLAUDE.md's 1b40df3 forensics.

-- 1. Add the column (idempotent; also added to db.py _init_tables for fresh deploys).
ALTER TABLE trades ADD COLUMN IF NOT EXISTS trade_mode TEXT DEFAULT 'paper';

-- 2. Mirror trade_mode from current paper_trades on (mint, entry_time≈created_at).
UPDATE trades t
   SET trade_mode = p.trade_mode
  FROM paper_trades p
 WHERE p.mint = t.mint
   AND ABS(p.entry_time - t.created_at) < 5;

-- 3. Mirror from the 2026-04-21 DASH-RESET archive where no current-table match.
UPDATE trades t
   SET trade_mode = a.trade_mode
  FROM paper_trades_archive_20260421 a
 WHERE a.mint = t.mint
   AND ABS(a.entry_time - t.created_at) < 5
   AND NOT EXISTS (
        SELECT 1 FROM paper_trades p
         WHERE p.mint = t.mint AND ABS(p.entry_time - t.created_at) < 5);

-- 4. The 35 v3/v4 live-trial rows: no paper_trades/archive mirror (they predate
--    the DASH-ENTRY-001 live->paper_trades mirror code). Confirmed genuine live
--    by an EXISTS in live_trade_log (every one has a TX_SUBMIT signature event).
UPDATE trades t
   SET trade_mode = 'live'
 WHERE NOT EXISTS (
        SELECT 1 FROM paper_trades p
         WHERE p.mint = t.mint AND ABS(p.entry_time - t.created_at) < 5)
   AND NOT EXISTS (
        SELECT 1 FROM paper_trades_archive_20260421 a
         WHERE a.mint = t.mint AND ABS(a.entry_time - t.created_at) < 5)
   AND EXISTS (
        SELECT 1 FROM live_trade_log l WHERE l.mint = t.mint);

-- Any row untouched by steps 2-4 keeps the column DEFAULT 'paper'.
-- Expected post-migration: trade_mode='paper' -> 9,480 ; trade_mode='live' -> 41.
-- NO rows deleted. Purge of historical rows is NOT part of this migration and
-- remains a separate, explicitly-Jay-authorized decision.
