# AGENT_CONTEXT — current bot state

**Last updated:** 2026-06-03 — **§B PHASES 0 + 1 + 2 COMPLETE (code + deploy-clean; live behaviour flip-confirmed-only). Phase-2 safety rails: #9 live-HIBERNATE-veto `7e83949`, #10 governance-cfgi-read `7fe2ad1`, #11+#12 live-startup-state (daily-loss reload + on-chain balance seed) `78cc45c`, #13 fill-MC fail-CLOSED `c70aba1` — all paper-safe (live-only/default-preserving), deploy-verified clean. 🚩 4 flagged: BUG-010 active (gov LLM dead → 0.8× paper haircut + no regime signal; #9's market:mode veto is the only live regime control; credits = go-live prereq), MAX_SD_POSITIONS=20 deployed-but-unread (`SIZING-CAPS-WIRING-001`), timezone/double time-of-day multiplier (`TIMEZONE-SIZING-FIX-001`), `GOVERNANCE-STALENESS-POLICY-001`. Phase 3 (accounting) NOT STARTED. **§B PHASES 0 + 1 COMPLETE (code + deploy-confirmed).** All 4 Phase-1 deploys came up clean (bot_core "ready" + trading paper after each; no import/Type/Syntax errors): #4+#8 `2a85508`, #6 `29fca1b`, #5+D02-F8 `09f71c1`, #7 `94457ef` — their *behaviour* is flip-confirmed-only (live `else:` branch not paper-observable), their *deployment* is confirmed clean. **END-TO-END VALIDATION:** bot now reads `market:health.mode: DEFENSIVE` (was warm-up HIBERNATE), `data_degraded: false`, dex $1.65B, `market:migration_count_1h` climbed 2→6→10 — correctly left HIBERNATE as the counter passed the DEFENSIVE threshold, proving the Phase-0 chain works end-to-end. **Current bot state: TEST_MODE=true (paper), 6 services Online, mode DEFENSIVE, trading paper normally, Redis timeouts largely cleared post-hardening, wallet 5.064 SOL unchanged.** **Remaining before any live flip: §B Phase 2 (safety rails) — #9 FIX-HIBERNATE-LIVE-VETO, #10 FIX-GOVERNANCE-FAIL-OPEN, #11 daily-loss persistence, #12 live-balance seed, #13 sizing-caps wiring; then Phase 3 (accounting: live staged-TP cumulative PnL, Path-B multi-exit, DASH-CORRECTED-PNL-COLUMN-001).** PC4 gated on Phase 2 + Phase 3. Paused at the Phase-1→Phase-2 boundary (Phase 2 = live-money safety gates). **§B Phase-1 #7 FIX-EXEC-001-002-ROUTING (CODE — `bot_core.py`):** **#7 (D02-F4 + D03-F3):** removed the `if pos.bonding_curve_progress > 0:` gate so `_check_pool_state_fresh` runs for EVERY live sell — fixes whale/Raydium bc=0 tokens (were 400'ing on the pump.fun path) AND reconciler-restored positions that lose bc_progress (stale pre-grad routing of graduated tokens). The helper returns 1.0 (BC closed → non-local/Jupiter) or 0.0 (BC live → pre-grad), so refresh always routes correctly regardless of stored/lost value (avoids a schema migration); fail-closed-to-stale on RPC error. EXEC-002 already resolved. py_compile PASS; 4/4 structural. **All four Phase-1 fixes done in code (#4+#8, #5+D02-F8, #6, #7); ALL flip-confirmed-only — they live in the `TEST_MODE=false` branch which does not execute in the current paper deployment, so runtime confirmation happens at the supervised first-live-trades.** **Deferred reliability follow-ups filed (not lost):** `SELL-STORM-PARK-PERSISTENCE-001` (D04-F10), `EXEC-FORCE-ABANDON-001` (D03-F8), `JITO-REIMPLEMENT-001`. **Remaining before flip: §B Phase 2 (safety rails) — #9 FIX-HIBERNATE-LIVE-VETO, #10 FIX-GOVERNANCE-FAIL-OPEN, #11 daily-loss persistence, #12 live-balance seed, #13 sizing-caps wiring; then Phase 3 (accounting: live staged-TP PnL, Path-B multi-exit, DASH-CORRECTED-PNL-COLUMN-001).** PC4 gated on Phase 2 + Phase 3. Prior: 2026-06-03 by §B Phase-1 #5 FIX-PARTIAL-SELL-SIZING + D02-F8 (CODE — `execution.py` + `bot_core.py`). **Staged-TP live sells no longer dump the whole position.** **D02-F5:** the pre-grad `_execute_pumpportal_local` SELL hardcoded `"amount":"100%"`, so every partial/staged-TP live sell (sell_pct 0.25/0.50/0.95) dumped the ENTIRE position → phantom remainder. **D02-F8 (done here, was #7 scope):** the Jupiter post-grad sell fetched + sold the FULL wallet balance. Fix: threaded `sell_fraction: float = 1.0` through `execute_trade` → both sell routes; `_close_position` passes `sell_fraction=sell_pct` (fraction of CURRENT on-chain balance, matching the multiplicative `remaining_pct *= (1-sell_pct)` semantics); pre-grad sends `"X%"` (e.g. "25%"), Jupiter sends `int(balance*sell_fraction)`. **Full closes (sell_pct=1.0) byte-for-byte unchanged (100%/full balance).** py_compile PASS; arithmetic 10/10 + 4/4 structural. **NOT paper-observable (live `else:` branch) — runtime-confirmed at the flip** (validate vs a multi-staged-TP live close). One lever. **§B Phase-1 remaining: ONLY #7 FIX-EXEC-001-002-ROUTING** (now smaller — D02-F8 done): refresh pool state for live sells (EXEC-001), persist/restore `bonding_curve_progress`/`pool_route` (D03-F3), force-abandon after N park cycles (D03-F8); EXEC-002 already resolved. Then Phase 2 (safety rails), Phase 3 (accounting incl. DASH-CORRECTED-PNL-COLUMN-001). Prior: 2026-06-03 by §B Phase-1 #6 FIX-BUY-IDEMPOTENCY (CODE — `services/execution.py`). **Stops live double-spend.** **D02-F3:** execute_trade's retry loop used to re-broadcast the same tx on a confirmation miss (double-spend on a buy that landed). New `_get_signature_status()` helper (`getSignatureStatuses`, 3-tier Helius RPC → landed/failed/unknown); on a confirm-miss execute_trade now polls on-chain status and decides: **landed → success (no resubmit); failed → resubmit (genuinely didn't execute); BUY-unknown → record-pending WITH the sig (never double-buy — reconcile/Path-B/_check_exits resolve it); SELL-unknown → failure (caller #4 parks + retries, no maybe-unlanded close booked).** **D02-F2/F7:** forced `use_jito=False` — the Jito bundle path returns the bundle UUID (not a tx sig → broke confirmation + Path B + fed the double-submit) and adds no tip (never lands) → now uses real-sig `_send_transaction` (local RPC, 3-tier). `JITO-REIMPLEMENT-001` follow-up filed (real-sig extraction + tip transfer). **D02-F14:** `_confirm_trade_helius` unset-parse-URL → `confirmed=False` (verify via getSignatureStatuses) not blind-`True` (env-verified: `HELIUS_PARSE_TX_URL` IS set on bot_core, so this was latent). py_compile PASS; `.tmp_phase1/verify_idempotency.py` 6/6 (helper unit-tested via mocked RPC) + 9/9 structural + review. **NOT paper-observable (live `else:` branch) — runtime-confirmed at the supervised flip.** One lever (execution.py only). **§B Phase-1 remaining: #7 FIX-EXEC-001-002-ROUTING** (refresh pool state for live sells, persist `bonding_curve_progress`/`pool_route`, AND include D02-F8 Jupiter partial-sizing so enabling a working Jupiter sell path doesn't reintroduce the full-bag dump). Then Phase 2 (safety rails), Phase 3 (accounting incl. DASH-CORRECTED-PNL-COLUMN-001). Prior: 2026-06-03 by §B Phase-1 #4+#8 MERGED (CODE — `services/bot_core.py`). **First live-execution-correctness fix; §B Phase 1 underway.** **#4 FIX-LIVE-SELL-RESULT-CHECK (D02-F1):** `execute_trade` returns `success=False` on failure (never raises) → the old `except ExecutionError` was dead code → a failed LIVE sell was **booked as a successful close** (SOL stranded on-chain, fabricated oracle PnL, position popped + never retried). Now a `if not result.success:` check (+ the except guard) calls a shared `_handle_failed_live_sell()` (park-and-continue, **never raises**) that increments the sell-storm counter, parks past `SELL_FAIL_THRESHOLD`, records, and returns WITHOUT booking/decrementing/popping → the position stays OPEN for `_check_exits` retry. Protects partial/staged-TP sells. **#8 FIX-EMERGENCY-STOP-ROBUSTNESS (D03-F1/D04-F8):** emergency_stop guards each `_close_position` (one un-sellable mint can't abort the stop), detects left-open via `key in self.positions`, sets the **durable Redis `bot:emergency_stop` kill key**, and always runs the Discord alert + `bot:status` publish (reports `positions_failed`). **Merged** because #4's failure semantics (park-and-continue, no raise) are what make #8's loop safe. py_compile PASS; `.tmp_phase1/verify_phase1_4_8.py` 10/10 PASS. **CANNOT be paper-observed** — this is the live (`TEST_MODE=false`) `else:` branch which does not execute in the current paper deployment; **runtime confirmation deferred to the supervised first-live-trades at the flip.** Deploy bar = bot_core comes up clean (no startup error). One lever (bot_core only; paper branch untouched; D04-F10 park-persistence deferred — less acute post-crash-loop-fix). **§B Phase-1 remaining before flip: #6 FIX-BUY-IDEMPOTENCY (double-submit guard + verify `HELIUS_PARSE_TX_URL` set + Jito), #7 FIX-EXEC-001-002-ROUTING (incl. D02-F8 Jupiter partial-sizing).** Then Phase 2 (safety rails), Phase 3 (accounting incl. DASH-CORRECTED-PNL-COLUMN-001). Prior: 2026-06-03 by DEPLOY-OBSERVABILITY (CODE — §B Phase-0 #3) — **§B PHASE 0 COMPLETE.** Bot is recovered + hardened + observable. **DEPLOY-OBSERVABILITY `51ed450`:** a crashed internal service is now VISIBLE + ALERTED (D12-F2/F3/F4 — the gap that made the 05-28 outage silent). Folded liveness checks into the existing `web` `_service_health_checker` (no new billable Railway worker): `dashboard_api.py` adds internal-service rows to `service:health` (bot_core via `service:bot_core:heartbeat`+`bot:status`, signal_aggregator via `signal_aggregator:health`, signal_listener via `signals:raw` proxy, market_health via `market:health` proxy; TTL'd keys → absence==down) + a rate-limited (30min) Discord down-alert; `dashboard-analytics.html` gains a "ZMN Services" health section. py_compile PASS; liveness keys verified present; HTML/JS aligned (dashboard visual not render-tested — Playwright gated on OBS-004). **REDIS-CLIENT-HARDENING-001 runtime-confirmed** (`2337565`): bot_core supervise-restarts=0 (safety listeners stable), `market:migration_count_1h` climbing 2→6 (increments landing), pipeline flowing; HIBERNATE persists as warm-up (counter filling). **§B Phase-0 status: #1 pubsub-isolation+leak-hotfix ✅, #2 market-mode ✅, #2.5 redis-hardening ✅, #3 observability ✅ — DONE.** Next before any live flip: §B Phase 1 (live-execution correctness — D02-F1 failed-sell-booked-as-closed, D02-F3 buy-double-submit, D02-F5 partial-sell-dumps-whole-bag, D03-F1 emergency-stop), Phase 2 (safety rails), Phase 3 (accounting). Open Phase-0 follow-ups: MARKET-MODE-THRESHOLD-RECALIBRATE-003 (≥1h steady-state counter), stronger-watchdog (continuous_audit.py as own service). PC4 gated on Phases 1-3. Prior: 2026-06-03 by REDIS-CLIENT-HARDENING-001 (CODE — Phase-0 reliability, prod-surfaced). **REDIS-CLIENT-HARDENING-001 `b72fac2`:** added `socket_keepalive=True, health_check_interval=30, retry_on_timeout=True` to ALL 15 `aioredis.from_url(...)` call sites across 11 service files. Prompted by prod observation: `market:health` showed `dex_volume_24h=$1.65B` healthy + `market:migration_count_1h=2` → HIBERNATE — the FIX-MARKET-MODE-MISCLASSIFICATION fix CORRECTLY enforced a PRESENT-but-low counter (`data_degraded=false`); the low 2/hr is a post-restart warm-up + Redis-timeout-dropped-increment artifact. The persistent `Timeout reading from redis.railway.internal:6379` (~6s) is environmental Railway-Redis slowness dropping counter increments/reads + churning the safety pubsub listeners (60s backoff); the hardening kwargs (health_check reconnects proxy-dropped conns, retry_on_timeout retries transient reads, keepalive holds idle conns) target it. Verified construct-safe on redis-py 7.4.0 before editing (all-services change); py_compile 11/11 PASS. **NEW `MARKET-MODE-THRESHOLD-RECALIBRATE-003` (🟡):** once a clean hour of counter data exists, verify capture-rate vs MARKET_MODES thresholds + consider warm-up bypass / Postgres-backed count. **Bot state:** RECOVERED — all 6 services ● Online, crash-loop resolved, paper trades flowing (mode HIBERNATE→DEFENSIVE via AGGRESSIVE_PAPER; live HIBERNATE veto is Phase-2 #9). **§B Phase-0:** #1 DONE, #2 deployed, #2.5 REDIS-CLIENT-HARDENING deployed (observe pending), then #3 DEPLOY-OBSERVABILITY. PC4 gated on Phase-0 + Phases 1-3. Prior: 2026-06-03 by FIX-MARKET-MODE-MISCLASSIFICATION (CODE — §B Phase-0 #2) + FIX-PUBSUB-ISOLATION runtime confirmation. **BOT RECOVERED:** prod observation confirms the pubsub fixes (`98c8007` + leak-hotfix `9fa45b0`) worked — all 6 services ● Online, the 05-28 crash-loop is RESOLVED, `MaxConnectionsError` gone, pipeline flowing, paper trades entering; `supervise` verified catching the exact redis `TimeoutError` in prod. (Round-2 hotfix `9fa45b0` fixed a connection leak the supervise-restart exposed in 3 listeners lacking `finally: aclose()`.) **FIX-MARKET-MODE-MISCLASSIFICATION `5a3e5aa`** (`services/market_health.py` only): `_determine_market_mode` no longer conflates missing-data with dead-market — an absent `market:migration_count_1h` → `None` ABSTAINS (not veto; distinguished from genuine 0 via `is not None`), `_fetch_defillama` returns `None`+last-good (not `0.0`), the fabricated `pumpfun_vol=0.15*dex_vol` placeholder is dropped from the binding decision (kept as labelled estimate), total-data-loss → DEFENSIVE not HIBERNATE, + a `data_degraded` flag; supersedes MARKET-MODE-001-RE-CALIBRATE-002. 10/10 classifier tests PASS (incl. $1.75B-dex+absent-counter → NORMAL). **NEW `REDIS-CLIENT-HARDENING-001` (🟡 Phase-0, prod-observed):** persistent `Timeout reading from redis.railway.internal:6379` (~6s) is environmental Railway-Redis slowness the resilience fix tolerates but doesn't cure (safety listeners back off to 60s); harden `aioredis.from_url` with keepalive/health_check/retry_on_timeout before live. **§B Phase-0 status:** #1 DONE+confirmed, #2 deployed (observe pending), then REDIS-CLIENT-HARDENING-001, then #3 DEPLOY-OBSERVABILITY. PC4 still gated on Phase-0 completion + Phases 1-3. Prior: 2026-06-03 by FIX-PUBSUB-ISOLATION (CODE change — FULL-CODE-AUDIT-001 §B Phase-0 #1; restores the crash-looped bot). **FIX-PUBSUB-ISOLATION:** NEW `services/async_utils.py` `supervise(coro_factory, name)` — a supervised-restart wrapper now wrapping every member of all 7 service top-level `asyncio.gather`s (signal_listener, bot_core, ml_engine ×2-engine, signal_aggregator, market_health, governance) + the dashboard background tasks; `main.py` single-service entrypoint now routes through the existing `run_service()` supervisor (was a bare `await mod.main()`). A crashing task (e.g. a transient redis pubsub `TimeoutError` escaping an unguarded `async for pubsub.listen()`) now restarts with capped exponential backoff while siblings keep running — restart re-subscribes (self-healing), CancelledError still propagates (clean shutdown), clean return does NOT hot-loop. Fixes D01-F1/F2/F3/F4/F5/F6 + D12-F5; resolves PIPELINE-PUBSUB-ISOLATION-001 + BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001 in code. **Deploy:** single `git push` → Railway auto-redeploys ALL services (the fix touches all; bot already down → simultaneous restore intended). **Verification:** py_compile 9/9 PASS; `.tmp_pubsub_fix/verify_pubsub_isolation.py` 25/25 PASS (behavioral + structural). **NOT runtime-verified against live Railway yet** — deploy observation pending (expect bot_core + signal_listener RUNNING not CRASHED). Rollback: `git revert 98c8007` + push. **One lever only:** no trading-logic change; the co-located Redis-URL-password log (D10-F1, `market_health.py:543`) deliberately left for FIX-SECRET-LOGGING. Wallet not re-verified (no on-chain activity; predecessor 5.064 SOL). PC4 still gated on §B Phase-0 #2 (market-mode) + #3 (observability) + Phases 1-3. Scratch `.tmp_pubsub_fix/`. Prior: 2026-06-03 by FULL-CODE-AUDIT-001 (read-only comprehensive pre-flip codebase audit; ZERO state writes — no env/Redis/DB/override/redeploy beyond the docs-push auto-deploy). **FULL-CODE-AUDIT-001:** systematic 12-dimension audit of the whole codebase (Opus 4.8 + multi-agent workflow: recon→12 dims→adversarial verify), hunting every defect that can lose money, hang a position, crash a process, or make accounting lie before the real-capital flip. **~90 findings; post-verification: 🔴 14 · 🟠 ~33 · 🟡 ~26 · 🟢 ~17.** Two reassuring NON-findings (verified): **(a) TEST_MODE money-path gating is correct, defense-in-depth — no real on-chain send can fire in paper mode**; **(b) the wallet private key is not leaked anywhere in code** (empirically verified, repr(Keypair) redacts the seed). **Headline NEW blocker cluster (execution path, masked because the only validated live trade id 6580 was a single full round-trip):** (1) **D02-F1** failed live sells are booked as successful closes — `execute_trade` returns `success=False` (never raises) so the `except ExecutionError` at `bot_core.py:1366` is dead code and `result.success` is never checked on the sell path → SOL stranded, accounting falsified, position popped & never retried; (2) **D02-F5** the pre-grad `_execute_pumpportal_local` SELL hardcodes `"amount":"100%"` → **every partial/staged-TP live sell dumps the entire position**; (3) **D02-F3** buy double-submit on a confirmation timeout (no idempotency); (4) **D03-F1** emergency_stop has no per-position guard → unreliable in the mass-dump it exists for. **CONFIRMS+EXTENDS the active outage** (`PIPELINE-PUBSUB-ISOLATION-001`): the pubsub-crash class is in **5 services not 2** (ml_engine/governance/dashboard added), all 6 top-level gathers omit `return_exceptions=True`, AND the single-service `main.py` entrypoint has **no supervised restart** (the resilient `run_service()` is wired only to dead legacy mode) — the second structural amplifier. **Outage is invisible:** heartbeat keys have **zero readers**, the dashboard health surface has **no internal-service rows**, and the only liveness alerter (`continuous_audit.py`) is **undeployed** — the proximate reason the ~05-28 outage went silent. **Safety fail-opens confirmed:** governance veto (BUG-010), AGGRESSIVE_PAPER HIBERNATE bypass → live-trades-in-HIBERNATE, daily-loss accumulator zeroed on every restart, `MAX_SD_POSITIONS` a phantom env var (real cap hardcoded 3, V5A 5/7 ladder unenforceable), dead `market:loss_override` (3 writers/0 readers). **Pre-flip remediation sequence is §B of the audit** — Phase 0 (restore: pubsub-isolation + market-mode + observability), Phase 1 (live-execution correctness), Phase 2 (safety rails), Phase 3 (accounting) must all be GREEN before `TEST_MODE=false`. Audit: `docs/audits/FULL_CODE_AUDIT_001_2026_06_02.md`; scratch `.tmp_full_audit/`. **PC4 stays `[ ]`; the flip is now gated on the §B Phase-0..3 fix-sessions, each its own verified session.** Prior: 2026-06-02 by MARKET-REGIME-DIAGNOSTIC-001 (read-only; resolves the V3R HIBERNATE verdict — the predecessor's "broad memecoin lull" interpretation is REFUTED). **MARKET-REGIME-DIAGNOSTIC-001 (read-only investigation; ZERO state writes — no env/Redis/DB/override/redeploy beyond the docs-push auto-deploy):** The HIBERNATE that halted the V3R flip is a **PIPELINE OUTAGE misclassified as a market lull**, not a real lull. All 6 sub-verdicts survived adversarial verification (conf 0.88-0.95): **(Q1) HIBERNATE-MISCLASSIFIED** — `market_health._determine_market_mode` (L281) ANDs 3 legs; live `dex_vol=$1.753B` clears NORMAL and `pumpfun_vol=$263M` (=`dex×0.15` placeholder, `market_health.py:390`) clears AGGRESSIVE, but `grad_rate=0` (Redis `market:migration_count_1h` ABSENT) single-leg-vetoes to HIBERNATE. **(Q2) LIVE-TRADES-IN-HIBERNATE** — the only HIBERNATE skip is `signal_aggregator.py:1741`, gated on `AGGRESSIVE_PAPER` (NOT TEST_MODE); `bot_core.process_signal` has NO independent HIBERNATE skip; a bot_core-only flip leaves the aggregator bypassing → **live would trade in HIBERNATE** (refutes "flip is inert"), and the flip's own redeploy would revive the CRASHED bot_core into live mode. Both services `AGGRESSIVE_PAPER_TRADING=true`. **(Q3)** bypass configured-active now (id 10926 traded 06-02 12:47Z in HIBERNATE, labeled `DEFENSIVE`) but starved to ~1 trade/24h. **(Q4) VALIDATION-WAS-TRADEABLE-REGIME** — the +8.91 SOL/day, 91.9% WR window (2026-05-20..28, n=1066) ran genuine NORMAL(830)/DEFENSIVE(236)/HIBERNATE(0); `portfolio_snapshots` NORMAL 1747 / DEFENSIVE 691 / HIBERNATE 0 → **PC2 NOT re-opened** (cost-fidelity gap still applies separately; even full Path-B 24.3% cost-correction leaves +32.5 SOL / 76.7% WR). **(Q5) FLOW-DEGRADED** — `signal_listener` AND `bot_core` BOTH in **CRASHED** Railway state, crash-looping ~6.7s on `redis.TimeoutError` in pubsub `.listen()` via unguarded `asyncio.gather` (`signal_listener.py:335`/`1395`; bot_core ~`L2410`); 3 external sources (conf 0.8-0.9): pump.fun launching ~1,500-2,000/hr + graduations ~350/day, so the bot feed (~64/hr) captures ~3% of reality; bot effectively **DOWN since ~2026-05-28T13:00Z** (zero trades 05-29..06-01; `portfolio_snapshots` stop 05-28T12:57 — the 5-min heartbeat task is unconditional, so ~1,150 missing = process non-functionality, not a lull). **VERDICT: PATH C (misclassified) + PATH D (flow degraded), one root cause; the system is DOWN, not hibernating — DO NOT flip into a broken pipeline.** The V3R NO-FLIP was correct but its *reason* ("wait for market") was wrong. Recommended next session **`PIPELINE-PUBSUB-ISOLATION-001`** (promote+extend `BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001` to a Tier-1 flip-blocker covering signal_listener + bot_core). Wallet not re-verified (read-only; predecessor 5.064095633 SOL; no on-chain activity). **PC4 stays `[ ]`.** NEW standing finding `docs/findings/MARKET_REGIME_GAP.md`; audit `docs/audits/MARKET_REGIME_DIAGNOSTIC_001_2026_06_02.md`; scratch `.tmp_market_regime/`. Prior: V5A-FLIP-002-V3R + a same-day RAILWAY-CLI-UPGRADE follow-on. **Follow-on (CLI):** Railway CLI upgraded 4.6.0 → 4.66.0 → `list-deployments` now works → **deploy-SHA carry-forward RESOLVED**: bot_core's active deployment is `39b44e7` (descendant of `7458f2d`), so all three V5A fixes (`f3591eb`/`3c50520`/`7458f2d`) are confirmed RUNNING in production (`bot:status=RUNNING test_mode=true HIBERNATE`; heartbeat alive). NEW Tier-2 follow-up `BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001` (not V5A-blocking): a transient `redis.TimeoutError` in `_emergency_listener` (`bot_core.py:2067`) crashed deployment `298833d` via unguarded `asyncio.gather` (`bot_core.py:2410`); follow-up `39b44e7` self-recovered. Isolate the listener before the next flip so a Redis blip can't abort the flip restart. **Session (the flip):** V5A-FLIP-002-V3R (read-only preflight; ⛔ **NO-FLIP — HALTED at Phase 1 on STOP-M**). The authorized V5A live-flip session ran its full read-only preflight and halted at the market-regime gate before any state write: `market:mode:current=HIBERNATE` (cfgi 34.0, sentiment 22.5, SOL $78.84) **plus** a near-dead signal pipeline (`market:new_token_count_1h=14`, was 10,257 on 2026-05-20; pumpportal "no signals") — two independent STOP-M triggers. Per D-S4 (binding), HIBERNATE aborts. **Zero state writes: TEST_MODE stayed `true`, sizing stayed 4.0/0.25/20 (the Phase 2 reconcile to 1.5/0.10/5 was never reached), no Redis/Postgres writes, no redeploy.** **Wallet 5.064095633 SOL on-chain, unchanged** (Helius `getBalance`, exact; cross-checked `bot:onchain:balance`). Everything-else-GO: Railway authed; commits `f3591eb`/`3c50520`/`7458f2d` all ancestors of HEAD `7d33994` (local==origin); all 3 fixes present in source; Path B engine intact (id 6580 on-chain native delta −374,251,786 lamports, exact); orphan baseline clean (`trades` live-open = 0 — the May-20 vector is clear); sell-storm default 8. **One open tooling item:** Railway CLI is v4.6.0 → `list-deployments` unsupported (needs ≥4.10.0), so the running-container SHA for `7458f2d` remains **UNCONFIRMED since 2026-05-28**; Phase 1.5 forced-redeploy fail-safe not triggered because the flip was halted on STOP-M. **NOT STOP-Rollback** (no failed flip — re-attemptable in the next non-HIBERNATE window under the same authorization framework). **PC4 stays `[ ]` outstanding.** §1 mode + §2 env tables unchanged this session. Audit: `docs/audits/V5A_FLIP_002_V3R_2026_06_02.md`; scratch `.tmp_v5a_flip_v3r/`. Prior: LIVE-FEE-CAPTURE-ENTRY-SIG-WIRING-001 (code-yes + deploy-yes; **1 FIX DEPLOYED — V5A-FIXES-001 §11 follow-up `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` RESOLVED**). Single-commit single-file fix (`services/bot_core.py` +9 LOC, 0 deletions) commit `7458f2d`: adds `entry_signature: str | None = None` to the Position dataclass (default-None covers paper entries + reconciler-restored Positions + buy results lacking signature attr — all fail-safe paths the close-path already handles) and wires `entry_signature=getattr(result, "signature", None)` at the live-entry Position construction site (`bot_core.py:1005`), mirroring the existing exit_signature mechanism (`_pt_exit_sig = getattr(result, "signature", None)` at L1434). Adds observability log `[ENTRY_SIG] captured entry_signature=<first 8>... for <personality> position (mint=<first 12>)` when populated. **Impact:** close-path Path B parser at L1450 (`helius_parse_signature(pos.entry_signature)`) now receives a real signature on live closes, producing `correction_method='live_actual_v1'` instead of `'live_estimated_v1'`. Tonight's V5A-FLIP-002-V3 live trades will count toward `PAPER-FEE-MODEL-CALIBRATION-001` ≥10-row Path B prereq. **Paper mode byte-for-byte unchanged** (paper Position at L903 doesn't pass kwarg → entry_signature stays default None → close path's existing `if getattr(pos, "entry_signature", None)` guard at L1450 skips entry parse exactly as today). **Q1-Q5 investigation answers:** (Q1) exit_signature template works; (Q2) `execute_trade` returns ExecutionResult.signature synchronously across all 3 routes — NOT STOP-Async; (Q3) Position constructed at L1005 with result.signature already in scope (used at L1061 INSERT $8 + L1090 ENTERED log); (Q4) close path reads in-memory pos.entry_signature at L1450 (DB column was already populated at INSERT L1061; fix is purely in-memory wiring); (Q5) live reconciler reads `trades` table at L309 which has no entry_signature column → mid-position restart loses sig → close falls back to live_estimated_v1 (known limitation, acceptable per session prompt §3 Q5; schema migration would be STOP-Scope; future enhancement out of scope: reconciler lookup of paper_trades.entry_signature by mint+open match). **Verify 17/17 PASS** (`.tmp_entrysig/verify_entrysig.py`): source assertions (entry_signature field present, live-entry kwarg wired, exit_signature template untouched, Path B reference unchanged, paper-entry regression-safe, reconciler unchanged, [ENTRY_SIG] log present); dataclass unit tests (Position(entry_signature='testSig123') sets field, Position() default is None); mock ExecutionResult fail-safe (getattr extracts present sig, defaults None on absent attr — no exception); Path B dry-run on id 6580 (entry_signature retrievable from DB; helius_parse_signature returns dict; `success=True` with `native_delta_lamports=-374251786` — confirms downstream consumer works end-to-end when given a real sig). **STOPs evaluated, none critical fired:** A/D/H/Z/Async/Investigate/Scope/Verify/Loop/L/Claude all clear. **STOP-J inconclusive at session end** — `railway logs -s <any_service>` returned `No deployments found` for bot_core AND ml_engine AND signal_listener (CLI 4.6.0 quirk, NOT bot-specific); `bot:filter:fill_mc_ceiling:rejects:2026-05-28=1982` confirms bot active today; `service:health` (written by market_health every ~53s) fresh — confirms cluster alive; commit confirmed on `origin/main`. Deploy verification flagged in STATUS active-blockers for next-session resolution; behavioral verification of the fix happens at V5A-FLIP-002-V3 Phase 10.5 first live close (must produce `live_actual_v1`; if `live_estimated_v1`, do NOT auto-rollback on this alone — profitability unaffected, calibration data quality is the only impact). **Wallet UNCHANGED 5.064 SOL on-chain** (not re-verified — no on-chain activity expected this session, none occurred). **Bot state at session end:** TEST_MODE=true paper (unchanged); MAX_POSITION_SOL=0.25; MAX_SD_POSITIONS=20; DAILY_LOSS_LIMIT_SOL=4.0; BOT_CORE_FILL_MC_CEILING_USD=1000; ML_THRESHOLD_BOT_CORE_SD=40. PC1/PC2/PC3 satisfied; **PC4 (V5A flip itself) remains the only outstanding V5A blocker**, Jay-authorization-gated for next D-S5 window. **V5A-FIXES-001 §11 follow-up `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` MOVES FROM 📋 Tier 3 → ✅ RESOLVED.** Remaining 3 Tier 3 follow-ups from V5A-FIXES-001 unchanged (PORTFOLIO-SNAPSHOT-MODE-FILTER-001, HEARTBEAT-EMERGENCY-STOP-REFLECTION-001, PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001). **Scope discipline:** NO TEST_MODE change; NO env change; NO exit_signature mechanism modification (mirrored as template only); NO schema migration; NO other service touched; NO Redis writes; NO DB writes. Audit: `docs/audits/LIVE_FEE_CAPTURE_ENTRY_SIG_WIRING_001_2026_05_27.md`. Scratch: `.tmp_entrysig/`. **Prior:** V5A-FIXES-001 (overnight autonomous; code-yes + DB-yes + deploy-yes; **3 FIXES DEPLOYED + 1 CLOSED-AS-NON-BUG + 14 PHANTOM ROWS TAGGED**). Executes the 3 follow-ups filed by V5A-FLIP-001-V2 rollback + the cleanup. (1) **Bug 1 / V5A-FLIP-RECONCILE-FILTER-001** ✅ DEPLOYED commit `f3591eb` 2026-05-21 ~14:42Z — `mode_clause` in `_reconcile_positions` (line 249) + `_load_state` (line 308) now applies trade_mode filter to BOTH `paper_trades` AND `trades`; previously only `paper_trades`. Root cause was different from filed description: the live-mode reconciler reads `trades` (paper+live ML corpus per LIVE-TRADES-LOGGING-AUDIT-001), where the `if table == "paper_trades"` guard left no filter. Open paper rows accumulate in `trades` when `pos.trades_ml_id` is falsy → `_close_position:1247-1257` skips `UPDATE trades SET closed_at=...`. Phase 1 investigation resolved V5A-FLIP-001-V2 audit §5 puzzle: the 09:55:28Z `paper_trades WHERE entry_time IS NOT NULL AND exit_time IS NULL`=0 query was on the WRONG table; the reconciler reads `trades`, where 14 rows were open. Verified live 14:42:26Z: new `[RECONCILE] mode=paper, table=paper_trades, loaded 0 position(s)` log line + `Bot Core ready`, no errors. (2) **Bug 2 / V5A-FLIP-CLOSE-TRADE-MODE-001** ✅ DEPLOYED commit `3c50520` 2026-05-21 ~15:05Z — defensive-INSERT `trade_mode` now derived from `trades.trade_mode` lookup (was hardcoded `'live'`). Plan's Option A (entry_signature discriminator) was infeasible — Position dataclass has no entry_signature field (filed Tier 3 `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` for the latent Path B bug surfaced). Adopted Option C (DB lookup): `SELECT trade_mode FROM trades WHERE id = pos.trade_id`; defaults to `'live'` on lookup failure. + `[ORIGIN_MISMATCH]` WARNING log if paper-origin position reaches the live close path. ~30 LOC in single file. Verified: all 14 V5A-FLIP-001-V2 incident trade_ids would return `'paper'` under the fix (defense-in-depth against Bug 1 regression). (3) **Bug 3 / BOT-CORE-EMERGENCY-STOP-LIVENESS-001** ✅ CLOSED-AS-NON-BUG — investigation found per-decision `bot:emergency_stop` Redis check ALREADY EXISTS at `services/bot_core.py:604-609` inside `process_signal`. V5A-FLIP-001-V2 audit's "Phase 5 finding" misinterpretation: heartbeat.emergency (in-memory) was conflated with the per-decision check; 14 phantoms had entry_time 2026-05-12..2026-05-19 (DAYS before incident, not new positions during 9-min drain). Filed observability follow-up `HEARTBEAT-EMERGENCY-STOP-REFLECTION-001` Tier 3 — surface Redis flag in heartbeat. (4) **V5A-FLIP-CONTAMINATION-CLEANUP-001** ✅ DONE — `UPDATE paper_trades SET correction_method='paper_orphan_at_flip_v5a_001', correction_applied_at='2026-05-21T14:31:14Z' WHERE id BETWEEN 9940 AND 9953 AND trade_mode='live' AND entry_signature IS NULL AND exit_signature IS NULL AND correction_method IS NULL`. 14 rows affected. id 6580 (`live_actual_v1`, the real on-chain live trade) verified unchanged. Live-mode analytics can now filter phantoms via `WHERE correction_method NOT LIKE 'paper_orphan%' OR correction_method IS NULL`. **Wallet UNCHANGED throughout: 5.064095633 SOL on-chain** (verified Helius `getBalance` Phase 0; no on-chain activity expected, none occurred). **Bot state at session end:** TEST_MODE=true paper (unchanged); MAX_POSITION_SOL=0.25; MAX_SD_POSITIONS=20; DAILY_LOSS_LIMIT_SOL=4.0 (baseline post-V5A-FLIP-001-V2 rollback); BOT_CORE_FILL_MC_CEILING_USD=1000; ML_THRESHOLD_BOT_CORE_SD=40; 3 paper open positions trading normally; bot:emergency_stop absent; bot:consecutive_losses=0. **Two clean Railway auto-deploys** (Phase 3 ready 14:42:26Z; Phase 6 ready ~15:05Z). PC1/PC2/PC3 satisfied; **PC4 (V5A flip itself) remains the only outstanding V5A blocker**, Jay-authorization-gated for next D-S5 window. **V5A-FLIP-002 is now structurally unblocked** from this session's deliverables. V5A-FLIP-002-V3 prep notes at `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md` capture 7 deltas vs V2 for chat-side prompt assembly. **4 new Tier 3 follow-ups filed** (all non-blocking): PORTFOLIO-SNAPSHOT-MODE-FILTER-001, LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001, HEARTBEAT-EMERGENCY-STOP-REFLECTION-001, PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001. **All STOPs evaluated, none critical fired:** A/A2/D/H/Z/INV1-3/CLEAN1-2/Scope1-5/Verify3-4/J3/Verify3-Post/J6/Loop/L/Claude all clear. **Scope discipline:** NO env changes (no TEST_MODE / no sizing); NO touch of other services; NO touch of trades table (only paper_trades cleanup); NO modification of id 6580; NO investigation of out-of-scope items (BUG-010 / VYBE drift / DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001). Audit: `docs/audits/V5A_FIXES_001_2026_05_21.md` (11 sections); Phase 1 investigation: `docs/audits/ORPHAN_PAPER_CLOSURE_INVESTIGATION_001_2026_05_21.md`; V3 prep: `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md`. Scratch: `.tmp_v5a_fixes/`. Prior: V5A-FLIP-001-V2 (env-yes + Redis-yes + deploy-yes; **FLIP ATTEMPTED → ROLLED BACK after Phase 8 failure**). At ~10:00:05 UTC TEST_MODE=false was set on bot_core; live container started ~10:04:11 UTC. Phase 8 failed at the first verification step — `Startup reconciliation: 14 open positions in DB` (not 0). The 14 phantom positions were pre-existing rows in `paper_trades` with `entry_time IS NOT NULL AND exit_time IS NULL` that the audit query at 09:55:28 UTC reported as 0 (suggests query-vs-reconcile-filter mismatch — root-cause vector). The live container reclassified them as `trade_mode='live'` and closed them in-memory at synthetic losses (entry_signature + exit_signature BOTH NULL — **no on-chain transactions ever fired**). Cumulative -1.858 SOL tripped `risk_manager EMERGENCY_STOP: Daily loss limit: -1.86 SOL` at 10:06:05 UTC — bot self-halted before any live buy could be attempted. **Wallet UNCHANGED: 5.064095633 SOL (verified Helius pre-flip 09:22Z, T-30s 09:59:30Z, post-emergency-stop 10:08Z, post-rollback 10:50Z).** **Rollback per §7 completed cleanly:** TEST_MODE=true set 10:22:42Z → first rollback restart 10:26:57Z (AUDIT auto-reset consecutive_losses 14→0, Startup reconciliation: 0 open positions in DB, Bot Core ready, emergency_stop honored — paper mode clean); sizing env reverted 10:38Z → second rollback restart 10:42:56Z (Position sizing caps MAX_ABS=0.25 SOL, all checks PASS); bot:emergency_stop DEL'd + bot:consecutive_losses set to 0 in Redis + Postgres at 10:52Z. Bot is now back in paper mode with original sizing (DAILY_LOSS_LIMIT_SOL=4.0, MAX_POSITION_SOL=0.25, MAX_SD_POSITIONS=20). **PC1 SATISFIED** (wallet 5.064 SOL ≥ 5.0 verified Phase 1 + Phase 6); **PC4 stays `[ ]`** — flip rolled back, no retry without diagnosis + fix + new authorization. **Data contamination side effect:** 14 rows in `paper_trades` (ids 9940-9953) committed with `trade_mode='live'`, `entry_signature=NULL`, `exit_signature=NULL`, `correction_method=NULL` — they pollute live-mode analytics and must be either DELETEd or tagged with `correction_method='paper_orphan_at_flip_v5a_001'` in a follow-up cleanup session. **CLEAN-003 deviation:** redis-cli not on Windows PATH → script step `bash scripts/live_flip_prep.sh` substituted with Redis MCP + asyncpg equivalents (functionally equivalent — bot:status DEL'd, paper:positions:* + bot:open_positions:* empty, bot:consecutive_losses=0 Redis+Postgres). The script doesn't reconcile `paper_trades` rows anyway — root cause is upstream of the script (`bot_core._reconcile_positions` lacks `trade_mode` filter, AND `bot:emergency_stop` Redis flag doesn't halt a running container's signal-entry loop — only honored at container startup). **Three follow-up items required before V5A-FLIP-002 can fire (all surfaced in audit §7):** (1) `V5A-FLIP-RECONCILE-FILTER-001` Tier 1 — patch `bot_core._reconcile_positions` to filter by `trade_mode='live'` when `TEST_MODE=false` (≤30 lines, in `services/bot_core.py`); (2) `V5A-FLIP-CONTAMINATION-CLEANUP-001` Tier 1 — tag or delete ids 9940-9953 in `paper_trades`; (3) `BOT-CORE-EMERGENCY-STOP-LIVENESS-001` Tier 2 — make the running bot honor `bot:emergency_stop` per-decision (not just at startup), OR replace the mechanism with an env-var-driven restart-halt. **Phase 5 finding:** my `bot:emergency_stop=true` at 09:55:01 UTC did not halt paper-bot signal intake — heartbeat.emergency stayed false through 10:08 (only flipped after the LIVE risk_manager triggered its own emergency_stop). This is the same fact pattern as item (3) above. **Scope discipline:** NO scope creep into investigation of the 14 historical orphans (entry_time spans 2026-05-12 to 2026-05-19 — some are days-old "open" rows in paper_trades that pre-existed Phase 2 — separate audit needed); NO retry without explicit Jay authorization. Audit: `docs/audits/V5A_FLIP_001_2026_05_20.md`. Scratch: `.tmp_v5a_flip/` (PROGRESS.md timeline, 01_preflight.md, 01_path_b_evidence.json, 03_clean003_output.md, 05_position_drain.md, 06_final_recheck.md, 07_flip_event_and_rollback.md, post_flip_live_check.txt, baseline_draft.md (unused — rollback voided baseline), path_b_revalidate.py, drain_check.py, live_trade_check.py, clean003_postgres.py, portfolio_snapshot_check.py). **STOP-Rollback applies — no auto-retry from this session.** Prior: API-MCP-PREFLIGHT-001 (read-only verification of live-execution dependencies pre-V5A-flip; NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy). **MATERIAL FINDING:** Helius `getBalance(4h4pst...)` returned **5.064095633 SOL** — exact +5.000000000 SOL on-chain top-up vs. 0.064 carry-forward from earlier today's PC1-WALLET-TARGET-RECONCILE-001 + CLAUDE-MD-MCP-INDEX-001. Matches D-S3 V5A trial budget exactly. **PC1 SATISFIED.** Outstanding V5A blockers drop **2 → 1** (PC4 flip itself remains — Jay-authorization-gated per CLAUDE.md "Live trading mode — session-gated"). §6 PC1 status flip from `[ ]` → `[x]` is the V5A FLIP SESSION's responsibility (not this preflight's scope) — the flip session must re-verify wallet at flip time, run `live_flip_prep.sh`, decide D-S4 market-mode (currently `market:mode:current=DEFENSIVE` — operator decides whether to override to NORMAL), reconcile `DAILY_LOSS_LIMIT_SOL=4.0 → 1.5` per D-S3, and set `TEST_MODE=false` on bot_core only. **VERDICT: ⚠ CONDITIONAL READY.** All technical preconditions verified GO; the one critical NO-GO is `mcp__railway__*` ("Not logged in to Railway CLI" — STOP-A FIRED, unchanged from yesterday). **Two paths for the flip:** (A) Jay runs `! railway login` interactively → CC-automated flip; (B) Jay flips manually via Railway dashboard → both technically unblocked. **Phase 1 (MCP no-op battery, 12 calls):** 10 OK (helius/redis/github [project]/vybe/dexpaprika/coingecko/playwright/shadcn/context7/Google Drive), 2 failed (Railway STOP-A, Socket known-broken non-blocking). **Phase 2 (External API probes, CONSTRAINED — no-auth only):** Binance SOLUSDT 200 $85.02 (0.14% delta vs Redis $84.9) ✅; Jito getTipAccounts 200 (8 accounts) ✅; GeckoTerminal Raydium SOL/USDC v4 pool 200 ($85.08) ✅; Rugcheck SOL report 200 (score=1, risks=[]) ✅. Jupiter prompt's `quote-api.jup.ag/v6` DNS-unreachable — current host is `api.jup.ag/swap/v2/*` per CLAUDE.md; `service:health.jupiter=ok HTTP 200` proxy-confirms. Authenticated APIs proxy-validated via `service:health` (helius/vybe/dexpaprika/rugcheck/gecko/defillama/jupiter all ok; anthropic key-configured-but-credit-exhausted per BUG-010; nansen 401 expected per NANSEN_DRY_RUN=TRUE; **pumpportal WARN "no signals" is a `dashboard_api.py:2041` `last_signal` Redis key-write quirk, NOT a signal-pipeline outage** — `market:new_token_count_1h=10257`, `signals:evaluated` present, 10K+ signals/hour flowing). `PUMPPORTAL_API_KEY` not referenced in `services/*` — local API is unauthenticated by design. **Phase 3 (Redis state snapshot):** Bot RUNNING paper (`bot:status.test_mode=true, status=RUNNING, open_positions=0, market_mode=DEFENSIVE, consecutive_losses=0`). `service:bot_core:heartbeat` alive 2h 5min, 0 positions, no emergency. STOP-E does NOT fire (0 paper + 0 live across `paper:positions:*`, `bot:open_positions:*`, `bot:status.positions={}`). STOP-I does NOT fire (consecutive_losses=0). `bot:emergency_stop` absent, `bot:loss_pause_until` absent. **`market:mode:current=DEFENSIVE`** — D-S4 manual judgment needed at flip time. `market:mode:override` absent. `market:session.sydney_hour=19` — D-S5 flip window OPEN. `nansen:disabled` absent (migrated to env). `bot:onchain:balance` absent (expected pre-flip). DB queries BLOCKED (`DATABASE_URL` in local `.env` is `sqlite:///toxibot.db` local-dev; no `DATABASE_PUBLIC_URL` without Railway). STOP-F (portfolio snapshot delta) cannot be evaluated — deferred to flip session. **Phase 4 (9/9 code checks PASS):** C1 paper `paper_trader.py:253-255`; C1 live PC3 `bot_core.py:953-965` (LIVE-MODE-FILTER-PARITY-001-V2 intact); Path B parser `services/helius_parser.py` (file + id-6580 docstring); Path B integration `bot_core.py:1436-1442`; ML gate `bot_core.py:60, 130-144, 674` (BOT-CORE-ML-GATE-001); sell-storm `bot_core.py:221-222, 1342-1361` (default 8/300s armed); CLEAN-003 `scripts/live_flip_prep.sh` executable; TIME_PRIME `bot_core.py:755-756` env-driven default `""`/`1.0`; Analyst suppression `signal_aggregator.py:153` (`ANALYST_DISABLED=true` at SA only — bot_core uses `ML_THRESHOLD_BOT_CORE_ANALYST=0` reserved-not-active; prompt's expectation of ANALYST_DISABLED in bot_core was prompt-side error, correct architectural layer is SA). **Tier 3 filed:** `DASHBOARD-PUMPPORTAL-HEALTH-PROBE-001` (cosmetic observability defect; not V5A-blocking). **Scope discipline:** NO services/* code change, NO env change, NO Redis writes, NO DB writes, NO deploy, NO TEST_MODE flip, NO use of local `.env` keys as substitutes for Railway env (audit principle: verify Railway's current config not local Apr-21 snapshot which may be post-rotation stale), NO scope creep into non-goals (TabPFN JWT, dashboard rebuild, ML training, BUG-010 fix, VYBE code drift). Audit: `docs/audits/API_MCP_PREFLIGHT_001_2026_05_20.md`. Scratch: `.tmp_api_preflight/`. Prior: STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001 (read-only analytical investigation; NO services/* code change, NO env change, NO Redis writes, NO deploy). Combined eval of F1 ($3K) + C1 ($1K) fill-time MC gate (the rug-filter angle) and post-C1 `no_momentum_90s` exit suppression (the structural-bleed angle) on the post-C1 SD-paper sample (n=511, 7.13d, 8 distinct days). **Verdict: ✅ VALIDATED — supports V5A relaunch.** §6 PC2 flipped `[ ]` → `[x]` SATISFIED. Outstanding V5A blockers drop **3 → 2** (PC1 wallet top-up to ~5 SOL per 2026-05-20 reconcile, PC4 flip remain). Headline numbers: WR 90.0% with every day above 83.6%, total +33.10 SOL / +4.64 SOL/day, max MC at entry $998 (under $1K ceiling), 0 above-ceiling, 0 FP winners, nm90 exit rate 0% (was 76.5% W4 pre-C1), TRAILING_STOP rate 95.5% (was ~14%), `stop_loss_20%` rate 2.5%, strip-top-10 daily rate +3.39 SOL/day. Cross-validated against C1 STOP-A counterfactual (523/+32.62/91.4%/8.12d) within 2.3% N, 1.5% PnL, 1.4 pp WR — counterfactual was correct, production rate slightly above projection. Cost-fidelity translation: live-equivalent at V5A staged sizing (D-S6, 0.10/5) ≈ +0.5 to +1.5 SOL/day with material uncertainty per COST_FIDELITY_GAP. Redis gate-firing evidence: 12,443 cumulative post-C1 rejects across 2026-05-13 → 2026-05-20 vs 511 kept (~96% reject rate; ~24× the F1 reject rate, consistent with $1K vs $3K ceiling structure). Both `STOP-LOSS-20-RUG-FILTER-EVAL-001` and `NO-MOMENTUM-90S-EVAL-001` closed as bundled by this combined session. All STOPs evaluated, none triggered (concurrent session, sample, distribution, config-drift, reconciliation, Claude-limit, git-conflict). Side-effect finding (NOT fixed this session per scope): `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS=1747104561.0` constant in DASHBOARD-DESIGN-REALIGNMENT-001 amendment is wrong-year — `1747104561` is **2025-05-13 02:49:21 UTC**, correct C1 floor for **2026-05-13 03:29:21 UTC** is **`1778642961`**. The session prompt used the same wrong value in §3.1 SQL template; first query pass returned 2,966 trades / 28d / Apr 22 onwards instead of expected ~7d / post-C1 sample. After correction to `1778642961`, analysis ran on correct post-C1 sample. Operational impact for DASH-001 BUILD-1 (Card 7 biggest wins): the literal `1747104561.0` constant must be corrected before Card 7 ships, otherwise the "post-C1 paper-only" floor would include 28d of pre-C1 data. Filed Tier 3 follow-up `DASH-CLEAN-DATA-FLOOR-FIX-001`. Audit: `docs/audits/STOP_LOSS_20_NO_MOMENTUM_90S_COMBINED_EVAL_001_2026_05_20.md`. Query script: `.tmp_combined_eval/queries.py`. Raw output: `.tmp_combined_eval/results.json`. Prior: CLAUDE-MD-MCP-INDEX-001 (docs-only; NO services/* code change, NO env change, NO Redis writes, NO deploy). Added new H2 section **"MCP servers available"** to `CLAUDE.md` between `## Standing findings — read before related work` and `## Resolved Bugs` — same neighborhood as the prior `CLAUDE-MD-FINDINGS-INDEX-001` (similar discoverability purpose). Indexes all configured MCPs with three sub-tables: **Connected (verified callable this session via no-op call) — 10 servers** (redis, helius, github [project], vybe, dexpaprika, coingecko, playwright, shadcn, context7 [plugin], Google Drive); **Connected per UI but BROKEN in session (re-auth / session reset needed) — 3 servers** (`mcp__railway__*` "Not logged in to Railway CLI", `mcp__plugin_github_github__*` "invalid session" — use project-scoped `mcp__github__*` instead, `mcp__socket__*` "No valid session"); **Configured-but-unavailable — 6 servers** (sentry △, defillama △, birdeye ✘, nansen ✘ [expected per NANSEN_DRY_RUN=TRUE], Gmail △, Calendar △). **Notably absent:** Postgres MCP — DB queries use `DATABASE_PUBLIC_URL` injected into a Python script (per `Scripts/export_paper_trades.py` pattern); historical audit docs reference "Postgres MCP" via the asyncpg-shim pattern (accurate-in-context). Self-amending instruction added so future sessions that change an MCP's state update the table. STOP-C did NOT fire (10/13 succeeded, > the "most fail" threshold). New Tier 3 🟢 follow-up filed: `MCP-REFERENCE-CORRECTION-001` — sweep historical audit docs to add "(via asyncpg shim — not an actual MCP)" qualifier where "Postgres MCP" is used as shorthand. Phase 1 verification recorded ground-truth callable status for each server (call + result + timestamp) inline in the new CLAUDE.md tables. Helius `getBalance` re-verified incidentally as part of the no-op battery: 0.064095633 SOL on trading wallet (unchanged). No services/env/Redis touched; the Railway MCP failure is an environment finding, NOT a session-fix to attempt here (re-auth is a Jay action). Prior: PC1-WALLET-TARGET-RECONCILE-001 (docs-only; NO services/* code change, NO env change, NO Redis writes, NO deploy). Reconciled §6 PC1 wallet top-up target from prior `≥1.5-2.5 SOL` (operational-minimum framing for swap-router viability) to `~5 SOL` per **D-S3 of `docs/findings/V5A_GO_LIVE_DECISIONS.md`** — the binding authority for the V5A trial budget (daily realized-loss halt 1.5 SOL = 30% of 5 SOL budget; cumulative halt 3.0 SOL = 60%; ~2 SOL operational floor at cumulative halt). Operational-minimum reasoning preserved inline as a lower-bound note (1.5-2.5 SOL remains true for swap router but is no longer the binding target). Added in-cell PC4-related flag: `DAILY_LOSS_LIMIT_SOL=4.0` currently on bot_core vs D-S3's 1.5 SOL daily halt — flagged for V5A flip session reconciliation (env change + verification belong with the flip, NOT this docs fix). Helius `getBalance` re-verified this session: **0.064095633 SOL** (unchanged since 2026-04-21; no surprise top-up). NO scope creep into PC2/PC3/PC4 substance, §6.6 historical snapshot (2026-05-01 audit), or §2 env table. D-S3 authority unchanged — no amendment to `V5A_GO_LIVE_DECISIONS.md` needed (verified §5 Amendments empty). STOP-A (concurrent session), STOP-B (PC1 already reconciled), STOP-C (D-S3 amended), STOP-D (scope creep) all evaluated, none triggered. Prior: V5A-GO-LIVE-DECISIONS-RECORD-001 (docs-only; NO services/* code change, NO env change, NO Redis writes, NO deploy). Captured seven chat-side V5A go-live decisions (D-S3 daily 1.5 / cumulative 3.0 SOL realized halt; D-S4 manual market-mode check NOT autonomous; D-S5 Wed/Thu AEST evening 18:00-21:00; D-S6 0.10/5 + NO auto-scale + staged ladder; D-S7 4-6h active observer) as a survivable record. Outputs: NEW `docs/findings/V5A_GO_LIVE_DECISIONS.md` (≤1500 words, follows COST_FIDELITY_GAP.md pattern — survivable summary, override-path appended-amendments); Tier 1 NEW `V5A-SIZING-GRADUATION-LADDER-001` ACTIVE RULE (governs trial sizing); Tier 2 NEW `GOVERNANCE-AGENT-MARKET-MODE-001` (autonomous classifier + halt authority, absorbs MARKET-MODE-001-RE-CALIBRATE-V2 linked-not-deleted); §6 V5A checklist gains NEW "Decisions (recorded)" subsection between "Known conditions at relaunch" and "Completed preconditions"; CLAUDE.md "Standing findings" table gains new row per yesterday's self-amending instruction (first session to fulfill that contract). No STOP triggered. No new audit doc — findings doc IS the survivable record. Scratch (untracked): `.tmp_v5a_decisions/` empty (decisions are inputs not outputs). Prior: CLAUDE-MD-FINDINGS-INDEX-001 (docs-only; NO services/* code change, NO env change, NO Redis writes, NO deploy). Added a new H2 section **"Standing findings — read before related work"** to `CLAUDE.md` between `## Roadmap` and `## Resolved Bugs` indexing `docs/findings/COST_FIDELITY_GAP.md` with about-column + read-before column; self-amending instruction added so future finding-creating sessions carry the obligation to append their row. Phase 1 catalog of `docs/findings/` returned only `COST_FIDELITY_GAP.md` — the session-prompt-anticipated `V5A_GO_LIVE_DECISIONS.md` does NOT exist and is NOT referenced anywhere in committed docs (`grep -ri V5A_GO_LIVE_DECISIONS` returned 0 matches); will be indexed by its own creating session when it lands. Phase 3 cross-reference verification: all 5 existing `docs/findings/COST_FIDELITY_GAP.md` references (this file lines 3 / 162 / 167; `ZMN_ROADMAP.md` lines 41 / 315) point at the existing file — no drift, no broken refs. Audit: this is a docs-only structural change, no separate audit doc written. Scratch (untracked): `.tmp_claude_md_findings/01_index_draft.md`, `02_cross_refs.md`. Prior: LIVE-MODE-FILTER-PARITY-001-V2 (code+deploy; `services/bot_core.py` live buy branch only; bot_core redeploy via single `git push`). Implemented Option A from yesterday's LIVE-MODE-FILTER-PARITY-001 STOP-C scoping: gate inserted in `bot_core.py` live `else:` branch at `:953` (pre-`execute_trade`), mirroring `paper_trader.py:247-275` (C1 gate) line-for-line. Same env var (`BOT_CORE_FILL_MC_CEILING_USD`), same `price * 1_000_000_000` MC formula, same strict-`>` threshold, same `(live)` suffix on the reject-log + distinct `:live:` Redis namespace so paper/live reject rates separate cleanly. **Gate is DORMANT under `TEST_MODE=true`** — the bot remains in paper; first live-fire is at V5A relaunch. **PC3 in §6 is now SATISFIED**, dropping outstanding V5A blockers from 4 → 3 (PC1 wallet top-up, PC2 observation through ≥2026-05-27 combined eval, PC4 flip-itself remain). Behavioral verification: 8 mock-input cases ALL PASS via `.tmp_live_filter_parity_v2/verify_live_mc_gate.py` (above-ceiling reject, at-ceiling pass-strict, below pass, gate-disabled pass, env-absent pass, price-failure fail-open, two ceiling-tier sanity). Dev loop completed in 2 iterations within the 3-cap. **Verification standard: code-level + clean-startup + rolled-back proof** — the gate cannot be observed firing in production because live mode is off (paper-mode caveat explicit in audit §6, same standard as LIVE-MODE-FILTER-PARITY-001). Two documented divergences from paper C1, both intentional: (a) MC term uses raw `fill_price` (no simulated slippage in live — paper's `_simulate_slippage` is a paper-sim artifact); (b) failure mode is fail-open at the gate (paper's fail-closed happens earlier in `paper_buy` at `:238-240`, NOT inside the gate block — V2 mirrors the gate block's literal logic). Rollback: `BOT_CORE_FILL_MC_CEILING_USD=0` (no redeploy). Audit: `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md`. Prior: COST-FIDELITY-FINDINGS-DOCUMENTATION-001 (2026-05-14, docs-only; NO services/* code change, NO env change, NO Redis writes, NO deploy). Folded the ML-TRAINING-COST-FIDELITY-AUDIT-001 conclusions into survivable, discoverable docs: (1) NEW `docs/findings/COST_FIDELITY_GAP.md` (≤1200-word summary-with-pointers; cites audit by section); (2) §6 V5A checklist gains a "Known conditions at relaunch (acknowledged, NOT blocking)" subsection with a cost-fidelity entry — deliberately not a precondition checkbox because closing the gap requires Path B data that only live trading produces (corpus has exactly 1 Path B row); (3) `ML_THRESHOLD_RETUNE_002` re-sequenced behind `PAPER-FEE-MODEL-CALIBRATION-001` in §6 Related milestones (date-gate → dependency-gate; rationale: marginal-band labels are exactly where the corruption lives, so a threshold sweep optimizes on partially-fictional labels); (4) `ANALYST-POST-GRAD-001` roadmap entry gains an explicit cost-fidelity gate at the top — Phase 0 sub-session (c) paper-mode activation must not ship until `PAPER-FEE-MODEL-CALIBRATION-001` deployed + ≥7d post-calibration data; sub-sessions (a)(b)(d) NOT gated; (5) `ML-TRAINING-MODE-FILTER-001` confirmed as single Tier 3 🟢 row (no duplicate filing). No re-investigation, no new code/env/Redis. Audit source: `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md`. Survivable doc: `docs/findings/COST_FIDELITY_GAP.md`. Prior: ML-TRAINING-COST-FIDELITY-AUDIT-001 (read-only investigation; NO services/* code change, NO env change, NO Redis writes, NO deploy). Answered chat-side question: does the ML train on realistic transaction costs and latency? **Verdict: sim-to-real gap CONFIRMED.** Training pipeline (`services/ml_model_accelerator.py`) reads `trades` + `paper_trades` with NO `trade_mode` or `correction_method` filter; target = `outcome` string (binary `win`/`loss`) derived from `pnl_sol > 0` (`paper_trader.py:415`; `bot_core.py:1149,1365`); `pnl_sol` is net of `_simulate_slippage` + `_simulate_fees` (`paper_trader.py:142-213`) — cost model IS in the training signal at threshold zero. **Cost fidelity (DB 2026-05-14, n=2874):** avg paper round-trip fee = 1.46% of position; Path B truth (id 6580) = 25.8% — **~17.6× under-count at avg paper sizing**. **Fidelity distribution:** 99.97% `pass_through` (paper sim), 0 `live_estimated_v1`, 1 `live_actual_v1`. ML-eligible corpus ≈ 8,680 rows; live share 0.47%; Path-B share 0.012%. **Latency:** 4 columns exist (`signal_detected_at`, `scored_at`, `traded_at`, `total_latency_ms`) but 100% NULL across 2874 rows; paper fill uses real-time Jupiter quote at `paper_buy` time — wall-clock-current but does NOT model the in-flight pump C1 was built to backstop. **Severity context (NOT a current-profitability fire):** ML already weakly predictive (AUC 0.536); SD profitability is structural-filter-driven (C1 MC ceiling); +1.49 SOL/day W3+W4 holds. **DOES materially affect:** ML_THRESHOLD_RETUNE_002 (≥2026-05-19, retune optimum optimizes against ~17×-optimistic labels — recommend "calibrated against sim costs" caveat in verdict, NOT blocked) + Analyst Phase 0 (June, ML-driven on mature features at higher sizing; recommended gate: `PAPER-FEE-MODEL-CALIBRATION-001` lands before Analyst ships). **3 new roadmap items:** `PAPER-FEE-MODEL-CALIBRATION-001` (Tier 2 🟡, env-only knob recalibration gated on ≥10 Path B rows — currently 1); `PAPER-LATENCY-MODEL-001` (Tier 3 🟢, gated on LATENCY-OBSERVABILITY-001); `PAPER-MEV-SLIPPAGE-MODEL-001` (Tier 3 🟢, structural addition). **Re-scoped:** `ML-TRAINING-MODE-FILTER-001` (from LIVE-TRADES-LOGGING-AUDIT-001 §9) → Tier 3 🟢 hygiene only; 0.47% live share is a rounding error on training signal — fidelity problem lives in paper sim, not paper/live blend. Surfaced (unresolved): `ML-CONTAMINATION-FILTER-BIAS-001` Tier 3 🟢. Audit: `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md`. DB queries: `.tmp_ml_cost_fidelity/query.py`. Prior: DASHBOARD-DESIGN-REALIGNMENT-001 (amendment; docs-only; NO services/* code change, NO env change, NO Redis writes, NO deploy). Folded Jay's §9 resolutions + 4 design additions into `docs/audits/DASHBOARD_DESIGN_REALIGNMENT_001_2026_05_14.md`. **§9 resolved:** re-scope ACCEPTED, ≥30d legacy coexistence YES, SINGLE accent (no picker), Sentry fold-in DEFER to v1.5, active emergency-stop DEFER (auth surface), June parallel-track CONFIRMED. **Design additions:** (A) Card 2 expanded — today + all-time cumulative P&L on one card, both numbers via `COALESCE(corrected_pnl_sol, realised_pnl_sol)` on `paper_trades` only (no `trades`/Redis-aggregate paths); (B) NEW Card 7 biggest wins — top-3 default → top-10 expand, mint tap-to-copy chip + DexScreener "↗" link, **CRITICAL hardcoded floor** `trade_mode='paper' AND entry_time >= 1747104561.0` (C1 deploy 2026-05-13 03:29:21Z UTC) as module constant `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS`; endpoint clamps `since` overrides to floor; (C) celebration FX on `realised_pnl_pct >= 200` (≥3x; column verified `services/db.py:128-129`) — confetti (`prefers-reduced-motion`-safe, vendored ~7KB) + `navigator.vibrate` haptic + optional sound toggle muted-by-default + `seenTradeIds` Set in `sessionStorage` prevents re-fire on reload; threshold = JS const `BIG_WIN_PCT_THRESHOLD=200`; (D) push-notification version EXPLICITLY DEFERRED to post-SD-validation (post-2026-05-27 combined eval + post-V5A flip stability) — SW push handler stub logs-to-console only. Card count 6 → 7 cap nudged with merge analysis preserved §11; still one route / zero tabs / zero sub-pages; 30 → 7 = ~77% smaller than Concept C (was 80%). **Build re-stated:** BUILD-0 0.5h → 1.0h (three endpoints: `/api/active-alerts` + `/api/top-wins` + `/api/lifetime-pnl`); BUILD-1 2.5h → 2.8h (Cards 1/2/4/7); BUILD-2 2.5h → 2.8h (Cards 3/5/6 + FX + PWA + push stub). **Total 7.5h → ~8.5h.** June parallel-track UNCHANGED. STOP-B revised: 3/7 cards need backend ≈ 43% (≪50%). 3 new roadmap items (all Tier 3 🟢, none V5A-blocking): DASH-BIGGEST-WINS-SCOPING-001 (prereq LIVE-TRADES-LOGGING-AUDIT-001 closed `b867daa` 2026-05-14 — but Card 7 floor remains for cliff-accounting reasons), DASH-PUSH-NOTIFICATIONS-001 (gated on SD-validation completion), DASH-CELEBRATION-FX-THRESHOLD-TUNE-001 (post-deploy fine-tune). DASH-001 ROADMAP row updated. Concurrent: pulled-rebase against `b867daa` LIVE-TRADES-LOGGING-AUDIT-001 which landed during this session; no conflict (different files except canonical doc append-only). Prior: LIVE-TRADES-LOGGING-AUDIT-001 (code+schema fix; bot_core redeploy). Investigated chat-side "paper trades leaking into a live_trades table". **There is no `live_trades` table** — the chat-side export mislabelled the **`trades` table** (the paper+live combined ML-training corpus, written by both `bot_core.py` branches by design). No misrouting bug; the real defect was that `trades` lacked a `trade_mode` discriminator. **Fix:** added `trade_mode TEXT DEFAULT 'paper'` to `trades` (db.py CREATE + idempotent ALTER), tagged both `bot_core.py` INSERT sites (`'paper'`/`'live'` literals), one-time backfill via `migrations/002_add_trade_mode_to_trades.sql` (applied this session). **Classification of all 9,521 `trades` rows: paper 9,480 / live 41 / unclassifiable 0.** The 41 live = 35 v3/v4 trial trades (all confirmed via `live_trade_log` TX_SUBMIT sigs) + 1 genuine on-chain round-trip (id 6596) + 5 reconcile-residuals. **Isolated real-money result ≈ −3.36 SOL — cross-validates the ~3.4 SOL on-chain wallet drawdown in CLAUDE.md's `1b40df3` forensics.** `paper_trades` was already correctly mode-separated and was NOT touched. `verify_logging_fix.py` ALL PASS. Recommendation: DO NOT purge — filter `trades` by `trade_mode`. New follow-up flagged: ML-TRAINING-MODE-FILTER-001. Audit: `docs/audits/LIVE_TRADES_LOGGING_AUDIT_001_2026_05_14.md`. Prior: V5A-PRECONDITION-CHECKLIST-CLEANUP-001 (docs-only; NO services/* code change, NO env change, NO Redis writes (read-only on live state), NO deploy). Rewrote §6 V5a preconditions outstanding to reflect verified 2026-05-14 state. Verification: wallet 0.064095633 SOL on-chain unchanged via Helius `getBalance`; `TEST_MODE=true` on bot_core + signal_aggregator via Railway MCP; `BOT_CORE_FILL_MC_CEILING_USD=1000` (C1) live; `SD_MC_CEILING_USD=3000` live; `SD_EARLY_CHECK_SECONDS=60` live; `market:mode:override` + `nansen:disabled` keys NOT present in Redis (latter migrated to `NANSEN_DRY_RUN=TRUE` env); `market:mode:current=NORMAL` automatically. **§6 changes:** kept PC1 wallet top-up; reframed observation window to post-C1 → combined eval ≥2026-05-27 (was "Sessions A-D 24-48h"); added PC3 `LIVE-MODE-FILTER-PARITY-001-V2` (resolves audit §8.2 open question from yesterday); folded Redis-override into PC4 flip-time check; removed SD_EARLY_CHECK relax (TUNE-009 deferred permanently) and `nansen:disabled` (env-migrated); moved SD_MC_CEILING_002 + LIVE-FEE-CAPTURE-002 Path B to "Completed preconditions (historical)". §7 LIVE-FEE-CAPTURE-002 row flagged as stale carry (out of scope for this cleanup). **Honest V5A blocker count: 4** (wallet, observation, V2, flip-itself); **2 completed (historical)**; **3 removed/folded**. Audit: `docs/audits/V5A_PRECONDITION_CHECKLIST_CLEANUP_001_2026_05_14.md`. Prior: LIVE-MODE-FILTER-PARITY-001 (read-only investigation; NO services/* code change, NO env change, NO Redis writes, NO deploy). Investigated NO_MOMENTUM_90S_AUDIT_001 §10: port the C1 fill-time MC ceiling to the LIVE execution path. **Verdict: STOP-C — SCOPING NEEDED.** Routing confirmed (`services/execution.py` is the live path only — not STOP-B); gate confirmed absent in `execution.py` (not STOP-A). STOP-C fired: the C1 gate (`paper_trader.py:247-275`) gates on a **fill-time** price; `execution.py` has 3 execution routes and computes no fill-time price (it returns a signature from unsigned tx bytes; bot_core fetches price *after* at `:956`). The only MC value reachable inside `execute_trade` is signal-time `token.liquidity_usd` — gating on it fails MC-computation parity and merely duplicates SA's `SD_MC_CEILING_USD`. **No env var introduced; execution.py does NOT now read `BOT_CORE_FILL_MC_CEILING_USD` — §2 config table unchanged.** New roadmap item **LIVE-MODE-FILTER-PARITY-001-V2** (Tier 1 🟡, V5A relaunch blocker) recommends Option A: gate in the `bot_core.py` live branch before `execute_trade` using `self._get_token_price`. Until V2 lands, a live relaunch reintroduces the $1k-$3k fill-time bleed C1 eliminated on the paper path. Audit: `docs/audits/LIVE_MODE_FILTER_PARITY_001_2026_05_14.md`. Prior: DASHBOARD-DESIGN-REALIGNMENT-001 (design session; NO services/* code change, NO env change, NO Redis writes; re-scope of DASH-001 ahead of any build session). DASH-001 transitions from Concept C "Unified Cockpit" (≈30 surfaces, 3 routes × 3 tabs × 14 panels) to a **mobile-first glanceable monitor at `/m`** (6 cards, single screen, PWA-installable, ~480px column on every viewport, 5-7× smaller in surface). Build breakdown: 3 sessions × 2.5h = 7.5h (BUILD-0 backend `/api/active-alerts` endpoint 0.5h; BUILD-1 UI scaffold + Cards 1/2/4 + `/m` route 2.5h; BUILD-2 Cards 3/5/6 + PWA manifest+SW 2.5h). Sequencing: **June parallel-track with Analyst Phase 0**, NOT May trading-logic critical path (C1 observation → combined eval ≥2026-05-27 → ML_THRESHOLD_RETUNE_002). Backend dependencies: 1 new endpoint (~30 lines) for Card 3 active-alerts (aggregates `bot:emergency_stop`, `bot:consecutive_losses`, `bot:loss_pause_until`, market_mode age, `bot:filter:fill_mc_ceiling:rejects:<date>`). 5 of 6 cards backed by existing endpoints. Legacy `dashboard.html` retained at `/` for desktop analytical depth; coexist ≥30 days. DASHBOARD_REDESIGN_2026_04_19.md header-noted as SUPERSEDED for scope. DASH-T-001 test list shrinks (3-4h → ~2.5h, no full realignment needed). Audit: `docs/audits/DASHBOARD_DESIGN_REALIGNMENT_001_2026_05_14.md`. Prior: DASHBOARD-AUDIT-002 (2026-05-13, read-only investigation; no env/Redis/code changes; verdict REAFFIRM REBUILD with recommendation to promote DASH-001 from QUEUED → Tier 1 scheduled; 14 panels × 18 endpoints inventoried; decision-flow audit shows 0 of 8 operator decisions fully SUPPORTED; 10 gap items all survive rebuild; PATCH-NOW count = 1 definitive below §8 BUNDLE threshold; STOP-A applies weakly — see `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md`). Prior: NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 (env-only retune of `BOT_CORE_FILL_MC_CEILING_USD` 3000 → 1000 on bot_core at 03:29:21Z UTC; container restart 03:38:37Z UTC clean; T1 audit skipped per audit §12 Jay-authorized fast-track; STOP-A retest pre-deploy confirmed C1 marginal ROI +1.49 SOL/day W3+W4 / +3.02 W4-only on 8.12d sample, 0 FP winners; §2 bot_core row + §6.5 nm90 row updated). Prior: ML-SCORE-ATH-VALIDATION-001 (read-only research session; new `mint_ath_lookups` table; verdict: ML is WEAKLY PREDICTIVE, AUC=0.5361; live `ML_THRESHOLD_BOT_CORE_SD=40` is sub-optimal in pre-gate sample, historical optimum thr=55 with +0.16 SOL/day lift; deploy DEFERRED to ML_THRESHOLD_RETUNE_002 ≥7d post-gate data). Prior: NO-MOMENTUM-90S-AUDIT-001 (T0 read-only; §6.5 nm90 row updated to AUDIT-COMPLETE / DEPLOY-RECOMMENDED for retune of F1 to $1,000; deploy is follow-on session). Prior: STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (code+env deploy of F1 fill-time MC ceiling at $3,000 on bot_core; §2 bot_core block + §6.5 `stop_loss_20%` leak row updated to MITIGATED). Earlier: STOP-LOSS-20-RUG-INVESTIGATION-001 (2026-05-09; read-only investigation; §6.5 leaks updated for `stop_loss_20%` row — DIAGNOSED, F1 fill-time MC ceiling deploy prompt ready). Prior: STATE-SNAPSHOT-2026-05-08 (~13:21 UTC; read-only; verified probe expiry, wallet balances, env state, code state — see `docs/audits/STATE_SNAPSHOT_2026_05_08.md`). Earlier: STRATEGY-CLIFF-INVESTIGATION-001 (2026-05-07; new §6.8), API-CREDITS-HEALTH-DIAGNOSTIC-001 (2026-05-06; new §6.7 external-API state matrix), MARKET-MODE-001-RE-CALIBRATE (2026-05-06; Path C / STOP, no code change), TIMEZONE-AUDIT-001 (2026-05-05; read-only sweep), BOT-CORE-ML-GATE-001 (2026-05-05; commit `ea0da2f`; ML_THRESHOLD_BOT_CORE_SD=40 env-active 14:16:48Z UTC). Earlier: STATE-RECONCILE-2026-05-01, TIME-PRIME-CONTRADICTION-FIX-001 (commit `13d4324`).
**Source:** Read directly from Railway env, Redis, DB, on-chain.
**NOT a chat-side carry.** Memory drift policy: see CLAUDE.md "Persistence Convention" (added Session E).

