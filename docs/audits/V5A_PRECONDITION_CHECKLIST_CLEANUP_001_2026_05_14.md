# V5A-PRECONDITION-CHECKLIST-CLEANUP-001 — audit

**Date:** 2026-05-14
**Type:** Docs cleanup with live-state verification. NO services/* code change, NO env change, NO Redis writes (read-only on live state), NO deploy.
**Trigger:** chat-side state synthesis on 2026-05-14 found `AGENT_CONTEXT.md` §6 "V5a preconditions outstanding" badly drifted: ~1-month-old framings ("Sessions A-D", "session-E snapshot"), config has changed 5+ times since, +1 new V5A blocker (LIVE-MODE-FILTER-PARITY-001-V2) added 2026-05-14 but checklist was not otherwise refreshed.

---

## §1 What was verified and how

| Check | Tool | Result |
|---|---|---|
| Trading wallet on-chain balance | Helius MCP `getBalance(4h4pst…ii8xJ)` | **0.064095633 SOL** — UNCHANGED since 2026-04-21 |
| `TEST_MODE` on bot_core | Railway MCP `list-variables bot_core --kv` | `TEST_MODE=true` ✓ |
| `TEST_MODE` on signal_aggregator | Railway MCP | `TEST_MODE=true` ✓ |
| `BOT_CORE_FILL_MC_CEILING_USD` (C1 retune) | Railway MCP | `1000` on bot_core (matches §2 of AGENT_CONTEXT) |
| `SD_MC_CEILING_USD` (deploy precondition 4) | Railway MCP | `3000` on signal_aggregator ✓ |
| `SD_EARLY_CHECK_SECONDS` (TUNE-009 deferred) | Railway MCP | `60` on bot_core ✓ |
| `ML_THRESHOLD_BOT_CORE_SD` (BOT-CORE-ML-GATE-001) | Railway MCP | `40` on bot_core ✓ |
| `ANALYST_DISABLED` | Railway MCP | `true` on signal_aggregator ✓ |
| `NANSEN_DRY_RUN` (replaces `nansen:disabled` Redis key) | Railway MCP | `TRUE` on signal_aggregator ✓ |
| `market:mode:override` Redis key | Redis MCP `get` | **Key not found** |
| `nansen:disabled` Redis key | Redis MCP `get` | **Key not found** |
| `market:mode:current` (automated) | Redis MCP `get` | `NORMAL` ✓ |
| `bot:status` heartbeat | Redis MCP `get` | `RUNNING`, portfolio 39.73 SOL, 0 open positions, consecutive_losses=1, timestamp 2026-05-14T12:56:38Z UTC |
| LIVE-MODE-FILTER-PARITY-001-V2 status | ZMN_ROADMAP Decision Log + STATUS.md | NEW Tier-1 🟡 V5A blocker added 2026-05-14; not in §6 yet |

All checks completed in a single parallel call cluster. No STATUS UNKNOWN items.

---

## §2 Old-vs-new diff of §6 (item by item)

| Old item | New status | Action |
|---|---|---|
| `~3 SOL transfer to trading wallet` `[ ]` | PC1 `[ ]` | KEPT, light reframe with verified 2026-05-14 balance + drop "session-E snapshot" anchor |
| `24-48h paper observation (Sessions A-D)` `[ ]` | PC2 `[ ]` | REFRAMED — anchored to post-C1 deploy (2026-05-13 03:38:37Z UTC) through combined eval ≥2026-05-27 |
| `Confirm SD_EARLY_CHECK relax verdict` `[ ]` | — | REMOVED — TUNE-009 permanently deferred; no relax pending; not a V5A gate. Continues to be tracked in §7. |
| `Resolve SD_MC_CEILING_002` `[x]` | "Completed preconditions" `[x]` | MOVED to historical subsection (verified `SD_MC_CEILING_USD=3000` live) |
| `Land LIVE-FEE-CAPTURE-002 (Path B)` `[x]` | "Completed preconditions" `[x]` | MOVED to historical subsection; §7 stale carry flagged inline `<!-- STALE: ... -->` |
| `Renew Redis daily TTLs (market:mode:override, nansen:disabled)` `[ ]` | folded into PC4 + REMOVED for nansen | `nansen:disabled` REMOVED (mechanism migrated to env `NANSEN_DRY_RUN=TRUE`); `market:mode:override` FOLDED into PC4 flip-time check (current state: automated NORMAL, no override needed unless calc lands non-NORMAL at flip time) |
| `V5a flip: TEST_MODE=false` `[ ]` | PC4 `[ ]` | KEPT as terminal action; expanded with pre-flip self-check list (CLEAN-003 script + Redis NORMAL check + DAILY_LOSS_LIMIT + sell-storm breaker) |
| (not present) | PC3 `[ ]` | ADDED — `LIVE-MODE-FILTER-PARITY-001-V2`, NEW Tier-1 🟡 blocker per ROADMAP 2026-05-14 + audit §8.2 open question |
| (not present) | "Related milestones" | ADDED — `ML_THRESHOLD_RETUNE_002` (≥2026-05-19, paper-only, orthogonal) + combined eval (≥2026-05-27, gates PC2) — explicitly labelled as parallel work, NOT preconditions |

---

## §3 STATUS UNKNOWN items + what check they need

None. Every old precondition had at least one verifiable signal from Railway env / Redis / on-chain at this session's verification window (2026-05-14 ~12:57 UTC).

---

## §4 Broader AGENT_CONTEXT staleness flagged (STOP-C territory)

While verifying §6 I noticed one definitively stale element:

- **§7 "Known unresolved (Tier-1 carry)" row `LIVE-FEE-CAPTURE-002 (Path B) 📋 V5a-blocking-but-degradable`** — this row contradicts the ZMN_ROADMAP Decision Log 2026-05-01 entry ("✅ DEPLOYED, closes V5a parity-of-truth precondition") and the §6 [x] DEPLOYED carry-forward. The row in §7 is a stale carry from before the 2026-05-01 deploy was landed. **Per STOP-C, NOT silently rewritten this session** — flagged inline in §6 with `<!-- STALE: ... -->` and recorded here. Recommend a separate small `AGENT_CONTEXT-SECTION-7-SYNC` session to clean up §7 row statuses against the Decision Log without scope creep.

No other §3 / §5 / §6.5 / §6.6 / §6.7 / §6.8 staleness surfaced during the §6 verification pass. §3 wallet balance was confirmed unchanged at 0.064095633 SOL; §6.6 V5A-GO-NO-GO is a 2026-05-01 audit snapshot (correctly point-in-time) and is referenced from the new PC1/PC2/PC4 as historical context, not as live truth.

---

## §5 The current honest V5A blocker count

**4 outstanding V5A blockers** (PC1-PC4 in the rewritten §6):
1. **PC1** — `~3 SOL transfer to trading wallet` (Jay action). Wallet 0.064 SOL verified 2026-05-14.
2. **PC2** — Post-C1 observation through combined `STOP-LOSS-20-RUG-FILTER-EVAL-001` + `NO-MOMENTUM-90S-EVAL-001` at ≥2026-05-27. (~33h elapsed at session start of T+14d window.)
3. **PC3** — `LIVE-MODE-FILTER-PARITY-001-V2` land. Per LIVE_MODE_FILTER_PARITY_001 audit §8.2 + ROADMAP/STATUS 2026-05-14. Recommended Option A scope: gate in `bot_core.py` live branch before `execute_trade` using `self._get_token_price(mint)`, mirroring `paper_buy`'s fill-time MC + env + reject-log + Redis counter.
4. **PC4** — V5A flip itself (`TEST_MODE=false` on bot_core). Terminal action; gated on PC1-PC3 + flip-time CLEAN-003 pre-flight + `market:mode:current=NORMAL` verification.

**2 completed (historical, verified, preserved in §6 historical subsection):**
- SD_MC_CEILING_002 (deployed 2026-04-30, verified live)
- LIVE-FEE-CAPTURE-002 (Path B) (deployed 2026-05-01, ROADMAP-confirmed)

**3 removed/folded (audit trail in §6):**
- `SD_EARLY_CHECK relax confirmation` — TUNE-009 deferred permanently, no V5A gate
- `nansen:disabled` Redis renewal — migrated to env var `NANSEN_DRY_RUN=TRUE`
- `market:mode:override` Redis renewal — folded into PC4 flip-time check (currently NORMAL automatically)

**Related parallel milestones (NOT V5A preconditions):**
- `ML_THRESHOLD_RETUNE_002` (≥2026-05-19, paper-only at flip, orthogonal)
- Combined eval (≥2026-05-27, gates PC2)

---

## Outputs

- `AGENT_CONTEXT.md` — §6 rewritten; header refreshed; one inline `<!-- STALE: ... -->` flag on `LIVE-FEE-CAPTURE-002` referencing §7 staleness.
- This audit doc.
- `ZMN_ROADMAP.md` — Decision Log entry.
- `MONITORING_LOG.md` — entry.
- `STATUS.md` — session prepend.
- `.tmp_v5a_cleanup/` (gitignored) — PROGRESS.md, 01_verification.md, 02_classification.md.

No code, no env, no Redis writes, no deploy. Single push.
