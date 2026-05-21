# V5A-FLIP-002-V3 prep notes — key changes vs V5A-FLIP-001-V2

**Prepared by:** V5A-FIXES-001 (this session)
**Purpose:** reference for Jay/chat-side to assemble the V5A-FLIP-002-V3 prompt before pasting it into a new CC session (Thursday evening AEST D-S5 window per `docs/findings/V5A_GO_LIVE_DECISIONS.md`).

**This document is reference notes — NOT a complete session prompt.** It captures only the deltas vs V2 driven by the incident + this session's fixes.

---

## What changed structurally (deployed this session)

| Item | Status | Commit |
|---|---|---|
| `V5A-FLIP-RECONCILE-FILTER-001` (Bug 1) | ✅ DEPLOYED | `f3591eb` 2026-05-21 ~14:42 UTC |
| `V5A-FLIP-CONTAMINATION-CLEANUP-001` (14 rows tagged) | ✅ DONE | DB-only — `paper_orphan_at_flip_v5a_001` tag on ids 9940-9953 |
| `V5A-FLIP-CLOSE-TRADE-MODE-001` (Bug 2) | ✅ DEPLOYED | `3c50520` 2026-05-21 |
| `BOT-CORE-EMERGENCY-STOP-LIVENESS-001` (Bug 3) | ⚠ NON-BUG | per-decision check already at `bot_core.py:604-609`; closed as not-needed |

---

## What V5A-FLIP-002-V3 must add vs V2 (the actual incident-driven deltas)

### Delta 1 — Phase 1 mirror the reconciler's EXACT query

V2's Phase 1 step 10 (env baseline) did NOT verify against the reconciler's actual SQL — it queried `paper_trades WHERE entry_time IS NOT NULL AND exit_time IS NULL` which returned 0 while the reconciler (in live mode) reads `trades WHERE closed_at IS NULL`. The mismatch let the flip proceed despite 14 orphans waiting in `trades`.

**V3 must add step 10.5 BEFORE the flip:** execute the reconciler's EXACT live-mode SQL and STOP if result > 0.

```python
# In V3 Phase 1 step 10.5 — runs against live DB before any env change.
rows = await pool.fetch(
    "SELECT mint, personality, trade_mode FROM trades "
    "WHERE closed_at IS NULL AND trade_mode='live'"
)
# Per V5A-FLIP-RECONCILE-FILTER-001 (deployed 2026-05-21), the reconciler in
# live mode now adds AND trade_mode='live' filter — this query mirrors the new
# behavior. Expected: 0 rows. If > 0, real live trades from prior incidents
# are still open in the corpus — STOP and investigate before flip.
```

Note: post-Bug-1, the previously dangerous query `trades WHERE closed_at IS NULL` (no mode filter) is no longer the one the reconciler runs. So mirroring the new query is the correct verification.

### Delta 2 — Phase 3 add explicit paper_trades-OPEN + trades-OPEN check after CLEAN-003

V2's Phase 3 (CLEAN-003 / `live_flip_prep.sh`) only cleared Redis keys, not Postgres rows. V3 must add a Postgres reconcile step.

For belt-and-braces (independent of Bug 1 fix):

```sql
-- Sanity check 1: paper_trades with open paper rows
SELECT COUNT(*) FROM paper_trades WHERE exit_time IS NULL AND trade_mode='paper';
-- Sanity check 2: trades-table open rows (any mode)
SELECT COUNT(*) FROM trades WHERE closed_at IS NULL;
-- Sanity check 3: trades-table open LIVE rows specifically (what the new reconciler loads)
SELECT COUNT(*) FROM trades WHERE closed_at IS NULL AND trade_mode='live';
```