When this file is older than ~3 days OR a session changes deployed config without updating it, run a fresh ENV-AUDIT before relying on it as authoritative. The values below are point-in-time snapshots, not load-bearing across the bot's lifetime.

---

## §1 Bot mode

`TEST_MODE=true` (paper) on **all services except treasury**. `treasury.TEST_MODE=false` is a known unaddressed risk (TREASURY-TEST-MODE-002 🟡; dormant because trading wallet 0.064 SOL ≪ 30.0 trigger).

Live mode flip is **session-gated** per CLAUDE.md "Live trading mode — session-gated" rule. V5a flip pending preconditions in §6.

---

## §2 Deployed config (post-Sessions A–D, 2026-04-30)

### bot_core (post-Session-D LIVE-FEE-CAPTURE Path A + Session-B BUG-022 fix + hotfix `17c2aac`)

| var | value | notes |
|---|---|---|
| TEST_MODE | true | paper |
| AGGRESSIVE_PAPER_TRADING | true | bypasses ML-threshold gate at signal_aggregator for paper |
| MIN_POSITION_SOL | 0.05 | |
| MAX_POSITION_SOL | 0.25 | FEE-MODEL-001 cap |
| MAX_POSITION_SOL_FRACTION | (unset; code default 0.10) | |
| SPEED_DEMON_BASE_SIZE_SOL | 0.15 | FEE-MODEL-001 |
| SPEED_DEMON_MAX_SIZE_SOL | 0.25 | FEE-MODEL-001 |
| MAX_SD_POSITIONS | 20 | |
| MAX_CONCURRENT_POSITIONS | 6 | |
| MAX_TRADES_PER_HOUR | 500 | |
| ML_THRESHOLD_SPEED_DEMON | 40 | bot_core no longer reads this var directly — deprecated in favour of ML_THRESHOLD_BOT_CORE_SD per BOT-CORE-ML-GATE-001 (2026-05-05). Kept for cross-service env hygiene. |
| ML_THRESHOLD_ANALYST | 35 | bot_core no longer reads this var directly — deprecated in favour of ML_THRESHOLD_BOT_CORE_ANALYST. |
| ML_THRESHOLD_WHALE_TRACKER | 35 | bot_core does not gate Whale Tracker by env (helper returns None for ungated personalities). Reserved for future. |
| **ML_THRESHOLD_BOT_CORE_SD** | **40** | **NEW (BOT-CORE-ML-GATE-001, 2026-05-05).** Env-active 14:16:48Z. The bot_core-side per-personality ML floor; binds at `process_signal` consumption time. Default 0 = disabled. Gate semantics: ml_score=None → ACCEPT (fail open); threshold ≤ 0 → ACCEPT (disabled); ml_score < threshold → REJECT; ml_score == threshold → ACCEPT (boundary inclusive). Independent of SA override; closes the AGGRESSIVE_PAPER+TEST_MODE bypass discovered in ML-RETUNE Session 4 §8. |
| **BOT_CORE_FILL_MC_CEILING_USD** | **1000** | **GOVERNS BOTH PAPER AND LIVE PATHS AS OF 2026-05-19 (LIVE-MODE-FILTER-PARITY-001-V2).** Originally deployed at **3000** by STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (2026-05-11). Retuned to **1000** per NO-MOMENTUM-90S-AUDIT-001 §7 C1 (audit `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md`, deploy 2026-05-13 03:29:21Z UTC; container restart 03:38:37Z UTC). Fill-time market-cap ceiling, env-controlled. **Paper path:** reads inside `services/paper_trader.paper_buy` after `entry_price` is computed; if `entry_price * 1_000_000_000 > ceiling`, returns `{success: False, error: "fill_mc_ceiling_exceeded"}` and increments Redis counter `bot:filter:fill_mc_ceiling:rejects:<date>` (14d TTL). **Live path (NEW 2026-05-19):** reads inside `services/bot_core.py` `else:` (live) branch before `execute_trade`; if `self._get_token_price(mint) * 1_000_000_000 > ceiling`, logs `FILL_MC_CEILING reject (live): ...` and increments Redis counter `bot:filter:fill_mc_ceiling:rejects:live:<date>` (distinct `:live:` namespace so paper/live reject rates separate; same 14d TTL); short-circuits with bare `return` before `execute_trade`. Default 0 in code = disabled on both paths. Closes both `stop_loss_20%` rug-tier bleed (originally targeted at $3K) AND `no_momentum_90s` $1k-$3k MC-band bleed (C1 retune). Counterfactual at retune: marginal +1.49 SOL/day (W3+W4 8.12d), +3.02 SOL/day (W4-only); 0 FP winners (max TRAILING_STOP-win MC in sample = $892). Rollback: env→0 (no redeploy required; disables both paper and live gates simultaneously); to undo retune only, env→3000. **Live gate currently dormant under `TEST_MODE=true`** — first live-fire at V5A relaunch. First post-deploy paper log: `FILL_MC_CEILING reject: 6X5V79NvN85P mc=$10753 > ceiling=$1000` at 03:41:38Z (2026-05-13) confirms paper plumbing. V2 audit: `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md`. |
| ML_THRESHOLD_BOT_CORE_ANALYST | 0 | NEW (BOT-CORE-ML-GATE-001). Reserved analyst-side var; not active (Analyst is HARD DISABLED via ANALYST_DISABLED=true). Activates if/when Analyst is re-enabled. |
| STAGED_TAKE_PROFITS_JSON | `[[2.00,0.20],[5.00,0.375],[10.00,1.00]]` | |
| TIERED_TRAIL_SCHEDULE_JSON | `[[0.10,0.30],[0.50,0.25],[1.00,0.20],[2.00,0.15],[5.00,0.12]]` | |
| STOP_LOSS_PCT | 0.20 | |
| TIME_PRIME_MULTIPLIER | 1.0 | TIME-PRIME-CONTRADICTION-FIX-001 (2026-05-01 commit `13d4324`); was hardcoded 2.0 at AEDT 18-20, now env-controlled and disabled by default |
| TIME_PRIME_HOURS_AEST | (unset → code default `""`) | empty hours = TIME_PRIME branch never fires; future re-tune lever |
| DAILY_LOSS_LIMIT_SOL | 4.0 | |
| DAILY_LOSS_LIMIT_PCT | 0.10 | |
| SD_EARLY_CHECK_SECONDS | 60 | TUNE-009 ⏸ DEFERRED — empirical evidence rules out relax |
| SD_EARLY_MIN_MOVE_PCT | 3.0 | window opens at 50s with `early_check_sec - 10 < hold` |
| MIN_BALANCE_SOL | 2.0 | |
| DASH_RESET_MARKER | 20260421_1113 | |

