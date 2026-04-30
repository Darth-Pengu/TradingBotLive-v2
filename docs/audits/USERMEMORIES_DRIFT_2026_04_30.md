# userMemories drift report — 2026-04-30

**Session:** SESSION_E_PERSISTENCE_HARDENING (chain A→B→C→D→E)
**Author:** Claude Code
**Scope:** Document the gap between chat-side userMemories claims and actual system state, as observed during the 4-day audit arc 2026-04-27 → 2026-04-30. **Read-only deliverable**; informs `CLAUDE.md` "Persistence Convention" + future memory-management policy.

---

## §1 Drift table (claims vs reality)

userMemories from prior chats was the load-bearing source of "what is currently deployed" until ENV-AUDIT-2026-04-29. Each row below contrasts a userMemories claim (carried in chat-side memory at the start of the 2026-04-29 audit cycle) against the empirical reality discovered.

| userMemories claim | Reality (post-audits) | Drift type |
|---|---|---|
| TEST_MODE=false (live mode) | **TEST_MODE=true on bot_core since 2026-04-25 EMERGENCY_STOP**; only `treasury` carries `false` | State-stale (event happened but memory not updated) |
| Breakeven lock removed; trail `[0.30, 0.35]` | Lock removed ✅ but trail is **5-tier** `[[0.10,0.30],[0.50,0.25],[1.00,0.20],[2.00,0.15],[5.00,0.12]]`, not 1-tier `[0.30, 0.35]` | Shape distortion (intent right, structure wrong) |
| TPs flattened `[2.0,0.2][5.0,0.375][10.0,1.0]` | bot_core `STAGED_TAKE_PROFITS_JSON` matches exactly | ✅ accurate |
| MIN_POSITION_SOL=0.05 | bot_core=0.05 (matches); other services = 0.10 (vestigial — services that don't size positions but carry stale env values) | Service-scope ambiguity |
| Trading wallet ~1.6 SOL | **0.064 SOL on-chain** since 2026-04-21 1.5 SOL outgoing transfer (Branch 1 confirmed) | State-stale (3-9 days behind reality depending on when memory was last refreshed) |
| ML threshold = 40 | **signal_aggregator=65, bot_core=40, web=45**; AGGRESSIVE_PAPER_TRADING bypasses SA gate for paper rows; effective gate < 40 for paper. The "40" was the bot_core value — never the gate value | Service-scope ambiguity + unstated mechanism |
| 246 trades / zero wins in 11-17 AEDT (dead zone) | Older window; 4-day audit (2026-04-22→25) shows **AEDT 12-15 is profitable** (+0.54 SOL on n=62, 43.5% WR), AEDT 18-21 is the actual worst window. CLAUDE.md note about 11-17 AEDT dead zone is mis-windowed vs current data | Sample-stale (analysis from old window) |
| MAX_SD_POSITIONS=20 | bot_core=20 (matches); other services = 2-3 (vestigial display-only) | ✅ accurate (with vestigial-elsewhere caveat) |
| ANALYST_DISABLED=true | signal_aggregator=true (matches); plus code-level fix at `_process_graduations` (ANALYST-DISABLE-002 `9d6e95c`) | ✅ accurate (with code-level fix not in memory) |
| MC ceiling proposal: $5k cut | Session C deployed at **$3k** (data-revised tighter cut) but ⏪ rolled back due to gate-placement design flaw | ✅ valid evolution (with design-flaw discovery as new finding) |
| `corrected_pnl_sol` is authoritative; ML uses it | **Was NULL on every row** until Session B fix (2026-04-30). `realised_pnl_sol` is now authoritative; corrected is `pass_through` copy on paper, `live_estimated_v1` on id 6580 | Direction-wrong (the rule pointed at a column never populated for any current row) |
| Wallet move 5.0 → ~1.6 SOL via real trades | Accurate for 2026-04-16/17 v3/v4 trial. Did NOT cover the **2026-04-21 1.5 SOL outflow** to `7DSQ3ktY...AgUy` (now appended to CLAUDE.md per WALLET-DRIFT investigation) | State-stale (single-event gap) |

**Summary:** of 13 claims surveyed, 4 were stale by some axis (state, sample, scope, or direction), 4 were accurate, and the remaining 5 had nuance (vestigial values elsewhere, mechanism caveats, code-level extensions).

---

## §2 Why drifts happen

1. **userMemories is a manual carry written at the end of conversations.** It snapshots what the conversation discovered, not the live system state. As soon as the conversation ends, the snapshot starts decaying.

2. **State changes outside the chat don't back-propagate.** Manual env var edits via Railway UI, scheduled deploys, on-chain transactions, and external system actions (e.g., the 2026-04-21 1.5 SOL transfer) don't get noticed by future chats unless someone surfaces them.

3. **Aggregate analysis from one window can stay in memory long after the window is no longer relevant.** The "246 trades / 11-17 AEDT" claim was true for an older window but became misleading as the strategy and market regime evolved.

4. **Service-scope is hard to capture in a 1-line memory.** `ML_THRESHOLD_SPEED_DEMON=40` is "true" if you're looking at bot_core, but the gate is at signal_aggregator (=65). userMemories tend to drop the service qualifier.

5. **Mechanism interactions are easy to overlook.** `AGGRESSIVE_PAPER_TRADING=true` bypasses the SA-side ML gate for paper, making the documented "40 floor" effectively lower for paper. This is a code-path interaction not reflected in any single memory.

6. **userMemories has no self-validation.** It doesn't periodically check itself against reality. ENV-AUDIT-2026-04-29 was the first systematic check in the audit cycle; it found 3 new blockers in 30 minutes that had been carrying unresolved.

---

## §3 Mitigation

### Landed this session (Session E)

1. **`AGENT_CONTEXT.md` rewritten** as the authoritative current-state file (this session). New chats read it first; stale-staleness is bounded by a "last updated" header. Refresh after any state change.

2. **`ZMN_ROADMAP.md` Decision Log added** (this session). Records *why* each lever has its current shape — separates the work-item catalogue from the judgement trail.

3. **`CLAUDE.md` "Persistence Convention" added** (this session). Codifies the rule: userMemories is NOT a source of truth. Verify against Railway env / Redis / DB / on-chain before acting on remembered config claims.

### Recommended (not landed)

4. **Periodic drift reports.** Run an ENV-AUDIT-style read-only sweep weekly, OR after any audit cycle (like this one), and check for new drifts. Update AGENT_CONTEXT + Decision Log accordingly.

5. **Pre-action verification.** Before recommending or acting on a remembered config value, grep / Railway-list / Redis-get to confirm. The `ENV_AUDIT_2026_04_29.md §5` drift table is the model — every claim got cross-referenced against ground truth.

6. **Memory hygiene at session end.** When updating userMemories at the end of a session, prefer pointers to canonical sources over verbatim values. "MIN_POSITION_SOL=0.05 on bot_core" is better than just "MIN_POSITION_SOL=0.05" because it identifies the service. Even better: "see AGENT_CONTEXT §2 for current sizing config".

### Anti-pattern to avoid

7. **Don't write memories that go stale within a week.** Specific env values, current trade counts, current PnL, current TTLs — all of these decay rapidly. Keep memories at the level of *patterns* and *constraints* (e.g., "live flips need explicit rollback steps" survives; "wallet at 1.6 SOL" doesn't).

