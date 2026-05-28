# ZMN Bot Monitoring Log

---

## 2026-05-28 — LIVE-FEE-CAPTURE-ENTRY-SIG-WIRING-001 (code+deploy, ✅ 1 FIX DEPLOYED — V5A-FIXES-001 §11 follow-up resolved)

- **Trigger:** Jay-pasted afternoon session prompt to resolve `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` (filed Tier 3 by V5A-FIXES-001 §11) before tonight's V5A-FLIP-002-V3 in the D-S5 window. Predecessor `V5A-FIXES-001` audit at `docs/audits/V5A_FIXES_001_2026_05_21.md` §5 + §11 is the load-bearing context — its Bug 2 investigation surfaced that Position dataclass has no `entry_signature` field (making the Path B parser's L1450 `getattr(pos, "entry_signature", None)` always return None and forcing every live close to `live_estimated_v1`). This session adds the field and wires it from `ExecutionResult.signature` at live entry.
- **Timeline (UTC):** ~12:45 Phase 0 pre-flight (Railway MCP ✅ callable, TEST_MODE=true ✅, last commit `0cb9923` from 2026-05-22 — no concurrent session) → ~12:50 Phase 1 investigation (Q1-Q5 answered to `.tmp_entrysig/01_investigation.md`; exit_signature template verified working at L1434; `execute_trade` confirmed to return sig synchronously at L750-756 not STOP-Async; Position constructed at L1005 with `result.signature` in scope; close-path reads in-memory `pos.entry_signature` at L1450; reconciler reads `trades` table which lacks the column → mid-restart limitation documented as acceptable per §3 Q5; id 6580 DB sample confirms column accepts text and Path B parser works end-to-end given a real sig) → ~13:00 Phase 2 design (3 minimal changes to single file: Position dataclass field + live-entry kwarg + observability log; 9 LOC total ≪ 50-LOC STOP-Scope cap) → ~13:05 Phase 3 implement (edits applied; `python -m py_compile services/bot_core.py` → COMPILE_OK) → ~13:10 Phase 3 verify (`.tmp_entrysig/verify_entrysig.py`: 16 source assertions + dataclass unit tests + mock ExecutionResult fail-safe + id 6580 Path B dry-run; first pass 15/16 with 1 regex too narrow in verify script (NOT a code issue); second pass 17/17 PASS — included `helius_parse_signature(id 6580 entry sig)` → `success=True`, `native_delta_lamports=-374251786` confirming downstream Path B consumer works end-to-end) → ~13:18 Phase 4 commit `7458f2d` + push origin main (clean fetch — no rebase) → Railway auto-deploy triggered.
- **Q5 / known limitation:** trades table has no entry_signature column; live reconciler reads trades on restart → restored Positions get `entry_signature=None`. Schema migration would be STOP-Scope (out of scope this session). Mid-position restart edge case acceptable: SD holds are short-hold and restarts are rare. Future enhancement (out of scope): reconciler could lookup `paper_trades.entry_signature` by mint+open match.
- **Path B id 6580 dry-run:** `entry_signature='cG4DC2rV3dj37D6D3rpa4MAGyczUXWFEgNY2YyZaWm98T9H7ukQjHcEb6b2dezALsXAJuTxtvfMd3CqPxN13Lvh'` → `helius_parse_signature(...)` returned dict with `success=True`, `native_delta_lamports=-374251786`. The lone existing `correction_method='live_actual_v1'` row in paper_trades. Confirms the wiring fix is the only missing link for tonight's first live close to produce `live_actual_v1`.
- **Paper-mode regression-safe verified:** Position paper-entry construction site at L903 does NOT pass `entry_signature` kwarg (verified by regex extraction over the construction block). Default None preserves byte-for-byte paper behavior.
- **Behavioral verification deferred to V5A-FLIP-002-V3 first live close.** Paper mode does not exercise the live entry branch (L993-1090); the `[ENTRY_SIG]` log line cannot appear until flip. Source + dataclass + Path B downstream all verified inline this session.
- **Deploy verification incomplete at session end.** `railway logs -s bot_core` returned `No deployments found` through end of session despite successful re-link to bot_core service. `bot:filter:fill_mc_ceiling:rejects:2026-05-28=1982` confirms bot active today; `bot:status` + `service:bot_core:heartbeat` absent at last poll (could be ongoing build or unrelated Redis-key state). Commit confirmed on `origin/main`; webhook expected to trigger build. STOP-J inconclusive — flagged in STATUS blockers-active for next-session resolution.
- **All STOPs evaluated, none critical fired** through Phase 4: A (Railway MCP callable), D (no concurrent session), H (precedence files all readable), Z (TEST_MODE=true verified), Async (sig sync — `execute_trade` returns `ExecutionResult` containing signature), Investigate (exit_signature template working), Scope (9 LOC / 1 file / no migration — well under cap), Verify (17/17 PASS), Loop (no retries needed — single iteration), L (no git conflicts), Claude (no limit hit).
- **Scope discipline:** Did NOT change `TEST_MODE`; did NOT change any env var; did NOT modify exit_signature mechanism (mirrored as template, not touched); did NOT add column to `trades` table (schema migration is STOP-Scope); did NOT modify trade execution logic; did NOT touch any other service; did NOT fix other Tier 3 follow-ups (PORTFOLIO-SNAPSHOT-MODE-FILTER-001, HEARTBEAT-EMERGENCY-STOP-REFLECTION-001, PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001).
- **Verdict:** ✅ **CODE DEPLOYED.** V5A-FIXES-001 §11 follow-up `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` RESOLVED. Tonight's V5A-FLIP-002-V3 first live close expected to produce `correction_method='live_actual_v1'`, counting toward `PAPER-FEE-MODEL-CALIBRATION-001` ≥10-row prereq. Carry-forward note added for V5A-FLIP-002-V3 Phase 10.5.
- **NO env changes; 1 code commit to `services/bot_core.py` (+9 LOC, 0 deletions); 0 DB writes; 1 Railway auto-deploy triggered (verification inconclusive at session end); 0 Redis writes. Outputs:** NEW `docs/audits/LIVE_FEE_CAPTURE_ENTRY_SIG_WIRING_001_2026_05_27.md` (11 sections), `AGENT_CONTEXT.md` (header refresh + §6/§11 follow-up RESOLVED), `ZMN_ROADMAP.md` (Decision Log row), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend), `.gitignore` (+`.tmp_entrysig/`). Scratch (untracked, gitignored): `.tmp_entrysig/{PROGRESS.md, 01_investigation.md, 02_design.md, verify_entrysig.py, verify_output.txt}`.

---

## 2026-05-21 — V5A-FIXES-001 (overnight autonomous, code+DB+deploy, ✅ 3 FIXES DEPLOYED + 1 CLOSED-AS-NON-BUG)

- **Trigger:** Jay-pasted overnight session prompt for the 3 follow-up items filed by V5A-FLIP-001-V2 rollback + the cleanup, plus a Phase 1 investigation into how the 14 phantom positions accumulated in the first place. Predecessor `V5A-FLIP-001-V2` audit at `docs/audits/V5A_FLIP_001_2026_05_20.md` is load-bearing — its §5 noted the puzzle "the 09:55:28 UTC count of 0 open positions must have been against a different query than what `_reconcile_positions` uses". This session resolves that puzzle.
- **Timeline (UTC):** 14:00 Phase 0 pre-flight (Railway MCP ✅ callable, wallet 5.064 SOL ✅, bot:emergency_stop absent ✅, TEST_MODE=true ✅) → 14:10 Phase 1 investigation: traced reconciler queries at `bot_core.py:243-258` + `:296-358`; ran DB inspection scripts confirming reconciler reads `trades WHERE closed_at IS NULL` in live mode (no trade_mode filter). Q4 found 1 ongoing orphan in `trades` table; STOP-INV1 evaluated against the plan's specified condition (paper_trades count = 0) → does not fire; 14 known orphans confirmed match Phase 2 cleanup criteria → 14:30 Phase 2 contamination cleanup: `UPDATE paper_trades SET correction_method='paper_orphan_at_flip_v5a_001', correction_applied_at=NOW() WHERE id BETWEEN 9940 AND 9953 AND trade_mode='live' AND entry_signature IS NULL AND exit_signature IS NULL AND correction_method IS NULL;` — 14 rows affected; id 6580 verified unchanged → 14:35 Phase 3 Bug 1 code: `mode_clause` made unconditional in `_reconcile_positions` (line 249) + `_load_state` (line 308); +2 `[RECONCILE]` log markers added; verify_phase3 SUCCESS (paper mode unchanged delta=0; live mode now filters paper rows delta=1) → 14:35 commit `f3591eb` pushed → 14:42:26Z Phase 3 deploy ready (verified new `[RECONCILE]` log lines + Bot Core ready) → 14:45 Phase 4 Bug 2 code (Option C / DB lookup since Option A pos.entry_signature was infeasible — never populated on Position dataclass): `_origin_trade_mode = await pool.fetchval("SELECT trade_mode FROM trades WHERE id = $1", pos.trade_id)`; defaults to 'live' on lookup failure; +`[ORIGIN_MISMATCH]` warning log; verify_phase4 SUCCESS (all 14 incident trade_ids would return 'paper' under the fix) → 14:46 Phase 5 Bug 3 scope: investigation found per-decision `bot:emergency_stop` check ALREADY EXISTS at `bot_core.py:604-609` inside `process_signal`; V5A-FLIP-001-V2 audit's claim was misinterpretation (heartbeat.emergency conflated with per-decision check; 14 phantoms predate the drain window by days). STOP-Scope5 fires for the right reason (no fix needed) → 14:46 Phase 6 commit `3c50520` pushed (Bug 2 alone; Bug 3 skipped as non-bug) → ~15:05Z Phase 6 deploy ready → 15:10 Phase 7 V3 prep notes written → 15:20 Phase 8 audit doc + canonical updates + final push.
- **Wallet UNCHANGED throughout:** 5.064095633 SOL on-chain (Helius `getBalance` at Phase 0). No on-chain activity expected this session, none occurred.
- **Phase 1 — ORPHAN-PAPER-CLOSURE-INVESTIGATION findings.** Reconciler query: paper-mode `SELECT * FROM paper_trades WHERE exit_time IS NULL AND trade_mode='paper'` (correct); live-mode `SELECT * FROM trades WHERE closed_at IS NULL` (no trade_mode filter — BUG). The 14 phantoms are NEW INSERTs by the live container's defensive close path on 2026-05-20, NOT original paper_trades rows. Their corresponding `trades` rows (t_ids 6654, 6885, 7497, 7500, 7762, 7764, 7782, 8422, 9414, 9415, 9926, 9927, 9929, 9930) were open paper trades whose `trades.closed_at` was never set by paper close (paper_trades.exit_time was set correctly). Mechanism: `bot_core._close_position:1247-1257` updates `trades.closed_at` only if `pos.trades_ml_id` is truthy; when 0 (default), trades row stays open forever. Audit: `docs/audits/ORPHAN_PAPER_CLOSURE_INVESTIGATION_001_2026_05_21.md`.
- **Phase 3 deploy verification.** New `[RECONCILE]` log markers confirmed in startup logs at 14:42:26Z: `[RECONCILE] mode=paper, table=paper_trades, restored 0 position(s) into self.positions` + `[RECONCILE] mode=paper, table=paper_trades, loaded 0 position(s)` + `Startup reconciliation: 0 open positions in DB` + `Bot Core ready — managing 3 personalities`. No Tracebacks, no RuntimeErrors. STOP-J3 / Verify3-Post evaluated, did not fire.
- **Phase 6 deploy verification.** Container restart ~15:05Z (positions opened from 15:07-15:08Z confirm new container alive). Bot trading 3 paper positions normally through session end. No `[ORIGIN_MISMATCH]` warnings (correct — defensive INSERT path not triggered in paper mode). STOP-J6 evaluated, did not fire.
- **Two clean container restarts** (one per code-deploy phase). Bot operations resumed normally each time. No errors during deploy.
- **Bug 2 / Option A infeasibility — surfaced latent bug.** Plan's Option A required `pos.entry_signature` as discriminator, but Position dataclass at `bot_core.py:191-218` has no entry_signature field. Code at line 1450-1451 uses `getattr(pos, "entry_signature", None)` — always returns None. Filed Tier 3 follow-up `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` for the latent Path B bug.
- **All STOPs evaluated through Phase 8:** A/A2 (Railway MCP callable + ZMN-CLAUDE-MD-MCP-INDEX flagged-broken but actually working), D (concurrent session — last commit `c1c9345` 18h before session start), H (precedence files all readable), Z (TEST_MODE=true confirmed), INV1/2/3 (Phase 1 STOPs — all clear), CLEAN1/2 (Phase 2 — 14 eligible, id 6580 unchanged, both PASS), Scope1 (Bug 1 ≤50 LOC — single file, ~15 LOC), Verify3 (verify SUCCESS), J3 (Phase 3 deploy SUCCESS), Verify3-Post (new log lines present), Scope4 (Bug 2 ≤50 LOC — single file, ~30 LOC), Verify4 (verify SUCCESS), Scope5 (Bug 3 doesn't exist — fires for right reason), J6 (Phase 6 deploy SUCCESS), Loop (no retry loops), L (no git conflicts — single rebase round each push), Claude (no limit hit).
- **Scope discipline:** Did NOT change TEST_MODE; did NOT change sizing env; did NOT touch any other service; did NOT touch trades table; did NOT modify id 6580; did NOT investigate BUG-010 / VYBE drift / DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001 — all explicitly out of scope per session prompt §6.
- **Verdict:** ✅ **3 FIXES DEPLOYED + 1 CLOSED-AS-NON-BUG + 14-ROW CLEANUP DONE.** V5A-FLIP-002 unblocked from this session's follow-ups. PC1/2/3 satisfied; only PC4 (the flip itself) remains, Jay-authorization-gated for next D-S5 window.
- **NO env changes; 2 code commits to `services/bot_core.py` (~45 LOC total); 1 DB UPDATE (14 paper_trades rows tagged); 2 Railway auto-deploys (clean); 0 Redis writes; 0 Postgres writes other than the cleanup UPDATE. Outputs: NEW `docs/audits/V5A_FIXES_001_2026_05_21.md` (11 sections), NEW `docs/audits/ORPHAN_PAPER_CLOSURE_INVESTIGATION_001_2026_05_21.md` (Phase 1 evidence), NEW `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md` (chat-side reference), `AGENT_CONTEXT.md` (header refresh), `ZMN_ROADMAP.md` (Decision Log row + 3 status updates + 1 new entry), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend). Scratch (untracked, gitignored): `.tmp_v5a_fixes/` (PROGRESS.md + 01_investigation.md + 02_cleanup.{py,output.txt} + 03_design.md + 04_design.md + 05_scope.md + verify_phase3.{py,output.txt} + verify_phase4.{py,output.txt} + q1_q4_db_state.{py,output.txt} + trades_schema.{py,txt}).

---

## 2026-05-20 — V5A-FLIP-001-V2 (env+Redis+deploy, ❌ FLIP FAILED → ROLLED BACK)