### signal_aggregator (post-Session-C SD_MC_CEILING **ROLLED BACK** to 999999999)

| var | value | notes |
|---|---|---|
| TEST_MODE | true | |
| ANALYST_DISABLED | true | ANALYST-DISABLE-002 ✅ effective |
| AGGRESSIVE_PAPER_TRADING | true | |
| HOLDER_COUNT_MIN | 1 | TUNE-005 ⏪ ROLLED BACK 2026-04-29 — 24h validation window |
| ML_THRESHOLD_SPEED_DEMON | 65 | live-mode gate; AGGRESSIVE_PAPER bypasses for paper |
| ML_THRESHOLD_ANALYST | 55 | |
| ML_THRESHOLD_WHALE_TRACKER | 55 | |
| BUY_SELL_RATIO_MIN | 3.0 | GATES-V5 |
| PRE_FILTER_SCORE_MIN | 1.15 | GATES-V5 |
| ENTRY_FILTER_MIN_BUY_SELL_RATIO | 1.5 | |
| ENTRY_FILTER_MIN_WALLET_VELOCITY | 15.0 | |
| RUGCHECK_REJECT_THRESHOLD | 2000 | |
| **SD_MC_CEILING_USD** | **3000** | ✅ ACTIVE post-SD_MC_CEILING_002 deploy 2026-04-30 ~12:30 UTC. Gate now computes MC from BC reserves (`vSolInBondingCurve / vTokensInBondingCurve × 1B × market:sol_price`) mirroring `bot_core.py:927`. _002 replaces _001's inert gate. Verification (Step 6 + 24h) queued. Rollback: env → 999999999. |
| CFGI_MIN | 20 | |
| SPEED_DEMON_BASE_SIZE_SOL | 0.15 | TUNE-004 ✅ FIXED 2026-04-30 — aligned with bot_core (was stale 0.45). SA code doesn't read these vars (vestigial). |
| SPEED_DEMON_MAX_SIZE_SOL | 0.25 | TUNE-004 ✅ FIXED 2026-04-30 — aligned with bot_core (was stale 0.75). |
| MAX_SD_POSITIONS | 20 | TUNE-004 ✅ FIXED 2026-04-30 — aligned with bot_core (was stale 3). |
| MIN_POSITION_SOL | 0.05 | TUNE-004 ✅ FIXED 2026-04-30 — aligned with bot_core (was stale 0.10). |