---

## §4 Drift severity classification

| severity | what it means | examples this cycle |
|---|---|---|
| 🔴 ACTION-CHANGING | acting on the memory would cause regression or wrong action | "TEST_MODE=false" claim during paper-only window (would have caused live actions). "corrected_pnl_sol authoritative" (analysis would silently fall back to NULL). |
| 🟡 SCOPE-CONFUSION | memory true on one service, drifts on others | ML threshold (true on bot_core, drifts elsewhere). MIN_POSITION_SOL (true on bot_core, vestigial elsewhere). |
| 🟢 SAMPLE-STALE | memory true at writing-time, but world moved on | "AEDT 11-17 dead zone". Wallet figures. |
| 🔵 NUANCE-MISSING | memory directionally correct but missing mechanism | "AGGRESSIVE_PAPER bypasses gate" (mechanism missing from threshold memory). "TPs flattened" (correct but missing the round-trip fee implication). |

**This cycle's tally:**
- 🔴 ACTION-CHANGING: 2 (TEST_MODE state, corrected_pnl_sol direction)
- 🟡 SCOPE-CONFUSION: 2 (ML threshold, MIN_POSITION_SOL)
- 🟢 SAMPLE-STALE: 2 (dead zone window, wallet figures)
- 🔵 NUANCE-MISSING: 1 (AGGRESSIVE_PAPER mechanism)

The 🔴 cases are the load-bearing argument for the Persistence Convention. They aren't theoretical — both could have caused real damage if a session had acted on them without verification.

---

## §5 What we DID right this audit cycle

1. **ENV-AUDIT-2026-04-29 was triggered explicitly** as a "ground-truth sweep" before stacking new tuning. That's the right pattern — do a verification audit before any chain of state-changing sessions.

2. **WALLET_DRIFT_INVESTIGATION_2026_04_29** treated the discovered drift as a blocker, not a footnote. Halt-and-investigate is the right response to a 1.5 SOL unaccounted gap.

3. **Each session in the chain (A-E) explicitly verified pre-conditions** before making changes — bot status, signals:scored LLEN, TEST_MODE, etc. None acted on memory alone.

4. **Session A's deferral verdict** (Option Gamma) is the *opposite* of memory-driven action — empirical evidence (dead-trade pnl_pct distribution) trumped the chain prompt's hypothesis. Memory said "the check is killing winners"; data said "no, it's killing losers cleanly". Data won.

These are the positive instances of the Persistence Convention in action, even before it was codified.

---

## §6 Open question — when CAN you trust userMemories?

Trust userMemories for:
- **Patterns and conventions** (e.g., "ALWAYS use git push, never `railway up` for deploy"). These don't decay because they're rules-of-engagement.
- **Operating principles** (e.g., "one lever per session"). Same.
- **Pointers to canonical sources** (e.g., "the trading wallet address is in CLAUDE.md"). Pointers decay slower than values.

DO NOT trust userMemories for:
- **Specific env values** (decay: ~1-7 days).
- **Current trade counts / PnL** (decay: ~hours).
- **Current Redis TTLs** (decay: hours).
- **Current wallet balances** (decay: arbitrary, depends on activity).

When in doubt, verify against AGENT_CONTEXT.md (refreshed at end of each state-changing session) or run a fresh sweep.

---

## §7 Next-cycle recommendations

1. **Weekly drift check** (or after every 3-4 state-changing sessions): re-run a slimmed-down ENV-AUDIT, update AGENT_CONTEXT, append to Decision Log if levers changed.
2. **Add `bot_core:health` heartbeat** (OBS-014) so AGENT_CONTEXT can show a live "is the bot heartbeating?" indicator without log inspection.
3. **Add a freshness measure** to AGENT_CONTEXT.md — auto-warn if `last_updated` > 72h.
4. **Promote ENV_AUDIT_2026_04_29 §5 drift table format** as a recurring deliverable. Every drift cycle should produce one.
