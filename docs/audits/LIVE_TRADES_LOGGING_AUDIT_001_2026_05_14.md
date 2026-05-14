# LIVE-TRADES-LOGGING-AUDIT-001 — Audit

**Date:** 2026-05-14
**Type:** Investigation → fix → deploy. Changed the persistence/logging path; deployed bot_core.
**Trigger:** Chat-side analysis of `live_trades` vs `paper_trades` exports found apparent
cross-contamination — a "live_trades" table with 9,521 rows whose recent dates matched
`paper_trades` SD counts and whose early-April rows showed impossible PnL for a 5 SOL live budget.

---

## §1 Verdict

**FIXED + DEPLOYED.** But the contamination framing was based on a false premise, corrected by
investigation:

- **There is no `live_trades` table.** Repo-wide grep: zero hits. `to_regclass('live_trades')` →
  `None`. The chat-side "live_trades" is the **`trades` table** (exact row count 9,521, exact
  date range, exact personality split).
- **`trades` is a paper+live combined ML-training corpus *by design*.** `bot_core.py` writes to
  it from both the paper branch (`:881`) and the live branch (`:973`); `ml_model_accelerator.py`
  trains from both `trades` and `paper_trades`. Nothing "leaked" — both modes were always
  written here intentionally.
- **The genuine defect:** `trades` had **no `trade_mode` column**, so paper and live were
  indistinguishable within it. The chat-side concern that "genuine live-money trades are buried
  inside paper-mode contamination" is the accurate part — the 41 live rows were *buried* among
  9,480 paper rows, not *leaked* into a live-only table.
- `paper_trades` already has `trade_mode` and is correctly separated; `live_trade_log` is
  correctly live-only. No misrouting bug exists.

**The fix:** add a `trade_mode` discriminator to `trades`, tag both INSERT sites, and backfill
history from the authoritative tables. **Not STOP-A** (logging is not entangled with decision
logic). **Not STOP-B** (live rows cleanly separable). **Not STOP-C** (contained: 1 column, 2
INSERT lines, 1 db.py migration, 1 backfill SQL).

## §2 Write-path investigation + contamination mechanism

Write sites (verified by reading source, not from exports):

| Site | Table | Mode | `trade_mode` before |
|---|---|---|---|
| `paper_trader.py:291` | `paper_trades` INSERT | paper | written `'paper'` |
| `bot_core.py:881` (was :878) | `trades` INSERT | paper branch (`if TEST_MODE`) | **absent** |
| `bot_core.py:973` (was :970) | `trades` INSERT | live branch (`else`) | **absent** |
| `bot_core.py:1005` | `paper_trades` INSERT | live branch | written `'live'` (DASH-ENTRY-001) |
| `bot_core.py:1217 / :1371` | `trades` UPDATE (close) | paper via `trades_ml_id` / live | n/a |
| `execution.py:98` | `live_trade_log` INSERT | live only (`TEST_MODE`-guarded) | n/a |

Mechanism: `trades` is the ML corpus; both branches INSERT into it deliberately. The close-side
ML write (`:1217` paper, `:1371` live) is why all 9,521 rows show closed. The "contamination" is
simply the absence of a discriminator on a deliberately-combined table.

## §3 Historical classification

Every `trades` row (n=9,521) classified on `(mint, |entry_time − created_at| < 5s)` against
current `paper_trades`, `paper_trades_archive_20260421` (the 2026-04-21 DASH-RESET archive), and
`live_trade_log` (TX_SUBMIT events carry on-chain signatures).

| Class | n |
|---|---:|
| paper — matches archive | 6,612 |
| paper — matches current `paper_trades` | 2,868 |
| live — matches `paper_trades.trade_mode='live'` | 6 |
| live — no paper match, **all 35 confirmed via `live_trade_log` TX_SUBMIT** | 35 |
| **total** | **9,521** |

**genuine_live: 41 · contaminated_paper: 9,480 · unclassifiable: 0.**

- The **35** no-match rows (`trades` ids 5093–5119, 5194–5202) are the v3/v4 live-trial trades —
  created in the 2026-04-16 trial window, every one carrying a TX_SUBMIT signature in
  `live_trade_log`. They have no `paper_trades` mirror because they predate the DASH-ENTRY-001
  live→`paper_trades` mirror code. **Sum `pnl_sol` = −3.3609 SOL, 9 wins / 35 (25.7% WR).**
- Of the **6** `paper_trades`-matched live rows: **1** (`trades` id 6596 / `paper_trades` id
  6580, mint `yh3n441…`) is the one genuine on-chain round-trip (signatures present, 2
  TX_SUBMIT). The other **5** (ids 5184/5202/5383/6041/6388 ↔ paper 6575–6579) are
  **reconcile-residual paper closures** — `trade_mode='live'` in `paper_trades` but with NULL
  signatures and no real on-chain execution, exactly as documented in CLAUDE.md. They are tagged
  `'live'` in `trades` for consistency with the authoritative `paper_trades` table; this audit
  documents what they actually are.

**The isolated real-money result:** the 36 genuine on-chain live rows (35 trial + id 6596) sum
to **≈ −3.36 SOL**. This **cross-validates** the ~3.4 SOL on-chain wallet drawdown (5.0 → ~1.6
SOL) recorded in CLAUDE.md's `1b40df3` forensics — confirming `trades.pnl_sol` for the trial
rows is a reliable record of the live trial outcome.