### treasury

| var | value | notes |
|---|---|---|
| **TEST_MODE** | **false** | TREASURY-TEST-MODE-002 🟡 — dormant at current wallet (0.064 SOL << 30 trigger), but latent on-chain risk if wallet ever crosses |
| TREASURY_TRIGGER_SOL | 30.0 | |
| TREASURY_TARGET_SOL | 25.0 | |

### Other services

`market_health`, `ml_engine`, `signal_listener`, `governance`, `web` — all `TEST_MODE=true`. Per ENV_AUDIT_2026_04_29 §2, `web` carries an extensive shadow set of personality params that may be vestigial display-only (TUNE-008 cleanup item). `ml_engine` uses `ML_ENGINE=original` (different from rest using `accelerated`); ml_engine is the ground truth. Two different Nansen API keys in production simultaneously (SEC-001 split-key state).

For full per-service env inventory see `docs/audits/ENV_AUDIT_2026_04_29.md` §2.

---

## §3 Wallets

| wallet | address | balance | last verified |
|---|---|---:|---|
| Trading | `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` | **0.064095633 SOL** | 2026-05-08 13:21 UTC via Helius `getBalance` (UNCHANGED from 2026-04-30) |
| Holding | `2gfHQvyQdpDtiyUcFQJE6o15VkrHn7YXubp8DRwttWJ9` | **0.190842421 SOL** 🟡 | 2026-05-08 13:21 UTC via Helius (was 0.0098 SOL on 2026-04-29; +0.181 drift — confirm with Jay; treasury is dormant so this should not be automation) |

**Wallet history (per CLAUDE.md "Live trading mode" + audits):**
- 5.0 → 1.564 SOL: v3/v4 trial real on-chain trades 2026-04-16/17 (~3.4 SOL net cost; per `1b40df3` forensics)
- 1.564 → 0.064 SOL: single 1.5 SOL outgoing transfer 2026-04-21 10:04:48 UTC to `7DSQ3ktY...AgUy` (sig `42dnuS1...`) — **confirmed intentional by Jay** (Branch 1 per WALLET_DRIFT_INVESTIGATION_2026_04_29.md). Reconciliation gap = 0 lamports.

**Pre-V5a top-up:** ~3 SOL transfer to trading wallet (Jay action) is required before V5a can size positions correctly. `MIN_POSITION_SOL=0.05` × `MAX_POSITION_SOL_FRACTION=0.10` = effective max 0.0064 SOL at 0.064 wallet → swap router rejects.

---

## §4 Active personalities

| personality | status | notes |
|---|---|---|
| Speed Demon | ACTIVE | sole live-trading personality |
| Analyst | DISABLED | env (`ANALYST_DISABLED=true` at SA + bot_core) + Redis override (clobbered, env-vars load-bearing per ANALYST-DISABLE-002 commit `9d6e95c`). Graduation-sniper bypass closed at code level. |
| Whale Tracker | DORMANT | signal source not configured; re-enable via WHALE-001-v2 (Vybe-first) |

---

## §5 Recent performance baseline (35h post-recovery, ending 2026-04-30 ~09:00 UTC)

Post-recovery window opened 2026-04-28 13:02 UTC (first paper close after the 2026-04-25 EMERGENCY_STOP). 35h sample of pure Speed Demon paper:

| metric | value | source |
|---|---:|---|
| SD trades | 272 | Session A audit §7 |
| SD WR | 23.4% (57/244 closed at audit time) | Session A audit |
| SD total PnL | +0.140 SOL | Session A audit |
| `no_momentum_90s` exits | 123 (50% of closed) | Session A audit §3 |
| `no_momentum_90s` bleed | -2.915 SOL on 0% WR | Session A audit |
| `TRAILING_STOP` wins | 55 (sole winner channel + 2 staged_tp_+1000%) | Session A §7 |
| Big winners ≥0.10 SOL | 13 | Session A §4 |

Last 24h SD trend (2026-04-30 08:53 UTC – 24h, snapshot):
- **n=64 trades, total_pnl=-1.31 SOL, 11 wins (17.2% WR)**.
- `no_momentum_90s` exits = 38/64 (59%) — bleed remains (TUNE-009 deferred per Session A).
- **`market_cap_at_entry > 3000` = 7/64 (11%)** — confirms SD_MC_CEILING_001 rollback was correct (gate inert on fresh signals); SD_MC_CEILING_002 follow-up needed.
- Three big winners closed 08:17-08:24 UTC at +249-333% peaks (DLDW21AjMqU3, EA6ZTu8RHWWg, 7NSipxskmTBk).
- `paper:stats` Redis hash: total_trades=7757, total_pnl_sol=601.39, winning_trades=3545 (lifetime).

---

## §6 V5a preconditions outstanding

> Rewritten 2026-05-14 by V5A-PRECONDITION-CHECKLIST-CLEANUP-001. Every item below was verified against live state (Railway env, Redis, on-chain) on the rewrite date. See `docs/audits/V5A_PRECONDITION_CHECKLIST_CLEANUP_001_2026_05_14.md` for the old-vs-new diff. Stale anchors from 2026-04-30 (Sessions A-D, session-E Redis TTL snapshot, SD_EARLY_CHECK relax investigation) removed; observation window re-anchored to current state.

**Outstanding V5A blockers (1 PC; 3 follow-ups from V5A-FLIP-001-V2 rollback all complete as of 2026-05-21 V5A-FIXES-001):**

- [x] **PC1 — `~5 SOL on trading wallet`** ✅ **SATISFIED 2026-05-20** by `V5A-FLIP-001-V2` (and incidentally by `API-MCP-PREFLIGHT-001` Phase 1 earlier same day). On-chain balance **5.064095633 SOL** (re-verified Helius `getBalance` 4× across the V5A-FLIP-001-V2 session at 09:22Z / 09:59:30Z / 10:08Z / 10:50Z — exact match every time; unchanged from earlier preflight reading and matches D-S3 trial budget exactly). Originally `[ ]` outstanding pending Jay action; the +5.000000000 SOL top-up has landed.