V3 Phase 3 must capture all three counts. The third one is the **load-bearing** check — if > 0, the live reconciler WILL load these and they should be expected real live positions or investigated before the flip. Sanity checks 1+2 are informational (post-Bug-1 they don't gate the flip but worth knowing).

### Delta 3 — Phase 5 verification: drop reliance on heartbeat.emergency

V2's Phase 5 (drain) relied on `bot:emergency_stop=true` + heartbeat reflection to confirm halt. But heartbeat reflects in-memory `self.emergency_stopped`, not the Redis flag. The Redis-flag check IS honored at the per-decision gate (services/bot_core.py:604-609), but heartbeat stays false until risk_manager fires emergency_stop directly.

**V3 must change Phase 5 verification to:** before flip (T-5min) capture `SELECT MAX(id) FROM paper_trades WHERE trade_mode='paper'`. At T-30s, capture again. If the max id changed, paper bot opened a new position despite the drain — STOP. If unchanged, drain is effective.

### Delta 4 — Phase 6 retry-time env reconciliation list update

V5A-FLIP-001-V2 noted `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` reconciliation needed. V5A-FLIP-001-V2 set it then reverted on rollback to 4.0. V3 must re-set per D-S3:
- `DAILY_LOSS_LIMIT_SOL = 1.5`
- `MAX_POSITION_SOL = 0.10`
- `MAX_SD_POSITIONS = 5`

(Same as V2 — unchanged here, but worth re-flagging since rollback reverted these.)

### Delta 5 — Phase 8 unchanged in spirit, harden in evidence

V2's Phase 8 check (Startup reconciliation: 0 open positions in DB) is the right safety net. With Bug 1 fix landed, the live reconciler's "0" count is now defended by trade_mode filter. V3 Phase 8 still checks for "0" but also captures the new `[RECONCILE]` log line which records `current_mode` + `table` + count — explicit evidence the new filter is on the loaded source.

```python
# V3 Phase 8 step 1: post-restart log check
# Expected logs (in this order, paper mode):
#   [RECONCILE] mode=paper, table=paper_trades, loaded N position(s)
#   [RECONCILE] mode=paper, table=paper_trades, restored N position(s) into self.positions
#   Startup reconciliation: N open positions in DB
#   Bot Core ready — managing 3 personalities
# In live mode post-flip:
#   [RECONCILE] mode=live, table=trades, loaded 0 position(s)  ← KEY CHECK
#   Startup reconciliation: 0 open positions in DB
# If [RECONCILE] log shows mode=live but loaded N > 0, STOP — investigate the N rows.
# Pre-Bug-1 this would happen routinely (the 14 incident); post-Bug-1 it should
# only happen if a real live trade is genuinely open.
```

### Delta 6 — Auto-rollback triggers (unchanged but worth restating)

V2's STOP-Rollback triggers all remain valid:
- RuntimeError at startup → revert
- EMERGENCY_STOP trip → revert
- Sell-storm (any mint > 8 errors) → revert
- HIBERNATE rejection → revert
- Drawdown log > 5% on fresh restart → revert

V3 should add ONE additional rollback trigger:
- `[ORIGIN_MISMATCH]` log appearing post-flip → indicates Bug 1 regression → revert

(Bug 2 logs this WARNING when the close path detects a paper-origin position being closed in live mode. If it ever fires post-flip, something has gone wrong with Bug 1 and we should rollback.)

### Delta 7 — Wallet baseline unchanged

V5A-FLIP-001-V2 confirmed wallet 5.064 SOL on-chain throughout. PC1 SATISFIED. No top-up needed for V5A-FLIP-002-V3.

---

## Operational summary — what makes V5A-FLIP-002-V3 safer than V2

| Risk in V2 | Mitigation in V3 (via this session) |
|---|---|
| 14 phantom paper rows in trades loaded by live reconciler | Bug 1 deployed — live reconciler now filters `trades WHERE closed_at IS NULL AND trade_mode='live'`. The 14 incident rows have closed_at set; future paper orphans skipped. |
| Defensive INSERT wrote trade_mode='live' for phantom closes | Bug 2 deployed — defensive INSERT queries trades.trade_mode for origin. Phantom closes would now be tagged 'paper' + log [ORIGIN_MISMATCH]. |
| 14 historical contaminated rows pollute live analytics | Cleanup done — ids 9940-9953 tagged `correction_method='paper_orphan_at_flip_v5a_001'`. Live-mode analytics can filter them out via `correction_method NOT LIKE 'paper_orphan%'`. |
| Phase 1/3 verification missed the trades-table orphans | V3 adds explicit reconciler-mirror queries (Delta 1, 2). |
| Phase 5 drain verification looked at heartbeat (in-memory) instead of actual position-opens | V3 uses `MAX(paper_trades.id)` delta as the drain effectiveness signal (Delta 3). |

---

## Pre-Phase-1 verification checklist for V3

Before any session writes V5A-FLIP-002-V3, confirm:
- [ ] Both Bug 1 and Bug 2 are live on `main` (commits `f3591eb` and `3c50520`).
- [ ] `[RECONCILE]` log lines appear in current bot_core logs on container restart.
- [ ] Wallet still 5.064 SOL on-chain (re-verify via Helius `getBalance`).
- [ ] No orphan rows match the new reconciler query: `SELECT COUNT(*) FROM trades WHERE closed_at IS NULL AND trade_mode='live'` returns 0.
- [ ] No phantom `paper_orphan_at_flip_v5a_001` rows added since this session (count stays at 14).

If all green, V5A-FLIP-002-V3 is GO for the next D-S5 window.

---

## What V3 must NOT change vs V2

- Wallet preconditions (PC1 already SATISFIED; 5.064 SOL).
- Observation/eval gate (PC2 already SATISFIED).
- C1 fill-time MC ceiling (PC3 already SATISFIED).
- Sizing ladder (D-S6: 0.10 SOL × 5 positions for first 24h).
- Active observer commitment (D-S7: 4-6h post-flip).
- Market-mode check method (D-S4: manual judgment; NORMAL/DEFENSIVE/AGGRESSIVE all GO; only HIBERNATE aborts).
- Flip timing window (D-S5: Wed/Thu AEST evening 18:00-21:00 Sydney).
- Wallet-target reconciliation (~5 SOL per D-S3 — confirmed unchanged).

End of V3 prep notes.
