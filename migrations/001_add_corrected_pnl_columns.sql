-- Migration: Add corrected P/L columns for staged TP backfill
-- Date: 2026-04-13
-- Context: The bot_core._close_position() bug (fixed in commit 5b92226)
--   caused trades with staged take-profits to record ONLY the final
--   residual exit's P/L, not the sum across all exits. This migration
--   adds corrected columns to preserve audit trail while providing
--   accurate P/L data.

ALTER TABLE paper_trades
  ADD COLUMN IF NOT EXISTS corrected_pnl_sol DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS corrected_pnl_pct DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS corrected_outcome TEXT,
  ADD COLUMN IF NOT EXISTS correction_applied_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS correction_method TEXT;

-- correction_method values:
--   'staged_tp_backfill_v1' — pre-fix trades recomputed using trigger prices
--   'pass_through'          — post-fix trades or non-staged (copies realised_pnl_sol)
--   NULL                    — not yet processed

-- Backfill was applied via Python script (not committed) on 2026-04-13.
-- See STAGED_TP_BACKFILL_REPORT.md for details.
