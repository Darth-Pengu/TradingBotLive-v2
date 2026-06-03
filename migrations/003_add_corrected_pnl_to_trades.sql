-- Migration: Add corrected P/L columns to the `trades` table (DASH-CORRECTED-PNL-COLUMN-001)
-- Date: 2026-06-03
-- Context: FULL-CODE-AUDIT-001 §B Phase-3 #15. Migration 001 added the corrected_* columns to
--   `paper_trades` ONLY. The `trades` table (the combined live+ML corpus) never got them, so a
--   dashboard query that references corrected_pnl_sol against `trades` errors
--   `column "corrected_pnl_sol" does not exist` every ~60s (web service), silently breaking a
--   PnL/analytics panel. Mirroring the columns onto `trades` resolves the error and lets the live
--   close path (#14 Path B) record on-chain-corrected PnL into the ML corpus going forward.
-- Additive + nullable + IF NOT EXISTS → safe and idempotent. Reverse: DROP COLUMN.

ALTER TABLE trades
  ADD COLUMN IF NOT EXISTS corrected_pnl_sol DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS corrected_pnl_pct DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS corrected_outcome TEXT,
  ADD COLUMN IF NOT EXISTS correction_applied_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS correction_method TEXT;

-- Same correction_method semantics as paper_trades:
--   'live_actual_v1'     — Path B (Helius on-chain native delta) succeeded
--   'live_estimated_v1'  — Path A (oracle + simulated fee/slippage) fallback
--   NULL                 — not yet processed (legacy/paper rows in the corpus)