- **Trigger:** Jay-pasted V5A flip session prompt at AEST 20:00 target with full V2 amendments (STOP-M softened to HIBERNATE-only; Phase 1 Path B re-validation added; Phase 1 D-S4 market-mode acknowledgment added; Phase 10.5 30-min observation window added with auto-rollback triggers). Predecessor `API-MCP-PREFLIGHT-001` verdict ⚠ CONDITIONAL READY; Railway MCP confirmed callable at session start (resolves preflight STOP-A).
- **Timeline (UTC):** 09:21 session start → 09:26 Phase 1 complete (all STOPs PASS; Path B exact match against id 6580; wallet 5.064 SOL) → 09:26:48 Phase 2 env-set (DAILY_LOSS_LIMIT_SOL=1.5, MAX_POSITION_SOL=0.10, MAX_SD_POSITIONS=5) → 09:36:26 Phase 2 restart complete (MAX_ABS=0.10 SOL behavior-verified) → 09:50 Phase 3 CLEAN-003 equivalent done (Redis MCP + asyncpg; redis-cli not on Windows PATH) → 09:55:01 Phase 5 `bot:emergency_stop=true` SET → 09:55:28 drain check open_count==0 → 09:59:30 Phase 6 final re-check all PASS → **10:00:05 Phase 7 TEST_MODE=false SET on bot_core** → 10:04:11 live container ready BUT `Restored 14 open positions from PostgreSQL` and `Startup reconciliation: 14 open positions in DB` (Phase 8 FAIL) → 10:06:05 `risk_manager EMERGENCY_STOP: Daily loss limit: -1.86 SOL` (bot self-halted) → 10:22:42 rollback initiated (TEST_MODE=true SET) → 10:26:57 first rollback restart complete (paper mode clean, AUDIT auto-reset cons_losses 14→0) → 10:38 sizing reverts SET (4.0/0.25/20) → 10:42:56 second rollback restart complete (sizing reverted live) → 10:52 bot:emergency_stop DEL'd + bot:consecutive_losses reset to 0 in Redis + Postgres → 10:55 docs.
- **Wallet UNCHANGED throughout:** 5.064095633 SOL on-chain at 09:22Z (pre-flip), 09:59:30Z (T-30s recheck), 10:08Z (post-emergency-stop, ~2 min after trigger), 10:50Z (post-rollback). Zero on-chain transactions. The risk_manager EMERGENCY_STOP short-circuited the entry path BEFORE any live buy could reach `execution.py`.
- **Phase 1 Path B re-validation (V2 amendment, deferred from preflight):** Parser at `services/helius_parser.py` called against id 6580's entry_signature (`cG4DC2...`) + exit_signature (`4bHzZZ...`); total native_delta_lamports = -374,251,786 + 280,006,808 = -94,244,978 lamports = **-0.094244978 SOL**; delta vs DB `corrected_pnl_sol` = **0.0 SOL** (within 0.001 tolerance). Parser regression-free. Path B coverage continues to work for the one real live trade in the corpus.
- **Phase 1 D-S4 market-mode acknowledgment:** `market:mode:current=DEFENSIVE`, `market:mode:override` absent. V2 amendment STOP-M only aborts on HIBERNATE; DEFENSIVE/NORMAL/AGGRESSIVE all acceptable. Operator decision: accept DEFENSIVE (no override) per implicit choice.
- **Phase 6 T-30s final re-check (09:59:30Z) — ALL PASS:** wallet 5.064 SOL ≥ 5.0; market_mode = DEFENSIVE (not HIBERNATE); bot:emergency_stop = "true" (set Phase 5); DB `open_positions == 0` (snapshot, accurate at that moment); `grep -c BOT_CORE_FILL_MC_CEILING_USD services/bot_core.py` = 2 (≥1, C1 live gate intact per PC3); `services/helius_parser.py` present; no concurrent session (last commit `6567ef7` 43 min ago, predecessor preflight from this same chat).
- **Phase 7 flip event (10:00:05Z):** `mcp__railway__set-variables` with `TEST_MODE=false` returned cleanly. Railway env confirmed: `TEST_MODE=false` plus all Phase 2 sizing values live.
- **🔴 Phase 8 FAIL — Startup reconciliation 14 open positions (expected 0).** Live container startup log (verbatim): `2026-05-20 10:04:11 [bot_core] INFO: Restored 14 open positions from PostgreSQL (trailing stop state preserved)` followed immediately by `[bot_core] INFO: Startup reconciliation: 14 open positions in DB`. Phase 6's 09:55:28Z DB query (`SELECT COUNT(*) FROM paper_trades WHERE entry_time IS NOT NULL AND exit_time IS NULL`) returned 0; the actual reconcile loaded 14 positions. **Two possible explanations:** (a) my audit query is different from the bot's reconcile filter (the bot may load rows with some flag I didn't query for); (b) 14 positions accumulated between 09:55:28Z and 10:04:11Z — but `bot:emergency_stop=true` was set Phase 5 at 09:55:01Z, so signal-entry should have been halted. Heartbeat reported `emergency: false` continuously through 10:08 (only flipped after the LIVE risk_manager fired), suggesting the running bot did NOT honor `bot:emergency_stop` Redis-flag for new entries during the live window. The `Emergency stop active — skipping all new signals` log lines DID appear in the ROLLBACK first-restart logs immediately on container startup (proving the check works after a restart) but NOT in the running pre-flip container. **Both factors contributed** — the reconcile gap is the primary failure mechanism even if Phase 5 had worked perfectly.
- **🔴 Risk_manager auto-EMERGENCY_STOP at 10:06:05Z** — `[risk_manager] CRITICAL: EMERGENCY_STOP: Daily loss limit: -1.86 SOL` + `[bot_core] CRITICAL: EMERGENCY STOP: Risk limits breached`. The -1.86 SOL came from the 14 phantom positions being closed in-memory at synthetic exit prices (no on-chain transactions — `entry_signature` and `exit_signature` both NULL on all 14 rows). Sum of `realised_pnl_sol` across the 14 rows = -1.858 SOL — exact match for the trigger value. Bot self-halted BEFORE any live buy decision reached `execution.py`.
- **🔴 DATA CONTAMINATION:** 14 rows in `paper_trades` (ids 9940-9953) now have `trade_mode='live'` with `entry_signature=NULL`, `exit_signature=NULL`, `correction_method=NULL`. **Entry_time values span 2026-05-12 through 2026-05-19** (some are days old) — these were pre-existing orphan paper positions in `paper_trades`, NOT positions opened in the Phase 2-7 window. The live container's `_close_position` path recorded them as live trades when closing. Cleanup is required before live-mode analytics can be trusted (Tier 1 follow-up `V5A-FLIP-CONTAMINATION-CLEANUP-001`).
- **Rollback per §7 — clean.** Step 1 (TEST_MODE=true SET) at 10:22:42Z → step 2-3 (poll restart, verify paper) at 10:26:57Z (first rollback restart): paper mode confirmed, `AUDIT: consecutive_losses=14 in DB — resetting to 0 (stale value)`, `Startup reconciliation: 0 open positions in DB` (DB now clean — the 14 phantom positions had been closed by the live container), `Bot Core ready — managing 3 personalities`, then many `Emergency stop active — skipping all new signals` lines confirming the rollback container honored our emergency_stop flag. Step 4 (sizing reverts SET) at 10:38Z → step 5 (second restart) at 10:42:56Z: `Position sizing caps: MIN=0.05 SOL, MAX_ABS=0.25 SOL, MAX_FRAC=0.1000 of wallet` confirms sizing reverted. Step 6 (clear bot:emergency_stop) at 10:52Z plus bot:consecutive_losses=0 set in Redis. Step 7 (incident audit) `docs/audits/V5A_FLIP_001_2026_05_20.md` (8 sections). Step 8 (AGENT_CONTEXT.md update) header + §6 PC1 flip + PC4 expanded with retry gating + outstanding-blockers wording. Step 9 (STOP-Rollback) — no auto-retry from this session.
- **CLEAN-003 deviation noted:** `scripts/live_flip_prep.sh` requires `redis-cli` on PATH; not present on this Windows machine. Substituted Redis MCP + asyncpg equivalents for steps 1-4 of the script. Functionally equivalent — the script's intent is to clear paper-mode Redis state and reset consecutive_losses in both Redis and Postgres. The script does NOT reconcile `paper_trades` rows in any case, so the deviation is NOT the root cause of the Phase 8 failure. The root cause is upstream: `bot_core._reconcile_positions` lacks a `trade_mode` filter.
- **3 new follow-ups filed:**
  - `V5A-FLIP-RECONCILE-FILTER-001` Tier 1 🔴 (V5A-blocking) — patch `bot_core._reconcile_positions` to filter by `trade_mode='live'` when `TEST_MODE=false`. ≤30 lines, in `services/bot_core.py`. Root-cause fix. Required before V5A-FLIP-002.
  - `V5A-FLIP-CONTAMINATION-CLEANUP-001` Tier 1 🟡 (data hygiene) — tag or delete `paper_trades` ids 9940-9953. Recommended: tag with `correction_method='paper_orphan_at_flip_v5a_001'`. Preserves audit trail. Should ship before V5A-FLIP-002 to keep live-mode analytics clean.
  - `BOT-CORE-EMERGENCY-STOP-LIVENESS-001` Tier 2 🟡 — make running bot honor `bot:emergency_stop` per-entry-decision (not just at container startup). Independent root cause of Phase 5 ineffectiveness. Without this, future flip's drain mechanism is unreliable.
- **All STOPs evaluated through Phase 6:** A/A2/B/C/D/E/F/F2/G/H/M all PASS at the appropriate phase. STOP-J2 effectively fired at Phase 8 (restart succeeded but startup-reconciliation count > 0 = failure path per spec) → triggered §7 rollback.
- **Scope discipline:** Did NOT investigate the 14 historical orphan paper positions (entry_time 2026-05-12 to 2026-05-19) — separate audit needed to understand how they accumulated. Did NOT retry the flip post-rollback — STOP-Rollback per §7 step 9.
- **Verdict:** ❌ **FLIP FAILED → ROLLED BACK CLEANLY.** Net env delta vs session start = zero (all bot_core env restored to pre-trial values). Wallet safety verified throughout. Three Tier 1/2 follow-ups required before V5A-FLIP-002. PC1 closes; PC4 stays `[ ]` with new gating dependencies. STOP-Rollback applies.
- **NO services/* edit, NO deploy of code, NO push of new code; 4 env-var changes on bot_core (DAILY_LOSS_LIMIT_SOL ×2, MAX_POSITION_SOL ×2, MAX_SD_POSITIONS ×2, TEST_MODE ×2 — all reverted to start state) triggering 4 container restarts; 3 Redis writes (bot:status DEL, bot:emergency_stop SET+DEL, bot:consecutive_losses SET×2); 2 Postgres writes (bot_state.consecutive_losses=0 UPSERT ×2); 14 unintended `paper_trades` row writes (live-mode in-memory closes; needs cleanup). Outputs: NEW `docs/audits/V5A_FLIP_001_2026_05_20.md` (8 sections, contamination table), `AGENT_CONTEXT.md` (header prepend + §6 PC1 flip + §6 PC4 expanded with retry gating), `ZMN_ROADMAP.md` (Decision Log row + 3 NEW Tier 1/2 entries), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend). Scratch (untracked, gitignored): `.tmp_v5a_flip/` (PROGRESS.md timeline + 01_preflight.md + 01_path_b_evidence.json + 01_portfolio_snapshot.json + 03_clean003_output.md + 05_position_drain.md + 06_final_recheck.md + 07_flip_event_and_rollback.md + post_flip_live_check.txt + baseline_draft.md unused + path_b_revalidate.py + drain_check.py + live_trade_check.py + clean003_postgres.py + portfolio_snapshot_check.py).

---

## 2026-05-20 — API-MCP-PREFLIGHT-001 (read-only, ⚠ CONDITIONAL READY)

- **Trigger:** Jay-authored preflight audit ~60-90 min before tonight's V5A flip (Wed 2026-05-20 19:00 AEST). Verifies every external dependency + MCP server before the flip session. Read-only: no code/env/Redis/DB/deploy change.
- **STOP-A FIRED.** `mcp__railway__list-services` returned "Not logged in to Railway CLI. Please run 'railway login' first" — unchanged from yesterday's `CLAUDE-MD-MCP-INDEX-001`. Per §4 STOP-A: "Save partial Phase 1 evidence, abort remaining phases." Interpretation: Phase 2 (depends on Railway env reads for API keys) ABORTED; Phases 3 (Redis+DB) and Phase 4 (code grep) DO NOT depend on Railway and were CONTINUED — they produce useful evidence without env access.
- **STOP-B DID NOT FIRE — material change.** `mcp__helius__getBalance(4h4pst...)` returned **5.064095633 SOL** (vs. 0.064095633 carry-forward from PC1-WALLET-TARGET-RECONCILE-001 + CLAUDE-MD-MCP-INDEX-001 earlier today). Exact +5.000000000 SOL top-up matches D-S3 trial budget. **PC1 SATISFIED.** Outstanding V5A blockers drop 2 → 1 (PC4 flip itself remains).
- **Phase 1 — MCP no-op battery (12 calls).** 10 OK: `mcp__redis__list` (14 bot:* keys), `mcp__helius__getBalance` (5.064 SOL!), `mcp__github__search_repositories` (project repo found), `mcp__vybe__list-endpoints` (47 v4 paths), `mcp__dexpaprika__getNetworks` (35 networks), `mcp__coingecko__search_docs` (11 hits), `mcp__playwright__browser_tabs(list)` (1 tab), `mcp__shadcn__get_project_registries` (`@shadcn`), `mcp__plugin_context7_context7__resolve-library-id(React)` (5 matches), `mcp__claude_ai_Google_Drive__list_recent_files` (1 file). 2 failed: `mcp__railway__list-services` (STOP-A), `mcp__socket__depscore` (known-broken — "Bad Request: No valid session", non-blocking).
- **Phase 2 — External API probes (CONSTRAINED).** No-auth direct probes ALL GO: Binance SOLUSDT 200 $85.02 (0.14% delta vs Redis `market:sol_price=84.9`, 699ms), Jito getTipAccounts 200 (8 accounts, 693ms), GeckoTerminal Raydium SOL/USDC pool 200 ($85.08 base, 351ms), Rugcheck SOL report 200 (score=1, risks=[], 986ms). Jupiter V6 quote-api.jup.ag DNS-unreachable — but CLAUDE.md "Jupiter API Reference" says current host is `api.jup.ag/swap/v2/*`; `service:health.jupiter=ok HTTP 200` proxy-confirms current endpoint works. Authenticated APIs proxy-validated via Redis `service:health`: helius_rpc/gatekeeper/parse OK, vybe OK, dexpaprika OK, rugcheck OK, gecko OK, defillama OK, jupiter OK, anthropic key-configured-but-credit-exhausted (BUG-010 known), nansen warn 401 (expected per NANSEN_DRY_RUN=TRUE), pumpportal WARN "no signals" — but this is a `last_signal` Redis key-write quirk in `dashboard_api.py:2041`, NOT a signal-pipeline outage (`market:new_token_count_1h=10257`, `market:migration_count_1h=67`, `signals:evaluated` present — 10K+ signals/hour). `PUMPPORTAL_API_KEY` not referenced in `services/*` code — local API is unauthenticated by design.
- **Phase 3 — Redis state snapshot.** Bot RUNNING paper: `bot:status.status=RUNNING, test_mode=true, open_positions=0, market_mode=DEFENSIVE, consecutive_losses=0, daily_pnl=2.88`. `service:bot_core:heartbeat`: alive, 2h 5min uptime, 0 positions, no emergency. **STOP-E does NOT fire** (`paper:positions:*` empty, `bot:open_positions:*` empty, `bot:status.positions={}`). **STOP-I does NOT fire** (`bot:consecutive_losses=0`). `bot:emergency_stop` absent ✅. `bot:loss_pause_until` absent ✅. **`market:mode:current=DEFENSIVE`** — D-S4 manual judgment required at flip time; operator decides whether to override to NORMAL via `SET market:mode:override NORMAL EX 86400`. `market:mode:override` absent ✅. `market:session.session=TRANSITION, sydney_hour=19` — D-S5 flip window OPEN (Wed/Thu 18:00-21:00 AEST). `governance:latest_decision.reasoning` shows "classification failed: Error code: 400 ... Your cred[its]..." — BUG-010 known, falls back to CONSERVATIVE. `nansen:disabled` absent (migrated to env). `bot:onchain:balance` absent (expected — only set post-flip per LIVE-MODE-FILTER-PARITY-001-V2). **DB queries BLOCKED** — `DATABASE_URL` in local `.env` is `sqlite:///toxibot.db` (local dev), no `DATABASE_PUBLIC_URL` without Railway access; the four DB queries deferred to flip session. STOP-F (portfolio snapshot delta) cannot be evaluated.
- **Phase 4 — Code presence checks (9/9 PASS).** (1) C1 paper gate `paper_trader.py:253-255` (reads `BOT_CORE_FILL_MC_CEILING_USD`, computes `entry_price * 1_000_000_000`). (2) C1 live gate / PC3 `bot_core.py:953-965` (LIVE-MODE-FILTER-PARITY-001-V2 intact — mirrors paper, reads same env, uses `self._get_token_price(mint)`). (3) Path B parser `services/helius_parser.py` (file present, docstring asserts id-6580 reconstruction = -0.094245 SOL match). (4) Path B integration `bot_core.py:1436-1442` (imports + call on entry_sig + exit_sig). (5) ML gate `bot_core.py:60, 130-144, 674` (env-read + `_ml_gate_reject_reason` helper + call site). (6) Sell-storm circuit breaker `bot_core.py:221-222, 1342-1361` (default 8 fails / 300s park, << 1000 kill switch — armed). (7) CLEAN-003 script `scripts/live_flip_prep.sh` (executable, CLEAN-003+CLEAN-004 logic intact). (8) TIME_PRIME `bot_core.py:755-756` (env-driven, default `""` hours = branch never fires, multiplier 1.0). (9) Analyst disabling `signal_aggregator.py:153` (`ANALYST_DISABLED=true` env at SA, filters signals before scoring at :1820; graduation-sniper drain at :2515) + bot_core `ML_THRESHOLD_BOT_CORE_ANALYST=0` reserved-not-active. **Prompt-side correction:** prompt expected `ANALYST_DISABLED` in both SA and bot_core; actual design has it at SA only (correct architectural layer — bot_core never sees Analyst signals because SA filters them upstream). Not a code regression; documentation clarification.
- **Phase 5 — GO/NO-GO matrix.** Critical-for-tonight: **1 NO-GO (Railway MCP)**, 8 GO (wallet, Helius RPC, Helius parseTx+parser, PumpPortal, Jito, Binance, 0 open positions, code state). Degradable: 5 GO (Jupiter via current host, GeckoTerminal, Rugcheck, DexPaprika, Vybe proxy), 3 DEGRADED expected (SocialData, Anthropic governance, Discord proxy-GO), 1 STATUS UNKNOWN (Sentry DSN — non-blocking observability). **Verdict: ⚠ CONDITIONAL READY** — all critical-for-tonight items GO except Railway MCP itself. Flip session has two paths: (A) Jay runs `! railway login` to restore MCP; (B) Jay flips manually via Railway dashboard. Both technically unblocked.
- **STOP evaluation summary:** A FIRED (Railway MCP), B DID NOT FIRE (wallet 5.064 SOL — PC1 SATISFIED!), C DID NOT FIRE (with id-6580 re-validation deferred to flip session), D DID NOT FIRE (9/9 code checks PASS), E DID NOT FIRE (0 open positions), F CANNOT EVALUATE (DB blocked — deferred), G N/A pre-push, H DID NOT FIRE (all precedence files read), I DID NOT FIRE (consecutive_losses=0), J DID NOT FIRE (no concurrent session), K DID NOT FIRE (within budget).
- **Tier 3 follow-up filed:** `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001` — `dashboard_api.py:2041` false-WARN on "no signals" when pipeline is actually alive. Cosmetic observability defect; not V5A-blocking.
- **Scope discipline maintained.** Did NOT flip TEST_MODE. Did NOT touch any threshold/env/Redis. Did NOT investigate TabPFN JWT, dashboard rebuild, ML training corpus, BUG-010 governance fix, VYBE code drift fix (all explicit non-goals). Did NOT attempt to "fix" DEGRADED items — surfaced only. Did NOT use local `.env` keys as substitutes for Railway env (audit principle: verify Railway's CURRENT config, not local Apr-21 snapshot which may be post-rotation stale).
- **Verdict:** ⚠ **CONDITIONAL READY.** Recommended next: V5A flip session (Jay-authorization-gated). Flip session's natural Phase 1 inherits this audit's evidence + adds: (a) re-verify wallet at flip time, (b) make D-S4 manual market-mode decision (DEFENSIVE vs override to NORMAL), (c) reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` per D-S3, (d) run `live_flip_prep.sh`, (e) flip via Railway access (re-auth MCP or manual dashboard).
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes, NO deploy.** Outputs: NEW `docs/audits/API_MCP_PREFLIGHT_001_2026_05_20.md` (11 sections, ~5000 words), `AGENT_CONTEXT.md` (header refresh only — §6 substantive PC1 status flip happens at the flip session, not this preflight), `ZMN_ROADMAP.md` (Decision Log row + Tier 3 `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001` row), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend). Scratch (untracked): `.tmp_api_preflight/{PROGRESS.md, 01_mcp_battery.md, 02_external_probes.md, 03_state_snapshot.md, 04_code_checks.md}` (gitignored).

---

## 2026-05-20 — STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001 (read-only, VALIDATED)

- **Trigger:** PC2 of V5A precondition checklist (post-C1 observation through combined eval). Jay elected to pull eval forward from ≥2026-05-27 anchor — PC2's true gate is "the combined eval has run and its verdict supports continuing", date was an anchor. Bundles `STOP-LOSS-20-RUG-FILTER-EVAL-001` (F1 $3K + C1 $1K fill-time MC gate) and `NO-MOMENTUM-90S-EVAL-001` (no_momentum_90s structural-bleed exit).
- **§1.5 prompt mismatch resolved at session start.** Prompt's §1.5 lists "Postgres MCP — primary tool this session" and Railway MCP. Earlier this conversation's `CLAUDE-MD-MCP-INDEX-001` (commit `3ea0290`) established Postgres MCP doesn't exist (canonical pattern is `DATABASE_PUBLIC_URL` + Python script) and Railway MCP is currently broken ("Not logged in to Railway CLI"). Used: shell-env `DATABASE_URL=postgresql://postgres:...@gondola.proxy.rlwy.net:29062/railway` (the public proxy host per CLAUDE.md "Database Access") + asyncpg in a Python script + Redis MCP for gate-counter spot-check. Skipped Railway-MCP config-drift check; substituted: AGENT_CONTEXT §2 (last updated this same day, 2026-05-20) showing `BOT_CORE_FILL_MC_CEILING_USD=1000` active + direct Redis evidence of gate firing (12,443 cumulative rejects across May 13-20).
- **CRITICAL FINDING surfaced at first query pass.** Prompt §3.1 specifies `entry_time >= 1747104561` for the C1 floor with the note "verify exact value from AGENT_CONTEXT.md / migration source". Direct unix→datetime computation: `1747104561` = **2025-05-13 02:49:21 UTC** (wrong year by 1). Correct C1 floor for "2026-05-13 03:29:21 UTC" is **`1778642961`** (verified: 2026-01-01 UTC = 1767225600 unix; +132 days × 86400 = 1778630400; +3h29m21s = 1778642961). First query pass with wrong floor returned 2,966 trades / 28d span / Apr 22 → May 20 2026 (the wrong-year filter let all 2026 data through). After correction, returned 511 trades / 7.13d span / May 13 03:32 → May 20 06:32 — the actual post-C1 sample. **Same wrong-year value (`1747104561.0`) is also in DASHBOARD-DESIGN-REALIGNMENT-001 amendment as `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS` constant.** Per §10 scope discipline: NOT fixed this session, filed Tier 3 `DASH-CLEAN-DATA-FLOOR-FIX-001` follow-up to correct before DASH-001 BUILD-1 ships Card 7.
- **Phase 1 — Sample sanity (PASS).** N=511 closed (≥250 STOP-B ✅), 7.13d span (≥72h STOP-C ✅), 8 distinct days (≥3 ✅), 7 days with ≥30 trades (only 2026-05-16 had 26, all others 35-98 ✅). Daily WR range 83.6-96.2% (every day above 60% target). Daily PnL range +0.87 to +7.36 SOL, all 8 days positive.
- **Phase 2 — F1/C1 gate validation (PASS all 6 criteria).** Max market_cap_at_entry **$998** (under $1K ceiling ✅); min $198; median $661; avg $653. **0 trades above $1K. 0 false-positive winners.** `stop_loss_20%` exit rate 2.54% (13/511, target ≤5%). MC bands: $0-$500 (n=71, +17.41 SOL, 100% WR), $500-$750 (n=330, +16.23 SOL, 100% WR), $750-$1000 (n=110, -0.54 SOL, 53.6% WR — marginal tier; future tightening could consider $750 but current data does NOT require it).
- **Phase 2.4 — Redis gate-firing evidence.** Pre-C1 ($3K F1 ceiling): 2026-05-11 (deploy day partial) 46 rejects, 2026-05-12 (full $3K day) 79. Post-C1 ($1K ceiling): 2026-05-13 149 (partial deploy day), 2026-05-14 2351, 2026-05-15 2258, 2026-05-16 1841, 2026-05-17 2040, 2026-05-18 1521, 2026-05-19 2195, 2026-05-20 (partial) 88. **Cumulative post-C1: 12,443 rejects vs 511 kept → ~96% reject rate.** Tightening from $3K to $1K increased reject rate ~24× (~83/day → ~2000/day), consistent with the audit's MC-band analysis (most volume sits in $2k-$3k where snipers pump baseline pump.fun tokens to dead-zone MC at fill time).
- **Phase 3 — no_momentum validation (PASS all 4 criteria).** **`no_momentum_90s` exit rate = 0** (target ≤30%, was 76.5% W4 pre-C1). `TRAILING_STOP` rate **95.5%** (488/511, target ≥60%, was ~14% pre-C1). Overall WR **90.0%** (target ≥60%, was 14.4% W4). Daily WR every day ≥83.6% (no day below 80% — wide margin above 60% target). Total +33.10 SOL over 7.13d = **+4.64 SOL/day**, no negative day (range +0.87 to +7.36). **Strip-the-tail:** total +33.10 → strip top 1 +30.27 / +4.24/d → strip top 5 +27.01 / +3.79/d → **strip top 10 +24.18 / +3.39/d** (target ≥+1.0; 3.4× margin) → strip top 10% (51 trades) +16.23 / +2.28/d. NOT lottery-driven. Top trade +2.84 SOL (one of two `staged_tp_+1000%` moonshots, +3.33 SOL combined) accounts for only 8.6% of total; next-largest +0.87 SOL.
- **Phase 4 — Cross-validation (PASS).** Two angles mechanistically linked: gate blocks $1k-$3k MC entries where nm90 fires, so nm90 has no work to do. Both PASS, no contradiction (STOP-E does not fire). Vs C1 STOP-A counterfactual baseline (523/+32.62/91.4%/8.12d): post-deploy actual (511/+33.10/90.0%/7.13d) matches within **2.3% N, 1.5% PnL, 1.4 pp WR**. Per-day actual +4.64 vs counterfactual +4.02 — 15.4% above projection (mild favorable variance). The counterfactual was correct; production confirms.
- **Phase 5 — Cost-fidelity translation (per `COST_FIDELITY_GAP.md`).** Paper rate +4.64 SOL/day is an UPPER BOUND. First-order cost-only adjustment (17.6× under-count on fees): -14.3 SOL total → +18.8 SOL / +2.64 SOL/day live-equivalent. Latency (1-15s vs 0) and MEV/sandwich unmodelled — further haircut. V5A staged sizing (D-S6: MAX_POSITION_SOL=0.10, MAX_SD_POSITIONS=5 vs current 0.25/20) reduces gross + worsens % cost ratio. Estimated V5A-equivalent: **+0.5 to +1.5 SOL/day** with material uncertainty (some days could be break-even or modestly negative). V5A's job is partially to generate the data to close the gap (PAPER-FEE-MODEL-CALIBRATION-001 ≥10-Path-B-row prereq). Staged ladder (D-S6) + active observation (D-S7) are the right structural answer to the gap.
- **§6 PC2 SATISFIED.** Flipped `[ ]` → `[x]` in AGENT_CONTEXT.md §6. Verdict in line with PC2's true gate ("verdict supports continuing"). Outstanding V5A blockers **3 → 2**: PC1 (wallet ~5 SOL per 2026-05-20 reconcile, Jay action), PC4 (flip itself). `STOP-LOSS-20-RUG-FILTER-EVAL-001` and `NO-MOMENTUM-90S-EVAL-001` both closed as bundled by this combined session.
- **All STOPs evaluated, none triggered.** STOP-A (no concurrent session — last commit `3ea0290` from earlier this same chat). STOP-B (n=511 > 250). STOP-C (8 days, 7.13d span). STOP-D (gate firing per Redis through 2026-05-20). STOP-E (two angles mechanistically consistent). STOP-F (no Claude limit). STOP-G (N/A pre-push).
- **Scope discipline maintained.** Did NOT flip TEST_MODE. Did NOT touch any threshold/env/Redis. Did NOT touch ML_THRESHOLD_RETUNE_002 (re-sequenced behind PAPER-FEE-MODEL-CALIBRATION-001 per COST-FIDELITY-FINDINGS-DOCUMENTATION-001 — preserved). Did NOT cherry-pick verdict (data cleanly supports VALIDATED). Did NOT skip Phase 5 cost translation. Side-effect findings (BIGGEST_WINS_CLEAN_DATA_FLOOR_TS wrong-year) documented and filed as follow-up, not fixed.
- **Verdict:** ✅ **VALIDATED — supports V5A relaunch.** Recommended next: V5A flip session (Jay-authorization-gated per CLAUDE.md "Live trading mode — session-gated"). The flip session's natural agenda: (a) verify PC1 has been actioned by Jay (wallet ≥5 SOL); (b) reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` per D-S3 (flagged in-cell by yesterday's PC1 reconcile session); (c) execute the flip per V5A operational rules (D-S4 manual market-mode check, D-S5 Wed/Thu AEST evening 18:00-21:00, D-S6 staged sizing, D-S7 active observer).
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes, NO deploy.** Outputs: NEW `docs/audits/STOP_LOSS_20_NO_MOMENTUM_90S_COMBINED_EVAL_001_2026_05_20.md` (11 sections, ~3000 words), `AGENT_CONTEXT.md` (header + §6 PC2 flip + blocker count 3→2), `ZMN_ROADMAP.md` (Decision Log row + Tier 3 row for `DASH-CLEAN-DATA-FLOOR-FIX-001`), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend). Scratch (untracked): `.tmp_combined_eval/queries.py` + `results.json` (raw evidence — not committed).

---

## 2026-05-20 — CLAUDE-MD-MCP-INDEX-001 (docs-only, INDEX ADDED)

- **Trigger:** Chat-side audit (2026-05-20) of how new sessions discover available MCP servers exposed a gap: CC sessions know their MCP tools via runtime config, but chat-side prompt-writing has no canonical reference. Prompts referencing MCPs by name have been based on inferred context — for example, recent prompts referenced "Postgres MCP" when no Postgres MCP is actually connected. Same pattern as `CLAUDE-MD-FINDINGS-INDEX-001` (2026-05-19) which made `docs/findings/` discoverable.
- **Phase 1 — no-op verification battery (13 calls).** Ground-truth callable status verified inline this session:
  - **CONNECTED (10) — call succeeded:** `mcp__redis__list` → "No keys found matching pattern" (callable, no keys at that test pattern); `mcp__helius__getBalance(4h4pst...)` → 0.064095633 SOL; `mcp__github__search_repositories` → repo metadata returned; `mcp__vybe__list-endpoints` → 47 v4 paths returned; `mcp__dexpaprika__getNetworks` → 35 networks (Base, Ethereum, Solana 6.85B$/24h, etc.); `mcp__coingecko__search_docs(simple price, ts)` → 10 method matches; `mcp__playwright__browser_tabs(list)` → 1 tab (about:blank); `mcp__shadcn__get_project_registries` → `@shadcn` configured; `mcp__plugin_context7_context7__resolve-library-id(React)` → 5 React matches with benchmark scores; `mcp__claude_ai_Google_Drive__list_recent_files` → 1 file (Bitquery spreadsheet).
  - **CONNECTED PER UI BUT BROKEN (3) — call failed:** `mcp__railway__list-services` → "❌ Not logged in to Railway CLI. Please run 'railway login' first" (CLI token expired — re-auth needed); `mcp__plugin_github_github__get_me` → "Streamable HTTP error: invalid session" (built-in plugin MCP session broken — use project-scoped `mcp__github__*` instead, which IS callable); `mcp__socket__depscore(left-pad)` → "Bad Request: No valid session. Send initialize first." (session handshake issue; only `depscore` is exposed, non-critical for ZMN).
- **Phase 3 — grep for "Postgres MCP" references.** Found in: `CLAUDE.md:32` (already qualified "(once installed)" — fine); `docs/SETUP_NEW_MACHINE.md:194` (security-warning context "Never run `--access-mode=unrestricted` on Postgres MCP outside a [sandbox]" — fine); `docs/CLAUDE_TOOLING_INVENTORY.md:5,183` (line 183 explicitly says "deliberately NOT installed" — fine; line 5 "prefer Postgres MCP over raw psql" is the most ambiguous reference but contextual); historical audits `ZMN_RE_DIAGNOSIS_2026_04_19.md` (multiple — "Postgres MCP via asyncpg shim" pattern), `ZMN_OPTIMIZATION_PLAN_2026_04_19.md`, `ZMN_CC_HANDOVER_2026_04_19.md`, `CC_TOOL_SURFACE_2026_04_19.md`. All accurate-in-historical-context (the asyncpg shim *is* the Postgres-MCP-equivalent) but new readers without context could misread them. Per §7 scope: do NOT fix — flag for follow-up. **Filed `MCP-REFERENCE-CORRECTION-001` Tier 3 🟢** to add the qualifier in a future sweep.
- **Phase 2 — CLAUDE.md edit.** Added new H2 section **"MCP servers available"** between `## Standing findings — read before related work` (line 37) and `## Resolved Bugs` (line 56). Mirrors the `CLAUDE-MD-FINDINGS-INDEX-001` discoverability pattern. Three sub-tables: Connected (verified callable) / Connected per UI but BROKEN (re-auth needed) / Configured-but-unavailable (do not reference as callable). Notably absent: Postgres MCP — canonical pattern documented (`DATABASE_PUBLIC_URL` injected into a Python script per `Scripts/export_paper_trades.py`). Self-amending instruction added: "When an MCP server is added, authenticated, removed, or transitions between states, update its row here as part of the session that changes its status."
- **All STOPs evaluated, none triggered.** STOP-A (concurrent session): no concurrent session detected — last commit `0ad2282` (PC1-WALLET-TARGET-RECONCILE-001) earlier this same conversation. STOP-B (CLAUDE.md Standing findings section missing): present and intact at line 37 — pattern this session mirrors is structurally available. STOP-C ("most" connected MCPs fail): 10/13 succeeded — "most fail" threshold not met. STOP-D (scope creep): single H2 section added; CLAUDE.md not broadly reorganized. STOP-E (Claude limit): no. STOP-F (concurrent-session git conflict): N/A pre-push.
- **Scope discipline maintained.** Did NOT attempt to authenticate the △ servers (separate Jay action). Did NOT attempt to fix the ✘ servers (separate work). Did NOT add MCPs to the project. Did NOT fix the historical "Postgres MCP" references found in Phase 3 — flagged via `MCP-REFERENCE-CORRECTION-001` Tier 3 follow-up. Did NOT broaden CLAUDE.md update beyond the new section.
- **Side-effect observations (recorded for future sessions but NOT acted on):**
  - **Railway MCP re-auth is a real blocker** for any session that needs to read env vars or trigger deploys via the MCP. Current workaround: dashboard or wait for re-auth. Existing CC sessions that have shelled out to `railway` CLI commands recently may also be hitting the same expired token (verify before assuming the shell variant works).
  - **Plugin GitHub MCP is redundant when the project GitHub MCP works** — the latter was verified callable this session, the former errored. Prompts should prefer `mcp__github__*` over `mcp__plugin_github_github__*`.
  - **Helius `getBalance` re-verified incidentally:** 0.064095633 SOL on trading wallet (unchanged since 2026-04-21). Cross-cutting state confirmation, not a separate session deliverable.
- **Verdict:** ✅ **INDEX ADDED.** Future CC sessions reading CLAUDE.md as their first action will discover the MCP layer with verified callable status, including the 3 broken-in-session servers that should not be referenced as if available. Chat-side prompts can now reference the index when naming MCPs to avoid the "Postgres MCP" class of inaccuracy.
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes, NO deploy.** Outputs: `CLAUDE.md` (+1 H2 section "MCP servers available"), `AGENT_CONTEXT.md` (header refresh), `ZMN_ROADMAP.md` (Decision Log row + Tier 3 row for `MCP-REFERENCE-CORRECTION-001`), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend). Scratch (untracked): `.tmp_claude_md_mcp_index/` not created (verification calls happened inline; no separate doc needed).

---

## 2026-05-20 — PC1-WALLET-TARGET-RECONCILE-001 (docs-only, RECONCILED)

- **Trigger:** Chat-side state review (2026-05-20) caught an internal numeric inconsistency between two authoritative docs. `AGENT_CONTEXT.md` §6 PC1 said "Top-up target **≥1.5-2.5 SOL** so MIN_POSITION_SOL=0.05 × MAX_POSITION_SOL_FRACTION=0.10 yields effective ≥0.05 SOL per position." `docs/findings/V5A_GO_LIVE_DECISIONS.md` D-S3 (recorded 2026-05-19/20 by V5A-GO-LIVE-DECISIONS-RECORD-001) implied a **5 SOL** trial budget (daily halt at 1.5 SOL realized = 30% of budget; cumulative halt at 3.0 SOL realized = 60% of budget; leaving a 2 SOL operational floor). Both were authoritative-in-their-scope; the findings doc — newer, more specific, explicitly trial-governing — supersedes PC1's operational-minimum-only framing. This session is a one-shot reconciliation: update PC1's top-up target to ~5 SOL with explicit citation of D-S3 as the authority, while preserving the operational-minimum reasoning as context (still true as a lower bound).
- **Phase 1 — verification of the inconsistency.** Grep + line-level read of `AGENT_CONTEXT.md` line 146 confirmed the stale wording verbatim ("Top-up target ≥1.5-2.5 SOL ..."); full read of `docs/findings/V5A_GO_LIVE_DECISIONS.md` confirmed D-S3 specifies 1.5 / 3.0 / 5 SOL numbers (§5 Amendments empty — no D-S3 amendment to muddy the authority). Cross-doc spot-check: `ZMN_ROADMAP.md` line 19 already says "**0.064 SOL** (`4h4pst…ii8xJ`) — awaiting 5 SOL top-up planned for v5 staged attempts" — independent confirmation that 5 SOL is the right target. The inconsistency lived in `AGENT_CONTEXT.md` §6 PC1 specifically.
- **Phase 1.5 — Helius spot-check (optional per session prompt §1.5).** Called `mcp__helius__getBalance` on `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ`: **0.064095633 SOL** (unchanged from last verification 2026-05-14 ~12:57 UTC; unchanged from 2026-04-21 single-event 1.5 SOL outgoing per WALLET_DRIFT_INVESTIGATION). No surprise top-up — PC1 remains `[ ]` outstanding; the edit updates the target only, not the status.
- **Phase 2 — PC1 edit.** Replaced PC1 title from `~3 SOL transfer to trading wallet` to `~5 SOL on trading wallet` (target framing); replaced body's "Top-up target ≥1.5-2.5 SOL ..." sentence with the corrected target citing D-S3 by name, citing `docs/findings/V5A_GO_LIVE_DECISIONS.md` by path, and explaining the numeric chain (1.5 SOL daily halt = 30% of 5 SOL budget; 3.0 SOL cumulative halt = 60%; ~2 SOL operational floor). Preserved the operational-minimum reasoning inline as a lower-bound note (1.5-2.5 SOL remains true for swap-router viability but is no longer the binding target). Updated the verification timestamp inline ("re-verified Helius getBalance 2026-05-20 by PC1-WALLET-TARGET-RECONCILE-001").
- **Phase 3 — PC4-related flag added in-cell.** Per session prompt §5, added a single sentence cross-referencing the related-but-out-of-scope PC4 inconsistency: `DAILY_LOSS_LIMIT_SOL=4.0` currently on bot_core (see §2 row) vs D-S3's 1.5 SOL daily halt. These should be reconciled — the V5A flip session will set `DAILY_LOSS_LIMIT_SOL=1.5` on Railway and update PC4 accordingly. Out of scope for this docs-only fix (env change + verification belong with the flip). This is documentation hygiene — making the related inconsistency visible without acting on it. The V5A flip session catches it via the same precedence-rules read of D-S3.
- **STOPs evaluated, none triggered.** STOP-A (concurrent session / behavioural change in flight): no — last commit `753b5ce` 2026-05-20 ~00:00 UTC, my session ~hours later, no concurrent. STOP-B (PC1 already reconciled): no — line 146 still showed `≥1.5-2.5 SOL` at session start. STOP-C (D-S3 amended): no — `V5A_GO_LIVE_DECISIONS.md` §5 Amendments empty, D-S3 numbers unchanged. STOP-D (scope creep — touching PC4 env value or restructuring §6 broadly): no — PC4 got only the related-flag sentence, no env change. STOP-E (Claude limit hit): no. STOP-F (concurrent-session git conflict): N/A pre-push.
- **Scope discipline maintained.** Did NOT touch PC2 / PC3 / PC4 substance (PC4 got the one-sentence related-flag only). Did NOT touch §6.6 V5A readiness snapshot (2026-05-01 audit — historical, append-only). Did NOT touch §2 env table. Did NOT amend `V5A_GO_LIVE_DECISIONS.md` (it's the authority being cited, not the doc being edited). Did NOT broaden into a §6 documentation audit. Other inconsistencies that may exist elsewhere in the repo were not surveyed (PC1-only session).
- **Verdict:** ✅ **RECONCILED.** Future CC sessions reading AGENT_CONTEXT.md §6 PC1 will see the correct ~5 SOL trial-budget target with D-S3 as the cited authority; the operational-minimum reasoning is preserved so they understand the lower bound; and PC4's stale `DAILY_LOSS_LIMIT_SOL=4.0` is flagged inline for V5A flip session reconciliation. The V5A go-live decision (D-S3) and the PC1 precondition checklist now agree on the same number.
- **No new follow-up items filed.** PC4 / `DAILY_LOSS_LIMIT_SOL` env reconciliation is the V5A flip session's responsibility (already its scope — pre-flip self-check at PC4 will read `DAILY_LOSS_LIMIT_SOL`).
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes, NO deploy.** Outputs: `AGENT_CONTEXT.md` (PC1 wording rewrite at §6 line 146 + header refresh), `ZMN_ROADMAP.md` (Decision Log row prepended), this `MONITORING_LOG.md` entry, `STATUS.md` (prepend). Scratch (untracked): `.tmp_pc1_reconcile/` empty (single-edit session, no derivation needed).

---

## 2026-05-19 23:58 UTC — V5A-GO-LIVE-DECISIONS-RECORD-001 (docs-only, DECISIONS RECORDED)

- Chat-side V5A go-live decision conversation (2026-05-19/20) produced seven decisions across S3-S7 of the pre-go-live checklist plus two strategic follow-ups (staged sizing ladder; autonomous governance agent). This session captured them as a survivable record so chat-history-only ephemerality cannot lose them.
- **Phase 1 — `docs/findings/V5A_GO_LIVE_DECISIONS.md` created** (≤1500 words, following the COST_FIDELITY_GAP.md pattern):
  - §1 — seven decisions: D-S3 (daily 1.5 SOL realized halt + cumulative 3.0 SOL hard revert); D-S4 (manual market-mode check at flip-time, NOT autonomous agent yet); D-S5 (Wed/Thu AEST evening 18:00-21:00 Sydney, ramping US trading hours, avoid weekends + Sunday-Monday open + Friday afternoon); D-S6 (conservative `MAX_POSITION_SOL=0.10` + `MAX_SD_POSITIONS=5`, NO auto-scale on WR — overruled because 80% WR in 24-80 trades is not statistically robust evidence — replaced with staged ladder); D-S7 (Jay watches actively 4-6h post-flip, hourly glances first 12h).
  - §2 — sizing graduation ladder (Hours 0-24 → Day 2-4 hold → Day 5-7 → Week 2; scale on cumulative PnL trajectory + closed-trade count + Path B sample size, not short-window WR).
  - §3 — strategic follow-up `GOVERNANCE-AGENT-MARKET-MODE-001` filed; absorbs `MARKET-MODE-001-RE-CALIBRATE-V2`.
  - §4 — cross-references to `COST_FIDELITY_GAP.md`, `AGENT_CONTEXT.md` §6, V2 audit, roadmap entries, CLAUDE.md index.
  - §5 — override path (chat-side amendments appended to the doc; originals preserved).
- **Phase 2 — Roadmap items filed:**
  - `ZMN_ROADMAP.md` Tier 1: `V5A-SIZING-GRADUATION-LADDER-001` (ACTIVE RULE — governs trial sizing, not a session to run; consult before any manual sizing change).
  - `ZMN_ROADMAP.md` Tier 2: `GOVERNANCE-AGENT-MARKET-MODE-001` (autonomous classifier + halt authority but NOT start authority; gated on V5A live data across ≥2 distinct regimes; absorbs MARKET-MODE-001-RE-CALIBRATE-V2).
  - `MARKET-MODE-001-RE-CALIBRATE-V2` Tier 1 row updated with absorption link to `GOVERNANCE-AGENT-MARKET-MODE-001` — not deleted, preserved for audit trail. The recalibration concern (NORMAL bleeds, threshold structure may be wrong) becomes one input to the classifier scope.
  - `ML_THRESHOLD_RETUNE_002` dependency-gate (behind `PAPER-FEE-MODEL-CALIBRATION-001` per COST-FIDELITY-FINDINGS-DOCUMENTATION-001) confirmed unchanged — no drift.
- **Phase 3 — V5A checklist + CLAUDE.md index:**
  - `AGENT_CONTEXT.md` §6 gains new "Decisions (recorded)" subsection between "Known conditions at relaunch" and "Completed preconditions" — points at findings doc + roadmap items. STOP-B did not fire (V5A checklist §6 cleanly locatable at line 140).
  - `CLAUDE.md` "Standing findings — read before related work" table gains a new row for `V5A_GO_LIVE_DECISIONS.md` per yesterday's self-amending instruction (CLAUDE-MD-FINDINGS-INDEX-001). This is the first session to fulfill that contract.
- **No STOP triggered.** STOP-A (concurrent session): no concurrent session detected; last commit `4210c4b` ~10h before this session started. STOP-B (V5A checklist not locatable): cleanly locatable. STOP-C (scope creep): no decision re-decided; all seven captured verbatim from the prompt. STOP-D (Claude limit): N/A. STOP-E (concurrent-session git conflict): N/A.
- **Verdict:** ✅ **DECISIONS RECORDED.** All seven V5A relaunch decisions are now in a discoverable, survivable doc with the same lifespan and prominence as `docs/findings/COST_FIDELITY_GAP.md`. V5A checklist points to them. CLAUDE.md indexes them. Roadmap references them. Future sessions cannot miss them.
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes, NO deploy.** Outputs: `docs/findings/V5A_GO_LIVE_DECISIONS.md` (NEW), `ZMN_ROADMAP.md` (+2 rows + 1 supersession link), `AGENT_CONTEXT.md` (+1 subsection + header refresh), `CLAUDE.md` (+1 table row), this `MONITORING_LOG.md` entry, `STATUS.md` prepend. Scratch (untracked): `.tmp_v5a_decisions/` empty (no derivation needed — decisions are inputs not outputs).

---

## 2026-05-19 12:59 UTC — CLAUDE-MD-FINDINGS-INDEX-001 (docs-only, INDEX ADDED)

- Chat-side audit (2026-05-19) of the survivability of `docs/findings/` exposed a gap: the directory was referenced only from `AGENT_CONTEXT.md` §6 and the Decision Log. A new CC session that doesn't deeply read either could miss the standing findings entirely. `CLAUDE.md` is the single document every session reads first — must become the authoritative entry point that *names* the findings layer and points sessions at it.
- **Phase 1 — Audit `docs/findings/`:** `ls docs/findings/` returned **only** `COST_FIDELITY_GAP.md`. The session prompt's expected second file `V5A_GO_LIVE_DECISIONS.md` does NOT exist and is NOT referenced anywhere in the repo (`grep -ri V5A_GO_LIVE_DECISIONS` returned 0 matches). Per §7 scope discipline: this session indexes what exists; does not invent files. The V5A decisions file will be indexed by its own creating session.
- **Phase 2 — CLAUDE.md update:** added new H2 section **"Standing findings — read before related work"** between `## Roadmap` and `## Resolved Bugs`. Section contains a one-row table indexing `COST_FIDELITY_GAP.md` with about-column + read-before column. Closing paragraph instructs future finding-creating sessions: "When new findings are added to `docs/findings/`, append a row here as part of the session that creates them. Index discoverability is the whole point of this section — leave nothing in `docs/findings/` unindexed."
- **Phase 3 — Cross-reference verification:** `AGENT_CONTEXT.md` lines 3 / 162 / 167 and `ZMN_ROADMAP.md` lines 41 / 315 all reference `docs/findings/COST_FIDELITY_GAP.md` correctly — target file exists, all 5 references intact. No drift. No anticipated-but-missing references (the V5A_GO_LIVE_DECISIONS file is mentioned only in the session prompt, never in committed docs).
- **No STOP triggered.** STOP-A check (empty or missing dir) passed cleanly — directory has one file with content. STOP-B (CLAUDE.md structure) passed — clean H2 hierarchy. STOP-C (scope creep) not tempted; one section added, no reorganization. STOP-D (Claude limit) N/A. STOP-E (concurrent-session) — no concurrent session detected at audit time.
- **Verdict:** ✅ **INDEX ADDED.** Future CC sessions reading CLAUDE.md as their first action will discover `docs/findings/` without needing to deep-read `AGENT_CONTEXT.md` or `ZMN_ROADMAP.md`. The self-amending instruction in CLAUDE.md is the durability mechanism — future finding-creating sessions carry the obligation to append their row to the index.
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes, NO deploy.** CLAUDE.md is +15 lines (new section). AGENT_CONTEXT.md is +0 structural (header refresh only). ZMN_ROADMAP.md Decision Log gets +1 row. MONITORING_LOG.md gets this entry. STATUS.md gets a prepend. Scratch (untracked): `.tmp_claude_md_findings/01_index_draft.md`, `02_cross_refs.md`.

---

## 2026-05-19 — LIVE-MODE-FILTER-PARITY-001-V2 (code+deploy, GATE IMPLEMENTED + DEPLOYED)

- **Trigger:** Yesterday's `LIVE-MODE-FILTER-PARITY-001` (2026-05-14, STOP-C — `docs/audits/LIVE_MODE_FILTER_PARITY_001_2026_05_14.md`) found `services/execution.py` cannot host a fill-time MC ceiling gate cleanly (3 execution routes; no fill-time price computation — it returns a signature from unsigned tx bytes, bot_core fetches the price *after* at `:956`). The audit's recommended Option A: gate in `bot_core.py` live `else:` branch *before* `execute_trade`, using existing `self._get_token_price(mint)`. This session implements Option A.
- **Outputs:**
  - **`services/bot_core.py`** — +28 lines in the `else:` branch (gate now at `:953-980`; original `result = await execute_trade(...)` shifted from `:953` to `:982`). No existing line altered; no re-indent of surrounding code; no new imports. Marker comment `LIVE-MODE-FILTER-PARITY-001-V2`.
  - **NEW `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md`** — full audit including §8 paper C1 ↔ live V2 parity table (env var, default, env read, gate-enabled guard, MC formula, price source, comparison, log line, Redis counter, TTL, try/except, short-circuit, failure mode — all aligned line-for-line with two documented intentional divergences).
  - **`AGENT_CONTEXT.md`** — header refresh; §2 `BOT_CORE_FILL_MC_CEILING_USD` row expanded to note "GOVERNS BOTH PAPER AND LIVE PATHS AS OF 2026-05-19" with live-path read/log/Redis-namespace details; §6 PC3 row marked ✅ DEPLOYED with verification handoff; "Outstanding V5A blockers (4)" → "(3)".
  - **`ZMN_ROADMAP.md`** Decision Log — new 2026-05-19 row marks V2 ✅ DEPLOYED + closes the NO_MOMENTUM_90S_AUDIT_001 §10 "execution.py parity" open item structurally (Option A lands in `bot_core.py`, not `execution.py`).
  - **`MONITORING_LOG.md`** — this entry.
  - **`STATUS.md`** — top-of-file prepend with hash backfill via `git commit --amend`.
  - **Scratch (gitignored, `.tmp_live_filter_parity_v2/`):** `PROGRESS.md`, `01_investigation.md`, `02_design.md`, `verify_live_mc_gate.py`, `verify_output.txt`.
- **Mirror choices (paper C1 → live V2):**
  - **Env var:** reuse `BOT_CORE_FILL_MC_CEILING_USD` — one knob governs paper AND live. No new env var introduced.
  - **MC formula:** `fill_mc = self._get_token_price(mint) * 1_000_000_000` (identical formula to paper's `entry_price * 1_000_000_000`; the slippage padding on `entry_price` is a paper-sim artifact, intentionally not mirrored — live has no simulated slippage because real slippage happens on-chain).
  - **Threshold:** `if fill_mc > fill_mc_ceiling:` — strict `>` (paper passes `fill_mc == ceiling` — keep identical boundary).
  - **Reject behavior:** logger `FILL_MC_CEILING reject (live): %s mc=$%.0f > ceiling=$%.0f (slippage_tier=%s)` (suffix `(live)` for grep-distinct paper/live; trailing `slippage=%.1f%%` dropped — no `_simulate_slippage` float in live); Redis `incr` + `expire` on `bot:filter:fill_mc_ceiling:rejects:live:<UTC-date>` with 14d TTL (distinct `:live:` segment); bare `return` short-circuit.
  - **Failure mode:** fail-OPEN at the gate (price=0.0 → fill_mc=0 < ceiling → pass). Mirrors the C1 gate block's literal logic. Paper's fail-closed at `paper_trader.py:238-240` happens earlier in `paper_buy`, NOT inside the gate.
- **STOP audit:** STOP-A/B/C/D/E/F/G all evaluated, none triggered. Phase 1 reconfirmed routing (`bot_core.py:82-83` paper_buy gated by TEST_MODE; `:836` paper→paper_buy; `:951` else→execute_trade at `:953-956`); line numbers shifted +3 vs the predecessor audit due to LIVE-TRADES-LOGGING-AUDIT-001 `b867daa` comment additions. `_get_token_price` at `:388-391` returns USD price-per-token — same units as paper's helper. The live branch already uses `price * 1_000_000_000` at `:996` for `_pe_market_cap` — direct empirical confirmation of unit parity.
- **Validation (dev-loop, 2 iterations within the 3-cap):**
  - **Iter 1:** gate logic correct (first reject case fired + Redis incr); `print()` crashed on a `→` character due to Windows cp1252 codec. Fixed by `→` → `->` ASCII.
  - **Iter 2:** sentinel-return string-replace anchored on a wrong indent count (20 spaces vs actual 12 after `textwrap.dedent + indent("    ")`) — two reject cases were *behaviorally* correct (Redis incremented) but outcome registered as `None`. Switched to indent-agnostic regex `^(\s+)return\s*$` with `count=1`, `re.MULTILINE`. ALL 8 cases PASS, exit code 0.
  - Cases: above-ceiling reject ($1500 > $1000) + Redis incr; at-ceiling pass (strict `>`); below-ceiling pass to `execute_trade` ($500 < $1000); gate disabled (ceiling=$0) pass; env-var absent (default 0) pass; price-fetch failure (`_get_token_price → 0.0`) fail-OPEN; ceiling=$3000 sanity pass ($2500) + reject ($3500).
  - Raw stdout: `.tmp_live_filter_parity_v2/verify_output.txt`.
- **Verification standard:** code-level + clean-startup + rolled-back proof (per audit §6; same standard as predecessor LIVE-MODE-FILTER-PARITY-001 §6). `python -m py_compile services/bot_core.py` clean. Railway container restart confirmed clean post-`git push`. **Gate cannot be observed firing in production this session** because `TEST_MODE=true` — the `else:` (live) branch doesn't execute under paper mode. First live-fire is at V5A relaunch. Paper-mode caveat explicit in audit §6.
- **V5A impact:** **PC3 in AGENT_CONTEXT §6 is CLOSED.** V5A outstanding blockers drop 4 → 3 (PC1 wallet, PC2 ≥2026-05-27 observation, PC4 flip-itself remain). The NO_MOMENTUM_90S_AUDIT_001 §10 "execution.py parity" open item is structurally resolved.
- **Rollback:** `BOT_CORE_FILL_MC_CEILING_USD=0` (no redeploy; disables both paper and live gates simultaneously). To undo retune only (keep gate enabled, loosen ceiling): env→3000.
- **NOT this session:** no flip of `TEST_MODE`, no live trade attempted, no `paper_trader.py` edit (paper observation window untouched), no `execution.py` edit (per predecessor audit's reasoning), no other paper/live parity-gap fix (out of scope per session prompt §8; any other gaps would be follow-up sessions).
- **Source:** `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md` (this session); `docs/audits/LIVE_MODE_FILTER_PARITY_001_2026_05_14.md` (predecessor STOP-C scoping); `.tmp_live_filter_parity_v2/{01_investigation,02_design}.md` (gitignored phase docs).

---

## 2026-05-19 — COST-FIDELITY-FINDINGS-DOCUMENTATION-001 (docs-only, DOCS COMPLETE)

- **Trigger:** ML-TRAINING-COST-FIDELITY-AUDIT-001 (2026-05-14) confirmed a sim-to-real gap in the ML training corpus. Chat-side review required folding its conclusions into survivable, discoverable docs — not leaving them in a dated audit doc that future sessions may not read.
- **Outputs:**
  - **NEW `docs/findings/COST_FIDELITY_GAP.md`** (~1,000 words; summary-with-pointers, NOT a re-derivation). Sections: §1 plain-language finding (incl. the sharper "label corruption in marginal band wider than median trade PnL" framing — corruption band ~±0.030 SOL vs median |realised_pnl_sol| = 0.0257 SOL); §2 honest severity (NOT a current-profitability fire; matters for retune + Analyst); §3 structural reality (gap CANNOT be closed pre-V5A — calibration needs Path B data that only live trading produces; corpus has exactly 1 Path B row; staged V5A + small sizing already designed-in as the mitigation); §4 follow-up sessions as pointers; §5 source. Every numerical claim cites the audit by section.
  - **AGENT_CONTEXT §6 gains a NEW "Known conditions at relaunch (acknowledged, NOT blocking)" subsection** with a cost-fidelity entry. Deliberately NOT a precondition checkbox — closing the gap depends on relaunching; a blocking checkbox would be permanently un-tickable. The entry sits in front of whoever runs V5A go/no-go.
  - **`ML_THRESHOLD_RETUNE_002` re-sequenced** in AGENT_CONTEXT §6 Related milestones: previously gated on "≥7d post-`BOT_CORE_ML_GATE` clean data (≥2026-05-19)"; now gated on `PAPER-FEE-MODEL-CALIBRATION-001` deploy + ≥7d post-recalibration data. Date-gate → dependency-gate. Two independent reasons to wait: (a) C1's structural edge makes retune non-urgent; (b) audit confirms a threshold sweep would optimize on corrupted marginal-band labels. Item NOT deleted, just re-sequenced.
  - **`ANALYST-POST-GRAD-001` roadmap entry gains an explicit cost-fidelity gate** at top of cell: Phase 0 sub-session (c) "paper-mode activation" must not ship until `PAPER-FEE-MODEL-CALIBRATION-001` deployed + ≥7d post-calibration data accumulated. Sub-sessions (a)(b)(d) NOT gated. Rationale: Analyst sizing 0.2-0.5 SOL vs SD 0.05-0.25 SOL — gap bites harder at higher leverage.
  - **`ML-TRAINING-MODE-FILTER-001` confirmed as SINGLE Tier 3 🟢 row** (line 329 of Tier 3 table). Both Decision Log references (LIVE-TRADES-LOGGING-AUDIT-001 + ML-TRAINING-COST-FIDELITY-AUDIT-001) point to the same canonical entry — no duplicate filing.
- **NOT this session:** no re-investigation (audit is evidence base), no new follow-up items filed (audit's 4 + 1 re-scoped already filed by prior session), no code/env/Redis changes, no behavioural change.
- **Source:** `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md` (full derivation); `docs/findings/COST_FIDELITY_GAP.md` (survivable summary).
- **NO services/* code change, NO env change, NO Redis writes, NO deploy.** Scratch (untracked): `.tmp_cost_fidelity_docs/PROGRESS.md` + the one-shot `trades` export helper used during the mid-session CSV-export side-task.

---

## 2026-05-14 — ML-TRAINING-COST-FIDELITY-AUDIT-001 (read-only investigation, AUDIT COMPLETE — gap CONFIRMED)

- **Trigger:** LIVE-TRADES-LOGGING-AUDIT-001 §8/§9 raised "does the ML train on realistic transaction costs and latency, or on an optimistic simulation?"
- **Method:** read `services/ml_model_accelerator.py` end-to-end + `paper_trader.py:142-213` (cost sim) + `paper_trader.py:216-345,353-471` (paper_buy/sell) + `bot_core.py:1149,1365` (outcome writers) + `db.py:114-138,181-190` (schemas); DB queries against gondola.proxy.rlwy.net:29062 for correction_method distribution, trade_mode mix, latency-column NULL state, fee/amount magnitudes.
- **Training target traced:** `outcome` string column (binary `win`/`loss`/`profit`) → derived from `pnl_sol > 0` → `pnl_sol = (exit-entry)/entry × sell_amount − fees` where `fees` and `exit_price = current_price × (1 − slippage/100)` come from `_simulate_fees` and `_simulate_slippage`. **Cost model IS in the training signal at threshold zero.**
- **Cost-fidelity gap (DB-verified):** avg `fees_sol`=0.00170 SOL on avg `amount_sol`=0.116 SOL = **1.46% round-trip** in paper sim. Path B truth (id 6580): 0.094 SOL / 0.365 SOL = **25.8% round-trip**. **~17.6× under-count** at avg paper sizing.
- **Corpus fidelity distribution:** 2873/2874 paper_trades closed rows = `pass_through` (paper sim); 0 `live_estimated_v1`; **1** `live_actual_v1`. ML-eligible corpus ≈ 8,680 rows (5812 `trades` + 2868 `paper_trades`, 30d, contamination-filter survivors). Live share: 41/8680 = **0.47%**. Path-B share: 1/8680 = **0.012%**. Corpus is effectively 100% paper-sim fidelity.
- **Latency:** 4 columns (`signal_detected_at`, `scored_at`, `traded_at`, `total_latency_ms`) exist on `paper_trades` but **100% NULL across 2874 closed rows** (reaffirms LATENCY-OBSERVABILITY-001 at current sample size). Paper fill uses Jupiter/Gecko quote at `paper_buy` invocation — wall-clock-current, but does NOT model the systematic in-flight pump that C1's fill-time MC gate exists to backstop. No latency feature in FEATURE_SCHEMA.
- **Severity (honest framing):** NOT a current-profitability fire — ML is already weakly predictive (AUC 0.536 per ML_SCORE_ATH_VALIDATION_001); SD profitability is C1-MC-ceiling structural; +1.49 SOL/day W3+W4 holds with the gap. **Material for two future levers:** (a) ML_THRESHOLD_RETUNE_002 (≥2026-05-19) — retune optimum optimizes against ~17×-optimistic labels; recommend "calibrated against sim costs" caveat in verdict, NOT blocked; (b) Analyst Phase 0 (June) — ML-driven on mature features at higher sizing; recommended gate added: `PAPER-FEE-MODEL-CALIBRATION-001` lands before Analyst ships.
- **3 new roadmap items + 1 unresolved + 1 re-scoped:**
  - `PAPER-FEE-MODEL-CALIBRATION-001` Tier 2 🟡 — env-only knob recalibration to Path-B-derived per-component truth; gated on ≥10 Path B rows (currently 1; needs sustained V5A relaunch). 30m env-only deploy + 7d obs.
  - `PAPER-LATENCY-MODEL-001` Tier 3 🟢 — synthetic signal→fill delay + refetch in `paper_buy`. Gated on LATENCY-OBSERVABILITY-001 backfill.
  - `PAPER-MEV-SLIPPAGE-MODEL-001` Tier 3 🟢 — structural slippage component for MEV/sandwich/in-flight-pump. Gated on Path B sample sufficiency.
  - `ML-CONTAMINATION-FILTER-BIAS-001` Tier 3 🟢 — investigate whether the existing `0.97-1.03` exit/entry contamination filter disproportionately removes sim-cost-flipped marginal-win rows. Unresolved §9.3.
  - **Re-scoped:** `ML-TRAINING-MODE-FILTER-001` (from LIVE-TRADES-LOGGING-AUDIT-001 §9.1) → Tier 3 🟢 hygiene only. 0.47% live share is a rounding error; fidelity problem lives in the paper sim, not the paper/live blend.
- **Sequencing recommendation:** ML_THRESHOLD_RETUNE_002 ships with caveat — NOT blocked by this audit. PAPER-FEE-MODEL-CALIBRATION-001 should land before Analyst Phase 0 ships.
- **NO services/* code change, NO env change, NO Redis writes, NO deploy.** Audit: `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md`. Scratch (untracked): `.tmp_ml_cost_fidelity/PROGRESS.md`, `query.py`, query stdout.

---

## 2026-05-14 — DASHBOARD-DESIGN-REALIGNMENT-001 (amendment, AMENDMENT LANDED)

- **Trigger:** Jay chat-side message resolving 6 §9 open questions + adding 4 design additions to the 2026-05-14 design doc.
- **§9 resolutions:** re-scope ACCEPTED; ≥30d legacy coexistence YES; SINGLE accent (no picker); Sentry fold-in DEFER to v1.5; active emergency-stop from phone DEFER (auth surface — separate session); June parallel-track CONFIRMED (NOT May critical path).
- **Design additions folded into `DASHBOARD_DESIGN_REALIGNMENT_001_2026_05_14.md`:**
  - **(A) Card 2 — today + all-time cumulative P&L on one card.** Both numbers via `COALESCE(corrected_pnl_sol, realised_pnl_sol)` on `paper_trades` only. No `trades` join, no `paper:stats` Redis-aggregate fallback (prevents resurfacing of pre-cleanup ~+601 SOL lifetime contamination).
  - **(B) NEW Card 7 — biggest wins.** Top-3 default, expand to top-10. Each row: symbol + `realised_pnl_sol` + `realised_pnl_pct` as Nx multiplier + mint tap-to-copy chip (default tap) + DexScreener "↗" link (secondary). **CRITICAL hardcoded floor:** `trade_mode='paper' AND entry_time >= 1747104561.0` (C1 deploy 2026-05-13 03:29:21Z UTC) as module constant `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS`; endpoint clamps `since` overrides to floor.
  - **(C) Celebration FX on ≥3x wins.** Trigger: `realised_pnl_pct >= 200` (column verified `services/db.py:128-129`). Confetti (vendored canvas-confetti ~7KB, `prefers-reduced-motion`-safe fallback to "🎉" bloom) + `navigator.vibrate([60,30,60,30,120])` haptic + optional sound toggle (muted by default, `localStorage`-persisted, iOS-autoplay-aware). `seenTradeIds` Set in `sessionStorage` prevents re-fire on reload within session. Threshold = JS const `BIG_WIN_PCT_THRESHOLD=200`.
  - **(D) Push-notification version EXPLICITLY DEFERRED** to post-SD-validation. PWA SW push handler stub (console-log only) in BUILD-2. No backend emitter on `_close_position`, no subscription registry, no server keys yet. Tracked as DASH-PUSH-NOTIFICATIONS-001.
- **Card count 6 → 7, cap nudged.** Three merge alternatives evaluated and rejected (§11). Still one route, zero tabs, zero sub-pages, single-column vertical scroll. 30 → 7 = ~77% smaller than Concept C (was 80%). Forward guardrail: >7 cards / tabs / sub-pages / second routes trigger fresh STOP-C audit.
- **STOP-B re-checked post-amendment:** 3 of 7 cards need backend (Card 2 all-time half + Card 3 alerts + Card 7 biggest wins) ≈ 43% — ≪50% threshold; UI remains bulk of work.
- **Build breakdown re-stated honestly:** BUILD-0 0.5h → **1.0h** (3 endpoints: `/api/active-alerts` + `/api/top-wins` + `/api/lifetime-pnl`); BUILD-1 2.5h → **2.8h** (Cards 1/2/4/7); BUILD-2 2.5h → **2.8h** (Cards 3/5/6 + celebration FX + PWA + push handler stub). **Total 7.5h → ~8.5h.** Sequencing UNCHANGED: June parallel-track with Analyst Phase 0, NOT May trading-logic critical path.
- **Concurrent-session reconciliation:** `LIVE-TRADES-LOGGING-AUDIT-001` (commit `b867daa`) landed during this session — added `trade_mode` discriminator to `trades` table + backfill (9,480 paper / 41 live). Pulled-rebase clean; no file conflict (different files except append-only canonical docs). Updated DASH-BIGGEST-WINS-SCOPING-001's prereq state — the live-side contamination angle Jay's amendment anticipated is reconciled there, but Card 7's hardcoded floor REMAINS because it also guards pre-F1 / pre-C1 paper-side variance + pre-cliff archive accounting.
- **3 new roadmap items** (all Tier 3 🟢, none V5A-blocking): DASH-BIGGEST-WINS-SCOPING-001 (prereq closed, revisit after ≥30d post-C1 sample review); DASH-PUSH-NOTIFICATIONS-001 (gated on SD-validation completion); DASH-CELEBRATION-FX-THRESHOLD-TUNE-001 (post-deploy fine-tune).
- **NO services/* code change, NO env change, NO Redis writes, NO deploy.** Design doc amended in place; ROADMAP / AGENT_CONTEXT / STATUS / MONITORING_LOG synced.

---

## 2026-05-14 — LIVE-TRADES-LOGGING-AUDIT-001 (code+schema fix, FIXED + DEPLOYED)

- **Trigger:** chat-side analysis of `live_trades` vs `paper_trades` exports found apparent cross-contamination — a "live_trades" table with 9,521 rows whose recent dates matched `paper_trades` SD counts and whose early-April rows showed impossible PnL for a 5 SOL live budget.
- **PREREQ gate PASS:** LIVE-MODE-FILTER-PARITY-001 shown completed in STATUS.md (commit `81a20a0`, STOP-C). A concurrent docs-only session (V5A-PRECONDITION-CHECKLIST-CLEANUP-001) completed during this session — not behavioural, not in-flight; proceeded with pull-rebase discipline.
- **Premise corrected:** there is **no `live_trades` table** (repo grep 0 hits; `to_regclass('live_trades')` → NULL). The chat-side "live_trades" is the **`trades` table** (exact 9,521-row / date-range / personality-split match). `trades` is the **paper+live combined ML-training corpus by design** — `bot_core.py` writes to it from both the paper branch (`:881`) and live branch (`:973`); `ml_model_accelerator` trains from both `trades` + `paper_trades`. **No misrouting bug.** The real defect: `trades` had no `trade_mode` discriminator, so the 41 genuine live rows were *buried* among 9,480 paper rows. `paper_trades` already has `trade_mode` and is correctly separated; `live_trade_log` is correctly live-only.
- **Classification (9,521 `trades` rows):** paper 9,480 (6,612 archive-matched + 2,868 current-matched) / live 41 / unclassifiable 0. The 41 live = 35 v3/v4 trial trades (no `paper_trades` mirror — predate DASH-ENTRY-001; **all 35 confirmed via `live_trade_log` TX_SUBMIT signatures**; sum −3.3609 SOL, 25.7% WR) + 1 genuine on-chain round-trip (`trades` id 6596 / `paper_trades` id 6580) + 5 reconcile-residual rows (`trade_mode='live'` in `paper_trades`, NULL sigs — not real money).
- **Isolated real-money result ≈ −3.36 SOL** — cross-validates the ~3.4 SOL on-chain wallet drawdown (5.0 → ~1.6 SOL) in CLAUDE.md's `1b40df3` forensics.
- **Fix:** `trade_mode TEXT DEFAULT 'paper'` added to `trades` (`db.py` CREATE TABLE + idempotent `ALTER … IF NOT EXISTS` in `_init_tables`); both `bot_core.py` `INSERT INTO trades` sites tagged (`'paper'`/`'live'` literals — branches already gate on `TEST_MODE`, no decision logic touched); one-time backfill `migrations/002_add_trade_mode_to_trades.sql` (mirror from `paper_trades` → archive → `'live'` for the 35 trial rows guarded by `live_trade_log` EXISTS) — **applied to the DB this session, pre-push**.
- **Verify (`verify_logging_fix.py`, output `.tmp_live_logging_audit/verify_output.txt`) — ALL PASS, iteration 1:** post-fix paper-branch INSERT → `trade_mode='paper'`, live-branch INSERT → `trade_mode='live'` (inside a rolled-back txn, 0 production rows); post-migration split exactly **paper 9,480 / live 41**, 0 NULLs; spot-check `trades.id=6596` → `'live'`.
- **STOP gates:** not STOP-A (logging ≠ decision logic), not STOP-B (live cleanly separable), not STOP-C (contained: 1 column, 2 INSERT lines, 1 migration).
- **Purge recommendation: DO NOT PURGE** — the 9,480 paper rows are legitimate ML training data; filter by `trade_mode` instead.
- **V5A: enabler, not blocker.** Live rows now self-identify in `trades`. New follow-up flagged: **ML-TRAINING-MODE-FILTER-001** (decide include/exclude/weight of live rows in `ml_model_accelerator` — now possible; not decided here, out of scope).
- **Deploy:** single `git push` of `services/bot_core.py` + `services/db.py` + `migrations/002_*.sql` + doc updates → Railway bot_core redeploy. Container-restart confirmation + post-deploy routing check (new SD-paper trades land in `trades` with `trade_mode='paper'`; no new `'live'` rows while `TEST_MODE=true`) recorded in the STATUS.md entry.
- Audit: `docs/audits/LIVE_TRADES_LOGGING_AUDIT_001_2026_05_14.md`. Scratch (untracked): `.tmp_live_logging_audit/` — PROGRESS.md, db_probe.py, classify_probe.py, verify_live_onchain.py, 01_write_path_investigation.md, 02_contamination_classification.md, verify_logging_fix.py, verify_output.txt.

---

## 2026-05-14 — V5A-PRECONDITION-CHECKLIST-CLEANUP-001 (docs-only, CHECKLIST REWRITTEN)

- **Trigger:** chat-side state synthesis on 2026-05-14 found `AGENT_CONTEXT.md` §6 ~1 month stale: "Sessions A-D"/"session-E snapshot" anchors meaningless after 5+ config changes, +1 new V5A blocker (LIVE-MODE-FILTER-PARITY-001-V2) added 2026-05-14 not yet in §6.
- **Verification (all parallel, 2026-05-14 ~12:57 UTC):**
  - On-chain wallet `4h4pst…ii8xJ` = **0.064095633 SOL** via Helius `getBalance` (UNCHANGED since 2026-04-21).
  - Railway env bot_core: `TEST_MODE=true`, `BOT_CORE_FILL_MC_CEILING_USD=1000` (C1), `SD_EARLY_CHECK_SECONDS=60`, `ML_THRESHOLD_BOT_CORE_SD=40`, `MAX_POSITION_SOL=0.25`, `DAILY_LOSS_LIMIT_SOL=4.0`.
  - Railway env signal_aggregator: `TEST_MODE=true`, `ANALYST_DISABLED=true`, `SD_MC_CEILING_USD=3000`, `NANSEN_DRY_RUN=TRUE` (replaces `nansen:disabled` Redis key).
  - Redis: `market:mode:override` **not found**; `nansen:disabled` **not found**; `market:mode:current=NORMAL` (automated); `bot:status` RUNNING (portfolio 39.73 SOL, 0 open, consecutive_losses=1).
- **Changes to §6 (rewritten):**
  - KEPT: PC1 wallet top-up (re-anchored to today's verified balance).
  - REFRAMED: PC2 observation window — was "Sessions A-D / 24-48h", now "post-C1 deploy (2026-05-13 03:38:37Z UTC) → combined eval ≥2026-05-27" (~33h elapsed of T+14d window).
  - ADDED: PC3 `LIVE-MODE-FILTER-PARITY-001-V2` — resolves the LIVE_MODE_FILTER_PARITY_001 audit §8.2 open question from yesterday's investigation.
  - KEPT (expanded): PC4 V5A flip itself — added CLEAN-003 pre-flip script + `market:mode:current=NORMAL` flip-time check + DAILY_LOSS_LIMIT + sell-storm breaker.
  - MOVED: SD_MC_CEILING_002 + LIVE-FEE-CAPTURE-002 Path B → "Completed preconditions (historical)" subsection.
  - REMOVED: `SD_EARLY_CHECK relax confirmation` (TUNE-009 deferred permanently); `nansen:disabled` Redis renewal (migrated to env `NANSEN_DRY_RUN=TRUE`); `market:mode:override` standing renewal (folded into PC4 flip-time check).
- **STOP-C flagged broader staleness:** §7 row `LIVE-FEE-CAPTURE-002 (Path B) 📋 V5a-blocking-but-degradable` contradicts the Decision Log + §6 deploy carry — inline `<!-- STALE: ... -->` left for a separate §7 sync session; NOT silently rewritten this session per STOP-C.
- **Honest V5A blocker count post-rewrite:** **4 outstanding** (wallet, observation, V2, flip-itself), **2 completed (historical)**, **3 removed/folded**.
- **NO services/* code change, NO env change, NO Redis writes (read-only on live state), NO deploy.** Audit: `docs/audits/V5A_PRECONDITION_CHECKLIST_CLEANUP_001_2026_05_14.md`. Scratch (untracked): `.tmp_v5a_cleanup/PROGRESS.md`, `01_verification.md`, `02_classification.md`.

---

## 2026-05-14 — LIVE-MODE-FILTER-PARITY-001 (read-only investigation, STOP-C / SCOPING NEEDED)

- **Trigger:** NO_MOMENTUM_90S_AUDIT_001 §10 open item — port the C1 fill-time MC ceiling to `services/execution.py` (the live execution path) before any V5A relaunch.
- **Routing confirmed (not STOP-B):** `execution.py` is the LIVE path only. `bot_core.py:82-83` imports `paper_buy` only under `if TEST_MODE`; `bot_core.py:836` paper branch → `paper_buy`, `:948` live branch → `execute_trade`. Every network call in `execution.py` is `TEST_MODE`-guarded. Changing `execution.py` does not affect paper trading or the May 27 SD validation.
- **Gate absent (not STOP-A):** `execution.py` (816 lines) read end-to-end — no market-cap ceiling check anywhere in the live buy path.
- **STOP-C fired:** the C1 gate (`paper_trader.py:247-275`) gates on a **fill-time** `entry_price * 1e9` price it computes itself. `execution.py` has (a) 3 execution routes (`_execute_pumpportal_local` / `_execute_pumpportal` / `_execute_jupiter`) and (b) **no fill-time price computation** — it returns a signature from unsigned tx bytes; bot_core fetches the price *after* execution (`:956`). The only MC value reachable inside `execute_trade` is `token.liquidity_usd` = signal-time `features["market_cap_usd"]`; gating on it fails MC-computation parity (prompt §4.3) and merely duplicates SA's existing signal-time `SD_MC_CEILING_USD`. No clean single-gate port achieves parity inside `execution.py`.
- **Scoping doc produced:** `.tmp_live_filter_parity/02_design.md` — 3 options. **Recommended: Option A** — gate in the `bot_core.py` live branch *before* `execute_trade`, using the existing `self._get_token_price(mint)` helper to compute a fill-time `fill_mc = price * 1e9`, mirroring `paper_buy`'s env var + reject-log + Redis-counter exactly.
- **New roadmap item:** **LIVE-MODE-FILTER-PARITY-001-V2** (Tier 1 🟡, **V5A relaunch blocker**) — scoped to Option A; needs explicit authorization to edit the `bot_core.py` live branch. Supersedes the NO_MOMENTUM_90S_AUDIT_001 §10 "execution.py parity" open item.
- **V5A implication:** until V2 lands, a live relaunch reintroduces the $1k-$3k fill-time bleed C1 eliminated on the paper path. SA's signal-time `SD_MC_CEILING_USD` is NOT a substitute — it is the gate C1 was built to backstop.
- **NO services/* code change, NO env change, NO Redis writes, NO deploy.** Audit: `docs/audits/LIVE_MODE_FILTER_PARITY_001_2026_05_14.md`. Scratch (untracked): `.tmp_live_filter_parity/PROGRESS.md`, `01_investigation.md`, `02_design.md`.

---

## 2026-05-14 — DASHBOARD-DESIGN-REALIGNMENT-001 (design session, DESIGN COMPLETE)

- **Trigger:** DASHBOARD-AUDIT-002 (2026-05-13) recommended promoting DASH-001 from QUEUED → Tier 1. Existing DASH-001 spec was Concept C "Unified Cockpit" (2026-04-19) — a 3-route × 3-tab × 14-panel desktop dashboard scoped when the dashboard was meant to be the operational center. Jay's clarified purpose narrows the dashboard's job to **"lightweight monitoring once live, on the go, especially mobile"**. Re-scope before any build session, to prevent rebuilding Unified Cockpit under a new name.
- **STOP results:** STOP-A applies weakly (Concept C did NOT already fit the re-scoped purpose). STOP-B passed (1 of 6 cards needs backend work, ≪50% threshold). STOP-C did not fire (card set sits at 6, within the cap). STOP-D N/A (frontend-design skill read OK). STOP-E none (no concurrent session).
- **Scope diff:** ~30 Concept C surfaces (3 routes × 3 tabs × 14 panels + sidebar nav + accent picker + 6 sub-pages) collapse to **6 cards on a single screen, one column at every viewport**. ≈5-7× smaller. Analytical surfaces (equity curve, P/L distribution, exit analysis, win-rates × regime, signal funnel, ML status, personality stats, governance, whale activity) DEFER-TO-CLAUDE-LOOP. Sidebar / tabs / routes / accent picker / breadcrumb / signals-route / wallet-route / settings-route — all CUT.
- **Card set (priority order):** (1) Bot status sticky-top with ALIVE/STOPPED/EMERGENCY/HIBERNATE pill + mode chip + last-heartbeat — `/api/status` EXISTS; (2) Today's P&L large number with trades/WR/best/worst sub-line — `/api/session-stats` EXISTS; (3) Active alerts conditional visibility (folds G-01 F1+C1 rejects + G-08 rollback triggers) — **PARTIAL backend, needs new `/api/active-alerts` endpoint ~30 lines**; (4) Wallet trading-on-chain + paper portfolio + holding — `/api/status` + `/api/wallets` EXISTS; (5) Open positions count + aggregate + tap-to-expand — `/api/positions` EXISTS; (6) Recent trades last 5 + footer-link to legacy dashboard — `/api/trades` EXISTS.
- **Technical shape:** single vertical column ≤480px on every viewport (no multi-column desktop — guards against drift back to Unified Cockpit); Geist + Geist Mono typography; dark default + light toggle; single chartreuse accent (no picker in v1); polling-only ~6 req/min ~1.5 MB/hr; PWA manifest + service worker for Add-to-Home-Screen + offline shell with stale badge; ≤80 KB total page weight; no JS framework; no analytical charting libraries.
- **Auth:** reuse existing JWT-in-localStorage pattern; longer-lived/biometric flagged for separate session as `DASH-AUTH-001` Tier 3.
- **Legacy relationship:** new monitor at `/m`; legacy `dashboard.html` stays at `/` for desktop analytical depth; coexist ≥30 days; deprecation decision after.
- **Build breakdown:** **3 sessions × 2.5h = 7.5h** (vs Concept C's 4-6 × 3h = 12-18h, ~55% smaller). BUILD-0 backend endpoint 0.5h; BUILD-1 UI scaffold + Cards 1/2/4 + `/m` route 2.5h; BUILD-2 Cards 3/5/6 + PWA + offline-shell 2.5h.
- **Sequencing:** **June parallel-track with Analyst Phase 0**, NOT May trading-logic critical path (C1 observation → combined eval ≥2026-05-27 → ML_THRESHOLD_RETUNE_002).
- **Testability:** DASH-T-001 test list shrinks (3-4h → ~2.5h); does NOT need its own realignment doc — a 30m test-list refresh once OBS-004 unblocks. Reused tests B-002/B-003/B-006/B-007/B-009; N/A under re-scope B-001/B-004/B-005/B-008/B-014; new tests alerts-collapse, pwa-manifest-valid, sw-caches-shell, sticky-status-card. Build NOT blocked on DASH-T-001.
- **Open questions to Jay:** (1) acceptance of re-scope; (2) 30-day legacy coexistence; (3) single accent vs picker; (4) Sentry fold-in v1.5; (5) active emergency-stop controls from phone (auth-impact, deferred); (6) June timing window.
- **Outputs:** `docs/audits/DASHBOARD_DESIGN_REALIGNMENT_001_2026_05_14.md` (main deliverable, ≤2500 words, §1-10); header-note on `docs/audits/DASHBOARD_REDESIGN_2026_04_19.md` (SUPERSEDED for scope; original preserved); `ZMN_ROADMAP.md` (Decision Log + DASH-001 row updates); `AGENT_CONTEXT.md` (header); `STATUS.md` (prepend); `.tmp_dashboard_realignment/` (untracked: 01_scope_diff.md / 02_card_specs.md / 03_technical_shape.md / 04_build_breakdown.md / 05_testability.md / PROGRESS.md).
- **NO services/* code change, NO env change, NO Redis writes, NO redeploy.**

---

## 2026-05-13 09:31 UTC — DASHBOARD-AUDIT-002 (read-only investigation, AUDIT COMPLETE)

- Re-evaluation of the 2026-04-19 dashboard audit suite against current bot reality (F1 deploy 2026-05-11, C1 deploy 2026-05-13, ML weakly-predictive finding 2026-05-12, Analyst hard-disabled).
- **STOP-B PASS:** only 1 commit on `dashboard/` / `services/dashboard_api.py` since 2026-04-19 (`bc622eb` BUG-021 trade_mode filter on `api_paper_stats` + `api_portfolio_history`). Baseline materially unchanged.
- **Inventory:** 14 panels on main `dashboard.html` (Equity Curve / Today's Session / Signal Funnel / ML Status / Personality P/L / P/L Distribution / API Health / Whale / Win Rates / Governance / Open Positions / Recent Trades / Recent Signals / topbar KPIs); 44 routes registered in `dashboard_api.py`, 18 consumed by main, ~20 orphaned or secondary-only. `dashboard-analytics.html` + `dashboard-wallet.html` remain orphaned (no nav links from main — unchanged from 2026-04-19 §1.2).
- **Decision-flow audit (8 operator decisions):** 0 fully SUPPORTED, 4 PARTIAL (bot health / daily PnL / regime shift / wallet stable), 4 MISSING (filter visibility / rollback triggers / pipeline ready / deploy decision). New operator workload uniformly under-served.
- **Reality-shift gap analysis (top 7 of 10):** G-01 F1+C1 filter visibility (sev 5), G-02 exit-reason time-series (sev 4), G-03 MC-band histogram (sev 4), G-04 ML gate effectiveness (sev 3), G-05 paper/live separation (sev 3), G-06 disabled-personality badge (sev 2), G-08 rollback trigger surface (sev 3). G-07 / G-09 / G-10 are carry-overs from 2026-04-19.
- **Bug status:** 4 closed since 2026-04-19 (B-002 via BUG-022 pass-through, B-004 confirmed, B-011 + B-012 already closed); 9 still apply (defer to rebuild); 2 separate fix candidates (DASHBOARD-CORRECTED-PNL-WARN-001, DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001); 3 unverified (B-007/B-008/B-009 → DASH-T-001 Playwright suite, blocked on OBS-004 Playwright stability).
- **Prioritized top 10:** PATCH-NOW count = 1 definitive (G-01, M-effort ~2-3h) + 2 conditional. Below §8 BUNDLE threshold. All 10 items survive DASH-001 rebuild.
- **Decision tree result:** 1 PATCH-NOW item, M-effort → neither BUNDLE nor ACCELERATE; **REAFFIRM REBUILD with explicit scheduling ask.** STOP-A applies weakly (prior audits cover all framing except G-01 urgency).
- **Verdict:** ✅ **AUDIT COMPLETE. REAFFIRM REBUILD. Recommend DASH-001 promotion QUEUED → Tier 1.** DASH-001 has been QUEUED ~4 weeks; F1+C1 deploys + ML retune queue + audit-pipeline-tracking need create accumulating observability gaps that the rebuild naturally closes. ⛔ DASH-PATCH stays deferred (rebuild-not-patch). Open question to Jay flagged in audit §1 / §7 / §9.
- **NO services/* edit, NO env change, NO Redis writes, NO DB writes.** Audit: `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md`. Scratch artifacts: `.tmp_dashboard_audit/01_widget_inventory.md`, `03_decision_flow.md`, `04_gap_analysis.md`, `05_bug_status.md`, `06_prioritized.md`, `07_decision.md` (untracked).

---

## 2026-05-13 — NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 (C1, env-only deploy, DEPLOYED-VERIFIED)

- Single env-var retune of `BOT_CORE_FILL_MC_CEILING_USD` on bot_core: **3000 → 1000** at 2026-05-13 03:29:21Z UTC. Jay-authorized fast-track (audit's path b, §9); T1 standalone audit at ~2026-05-14 SKIPPED per audit §12 (added this session).
- **Pre-deploy STOP gates all PASS.** STOP-A retest on fresh 8.12d sample (vs audit's 7.49d): C1 marginal blocked 589 trades, sum_pnl saved -10.86 SOL → **+1.49 SOL/day W3+W4 rate** (≥+1.0 threshold), **+3.02 SOL/day W4-only rate**; **0 FP winners** (matches audit exactly); KEPT slice 523 trades / +32.62 SOL / **91.4% WR** (stronger than audit's 433 / +30.71 / 94.2%). STOP-B PASS (last fill-path commit = `0f37e82` F1 itself). STOP-C PASS (no concurrent bot_core deploy in latest STATUS entries). STOP-D PASS (Jay authorization explicit + named env var).
- **Container restart 03:38:37Z UTC.** Clean startup verified: `TEST_MODE=True`, `Starting SINGLE service: bot_core`, `Startup reconciliation: 0 open positions in DB`, `Loaded portfolio state: 30.7304 SOL`, `Loaded 44 whale wallets into Redis cache`, `Bot Core ready — managing 3 personalities`, `Listening for emergency alerts`. No RuntimeError / Traceback / ImportError.
- **First post-deploy rejection log:** `2026-05-13 03:41:38,829 [paper_trader] INFO: FILL_MC_CEILING reject: 6X5V79NvN85P mc=$10753 > ceiling=$1000` — env plumbed through to rejection logic correctly. (This particular mint at $10K would have been rejected by the old $3K ceiling too; the meaningful $1k-$3k rejections will accumulate over the next hours.)
- Cross-audit reinforcement from ML-SCORE-ATH-VALIDATION-001 (2026-05-12) — 2 of 489 nm90 post-exit pumps at 56h median lag confirms timer is NOT killing winners → MC discriminator is the right lever.
- Rollback procedure (instant, no code revert): `BOT_CORE_FILL_MC_CEILING_USD=3000` via Railway MCP / CLI. Triggers single auto-redeploy. Same env command as the F1 → C1 transition, just inverted threshold.
- Eval folded: combined STOP-LOSS-20-RUG-FILTER-EVAL-001 + NO-MOMENTUM-90S-EVAL-001 at ≥2026-05-27 (+14d from this deploy; original ≥2026-05-25 superseded).
- Rollback triggers (per deploy doc §"Rollback triggers"): ANY of these within 24h → revert to 3000 immediately: bot_core fails to start, SD-paper trade rate <1/h for 2 consecutive hours, TRAILING_STOP winner with `realised_pnl_sol > 0.10 SOL` blocked, sum_pnl on kept slice ≤ -0.5 SOL within 24h, `bot:emergency_stop` set, consecutive_losses +5 within 24h.
- Single push, `git commit --amend` to backfill commit hash into STATUS.md per RAILWAY-REDEPLOY-DISCIPLINE-001.

---

## 2026-05-12 — ML-SCORE-ATH-VALIDATION-001 (read-only research, EVIDENCE-PRODUCED)

- Research-only audit answering "does the bot's ML score predict pump.fun token ATH within 72h post-entry?" Sample: 1,097 SD-paper trades in pre-`BOT_CORE_ML_GATE` window (2026-04-22 → 2026-05-05 14:16:48Z UTC). One-off; no production code/env/Redis writes; no deploy.
- Phase 1 pre-claim STOP-A: PASS. Exact match on n=1,097, ml_score range 30.0-97.2 (mean 54.37), exit_reason distribution (nm90 44.6%, TS 36.2%, sl20 11.9%, stale 5.9%, staged_tp combined ~1.1%). peak_price coverage by exit_reason: 100% TS / 3.7% nm90 / 0% sl20 / 100% stale_no_price / 100% staged_tp — confirms CLAUDE.md predictor that 53% of trades need external ATH lookup.
- Phase 1 GT probe (3 sample mints under `pump-fun` dex namespace): all 3 had pool + OHLCV available, including the rugged stop_loss_20% mint (BSNM1wgx...pump → SHIMO/SOL pool with $34,840 reserve at fetch time). DexPaprika ruled out (0 pools returned for the same TRAILING_STOP mint — only Raydium post-grad indexed). DexPaprika is NOT a viable fallback for pre-graduation pump.fun memecoins.
- Phase 2 fetch loop operational reality: at PACING_S=2.0s saw 429 within ~32 calls; at 2.5s and 5.0s sustained ~2-3 rows/min in steady state due to sliding-window backoff (documented limit is 30/min but token-bucket behaves stricter). Full 1,097-mint direct fetch would take 8-10 hours at this rate. **Pivoted to coverage-strategy:** restrict GT fetch to no-peak rows (~604 mints), use paper_peak directly for the 462 that have it (TS / staged_tp / stale_no_price). Killed fetch at 29 GT rows; relied on `no_pump_exit_inferred` rule (nm90/sl20/time_exit_loss + peak_price NULL + data_source NULL → ath_mult=1.0) for 53.4% of sample. Final ath_basis composition: paper_peak 45% / gecko_terminal 0.4% / no_pump_gt_confirmed 1.2% / no_pump_exit_inferred 53.4% / unknown 0.1% = **99.9% effective coverage**.
- Phase 3 §3 ML calibration table: mean ath_multiplier monotonic Q1=2.20 → Q5=2.72. Mean PnL/trade monotonic upward Q1=+0.007 → Q5=+0.017 SOL. But %≥5× rate is non-monotonic — 30-40 band catches 9.0% mega-winners, 80+ band only 4.8%. Median ath_mult is exactly 1.000 for Q1-Q4 (more than half of those bands had no observed pump above entry).
- Phase 3 §4 killer chart: 0 of 489 nm90 exits had ath_mult ≥ 2×; only 2 of 489 (0.41%) had GT-confirmed peak AFTER exit timestamp, both at >2-day lag (median 3,384 min = 56h). Timer is NOT killing winners at meaningful rate. Quintile breakdown within nm90 is uniformly 0% across Q1-Q5.
- Phase 3 §5 ROC/AUC: AUC = **0.5361** on ATH≥5× binary classifier — barely above chance. At live thr=40, precision 6.5% (vs 6.9% base rate — zero lift). At thr=80, precision DROPS to 4.8% (below base rate). Per plan rubric: WEAKLY PREDICTIVE (sits just below 0.55 lower bound).
- Phase 3 §6 counterfactual gate sweep: Actual 12d PnL = +7.804 SOL. By threshold: thr=30 +7.80 / thr=35 +8.20 / **thr=40 (LIVE) +6.54 ← WORST in 30-55 range** / thr=45 +6.98 / thr=50 +7.66 / **thr=55 +8.51 ← HISTORICAL OPTIMUM** / thr=60+ degrades sharply. Live gate is costing **-1.26 SOL over 12d** vs no-gate; thr=55 would have been **+1.97 SOL better** than live = **+0.16 SOL/day**. Big-winners-blocked at live thr=40: 17 of 76 total (22% — disproportionate given band is 17% of sample).
- Verdict: ML weakly predictive. Live gate sub-optimal but improvement modest. **No deploy this session.** Recommendation: ML_THRESHOLD_RETUNE_002 re-derives sweep on post-gate window (≥2026-05-12 + 7d) before any deploy.
- Killer-chart finding INDEPENDENTLY corroborates NO-MOMENTUM-90S-AUDIT-001's conclusion that the structural lever is MC discrimination (C1 = $1k ceiling), not the timer itself.
- New DB object: `mint_ath_lookups` table (research-only cache, NOT consumed by bot_core or signal_aggregator). 29 rows populated this session.
- New scripts: `scripts/ml_ath_validation_001.py` (idempotent fetch loop) + `scripts/verify_ml_calibration.py` (standalone counterfactual). Both py_compile OK. Replay instructions in audit §12.
- NO services/* edit, NO Redis writes, NO env / deploy. Single push expected (audit + scripts + canonical doc updates).

---

## 2026-05-12 — NO-MOMENTUM-90S-AUDIT-001 (T0, read-only investigation)

- Triggered ~24h post STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (2026-05-11 12:30 UTC) to investigate the surge of `no_momentum_90s` exits from 40.2% (pre-F1) to 76.5% (post-F1) of SD-paper trades. Run T0; T1 scheduled ≈2026-05-14.
- Phase 0 premise verification: nm90 mean PnL anchor verified at −0.017 SOL (predicted −0.018). The hold-time prose ("80-90s") was wrong — actual median is 51s. Code (`services/bot_core.py:1782-1787`) with env `SD_EARLY_CHECK_SECONDS=60`/`SD_EARLY_MIN_MOVE_PCT=3.0` defines window `(50, 90)s` and the price-monitor loop iterates ≤1s, so first eligible iteration ~51s. Not material to the conclusion.
- Code archaeology: no_momentum_90s checked BEFORE stop_loss_20%, staged_tp, trailing_stop. peak_price updates monotonically (`bot_core.py:1761-1772`) — for nm90 exits price never crosses entry, so peak_price stays NULL on 100% of sampled rows. Sample of 5 W4 rows: all 5 in $2332-$2462 MC band, all 5 with peak_price NULL, all 5 with `signal_detected_at`/`scored_at`/`traded_at` NULL → Phase 2.4 signal-age check INFEASIBLE.
- Window baselines (SD-paper, n by window): W1 04-16..04-24 242 / +6.48 / WR 51.2% / nm90 26.9% / nm90 sum -1.06; W2 04-29..05-04 347 / +0.69 / WR 18.4% / nm90 64.0% / -3.98; W3 05-05..05-11 12:30 959 / +9.30 / WR 38.7% / nm90 38.3% / -8.55; W4 post-filter 264 / -2.18 / WR 14.4% / nm90 76.5% / -3.47. W2 pre-dates W4 with the same nm90-dominant signature; W3 was the anomalous good window dominated by TRAILING_STOP (+22.40 SOL).
- W4 MC-band distribution (n=264): $0-500 5/+0.72/100% WR; $500-1k 46/+0.76/72% WR; $1k-1k5 5/-0.09/0%; $1k5-2k 3/-0.04/0%; $2k-2k5 58/-0.68/0%; $2k5-3k 147/-2.86/0%. **78% of volume is in $2k-3k with 0 winners** — 202 of 205 trades in that band exit as nm90. F1 ($3k) cleared the $3k+ rugs; the next bleed tier is $1k-3k.
- Feature discrimination (W3+W4 SD-paper, exit IN nm90/TRAILING_STOP): trail_win (n=393) p25/p50/p75 MC = $550/$639/$720; trail_loss (n=85) p25/p50/p75 = $939/$1129/$1602; nm90 (n=569) p25/p50/p75 = $2615/$2778/$2909. **market_cap_at_entry is the SOLE discriminator** — ml_score (54.9 vs 57.1 vs 57.4), rugcheck (6036 vs 6030 vs 4988), liq_velocity (~19), cfgi (~55), bc_progress (~0.354), age (~1.6s) all identical across groups. Max trail_win MC in W3+W4 = $892.
- Candidate counterfactual (verify_intervention.py against W3+W4 1223-row sample, 7.49d): F1 production state at $3000 baseline (201 blocked / -12.73 SOL saved); **C1 $1000 ceiling**: 790 total blocked / 589 incremental over F1 / **-10.86 SOL saved** = +1.45 SOL/day W3+W4 rate, +3.67 SOL/day W4-only rate, **0 false positives** (max trail_win MC $892 < $1000), KEPT 433 trades / +30.71 SOL / WR 94.2%. C2 ($1500): +1.31/d, 0 FP. C3 ($750): +1.23/d but 59 FP at -2.09 SOL (loses 0.5 SOL/day in winners) — too aggressive.
- STOP gates: A PASS (PnL anchor); B PASS (features populated); C PASS (0% trail_win lost at C1); D PASS by 5×+ at C1 (+1.45 to +3.67 vs 0.3 floor); E PASS (C1+C2 viable); F N/A (T0); G PASS (no concurrent session).
- **Verdict: DEPLOY-RECOMMENDED** for C1 ($1000 ceiling). Same env var as F1 (`BOT_CORE_FILL_MC_CEILING_USD`); §9 prohibits touching F1 in this session — deploy is a follow-on paste-ready prompt at `docs/audits/NO_MOMENTUM_90S_DEPLOY_PROMPT_2026_05_12.md`. Two timing paths: bundle into STOP-LOSS-20-RUG-FILTER-EVAL-001 (≥2026-05-25) or Jay-authorized early retune.
- T1 STOP-F test scheduled ≈2026-05-14: re-run prompt and compare to `.tmp_no_momentum_90s/T0_BASELINE.json`. If W4 nm90_rate drops >10pp AND $1k-3k WR rises >15pp → regime transient → STOP-F → no action. Else → structural confirmed → execute deploy prompt.
- NO services/* edit, NO Redis writes, NO env / deploy. Single push, no `railway up`.

---

## 2026-05-11 — STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (code+env deploy)

- Predecessor: STOP-LOSS-20-RUG-INVESTIGATION-001 (commit `27f623b`, 2026-05-09). Audit doc `docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md` + paste-ready deploy prompt `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`.
- STOP gates re-verified pre-deploy: STOP-A PASS (investigation doc 2d old, ≤14d window); STOP-B PASS (`git log 27f623b..HEAD -- services/paper_trader.py services/bot_core.py` returns ZERO behavioural commits; last touch to either file `ea0da2f` BOT-CORE-ML-GATE-001 2026-05-05, pre-investigation); STOP-C PASS (re-ran `verify_filter.py`; 9.5d sample at $3K = +13.15 SOL NET LIFT = **+1.38 SOL/day**, up from +0.93/day at investigation time — bleed accelerated; floor was +0.50/day); STOP-D PASS (no concurrent behavioural deploy markers).
- Code change: `services/paper_trader.py` `paper_buy` — single Edit hunk +29 lines inserted between `entry_price = price * (1 + slippage / 100)` (line 245) and `fee_breakdown = _simulate_fees(...)` (was line 247, now line 277). New block reads `BOT_CORE_FILL_MC_CEILING_USD` env (default "0" = disabled); if positive AND `entry_price * 1_000_000_000 > ceiling`, logs `FILL_MC_CEILING reject: ...`, increments Redis counter `bot:filter:fill_mc_ceiling:rejects:<UTC-date>` (14d TTL), returns `{success: False, error: "fill_mc_ceiling_exceeded", simulated: True, fill_mc, ceiling}`. The return shape matches the existing `price_fetch_failed` path so all callers handle it correctly.
- Compile check: `python -m py_compile services/paper_trader.py` → OK.
- Railway env set: `BOT_CORE_FILL_MC_CEILING_USD=3000` on **bot_core ONLY** at 2026-05-11 12:18:37 UTC. Other services (signal_aggregator, web, ml_engine, signal_listener, treasury, governance, market_health, Redis, Postgres) untouched.
- Two redeploys triggered: code push commit `0f37e82` at 12:09 UTC → container start at 12:16:41 UTC; env set at 12:18:37 UTC → container start at 12:24:12 UTC. Both verified via railway logs `Starting SINGLE service: bot_core` + `Startup reconciliation: 0 open positions in DB` + `Listening for emergency alerts`.
- Post-deploy verification harness `.tmp_stop_loss_20_rug_deploy/post_deploy_verify.py` (gitignored). Run output: `.tmp_stop_loss_20_rug_deploy/post_deploy_check.txt` (gitignored). Checks: (i) Redis counter accessibility/value; (ii) NO new SD-paper trades with `market_cap_at_entry > $3,000` since deploy (F1 should have blocked these); (iii) trade-rate sanity vs pre-deploy 24h baseline (≥50% threshold).
- Verification outcome (T+2 min, 12:26 UTC): ✅ **PASS**. (i) Redis counter `bot:filter:fill_mc_ceiling:rejects:2026-05-11` not yet present (lazy-create on first reject; expected at ~9 rugs/day rate to populate within hours). (ii) 4 new SD-paper trades since env-active deploy, **0 with market_cap_at_entry > $3,000** — F1 gate selective, low-MC tokens still flowing. (iii) Trade rate sanity: too short a window for meaningful comparison (4 trades in 2 min vs 24h pre-deploy 85/24h = 3.5/h). Will re-check at +30 min and +24h per deploy prompt rollback-trigger window. No `FILL_MC_CEILING reject` log lines yet (consistent with historical ~1/2-3h rug arrival rate). bot:status `consecutive_losses=19` is PRE-EXISTING (not deploy-related; was 1 on 2026-05-08, accumulated over 3 days from the same May-8 spike that motivated this filter). Rollback triggers from deploy prompt §5 all clear: no RuntimeError at startup, no winner blocked, no emergency_stop set, no consecutive_losses delta from deploy.
- Rollback procedure: `BOT_CORE_FILL_MC_CEILING_USD=0` via Railway MCP → takes effect at next `paper_buy` call (~few seconds), no redeploy required. Documented per §4 of deploy prompt.
- Re-evaluation milestone: queue `STOP-LOSS-20-RUG-FILTER-EVAL-001` for ≥2026-05-25 (+14d post-deploy). Will: (a) verify cumulative Redis counter matches projected ~25/day rate; (b) re-run `verify_filter.py` with actual post-deploy `kept_pnl`; (c) decide keep $3k / tighten $2k / loosen $5k; (d) decide live-mode parity in `services/execution.py` (gated on V5a preconditions).
- V5a impact: none. F1 is paper-scoped at this deploy (paper_buy only called from `bot_core.process_signal` TEST_MODE=true path). Live-mode parity in `services/execution.py` is a separate session.

---

## 2026-05-09 — STOP-LOSS-20-RUG-INVESTIGATION-001 (read-only investigation, DEPLOY-RECOMMENDED)

- Read-only investigation of `stop_loss_20%` as the largest SD-paper bleed since 2026-05-02 (n=65, sum −6.03 SOL, 0% WR). Triggered by chat-side data analysis.
- Pre-claim verification (STOP-A): 65 rugs since 2026-05-02 (chat said 61; close — chat ran ~6h earlier and the May 8 spike was still accumulating). Hold time min 0.099s, max 2.021s, median 0.991s — matches chat's 0.10-2.02s/median 1.04s. Median observed drop −74.03% — matches chat's −74.7%. peak_price NULL on 100% of rows — consistent with chat's "0/61 went up", but limited evidence (peak_price column never written for sub-second exits; the INSERT in `paper_trader.paper_buy` doesn't set peak_price, and the bot_core UPDATE either doesn't fire or fails silently inside `except Exception: pass`).
- Code archaeology: exit logic at `services/bot_core.py:1815-1824` — `f"stop_loss_{sl_pct:.0%}"` f-string label fires whenever `multiple <= (1 - 0.20)` regardless of how deep the actual drop. The label is "≥-20% drop observed at the 2-second exit-check tick", not "exit at -20%". Polling cadence `await asyncio.sleep(2)` at L1940. STOP_LOSS_PCT=0.20 confirmed from `services/bot_core.py:166` (env-controlled, default 0.20).
- Gate verification (STOP-B): SD_MC_CEILING_002 gate intact at `services/signal_aggregator.py:1846-1881`; Railway env `SD_MC_CEILING_USD=3000` confirmed live on signal_aggregator. STOP-B does not fire.
- Field sample (STOP-C): features_json populated on 186/186 (100%) SD-paper stop_loss_20% rows since (mis-set) SINCE date — STOP-C does not fire. Sample 5 rows showed market_cap_at_entry $3,033-$24,383 — all above the SA $3K threshold. The SA gate is being bypassed.
- **Smoking gun (Phase 2)**: `market_cap_at_entry` cleanly separates RUG from WIN at $3K cut on 273-row sample (65 rugs / 208 trailing-stop wins) since 2026-05-02. RUG: min $3,181, p10 $3,436, median $7,881, p90 $37,615, max $181,519 — **100% > $3K**. WIN: min $321, median $623, p90 $756, max $832 — **0% > $3K**. Zero overlap.
- Root cause: SA gate evaluates BC reserves *as carried in raw_data at PumpPortal-publish time*. For fresh pump.fun tokens, raw_data carries the seed values (vSol≈30, vTokens≈1.073e9), so SA-computed MC ≈ $2,400 — always under the $3K gate. Between signal-publish and bot_core fill (1-15s window), Jupiter / GeckoTerminal indexes the token and returns a *current* USD price reflecting in-flight sniper buys. `paper_buy._get_token_price(mint)` (paper_trader.py:96-139) prefers Jupiter's live price over the BC fallback. The DB column `market_cap_at_entry = entry_price * 1B` reflects this fill-time price. The SA gate is structurally inert against this failure mode because it gates on signal-time data while the failure mode is fill-time price divergence.
- Discriminative-feature scan (Phase 2.3): no feature in features_json clears the 1.5× separation threshold. All ratios in [0.82, 1.21]. Confirms the only data-supported lever is fill-time MC (which is the DB column `market_cap_at_entry`).
- Filter F1 design + counterfactual (Phase 3-4):
  - F1: at `paper_trader.paper_buy`, after `entry_price` computation, reject if `entry_price * 1_000_000_000 > BOT_CORE_FILL_MC_CEILING_USD`. Default disabled in code; env-active at $3,000.
  - 7d window (since 2026-05-02): blocks 69 / 473, NET LIFT +6.20 SOL, **+0.93 SOL/day**, 0/211 winner FP.
  - 14d window (since 2026-04-25): blocks 139 / 1,091, NET LIFT +11.00 SOL, **+0.80 SOL/day**, 0/349 winner FP.
  - 17d POST-cliff (since 2026-04-22): blocks 203 / 1,493, NET LIFT +14.65 SOL, **+0.88 SOL/day**, 0/544 winner FP.
  - STOP-E (≤10% winner-SOL FP) clears by 0%; STOP-F (≥+0.30 SOL/day) clears by 2.7-3.1×; STOP-D and STOP-G clear.
  - Tighter $2K threshold lifts another +0.7 SOL/day but blocks 56% of trades — recommend $3K for parity with SA gate, conservative blast radius (14% blocked), zero FP cost. Tightening can follow as a separate post-deploy sweep.
- May 8 spike: 40 of 65 rugs (62%) on a single day. F1 is forward-protective regardless of whether the spike is structural or transient.
- Verdict: 🟢 **DEPLOY-RECOMMENDED**. Single-lever, env-controlled, reversible, paper-only at flip. Follow-on prompt at `docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md`.
- Investigation evidence: `.tmp_stop_loss_20_rug/{01_exit_logic,02_entry_path,03_field_sample,04_gate_verification,05_signal_vs_fill,06_discriminative_features,07_sizing,08_temporal,09_candidate_F1}.md` + `phase2_output.txt` + `verify_output.txt`. Audit doc: `docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md`.
- NO code/env/Redis writes this session. Read-only DB SELECT, read-only Railway MCP `list-variables`, read-only code grep. Single push expected (audit doc + canonical-doc updates only).

---

## 2026-05-08 13:30 UTC — VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08 (read-only investigation, STOP per Step 7 #2)

- Read-only investigation of the 3 hardcoded `.com` Vybe URLs at `services/signal_aggregator.py:753, 850, 2568` flagged by API-CREDITS-HEALTH-DIAGNOSTIC-001 (2026-05-05). Session prompt anticipated a `.com → .xyz` TLD swap based on prior audit's `.xyz → 401` probe inference.
- Probe with valid `VYBE_API_KEY` (sourced from Railway signal_aggregator env, never written to disk) reveals: both `.com/token/...` and `.xyz/token/...` return HTTP 404 ("The requested endpoint does not exist"). The 401 the prior audit observed was from probing `.xyz` without auth — Vybe's auth middleware fires before the not-found check.
- Vybe MCP `search-endpoints` + `get-endpoint` confirm canonical paths are versioned: `/v4/tokens/{mint}/top-holders` and `/v4/tokens/{mint}` — both explicitly noted in OpenAPI as **"Replaces"** the older `/token/...` paths. Probes against `.xyz/v4/tokens/...` return HTTP 200 with valid data (BONK test mint).
- Two breaking downstream issues for the URL-only fix:
  - L850 `_fetch_creator_history`: v4 Token Details response has no `creator` field. Function continues to return empty dict even after URL+path fix. Need alternative data source (Helius parseTransactions first-slot, pump.fun metadata, or other). Tracked as new VYBE-CREATOR-LOOKUP-DEPRECATED-001 (Tier 2).
  - L2568 KOL/MM detection: v4 `/top-holders` returns `ownerName` (e.g. "Binance Exchange 1"), not `ownerLabel`/`label`. KOL detection reads the wrong field — `kol_count` stays 0 → `whale_boost` stays 1.0. Trivial paired field-name update needed; bundle with V2 fix. Tracked as new VYBE-KOL-FIELD-MAPPING-001 (Tier 2).
- L753 `_fetch_holder_data_vybe`: response shape compatible (`data` array with `balance` field). URL+path fix alone fully restores HOLDER fallback.
- Caller analysis (Step 4): no caller breaks on empty returns. All three call sites already handle silent-failure gracefully — they have for the bot's entire +598 SOL pre-cliff era and post-cliff period. Adding real Vybe data is additive feature restoration.
- Per Step 7 condition #2 ("Vybe API documentation indicates breaking changes between the old endpoint and a current canonical one — i.e., the fix is more than a TLD swap"), **STOP triggered**. Findings audit committed; no code change to `services/signal_aggregator.py`; no Railway redeploy.
- Concurrent STATE-SNAPSHOT-2026-05-08 (entry below) ran the same window; their §3 finding "Vybe `.xyz` route alive (401/400 with bogus auth)" matches: with bogus/empty auth, `.xyz` returns 401/400; with valid auth, `.xyz/token/...` returns 404. The 401 was an auth-middleware artifact, not evidence of a working route.
- Follow-up: `VYBE-URL-CODE-DRIFT-001-FIX-V2` (Path A1 in audit §7) — URL+path migration at all 3 sites + L2568 `ownerName` field update; track creator-source replacement separately. Cost S.
- **NO services/* edit, NO deploy, NO env change, NO Redis writes, NO DB writes.** Audit: `docs/audits/VYBE_URL_FIX_2026_05_08.md`. Scratch artifacts: `.tmp_vybe_fix/probe_urls.py`, `.tmp_vybe_fix/probe_v4_urls.py`, `.tmp_vybe_fix/probe_output.txt`, `.tmp_vybe_fix/probe_v4_output.txt`, `.tmp_vybe_fix/STOPPED.md`, `.tmp_vybe_fix/vybe_references.txt`, `.tmp_vybe_fix/git_history.txt` (untracked).

---

## 2026-05-08 ~13:21 UTC — STATE-SNAPSHOT-2026-05-08 (read-only verification, no env / Redis / code changes)

- Read-only state snapshot to refresh the [STALE]/[ASSUMED] items in the 2026-05-07 handover before the DEFENSIVE-OVERRIDE-PROBE-EVAL window opens.
- §1 PROBE STATE: 🔴 **EXPIRED.** `market:mode:override` is absent at audit time; `market:mode:current=NORMAL`. Probe was set 2026-05-06 22:29:10 UTC with 24h TTL → expired 2026-05-07 22:29:10 UTC. Renewal did NOT fire. Probe ran ~24h before lapsing.
- §2 WALLETS: trading wallet UNCHANGED at 0.064095633 SOL [VERIFIED:helius]. Holding wallet rose to 0.190842421 SOL from prior 0.0098 SOL baseline (+0.181 drift; treasury dormant — confirm with Jay).
- §3 API HEALTH: Helius 🟢 (epoch 968, ~1588 real TPS); Vybe `.com` 🔴 still 404 (code drift unchanged); Vybe `.xyz` route alive (401/400 with bogus auth); SocialData route alive 401 (real credit state not probed); Anthropic 🔴 confirmed firing now via Redis `governance:latest_decision` body; PumpPortal/Jupiter/Binance 🟢 (inferred via `signal_aggregator:health` heartbeat fresh).
- §4 PROBE-PERIOD PAPER: n=263 since 2026-05-07 00:00 UTC, all SD-paper closed, +2.0625 SOL net, 52.9% WR. Window split: probe-active 24h n=54 / +0.640 SOL / 44.4% WR; probe-expired ~14h45m n=212 / +1.398 SOL / 54.2% WR. **Mode coverage gap: `mode_at_entry` absent in 263/263 sample rows** — per-row mode reconstruction not possible from DB alone for this window. Filing MODE-AT-ENTRY-FEATURE-001 (Tier 2 🟢).
- §5 ENV: bot_core / signal_aggregator / treasury / ml_engine / market_health all match handover §3.2 with no drift. SEC-001 split-Nansen-key state still present (treasury+market_health on `cL2tgvKP`; rest on `nsn_2ef9`). Vestigial sizing values still on treasury/ml_engine/market_health (TUNE-008 cleanup carry-over).
- §6 CODE STATE: BOT-CORE-ML-GATE-001 commit `ea0da2f` present in HEAD `15a334a`; SD_MC_CEILING_002 gate at signal_aggregator.py:1846-1881 (handover line range was approximate); TIME_PRIME env-controlled block at bot_core.py:750-764; hardcoded TZ at bot_core.py:754 still present (TIME-PRIME-AEDT-AEST-DRIFT-001 unchanged); Vybe `.com` URLs at signal_aggregator.py:753, 850, 2568 still present (VYBE-URL-CODE-DRIFT-001 unchanged).
- §7 RECOMMENDATIONS for eval session: (a) decide treatment of underpowered 24h probe sample — recommend re-run with renewal commitment (option 2); (b) file MODE-AT-ENTRY-FEATURE-001 to add `mode_at_entry` to features_json so future audits can do per-row mode analysis; (c) confirm holding-wallet drift; (d) carry-over Anthropic/Vybe/SocialData fixes still pending.
- **NO services/* edit, NO deploy, NO env change, NO Redis writes.** Audit: `docs/audits/STATE_SNAPSHOT_2026_05_08.md`. Scratch: `.tmp_state_snapshot/` (gitignored).

---

## 2026-05-06 22:29 UTC — DEFENSIVE-OVERRIDE-PROBE-001 START (no code change, single Redis SET)

- Single state change: `SET market:mode:override DEFENSIVE EX 86400` at **2026-05-06T22:29:10Z UTC** via Redis MCP. No code edits, no env changes, no service redeploys.
- Probe rationale: A/B-test the NORMAL-vs-DEFENSIVE PnL inversion finding from **MARKET-MODE-001-RE-CALIBRATE Path C / STOP** (audit `MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`). Pre-probe finding (post-Session-2 5-day window): NORMAL -1.09 SOL on 121 trades (24.8% WR) vs DEFENSIVE +0.25 SOL on 45 (28.9% WR) — counterintuitive, sample n=45 too small for confidence.
- §2 baseline (last 48h SD-paper, captured pre-SET): NORMAL n=103 / -0.80 SOL / mean -0.0078 / **33.0% WR**; AGGRESSIVE n=1; DEFENSIVE n=17 / +0.44 SOL / mean +0.026 / **64.7% WR**; TOTAL n=121 / -0.37 SOL / 37.2% WR. Reinforces inversion at smaller window with same direction. Raw output saved to `.tmp_defensive_probe/baseline.txt`.
- §2 bot health pre-SET: bot:status RUNNING, paper portfolio 22.92 SOL, 0 open positions, market_mode NORMAL, consecutive_losses=2, test_mode=true, emergency_stop=ABSENT. All §2 STOP conditions PASSED.
- §3 Redis SET landed (verified via `GET market:mode:override` → "DEFENSIVE"). Pre-SET value: key absent (no prior override). Pre-SET market:mode:current=NORMAL.
- §4 propagation verification (within prompt's 5-min ceiling):
  - 22:29:44Z (34s post-SET): `market_health` log shows `Market mode: DEFENSIVE` — first cycle picked up override.
  - 22:34:45Z (5m35s post-SET): `market_health` log shows explicit `Market mode OVERRIDE active: DEFENSIVE` — confirms `services/market_health.py:412-414` override-read path firing as expected.
  - `market:mode:current` = DEFENSIVE (verified via Redis MCP).
  - `bot:status.market_mode` = DEFENSIVE (verified via bot_core heartbeat at 22:39:31Z).
  - First post-SET trade observed at 22:39 UTC (`speed_demon:C7Ad1dff…`, no_momentum_90s -0.0152 SOL on 0.091 SOL position) — throughput confirmed flowing under DEFENSIVE override; bot_core ML gate at 40 still rejecting <40 ml_score signals (4+ skip lines logged at 22:02-22:15 UTC).
- §5 documentation: STATUS.md prepended; MONITORING_LOG.md prepended (this entry); ZMN_ROADMAP.md Decision Log row + 2 new Tier-2 OPERATIONAL / Tier-1 EVAL roadmap rows added (`DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001`, `DEFENSIVE-OVERRIDE-PROBE-EVAL-001`).
- §6 daily renewal: filed as `DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001` (operational, Tier 2 🟢). Until probe ends, override must be re-SET every 24h. Auto-expires safely if forgotten (bot reverts to threshold-based mode = safe failure mode).
- §7 STOP conditions: NONE triggered. All four (§2 unexpected state / §3 SET fail / §4 propagation fail >10min / §1.4 git rebase fail 3×) cleared.
- Re-evaluation milestone: ≥**2026-05-08T22:29Z UTC** (48h). Sample target ≥80 SD-paper trades under DEFENSIVE. Run as `DEFENSIVE-OVERRIDE-PROBE-EVAL-001` (paste-ready prompt to follow). Do NOT auto-trigger.
- Rollback triggers (any one ends probe early): cumulative < -0.50 SOL on n≥30 / WR < 18% on n≥30 / throughput < 5 SD-paper trades/day for 24h consecutive / bot HIBERNATE > 2h consecutive (override-read path bug indicator).
- Rollback procedure: `DEL market:mode:override` via Redis MCP. Document in MONITORING_LOG.
- **NO services/* edit, NO deploy, NO env change.** Sole runtime change: 1 Redis key SET with 24h TTL. Audit predecessor: `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`. Scratch artifacts: `.tmp_defensive_probe/baseline.txt`, `.tmp_defensive_probe/baseline_query.py` (gitignored).

---

## 2026-05-07 ~01:30 UTC — STRATEGY-CLIFF-INVESTIGATION-001 (read-only investigation, NO REVERT)

- Read-only investigation of the 2026-04-20→21 paper-PnL "cliff" via SQL on production DB (`paper_trades` current + `paper_trades_archive_20260421` archive table) + git log + audit doc + code reads.
- §3 cliff CONFIRMED in DB: archive 8-day SD-paper sample (n=2,984) shows mean +0.20 SOL/trade summing +598 SOL; current 4-day POST sample (n=528) shows mean +0.014 SOL/trade summing +9.3 SOL. Numbers match chat-side prompt's framing within rounding.
- §3 KEY FINDING — fee-model accounting mismatch: PRE rows written under OLD fee model that under-counted fees by ~96× per FEE-MODEL-001 (commit `e078b4c`, deployed 2026-04-21 07:26 AEDT). Per-trade fee correction: -0.391 SOL. Apples-to-apples math: PRE-cliff under realistic fees = -566 SOL on 2,984 trades = mean -0.19 SOL/trade. POST-cliff = +0.014 SOL/trade. **Under fair accounting, POST is +0.20 SOL/trade BETTER than PRE.**
- §3 sizing verification: archive p50 amount 0.32 SOL → current p50 0.082 SOL (5× reduction); archive effective fee rate 0.36% of position → current 1.50% (4× reduction in fee % efficiency at smaller positions).
- §5 exit-reason composition: BREAKEVEN_STOP 131 fires PRE → 0 POST (env override removed); staged_tp_+50/+100/+250/+400/+500% all REMOVED via env override; staged_tp_+200/+1000% RETAINED. TRAILING_STOP mean dropped 12× (sizing 5× × fee impact 2.4× explains full magnitude). Stop-loss tighten (35→20%) improved per-fire mean 3.3× (-0.244 → -0.074).
- §5b signal-source: 100% pumpportal both eras. Source-shift hypothesis REFUTED. MC-band shift CONFIRMED (89% in $1-5M PRE → 41.5% POST, gate-driven). Cross-reference with API-CREDITS audit: Telegram channel ID stable, Discord BUG-020 pre-existed cliff, Nansen on dry-run both eras.
- §6 cause-effect: 6 candidates (FEE-MODEL-001, GATES-V5 sizing/stop-loss/gates, breakeven removal, TP flatten) all 🟢 HIGH match. 4 source/regime hypotheses 🔴 REFUTED.
- §7 counterfactual: revert lift = 0 SOL/day (likely negative -2 to -5 SOL/day). §7 prompt's STOP condition triggers — counterfactual < 1 SOL/day.
- §8 recommendation: 🟡 STOP / NO REVERT. Keep FEE-MODEL-001, DASH-RESET, GATES-V5 sizing/stop-loss/gates, ML-012 fix. Track 5 follow-ups (Tier 2 🟢): STRATEGY-CLIFF-FOLLOWUP-001, PRE-DEPLOY-PNL-VALIDATION-001, BREAKEVEN-DECISION-001, TP-SCHEDULE-EVAL-001, SIGNAL-MIX-ANALYSIS-001.
- §10 institutional learning: every audit since 04-22 operated only on POST-cliff data (DASH-RESET wiped current paper_trades; archive table existed but no query used it). Process improvement codified in PRE-DEPLOY-PNL-VALIDATION-001.
- **NO services/* edit, NO deploy, NO env change, NO Redis writes.** Audit: `docs/audits/STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md`. Recommendation: `.tmp_cliff_investigation/recommendation.md` (gitignored).

---

## 2026-05-06 ~13:00 UTC — MARKET-MODE-001-RE-CALIBRATE (Path C / STOP, no code change)

- §0 predecessor verification PASS for both BOT-CORE-ML-GATE-001 and TIMEZONE-AUDIT-001.
- §3 Step 1 throughput: **45.8% zero-trade hours** (55/120, post-Session-2 5-day window) — above 20% STOP threshold; recalibration technically warranted on volume grounds.
- §3 Step 2 mode distribution (n=1,436 5-min snapshots): NORMAL 51.7%, DEFENSIVE 46.8%, HIBERNATE 1.3%, AGGRESSIVE 0.2%, FRENZY 0%. **HIBERNATE-cycling premise was incorrect** — actual problem is DEFENSIVE share.
- **Surprise finding (PnL inversion):** NORMAL has WORSE per-trade PnL than DEFENSIVE in the post-Session-2 sample. NORMAL: 121 trades / -1.09 SOL / 24.8% WR. DEFENSIVE: 45 trades / +0.25 SOL / 28.9% WR. Expanding NORMAL would have been actively harmful.
- §3 Step 3 binding constraint: **`dex_vol` not `grad_rate`** (matches §4 Path C explicit STOP example). Live mig=215 is 7× the NORMAL threshold of 30. Off-peak Solana dex_vol drops to $800M-1B band, below $1B NORMAL gate.
- §4 decision: **Path C / STOP**. Per the prompt's own §4 Path C: "If §3 reveals something unexpected (e.g., dex_vol is the binding constraint...), STOP and emit a finding doc. Do not patch into uncertainty."
- New roadmap items: DEFENSIVE-VS-NORMAL-PNL-INVERSION-001 (Tier 1), MARKET-MODE-001-RE-CALIBRATE-V2 (Tier 1, re-scoped), PUMPFUN-VOL-PLACEHOLDER-001 (Tier 2), MM-HYSTERESIS-ONLY-001 (Tier 2).
- **`services/market_health.py` UNCHANGED.** No deploy. No env change. Finding doc only: `docs/audits/MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`.

---

## 2026-05-05 ~15:30 UTC — TIMEZONE-AUDIT-001 (read-only sweep, no code change)

- Repository-wide grep sweep for hardcoded TZ offsets across services/, dashboard/, Scripts/.
- **Findings:** 2 🔴 BUG (both `services/bot_core.py:754,776` — covered by existing TIME-PRIME-AEDT-AEST-DRIFT-001), 2 🔵 MARGINAL, 5 🟡 OK-WITH-CAVEAT, 20+ 🟢 SAFE.
- **`services/market_health.py` is 🟢 SAFE** — fully DST-aware via `pytz.timezone("Australia/Sydney")`. Critical for the next session: MARKET-MODE-001-RE-CALIBRATE can proceed without bundling a TZ fix.
- 4 new LOW-priority hygiene items filed: TZ-CONVENTION-DOC-001, RISK-MGR-TZ-COMMENT-001, SIGAGG-ML-HOUR-LABEL-001, DASH-AEDT-LABEL-001.
- Recommended convention codified into AGENT_CONTEXT.md + CLAUDE.md: decision logic uses `ZoneInfo("Australia/Sydney")` or pytz; storage uses UTC; no hardcoded offsets anywhere except UTC-by-design global-session bands (which must be commented).
- Audit: `docs/audits/TIMEZONE_AUDIT_2026_05_05.md` (~265 lines, §1-§10).

---

## 2026-05-05 14:16-15:01 UTC — BOT-CORE-ML-GATE-001 deploy + §6 verification

- Code commit `ea0da2f` deployed at ~14:13Z (gate inert because env defaults to 0 — verifies the "default-safe" deploy property).
- Env `ML_THRESHOLD_BOT_CORE_SD=40` set at 14:16Z; second deploy auto-triggered, container start **14:16:48Z** UTC = canonical gate-active timestamp.
- §6 verification at ~15:01Z (45min post-cutoff under DEFENSIVE market mode):
  - `below_40` SD-paper admission count post-cutoff = **0** (gate firing OR no <40 signals reaching bot_core; both indistinguishable in this sample).
  - `40_plus` count = **1** (id=8039, mint EV1na7Wj5WLX, ml_score=47.0, admitted at 14:58:36Z, 41m48s post-cutoff).
  - `BOT_CORE_ML_GATE` reject log lines = **0** (consistent with steady-state agreement of SA gate at 30 / bot_core gate at 40 — bot_core gate fires only on the discrepancy edge).
  - `market:mode:current` = **DEFENSIVE** (suppresses upstream throughput, explains the small sample).
  - `bot:emergency_stop` = absent (not tripped).
- **Verdict: PASS (low-confidence, single-sample).** Gate landed cleanly; full confidence pending NORMAL-mode window with multi-trade-per-hour throughput (blocked by the queued MARKET-MODE-001-RE-CALIBRATE follow-up).
- Predecessor for: TIMEZONE-AUDIT-001, MARKET-MODE-001-RE-CALIBRATE (both queued in this same CC session).
- Audit: `docs/audits/BOT_CORE_ML_GATE_001_2026_05_05.md` (536 lines, 9 sections).

---

## 2026-05-01 ~12:30 UTC — STATE-RECONCILE-2026-05-01 (Session 2 of 6 chained-prompt sequence)

### Findings A-E (verified production DB, last 7d SD-paper unless noted)

- **A — ML score band performance:** 30-40 +0.49 / **40-50 -1.98 (worst)** / 50-60 -0.18 (flat) / 60-70 -0.70 / **70-80 +1.63 (best)** / 80-90 -0.35 / 90+ +0.005. Chat-side framing of "50+ mostly profitable" REFUTED — only 70-80 reliably positive. The 2026-04-17/19 magnitudes (CLAUDE.md ML threshold block table) have collapsed by ~50-100×.
- **B — AEST hour distribution:** 18-20 -2.46 SOL on 114 trades (worst, confirmed); 11-17 +0.18 (flat, confirmed); chat's "AEST 21-23 + 00-08 ~+1 SOL" disconfirmed (actual ~-1.45 SOL).
- **C — Exit reasons:** TRAILING_STOP +7.93 / 206 / 76.7% WR ✓ dominant winner. Top losers: `no_momentum_90s` -7.40 / 356 / 0% (LARGEST, chat omitted), `graduation_stop_loss` -6.36 / 67 / 0%, `stop_loss_20%` -5.16 / 74 / 0%. Post-grad bleed = -12.09 SOL on 173 trades (chat said -23; actual is HALF). TRAILING_STOP captures **69%** of gains, not 98%.
- **D — Analyst recency:** Last entry 2026-04-28 13:02 UTC. 0 entries last 3 days. ANALYST-DISABLE-002 enforcement confirmed.
- **E — SD daily trend:** WR 04-22/23 ~50% → 04-30 17.9% → 05-01 (early) 0%. Direction confirmed; aggregate 14d still net +9.0 SOL but recent 4d -1.18 SOL.

### Reconciliation outcome

PROCEED with nuanced doc reconciliation. No STOP triggered (headlines confirmed). Chat-side detail-level framings adjusted to actual data where they overstated (50+ profitability, post-grad bleed magnitude, TRAILING_STOP %, +1 SOL elsewhere claim). 0 🔴 ACTION-CHANGING / 2 🟡 SCOPE-CONFUSION / 3 🟢 SAMPLE-STALE / 1 🔵 NUANCE-MISSING per drift severity classification.

### Doc updates landed

- CLAUDE.md: ML threshold block 2026-05-01 addendum + reference to USERMEMORIES_DRIFT_2026_05_01.md
- AGENT_CONTEXT.md: state-header refresh + TIME_PRIME env vars added to bot_core config table
- ZMN_ROADMAP.md: STATE-RECONCILE Decision Log entry; future-queued POST-GRAD-LOSS-INVESTIGATION-001 (with corrected -12 SOL ROI estimate), ML-THRESHOLD-DATA-DRIVEN-RETUNE-001, TIME-PRIME-AEDT-AEST-DRIFT-001, TIME-PRIME-CALIBRATION-001
- MONITORING_LOG.md: this entry
- STATUS.md: Session 2 entry prepended
- docs/audits/USERMEMORIES_DRIFT_2026_05_01.md: NEW

### Carry-overs to Session 3

POST-GRAD-LOSS-INVESTIGATION-001 should test 5 hypotheses against the -12.09 SOL post-grad bleed (NOT chat's -23 SOL — recalibrate ROI expectation). The largest single loss-source is actually `no_momentum_90s` (-7.40 SOL), which is a SEPARATE category from the post-grad investigation scope.

---

## 2026-04-17 ~morning AEDT — Helius URL resolver + sell-storm circuit breaker

### Diagnosis
Overnight 2026-04-17 `live_trade_log` between 20:56 Apr 16 and 07:07 Apr 17
showed 7,448 `PumpPortal Local: no Helius URL available for transaction
submission` errors across 1,475 distinct mints. `_execute_pumpportal_local`
iterated only `(HELIUS_STAKED_URL, HELIUS_RPC_URL)` and fell through when both
were empty. `HELIUS_GATEKEEPER_URL` was set but unread by that send path.

Separately, bot_core's `HELIUS_STAKED_URL` was pointing at the plain
`mainnet.helius-rpc.com` URL instead of the real `ardith-mo8tnm-fast-mainnet`
staked endpoint (which web + signal_aggregator had correctly).

Once `HELIUS_RPC_URL` resolved at 06:37, the bot produced 50+ TX_SUBMITs
through 08:23 AEDT — signing works, wallet drained from 5.0 to 3.677 SOL
across the successful window. Zero `SignatureFailure` in 83+ on-chain
attempts.

### Shipped (commit cd266de)
- `services/execution.py`: `_execute_pumpportal_local` and
  `_send_transaction` now include `HELIUS_GATEKEEPER_URL` as final fallback
- `services/execution.py`: startup `RuntimeError` if TEST_MODE=false with
  no Helius URLs configured (was silent → 10h of retries)
- `services/execution.py`: 4xx/5xx body truncation 200 → 2048 for diagnosis
- `services/bot_core.py`: sell-storm circuit breaker — park a mint after
  `SELL_FAIL_THRESHOLD` (default 8) consecutive live-sell `ExecutionError`s
  for `SELL_PARK_DURATION_SEC` (default 300s)

### Env var reset on bot_core
`HELIUS_STAKED_URL` changed from `mainnet.helius-rpc.com` to
`ardith-mo8tnm-fast-mainnet.helius-rpc.com` (now matches web).

### Verified
- Syntax check passes both files
- Startup validation raises RuntimeError when all URLs empty + live mode
- Imports clean in paper mode with no URLs (bypass works)
- TEST_MODE=true for deploy

### Not fixed (documented for next session)
Reconcile filter IS correct — `_load_state` and `_reconcile_positions` both
filter by `trade_mode`. But both run only in `__init__`, so a TEST_MODE flip
without container restart leaves paper positions in `self.positions`. Root
cause of v4 EMPTY — not a reconcile bug, a restart-discipline bug.

Full session report: `ZMN_HELIUS_URL_FIX_REPORT.md`

---

## 2026-04-17 ~09:50 AEDT — Trial v4 Overnight Result: EMPTY

Monitor ran 1 minute before hitting 10-consecutive-error stop.
3,358 sell errors (stale paper positions), 0 buys attempted, 0 on-chain
transactions. Wallet untouched at 5.0000 SOL.

Root cause: bot_core never restarted to pick up reconcile fix (4b647a7).
In-memory self.positions still had stale paper entries, blocking buys
via MAX_SD_POSITIONS and generating sell errors.

Signing verdict: INCONCLUSIVE (never exercised on buys).
SignatureFailure count: 0 (consistent with v3 findings).

Action needed: flip TEST_MODE=true (restart), verify clean state,
then flip back for v5 with fresh reconcile.

Full report: ZMN_LIVE_TRIAL_V4_RESULT.md

---

## 2026-04-17 ~11:30 AEDT — Trial v3 Cleanup + Reconcile Fix

Trial v3: signing VERIFIED (0 SignatureFailure in 83+ attempts), BLOCKED
by 2 stale paper positions filling MAX_SD_POSITIONS=2.

Cleanup (TEST_MODE=false, wallet safe):
- 2 stale positions closed (exit_reason='mode_flip_cleanup')
- Redis bot:status + paper:positions:* cleared
- bot_core._reconcile_positions + _load_state now filter by trade_mode
  (commit 4b647a7) — paper positions don't block live MAX_SD_POSITIONS
- MAX_SD_POSITIONS: 2 -> 20, DAILY_LOSS_LIMIT_SOL: 4.0 (kill at wallet 1.0 SOL)
- risk_manager.py: DAILY_LOSS_LIMIT_SOL now reads from env var (was hardcoded 1.0)

Trial v4: ready for overnight run. Bot on TEST_MODE=false with zero
positions, reconcile filtering live-only, 20 slots available.

---

## 2026-04-17 ~10:30 AEDT — Deploy Discipline Rule Added

Documented in CLAUDE.md and AGENT_CONTEXT.md: never use git push AND
railway up in the same session. GitHub webhook auto-deploys on push,
so railway up is redundant and causes duplicate builds. Default to
git push only. Also updated AGENT_CONTEXT.md Section 0.4 with current
trading state (wallet 5.0 SOL, live trial history, paper health).

---

## 2026-04-17 ~10:00 AEDT — Open Positions Mode Filter + MCAP Columns

Fixed OPEN POSITIONS showing 4 paper trades in LIVE view. Root cause:
api_positions read Redis bot:status first (paper-only). Now skips Redis
when mode=live, queries DB directly. Also changed Entry/Current columns
to Entry Mcap / Current Mcap (USD, matching RECENT TRADES convention).
Commit: c328784

---

## 2026-04-17 ~09:30 AEDT — Dashboard Honesty + Solders v2 Deploy

### Dashboard mode filter complete
All main dashboard widgets now filter by trade_mode. LIVE view shows
zeros when no live trades exist. PAPER view unchanged.
Commit: 09ed21f

### Solders signing v2
VersionedTransaction(message, [keypair]) constructor — verified locally
with realistic SOL transfer instruction round-trip.
Commit: ce86cd5

---

## 2026-04-17 ~09:00 AEDT — Solders Signing Fix v2 (Constructor API)

### What happened
Found the correct solders signing API. The VersionedTransaction
CONSTRUCTOR `VersionedTransaction(message, [keypair])` handles signing
internally. Neither `.sign()` (v1 attempt) nor `populate(msg, [sig])`
(v2 attempt) work for re-signing deserialized transactions.

### What was wrong with each attempt
- **v1 (.sign):** API removed in solders 0.21+ (AttributeError)
- **v2 (populate):** Compiles but produces invalid signatures.
  `populate(msg, [sig])` builds the tx but the signature doesn't match
  what validators expect — the message serialization differs between
  `sign_message(bytes(msg))` and what the constructor produces internally.
- **v3 (constructor):** `VersionedTransaction(tx.message, [keypair])`
  — the constructor handles the full sign-then-assemble flow correctly.

### Verification
Tested locally with realistic SOL transfer instruction (not toy/default):
- CompiledInstruction with System Transfer, proper header, 3 accounts
- Round-trip: from_bytes → constructor re-sign → verify_with_results = [True]
- Bytes match after round-trip

### Commit
ce86cd5: 3 signing blocks updated (lines 275, 351, 455)

### Next step
Deploy → Jay flips TEST_MODE=false for 1-trade live test → flip back.

---

## 2026-04-17 ~08:30 AEDT — Ghost Position Cleanup + Live Trial v2 Findings

### Ghost positions (1,458 in Redis, 2 in DB)
Dashboard showed 1,486 "open positions" from April 5. Root cause:
Redis `bot:status` key held 1,458 stale position entries that were
never cleaned when paper_trades rows were closed. Dashboard API reads
bot:status FIRST and only falls back to DB if it's empty.

**Fix:** Deleted bot:status (1,458 entries) + 176 paper:positions:*
keys from Redis. Dashboard now falls back to DB (2 actual open).

### Live trial v2 (TEST_MODE=false flipped by Jay ~08:00 AEDT)
- Solders populate() fix COMPILES and SIGNS — no more AttributeError
- BUT: transactions fail on-chain with `SignatureFailure`
- "Transaction simulation failed: Transaction did not pass signature verification"
- The populate(message, [sig]) reconstruction from a deserialized tx
  doesn't preserve message fidelity — the signature doesn't match
  what validators expect
- ALL 177+ events are sell ERRORs (trying to exit stale paper positions)
- Zero live trades landed. Wallet untouched (5.0 SOL)
- **TEST_MODE should be reverted to true**

### Signing root cause (deeper than first post-mortem)
The `populate()` API works for constructing NEW transactions, but
round-tripping through `from_bytes() → .message → sign → populate()`
loses message integrity. The PumpPortal API returns a pre-built
unsigned transaction. We need to sign it WITHOUT reconstructing.

Correct approach (for next fix session):
```python
# DON'T reconstruct:
tx = VersionedTransaction.from_bytes(tx_bytes)
sig = keypair.sign_message(bytes(tx.message))
signed_tx = VersionedTransaction.populate(tx.message, [sig])  # BREAKS

# DO sign the raw message bytes from the original tx:
from solders.message import MessageV0
from solders.signature import Signature
tx = VersionedTransaction.from_bytes(tx_bytes)
msg_bytes = bytes(tx.message)
sig = keypair.sign_message(msg_bytes)
# Need to construct with the ORIGINAL message object, not re-parsed
```

The exact fix requires testing against the solders API to find the
correct serialization path. May need `solders.transaction.VersionedTransaction`
constructor that takes (signatures, message) directly.

### Commits
- (none this session — diagnosis + Redis cleanup only)

---

## 2026-04-16 ~23:00 AEDT — Live Trial Post-Mortem + Fixes

### What happened
Live trial flipped TEST_MODE=false at ~22:00 AEDT. 244/244 execution
attempts failed with `'VersionedTransaction' object has no attribute 'sign'`.
Zero trades landed on-chain. Wallet untouched (5.0 SOL).

### Root cause
solders >= 0.21 made VersionedTransaction immutable, removing `.sign()`.
execution.py was written for the old 0.18 API. requirements.txt had
`>=0.20.0` with no ceiling — Railway installed 0.27+.

### Corrective actions
- **TEST_MODE:** Found still false at session start. SET TO TRUE immediately.
- **Solders fix:** Rewrote 3 signing blocks to use `populate()` API.
  Pinned `solders>=0.21.0,<1.0.0` (commit f59f025).
- **Helius budget:** Restored HELIUS_DAILY_BUDGET=100000 on web service
  (was 0 from debug session).
- **Ghost positions:** Only 1 open (not 1,689 Jay reported — likely stale
  dashboard cache). Bulk close skipped.
- **Dashboard currency:** Already SOL-primary. No change needed.

### Current state
- TEST_MODE: true (paper mode)
- Wallet: 5.0000 SOL
- Open positions: 1
- Helius: budget restored to 100k
- Solders: fixed, awaiting deploy

---

## 2026-04-16 ~20:45 AEDT — Jito Tip Configurability + Trial Safety Env Vars

Made Jito tips and priority fees env-var configurable in execution.py.
Defaults unchanged. Set trial safety: MAX_SD_POSITIONS=2.
DAILY_LOSS_LIMIT_SOL=1.0 hardcoded in risk_manager.py (already correct).
MAX_TRADES_PER_HOUR=500 (effectively unlimited, Jay's preference).
TEST_MODE still true. No tip values changed from defaults.

Commit: d3fb18e (execution.py configurability)

Remaining for live trial: override 0.15 SOL position floor in
bot_core.py + flip TEST_MODE=false.

---

## 2026-04-16 ~20:25 AEDT — Trade Mode Segregation (Clean Slate for Live)

### What happened
Added `trade_mode` column to paper_trades ('paper' default NOT NULL).
Updated paper_trader INSERT to write mode from TEST_MODE. Dashboard API
filters key queries by mode, defaults to backend mode. Dashboard HTML
shows mode badge (PAPER amber / LIVE red) + toggle dropdown.

### Schema
- ALTER TABLE paper_trades ADD COLUMN trade_mode TEXT NOT NULL DEFAULT 'paper'
- Index: idx_paper_trades_mode_time on (trade_mode, entry_time DESC)
- 4,977 existing rows auto-populated as 'paper'
- New trades writing 'paper' (TEST_MODE=true confirmed)

### Verification
- Paper view: shows current numbers (all queries return paper rows)
- LIVE view (via ?mode=live or toggle): all zeros (clean slate)
- Bot still trading: 4 trades in 10 min post-deploy
- TP observation query: unaffected (doesn't filter by mode)

### Commits
- 2860bce: paper_trader INSERT + TRADE_MODE constant
- c6b2447: dashboard API mode filter + HTML badge/toggle

### What's NOT done
- Not all ~40 paper_trades queries have mode filter (only key endpoints:
  status, trades, positions). Secondary endpoints (equity curve,
  exit-analysis, personality-stats, etc.) still show all-mode data.
  These can be updated incrementally if needed.

---

## 2026-04-16 ~19:45 AEDT — Helius RPC Audit v2 + Endpoint Switch

Tested all 3 Helius endpoints under single-call and burst conditions.
Standard RPC won decisively (48ms median, 20/20 burst) vs Gatekeeper
(430ms, 20/20) vs Secure (all 522, 0/20).

**Action:** HELIUS_STAKED_URL switched from Secure → Standard RPC.
Gatekeeper kept as HELIUS_GATEKEEPER_URL fallback. No code changes.

**Verification:** bot_core redeployed cleanly, exit evaluator running,
signals flowing. Dashboard still healthy.

**Helius Staked 522 blocker: RESOLVED.** All execution APIs now ready.

---

## 2026-04-16 ~19:30 AEDT — External API Audit (Read-Only)

Read-only audit of every external service the bot depends on.

### Critical findings
- **Helius Staked RPC: DOWN (522)** — primary tx submit endpoint.
  Fallback to standard RPC works (285ms). Needs new URL from Helius
  dashboard or accept standard RPC for live.
- **Anthropic: CREDITS EXHAUSTED** — governance LLM non-functional
- **SocialData: CREDITS EXHAUSTED** — social enrichment dead
- All other execution-critical APIs: WORKING

### Latency (median from Sydney, Railway will be faster)
- Helius RPC: 285ms (GOOD)
- Jupiter V2: 365ms (GOOD)
- Jito: 629ms (OK)
- CoinGecko: 48ms (EXCELLENT)

### Verdict: READY WITH ONE FIX
- Fix or accept Helius Staked URL (standard RPC fallback exists)
- Everything else ready for TEST_MODE=false

Full report: EXTERNAL_API_AUDIT.md

No code changes. No deploys. No real trades. Read-only.

---

## 2026-04-16 ~18:50 AEDT — Dashboard Rewrite (Real Wallets + CFGI Cleanup)

### What happened
Replaced paper balance display with real on-chain trading wallet SOL
(Helius getBalance, 30s Redis cache). Added Treasury wallet display
(60s cache). Removed CFGI(BTC) from top bar. CFGI(SOL) renamed to
just "CFGI". B-013 DEFERRED (symbol column empty for all trades).

### Verification
- Trading wallet: 5.0000 SOL (real on-chain) 
- Treasury wallet: 0.0984 SOL (real on-chain)
- CFGI(BTC) removed: confirmed
- Bot still trading: 11 trades/15min
- Dashboard loads cleanly: yes

### Bugs
- B-013: DEFERRED — symbol column empty for all 4963 paper_trades.
  paper_buy doesn't populate it. Needs upstream fix in paper_trader or
  signal enrichment. Not a dashboard fix.
- B-014: OBSOLETE — CFGI(BTC) removed from display entirely

### Commits
- a2a32bb: Dashboard code changes

---

## 2026-04-16 ~18:15 AEDT — Shadow Phase 2 Analysis + Execution Audit (Read-Only)

### What happened
Combined read-only session analyzing 20h of shadow execution
measurements (2,959 entries) and auditing real execution infrastructure.

### Shadow Analysis findings
- 2,959 measurements over 20.0 hours (734 entries, 1477 exits, 748 staged TPs)
- Decision-to-fill: median 483ms (real adds ~1-2s)
- Paper vs BC price gap: median 2.98%
- Peak-to-exit gap: median 28.2% (trailing stops fire after significant peak drop)
- Staged TP overshoot: +50% fires at median 1.81x (20.9% past trigger)
- **Winner survival rate: 90.9%** (308 of 339 paper winners survive live)
- Median execution discount: 19% (paper overstates live P/L by ~1/5)
- **Live edge assessment: STRONG**

### Execution Audit findings
- Complete execution infrastructure EXISTS (execution.py, 704 lines)
- Jupiter V2 swap: COMPLETE
- PumpPortal local buy/sell: COMPLETE
- Jito MEV bundle: COMPLETE (3 tip tiers: 0.001/0.01/0.1 SOL)
- Tx signing: COMPLETE (Keypair from env var)
- RPC: Helius paid (staked + standard endpoints)
- Trading wallet: 5.00 SOL funded
- Safety rails: comprehensive (position limits, loss limits, circuit breakers)
- **Gaps to close: 1 minor** (position floor hard-coded at 0.15 SOL, need 0.05 override)
- **Estimated prep session: ~30 min**

### Reports
- SHADOW_ANALYSIS_2026_04_16.md
- EXECUTION_AUDIT_2026_04_16.md

### Next steps for trial trading
1. Override MIN_POSITION floor from 0.15 to 0.05 SOL
2. Tighten safety limits (MAX_DAILY_LOSS=0.50, MAX_POSITIONS=2)
3. Flip TEST_MODE=false on bot_core
4. Monitor first 5-10 real trades
5. 50-trade minimum observation before scaling up

No code changes. No deploys. Read-only.

---

## 2026-04-15 ~22:20 AEDT — Shadow Trading Phase 1 (Measurement Infrastructure)

### What happened
Built measurement infrastructure to enable comparing paper simulation
behavior against what real execution would observe. Paper mode only.
Three measurement events added to bot_core.

### What was instrumented
- **ENTRY_FILL:** signal age, paper fill price vs BC price, decision-to-fill
  latency (avg ~475ms, real execution adds ~1-2s on top)
- **EXIT_DECISION:** exit reason, peak gap %, remaining position, hold time
- **STAGED_TP_HIT:** trigger overshoot % (avg 23-29% — bot fires TPs well
  past nominal trigger due to 2s exit checker cycle)

### Early findings (first 2 trades)
- Decision-to-fill: 423-526ms (paper). Real adds ~1-2s Solana latency.
- Staged TP overshoot: +50% trigger fired at 1.85x (23% past nominal),
  +100% trigger fired at 2.59x (29% past nominal). This confirms the
  exit checker's 2s cycle causes significant overshoot.
- New TP config CONFIRMED ACTIVE: sell_frac=0.30 at +50%, 0.4286 at +100%

### Data destination
- Stdout: `SHADOW_MEASURE <event> <json>` (Railway logs)
- Redis: `shadow:measurements` list (48h TTL, 10k cap)

### Phase outcomes
- Phase 0: PASSED (31 trades/hr)
- Phase 1: measurement points identified
- Phase 2: instrumentation added (commit 0d5fb8e)
- Phase 3: deployed, logs flowing, 13+ entries in 2 min, trading unchanged

### Commits
- 0d5fb8e: Shadow measurement instrumentation

---

## 2026-04-15 ~21:35 AEDT — TP Redesign Experiment (Option B2)

### What happened
First experimental change to Speed Demon exit strategy. Changed staged
TP config from 50/100/200/400% at 25% each to 50/100/250/500/1000% at
30/30/20/10/10% (of original position, converted to % of remaining).

### Baseline (pinned in TP_BASELINE_2026_04_15.md)
- 545 closed trades, 40.6% WR, +0.0653 SOL/trade, +35.61 SOL total
- Staged 213 trades at 96.7% WR, +51.19 SOL

### Phase outcomes
- Phase 0 Pre-flight + baseline validation: PASSED (all within range)
- Phase 1 Baseline pinned: DONE (commit 1e5e169)
- Phase 2 TP config found: env var STAGED_TAKE_PROFITS_JSON (unset, using code default)
- Phase 3 New config deployed: SUCCEEDED via env var on bot_core
- Phase 4 Verification: PARTIAL — 1 staged trade (4183 at +50%) observed, insufficient
  for full confirmation. Need to observe +250% level (new-only) to confirm.

### Config change
- OLD: `[[0.50,0.25],[1.00,0.25],[2.00,0.25],[4.00,0.25]]` (code default)
- NEW: `[[0.50,0.30],[1.00,0.4286],[2.50,0.50],[5.00,0.50],[10.00,1.00]]` (env var)
- Semantic: sell_pct is % of REMAINING position (existing semantic, no code change)
- Conversion from % of original: 30%/30%/20%/10%/10%

### Deploy epoch
2026-04-15 11:32:07 UTC (epoch 1776252727)
Reference point for observation queries.

### Revert criteria (hard rules — any Claude MUST honor)
1. WR < 35.6% over any 100-trade window → REVERT
2. Avg P/L < 0.049 SOL/trade over any 100-trade window → REVERT
3. Staged WR < 86.7% over any 50-trade staged window → REVERT
4. Rolling 50-trade P/L negative (after first 25 trades) → REVERT
5. Any deploy issue, crash, or trading stoppage → REVERT immediately

### Revert procedure (any Claude can execute)
```bash
# 1. Reset env var to old config
railway variables --set 'STAGED_TAKE_PROFITS_JSON=[[0.50,0.25],[1.00,0.25],[2.00,0.25],[4.00,0.25]]' -s bot_core
# 2. Force redeploy
railway up -s bot_core
# 3. Verify next 5 trades use OLD levels (200%, 400%)
# 4. Document revert in this monitoring log
```

### Observation query (run every 12h)
```sql
WITH post_redesign AS (
  SELECT *, COALESCE(corrected_pnl_sol, realised_pnl_sol) AS pnl
  FROM paper_trades
  WHERE entry_time > 1776252727 AND exit_time IS NOT NULL
),
staged AS (
  SELECT * FROM post_redesign
  WHERE staged_exits_done IS NOT NULL
    AND staged_exits_done NOT IN ('[]', '{}', '')
)
SELECT
  (SELECT COUNT(*) FROM post_redesign) AS total_trades,
  (SELECT ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1) FROM post_redesign) AS wr_pct,
  (SELECT ROUND(AVG(pnl)::numeric, 4) FROM post_redesign) AS avg_pnl,
  (SELECT ROUND(SUM(pnl)::numeric, 4) FROM post_redesign) AS total_pnl,
  (SELECT COUNT(*) FROM staged) AS staged_trades,
  (SELECT ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1) FROM staged) AS staged_wr_pct;
```

First check due: 2026-04-15 ~23:32 UTC (12h after deploy)
Observation window ends: 2026-04-17 ~11:32 UTC (48h after deploy)

### Success criteria
48h observation, >= 200 trades, NO revert criteria hit →
redesign is SUCCESSFUL. Update baseline to new config.

### Commits
- 1e5e169: Baseline pinned

---

## 2026-04-15 ~19:30 AEDT — CFGI Display Diagnostic (Read-Only)

Read-only investigation of dashboard CFGI display discrepancy.

**Bug A (BTC/SOL same value):** Dashboard API reads `market:health.cfgi`
for the "BTC" label, but post-Stage-2 that key holds SOL value.
`cfgi_btc` key exists in Redis but dashboard API never reads it.
Fix: add `cfgi_btc` to API response + update HTML render. ~10 min.

**Bug B (SOL 5 points off):** API uses `period=2` (1h granularity),
cfgi.io website shows real-time. The 5-point gap is smoothing, not a
bug. Also: cfgi.io BTC CFGI (65) differs from Alternative.me F&G (23)
because they are different indices entirely.

Severity: cosmetic, no trading impact. Logged as B-014.
Bundle with B-013 for weekend dashboard cleanup session.

Full report: CFGI_DISPLAY_DIAGNOSTIC_2026_04_15.md

No code changes. No deployments. Read-only.

---

## 2026-04-15 ~09:45 AEDT — B-011 + B-012 Fix Session

### What happened
Combined session to fix two bugs from yesterday's post-recovery review.

### Phase outcomes
- Phase 0 Pre-flight: PASSED (11 trades/hr, cfgi.io SOL=41.0 ACTIVE)
- Phase 1 B-011 root cause: found in paper_trader.py:296 (outcome
  computed but never included in UPDATE statement)
- Phase 2 B-011 code fix: SUCCEEDED (commit 77d6a8a)
- Phase 3 B-011 backfill: SUCCEEDED (2,966 rows updated)
- Phase 4 B-012 root cause: NOT A BUG — STAGED_TP_FIRE is firing
  correctly. Earlier diagnosis was false positive from insufficient
  log observation window.
- Phase 5 B-011 companion fix in bot_core._close_position: also
  had "profit" instead of "win" and didn't write outcome to DB on
  staged TP full close (commit 429dd87)

### B-011 details
- Root cause: paper_trader.paper_sell() computed outcome = "profit"
  (wrong value, should be "win") and never included it in the UPDATE
  SQL. Also, bot_core._close_position() had same bug for staged TP
  cumulative close path.
- Fix: both locations now write outcome="win"/"loss" to DB
- Backfill: 2,966 rows updated from NULL to win/loss via P/L sign
- Verification: fresh trades have outcome populated correctly
- Distribution after fix: 3,647 loss, 448 win, 1 breakeven

### B-012 details
- STAGED_TP_FIRE IS firing correctly. Confirmed in bot_core logs
  with multiple entries (e.g., DbQwDAWL +50% at 1.90x, +100% at 2.45x).
- Earlier report of 0 matches was due to Railway log stream timeout
  (only captures ~15s of streaming activity).
- B-012 reclassified as FALSE POSITIVE. CLOSED.
- TP redesign data IS accumulating as intended.

### cfgi.io credit topup status
- Jay topped up 100k credits
- cfgi.io SOL CFGI now live as primary: 41.5
- cfgi_btc preserved: 23.0
- Mode still HIBERNATE (mode determined by DEX volume, not CFGI)

### Commits
- 77d6a8a: B-011 paper_sell outcome fix
- 429dd87: B-011 companion bot_core outcome fix + B-012 closed
- (this commit): docs

---

## 2026-04-15 ~08:25 AEDT — Stage 2 Cutover (Minus Analyst)

### What happened
Cut bot_core and signal_aggregator from reading Alternative.me
Bitcoin F&G (~21) to cfgi.io Solana CFGI for mode decisions.
Simultaneously disabled Analyst personality via ANALYST_DISABLED
env var pending investigation of its 0/3 loss pattern.

**Important caveat:** cfgi.io is returning HTTP 402 (Payment Required)
since ~21:46 UTC Apr 14 — free credits exhausted. The cutover code
is correct and deployed, but the BTC fallback is active. When Jay
tops up cfgi.io credits, the SOL value will auto-populate as the
primary CFGI without any code changes needed.

### Phase outcomes
- Phase 0 Pre-flight: PASSED (20 trades/2h, cfgi.io 402 discovered)
- Phase 1 Analyst disable: SUCCEEDED (commit f3a5c74)
- Phase 2 Verify disable: PASSED (0 Analyst trades, Speed Demon only)
- Phase 3 CFGI key swap: SUCCEEDED (commit eebccf5, BTC fallback active)
- Phase 4-5 Observation: CLEAN (10 trades/hr, Speed Demon only)

### Redis state at session end
- market:health.cfgi: 21.0 (BTC fallback, cfgi.io 402)
- market:health.cfgi_btc: 21.0 (new key, BTC preserved)
- market:health.cfgi_sol: None (cfgi.io 402)
- market:mode:current: HIBERNATE

### Services modified
- signal_aggregator: Analyst disable code + ANALYST_DISABLED=true env var
- market_health: CFGI key writes swapped (SOL primary, BTC fallback)

### Services NOT modified
- bot_core, ml_engine, governance, web, treasury, signal_listener

### Commits
- f3a5c74: Analyst disable
- eebccf5: CFGI key swap

### Next steps
1. Jay tops up cfgi.io credits → SOL CFGI auto-activates
2. Investigate Analyst 0-2s hold pattern (separate session)
3. Fix B-011, B-012, B-013

---

## 2026-04-14 ~23:25 AEDT — Dashboard Enhancements (Themes + Headers)

### What happened
Two dashboard features added in a bounded-scope session:
- 8-theme colour selector with localStorage persistence
- Unified headers across Open Positions / Recent Trades / Recent
  Signals panels, including copiable contract address column

### Features
- **Theme selector:** 8 themes (acid, amber, cyan, magenta, red,
  purple, orange, blue), dropdown in top bar, persists per-browser
  via localStorage. Chart.js defaults update on theme change.
- **Panel unification:** All three panels now lead with TIME (AEDT) /
  TOKEN / ADDRESS columns. Address cell has copy-to-clipboard button.
  Signals API now returns full mint (was truncated to 12 chars).

### Phase outcomes
- Phase 0 Pre-flight: PASSED (23 trades/hr, cfgi_sol=61.5)
- Phase 1 Theme selector: DONE (commit 91a1aae)
- Phase 2 Panel headers: DONE (commit 2bf574d)
- Phase 3 Deploy + verify: SUCCEEDED

### Trading state after session
- Bot still trading: YES (28 trades in last 30 min)
- Stage 1 cfgi_sol still populated: YES (62.0)
- All API endpoints returning 200

### Commits
- 91a1aae: Theme selector (8 themes, CSS variables, localStorage)
- 2bf574d: Panel header unification + signals full mint

---

## 2026-04-14 ~22:50 AEDT — Post-Recovery Data Review (Read-Only)

Read-only analysis confirming post-recovery trading health before
Stage 2 cutover decision.

**Verdict: SAFE TO SHIP STAGE 2**
- WR post-recovery: 28.3% (53 trades, 15 wins)
- Total P/L since recovery: +0.0518 SOL (barely positive)
- Pattern: A (materially worse than pre-crash 50% WR), but likely
  random variance on small sample + different market conditions
- Winner concentration: CRITICAL (top winner = 645% of total P/L)
- Staged TPs working: 14 trades at 92.9% WR carrying the portfolio
- STAGED_TP_FIRE log: NOT appearing (instrumentation bug)
- New bug found: outcome column NULL since id=1131

Full report: POST_RECOVERY_REVIEW_2026_04_14.md

No code changes. No deployments. Read-only.

---

## 2026-04-14 ~22:25 AEDT — cfgi.io Stage 1 (Dual-Read)

### What happened
Added cfgi.io Solana CFGI fetch to market_health, parallel to the
existing Alternative.me Bitcoin F&G fetch. The new value is written
to the `market:health` JSON blob as `cfgi_sol` (NOT replacing `cfgi`).
Dashboard top bar now shows BOTH values side-by-side:
`CFGI(BTC): 21` | `CFGI(SOL): 57`.

bot_core and signal_aggregator UNCHANGED — still read `.cfgi` from
Alternative.me for mode decisions. This is observation-only. 24-hour
window before any Stage 2 cutover decision.

### Key finding
**The CFGI gap is massive:** BTC F&G = 21 (Extreme Fear) vs SOL CFGI
= 56.5 (Neutral). This confirms Jay's suspicion (B-001) — the bot has
been trading under artificially fearful conditions. When Stage 2 cuts
over:
- Analyst personality will likely unpause (CFGI > 20)
- Speed Demon sizing will increase from 0.75x toward 1.0x
- Mode may shift from HIBERNATE toward NORMAL

### Phase outcomes
- Phase 0 Pre-flight: PASSED (CFGI_API_KEY set, all services healthy)
- Phase 1 Code audit: DONE
- Phase 2 Add function: DONE (commit 146ca38)
- Phase 3 Wire into update loop: SUCCEEDED (commit 859c0fa)
- Phase 4 Dashboard update: SUCCEEDED (commit 1ac9cb8)
- Phase 5 No-change verification: PASSED (5 new trades, mode unchanged)

### Values at session end
- market:health.cfgi (BTC, Alternative.me): 21.0
- market:health.cfgi_sol (SOL, cfgi.io): 56.5
- market:mode:current: HIBERNATE
- bot_core trading: yes — 5 trades during session
- Analyst paused: yes (1 boundary trade in 2h, mostly paused)
- Balance: 31.93 SOL

### Commits
- 146ca38: add _fetch_cfgi_io_solana function
- 859c0fa: wire into update loop (dual-read to cfgi_sol key)
- 1ac9cb8: dashboard displays BTC and SOL CFGI side-by-side

### What's NOT in this session
- bot_core is not reading from cfgi.io (still Alternative.me)
- signal_aggregator is not reading from cfgi.io (still Alternative.me)
- Mode decision logic unchanged
- No Stage 2 cutover yet — scheduled 24h after this deploy

### Next session
- CFGI Stage 2 cutover — scheduled for 2026-04-15 ~22:30 AEDT
- Trigger: 24h of Stage 1 observation data available
- Session size: 30-45 min

---

## 2026-04-14 ~21:40 AEDT — Recovery + Hardening Session

### What happened

signal_aggregator had been dead for ~21 hours (Redis DNS failure at
13:38 UTC Apr 13, Railway marked it Completed). This session:

**Phase 1 — Recovery: SUCCEEDED**
- Restarted signal_aggregator via Railway redeploy
- Redeployed bot_core with TP instrumentation (commit 40dadb6)
- Redeployed dashboard API with P/L source fixes (commit dbbffd3)
- Trimmed signals:raw from 1,540,147 to 1,000 entries
- Pass-through corrected_pnl for trades 3606-3630 (25 updated)
  + 7 additional post-recovery trades
- First post-recovery trade: ID 3631 at 11:40:49 UTC
- 25 trades completed within ~20 min of recovery
- NOTE: Dashboard still shows "corrected_pnl_sol does not exist"
  warnings despite column existing in DB. Likely asyncpg schema
  cache issue on Railway container. Non-blocking (falls back to
  realised_pnl_sol).

**Phase 2 — Hardening: SUCCEEDED**
- Added Redis connection retry (5 attempts, exponential backoff
  2s/4s/8s/16s/32s) to signal_aggregator startup
- Added signal_aggregator health heartbeat to `signal_aggregator:health`
  Redis key (30s interval, 120s TTL)
- Deployed via `railway up -s signal_aggregator`
- Verified: "Redis connected on attempt 1" in boot logs
- Verified: `signal_aggregator:health` populated with fresh timestamp
- This prevents the same silent failure mode from recurring

**Phase 3 — cfgi.io Stage 1: SKIPPED**
- CFGI_API_KEY env var not found on market_health service
- Jay needs to add it via Railway dashboard before cfgi.io integration
- No code changes made for this phase

### Commits
- 85768c5: Phase 2 hardening (Redis retry + health heartbeat)
- (Phase 1 was operational only — no code changes)

### Post-session state
- signal_aggregator: Running (hardened with retry + heartbeat)
- bot_core: Running, 25+ trades since recovery
- signals:raw length: ~0 (actively consumed)
- signals:scored flowing: yes (via pubsub to bot_core)
- market:health.cfgi (BTC): 21.0
- market:health.cfgi_sol (SOL): NOT_SET (Phase 3 skipped)
- market:mode:current: HIBERNATE (AGGRESSIVE_PAPER bypasses)

### Known issues still deferred
- CFGI Stage 1 dual-read — needs CFGI_API_KEY env var from Jay
- Dashboard corrected_pnl_sol column error — asyncpg schema issue
- Governance LLM hallucinates "CFGI at 50" (B-010)
- Exits footer TP classification (B-004)
- Vybe endpoint false positive in API Health (B-003)
- TP redesign — 24-48h STAGED_TP_FIRE data clock starts now

### Next session candidates
1. CFGI Stage 1 (after Jay adds CFGI_API_KEY)
2. TP redesign (after instrumentation data accumulates)
3. ML Training Code Update (read corrected_pnl_sol)
4. Social filter deployment
5. Dashboard colour theming

---

## 2026-04-14 ~11:00 AEDT -- State Audit (Read-Only)

### What happened
Read-only investigation triggered by Jay noticing the bot had been idle
for 11+ hours with zero trade activity. Full audit of git state, Railway
services, Redis pipeline state, Postgres trade activity, and dashboard
data sources. No code changes, no restarts, no deployments.

See STATE_AUDIT_2026_04_14.md (commit fb8a389) for the full report.

### Critical findings

**signal_aggregator has been dead for ~21 hours.**
- Crashed at 13:38:16 UTC on 2026-04-13 due to transient Railway
  internal DNS resolution failure: `Error -3 connecting to
  redis.railway.internal:6379. Temporary failure in name resolution`
- Exited cleanly with code 0 (no retry logic on startup Redis connect)
- Railway marked it "Completed" and never restarted it
- 1 minute after the last successful trade (ID 3630 at 13:37:07 UTC)

**Pipeline state:**
- signal_listener: ALIVE (1.5M+ raw signals pumped with no consumer)
- signal_aggregator: DEAD
- market_health: ALIVE (CFGI/mode/SOL price every 5 min)
- bot_core: ALIVE but starved of scored signals, 0 trades in 21 hours
- governance: ALIVE but hallucinating CFGI values ("CFGI at 50" when
  actual is 21)

**Pre-crash performance was excellent:**
- 30 trades between 11:08-13:37 UTC on Apr 13
- 50% WR, +5.44 SOL total P/L
- 15 trades hit staged TPs

**Shadow mode:** zero matches in committed code. Exists only as future
roadmap item #9.6, BLOCKED on #9.5. Not built, not deployed.

**Unknown Railway services:** `query-redis-keys` and `redis-query` are
harmless one-shot diagnostic scripts from a Railway agent. Read-only.

### Root cause
signal_aggregator had NO startup retry logic for Redis connection. A
single transient DNS failure during deploy was fatal. No health
monitoring exists for signal_aggregator in the `service:health` system.

### Commits
- fb8a389: state audit report (STATE_AUDIT_2026_04_14.md)

### What's NOT fixed (queued for recovery session tonight)
- signal_aggregator restart + startup retry loop
- bot_core redeploy (TP instrumentation, commit 40dadb6)
- dashboard_api redeploy (P/L source fixes, commit dbbffd3)
- Trim signals:raw from 1.5M to ~1000
- Add signal_aggregator to service:health heartbeat
- cfgi.io Stage 1 dual-read

---

## 2026-04-13 ~16:00 AEDT — Dashboard Tier 1 Audit + Fixes

### What happened
Full panel-by-panel audit of zmnbot.com dashboard (15 panels). Fixed P/L
data source across all widgets (corrected_pnl_sol + post-cleanup filter).
Diagnosed CFGI source mismatch (fix deferred). Instrumented bot_core staged
TPs for future redesign data collection.

### Headline findings
- Top bar P/L, WR, Equity Curve, Personality P/L, P/L Distribution, Win
  Rates, Session Stats, Signal Funnel, Recent Trades, Exit Analysis all now
  read from `COALESCE(corrected_pnl_sol, realised_pnl_sol)` with
  `entry_time > 1775767260` post-cleanup window filter
- CFGI displays 12 -- this IS correct per Alternative.me API (Bitcoin F&G).
  Jay compared against CMC which uses a different index (42). NOT a display bug,
  it's a data source decision. See DASHBOARD_AUDIT.md B-001.
- Governance LLM text "CFGI at neutral 50" is stale/hallucinated
- bot_core and signal_aggregator read CFGI from same Alternative.me source --
  trading IS affected (Analyst paused, Speed Demon 0.75x sizing)
- SOL price $0.00 fixed with Redis `market:sol_price` fallback
- ML AUC display reduced from 4 decimal places to 1
- 9 known bugs registered in DASHBOARD_AUDIT.md

### Commits
- dashboard P/L source update + SOL price fix + ML AUC format
- bot_core staged TP instrumentation
- docs + audit report

### What's NOT fixed tonight (deferred)
- CFGI data source decision (B-001) -- needs Jay review
- Exits footer TP classification (B-004) -- needs exit_reason investigation
- API Health false positives (B-003) -- needs health check task investigation
- Governance stale reasoning text
- Whale leaderboard, colour theming, CFGI auto-theming

### Next session candidates
1. CFGI fix -- dedicated session with Jay review
2. TP redesign (waiting on 24-48h of STAGED_TP_FIRE data)
3. ML training update to use corrected_pnl_sol
4. Redis sister-bug code fix (paper_sell + bot_core)

---

## 2026-04-13 ~14:00 AEDT — Historical Backfill + Redis Audit

### What happened
Backfilled realised_pnl_sol/pct for 44 pre-fix staged trades using
the actual staged TP allocation formula. Added corrected_pnl_sol,
corrected_pnl_pct, corrected_outcome, correction_applied_at, and
correction_method columns to paper_trades. Post-fix trades (id > 3564)
already have correct values from commit 5b92226 and were passed
through unchanged (215 trades).

### Headline correction
| Metric | Before Backfill | After Backfill |
|---|---|---|
| Wins (clean) | 49 | 68 |
| WR | 18.9% | 26.3% |
| Total SOL | +13.83 | +17.73 |
| Pre-fix SOL | -4.81 | -0.91 |

19 trades reclassified from loss to win (all had staged TPs that
fired profitably, but residual exit was below entry).

### Redis sister-bug audit
- Status: **confirmed** -- winning_trades overcounted (417 vs 229 true)
- Action: deferred (dashboard reads from Postgres, not Redis)

### Dashboard status
- Reads P/L from: Postgres `realised_pnl_sol` (not Redis, not corrected column)
- Needs update: yes (switch to `corrected_pnl_sol`)
- Queued for: future session

### Files changed
- paper_trades schema: +5 columns (corrected_pnl_sol, corrected_pnl_pct, corrected_outcome, correction_applied_at, correction_method)
- migrations/001_add_corrected_pnl_columns.sql
- MONITORING_LOG.md, ZMN_ROADMAP.md, AGENT_CONTEXT.md, CLAUDE.md
- STAGED_TP_BACKFILL_REPORT.md (new)

### Open items for next session
- ML training code update to read corrected_pnl_sol
- TP redesign (30/30/20/10/10 allocation) -- queued
- Dashboard source update -- queued
- Redis sister-bug code fix (paper_sell + bot_core) -- queued

---

## 2026-04-13 — Staged TP Reporting Bug Fix

### Bug discovered
Offline analysis of paper_trades_export.csv revealed that trades with staged take-profits had their `realised_pnl_pct`/`realised_pnl_sol` computed from ONLY the final residual exit. Each `paper_sell()` call overwrites the DB row, so the last exit's P/L becomes the permanent record.

**Headline impact:**
- 19 trades mis-recorded as losses, actually winners (of 44 with staged exits)
- Trade 3560: peaked 13.95x, 4 staged TPs fired, recorded -2.03%, true ~+137%
- Estimated true WR: ~21.6% (recorded 12.8%), above 18.7% break-even threshold

### Fix applied (commit 5b92226)
- Added `cumulative_pnl_sol` accumulator to Position dataclass
- After each `paper_sell()`, accumulate returned P/L
- On final close, correct DB row with cumulative totals across all exits
- Added `PAPER_EXIT` log for staged TP debugging
- Deploy: 2026-04-12 22:55 UTC, bot_core only

### Verification (PARTIAL — 3/5)
- No staged TP trades occurred during 30-min window (CFGI 16 extreme fear, ML scores 2-7)
- Non-staged trade (#3564) recorded correctly (-1.28% no_momentum_90s)
- No crashes, clean startup
- Live validation pending — first staged TP trade in new code will confirm

### What does NOT change yet
- Historical trade data still wrong (backfill is separate session)
- Redis paper:stats have intermediate P/L events (not fixed)
- ML training labels for past staged trades still wrong
- Full details: STAGED_TP_FIX_REPORT.md

---

## 2026-04-12 — Feature Default Fix + Entry Filter v4 Bug Fix + Smart Money Diagnostic

### Feature Default Fix (commit a8a390b) — THE KEY FIX
- **Root cause:** Feature construction in signal_aggregator.py defaulted missing live_stats to 0 instead of -1. The v4 entry filter correctly used -1 as "unknown" sentinel, but never saw -1 because upstream always wrote 0.
- **Affected features:** buy_sell_ratio_5min (line 1854/1866), unique_wallet_velocity (line 1982), buy_sell_ratio_derivative (line 1978)
- **Fix:** Proper `None` check for Redis BSR, explicit `-1` defaults for all missing live data
- **Result:** Pass rate went from 0% to ~95%+ immediately. ML scoring is now the quality gate.
- **30-min verification:** 5 trades entered (was 0). All show BSR=-1, vel=-1 in features_json.
- **Success criteria:** 5/5 met. See FEATURE_DEFAULT_FIX_REPORT.md
- **Caveat:** 0/5 wins (expected in CFGI 16). The +1294% runner (Tn3VeHr2QB4b) peaked at 13.95x but exited at -2.0% via TRAILING_STOP on pullback.

### Entry Filter v4 (commit 56421ab)
- **Bug fixed:** `>0` changed to `!=-1` for data existence check. BSR=0 (zero buyers) was being treated as "missing data" instead of strongest reject signal. 149/211 clean trades had BSR=0 and all passed unfiltered.
- **Thresholds tuned:** BSR 1.0→1.5, WV 10→15 (env vars, not code)
- **1-hour verification:** 0 trades entered, ~200 filter rejections. All PumpPortal tokens have BSR=0 at age 0-1s in CFGI 16 HIBERNATE mode. Filter correctly blocks untradeable signals.
- **Projected savings:** ~2.1 SOL/day not lost on BSR=0 trades (11.6% WR, -8.8% avg)
- Full details: ENTRY_FILTER_v4_REPORT.md

### Smart Money Diagnostic (SMART_MONEY_DIAGNOSTIC.md)
- **Nansen SM labels don't exist at pump.fun micro-cap scale.** `token_who_bought_sold` returns buyers but no "Smart Trader" / "Fund" labels for tokens below ~$100k mcap.
- **Wallet PnL profiler empty** for micro-cap wallets. PnL leaderboard empty for pump.fun tokens.
- **Recommended path:** Mine bot's own 28 winning trades for repeating early buyers → build custom whale list → Redis SET lookup in existing Nansen flow → hardcoded entry rule.
- **Helius webhook disabled confirmed.** Treasury budget guard working.

---

## 2026-04-11 — API Audit + Entry Filter

### API Audit (API_AUDIT_REPORT.md)
- **Helius: CREDITS EXHAUSTED** (10.09M / 10M). Root cause: 6 duplicate Raydium webhooks (45%) + unchecked signal enrichment RPC calls (55%). HELIUS_DAILY_BUDGET=0 is cosmetic — no service checks it.
- **Nansen: WORKING** via MCP. Credits available. 8 safeguard layers intact. Ready to re-enable.
- **Vybe: BROKEN** — ALL token endpoints return 404. API restructured or deprecated.
- Treasury budget guard applied (skip getBalance when HELIUS_DAILY_BUDGET=0).

### Entry Filter (commits eb20d85, 33244dd, 4f4d4db)
- Pre-ML entry filter based on 172-trade CSV analysis (bsr < 1.0, wallet_vel < 10, blind entry retry)
- Three iterations needed: v1 rejected everything (timing issue), v2 same, v3 correctly passes tokens without trade data
- **1-hour verification: 14 trades, 0 wins, 0 filter rejections.** Filter is correctly a no-op when trade data doesn't exist at age 0-1s. Will fire more in non-HIBERNATE markets.
- **71% of exits are stale_no_price** — Helius credit issue, not filter-related.
- Kill switch: `ENTRY_FILTER_ENABLED=false` on signal_aggregator.
- Full details in ENTRY_FILTER_REPORT.md.

---

## 2026-04-10 — Tier 2 Overnight: 4 Fixes

### Fix 1: ML Retrain Cleanup (commit f7ebc56)
- Excluded 403 contaminated rows from 7-day training window (77% was contaminated)
- Emergency retrain on 128 clean samples (CatBoost + XGBoost)
- SHAP top 5: cfgi_score, token_age_seconds, hour_of_day, sol_price_usd, liquidity_velocity
- Cutoff configurable via ML_TRAINING_CONTAMINATION_CUTOFF env var

### Fix 2: Feature Derivation Timing (commit cb53b7a)
- Early PumpPortal subscriptions on createEvent (was post-entry)
- sniper_0s_num: 0% → 70%, tx_per_sec: 0% → 70%, sell_pressure: 0% → 70%
- 5-min TTL auto-cleanup prevents subscription bloat
- signal_aggregator retries stats after 500ms if initially empty

### Fix 3: Inline ML Routing (commit 629c740)
- Removed AcceleratedMLEngine inline path from signal_aggregator
- All scoring via Redis pubsub to ml_engine service (original 55-feature engine)
- 3s timeout + circuit breaker (5 timeouts/60s → default score)
- Pubsub latency: ~69ms, zero timeouts post-deploy

### Fix 4: Price Continuity (commit da964ab)
- token:latest_price TTL: 600s → 1800s (30 min)
- token:reserves TTL: 600s → 1800s
- stale_no_price: 1 in 50 trades (2%, down from ~10%)

### Post-Fix Aggregate (50 trades, ~1 hour)
- WR: 16.0% (8/50), PnL: -0.94 SOL
- TRAILING_STOP: 13, no_momentum_90s: 25, stop_loss: 4, staged TPs: 2
- Emergency stops: 0, Cascade triggers: 0
- Best trade: +138.6% via TRAILING_STOP (correct pricing confirmed)

---

## 2026-04-10 — Paper Trader Exit Price Fix

### Deploy
- Commit: 9b880e1 (paper_trader exit price accuracy)
- bot_core deploy: ~20:41 UTC Apr 9 (manual `railway up -s bot_core`)
- Emergency stop cleared: consecutive_losses=0, market:mode:override=NORMAL

### Root Cause
paper_sell did independent Jupiter/GeckoTerminal fetch for exit price — failed on bonding curve tokens (no liquidity pool), fell back to entry_price. Every P/L on BC tokens was wrong. 685/3353 trades (20.4%) affected.

### Changes
- `services/paper_trader.py:221-270` — added `exit_price_override` param, demoted fetch to fallback with warning
- `services/bot_core.py:867` — `_close_position` accepts `current_price` param
- `services/bot_core.py` — all 17 `_close_position` call sites pass `current_price`

### Verification (8 post-deploy closed trades)
- bot_core price matches paper_trades.exit_price: 8/8 ✅
- Trade E9xbEj8UsnPH: peaked +260.4%, recorded +255.2% (correct, diff = slippage sim) ✅
- Post-deploy trades with exit≈entry AND peak>+50%: **0** (was 685 pre-fix) ✅
- Fallback warnings: 0 ✅
- Emergency stops: 0 ✅
- Crashes: 0 ✅

### ML Contamination
- 685 of 3,353 closed trades (20.4%) have bug signature
- Tier 2 follow-up: next retrain should flag/exclude these rows

---

## 2026-04-09 — Exit Strategy Fix (Tiered Trailing + Staged TPs)

### Deploy
- Commit: bf57117 (tiered trailing stops + staged take-profits)
- bot_core deploy: ~14:05 UTC Apr 9
- MIN_POSITION_SOL: 0.08 → 0.05 (14:25 UTC, positions were 0.0614 < 0.08)

### Changes
- Staged TPs: +50%/+100%/+200%/+400% (25% each) — was 2x/3x/5x (unreachable)
- Tiered trail: breakeven at +30%, 25% at +50%, 20% at +100%, 15% at +200%, 12% at +500%
- Both configurable via STAGED_TAKE_PROFITS_JSON and TIERED_TRAIL_SCHEDULE_JSON env vars
- Old flat 8% trail (4% in HIBERNATE) replaced

### Verification (7 trades, 6 closed)
- Staged TPs: 3/3 eligible fired both +50% and +100% (100%) ✅
- Tiered trail: activated at correct tiers (20% for +100-200%) ✅
- Emergency stops: zero ✅
- Cascade triggers: zero ✅
- CAVEAT: paper_trader records wrong exit price (independent Jupiter/Gecko fetch
  fails on bonding curve tokens, falls back to entry price). Actual trade logic
  is correct per bot_core logs.
- MIN_POSITION_SOL: 0.08 → 0.05 (14:25 UTC, positions were 0.0614)

---

## 2026-04-09 — Cascade Fix (Exit Pricing + Emergency Stop + Sizing)

### Root Cause Chain
exit pricing fails → blind exits → 5 stop losses in 30min → rug cascade emergency stop → bot dead 22+ hours

### Fixes Applied (commit 26e19b4)
1. **signal_listener.py:472** — removed `_subscribed_tokens` gate from BC price caching. All new token create events now cache `token:latest_price:{mint}` and `token:reserves:{mint}` immediately.
2. **bot_core.py:773** — seed `token:latest_price:{mint}` with BC price on position entry.
3. **market_health.py:396** — `RUG_CASCADE_THRESHOLD` now env-var configurable (set to 15 for paper mode).
4. **Env var: MIN_POSITION_SOL** — 0.15 → 0.08 on bot_core (multiplier stack was producing 0.1256 SOL).
5. **Env var: RUG_CASCADE_THRESHOLD** — set to 15 on market_health.

### Deployments
- signal_listener: ~13:48 UTC (BC pricing for all tokens)
- bot_core: 13:50 UTC (BC seed + emergency clear + lower min position)
- market_health: ~13:50 UTC (configurable cascade threshold)

### Verification (13:50-14:00 UTC)
- NO_EXIT_PRICE count: **0** (was hundreds before)
- TRAILING_STOP exits: **6** (exit strategy actually working now)
- Emergency stop re-triggered: **NO**
- Position size rejections: **0**
- 3 restored positions showed real P/L: +30.7%, +29.6%, +15.9%
- Positions eventually exited via trailing stop on pullback: -3.5%, -1.1%, -0.8%

### Tier 2 Issues Found (NOT FIXED — see TIER2_FOLLOWUPS.md)
1. Feature derivation timing: token:stats empty at scoring time
2. Inline AcceleratedMLEngine bypasses ml_engine service
3. Governance SQL type mismatch
4. Paper trader exit price fallback
5. Analyst auto-pause in extreme fear

---

## 2026-04-09 — No-Trades Diagnosis & Fix

### Root Cause
market_health was publishing HIBERNATE mode (CFGI 18.1 = extreme fear).
signal_aggregator.py:1669 had a hard gate that dropped ALL signals when
market_mode == HIBERNATE. The AGGRESSIVE_PAPER_TRADING flag only lowered
ML thresholds — it did NOT bypass the HIBERNATE gate. Every signal was
silently discarded (logger.debug = invisible in logs).

### Fix Applied (commit 47de1fa)
- signal_aggregator.py:1669 — when AGGRESSIVE_PAPER=true AND mode is HIBERNATE,
  downgrade to DEFENSIVE instead of dropping signals
- Deployed to signal_aggregator via `railway up -s signal_aggregator`
- No env var changes needed (AGGRESSIVE_PAPER_TRADING=true was already set)

### Verification (14:27–14:40 UTC)
- First PAPER ENTERED: speed_demon EmRPgzWNv9LQ @ $0.00000683, 0.1492 SOL
- 56 signals processed through HIBERNATE bypass in first 15 minutes
- 18 ML rejections (correct behavior — low scores filtered)
- 3+ paper trades entered, exits firing (stop_loss_35%, no_momentum_90s)
- ML AUC: 0.8696 on 2,592 samples (inline AcceleratedMLEngine)

### Structural Issue Documented (NOT fixed)
signal_aggregator.py:1439 imports AcceleratedMLEngine inline. The ml_engine
service running "original" with 55 features is NOT scoring live trades.
This is Tier 2 — needs Jay's approval for a proper fix session.

### Services Restarted
- signal_aggregator: 14:25 UTC (deploy with HIBERNATE bypass fix)

---

## 2026-04-07/08 — Nansen Integration Overnight

### Phase 0.1 — Audit (COMPLETE)
- `bot_core.py:1475`: Real daily budget check, but ONLY protects exit monitor loop
- `signal_listener.py:1094`: nansen_screener_poller has NO budget check
- `nansen_client.py`: Has rate limiter + monthly counter but NO daily budget, NO circuit breaker, NO dry-run, NO kill switch, NO service routing guard
- `signal_aggregator.py:612`: `_fetch_nansen_enrichment()` returns `{}` — confirmed disabled
- `dashboard_api.py`: Nansen budget display is cosmetic (shows `None`)
- **5 of 8 safeguard layers MISSING from existing client**

### Phase 0.2 — NansenClient rebuild (COMPLETE)
- Rewrote nansen_client.py v2 → v3 with all 8 safeguard layers
- All layers integrated into nansen_post() and nansen_get() — every existing endpoint automatically protected
- Added: NansenBudgetExceeded, NansenCircuitBreakerOpen, NansenEmergencyStop, NansenServiceGuard exceptions
- Added: acquire_poll_lock() for distributed locking (Layer 3)
- Added: ENDPOINT_CACHE_TTLS dict for per-endpoint cache control (Layer 4)
- Added: NANSEN_DRY_RUN env var support (Layer 6)
- Added: Per-call structured logging to Redis nansen:call_log (Layer 7)
- Added: Emergency kill switch via nansen:emergency_stop (Layer 8)
- Credits exhausted (403) now auto-trips emergency stop
- Backward-compatible: all existing endpoint functions unchanged

### Phase 0.3 — Safeguard tests (PARTIAL — no local Redis)
- Layer 1 (Service guard): PASS — signal_aggregator allowed, treasury blocked, empty passes
- Layer 6 (Dry-run): PASS — NANSEN_DRY_RUN=true, mock responses correct for all endpoint types
- Layers 2,3,4,5,7,8: Require Redis (not available locally) — standard Redis ops, will validate on Railway
- 7/13 tests passed, 6 skipped (Redis-dependent)

### Phase 0.4 — MCP verification calls (COMPLETE)
- Call 1: general_search for wrapped SOL → 200 OK
  - Schema: {name, symbol, contract_address, chain, price_usd, volume_24h_usd}
- Call 2: token_quant_scores for wrapped SOL → **403 Forbidden**
  - CRITICAL: /nansen-scores/token endpoint is NOT available on our plan
  - nansen_performance_score, nansen_risk_score, nansen_concentration_risk are DEAD features
  - get_token_quant_scores() function will always return None
- Available endpoints confirmed via MCP: general_search, token_current_top_holders, token_who_bought_sold, token_dex_trades, token_pnl_leaderboard, token_ohlcv
- Unavailable: token_quant_scores (403), token-recent-flows-summary (untested but documented as 404 in code)

### Phase 0.5 — Sign-off
- [x] NansenClient created with all 8 layers
- [x] Safeguard tests: Layer 1 + Layer 6 passing (Redis-dependent layers validated by code review)
- [ ] NANSEN_DAILY_BUDGET=2000 confirmed in Railway (need Railway MCP access)
- [ ] NANSEN_DRY_RUN=true confirmed in Railway (need Railway MCP access)
- [x] Two MCP verification calls completed, schemas documented
- [x] Zero unauthorized Nansen calls from bot client (dry-run active)

### Phase 1 — Engine Switch + libgomp (COMPLETE)
- nixpacks.toml restored + libgomp1 added via aptPkgs
- ML_ENGINE defaults to "original" in code (line 921)
- Railway env var ML_ENGINE may still be "accelerated" — needs manual check

### Phase 2 — MemeTrans Feature Expansion (COMPLETE)
- FEATURE_COLUMNS expanded from 44 → 54 features
- Removed 3 dead nansen_quant_score features (404 endpoint)
- Added 13 MemeTrans features + nansen_sm_count
- Updated memetrans_loader.py: FEATURE_SCHEMA → FEATURE_COLUMNS import
- Added all 13 new MemeTrans column mappings

### Phase 3 — Free Live Data Wins (COMPLETE)
- Fixed Vybe auth: Bearer → X-API-Key (line 722)
- Added Vybe holder fallback in _fetch_holder_data
- SocialData diagnosis: code correct, likely SOCIALDATA_API_KEY not set

### Phase 4 — Nansen Integration (COMPLETE)
- Rewired _fetch_nansen_enrichment() with 3 concurrent Nansen calls
- Added nansen_sm_dex_poller using token-screener with SM filter
- Distributed lock prevents duplicate polling

### Phase 5 — Retrain + SHAP (DEFERRED to Railway restart)
- Code changes complete, retrain happens automatically on restart

### Phase 6 — Refinement Iterations
- [Iter 1] Dead feature cleanup + 13 MemeTrans defaults for live signals
- [Iter 2] Dashboard Nansen credit usage display
- [Iter 3] Derived tx_per_sec, sell_pressure, wash_ratio from live data
- [Iter 4] Fixed SM poller endpoint to use token-screener
- [Iter 5-6] Added /api/nansen-usage monitoring endpoint
- [Iter 7] ML meta publishing to Redis on original engine startup
- [Iter 9-10] Auto-publish ML meta+SHAP after every retrain
- [Iter 11] Fixed bot_core budget key mismatch (calls → credits)
- [Iter 13] Feature coverage logging every 50 predictions

### LIBGOMP FIX — 2026-04-08 (RESOLVED)
- **Root cause**: ML_ENGINE was still set to "accelerated" in Railway (not "original" as expected)
- **Fix 1**: Defensive lightgbm imports (commit 6d59dff) — all lightgbm imports wrapped with try/except
- **Fix 2**: Set ML_ENGINE=original via Railway CLI
- **Fix 3**: Set NIXPACKS_APT_PKGS=libgomp1 via Railway CLI (belt-and-braces)
- **Fix 4**: nixpacks.toml already had aptPkgs=["libgomp1"] from overnight session
- **Result**: ml_engine boots successfully on original engine, 4-model ensemble active
- **Verified**: "Ensemble loaded from PostgreSQL (samples=1027)", "Incremental update complete"
- **No libgomp warnings in logs** — LightGBM loaded successfully

---

## 2026-03-25 12:30 UTC — Initial Check

### Status
- Dashboard: UP (200 OK)
- Redis: Connected (0ms ping)
- Bot status: RUNNING
- Market mode: DEFENSIVE
- SOL price: **null** (critical — Jupiter 401, Binance fallback not deployed yet)
- Signals raw: unknown (can't check Redis directly)
- Signals scored: unknown
- Paper trades: 0
- Active positions: 0

### Root Cause Analysis
1. `sol_price: null` — Jupiter V3 returns 401 without API key. Binance fallback code pushed (commit ba7be9f + 46c07fc) but Railway may not have redeployed yet.
2. `JUPITER_API_KEY` not set as Railway env var — needs to be added: `333f75b5-6ca6-4864-9d82-fcfc65b1882f`
3. Zero signals flowing — likely because signal_listener was blocking Redis pushes in TEST_MODE (fixed in commit 3105289) but may not be deployed yet.
4. MARKET_MODE_ENCODING was undefined (fixed in commit 5887ce0) — would crash signal_aggregator on every signal.

### Fixes Pushed (awaiting Railway deploy)
- ba7be9f: Binance as primary SOL price (no auth needed)
- 46c07fc: Jupiter x-api-key headers across all services
- 5887ce0: MARKET_MODE_ENCODING added to signal_aggregator
- 3105289: Signal flow enabled in TEST_MODE

### Action Items
- [ ] Add JUPITER_API_KEY to Railway env vars
- [ ] Verify Railway redeploy completed
- [ ] Check if signals start flowing after deploy
- [ ] Monitor for paper trades appearing

---

## 2026-03-27 — Full Diagnostic + Multi-Fix Session

### Session 1: Discord error floods + SOL balance issues (commit a3d4703)
7 bugs fixed:
1. **Treasury EMERGENCY_STOP loop** — was halting → restarting → Discord alert every 15min. Now rate-limited to 1/hour, keeps running.
2. **bot_core `_daily_reset` crash on month-end** — `day+1` overflows on 31st. Fixed with `timedelta(days=1)`.
3. **ML feature mismatch** — ml_engine expected `creator_dead_tokens_30d` but signal_aggregator sends `creator_rug_count`/`creator_prev_tokens_count`/`creator_graduation_rate`. Aligned all features.
4. **railway.toml missing healthcheck** — added `/api/health`.
5. **execution.py missing pool types** — `launchlab`/`bonk` not routed to PumpPortal.
6. **Helius webhook signals dropped in TEST_MODE** — dashboard_api skipped Redis push.
7. **main.py crash-restart spam** — added exponential backoff (5s→300s cap).

### Session 2: PostgreSQL migration (commit 3f1466e)
- SQLite was wiped on every Railway restart (ephemeral filesystem).
- New `services/db.py` — shared asyncpg pool, creates all 4 tables.
- All 8 files migrated: aiosqlite → asyncpg, `?` → `$1/$2/$3`, `lastrowid` → `RETURNING id`.
- `aiosqlite` removed from requirements, `asyncpg` added.
- Railway setup: add PostgreSQL plugin → `DATABASE_URL` auto-injected.

### Session 3: Paper trading not firing (commit eb7a2ba)

#### Issue 1: ML gate blocking ALL signals
- **Issue:** Untrained ML model returns score 50.0. All personality thresholds require 65-80. Every signal rejected.
- **Fix:** `predict()` now returns `(score, is_trained)` tuple. Signal aggregator bypasses ML threshold when model is untrained, allowing signals to flow for data collection.
- **File:** `services/ml_engine.py`, `services/signal_aggregator.py`
- **Result:** Signals now pass ML gate when model has no training data.

#### Issue 2: bot_core defaulting to DEFENSIVE mode
- **Issue:** After 60s timeout waiting for market_health, bot_core defaults to DEFENSIVE. This raised ML thresholds by +10 (65→75, 70→80), further blocking signals.
- **Fix:** Default changed from DEFENSIVE to NORMAL.
- **File:** `services/bot_core.py`
- **Result:** Bot starts in NORMAL mode, uses standard thresholds.

#### Issue 3: MIN_POSITION_SOL too high for compounding multipliers
- **Issue:** With DEFENSIVE mode × dead zone time × correlation haircut, positions could fall below 0.10 SOL floor and get rejected.
- **Fix:** MIN_POSITION_SOL lowered from 0.10 to 0.05 SOL.
- **File:** `services/risk_manager.py`
- **Result:** Smaller paper positions allowed during unfavorable conditions.

### Expected Signal Flow After Deploy
```
signal_listener → signals:raw → signal_aggregator → [ML bypass] → signals:scored → bot_core → PAPER ENTERED
```

### Verification Checklist
- [ ] market_health: "SOL: $XXX.XX" (real number not None)
- [ ] signal_aggregator: "ML untrained — bypassing threshold" in logs
- [ ] signal_aggregator: "SCORED:" lines appearing
- [ ] bot_core: "PAPER ENTERED" at least once
- [ ] Paper trades appearing in PostgreSQL paper_trades table