- [x] **PC2 — Post-C1 observation through combined eval** ✅ **SATISFIED 2026-05-20** by `STOP-LOSS-20-NO-MOMENTUM-90S-COMBINED-EVAL-001`. Eval pulled forward from ≥2026-05-27 anchor (PC2's true gate is "the combined eval has run and its verdict supports continuing" — date was an anchor, not a sacred deadline). Verdict: ✅ **VALIDATED**. Sample: n=511 closed SD-paper trades, 7.13d span, 8 distinct days, 7 days with ≥30 trades (all STOP-B/C gates pass). Headline metrics: WR **90.0%** (target ≥60%) with every one of 8 days above 83.6%; total **+33.10 SOL / +4.64 SOL/day**; no negative day, no day below the +0.87 SOL minimum; max market_cap_at_entry **$998** (under $1K ceiling); **0** trades above $1K; **0** false-positive winners; `stop_loss_20%` exit rate **2.5%** (target ≤5%); **`no_momentum_90s` exit rate 0%** (target ≤30%); `TRAILING_STOP` rate **95.5%** (target ≥60%); strip-top-10 daily rate **+3.39 SOL/day** (target ≥+1.0). Cross-validated against C1 STOP-A counterfactual baseline (523/+32.62/91.4%/8.12d) — matches within 2.3% N, 1.5% PnL, 1.4 pp WR. Cost-fidelity translation: live-equivalent expectation at V5A staged sizing (D-S6, 0.10/5) ≈ +0.5 to +1.5 SOL/day with material uncertainty per `docs/findings/COST_FIDELITY_GAP.md`. Full audit: `docs/audits/STOP_LOSS_20_NO_MOMENTUM_90S_COMBINED_EVAL_001_2026_05_20.md`. Both `STOP-LOSS-20-RUG-FILTER-EVAL-001` and `NO-MOMENTUM-90S-EVAL-001` closed as bundled by this combined session.

- [x] **PC3 — `LIVE-MODE-FILTER-PARITY-001-V2` landed** ✅ **DEPLOYED 2026-05-19** per audit `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md`. Gate inserted in `services/bot_core.py` live `else:` branch before `execute_trade` (Option A), reading `BOT_CORE_FILL_MC_CEILING_USD` and computing `fill_mc = self._get_token_price(mint) * 1_000_000_000`. Mirrors paper C1 (`paper_trader.py:247-275`) line-for-line — same env var, same MC formula, same strict-`>` threshold, same reject-log + Redis-counter (live namespace `bot:filter:fill_mc_ceiling:rejects:live:<date>`, 14d TTL). Gate currently **DORMANT under `TEST_MODE=true`**; first live-fire at V5A flip. 8-case verify harness ALL PASS (`.tmp_live_filter_parity_v2/verify_live_mc_gate.py`); container restart confirmed clean post-`git push`. Two documented intentional divergences vs paper C1 (slippage padding on the MC term; fail-open at the gate block) covered in audit §8 parity table. Re-verify at flip time via `grep BOT_CORE_FILL_MC_CEILING_USD services/bot_core.py` (still present) + Redis `keys bot:filter:fill_mc_ceiling:rejects:live:*` after first live traffic.

- [ ] **PC4 — V5A flip itself: `TEST_MODE=false` on bot_core**. Terminal action per CLAUDE.md "Live trading mode — session-gated" rule (§Operating Principles). **Attempted by `V5A-FLIP-001-V2` 2026-05-20 ~10:00 UTC → ROLLED BACK after Phase 8 failure (14 phantom 'live' rows from paper_trades reconcile; wallet UNCHANGED 5.064 SOL — no on-chain transactions fired).** See `docs/audits/V5A_FLIP_001_2026_05_20.md` §4 for root cause. **2026-05-21 update by V5A-FIXES-001: 3 follow-ups complete — V5A-FLIP-002 is structurally unblocked.** (1) `V5A-FLIP-RECONCILE-FILTER-001` ✅ DEPLOYED commit `f3591eb` 2026-05-21 ~14:42Z — `mode_clause` in `_reconcile_positions` (line 249) + `_load_state` (line 308) now applies trade_mode filter to BOTH `paper_trades` AND `trades` (root cause was different from filed: live-mode reconciler reads `trades` corpus, not `paper_trades`). (2) `V5A-FLIP-CONTAMINATION-CLEANUP-001` ✅ DONE — 14 phantom rows ids 9940-9953 tagged `correction_method='paper_orphan_at_flip_v5a_001'`; id 6580 untouched. (3) `BOT-CORE-EMERGENCY-STOP-LIVENESS-001` ✅ CLOSED-AS-NON-BUG — per-decision check already exists at `bot_core.py:604-609` inside `process_signal`. V5A-FLIP-001-V2 audit's "Phase 5 finding" was misinterpretation (heartbeat.emergency conflated with per-decision check; 14 phantoms predate the 9-min drain window by days). Bonus deploy: `V5A-FLIP-CLOSE-TRADE-MODE-001` ✅ DEPLOYED commit `3c50520` — defensive-INSERT trade_mode now derived from `trades.trade_mode` lookup (defense-in-depth post-Bug-1). V5A-FLIP-002-V3 prep notes at `docs/audits/V5A_FLIP_002_V3_PREP_NOTES_2026_05_21.md` capture 7 deltas vs V2. **2026-06-02 update by V5A-FLIP-002-V3R: ⛔ NO-FLIP — the authorized flip session halted at Phase 1 preflight on STOP-M (`market:mode:current=HIBERNATE` + dead signal pipeline, `new_token_count_1h=14`). Zero state writes; wallet unchanged 5.064 SOL on-chain. NOT a rollback — re-attemptable in the next non-HIBERNATE window with the same authorization. All non-market preflight checks GO (commits at HEAD, source fixes present, Path B engine exact, `trades` live-open=0). Open tooling item: Railway CLI v4.6.0 can't confirm the running `7458f2d` SHA — upgrade to ≥4.10.0 or use the Phase 1.5 forced-redeploy fail-safe. See `docs/audits/V5A_FLIP_002_V3R_2026_06_02.md`.** **2026-06-03 update by MARKET-REGIME-DIAGNOSTIC-001 (read-only): the V3R HIBERNATE is a PIPELINE OUTAGE, NOT a market lull — do NOT "wait for the market to recover."** Both `bot_core` and `signal_listener` are in CRASHED Railway state, crash-looping ~6.7s on a `redis.TimeoutError` in pubsub `.listen()` via an unguarded `asyncio.gather` (`signal_listener.py:335`/`1395`; bot_core ~`L2410`); this starves `market:migration_count_1h` (absent → `grad_rate=0`) which single-leg-vetoes the mode to HIBERNATE while `dex_vol=$1.753B` is healthy and pump.fun is launching ~1,500-2,000/hr (3 external sources, conf 0.8-0.9). The bot has been effectively DOWN since ~2026-05-28T13:00Z (zero trades 05-29..06-01). **A flip now would (a) trade LIVE in HIBERNATE (Q2: the HIBERNATE skip is `AGGRESSIVE_PAPER`-gated not TEST_MODE; bot_core has no independent skip) and (b) the flip's own redeploy would revive the CRASHED bot_core into live mode.** Flip is now also blocked on **`PIPELINE-PUBSUB-ISOLATION-001` (Tier 1)**. Validation edge is UNAFFECTED (Q4: genuine NORMAL/DEFENSIVE regime; PC2 not re-opened). Audit `docs/audits/MARKET_REGIME_DIAGNOSTIC_001_2026_06_02.md`; finding `docs/findings/MARKET_REGIME_GAP.md`. PC4 stays `[ ]`.** **Pre-flip self-check at retry time:**
  - PC1-PC3 all satisfied (PC1 currently `[x]`; PC2 `[x]`; PC3 `[x]`).
  - 3 follow-ups above all landed.
  - `bash scripts/live_flip_prep.sh` (CLEAN-003) ran clean AND `paper_trades` open count actually == 0 (verify via DB query at T-30s, not just T-5min).
  - `market:mode:current` ≠ HIBERNATE per D-S4 manual judgment (V5A-FLIP-001-V2 V2 amendment: NORMAL/DEFENSIVE/AGGRESSIVE all acceptable; only HIBERNATE aborts).
  - **NEW (MARKET-REGIME-DIAGNOSTIC-001) — pipeline-health gate:** `PIPELINE-PUBSUB-ISOLATION-001` landed AND both `bot_core` and `signal_listener` Railway deployments are RUNNING (not CRASHED) AND `market:new_token_count_1h` is in the hundreds–thousands AND `market:migration_count_1h` is present/non-trivial AND any non-HIBERNATE mode is GENUINE (all three legs clear), NOT via a manual `market:mode:override`. **A HIBERNATE reading while `dex_vol ≥ $1B` means a starved counter / crashed pipeline, not a quiet market** (`docs/findings/MARKET_REGIME_GAP.md` §2,§5). Cross-check the bot's `new_token_count` against an external pump.fun launch rate (dexpaprika; ~1,500/hr is normal) before trusting "the market is quiet."
  - `DAILY_LOSS_LIMIT_SOL` set to 1.5 per D-S3 (V5A-FLIP-001-V2 set this then reverted to 4.0 on rollback — needs re-set at retry).
  - `MAX_POSITION_SOL=0.10` + `MAX_SD_POSITIONS=5` per D-S6 (V5A-FLIP-001-V2 set then reverted — needs re-set at retry).
  - On-chain balance within 0.01 SOL of `portfolio_snapshots.total_balance_sol` (NOTE: paper portfolio at retry will show ~64-66 SOL vs wallet ~5 SOL — that's expected paper-vs-real divergence and not a STOP-F2 condition per V5A-FLIP-001-V2 V2 amendment).
  - Sell-storm circuit breaker present (`SELL_FAIL_THRESHOLD` code default = 8, env unset is fine — < 1000).

**Related milestones (parallel work, not V5A preconditions):**

- `ML_THRESHOLD_RETUNE_002` — **RE-SEQUENCED 2026-05-14 by COST-FIDELITY-FINDINGS-DOCUMENTATION-001.** Previously gated on "≥7d post-`BOT_CORE_ML_GATE` clean data (≥2026-05-19)". Now **gated on `PAPER-FEE-MODEL-CALIBRATION-001` deploy + ≥7d post-recalibration paper data**. Rationale: a threshold sweep is a marginal-trade optimization, and the marginal band is exactly where the audit confirmed labels are corrupted by the ~17.6× cost-optimism — running the retune on the current corpus optimizes on partially-fictional labels. Date-gate replaced with dependency-gate. See `docs/findings/COST_FIDELITY_GAP.md` §4 + `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md` §7.4. Paper-only at flip — orthogonal to V5A.
- Combined `STOP-LOSS-20-RUG-FILTER-EVAL-001` + `NO-MOMENTUM-90S-EVAL-001` at ≥2026-05-27 — gates PC2 observation completion (see PC2 above).

**Known conditions at relaunch (acknowledged, NOT blocking):**

- **Cost-fidelity gap (acknowledged 2026-05-14):** V5A relaunches with a known **~17.6× cost-optimism** and **zero-latency optimism** in the ML training corpus per `docs/audits/ML_TRAINING_COST_FIDELITY_AUDIT_001_2026_05_14.md`. The corruption band (~±0.030 SOL) is wider than the median trade's entire P&L (0.0257 SOL) — a large fraction of training labels may be flipped under realistic costs. **This cannot be closed pre-relaunch:** calibration needs Path B (real on-chain) cost data, which only live trading produces; the corpus currently has exactly 1 Path B row. V5A relaunch is the data-gathering mechanism for closing it, not a step that has to wait for it to be closed. **Mitigation already designed-in:** staged relaunch (v5a→v5d) + small position sizing (`MAX_POSITION_SOL=0.10`, `MAX_SD_POSITIONS=5` for first 24h per V5A-GO-NO-GO 2026-05-01 PC8). **Why it is not a fire today:** ML is already weakly predictive (AUC 0.536) and SD's edge is C1-MC-ceiling structural, not ML-driven — the gap degrades a component that is currently a minor input. **Why it matters tomorrow:** `ML_THRESHOLD_RETUNE_002` (re-sequenced behind `PAPER-FEE-MODEL-CALIBRATION-001` above) and Analyst Phase 0 (gated in `ANALYST-POST-GRAD-001` roadmap entry) both inherit the gap at higher leverage. Closing the gap is post-relaunch work: see `PAPER-FEE-MODEL-CALIBRATION-001` (Tier 2 🟡, gated on ≥10 Path B rows). Full detail: `docs/findings/COST_FIDELITY_GAP.md`.

**Decisions (recorded):**

- **V5A go-live decisions:** seven decisions governing the relaunch — daily/cumulative loss tolerance, market-mode check method, flip timing window, sizing graduation, observer commitment — recorded in `docs/findings/V5A_GO_LIVE_DECISIONS.md`. Override path: chat-side with explicit Jay acknowledgement (appended to the doc as amendments; originals preserved). **The sizing graduation ladder (D-S6 / §2 of the findings doc) is the active rule during the trial** — consult it before any manual sizing change. Roadmap references: Tier 1 `V5A-SIZING-GRADUATION-LADDER-001` (the ladder), Tier 2 `GOVERNANCE-AGENT-MARKET-MODE-001` (D-S4 strategic follow-up, absorbs `MARKET-MODE-001-RE-CALIBRATE-V2`).

**Completed preconditions (historical, verified):**

- [x] **SD_MC_CEILING_002** ✅ DEPLOYED 2026-04-30 ~12:30 UTC. BC-reserves MC compute in SA gate. Verified live 2026-05-14: `SD_MC_CEILING_USD=3000` active on signal_aggregator. See `docs/audits/SD_MC_CEILING_002_DEPLOY_2026_04_30.md`.
- [x] **LIVE-FEE-CAPTURE-002 (Path B)** ✅ DEPLOYED 2026-05-01. `services/helius_parser.py` helper + bot_core live-close wiring using `accountData[*].nativeBalanceChange`. id 6580 backfilled to `corrected_pnl_sol=-0.094245` (exact on-chain match). `correction_method='live_actual_v1'` is the authoritative source for live rows; Path A `live_estimated_v1` remains as automatic fallback on parse failure. See `docs/audits/LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md`. <!-- STALE: §7 row "LIVE-FEE-CAPTURE-002 (Path B) 📋 V5a-blocking-but-degradable" is a stale carry — out of scope for this §6 cleanup; flagged for separate §7 sync session. -->

**Removed preconditions (audit trail):**

- ~~`Confirm SD_EARLY_CHECK relax verdict holds in observation`~~ — removed. TUNE-009 is ⏸ DEFERRED permanently per AGENT_CONTEXT §7 ("empirical data does not support relax"); there is no relax pending. Not a V5A gate. TUNE-009 tracking continues in §7.
- ~~`Renew nansen:disabled Redis TTL`~~ — removed. Mechanism migrated to env var `NANSEN_DRY_RUN=TRUE` on signal_aggregator (verified live 2026-05-14). No Redis renewal needed.
- ~~`Renew market:mode:override Redis TTL`~~ — folded into PC4 flip-time check. Current state (verified 2026-05-14 ~12:57 UTC): key not present, automated `market:mode:current=NORMAL` — override only required if calculation lands non-NORMAL at flip time.

> **⚠ V5a flip-time leak status (carried from 2026-05-01, refreshed 2026-05-14):** the SD-paper-active leaks at flip time are `no_momentum_90s` and `stop_loss_20%`, both rooted in fill-time MC-band exposure. F1 (2026-05-11, $3K) + C1 (2026-05-13, retune to $1K) mitigate these on the paper path — paper KEPT slice on 8.12d sample is 523 trades / +32.62 SOL / 91.4% WR per the C1 STOP-A retest. **Live mode does NOT inherit these mitigations until PC3 (LIVE-MODE-FILTER-PARITY-001-V2) lands** — see §6.5 + LIVE_MODE_FILTER_PARITY_001 audit. Without V2, live relaunch reintroduces $1k–$3k fill-time bleed at sizing factor (~5× MIN_POSITION_SOL=0.05 cap of MAX_POSITION_SOL=0.25). V5A-GO-NO-GO 2026-05-01 recommended caps remain advisory: `MAX_POSITION_SOL=0.10`, `MAX_SD_POSITIONS=5` for first 24h. The `POST-GRAD-ENTRY-GATE-001` mitigation is re-scoped to insurance value only (analyst already disabled).

---

## §6.6 V5A readiness (post-Session-6 audit, 2026-05-01 ~13:00 UTC)

**Current verdict: 🔴 NO_GO** — 3/10 PASS, 4/10 CONDITIONAL, 3/10 FAIL.

**Blockers:**
- 🔴 PC1 wallet capacity: 0.064 SOL on-chain << 0.5 SOL floor. **Jay action: top-up to ~3 SOL.**
- 🔴 PC5 48h observation: <1h since most-recent behavioral deploy (Session 5 LIVE-FEE-CAPTURE-002 at 12:55 UTC). 48h window opens ~2026-05-03 12:55 UTC.
- 🔴 PC7 service health: market:mode:current=HIBERNATE at audit time. Wait for NORMAL window.

**When all 3 blockers resolved, recommended live mode parameters (per CONDITIONAL_GO):**
```
TEST_MODE: false (set on bot_core ONLY; signal_aggregator stays true)
MAX_POSITION_SOL: 0.10 (reduced from 0.25 for first 24h)
MAX_SD_POSITIONS: 5 (reduced from 20 for first 24h)
Suggested duration: 24h before scale-up evaluation
Re-run V5A-GO-NO-GO after 24h
```

**Persistent CONDITIONAL items (do not block GO but track):**
- 🟡 PC3 TIME_PRIME small post-fix sample (forward PASS pending data accumulation)
- 🟡 PC6 ML retune (Session 4 stopped; threshold remains at original env values; reduced confidence)
- 🟡 PC8 ML threshold drift across services (SA=65 / bot_core=40 / web=45)
- 🟡 PC9 recent 7d aggregate -0.98 SOL (mildly negative; degradation watch)

See `docs/audits/V5A_GO_NO_GO_2026_05_01.md` for full evidence + recommendations.

---

## §6.8 Strategy cliff (added 2026-05-07 by STRATEGY-CLIFF-INVESTIGATION-001)

**Cliff date:** 2026-04-20 → 2026-04-21. Magnitude: PRE-cliff archive (`paper_trades_archive_20260421`) shows mean +0.20 SOL/trade on 2,984 SD-paper trades; POST-cliff current shows +0.014 SOL/trade on 528 SD-paper trades.

**Verdict: 🟡 STOP / NO REVERT.** The cliff is **primarily a fee-model accounting artifact**, NOT a strategy regression.

The two eras are not on the same accounting basis:
- PRE rows (archive) were written under the OLD paper fee model that under-counted fees by ~96× per FEE-MODEL-001 (commit `e078b4c`, deployed 2026-04-21 07:26 AEDT)
- POST rows (current) are written under the realistic fee model
- Per-trade fee correction quoted in `e078b4c`: **-0.391 SOL/trade**

**Apples-to-apples calculation (PRE-cliff under realistic fees):**
- PRE-cliff +598 SOL → estimated **-566 SOL** under realistic accounting (mean -0.19 SOL/trade)
- POST-cliff +9.3 SOL (mean +0.014 SOL/trade)
- **Under fair accounting, the new strategy is +0.20 SOL/trade BETTER than the old.**

**Key implication for any future audit:** raw `realised_pnl_sol` is **incomparable across the 2026-04-21 boundary**. To compare across the cliff, either re-derive from raw fields (entry_price, exit_price, amount_sol) under a single fee model OR confine analysis to one side. Default queries that hit only `paper_trades` (current) implicitly choose the latter — that's fine for in-era questions but invalidates "edge collapsed" claims that span the cliff.

**5 follow-up items proposed (all Tier 2 🟢, none V5a-blocking):**
- STRATEGY-CLIFF-FOLLOWUP-001: re-validate at 14d POST sample (≥2026-05-12)
- PRE-DEPLOY-PNL-VALIDATION-001: process improvement (accounting-regime check on cliff investigations)
- BREAKEVEN-DECISION-001: A/B test breakeven lock (PRE: 131 fires, -8.1 SOL realized; POST: 0 fires)
- TP-SCHEDULE-EVAL-001: re-evaluate full ladder TP (PRE had +50/+100/+200/+250/+400/+500/+1000% schedule; POST only +200/+1000%)
- SIGNAL-MIX-ANALYSIS-001: per-gate ablation of HOLDER/BSR/PRE_FILTER/CFGI

**Post-cliff degradation 04-25 onwards is a SEPARATE concern**, not caused by the cliff itself, already tracked via NO-MOMENTUM-90S-AUDIT-001 + ML-THRESHOLD-DATA-DRIVEN-RETUNE-002 + DEFENSIVE-VS-NORMAL-PNL-INVERSION-001.

See `docs/audits/STRATEGY_CLIFF_INVESTIGATION_001_2026_05_05.md` for full evidence (cliff confirmation, FEE-MODEL-001 rebaseline math, exit-reason composition, signal-source REFUTED, MC-band shift, cause-effect mapping, counterfactual estimate, why this wasn't caught earlier).

---

## §6.7 External-API state matrix (post-API-CREDITS-HEALTH-DIAGNOSTIC-001 audit, 2026-05-05 ~14:50 UTC)

> Snapshot from read-only diagnostic (`docs/audits/SERVICE_HEALTH_SNAPSHOT_2026_05_05.md`).
> Rebuild via the §11 reproducibility recipe; refresh if older than 7 days OR after any external-API config change.

| API / dependency | Status | Evidence | Notes |
|---|---|---|---|
| Helius RPC + parseTx | 🟢 | `getNetworkStatus` returned epoch 967, ~1227 TPS; `getBalance(4h4pst…)`= 0.064095633 SOL | All 5 Helius URLs identical across 8 services; single api-key family `0f2e5160-...` |
| PumpPortal WebSocket | 🟢 | signal_listener log: 186 new_token + 157 new_pool signals/8.5min; 0 disconnects | Trade endpoint not probed (would risk real trade); inferred healthy |
| Binance SOL price | 🟢 | `price=85.32` | `service:health.binance` warn 319ms — slightly slow but functional |
| Jupiter V3 SOL price | 🟢 | `usdPrice=85.31`, agreement within $0.03 | `service:health.jupiter` ok 2050ms (slow; watch) |
| Anthropic | 🔴 | governance log 13:55:58: `400 Your credit balance is too low` | **BUG-010 still active.** Falls back to CONSERVATIVE defaults. Jay action: top-up |
| SocialData.tools | 🔴 | signal_aggregator log: 113 `SocialData out of credits` ERROR/11min | `twitter_followers` permanently sentinel `-1`. Promotes SOCIALDATA-AUTO-TOPUP-001 to ACTIVE |
| Vybe | 🔴 | With valid key: `.com/token/...` → 404, `.xyz/token/...` → 404, `.xyz/v4/tokens/...` → 200. signal_aggregator.py:753/850/2568 still use `.com/token/...` | **VYBE-URL-CODE-DRIFT-001 scope expanded 2026-05-08** — fix is URL+path migration to `/v4/tokens/`, not just TLD swap (per VYBE_URL_FIX_2026_05_08.md STOP). v4 Token Details has no `creator` field (L850 affected); `/top-holders` returns `ownerName` not `ownerLabel`/`label` (L2568 affected). Pending VYBE-URL-CODE-DRIFT-001-FIX-V2 |
| Telethon / Telegram | 🟡 | listener connected (2 channel update events in 8.5min); no FloodWait/AuthRestart | channel `cryptoyeezuscalls` quiet during this window — not a session issue |
| Nansen | 🟢 (dormant) | `service:health.nansen` warn HTTP 401; but `NANSEN_DRY_RUN=TRUE` on hot services | Effective consumption ≈ 0 credits. SEC-001 split-key hygiene-only |
| TabPFN | 🟢 | JWT exp = **2027-04-05 04:55:55 UTC** (≈335 days runway) | TABPFN-EXPIRY-DOC-DRIFT: handoff doc said 2033 — wrong by ~6 years |
| Sentry | 🟢 | Distinct DSN per service across all 8; release `ea0da2f89164` matches main HEAD | Release tagging active for V5a flip retrospectives |
| Railway | 🟢 | All 8 services running; all started in same ~21-min window | Confirms `RAILWAY-REDEPLOY-DISCIPLINE-001` (no `paths` filter on docs commits) |
| Discord webhook | 🔴 | signal_listener: 2× `403 lacks permission` per 5min | `BUG-020` still firing — permission/role config issue |
| Discord bot read | n/a | (carryover BUG-020) | |

**Treasury Helius gate:** `services/treasury.py:60` early-returns None when `HELIUS_DAILY_BUDGET=="0"` (treasury env doesn't set the var). This produces 270+ misleading `WARNING: Could not fetch trading wallet balance` per 22h. Helius RPC itself is healthy — this is **TREASURY-HELIUS-LOG-NOISE-001** (rename WARN to reflect the gate, not connectivity). Currently dormant because wallet=0.064 SOL << 30 SOL trigger.

**Dashboard health-check probe depth:** `service:health.anthropic = ok "key configured"` — only checks env-var presence, NOT actual API responsiveness. While BUG-010 is active this status is **misleading**. New tracking item `DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001`.

**ML AUC=0.0000:** `ml:model:meta.auc=0.0000` after 7109-sample retrain at 14:00 UTC — separate ML quality investigation. Feature coverage 13-14/55 = 24-25% (CLAUDE.md Issue #2). Not API-related.

**V5a impact:** None of the 4 🔴 findings are V5a-blocking by current gating rules. Original V5a blockers (wallet 0.064 SOL, 48h observation, NORMAL window) unchanged.

---

## §6.5 Known leaks under investigation (post-Session-4 correction, 2026-05-01)

> **Session 4 correction (2026-05-01):** Session 3 H2 attributed the post-grad bleed (-14.60 SOL/14d on 280 trades) as "structural across personalities". Session 4 personality breakdown shows ALL 280 graduation_* exits are from `analyst`, NOT speed_demon. Analyst is disabled since 2026-04-28 13:02 UTC (ANALYST-DISABLE-002). **The post-grad bleed has ALREADY STOPPED.** SD has 0 post-grad entries. POST-GRAD-ENTRY-GATE-001 has been re-scoped to insurance value only.

| Leak | 14d attribution | Personality | Status | Patch path |
|---|---:|---|---|---|
| `no_momentum_90s` (pre-grad) | −8.48 SOL on 423 trades (14d pre-2026-05-12); −3.47 SOL on 202 trades W4 post-F1 alone | speed_demon (paper) | ⏸ MITIGATED 2026-05-13 — `NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001` deployed C1 ($1000) | **Diagnosis:** structural MC-band cliff, not exit-timer bug. nm90 is the visible symptom of $1k-3k MC tokens being net-negative regardless of exit reason. F1 ($3K ceiling, deployed 2026-05-11) cleared the deepest tier; the next tier was $1k-3k. **Sole discriminator:** market_cap_at_entry (trail_win p75=$720 / max=$892 vs nm90 p25=$2615 — zero overlap). All other features (ml_score, rugcheck, liq_velocity, cfgi, bc_progress, age) identical across groups. **Patch deployed:** `BOT_CORE_FILL_MC_CEILING_USD` retuned 3000 → 1000 at 2026-05-13 03:29:21Z UTC (Jay-authorized fast-track; T1 audit skipped per audit §12). STOP-A retest pre-deploy on 8.12d sample confirmed marginal ROI +1.49 SOL/day (W3+W4) / +3.02 SOL/day (W4-only); 0 FP winners. Eval at +14d (≥2026-05-27) via folded NO-MOMENTUM-90S-EVAL-001 (bundled with STOP-LOSS-20-RUG-FILTER-EVAL-001). Audit: `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md`. |
| `stop_loss_20%` (pre-grad) | −8.00 SOL on 119 trades / 14d (post-investigation: −10.43 SOL on 128 trades / 14d, −14.65 SOL on 186 trades / 17d POST-cliff) | speed_demon (paper) | ⏸ MITIGATED 2026-05-11 — `STOP-LOSS-20-RUG-FILTER-DEPLOY-001` deployed F1 at $3,000 | F1 fill-time MC ceiling deployed via `services/paper_trader.paper_buy` (default OFF in code; Railway env `BOT_CORE_FILL_MC_CEILING_USD=3000` on bot_core). Counterfactual ROI **+1.38 SOL/day** at deploy time (9.5d sample). Eval at +14d via STOP-LOSS-20-RUG-FILTER-EVAL-001 (queued ≥2026-05-25): decide keep/tighten/loosen + live-mode parity in execution.py. |
| Historical `graduation_*` (analyst) | −14.60 SOL on 280 trades / 14d | analyst (DISABLED since 2026-04-28) | ⏸ STOPPED via `ANALYST_DISABLED=true` | None needed — bleed already stopped. Insurance: `POST-GRAD-ENTRY-GATE-001` (re-scoped to Tier 2) layered atop ANALYST_DISABLED for safety. |
| **ML threshold not enforced on paper** | — (constraint, not direct loss) | all (paper) | ⏸ STOP per Session 4 §8 | `BOT-CORE-ML-GATE-001` (Tier 1) — add second ML gate at bot_core to make env changes take effect. Recommended threshold = 55 per sweep. |

**Interpretation:** With analyst disabled, the SD-paper bleed was dominated by `no_momentum_90s` and `stop_loss_20%` (combined ~-16.5 SOL/14d on 542 trades pre-deploys). Both leaks shared the same root cause — fill-time MC band exposure. **As of 2026-05-13:** F1 ($3K ceiling, deployed 2026-05-11) handles the `stop_loss_20%` rug tier. C1 retune ($1K ceiling, deployed 2026-05-13 03:29:21Z UTC) handles the `no_momentum_90s` $1k-$3k tier. Same env var (`BOT_CORE_FILL_MC_CEILING_USD`), same lever family — successive tightening. KEPT slice in counterfactual on 8.12d sample: 523 trades, +32.62 SOL, 91.4% WR. ML threshold retune is data-supported (optimum 55) but blocked by AGGRESSIVE_PAPER+TEST_MODE override; the bot_core-side gate (`ML_THRESHOLD_BOT_CORE_SD=40` since 2026-05-05) is the only paper-effective ML filter. Awaiting ≥7d post-gate clean data for ML_THRESHOLD_RETUNE_002.

**For V5a decision:** the historical post-grad bleed has stopped (analyst disabled) so V5a is NOT blocked on that mitigation. SD-paper-active leaks remain (no_momentum_90s + stop_loss_20%); these would amplify on live at sizing factor. Recommended V5a flip caps: `MAX_POSITION_SOL=0.10` (vs current 0.25) for first 24h to limit blast radius until live data confirms paper-to-live edge ratio.

---

## §7 Known unresolved (Tier-1 carry)

| ID | status | notes |
|---|---|---|
| ML-THRESHOLD-DRIFT-2026-04-29 | 🟡 | SA=65 / bot_core=40 / web=45; effective gate < 40 due to AGGRESSIVE_PAPER bypass. 44 of last 100 closes have ml_score ∈ (0,40]. |
| TREASURY-TEST-MODE-002 | 🟡 | treasury alone has TEST_MODE=false. Dormant but latent. |
| LIVE-FEE-CAPTURE-002 (Path B) | 📋 | V5a-blocking-but-degradable. Helius parseTransactions for actual fill data. Slippage-tier fix (FEE-LATENCY-REALISM-2026-04-30) closes ~30% of Path A's id 6580 gap; remaining gap requires Path B. |
| LATENCY-OBSERVABILITY-001 (NEW) | 📋 | All 4 latency columns NULL on 1182 paper_trades. 4-file refactor required (signal_listener + signal_aggregator + paper_trader + bot_core + Redis-payload schema). Not V5a-blocking. |
| MARKET-MODE-001-RE-CALIBRATE (NEW) | 📋 | 24h observation post-fix to validate threshold distribution; re-tune if NORMAL fires constantly during quiet hours or AGGRESSIVE never fires during peak. Sample size = 2 readings during fix. |
| MARKET-LOSS-OVERRIDE-DEAD-CODE-001 (NEW) | 📋 | `rug_cascade_monitor` writes `market:loss_override` Redis key; no reader. Either wire into `_determine_market_mode` (DEFENSIVE-cap behavior) or remove the writer. Code hygiene; low priority. |
| PUMPPORTAL-STATS-API-001 (NEW) | 📋 | Replace `pumpfun_vol_estimate = dex_vol * 0.15` placeholder with real PumpPortal stats endpoint (Patch 1C deferred). Observability improvement. |
| LIVE-CLOSE-FALLBACK-INSERT-001 | 📋 | bot_core.py:1330 legacy 21-column INSERT not extended with new columns. Low-traffic path. |
| TUNE-009 (SD_EARLY_CHECK relax) | ⏸ DEFERRED | empirical data does not support relax — see audit §6 conditions for re-evaluation. |
| SD_MC_CEILING_001 | ⚠️ SUPERSEDED | _002 replaces inert gate. Keep marker for git-history reference. |
| SD_MC_CEILING_002 | ✅ DEPLOYED 2026-04-30 ~12:30 UTC | BC-reserves MC compute in SA gate. Step 6 + 24h verification queued. |
| TIME_PRIME-CONTRADICTION-001 | ✅ DEPLOYED 2026-05-01 | Resolved via env-driven multiplier (defaults disabled). State: TIME_PRIME disabled (multiplier=1.0, hours=""). See `docs/audits/TIME_PRIME_CONTRADICTION_FIX_2026_04_30.md`. New follow-ups: TIME-PRIME-AEDT-AEST-DRIFT-001 (LOW), TIME-PRIME-CALIBRATION-001 (MEDIUM). |
| TUNE-006 (other components) | 📋 | SD_DEAD_ZONE_001, SD_ML_THRESHOLD_LIFT 40→50 — deferred from chain A-D. |
| TUNE-005-ROLLBACK validation | 📋 | 24h window closes ~2026-04-30 09:34 UTC. Decide codify-rollback vs reapply. |
| SILENCE-RECOVERY (post-2026-04-25 EMERGENCY_STOP) | ✅ CLEARED | bot recovered between 2026-04-28 13:02 UTC (first close) and 2026-04-30 (current). |

For the full Tier-1/2/3 list see `ZMN_ROADMAP.md`.

---

## §8 Recent Redis state snapshot (2026-05-08 ~13:21 UTC, refreshed by STATE-SNAPSHOT-2026-05-08)

| key | value | notes |
|---|---|---|
| bot:status | RUNNING, paper portfolio 24.83 SOL, daily_pnl=+0.41 SOL, test_mode=true, market_mode=NORMAL, 1 open partial position (mint GnNFCenU…, +339% unrealised — staged_tp_+200% partial exit, 80% remaining; cosmetic, not a ghost-cache bug) | 27s TTL |
| bot:emergency_stop | (absent) | not tripped |
| bot:loss_pause_until | (not checked this session) | — |
| bot:consecutive_losses | 1 | — |
| market:mode:current | **NORMAL** | thresholds determining (probe expired) |
| market:mode:override | **(absent — DEFENSIVE-OVERRIDE-PROBE-001 EXPIRED 2026-05-07 22:29 UTC, no renewal)** 🔴 | probe ran 24h before lapsing; sample n=54 underpowered; eval session needs decision (re-run with renewal or use thin sample) |
| market:sol_price | 88.37 USD | fresh |
| market:health | mode=NORMAL, cfgi_sol=46 (cfgi.io primary), dex_volume_24h $1.75B | fresh ~30s old |
| governance:latest_decision | mode=CONSERVATIVE; reasoning="classification failed: Error code: 400 ... 'Your cred..." | 🔴 BUG-010 still firing (Anthropic credit exhaustion confirmed) |
| nansen:disabled | (absent — TTL expired) | renewal needed if Nansen budget enforcement matters; NANSEN_DRY_RUN=TRUE on SA effectively neutralizes |
| signal_aggregator:health | ok at 2026-05-08 13:20:57 UTC | 4s before audit fetch — fresh |
| **bot_core:health** | **(absent — OBS-014 still open)** | bot_core lacks heartbeat key |

**Action items from snapshot (2026-05-08):**
- 🔴 DEFENSIVE-OVERRIDE-PROBE expired without renewal at 2026-05-07 22:29 UTC. Eval session must decide: re-run with renewal vs accept underpowered 24h sample (n=54).
- 🔴 Anthropic credits still exhausted (BUG-010). Top-up required for governance to function beyond CONSERVATIVE fallback.
- bot_core still lacks heartbeat key — OBS-014 cleanup.
- Holding wallet drift 0.0098 → 0.190 SOL since 2026-04-29; treasury is dormant — confirm with Jay.

---

## §9 DB state snapshot (2026-04-30 ~09:00 UTC)

| metric | value | source |
|---|---|---|
| paper_trades total | **1138 closed** | snapshot 2026-04-30 08:53 UTC |
| paper_trades open | 0 currently | confirmed via Redis + DB |
| BUG-022 status | **0 NULL closed rows; 1137 pass_through; 1 live_v1** | Session B fix verified post-deploy |
| `correction_method='pass_through'` | 1137 | Session B inline write working |
| `correction_method='live_estimated_v1'` | 1 (id 6580) | Session D backfill |
| `trade_mode='live'` rows | 6 total | id 6580 = real on-chain (live_estimated_v1); ids 6575-6579 = reconcile-residual paper closures with NULL signatures (pass_through, fees=0, slip=0) |

For exact counts at-time-of-need, run `python .tmp_session_e/snapshot.py` (gitignored; see §11).

---

## §10 Where to read more

| topic | file |
|---|---|
| Recent audits (last 30 days) | `docs/audits/` |
| Decision history | `ZMN_ROADMAP.md` "Decision Log" section (added Session E 2026-04-30) |
| Session-by-session activity | `STATUS.md` (newest entry at top) |
| Persistent rules + conventions | `CLAUDE.md` |
| Memory drift report | `docs/audits/USERMEMORIES_DRIFT_2026_04_30.md` (Session E) |
| Per-service env inventory | `docs/audits/ENV_AUDIT_2026_04_29.md` §2 (refresh if older than 3 days) |
| Live trading wallet history | `docs/audits/WALLET_DRIFT_INVESTIGATION_2026_04_29.md` |
| Live PnL fee-capture spec + impl | `docs/audits/LIVE_FEE_CAPTURE_PATH_A_2026_04_30.md` |
| BUG-022 pass-through fix | `docs/audits/BUG_022_FIX_2026_04_30.md` |
| no_momentum_90s deferral | `docs/audits/SD_EARLY_CHECK_RELAX_2026_04_30.md` |
| MC ceiling rollback | `docs/audits/SD_MC_CEILING_DEPLOY_2026_04_30.md` |

---

## §11 Reproducibility

To refresh §8 + §9 + §3 with current values:

```python
# .tmp_session_e/snapshot.py — reads Redis + DB; gitignored
python .tmp_session_e/snapshot.py
```

```python
# Trading wallet balance via Helius MCP
mcp__helius__getBalance(address="4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ")
```

Per-service env via Railway MCP:
```python
mcp__railway__list-variables(service="<bot_core|signal_aggregator|treasury|...>", kv=true)
```

---

## §12 Timezone convention (added 2026-05-05 by TIMEZONE-AUDIT-001)

**Rule:** All time-based **decision** logic (entry filters, sizing
multipliers, gates, scheduled-task firing branches, daily/weekly window
rollovers) MUST resolve the timezone dynamically via
`zoneinfo.ZoneInfo("Australia/Sydney")` (preferred, stdlib in 3.9+) or
`pytz.timezone("Australia/Sydney")` (existing convention in
`market_health.py` and `governance.py`). All **storage** timestamps MUST
use `datetime.now(timezone.utc)`. All **display** layers SHOULD use
`Australia/Sydney` (Postgres `AT TIME ZONE`, JS `toLocaleString` with
`timeZone:'Australia/Sydney'`).

**Forbidden:** hardcoded fixed offsets — `timezone(timedelta(hours=N))`,
`+10:00`, `+11:00`, `_td(hours=11)`, etc. — for any decision/scheduling
purpose.

**Legitimate UTC-by-design exception:** when a decision is genuinely
UTC-anchored (e.g. `services/risk_manager.py:160-174`
`_time_of_day_multiplier` global market-session bands; the
`signals_aggregator` `hour_of_day` ML feature). Such uses MUST be
commented as `# UTC by design` with a one-line rationale.

**Pending 🔴 fixes (production code):** **1** — `TIME-PRIME-AEDT-AEST-DRIFT-001`
(`services/bot_core.py:754,776`). Single fix-point in
`_compute_position_size_for_signal` clears both lines. See
`docs/audits/TIMEZONE_AUDIT_2026_05_05.md` for the full sweep.

**Audit:** `docs/audits/TIMEZONE_AUDIT_2026_05_05.md` (TIMEZONE-AUDIT-001,
2026-05-05). Verified `services/market_health.py` is fully DST-aware via
pytz Australia/Sydney.

---

═══════════════════════════════════════════════════════════════
HISTORICAL ARCHIVE — pre-2026-04-30 content preserved below
═══════════════════════════════════════════════════════════════

The content below is the prior `AGENT_CONTEXT.md` as of April 5 2026.
**Newer state above takes precedence.** This archive is kept for API
reference, DB schemas, and historical context that hasn't been
re-written in audits or CLAUDE.md.

═══════════════════════════════════════════════════════════════
AGENT CONTEXT UPDATE — April 5, 2026
Prepend this section to the TOP of AGENT_CONTEXT.md
Keep all existing sections below — they contain API reference,
DB schemas, and other details that are still relevant.
═══════════════════════════════════════════════════════════════
Section 0: Critical Current State (READ FIRST)
0.1 — System Architecture (FIXED April 3)
Each of the 8 Railway services runs ONLY its assigned service via
SERVICE_NAME env var in main.py. This was the #1 bug — previously
all 8 services ran ALL code via asyncio.gather(), causing 8x duplicate
trades, 8x API costs, and 0 working exit strategies.
DO NOT change main.py SERVICE_NAME routing. It is correct.
0.2 — Exit Price Pipeline — FIXED April 9-13

Historical note: the exit price pipeline was BROKEN for weeks before
being progressively fixed in a chain of commits:

- 26e19b4: exit pricing pipeline initial fix
- 9b880e1: paper_trader price pass-through (resolved the 20.4% of
  contaminated historical trades)
- 5b92226: staged TP P/L sums across all exits (resolved residual
  exit overwriting cumulative P/L)
- a8a390b: feature defaults -1 not 0 (unblocked entry filter v4)

The original bug: exit checker tried Jupiter/GeckoTerminal first (both
always fail for bonding-curve tokens), only falling back to Redis
token:latest_price too late. Result was 1800+ trades with zero TPs.

The fix reordered price sources: Redis token:latest_price first, then
bonding curve reserves, then Jupiter, then Gecko.

Current state (April 13+): staged TPs fire at 100% rate (verified
20/20 in post-fix data). Exit pipeline is working correctly. Do not
revert these commits. Do not reintroduce the old price source order.

For the full fix history see MONITORING_LOG.md entries for April 9-13.
0.3 — Price Format Mismatch (critical to understand)
paper_buy() stores entry_price in USD (from Jupiter/GeckoTerminal)
PumpPortal trade stream stores prices in SOL (sol_amount / token_amount)
Redis token:latest_price stores SOL denomination
Exit checker MUST convert SOL→USD before comparing to entry_price
Conversion: usd_price = sol_price_per_token × market:sol_price
If market:sol_price is missing, fallback to $80 (fragile)
Always fetch SOL/USD price in same batch as token prices
### Railway deploy rules
- `git push origin main` → auto-deploys via GitHub webhook (DEFAULT)
- `railway up` → also triggers deploy (USE ONLY when skipping git)
- NEVER use both together. Duplicate deploys waste build minutes.
- Env var changes in Railway UI → triggers deploy of that service only
- Batch env var changes with `railway variables --set A=X --set B=Y`
  in ONE call to avoid N redeploys

0.4 — Trading Performance (2026-04-17 — current)

Trading wallet: 3.6774 SOL (mainnet, 1.32 SOL spent in v4 live window)
Treasury wallet: 0.0984 SOL
Mode: Paper (TEST_MODE=true) — safe following cd266de deploy.
  Authorization for `TEST_MODE=false` is governed by `CLAUDE.md` "Live
  trading mode — session-gated" (single source of truth; 4 preconditions
  per session).

Live trial history:
- v1 (2026-04-16 22:00 AEDT): FAILED — solders .sign() removed in 0.21+
- v2 (2026-04-17 08:00 AEDT): FAILED — populate() invalid signatures
- v3 (2026-04-17 10:00 AEDT): SIGNING VERIFIED (0 SigFail in 83 attempts),
  BLOCKED by stale paper positions filling MAX_SD_POSITIONS=2
- v4 (overnight → 2026-04-17 ~08:23 AEDT):
  Briefing described as EMPTY. Actual: PARTIAL SUCCESS once
  HELIUS_RPC_URL appeared at 06:37 — 50+ TX_SUBMITs, 10+ OK on-chain
  signatures, zero SignatureFailure. Wallet 5.0 → 3.677 SOL.
  7,448 "no Helius URL" errors were sell attempts against zombie paper
  positions in bot_core's in-memory state (TEST_MODE flipped without
  restart). Not a trade-path failure.
- v5: READY after cd266de deploy settles. Restart bot_core before flipping
  TEST_MODE=false to clear in-memory positions.

0.5 — Execution URL resolution (2026-04-17)

`services/execution.py` now reads URLs in this order for tx submission:
- `_execute_pumpportal_local`: STAKED, RPC, GATEKEEPER
- `_send_transaction`: STAKED, RPC, GATEKEEPER
- `_get_dynamic_priority_fee`: RPC, GATEKEEPER (read-only)
- `_get_token_balance`: RPC, GATEKEEPER (read-only)

Startup validation: if TEST_MODE=false and all three URLs are empty,
the module raises RuntimeError at import. Fails loudly rather than
looping quietly (which is what produced the 7,448-error overnight
storm before the fix).

0.6 — Sell-storm circuit breaker (2026-04-17)

bot_core parks a mint after `SELL_FAIL_THRESHOLD` (default 8) consecutive
live-sell ExecutionErrors. Parked mints get silent-skipped for
`SELL_PARK_DURATION_SEC` (default 300). One retry allowed after cool-off.
PARK event logged to live_trade_log with `event_type=ERROR,
extra.parked=True`. Kill switch: set `SELL_FAIL_THRESHOLD=1000` on bot_core.

Paper trading (current):
- Exit pipeline healthy, ~8 entries per 15 min
- Win rate last 50: ~36%
- Ghost position Redis cache cleaned (1,458 stale from April 5)

Dashboard state:
- LIVE view: all zeros (no live trades yet)
- PAPER view: current activity
- OPEN POSITIONS + RECENT TRADES: MCAP columns (USD)
- Mode toggle filters all main widgets

## Dashboard Data Source Notes (2026-04-13)

Dashboard has a "Known Bugs Registry" in DASHBOARD_AUDIT.md. All
dashboard P/L widgets use COALESCE(corrected_pnl_sol, realised_pnl_sol)
with post-cleanup window filter (entry_time > 1775767260) after
2026-04-13 Tier 1 session.

CFGI displayed on dashboard is from Alternative.me Bitcoin F&G (value=12).
Jay expected CMC index (~42). This is NOT a display bug -- it's a data
source decision pending Jay's review. Both bot_core and signal_aggregator
use the same Alternative.me source for trading decisions.

### Post-Stage-2 State (2026-04-15)

Stage 2-minus cutover completed. Key changes:

1. **CFGI source swapped.** `market:health.cfgi` now holds cfgi.io SOL
   value as primary, with Alternative.me BTC as fallback. BTC preserved
   as `market:health.cfgi_btc`. **Currently in fallback mode** because
   cfgi.io returns 402 (credits exhausted). When credits restored,
   SOL value auto-activates.

2. **Analyst hard-disabled.** ANALYST_DISABLED=true env var on
   signal_aggregator. Analyst showed 0/3 WR (all 0-2s holds,
   stop_loss_20%) in 348-trade post-recovery window. Do not re-enable
   until the hold pattern is investigated.

3. **Mode unchanged.** HIBERNATE persists because BTC fallback is active
   (CFGI=21). When cfgi.io credits restored (SOL CFGI ~62), mode
   may transition to NORMAL. Speed Demon sizing may increase from
   0.75x toward 1.0x.

### Service Configuration Snapshot (2026-04-15)

Key env vars:
- TEST_MODE=true (paper mode)
- AGGRESSIVE_PAPER=true (bypasses HIBERNATE gating)
- ANALYST_DISABLED=true (Stage 2-minus)
- CFGI_API_KEY set on market_health (cfgi.io, 100k credits topped up)
- HELIUS_ENRICHMENT_ENABLED=false (credit exhaustion until Apr 26)

### B-011 + B-012 Fix State (2026-04-15)

1. **B-011 RESOLVED:** paper_sell and bot_core._close_position now
   write `outcome` column on trade exit. 2,966 historical NULL
   outcomes backfilled from P/L sign. `WHERE outcome = 'win'` queries
   now return correct data. Distribution: 448 win, 3,647 loss,
   1 breakeven.

2. **B-012 CLOSED (false positive):** STAGED_TP_FIRE log line IS
   firing correctly in bot_core. Confirmed with live data (e.g.,
   DbQwDAWL +50% at 1.90x, +100% at 2.45x). TP redesign data IS
   accumulating. Earlier report of 0 matches was due to Railway log
   stream timeout limitation.

3. **cfgi.io credits topped up.** 100k credits. SOL CFGI now active
   as primary: 41.5. Mode still HIBERNATE (mode determined by DEX
   volume thresholds in _determine_market_mode, not CFGI directly).
   CFGI affects Analyst pause threshold and Speed Demon sizing
   multiplier, but the mode gate is volumetric.

### TP Redesign Experiment (2026-04-15 11:32 UTC)

First experimental change to Speed Demon exit strategy. A/B test with
explicit revert criteria (see MONITORING_LOG.md).

Config: 50/100/250/500/1000% at 30/30/20/10/10 (vs baseline
50/100/200/400% at 25% each). Env var STAGED_TAKE_PROFITS_JSON on
bot_core. No code change — semantic is still % of remaining.

During observation window (ends 2026-04-17 ~11:32 UTC), NO other
changes to bot_core, Speed Demon, exit strategy, or entry filter.
Multiple concurrent changes prevent attributing results to the TP
change specifically.

Baseline: TP_BASELINE_2026_04_15.md
Revert procedure: MONITORING_LOG.md (TP redesign entry)

### Shadow Trading Measurement (Phase 1, 2026-04-15)

bot_core emits SHADOW_MEASURE events to stdout + Redis
`shadow:measurements` list (48h TTL, 10k cap). Three events:
ENTRY_FILL, EXIT_DECISION, STAGED_TP_HIT. Paper-only instrumentation.
Does not affect trading. Early finding: staged TP overshoot is 23-29%
(bot fires at 1.85x when trigger is 1.5x due to 2s exit checker cycle).
Phase 2 analysis after 24h of data accumulation.
See: SHADOW_MEASUREMENT_PLAN.md

### Shadow Phase 2 + Execution Audit (2026-04-16)

Shadow analysis of 2,959 measurements over 20h found:
- Winner survival rate: 90.9% (STRONG — 9/10 paper wins survive live)
- Median execution discount: 19% (paper overstates by ~1/5)
- Staged TP overshoot: 20-49% (bot fires above trigger, favorable)
- Peak-to-exit gap: median 28.2% (trailing stop reaction latency)

Execution audit found ALL infrastructure exists (execution.py):
- Jupiter V2 swap, PumpPortal local, Jito bundle, Helius RPC
- Trading wallet: 5.00 SOL funded on mainnet
- Clean TEST_MODE branch in bot_core (paper vs live paths)
- 1 gap: position floor hard-coded at 0.15 SOL, need 0.05 for trial

See: SHADOW_ANALYSIS_2026_04_16.md, EXECUTION_AUDIT_2026_04_16.md

### Dashboard Real Wallet Displays (2026-04-16)

Dashboard top bar now shows real on-chain SOL balances:
- TRADE: trading wallet (TRADING_WALLET_ADDRESS) via Helius getBalance, 30s cache
- TREASURY: holding wallet (HOLDING_WALLET_ADDRESS) via Helius getBalance, 60s cache
- CFGI(BTC) removed, only CFGI (SOL from cfgi.io) displayed
- B-013 DEFERRED: symbol column empty, paper_buy doesn't populate it
- B-014 OBSOLETE: BTC display removed

### External API Audit + Helius Switch (2026-04-16)

Every external service tested. Helius Staked was Secure RPC (5 TPS,
all 522). **FIXED:** switched to Standard RPC (48ms median, 20/20
burst). Gatekeeper beta kept as fallback (430ms, 20/20 burst).

Bot now uses:
- HELIUS_STAKED_URL = Standard RPC (mainnet.helius-rpc.com) — fastest
- HELIUS_GATEKEEPER_URL = Gatekeeper beta (beta.helius-rpc.com) — backup
- HELIUS_RPC_URL = Standard RPC (unchanged)
- Secure RPC (ardith-...) removed permanently (5 TPS per IP limit)

Go/No-Go: **READY for live trial.** All execution APIs confirmed.
See: EXTERNAL_API_AUDIT.md

### Trade Mode Segregation (2026-04-16)

paper_trades has `trade_mode` column ('paper' or 'live', DEFAULT 'paper').
Set on INSERT from TEST_MODE env var. Dashboard API filters key queries
by mode (status, trades, positions). ?mode=paper|live override param.
Dashboard HTML has mode badge + toggle dropdown. When TEST_MODE flips
to false, new trades get 'live', dashboard auto-shows LIVE view (zero
counters). Paper history preserved for ML training and analysis.

### Tip/Fee Configurability (2026-04-16)

execution.py: JITO_TIPS_LAMPORTS and PRIORITY_FEE_TIERS are env-var
driven. Defaults match pre-session hardcoded values. Override via:
JITO_TIP_LAMPORTS_NORMAL/COMPETITIVE/FRENZY,
PRIORITY_FEE_TIER_1_SOL through _5_SOL. EXECUTION_CONFIG log on boot.
Tip tuning is REACTIVE — only adjust if live fee burn exceeds projected
0.0042 SOL/trade.

Trial safety env vars on bot_core: MAX_SD_POSITIONS=2,
DAILY_LOSS_LIMIT_SOL=1.0 (hardcoded), MAX_TRADES_PER_HOUR=500.

### Live Trial v1 + v2 Post-Mortem (2026-04-16/17)

**v1 (Apr 16 22:00 AEDT):** 244/244 `.sign()` AttributeError.
**v2 (Apr 17 08:00 AEDT):** `populate()` compiles but produces
invalid signatures. On-chain `SignatureFailure` from validators.

**v3 fix (ce86cd5):** Use `VersionedTransaction(tx.message, [keypair])`
constructor. Neither `.sign()` nor `populate()` work. The constructor
is the only API that correctly signs a deserialized VersionedTransaction.
Verified locally with realistic SOL transfer instruction round-trip.

**Signing is the SOLE blocker for live trading.** All other
infrastructure (Helius, Jupiter, PumpPortal, Jito, wallet, safety
rails, dashboard, trade_mode segregation) is ready.

Wallet untouched at 5.0 SOL across both trials. Zero trades
ever landed on-chain.

### Ghost Position Cache Bug (2026-04-17)

Redis `bot:status` accumulated 1,458 positions from April 5 that
were never removed when paper_trades rows were closed. Dashboard
API reads bot:status first, showing ghost positions.

Cleaned: DEL bot:status + 176 paper:positions:* keys.
Dashboard now shows 2 actual open positions from DB fallback.

**Bug still exists in code:** bot_core publishes positions to
bot:status but never removes closed ones from the Redis cache.
Needs code fix: when a position is closed, also delete it from
bot:status and paper:positions:{mint}.

### Dashboard Mode Filter Complete (2026-04-17)
All main dashboard widgets filter by trade_mode. LIVE view = zeros.
OPEN POSITIONS skips Redis bot:status when mode=live (Redis only holds
paper). Both OPEN POSITIONS and RECENT TRADES use MCAP columns (USD).

## Service Monitoring Rule (added 2026-04-14)

signal_aggregator now writes a health heartbeat to
`signal_aggregator:health` every 30 seconds with a 120s TTL.
If this key is missing or stale, signal_aggregator is dead.

Before assuming the bot is idle due to HIBERNATE mode or market
conditions, ALWAYS check this health heartbeat first. A silent dead
signal_aggregator was the cause of a 21-hour outage on 2026-04-13.

0.5 — Personality Status
Personality    Trades    Wins    PnL SOL    WR    Status
Speed Demon    511    19    -9.25    3.7%    Trading — 0.7x sizing, momentum gates active
Analyst    1,206    35    -11.05    2.9%    Trading — 1.3x sizing, best consistency
Whale Tracker    2    0    -0.04    0%    BROKEN — 44 wallets in DB, 0 in Redis cache
0.6 — ML Model Status
Engine: CatBoost + LightGBM ensemble (Phase 3)
AUC: 0.889 on 1,729 labeled samples
Features populated: 20/58 (34%) — 38 features always zero
Zero features: Nansen (disabled, 9 features), Helius (disabled, 8 features),
creator history (5), trade data timing (6+), other (10)
Thresholds: SD=50, AN=55, WT=55
AGGRESSIVE_PAPER_TRADING=true on signal_aggregator and bot_core
(thresholds not enforced — collecting unbiased training data)
ML metadata NOT stored in Redis — dashboard can't display AUC/features
0.7 — API Status
API    Status    Auth    Notes
PumpPortal    ONLINE    No auth needed    Primary signal source. subscribeTokenTrade for exit pricing.
Jupiter    ONLINE    JUPITER_API_KEY    Price API v3. REQUIRES x-api-key header. Returns 401 without.
GeckoTerminal    ONLINE    No auth    Trending pools, token prices. Free.
RugCheck    ONLINE    No auth    Risk scoring with graduated multiplier.
Vybe    ONLINE    VYBE_API_KEY    Holder labels (CEX/KOL/MM), wallet PnL. Base URL: api.vybenetwork.xyz (NOT .com — DOCS-004 fix 2026-04-30)
Nansen    PAUSED    NANSEN_API_KEY    508% over budget. Disabled via Redis. Smart money discovery when re-enabled.
Anthropic    DEAD    ANTHROPIC_API_KEY    Credits exhausted. Governance non-functional. Needs top-up.
SocialData    IDLE    SOCIALDATA_API_KEY    $10.10 balance, 0 requests ever. Pump.fun tokens lack Twitter URLs.
Helius    PAUSED    HELIUS_API_KEY    Budget=0. NOT used for pricing. Was used for tx confirmation.
Discord    ONLINE    DISCORD_WEBHOOK_URL    Trade notifications. Webhook may need regeneration (403).
0.8 — Dashboard Status (14 panels)
All 14 panels render with the retro green CRT theme (VT323, scanlines, #00FF41).
Issues remaining:
ML Status: AUC="--", Features="--" (model metadata not stored in Redis)
Whale panel: shows "44 wallets" but no leaderboard/stats
Governance: shows raw text, needs structured display
Win rates: correct but labels unclear (WR10/25/50 not intuitive)
Recent trades: missing market cap, hold time
Open positions: usually empty (positions close within 5-10 min)
Exit analysis: no "profitable" count per exit reason
0.9 — Key Commits (last 30)
8719d63 fix: stale exits don't count toward consecutive losses
577aa74 fix: ML status and signal funnel data improvements
d1f2c7b fix: force close stale positions with no price data
0ea4335 fix: check both token:price and token:latest_price
45bad06 fix: persist peak_price to DB
6dfb56b fix: load existing token subscriptions on startup
ceaaaa1 fix: Decimal serialization in exit-analysis endpoint
266850f feat: store signal evaluations in Redis for dashboard
31204fd feat: token subscribe/unsubscribe for live exit pricing
5b509db feat: per-token trade subscription for exit pricing
a4b8265 feat: complete dashboard redesign — all 14 panels
7a122fd feat: live trade stats via Redis for ML features
80b0ece fix: staged exits before time_exit, SD sizing
feb994b feat: cache PumpPortal trade prices in Redis
ef8e196 fix: move momentum gates after feature extraction
d0b13ba fix: gitignore package.json, restore railway.toml
1fe497e fix: respect risk manager rejection (max(0.15) override)
b731f80 fix: bsr default 1.0→0, threshold 1.2→0.8
(+ ~20 more commits from overnight sessions)
0.10 — Database Tables (key ones)
paper_trades: all paper trade records (entry/exit/pnl/features/ml_score)
Has: staged_exits_done, peak_price, signal_source, rugcheck_risk
Missing: market_cap_at_entry (should be added)
trades: ML training table (features_json, outcome, ml_score)
portfolio_snapshots: balance history for equity curve
watched_wallets: qualified whale wallets (address, win_rate, pnl, source)
bot_state: key-value store for persistent state
0.11 — LetsBonk.fun / Bonk.fun Coverage
PumpPortal already delivers Bonk.fun/LaunchLab tokens via the same WebSocket.
LaunchLab program ID: LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj
Platform detection is implemented in signal_listener.py.
Execution layer supports launchlab and bonk pool types.
Pump.fun has 70-80% of bonding curve market share (not 18% as previously stated).
0.12 — Graduation Sniper
Implemented in signal_aggregator.py:
signal_listener pushes migration events to signals:graduated
Aggregator waits 60s, checks rugcheck + holder count + KOL presence
Holder threshold: 25 minimum (was 100, lowered)
Graduated tokens bypass KOTH zone and ML threshold
Exit: 95% at +30%, 5% moonbag with 15% trailing, -20% stop, 20min window
Results so far: 5+ graduation events detected, all rejected (high rug risk)
0.13 — KOTH Zone
King of the Hill zone narrowed from 30-55% to 45-65% bonding curve progress.
ML override threshold lowered from 85 to 60.
Velocity bypass: if bc_progress increasing >0.5%/s, token has momentum → bypass KOTH.
Tokens at 36-40% are EARLY with momentum, not stalled.

# ZMN Bot — Agent Context Document
**Version:** 3.1
**Last Updated:** March 2026
**Changes from v3.0:**
- Jupiter migrated from lite-api.jup.ag to api.jup.ag with V3 price API
- Rugcheck score threshold corrected (unbounded integer, not 0-100)
- DexPaprika SSE migrated to streaming.dexpaprika.com
- Vybe domain changed from .xyz to .com
- Helius webhook URL migrated to api-mainnet.helius-rpc.com
- Governance agent v2: memory, anomaly detection, parameter approval, two-way Discord
- Dashboard v4: commercial-grade terminal with JWT auth, command palette, keyboard shortcuts
- Paper trading infrastructure with full simulation
- Sydney timezone scheduling for all governance tasks
- All API URLs verified and corrected (see Section 21)

**Purpose:** Complete context for an autonomous coding agent. Read this entire file before writing a single line of code. Do not rely on memory of previous versions — this document supersedes all prior versions.

---

## 1. Project Overview

ZMN Bot is a **Solana memecoin trading bot** with three concurrent AI personalities, ML scoring, real-time market health detection, an agent governance layer, and a web dashboard. It executes trades directly on-chain via two clean REST APIs (no Telegram dependency), validates tokens through Rugcheck, and monitors the market via multiple on-chain and off-chain data feeds.

**Deployment:** Railway.app  
**Language:** Python 3.11+ (async/await throughout — no sync/blocking calls anywhere)  
**DB:** SQLite (`toxibot.db`) via `aiosqlite`  
**Queue:** Redis for inter-service communication  
**Dashboard:** HTML/CSS/JS (Satoshi template — needs repurposing per Section 13)  
**Starting capital:** 20+ SOL  
**Holding wallet:** Separate Phantom wallet — receives swept profits above 30 SOL threshold

---

## 2. Repository Structure

```
/
├── AGENT_CONTEXT.md              ← this file (always read first)
├── requirements.txt              ← see Section 20 for full list
├── .gitignore
├── Procfile                      ← Railway process definitions
├── railway.toml                  ← Railway service config
├── .env.example                  ← all required env vars, no values
│
├── services/
│   ├── signal_listener.py        ← PumpPortal WS + GeckoTerminal + DexPaprika
│   ├── signal_aggregator.py      ← dedup, score, ML gate, route to personalities
│   ├── market_health.py          ← daily/intraday market condition detector
│   ├── bot_core.py               ← trading engine, personality coordinator
│   ├── ml_engine.py              ← CatBoost + LightGBM ensemble (legacy)
│   ├── ml_model_accelerator.py   ← Phase 3 ensemble engine (ACTIVE — requires ML_ENGINE=accelerated)
│   ├── train_accelerated.py      ← training script for accelerated model
│   ├── risk_manager.py           ← quarter-Kelly, drawdown scaling, position sizing
│   ├── execution.py              ← PumpPortal Local + Jupiter Ultra + Jito + retry
│   ├── treasury.py               ← SOL sweep: trading wallet → holding wallet
│   ├── governance.py             ← Claude API governance agent (scheduled)
│   └── dashboard_api.py          ← WebSocket server feeding live data to dashboard
│
├── data/
│   ├── whale_wallets.json        ← curated wallet list with scores
│   ├── market_baselines.json     ← rolling 7-day baseline cache
│   ├── governance_notes.md       ← agent writes recommendations here for review
│   ├── memetrans/                ← MemeTrans training dataset (gitignored)
│   └── models/
│       ├── accelerated_model.pkl ← trained Phase 3 model (41,470 samples)
│       └── model_meta.json       ← training metadata (phase, AUC, features)
│
├── db/
│   └── migrations/               ← numbered SQL migration files
│
└── dashboard/
    ├── dashboard.html            ← Bot Overview
    ├── dashboard-analytics.html  ← Performance & ML
    └── dashboard-wallet.html     ← Live Trade Feed
```

**Files that do NOT yet exist and must be built:**
All files under `services/`, `data/`, `db/migrations/`, Procfile, railway.toml, .env.example.

---

## 3. The Three Bot Personalities

All three run **concurrently** and share a single ML learning pipeline. Never disable one to run another. If two personalities would enter the same token simultaneously, reduce the second entry's position by 50%. Never allow more than 2 personalities in the same token at once.

---

### Speed Demon ⚡ (Ultra-Early Hunter)

**Mission:** First-mover on brand new pump.fun bonding curve tokens using tiered entries.

**Execution method:** PumpPortal Local API (`/api/trade-local`) — bonding curve only.

**Signal sources:**
- PumpPortal `subscribeNewToken` WebSocket (primary — sub-100ms)
- GeckoTerminal `/networks/solana/new_pools` (backup — poll 60s)
- DexPaprika SSE stream (tertiary)

**Tiered entry system:**

| Tier | Window | ML threshold | Position size | Key conditions |
|------|--------|-------------|--------------|----------------|
| Alpha Snipe | 0–30 sec | ≥ 80% | 0.5–1 SOL | No bundle, diverse wallets, high liq velocity |
| Confirmation | 30 sec–3 min | ≥ 65% | 0.3–0.5 SOL | Positive dev signals, healthy holders |
| Post-Grad Dip | 5–15 min post-migration | ≥ 70% | 0.5–1 SOL DCA × 2 | Token graduated, mcap $30–50K, dip confirmed |

**Entry hard filters (reject if ANY fail):**
- `liquidity_sol > 5`
- Bonding curve progress NOT in 30–55% range (KOTH dump zone) — unless ML ≥ 85%
- `bundle_detected == False`
- `bundled_supply_pct < 10%`
- Dev sold <20% of holdings in first 2 minutes
- Creator has <3 dead tokens in last 30 days
- `bot_transaction_ratio < 0.60`
- `fresh_wallet_ratio < 0.40`

**Exit strategy (staged — not a single TP):**
- Sell **40%** at 2× — recover investment
- Sell **30%** at 3× — lock profit
- Keep **30%** as moon bag with 30% trailing stop
- Time-based exit: if no positive movement in 5 minutes from entry, close entire position
- Signal-based hard exits (immediate): dev wallet sells >20%, bundle dump detected, buyer diversity collapses, Rugcheck risk score spikes

**Stop loss:** 50% absolute floor for alpha snipe. Once in profit >30%, switch to 30% trailing stop.

---

### Analyst 🔍 (Data-Driven Researcher)

**Mission:** Medium-term positions (5 min – 2 hours) on confirmed tokens using multi-source signals.

**Execution method:** Jupiter Ultra API for post-graduation tokens (`/swap/v1/`). PumpPortal Local API for tokens still on the bonding curve (when Analyst enters pre-graduation).

**Signal sources:**
- BitQuery GraphQL streams
- GeckoTerminal trending pools
- Vybe Network token analytics
- Nansen Smart Money flows (if subscribed)

**Signal stack (by predictive weight):**
1. Liquidity velocity (2× weight in ML) — SOL per trade in first 30 sec
2. Holder concentration — top 10 wallets combined <25%
3. Volume acceleration — 3×+ increase in any 15-min window
4. Unique buyer growth — >20 new holders in first 30 min
5. Buy/sell ratio — >1.2× = healthy, <1.0 = reject

**Entry criteria:**
- `liquidity_sol > 10`
- 2+ independent sources agree on signal
- ML score ≥ 70%
- Token NOT already held by Speed Demon (if yes, wait 5 min and halve position)
- Bonding curve progress in 20–30% OR >60% (avoid 30–60% KOTH zone)

**Exit strategy:**
- Sell **30%** at 1.5×
- Sell **30%** at 2.5×
- Sell **25%** via 25% trailing stop from peak
- Keep **15%** as moon bag — 40% trailing stop, 2-hour maximum hold

**Stop loss:** 30% from entry. Time-based: exit if no movement in 30 minutes.

---

### Whale Tracker 🐋 (Smart Money Follower)

**Mission:** Copy-trade systematically identified profitable wallets.

**Execution method:** Jupiter Ultra API for graduated tokens. PumpPortal Local API for bonding curve tokens that whales are buying.

**Signal sources:**
- PumpPortal `subscribeAccountTrade` (tracked wallets list)
- Helius webhooks on tracked wallet addresses
- Vybe Network labeled wallets
- Nansen Smart Money Dashboard (weekly refresh)

**Wallet scoring pipeline (maintain 50–100 wallets, score weekly):**

| Dimension | Weight | Minimum threshold |
|-----------|--------|-------------------|
| Win rate | 25% | >55% |
| Avg ROI per trade | 20% | >50% |
| Trade frequency (per week) | 15% | 5–50 |
| Realized PnL (SOL/month) | 15% | >10 SOL |
| Consistency (low std dev) | 15% | — |
| Hold period alignment | 10% | 5 min – 4 hr |

**Auto-disqualify wallets with ANY of:** win rate >90%, hold time <30s, all profit from one token, wallet age <7 days, >200 trades/day.

**Entry criteria:**
- Wallet score ≥ 70/100
- `holders > 100`
- ML score ≥ 70%
- 3+ tracked whales in same token within 1 hour → treat as maximum confidence, enter immediately

**Copy-trade delay by tier:** Top 10 wallets (score ≥ 85) → 0–5 seconds. Mid-tier (70–85) → 15–30 seconds.

**Accumulation vs. distribution:** If tracked whale sends >10% of token position to a CEX address → immediately exit or reduce copy position by 50%.

**Exit strategy:**
- Sell **30%** at 2×
- Sell **40%** at 5×
- Keep **30%** as runner — 25% trailing stop, 4-hour maximum hold
- Immediate exit if whale starts selling (detected via subscribeAccountTrade)

---

## 4. Risk Management (Hard Rules — Never Override in Code)

### Quarter-Kelly position sizing

```python
# Kelly: f* = (b * p - q) / b   Quarter Kelly: f = f* * 0.25
KELLY_PARAMS = {
    "speed_demon":   {"win_rate": 0.35, "avg_win": 2.00, "avg_loss": 0.50},  # ~4.7% quarter Kelly
    "analyst":       {"win_rate": 0.45, "avg_win": 1.00, "avg_loss": 0.30},  # ~7.1% quarter Kelly
    "whale_tracker": {"win_rate": 0.40, "avg_win": 1.50, "avg_loss": 0.40},  # ~6.0% quarter Kelly
}

# Final position = quarterKelly × volatilityRatio × drawdownMultiplier × streakMultiplier × timeOfDayMultiplier
# Cap at per-personality max AND portfolio limits below. Never skip a multiplier.
```

### Hard position limits

```python
MAX_POSITION_PCT = {
    "speed_demon":   0.03,   # 3% of portfolio (~0.6 SOL on 20 SOL)
    "analyst":       0.05,   # 5% (~1.0 SOL)
    "whale_tracker": 0.04,   # 4% (~0.8 SOL)
}
MIN_POSITION_SOL            = 0.10   # Below this, fees destroy edge
MAX_CONCURRENT_PER_PERSONALITY = 3
MAX_CONCURRENT_WHALE        = 2
PORTFOLIO_MAX_EXPOSURE      = 0.25   # 25% total — never exceed
RESERVE_FLOOR_PCT           = 0.60   # Always keep 60% in reserve
DAILY_LOSS_LIMIT_SOL        = 1.0    # 5% of 20 SOL — triggers EMERGENCY_STOP
CORRELATION_HAIRCUT         = 0.70   # pump.fun tokens ~70% correlated
```

### Drawdown-based position scaling

```python
DRAWDOWN_MULTIPLIERS = {
    (0.00, 0.05):  1.00,
    (0.05, 0.10):  0.75,
    (0.10, 0.15):  0.50,
    (0.15, 0.20):  0.25,
    (0.20, 1.00):  0.00,   # >20% drawdown: STOP ALL TRADING
}
CONSECUTIVE_LOSS_MULTIPLIERS = {0: 1.0, 1: 1.0, 2: 0.85, 3: 0.65, 4: 0.50, 5: 0.25}
```

### Time-of-day multipliers

```python
TIME_OF_DAY_MULTIPLIERS = {
    (0,  4):  0.70,   # Asia
    (4,  8):  0.55,   # Dead zone
    (8,  12): 0.90,   # EU opens
    (12, 17): 1.00,   # Peak: EU+US overlap
    (17, 21): 0.90,   # US afternoon
    (21, 24): 0.70,   # Declining
}
WEEKEND_MULTIPLIER = 0.70   # Fri eve–Sun: lower volume + concentrated rug risk
```

### EMERGENCY_STOP triggers

When ANY of these fire → halt all three personalities simultaneously, cancel pending orders, send Discord alert, log reason, require manual restart:
- `daily_pl_sol <= -1.0`
- `portfolio_drawdown_pct >= 0.20`
- Network: veryHigh priority fees >50M microlamports for >10 consecutive minutes
- RUG CASCADE: >10 tokens dropped >80% in same 5-minute window
- SOL price drops >10% in 24h
- Treasury sweep fails 3× in a row (possible wallet compromise — halt and alert)

---

## 5. Execution Layer (v3.0 — PumpPortal Local + Jupiter Ultra)

**The Telethon/ToxiBot approach is completely removed. All execution goes through two official REST APIs. No Telegram dependency anywhere in the execution path.**

---

### Primary: PumpPortal Local API (bonding curve tokens)

Used by: Speed Demon (all tiers), Analyst/Whale Tracker (pre-graduation tokens only).

```
Endpoint: POST https://pumpportal.fun/api/trade-local
Fee: 0.5% per trade (calculated before slippage)
Custody: Full — API builds the transaction, YOU sign and send it
Key feature: Supports pump, raydium, pump-amm, launchlab, raydium-cpmm, bonk, auto
```

**Implementation pattern:**
```python
import aiohttp
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair

async def execute_pumpportal(
    action: str,          # "buy" or "sell"
    mint: str,            # token contract address
    amount_sol: float,
    slippage_pct: int,
    priority_fee_sol: float,
    pool: str = "auto"
) -> str:
    payload = {
        "publicKey": TRADING_WALLET_PUBLIC_KEY,
        "action": action,
        "mint": mint,
        "amount": amount_sol,
        "denominatedInSol": "true",
        "slippage": slippage_pct,
        "priorityFee": priority_fee_sol,
        "pool": pool
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://pumpportal.fun/api/trade-local",
            json=payload
        ) as resp:
            if resp.status != 200:
                raise ExecutionError(f"PumpPortal error: {resp.status}")
            tx_bytes = await resp.read()

    # Sign with trading wallet keypair (key loaded from env, never hardcoded)
    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx = VersionedTransaction.deserialize(tx_bytes)
    tx.sign([keypair])

    # Send via Helius staked RPC (better landing rate than public RPC)
    signature = await helius_rpc.send_transaction(tx)
    return signature
```

**Slippage config for PumpPortal:**
```python
PUMPPORTAL_SLIPPAGE = {
    "alpha_snipe":   25,   # 0–30 sec entries, high volatility
    "confirmation":  15,   # 30 sec–3 min entries
    "post_grad_dip": 10,   # post-graduation dip entries
    "sell":          10,   # sells
}
```

---

### Secondary: Jupiter Swap API (graduated/AMM tokens)

Used by: Analyst (primarily), Whale Tracker (primarily), Speed Demon (post-graduation Tier 3 entries when pool is deep enough).

```
Quote: GET https://api.jup.ag/swap/v1/quote
Swap:  POST https://api.jup.ag/swap/v1/swap
Price: GET https://api.jup.ag/price/v3?ids=<mints>  (price field: "usdPrice")
Auth:  x-api-key header with JUPITER_API_KEY env var (free at portal.jup.ag)
Fee: 0% protocol fee — only Solana network fees
MEV protection: ShadowLane private transaction routing built in
DEPRECATED: lite-api.jup.ag — do not use in new code
Does NOT handle: pump.fun bonding curve tokens — use PumpPortal for those

Sell note: _get_token_balance() fetches actual token balance via Helius RPC
getTokenAccountsByOwner before executing sell. amount_sol on sells represents
SOL value of position, not the token amount passed to Jupiter.
```

**Implementation pattern:**
```python
import aiohttp

async def execute_jupiter_ultra(
    input_mint: str,      # "So11111111111111111111111111111111111111112" for SOL
    output_mint: str,     # token mint address
    amount_lamports: int,
    slippage_bps: int
) -> str:
    # Step 1: Get quote
    async with aiohttp.ClientSession() as session:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_lamports,
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": False,
        }
        headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
        async with session.get(
            "https://api.jup.ag/swap/v1/quote", params=params, headers=headers
        ) as resp:
            quote = await resp.json()

        # Step 2: Get swap transaction
        swap_payload = {
            "quoteResponse": quote,
            "userPublicKey": TRADING_WALLET_PUBLIC_KEY,
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": await get_dynamic_priority_fee(),
        }
        async with session.post(
            "https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers
        ) as resp:
            swap_data = await resp.json()

    # Step 3: Sign and send
    import base64
    from solders.transaction import VersionedTransaction
    tx_bytes = base64.b64decode(swap_data["swapTransaction"])
    tx = VersionedTransaction.deserialize(tx_bytes)
    keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    tx.sign([keypair])
    signature = await helius_rpc.send_transaction(tx)
    return signature
```

**Slippage config for Jupiter Ultra:**
```python
JUPITER_SLIPPAGE_BPS = {
    "graduated_deep":    50,    # 0.5% — pools >$1M liquidity
    "graduated_medium":  150,   # 1.5% — pools $100K–$1M
    "graduated_shallow": 350,   # 3.5% — pools <$100K
}
```

---

### Routing decision: which API to use

```python
PUMPPORTAL_POOLS = {"pump", "pump-amm", "launchlab", "bonk"}
JUPITER_POOLS = {"raydium", "raydium-cpmm", "orca", "meteora", "pumpswap"}

def choose_execution_api(token: Token) -> str:
    if token.pool in PUMPPORTAL_POOLS and token.bonding_curve_progress < 1.0:
        return "pumpportal"   # Still on bonding curve — must use PumpPortal
    elif token.pool in JUPITER_POOLS:
        return "jupiter"      # Graduated to AMM pool — use Jupiter
    else:
        return "pumpportal"   # Default to PumpPortal with pool="auto"
```

---

### Jito MEV protection (wrap all PumpPortal transactions)

```python
JITO_ENDPOINT = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
JITO_DONTFRONT_PUBKEY = "jitodontfront111111111111111111111111111111"

JITO_TIPS_LAMPORTS = {
    "normal":       1_000_000,    # 0.001 SOL
    "competitive":  10_000_000,   # 0.01 SOL
    "frenzy_snipe": 100_000_000,  # 0.1 SOL — hard maximum, never exceed
}
# Add JITO_DONTFRONT_PUBKEY as read-only account on every swap instruction
# Jupiter Ultra has MEV protection built in — no Jito wrap needed for Jupiter trades
```

---

### Transaction retry config

```python
RETRY_CONFIG = {
    "max_retries":      5,
    "initial_delay_ms": 500,
    "backoff_factor":   1.5,
    "escalate_fee":     True,    # bump priority fee tier on each retry
    "preflight":        True,    # enable on attempt 1, skip on retries 2+
    "commitment":       "confirmed",
    "encoding":         "base64",
}
```

---

## 6. Treasury Sweep Service (`services/treasury.py`)

**Purpose:** Automatically transfer excess SOL from the trading wallet to the holding wallet, preventing catastrophic loss of all capital if a trade goes catastrophically wrong or the bot is compromised.

### Rules (hard-coded — never make these configurable at runtime)

```python
TREASURY_RULES = {
    "trigger_threshold_sol": 30.0,   # Only sweep when trading wallet exceeds this
    "target_balance_sol":    25.0,   # Leave this much in trading wallet after sweep
    "min_transfer_sol":       1.0,   # Never transfer less than this (prevents dust sweeps)
    "holding_wallet":        HOLDING_WALLET_ADDRESS,  # From env — never hardcoded
    "check_interval_seconds": 300,   # Poll every 5 minutes
    "max_retries":            3,     # Retry failed sweeps up to 3 times
    "sweep_priority_fee":     0.000005,  # Low priority — this is not time-sensitive
}
```

### Sweep logic

```python
async def run_treasury_sweep():
    """
    Run continuously. Every 5 minutes:
    1. Check trading wallet SOL balance (use Helius RPC getBalance)
    2. If balance > 30 SOL:
       a. Calculate transfer amount = balance - 25.0 SOL
       b. If transfer_amount < 1.0 SOL: skip (below minimum transfer threshold)
       c. Build SOL transfer transaction (SystemProgram.transfer)
       d. Sign with trading wallet keypair
       e. Send via Helius RPC (NOT Jito — this is a simple SOL transfer, low priority)
       f. Log to SQLite: timestamp, amount_swept, trading_balance_before, trading_balance_after
       g. Send Discord notification: "Treasury sweep: {amount} SOL → holding wallet. Trading balance: {after} SOL"
    3. If sweep fails: log error, increment failure counter
    4. If 3 consecutive failures: trigger EMERGENCY_STOP and alert Discord
       (consecutive failures may indicate wallet compromise or RPC issue)
    """
    pass  # Agent implements this
```

### Sweep transaction implementation

```python
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey

async def execute_treasury_sweep(amount_sol: float) -> str:
    amount_lamports = int(amount_sol * 1_000_000_000)
    trading_keypair = Keypair.from_base58_string(TRADING_WALLET_PRIVATE_KEY)
    holding_pubkey = Pubkey.from_string(HOLDING_WALLET_ADDRESS)

    ix = transfer(TransferParams(
        from_pubkey=trading_keypair.pubkey(),
        to_pubkey=holding_pubkey,
        lamports=amount_lamports
    ))

    blockhash = await helius_rpc.get_latest_blockhash()
    tx = Transaction(
        recent_blockhash=blockhash.value.blockhash,
        fee_payer=trading_keypair.pubkey(),
        instructions=[ix]
    )
    tx.sign([trading_keypair])
    signature = await helius_rpc.send_transaction(tx)
    return str(signature)
```

### Sweep dashboard display

The dashboard must show a **Treasury panel** on `dashboard.html`:
- Trading wallet current balance (SOL)
- Holding wallet current balance (SOL — read-only query, no private key needed)
- Sweep threshold indicator (progress bar: current balance vs 30 SOL trigger)
- Last sweep: timestamp + amount
- Total swept to date (SOL)
- Sweep history (last 10 sweeps)

### Security notes

- `HOLDING_WALLET_ADDRESS` is a **public key only** — never put the holding wallet's private key anywhere in the system
- The bot can only transfer TO the holding wallet, never from it
- Holding wallet private key stays in Phantom, accessed manually by the owner only
- The sweep is one-directional by design — even if the trading bot is fully compromised, the attacker can only drain 25 SOL (trading balance floor), not the accumulated holdings

---

## 7. Agent Governance Layer (`services/governance.py`)

**Purpose:** A separate scheduled process that calls the Anthropic Claude API to perform reasoning-level oversight that deterministic rules cannot handle — wallet scoring, anomaly diagnosis, strategy parameter recommendations. It never touches trade execution.

### What the governance agent does (and does not do)

**Does:**
- Weekly: Re-score whale wallet list using Vybe/Nansen data, write updated `whale_wallets.json`
- Daily: Interpret composite market health score and write a plain-English daily briefing to `governance_notes.md`
- On drawdown event: Diagnose what went wrong (bad signal? bad market? parameter issue?) and write recommendations
- On 3+ consecutive losses per personality: Suggest specific parameter adjustments (tighter stops, higher ML threshold, etc.)
- On anomalous token patterns: Flag unusual activity for human review
- Monthly: Write a performance report summarising what's working and what isn't

**Does NOT:**
- Make live trade decisions
- Write directly to any config that affects live execution without human review
- Override EMERGENCY_STOP
- Modify `MAX_WALLET_EXPOSURE`, `DAILY_LOSS_LIMIT_SOL`, or position sizing hard caps
- Automatically deploy any code changes

### Implementation

```python
import anthropic
import json
from datetime import datetime

GOVERNANCE_SCHEDULE = {
    "wallet_rescore":     "weekly",    # Every Monday 02:00 UTC
    "daily_briefing":     "daily",     # Every day 06:00 UTC
    "drawdown_diagnosis": "triggered", # On drawdown event from Redis pub/sub
    "loss_streak_review": "triggered", # On 3+ consecutive losses
    "monthly_report":     "monthly",   # First of month 06:00 UTC
}

async def run_governance_task(task_type: str, context_data: dict):
    """
    Calls Claude API (claude-sonnet-4-6) with relevant data.
    Writes output to governance_notes.md and/or whale_wallets.json.
    Never writes to execution config directly.
    """
    client = anthropic.AsyncAnthropic()

    system_prompt = """You are the governance agent for ToxiBot, a Solana memecoin trading bot.
    Your role is strategic oversight — you analyse performance data, score whale wallets,
    and make recommendations. You never make live trading decisions.
    Write clearly and concisely. All output will be reviewed by the bot owner before any
    parameter changes are applied. Flag anything unusual. Be direct about problems."""

    user_prompt = build_governance_prompt(task_type, context_data)

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": user_prompt}]
    )

    output = message.content[0].text
    await write_governance_output(task_type, output, context_data)
    await notify_discord(f"Governance: {task_type} complete — check governance_notes.md")
```

### Governance prompts by task type

```python
def build_governance_prompt(task_type: str, context: dict) -> str:
    if task_type == "wallet_rescore":
        return f"""
Review the following whale wallet performance data from the past 7 days and provide
an updated score (0–100) for each wallet. Remove wallets that no longer meet minimum
thresholds. Suggest any new wallets from the top trader lists that should be added.

Current wallet list: {json.dumps(context['current_wallets'], indent=2)}
Performance data (7 days): {json.dumps(context['performance_data'], indent=2)}
Vybe top trader data: {json.dumps(context['vybe_data'], indent=2)}

Output: Valid JSON array matching the whale_wallets.json schema. Nothing else.
"""

    elif task_type == "daily_briefing":
        return f"""
Write a concise daily briefing for the ToxiBot owner. Cover:
1. Yesterday's performance (P/L, win rate, best/worst trade per personality)
2. Current market condition and whether the HIBERNATE/DEFENSIVE/NORMAL/AGGRESSIVE/FRENZY
   mode seems correct given what you see in the data
3. Any anomalies or concerns worth flagging
4. One specific recommendation if something looks off

Data: {json.dumps(context, indent=2)}

Be direct. No fluff. Max 300 words.
"""

    elif task_type == "drawdown_diagnosis":
        return f"""
ToxiBot has hit a significant drawdown. Analyse the recent trade history and diagnose
the root cause. Was this a market condition problem, a signal quality problem, a position
sizing problem, or something else? Be specific about which trades caused the most damage
and why.

Drawdown details: {json.dumps(context['drawdown_info'], indent=2)}
Recent trades (last 48h): {json.dumps(context['recent_trades'], indent=2)}
Market conditions during drawdown: {json.dumps(context['market_conditions'], indent=2)}
Signal sources that triggered losing trades: {json.dumps(context['signal_sources'], indent=2)}

Provide: (1) root cause diagnosis, (2) specific parameter changes to consider,
(3) whether trading should resume or stay paused. Be direct.
"""

    elif task_type == "loss_streak_review":
        return f"""
{context['personality']} has had {context['consecutive_losses']} consecutive losses.
Review the losing trades and determine whether this is:
a) Bad luck in a volatile market (no action needed — resume at reduced sizing)
b) A signal quality issue (specific signal sources to stop trusting temporarily)
c) A parameter issue (specific thresholds to adjust)
d) A market regime change (the personality's strategy isn't suited to current conditions)

Losing trades: {json.dumps(context['losing_trades'], indent=2)}
Current parameters: {json.dumps(context['parameters'], indent=2)}

Provide: diagnosis + specific recommendation. One paragraph max.
"""

    elif task_type == "monthly_report":
        return f"""
Write a monthly performance report for ToxiBot. Include:
1. Overall P/L and Sharpe ratio
2. Per-personality breakdown (Speed Demon, Analyst, Whale Tracker)
3. ML model accuracy trend
4. Best performing signal sources
5. Worst performing signal sources (consider dropping)
6. Treasury sweep summary (total swept to holding wallet)
7. Top 3 recommendations for next month

Data: {json.dumps(context, indent=2)}
"""
    return ""
```

### Governance output handling

```python
async def write_governance_output(task_type: str, output: str, context: dict):
    timestamp = datetime.utcnow().isoformat()

    if task_type == "wallet_rescore":
        # Parse JSON output and write to whale_wallets.json
        # IMPORTANT: Write to whale_wallets_pending.json first
        # Bot owner must manually rename to whale_wallets.json to activate
        # This prevents auto-activation of AI-generated wallet changes
        updated_wallets = json.loads(output)
        with open("data/whale_wallets_pending.json", "w") as f:
            json.dump(updated_wallets, f, indent=2)
        # Notify owner to review and approve
        await notify_discord(
            "Whale wallet rescore complete. Review data/whale_wallets_pending.json "
            "and rename to whale_wallets.json to activate. Changes NOT yet live."
        )
    else:
        # All other outputs → append to governance_notes.md
        with open("data/governance_notes.md", "a") as f:
            f.write(f"\n\n---\n## {task_type} — {timestamp}\n\n{output}\n")
```

### Governance triggers via Redis

```python
# Bot core publishes these events to Redis when thresholds are hit
GOVERNANCE_TRIGGERS = {
    "drawdown:significant":    "drawdown_diagnosis",  # drawdown > 10%
    "streak:loss":             "loss_streak_review",   # 3+ consecutive losses/personality
}
# Governance service subscribes to these channels and fires the appropriate Claude API call
```

### Governance check-in frequency — deliberate decision

Governance runs on a strategic schedule only (daily 7am Sydney, weekly Monday, anomaly detection every 30min). Do NOT add more frequent market check-ins to governance. Reason: `market_health.py` already monitors every 5 minutes intraday and publishes to Redis in real-time. Governance is for strategic oversight only. Adding hourly or 6-hourly market check-ins would duplicate monitoring and create unnecessary Anthropic API costs. If more frequent automated analysis is needed, extend `market_health.py` not `governance.py`.

---

## 8. Market Health Detection (`services/market_health.py`)

### Market modes and thresholds

| Mode | Pump.fun 24h vol | Graduation rate | Solana DEX vol | Effect |
|------|-----------------|----------------|---------------|--------|
| HIBERNATE | <$50M | <0.5% | <$1.5B | No new positions |
| DEFENSIVE | $50M–$100M | 0.5–0.8% | $1.5B–$2.5B | 0.5× sizing, tighter stops |
| NORMAL | $100M–$500M | 0.8–1.0% | $2B–$4B | Full operation |
| AGGRESSIVE | $200M–$500M | >1.0% | >$4B | 1.25× sizing |
| FRENZY | >$500M | >1.5% | >$6B | 1.5× sizing (watch for reversal) |

Publish current mode to Redis pub/sub channel `market:mode` — all services subscribe and immediately apply multipliers on mode change.

### Daily composite sentiment score (0–100)

```python
sentiment_score = (
    cfgi_fear_greed_index          * 0.30 +
    graduation_rate_z_score_scaled * 0.25 +
    sol_24h_change_scaled          * 0.20 +
    dex_volume_z_score_scaled      * 0.15 +
    launch_rate_z_score_scaled     * 0.10
)
```

### Intraday real-time checks (every 5 minutes)

```python
# Rug cascade
rugged = count_tokens_dropped(pct=0.80, window_minutes=5)
if rugged > 5:  trigger_rug_alert()     # halt new entries
if rugged > 10: trigger_emergency_halt() # exit all positions

# SOL price shock (check every 60 seconds)
if sol_change_1h < -0.05:  halt_new_entries()
if sol_change_24h < -0.10: trigger_emergency_stop()

# Network congestion (check every 30 seconds)
if helius_priority_fee["veryHigh"] > 50_000_000:  # 50M microlamports
    halt_trading("network_congested")
```

### Market health data sources

- DefiLlama: `GET https://api.llama.fi/overview/dexs/Solana` (chain is PATH param, not query)
- CFGI: `GET https://cfgi.io/api/solana-fear-greed-index/1d` (no public docs, falls back to 50.0)
- SOL price: `GET https://api.jup.ag/price/v3?ids=So11...112` (field: `usdPrice`)
- Network fees: Helius `getPriorityFeeEstimate`
- Token launch rate: Count PumpPortal `subscribeNewToken` events per window

### Known limitations
- Pump.fun volume estimated as 15% of total Solana DEX volume (no direct API)
- Graduation rate defaults to 1.0% baseline (refined as signal_listener counts migrations)
- CFGI API has no public documentation — falls back to neutral 50.0 if unavailable

---

## 9. Data API Stack

### Existing APIs (keep)
| API | Cost | Primary use |
|-----|------|-------------|
| Helius | $49/mo | RPC, webhooks, priority fee estimation, staked tx landing |
| Vybe Network | Free | Labeled wallets, creator history, top traders |
| PumpPortal | Free data / 0.5% trades | WebSocket signals + trade execution |
| Jupiter | Free | Ultra swap API + price data |
| Rugcheck | Free | Token safety scoring |
| Dexscreener | Free | Token metadata backup |

### New APIs (add)
| API | Cost | Primary use |
|-----|------|-------------|
| Vybe Network | Free (4 req/min) | Labeled wallets, whale wallet scoring |
| GeckoTerminal | Free (30 req/min) | New pool detection, trending, OHLCV |
| DexPaprika | Free (SSE) | Tertiary signal stream |
| DefiLlama | Free | Market health — Solana DEX volume |
| CFGI | Free | Solana Fear & Greed Index |
| Nansen Pro | $49/mo optional | Smart money tracking, wallet PnL leaderboards |
| Birdeye Lite | $39/mo optional | Trending tokens, holder analytics |

### Dropped completely
- **Telethon** — no longer needed for execution
- **ToxiBot (@toxi_solana_bot)** — replaced by PumpPortal Local + Jupiter Ultra
- All Telegram session management code

---

## 10. Environment Variables (Complete — v3.0)

```bash
# === BLOCKCHAIN ===
HELIUS_API_KEY=                    # helius.dev — Developer tier $49/mo
HELIUS_RPC_URL=                    # https://mainnet.helius-rpc.com/?api-key=...
JITO_ENDPOINT=https://mainnet.block-engine.jito.wtf/api/v1/bundles

# === TRADING WALLETS ===
TRADING_WALLET_PRIVATE_KEY=        # Base58 private key — NEVER commit, env only
TRADING_WALLET_ADDRESS=            # Public key of trading wallet
HOLDING_WALLET_ADDRESS=            # Public key ONLY — no private key needed/allowed

# === TREASURY ===
TREASURY_TRIGGER_SOL=30.0          # Sweep when trading wallet exceeds this
TREASURY_TARGET_SOL=25.0           # Leave this much after sweep
TREASURY_MIN_TRANSFER_SOL=1.0      # Minimum single transfer amount

# === DATA APIS ===
JUPITER_API_KEY=                   # Free at https://portal.jup.ag
VYBE_API_KEY=                      # vybenetwork.com (free tier)
NANSEN_API_KEY=                    # nansen.ai (auth header: "apikey" lowercase)
DISCORD_OWNER_ID=                  # Your Discord user ID for !zmn commands

# === GOVERNANCE ===
ANTHROPIC_API_KEY=                 # From console.anthropic.com — for governance agent
GOVERNANCE_MODEL=claude-sonnet-4-6 # Model to use for governance tasks

# === ALERTS ===
DISCORD_WEBHOOK_URL=               # Discord webhook for alerts + daily briefings
DISCORD_WEBHOOK_TREASURY=          # Separate channel for treasury sweep notifications

# === INFRASTRUCTURE ===
REDIS_URL=                         # Railway Redis plugin
DATABASE_URL=sqlite:///toxibot.db
DASHBOARD_SECRET=                  # JWT secret for dashboard auth

# === RUNTIME ===
ENVIRONMENT=development            # 'development' or 'production'
TEST_MODE=true                     # true = detect signals, never execute trades
STARTING_CAPITAL_SOL=20
LOG_LEVEL=INFO
ML_ENGINE=accelerated              # REQUIRED — "accelerated" for Phase 3 ensemble, "original" for legacy
SPEED_DEMON_FILTERS_ENABLED=true   # Enable social/bundle/rugcheck pre-filters
DEXPAPRIKA_ENABLED=false           # Disabled — SSE returns HTTP 400
SPEED_DEMON_BASE_SIZE_SOL=0.45     # Default position size
SPEED_DEMON_MAX_SIZE_SOL=0.75      # Max position for high confidence
MAX_SD_POSITIONS=3                 # Max concurrent Speed Demon positions
MIN_BALANCE_SOL=2.0                # Minimum wallet balance before trading halts
DAILY_LOSS_LIMIT_PCT=0.10          # 10% daily loss limit

# === DATA APIS (additional) ===
SOCIALDATA_API_KEY=                 # socialdata.tools — Twitter follower lookups (NOT SOCIAL_DATA_API_KEY)
HELIUS_STAKED_URL=                  # Staked RPC for faster confirmations

# === NO LONGER NEEDED (removed in v3.0) ===
# TELEGRAM_API_ID — removed
# TELEGRAM_API_HASH — removed
# TELEGRAM_SESSION — removed
# TELEGRAM_SIGNAL_CHANNELS — removed
# TOXI_BOT_USERNAME — removed
```

---

## 11. Signal Stack Architecture (v3.0)

```
Layer 1 — On-chain primary (self-owned, zero Telegram dependency)
  ├── PumpPortal WebSocket: wss://pumpportal.fun/api/data
  │     subscribeNewToken        → Speed Demon primary feed
  │     subscribeAccountTrade    → Whale Tracker (tracked wallets)
  │     subscribeMigration       → graduation events
  ├── GeckoTerminal new_pools    → Speed Demon backup (poll 60s)
  ├── DexPaprika SSE stream      → tertiary signal feed
  ├── Helius webhooks            → large wallet movements
  ├── BitQuery GraphQL streams   → volume, holders, dev wallet, creator history
  ├── Vybe Network               → labeled wallets, smart money
  └── Rugcheck                   → per-token safety gate

Layer 2 — Optional external signal channels (supplementary only)
  └── GeckoTerminal trending + Vybe top traders as confirmation signals
      (Telethon/Telegram channels removed entirely in v3.0)

Layer 3 — Signal aggregator
  ├── Deduplicates by token address within 60-second window
  ├── Multi-source confidence: base 50 + 15 per additional source
  ├── Applies market mode multiplier (HIBERNATE → skip all)
  ├── Applies bonding curve filter (reject 30–55% KOTH zone for Speed Demon)
  └── Routes through ML gate before forwarding to execution
```

---

## 12. ML Scoring System (v2.0 features — unchanged from v2)

**Model:** CatBoost + LightGBM ensemble. `auto_class_weights="Balanced"`. Retrain weekly. 7-day sliding window. Min 50 samples before first train, 200 before production.

**Key features (26 total):** See v2.0 Section 7 for full feature vector. Highest-weight features: `liquidity_velocity` (2×), `bonding_curve_progress` (2×), `buy_sell_ratio_5min` (2×), `dev_wallet_hold_pct` (strong negative predictor), `bundle_detected` (strong negative predictor).

**ML thresholds:**
```python
ML_THRESHOLDS = {
    "speed_demon":   65,   # FRENZY mode: −5. DEFENSIVE mode: +10
    "analyst":       70,
    "whale_tracker": 70,
}
```

---

## 13. Dashboard Repurposing

**dashboard.html → Bot Overview**
- SOL trading balance + holding wallet balance (read-only)
- Treasury sweep panel: current balance, threshold progress bar (vs 30 SOL), last sweep, total swept
- Bot personality leaderboard (Speed Demon / Analyst / Whale Tracker)
- Market mode indicator (HIBERNATE / DEFENSIVE / NORMAL / AGGRESSIVE / FRENZY)
- EMERGENCY STOP button (red, requires confirmation)
- CFGI Fear & Greed gauge

**dashboard-analytics.html → Performance & ML + Governance**
- Sharpe ratio per bot, max drawdown chart, ML confidence distribution
- Governance notes panel: latest entry from `governance_notes.md`
- Whale wallet pending review notification (when `whale_wallets_pending.json` exists)
- Monthly report when available

**dashboard-wallet.html → Live Trade Feed**
- Incoming signal feed (pre-ML gate)
- Active positions with unrealised P/L
- Recent closed trades log (last 50)
- Whale wallet activity panel

**All pages:** Solana only. JWT authentication required. Satoshi font + Bootstrap Icons.

### Dashboard data architecture

Three dashboard pages load data via two mechanisms:

1. **REST endpoints on page load** (JWT required):
   - `GET /api/trades` — last 50 closed trades from SQLite
   - `GET /api/trades/active` — current open positions
   - `GET /api/personality-stats` — P/L, win rate, trade count per personality
   - `GET /api/ml-status` — reads `data/models/model_meta.json`
   - `GET /api/treasury` — treasury sweeps table, last 10
   - `GET /api/governance` — governance_notes.md preview + pending flag
   - `GET /api/paper-stats` — paper trading stats from Redis/SQLite

2. **WebSocket push for live updates** (JWT required as first message):
   - `periodic_update` every 2 seconds: status, market_health, test_mode, trading_balance, holding_balance, paper_stats, active_positions count

All REST endpoints return empty arrays/zeros if no data exists — never return errors for missing data. Dashboard shows empty states ("No trades yet") until real data arrives. No hardcoded placeholder data anywhere in the dashboard files.

---

## 14. Railway Deployment

**Procfile:**
```
web: python services/dashboard_api.py
signal_listener: python services/signal_listener.py
market_health: python services/market_health.py
signal_aggregator: python services/signal_aggregator.py
bot_core: python services/bot_core.py
ml_engine: python services/ml_engine.py
treasury: python services/treasury.py
governance: python services/governance.py
```

**Startup order:** `market_health` must publish to Redis before `bot_core` processes any signals. `bot_core` waits up to 60 seconds for `market:mode` key in Redis before starting.

**Resource notes:**
- `governance.py` makes Anthropic API calls — costs money per call. Guard all calls with try/except and log token usage.
- `treasury.py` is the most critical safety service — give it `restart: always` and monitor its logs closely.
- `ml_engine.py` retrains weekly — watch for Railway memory spikes during retraining.

**Railway service architecture — CRITICAL:**
Only `services/dashboard_api.py` has an HTTP server. The other 7 services are pure asyncio workers with no web server. Only the "web" service in `railway.toml` should have `healthcheckPath`. Worker services must NOT have healthcheck config — no HTTP server to respond to it. Setting healthcheck on a worker causes Railway deployment failures.

**nixpacks.toml** is used for Railway build config: Python 3.11, `PYTHONPATH=/app`. Only web service uses `healthcheckPath = "/api/health"`. `restartPolicyType = "ON_FAILURE"` for all services.

---

## 15. Build Priority Order

**Phase 1 — Core infrastructure**
1. `services/signal_listener.py` — PumpPortal + GeckoTerminal + DexPaprika (no Telethon)
2. `services/market_health.py` — health check + Redis broadcast
3. `.env.example`, `Procfile`, `railway.toml`

**Phase 2 — Execution (replaces ToxiBot/Telethon entirely)**
4. `services/execution.py` — PumpPortal Local API + Jupiter Ultra API + Jito wrap + retry
5. `services/risk_manager.py` — quarter-Kelly + drawdown scaling + time-of-day

**Phase 3 — Safety and intelligence**
6. `services/treasury.py` — SOL sweep to holding wallet
7. `services/ml_engine.py` — CatBoost + LightGBM ensemble
8. `services/signal_aggregator.py` — dedup + score + ML gate + route
9. `data/whale_wallets.json` — initial list (empty schema)

**Phase 4 — Bot core and governance**
10. `services/bot_core.py` — personality coordinator + EMERGENCY_STOP
11. `services/governance.py` — Claude API governance agent
12. `services/dashboard_api.py` — WebSocket server

**Phase 5 — Dashboard**
13. All three HTML dashboard pages

---

## 16. Testing Approach

- `ENVIRONMENT=development` + `TEST_MODE=true` before any live trading
- Treasury sweep: test with 0.001 SOL transfers first, verify holding wallet receives them
- Governance: test with `max_tokens=100` first to verify API calls work before full prompts
- Paper trade minimum 48 hours before enabling live execution
- Start live with 0.1 SOL test positions, scale to full sizing after 20+ successful trades
- Verify EMERGENCY_STOP halts all three personalities simultaneously before going live

---

## 17. Key Constraints (Inviolable)

- **Never commit `.env`, `*.session`, `toxibot.db`, or any private key file**
- **Never hardcode any private key or API key**
- **TEST_MODE=true means zero trades — not reduced trades**
- **25% portfolio exposure is the absolute ceiling — no code path can exceed it**
- **EMERGENCY_STOP halts all three personalities simultaneously — never per-personality**
- **Daily loss limit: 1.0 SOL / 5% of portfolio (whichever is lower)**
- **Jito tip never exceeds 0.1 SOL**
- **Treasury sweep is one-directional: trading wallet → holding wallet only**
- **Holding wallet private key NEVER enters the system — public key only**
- **Governance agent output is advisory — no auto-deployment of parameter changes**
- **`whale_wallets_pending.json` requires manual review and rename before activation**
- **Never enter a token in the 30–55% bonding curve KOTH zone unless ML score ≥ 85%**
- **Maximum 2 personalities in any single token simultaneously**
- **No Telethon, no Telegram session files, no @toxi_solana_bot calls — anywhere**

---

## 18. First Agent Task (Copy-Paste Ready)

```
Read AGENT_CONTEXT.md in full before writing any code.

Build Phase 1 + Phase 2:

PHASE 1 — Signal infrastructure:

1. services/signal_listener.py
   - PumpPortal WebSocket (wss://pumpportal.fun/api/data):
     subscribeNewToken, subscribeAccountTrade (wallets from whale_wallets.json),
     subscribeMigration, subscribeTokenTrade
   - GeckoTerminal polling every 60s: GET /networks/solana/new_pools (backup)
   - DexPaprika SSE: /v1/solana/events/stream (tertiary)
   - All signals → Redis LPUSH "signals:raw" as JSON:
     {mint, source, timestamp, age_seconds, raw_data, signal_type}
   - Exponential backoff reconnect: 1s base, ×2 each attempt, 60s max
   - TEST_MODE=true: log signals, do NOT push to Redis
   - NO Telethon. NO Telegram. Nothing related to messaging.

2. services/market_health.py
   - Daily 00:00 UTC: query DefiLlama, CFGI, Jupiter price
   - Compute composite sentiment score and market mode
   - Publish to Redis pub/sub "market:mode"
   - Cache to Redis key "market:health" (5-min TTL)
   - Intraday every 5 minutes: rug cascade detection, SOL price shock, congestion
   - Publish EMERGENCY events to "alerts:emergency" Redis channel

3. services/treasury.py
   - Poll Helius getBalance on TRADING_WALLET_ADDRESS every 5 minutes
   - If balance > TREASURY_TRIGGER_SOL (30.0):
     transfer_amount = balance - TREASURY_TARGET_SOL (25.0)
     if transfer_amount >= TREASURY_MIN_TRANSFER_SOL (1.0): execute sweep
   - Use SystemProgram.transfer via Helius RPC (NOT Jito — low priority)
   - Log every sweep to SQLite treasury_sweeps table
   - Send Discord notification on each sweep
   - On 3 consecutive failures: publish to "alerts:emergency" and halt
   - TEST_MODE=true: log what WOULD be swept, do not execute transfer

PHASE 2 — Execution layer:

4. services/execution.py
   - PumpPortal Local API: POST https://pumpportal.fun/api/trade-local
     - Build payload, receive serialized tx, sign with trading keypair, send via Helius RPC
     - Wrap in Jito bundle with dontfront pubkey for MEV protection
     - Slippage config from Section 5 of AGENT_CONTEXT.md
   - Jupiter Ultra API: GET quote + POST swap from https://lite-api.jup.ag/swap/v1/
     - MEV protection built in — no Jito wrap needed
     - Slippage config from Section 5 of AGENT_CONTEXT.md
   - choose_execution_api() routing function from Section 5
   - Retry logic: 5 attempts, 500ms initial, 1.5× backoff, escalate fee tier on each retry
   - TEST_MODE=true: build and log transaction details, do NOT sign or send

5. .env.example — all vars from Section 10, descriptions, no values
6. Procfile — all 8 services from Section 14
7. data/whale_wallets.json — empty array [] with schema comment
8. data/governance_notes.md — empty file with header comment

Do NOT build signal_aggregator.py, ml_engine.py, bot_core.py, or governance.py yet.
When done: commit "feat: phase-1-2 signal infra, execution layer, treasury sweep"
```

---

## 19. Useful Commands

```bash
pip install -r requirements.txt

# Run services individually for testing
python services/market_health.py
python services/signal_listener.py
python services/treasury.py       # watch logs carefully — real SOL if not TEST_MODE
python services/execution.py      # only safe in TEST_MODE=true

# Deploy
git push origin main   # Railway auto-deploys

# Logs
railway logs --service treasury    # most important to monitor
railway logs --service bot_core
railway logs --service governance
```

---

## 20. Requirements (Full)

```
# Core async
aiohttp>=3.9.0
aiofiles>=23.2.0
websockets>=12.0
aiohttp-sse-client>=0.2.1    # for DexPaprika SSE stream

# Solana
solders>=0.20.0
solana>=0.34.0
base58>=2.1.1

# Database
aiosqlite>=0.20.0
redis[asyncio]>=5.0.0

# ML
catboost>=1.2.5
lightgbm>=4.3.0
scikit-learn>=1.4.0
numpy>=1.26.0
pandas>=2.2.0

# Governance agent
anthropic>=0.25.0

# Utilities
python-dotenv>=1.0.0
httpx>=0.27.0
pydantic>=2.6.0
schedule>=1.2.0
python-jose[cryptography]>=3.3.0

# REMOVED from v2.0:
# telethon — no longer needed
```

---

## 21. Verified API Reference (March 2026)

**Before fixing any API integration, check this section first. Do not rely on training data for API details -- they change.**

### PumpPortal
- Local API: POST https://pumpportal.fun/api/trade-local (no auth)
- WebSocket: wss://pumpportal.fun/api/data
- Pool values: pump, pump-amm, launchlab, raydium-cpmm, bonk, auto
- denominatedInSol: STRING "true"/"false" not boolean
- Fee: 0.5% (Local API), 1% (Lightning API)

### Jupiter (V2 — active since March 2026)
- Order: GET https://api.jup.ag/swap/v2/order
- Execute: POST https://api.jup.ag/swap/v2/execute
- V1 DEPRECATED (returns 401): /swap/v1/quote, /swap/v1/swap
- Price: GET https://api.jup.ag/price/v3?ids=<mints>
- Auth: x-api-key header (free key at portal.jup.ag)
- Price field: "usdPrice" (not "price")
- Swap payload: "prioritizationFeeLamports" (not computeUnitPriceMicroLamports)
- lite-api.jup.ag: DEPRECATED -- do not use in new code

### Helius
- RPC: https://mainnet.helius-rpc.com/?api-key=KEY
- Enhanced API: https://api-mainnet.helius-rpc.com
- Staked RPC: HELIUS_STAKED_URL env var, auth: Authorization Bearer header
- Parse TX: POST https://api-mainnet.helius-rpc.com/v0/transactions?api-key=KEY
- Parse History: GET https://api-mainnet.helius-rpc.com/v0/addresses/{address}/transactions?api-key=KEY
- Webhooks: POST https://api-mainnet.helius-rpc.com/v0/webhooks?api-key=KEY
- Auth: ?api-key= query param on ALL endpoints except Staked RPC (Bearer)

### Nansen
- Base: https://api.nansen.ai/api/v1
- Auth: "apikey" header (lowercase)
- token-screener: uses "timeframe" field (not "date")
- Valid timeframes: 5m, 10m, 1h, 6h, 24h, 7d, 30d

### Vybe Network
- Base: https://api.vybenetwork.xyz (NOT .com — DOCS-004 fix 2026-04-30; .com returns 404 on every endpoint)
- Auth: X-API-Key header
- Top traders: GET /v4/wallets/top-traders?resolution=30d&limit=50&sortByDesc=realizedPnlUsd
- Field names: accountAddress, winRate (0-100 scale), realizedPnlUsd, tradesCount

### GeckoTerminal
- Base: https://api.geckoterminal.com/api/v2
- New pools: GET /networks/solana/new_pools
- Trending: GET /networks/solana/trending_pools?include=base_token,quote_token,dex
  - Param is "duration" not "timeframe" (optional: duration=24h)
  - Polling interval: 60s
  - Volume filter: >$10K/hr applied in signal_listener
- No auth required, 30 req/min

### DexPaprika
- SSE: https://streaming.dexpaprika.com/stream?method=t_p&chain=solana
- SSE fields: a=address, p=price, t=timestamp, c=chain
- No auth required

### DefiLlama
- Solana DEX volume: GET https://api.llama.fi/overview/dexs/Solana (chain is PATH param)
- Volume field: "total24h"

### Rugcheck
- Report: GET https://api.rugcheck.xyz/v1/tokens/{mint}/report (no auth)
- Summary: GET https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary (no auth)
- Score: UNBOUNDED INTEGER (not 0-100). Higher = more risky.
- Reject threshold: score >= 2000 OR has_danger/critical in risks[]
- Real examples: safe ~100-500, risky ~1000-3000, rugs 5000+, TRUMP scored 18,715
- Returns: score, result, risks[], topHolders[], graphInsidersDetected

### SocialData.tools
- User lookup: GET https://api.socialdata.tools/twitter/user/{username}
- Auth: Authorization: Bearer {SOCIALDATA_API_KEY}
- Returns: followers_count, friends_count, verified
- Rate limit: 120 req/min, 0.5s minimum between calls
- Cache: 24h per username in Redis
- ENV VAR NAME: SOCIALDATA_API_KEY (not SOCIAL_DATA_API_KEY)

### Jito
- Bundles: POST https://mainnet.block-engine.jito.wtf/api/v1/bundles
- Tip floor: GET https://bundles.jito.wtf/api/v1/bundles/tip_floor
- Max tip: 0.1 SOL (100M lamports) hard cap

## Connected MCP Servers (Claude Code)

Nansen MCP: https://mcp.nansen.ai/ra/mcp/
- Auth: authorization_token from NANSEN_API_KEY
- Integrated in governance.py via NANSEN_MCP_SERVER dict
- Used for: wallet_rescore, weekly_meta, smart_money_analysis

Railway MCP: npx @railway/mcp-server
- Use for: service health, logs, env vars, restarts, deployments

Redis MCP: npx @gongrzhe/server-redis-mcp@1.0.0
- Use for: inspecting keys, queue depths, bot state, emergency resets

CoinGecko MCP: npx mcp-remote https://mcp.api.coingecko.com/mcp
- Use for: SOL price, market data, trending tokens, pool analysis

Playwright MCP: npx @playwright/mcp@latest
- Use for: testing live dashboard at zmnbot.com, screenshots

Gmail MCP: https://gmail.mcp.claude.com/mcp
Google Calendar MCP: https://gcal.mcp.claude.com/mcp

Security rule: No MCP server ever handles trade execution
or has access to TRADING_WALLET_PRIVATE_KEY.

---

## 22. Governance Agent v2 Features

1. **Rolling memory** (data/governance_memory.json): last 10 recommendations, confirmed strengths, known weaknesses
2. **Anomaly detection** (every 30 min): win rate drops, exit reason spikes, signal source degradation
3. **Parameter approval system**: pending_parameters.json -> active_parameters.json via POST /api/approve-parameter
4. **Personality weighting** by market regime (personality_weights.json): bull_trend, high_volatility, choppy, defensive
5. **Weekly meta report**: GeckoTerminal trending + Nansen MCP + Claude pattern analysis
6. **Self-improving prompts**: memory context injected into every Claude call
7. **Discord two-way commands**: !zmn status/today/best/worst/pause/resume/meta/diagnose
   - Handler: governance.py handle_discord_command() called from signal_listener.py
   - Requires DISCORD_OWNER_ID env var

All scheduled tasks use Australia/Sydney timezone (auto DST via pytz).
Daily briefing: 7:00 AM Sydney. Wallet rescore: Monday 6:00 AM Sydney.

## 23. ML Architecture (Current Implementation — March 2026)

### Model ensemble
Three gradient boosted tree models with equal-weight averaging:
- CatBoost (ordered boosting, depth=6, 500 iterations,
  auto_class_weights="Balanced")
- LightGBM (leaf-wise growth, depth=6, 500 iterations,
  class_weight="balanced")
- XGBoost (level-wise growth, depth=4, 500 iterations,
  scale_pos_weight=dynamic) — added for inductive bias diversity

When FLAML has run (sample_count >= 200), a fourth auto-tuned
model from FLAML's 60-second search is added to the ensemble.

All models saved as pickle files in data/models/.
Ensemble score = mean(all available model probabilities) * 100.

### Training schedule
- Minimum 50 samples for first training
- Minimum 200 samples for production scoring (65/70/70 thresholds)
- Below 200 samples: bootstrap thresholds (40/45/45)
- Incremental update (init_model, 50 new trees): every 50 new
  labeled trades
- Full retrain: weekly (7-day sliding window)
- Emergency retrain: triggered by ADWIN drift detection

### Drift detection
River ML ADWIN detector (~1MB RAM) monitors rolling prediction
error rate. When drift detected, publishes to Redis
"ml:emergency_retrain" channel. Typical sensitivity: detects
regime change within 20-30 trades after the change occurs.

### Feature set (33 features)
Original 26 features plus 7 new additions:
- creator_prev_launches: count of prior token launches by deployer
- creator_rug_rate: fraction of prior launches that failed (<24h)
- creator_avg_hold_hours: how long creator typically holds own tokens
- jito_bundle_count: bundled txs in first 10 trades (0-10)
- jito_tip_lamports: avg Jito tip in first bundles
- token_freshness_score: exp(-age_hours / 6) decay function
- mint_authority_revoked: 1=revoked, 0=active

Creator stats cached in Redis for 1 hour (key: "creator:{wallet}").
Jito bundle stats fetched via Helius Enhanced Transactions API.

### Haiku enrichment layer (warm path)
Claude Haiku 4.5 runs async in parallel with ML scoring.
Returns JSON with risk_score (0-100) and recommendation.
Latency: 200-400ms. Cost: ~$0.0003/call.
Hard timeout: 3s — never blocks trade execution.

Score modifiers applied AFTER ML scoring:
- hard_pass recommendation → score * 0.3 (near-zero)
- strong_buy + risk_score < 20 → score * 1.15 (15% boost)
- risk_score > 70 → score * 0.8 (20% penalty)
- Haiku result cached in Redis 5 minutes (key: "haiku:{mint}")

IMPORTANT: Haiku is a soft modifier only. The ML model makes
the primary decision. Haiku can veto or boost but not solely
trigger a trade. Never put Haiku in the synchronous hot path.

### SHAP feature importance
Computed after each full retrain using shap.TreeExplainer
on the LightGBM model. Saved to data/models/model_meta.json
under "feature_importance" key. Rendered in dashboard
/analytics page as horizontal bar chart.

### Accuracy tracking
Rolling accuracy tracked in Redis "ml:prediction_history"
list (last 100 predictions). Metrics:
- accuracy_last_100: directional accuracy (predicted
  positive=score>=65, actual outcome matches)
- win_rate_last_100: of trades taken, % profitable
Updated on every trade outcome received from bot_core.

### Memory footprint (Railway 512MB)
- LightGBM: ~50-80MB import + training
- CatBoost: ~100-200MB training (known memory leak — restart
  ml_engine service weekly to reset)
- XGBoost: ~30-50MB
- River ADWIN: ~1MB
- FLAML: ~50MB during search (weekly only)
- SHAP: ~20MB during computation (weekly only)
Total inference footprint: ~150-250MB

### What NOT to add (documented decisions)
- PyTorch/deep learning: 200-400MB import alone — exceeds budget
- TabNet, FT-Transformer: require PyTorch
- AutoGluon in production: multi-GB RAM
- Stable Baselines3 / RL: requires 10K+ episodes minimum
- Social sentiment (Twitter/X/Telegram) in hot path: 1-2 day
  lag — not predictive for sub-minute memecoin sniping
- LLMs in synchronous hot path: 200-500ms too slow for
  sub-second sniping

### Accelerated ML Engine (ml_model_accelerator.py) — ACTIVE
Drop-in replacement for ml_engine.py. 3-phase model:
- Phase 1 (n < 250): TabPFN only
- Phase 2 (250-999): TabPFN + CatBoost ensemble
- Phase 3 (n >= 1000): TabPFN + CatBoost + LightGBM ensemble

Current state (2026-03-30):
- Phase 3 active, trained on 41,470 MemeTrans samples + 187 live trades
- CV AUC: 0.8113
- TabPFN: installed (tabpfn>=0.1.10) but may fail on Railway —
  graceful fallback to CatBoost+LightGBM 50/50 weighting
- Model file: data/models/accelerated_model.pkl
- Meta file: data/models/model_meta.json
- Requires: ML_ENGINE=accelerated env var

### TabPFN status
TabPFN is in requirements.txt (tabpfn>=0.1.10) and wrapped
with ImportError handling in ml_model_accelerator.py.
If TabPFN fails to import, the engine falls back to
CatBoost+LightGBM without it. Check logs for:
"TabPFN not installed — running without it"

## 24. Current Bootstrap Status (March 2026 Audit)

**Date:** 2026-03-30 (updated)
**Audit tool:** Railway CLI + Redis MCP + PostgreSQL direct

### Personality status
- **Speed Demon:** ACTIVE — generating paper trades, pre-filters active (social, bundle, rugcheck, age, liquidity)
- **Analyst:** ACTIVE — routing fixed, receives new_token + trending signals. Source gate relaxed to 1 during bootstrap.
- **Whale Tracker:** ACTIVE — 44 watched wallets (36 Nansen MCP, 8 fallback). Receives whale_trade + whale_transfer.

### ML training status
- Accelerated engine (ml_model_accelerator.py): Phase 3, 41,470 MemeTrans samples
- Live trades in DB: 187 paper trades (all Speed Demon), 174 in trades table (117 labelled)
- CV AUC: 0.8113
- ML scores in production: 57-62 range (bootstrap thresholds letting these through)
- Thresholds: speed_demon=65/40, analyst=70/45, whale_tracker=70/45 (trained/bootstrap)

### Position sizing
- Speed Demon: 0.45 SOL base, up to 0.75 SOL high confidence
- MAX_SD_POSITIONS=3 (enforced by risk_manager)
- Position size multiplier from pre-filters: 0.5x-1.5x

### Trading performance (187 paper trades)
- Win rate: 0.5% (1/187)
- Total PnL: -6.97 SOL (-34.8%)
- Exit reasons: emergency_stop (122), time_exit_no_movement (65)
- Average hold: 3.7 minutes

### Known issues fixed (2026-03-30)
1. Redis pubsub connection leak in signal_aggregator (pubsub.aclose() added)
2. Redis max_connections bumped 5→20 in signal_aggregator
3. DexPaprika SSE HTTP 400 — disabled via DEXPAPRIKA_ENABLED=false
4. TabPFN silent failure — ImportError now caught with graceful fallback
5. nixpacks.toml install phase was overriding pip install -r requirements.txt
6. Emergency stop reset: consecutive_losses=84 cleared in PostgreSQL + Redis
7. ML_ENGINE=accelerated env var added to Railway
8. market:mode:override set to NORMAL for paper trading (expires 24h)

### Gotchas / known issues
- consecutive_losses in bot_state PostgreSQL can accumulate and trigger false emergency stops.
  Fix: UPDATE bot_state SET value_int=0 WHERE key='consecutive_losses'
- market:mode:override Redis key expires every 24h — real market is HIBERNATE (CFGI ~8).
  Must renew daily for paper trading: SET market:mode:override NORMAL EX 86400
- ML_ENGINE defaults to "original" if env var not set — accelerated model sits unused
- SOCIALDATA_API_KEY naming: code reads SOCIALDATA_API_KEY (not SOCIAL_DATA_API_KEY)
- DexPaprika SSE returns HTTP 400 — disabled via DEXPAPRIKA_ENABLED=false
- Nansen direct API returns 405 on some endpoints — use MCP tools instead
- Anthropic API credits exhausted — governance agent failing (needs credit top-up)
- Nansen credits at 510% of monthly limit (50974/10000)

## 25. Nansen Integration Status (March 2026)

### Discord listener (signal_listener.py)
- Channel: DISCORD_NANSEN_CHANNEL_ID env var
- Bot: DISCORD_BOT_TOKEN (Toxibot Listener)
- Poll interval: 15 seconds
- Alert types wired (case-insensitive matching):
  - "Whale Entry" → whale_tracker, confidence_boost=30
  - "Smart Money Inflow" → analyst, confidence_boost=25
  - "Smart Money Concentration" → analyst, confidence_boost=35
  - "Smart Money Sell/Exit" → alerts:exit_check (high urgency)
  - "Fund Activity" → whale_tracker, confidence_boost=30
  - "Netflow Spike" → market:netflow_boost Redis key (1.2x multiplier)
- Prerequisite: bot needs Read Messages + Read Message History + View Channel

### watched_wallets (PostgreSQL source of truth)
- Table: watched_wallets with qualification_score, personality_route, nansen_labels
- Source: nansen_wallet_fetcher.fetch_and_upsert_wallets() (every 48h via governance)
- Fallback: whale_wallets.json → auto-seeded with 8 known addresses
- Dashboard: GET /api/wallets, POST /api/wallets/refresh

### Token screener (signal_listener.py)
- Endpoint: POST https://api.nansen.ai/api/v1/token-screener
- Poll interval: 10 minutes
- Filters: Solana, max 1 day old, top 20 by market cap
- Routes to: analyst personality via "nansen_screener" source
- Dedup: NANSEN_SCREENER_SEEN set (in-memory, clears at 2000)

### Nansen MCP (governance.py only)
- Server: https://mcp.nansen.ai/ra/mcp/
- Auth: NANSEN-API-KEY header
- Used by: wallet_rescore, daily_briefing, weekly_meta tasks
- NOT used in signal_aggregator or signal_listener (latency-sensitive → REST only)

### Which personalities consume Nansen data
- Speed Demon: indirect (confidence_boost from Nansen Discord alerts)
- Analyst: direct (nansen_screener + smart_money_inflow + sm_concentration alerts)
- Whale Tracker: direct (whale_entry + fund_activity alerts + watched_wallets)

## 26. Service Connectivity Baseline (March 2026)

### How to connect in Claude Code agent sessions

Use DATABASE_URL and REDIS_URL environment variables directly — do not hardcode credentials.
Railway rotates passwords on redeploy; hardcoded values go stale.

**IMPORTANT:** DATABASE_URL is internal only (postgres.railway.internal).
For external access from Claude Code, use DATABASE_PUBLIC_URL from the
Postgres service variables (gondola.proxy.rlwy.net:29062).
Similarly, REDIS_URL is internal — use REDIS_PUBLIC_URL (crossover.proxy.rlwy.net:36328).

```python
# PostgreSQL (via services/db.py — uses DATABASE_PUBLIC_URL or DATABASE_URL)
import asyncpg
dsn = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
conn = await asyncpg.connect(dsn)

# Redis
import redis
r = redis.from_url(os.getenv("REDIS_URL"))
```

**Preferred: Use MCP servers instead of raw connections.**
Redis MCP and Railway MCP are connected and provide direct access
without managing connection strings.

Dashboard: https://zmnbot.com (JWT auth required — DASHBOARD_SECRET env var)

### External service status (reference)
| Service | Notes |
|---------|-------|
| PumpPortal WS | Primary signal source — working |
| Jupiter | V2 /order + /execute + V3 /price endpoints |
| Jito | Bundles endpoint — working |
| Helius RPC | Rate limited — use sparingly |
| Nansen | Direct API returns 405 on some endpoints — use MCP tools |
| GeckoTerminal | new_pools + trending_pools working |
| DexPaprika | SSE HTTP 400 — disabled (DEXPAPRIKA_ENABLED=false) |
| DefiLlama | Market health data — working |
| SocialData | Twitter follower lookups — working (SOCIALDATA_API_KEY) |
| Anthropic | Governance agent — credits exhausted, needs top-up |
| Discord | Bot configured, 403 on Nansen channel (needs permission fix) |