## §4 The fix + verify output

**Code (`services/bot_core.py`):** both `INSERT INTO trades` statements gain a `trade_mode`
column — literal `'paper'` in the paper branch (`if TEST_MODE`), `'live'` in the live branch
(`else`). The branches already gate on `TEST_MODE`, so the literals are unambiguous; no
trade-decision logic touched. asyncpg param slots unchanged (8 params, 2 literals).

**Schema (`services/db.py`):** `trade_mode TEXT DEFAULT 'paper'` added to the `trades`
`CREATE TABLE` (fresh deploys) and as an idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS`
in `_init_tables` (existing deploys — no-op once present).

**Migration (`migrations/002_add_trade_mode_to_trades.sql`):** one-time backfill — mirror
`trade_mode` from current `paper_trades`, then from the archive, then `'live'` for the 35
trial rows (guarded by `EXISTS` in `live_trade_log`). Applied this session.

**Verification (`verify_logging_fix.py`, output in `.tmp_live_logging_audit/verify_output.txt`):**
the prompt's verify spec assumed a misrouting bug ("lands only in paper_trades"); since the real
fix is a discriminator on a deliberately-combined table, the verify was adapted to prove the
real behaviour change. All checks PASS on iteration 1:
- (a) post-fix paper-branch INSERT SQL → `trade_mode='paper'`;
- (b) post-fix live-branch INSERT SQL → `trade_mode='live'` — both inside a rolled-back
  transaction (0 rows persisted; zero production impact);
- (c) post-migration: column exists, 0 NULLs, split exactly **paper 9,480 / live 41**,
  spot-check `trades.id=6596` → `'live'`.

## §5 Historical-row tagging (TAG, not purge)

Per the prompt's Phase 4, historical rows were **tagged, not purged.** The migration's backfill
*is* the tagging — every one of the 9,521 rows now carries `trade_mode`. No rows were deleted or
modified beyond the new column. `paper_trades` (the clean table) was not touched at all.

## §6 Deploy record + post-deploy verification

Single `git push` of: `services/bot_core.py`, `services/db.py`,
`migrations/002_add_trade_mode_to_trades.sql`, plus doc updates. Triggers a Railway redeploy of
bot_core. db.py changes are additive + idempotent — safe for all services that import it. The
migration backfill was applied to the DB *this session* (pre-push), so historical tagging is
already live regardless of deploy timing; the code push only governs *forward* tagging.

Railway deploys take 15-20 min — container restart confirmed via Railway MCP before post-deploy
verification. Post-deploy checks (per §7 of the session prompt): (i) clean container startup —
no RuntimeError / import error; (ii) within ~30 min of trade flow, confirm new SD-paper trades
land in `trades` with `trade_mode='paper'` and no new `trade_mode='live'` rows appear while
`TEST_MODE=true`. Container-restart confirmation + post-deploy routing-check results are
recorded in this session's `STATUS.md` and `MONITORING_LOG.md` entries.

## §7 Recommendation on purging contaminated rows

**Do not purge.** The 9,480 paper rows in `trades` are not erroneous — `trades` is the ML
corpus and always contained paper rows by design. With `trade_mode` now present, ML-training
queries and analyses can simply filter (`WHERE trade_mode='paper'` or `'live'`). Purging would
destroy 9,480 rows of legitimate ML training data to solve a problem that a `WHERE` clause now
solves. The only rows one might *consider* separating are the 5 reconcile-residuals, but they
are consistently tagged across `trades` and `paper_trades` and documented — leave them.
**Recommendation: keep all rows; filter by `trade_mode`. No purge.**

## §8 V5A relaunch implications

Positive. Before this fix, a V5A relaunch would have continued writing live trades into `trades`
with no way to separate them from the paper corpus — every post-relaunch analysis of "what did
live actually do" would have required the same painful cross-reference this audit just did.
Now: live rows self-identify. ML training can choose to include/exclude live rows deliberately
(they carry real fee/slippage reality that differs from the paper model — see FEE-MODEL-001).
Not a V5A blocker; a V5A *enabler*. Recommend ML-training queries adopt explicit
`trade_mode` filtering as a follow-up (see §9).

## §9 Open questions

1. **ML-training filter policy.** `ml_model_accelerator.py` reads from both `trades` and
   `paper_trades` with no `trade_mode` filter. Should live rows be included in the paper-model
   training corpus, excluded, or weighted? Now *possible* to decide; not decided here (out of
   scope — would touch ML logic). Suggested follow-up: **ML-TRAINING-MODE-FILTER-001**.
2. **`paper_trades` live rows beyond the 6.** Only 6 live rows exist in `paper_trades`; the 35
   trial trades were never mirrored there (predate DASH-ENTRY-001). Should the 35 be
   back-mirrored into `paper_trades` for dashboard completeness? Low value (trial is long over);
   flagged, not recommended.
3. **`live_trade_log` 9,069 ERROR rows** — out of scope here, but that 99.2%-error ratio on the
   v3/v4 trial is a separate known story (sell-storm / routing). No action this session.
