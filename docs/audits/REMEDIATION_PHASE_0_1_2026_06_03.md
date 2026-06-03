# GO-LIVE REMEDIATION — PHASES 0 & 1 (consolidated record for oversight)

**Date:** 2026-06-03 (Sydney) · **Companion to:** `docs/audits/FULL_CODE_AUDIT_001_2026_06_02.md` (the findings register + §B remediation sequence).
**Purpose:** a single self-contained record of every fix shipped in §B Phase 0 (restore/harden/observe) and §B Phase 1 (live-execution correctness) — what each fix was, why it's correct, how it was verified, its **runtime-confirmation status**, the commit to inspect, and the rollback. Built so an independent reviewer (Jay / Claude web) can audit the work without reading the scattered chronological entries in STATUS/ZMN_ROADMAP.

> **This is a record, not a substitute for reading the diffs.** Each fix cites its **pushed** commit hash — `git show <hash>` on `origin/main` shows the exact change.
> **Hash convention note:** STATUS.md entries cite the *pre-amend content* hash (repo convention); the **pushed** hashes below are the post-amend ones that actually exist on `origin/main`.

---

## ⚠️ THE ONE CAVEAT THE REVIEWER MUST UNDERSTAND

**All four Phase-1 fixes live in the `TEST_MODE=false` (live) `else:` branch of the execution/close path.** That code **does not execute in the current paper deployment** (TEST_MODE=true). Therefore:

- Their **behaviour is NOT runtime-confirmed** — it cannot be observed in paper. It is verified by `py_compile` + unit tests (where the logic is isolable) + structural assertions + code review.
- Their **behaviour will be runtime-confirmed only at the supervised first-live-trades** (the flip).
- What *was* confirmed for each: the **deployment is clean** (bot_core/execution import without error and the service stays up).

**Phase-0 fixes are different** — they run in paper, so they ARE runtime-confirmed (see the end-to-end validation section). This asymmetry is the single most important thing to keep in mind when reviewing.

**Highest-risk changes to scrutinise first** (live-money, not paper-observable):
1. **#6 buy-idempotency** (`execution.py`, `29fca1b`) — the on-chain `getSignatureStatuses` decision logic (landed/failed/unknown) and the `action`-differentiated `unknown` handling. A logic error here could double-spend or mis-record at the flip.
2. **#4 failed-sell handling** (`bot_core.py`, `259a20d`) — the `result.success` check + park-and-continue; confirm a failed sell truly does not book/pop/decrement.
3. **#5 partial-sell sizing** (`execution.py`, `09f71c1`) — the `sell_fraction` → `"X%"` / `int(balance*frac)` math; confirm full closes (sell_pct=1.0) are unchanged.

---

## TL;DR status

| Phase | Fix | Pushed commit | Files | Runtime status |
|---|---|---|---|---|
| 0 #1 | FIX-PUBSUB-ISOLATION (supervise) | `f343295` | main.py, **async_utils.py (new)**, bot_core, dashboard, governance, market_health, ml_engine, signal_aggregator | ✅ **confirmed in prod** (crash-loop resolved; supervise caught the real TimeoutError) |
| 0 #1b | pubsub connection-leak hotfix | `9fa45b0` | async_utils, dashboard, governance, signal_listener | ✅ confirmed (MaxConnectionsError gone) |
| 0 #2 | FIX-MARKET-MODE-MISCLASSIFICATION | `e30d41b` | market_health.py | ✅ confirmed (mode→DEFENSIVE correctly) |
| 0 #2.5 | REDIS-CLIENT-HARDENING-001 | `2337565` | 8 services (all `from_url`) | ✅ confirmed (supervise-restarts→0; counter accumulates) |
| 0 #3 | DEPLOY-OBSERVABILITY | `34f2515` | dashboard_api.py, dashboard-analytics.html | ✅ confirmed (internal-svc rows populated, alert armed) |
| 1 #4+#8 | live-sell result-check + emergency-stop | `259a20d` | bot_core.py | ⚠️ deploy-clean; **behaviour flip-confirmed-only** |
| 1 #6 | buy-idempotency + Jito-off + D02-F14 | `29fca1b` | execution.py | ⚠️ deploy-clean; **behaviour flip-confirmed-only** |
| 1 #5+D02-F8 | partial-sell sizing (both routes) | `09f71c1` | execution.py, bot_core.py | ⚠️ deploy-clean; **behaviour flip-confirmed-only** |
| 1 #7 | unconditional pool-state refresh | `94457ef` | bot_core.py | ⚠️ deploy-clean; **behaviour flip-confirmed-only** |

Bot state at writing: TEST_MODE=true (paper), 6 services Online, `market:health.mode=DEFENSIVE`, trading paper normally, wallet 5.064 SOL unchanged.

---

## PHASE 0 — restore the bot, harden it, make it observable (runtime-confirmed)

### 0 #1 — FIX-PUBSUB-ISOLATION  (`f343295` + leak-hotfix `9fa45b0`)
- **Findings:** D01-F1/F2/F3/F4/F5/F6, D12-F5 (= PIPELINE-PUBSUB-ISOLATION-001, the active outage).
- **Defect:** a transient redis pubsub `TimeoutError` raised by an unguarded `async for pubsub.listen()` propagated through the no-`return_exceptions` top-level `asyncio.gather` → whole-process crash → Railway crash-loop (~6.7s) → migration-counter starvation → HIBERNATE. Present in 5 services; the single-service `main.py` entrypoint also had no supervised restart.
- **Fix:** NEW `services/async_utils.py::supervise(coro_factory, name)` — runs a long-lived coroutine in a restart-on-crash loop (capped exp backoff), **stops on clean return** (no hot-loop), **propagates `CancelledError`** (clean shutdown). Wrapped every member of all 7 service top-level gathers + the dashboard bg-tasks. `main.py` single-service path now routes through the existing `run_service()` supervisor. **Design choice:** supervise-at-the-gather (zero edits to 7 different listener bodies) — minimal/uniform/reversible; restarting a listener re-subscribes, so it's both crash-isolation AND self-healing.
- **Leak hotfix (`9fa45b0`):** prod observation showed the supervise-restart exposed a connection leak — 3 listeners created a pubsub with no `finally: aclose()`, so each restart leaked a pool connection → `MaxConnectionsError`. Added `try/finally: await pubsub.aclose()` to `signal_listener._token_subscribe_listener`, `governance._trigger_listener`, `dashboard_api._redis_broadcaster` (bot_core ×2 + ml_engine ×3 already cleaned up). Made `supervise` log concisely (one-liner per restart, not a full traceback) to avoid spam.
- **Verification:** py_compile 9/9; `.tmp_pubsub_fix/verify_pubsub_isolation.py` 25/25 (behavioural: restart-on-exception, stop-on-clean-return, CancelledError propagation, sibling-survives-a-perma-crasher; + structural). **RUNTIME-CONFIRMED:** prod logs show the exact `redis.exceptions.TimeoutError` from `_emergency_listener` now caught by `supervise` (`async_utils.py:52`) while the process stays Online.
- **Reviewer check:** confirm `supervise` never swallows `CancelledError`; confirm clean-return doesn't hot-loop; confirm the 3 leak-fixed listeners close their pubsub on exit.
- **Rollback:** `git revert 9fa45b0 f343295` (newest first).

### 0 #2 — FIX-MARKET-MODE-MISCLASSIFICATION  (`e30d41b`)
- **Findings:** D07-F1/F3/F4/F5/F7, D06-F6 (MARKET-MODE-001-RE-CALIBRATE-002).
- **Defect:** `_determine_market_mode` ANDs 3 volumetric legs; an absent `market:migration_count_1h` (counter starved) defaulted `grad_rate` to 0, and a DefiLlama blip coerced `dex_vol` to 0.0 — either single-leg-vetoed a healthy market straight to HIBERNATE. Missing-data conflated with dead-market.
- **Fix (`services/market_health.py` only):** absent migration counter → `None` sentinel that **abstains** in the classifier (distinguished from a genuine 0 via `is not None`); `_fetch_defillama` returns `None` (+ last-good ≤1h fallback) not `0.0`; the fabricated `pumpfun_vol = 0.15*dex_vol` placeholder is **dropped as a binding leg** (kept only as a labelled estimate); total-data-loss → **DEFENSIVE** (cautious-but-trading), never HIBERNATE-on-a-data-outage; added a `data_degraded` flag. Genuine low volume still → HIBERNATE.
- **Verification:** py_compile; `.tmp_market_mode/verify_market_mode.py` 10/10 (incl. the exact outage case: $1.75B dex + absent counter → NORMAL, and genuine-dead → HIBERNATE). **RUNTIME-CONFIRMED:** see end-to-end validation — mode correctly moved to DEFENSIVE.
- **Reviewer check:** confirm a *genuine* grad_rate=0 (known, not absent) still yields HIBERNATE; confirm dropping the pumpfun leg can't over-promote (dex_vol is the binding leg at the thresholds).
- **Rollback:** `git revert e30d41b`.

### 0 #2.5 — REDIS-CLIENT-HARDENING-001  (`2337565`)  *(prod-surfaced, not in the original §B list)*
- **Finding:** prod-observed — persistent `Timeout reading from redis.railway.internal:6379` (~every 6s, environmental Railway-Redis latency) was dropping migration-counter increments + churning the safety pubsub listeners (60s backoff under supervise).
- **Fix:** added `socket_keepalive=True, health_check_interval=30, retry_on_timeout=True` to **all 15 `aioredis.from_url(...)` call sites across 11 service files**. health_check reconnects Railway-proxy-dropped connections; retry_on_timeout retries transient reads; keepalive holds idle connections.
- **Verification:** **construct-tested on redis-py 7.4.0 BEFORE editing** (an all-services change — a rejected kwarg would crash every service at startup; `from_url` accepted all 3); py_compile 11/11. **RUNTIME-CONFIRMED:** bot_core supervise-restarts → 0 (was #8/#9 every 60s); migration counter began accumulating (2→6→10).
- **Reviewer check:** confirm none of the kwargs change blocking-command (brpop) semantics. (We deliberately did NOT set `socket_timeout`.)
- **Rollback:** `git revert 2337565`.

### 0 #3 — DEPLOY-OBSERVABILITY  (`34f2515`)
- **Findings:** D12-F2/F3/F4/F6 (the reason the 05-28 outage was silent).
- **Defect:** heartbeat keys had zero readers; the dashboard health surface showed only external APIs (a crashed internal service appeared as "PumpPortal DOWN"); the only liveness alerter (`continuous_audit.py`) was undeployed.
- **Fix:** folded liveness checks into the existing `web` service's `_service_health_checker` (runs every 60s — **no new billable Railway worker**): adds internal-service rows to `service:health` (bot_core via `service:bot_core:heartbeat`+`bot:status`, signal_aggregator via `signal_aggregator:health`, signal_listener via `signals:raw` freshness, market_health via `market:health` freshness; TTL'd keys → absence==down) + a **rate-limited (30min) Discord down-alert** when a critical internal service has no liveness key. Dashboard gains a "ZMN Services" health section.
- **Verification:** py_compile; liveness keys confirmed present+fresh via Redis; HTML/JS aligned (5 grids ↔ 5 sections). **RUNTIME-CONFIRMED:** `service:health` now carries all internal-service rows = `ok` with accurate ages; no false-down → no spurious alerts.
- **Caveat:** the dashboard *visual* was not render-tested (Playwright gated on OBS-004); markup is append-only, low layout risk. A fully-independent watchdog (`continuous_audit.py` as its own Railway service) would survive a `web` outage too — filed as the stronger-option follow-up.
- **Rollback:** `git revert 34f2515`.

---

## PHASE 1 — live-execution correctness (deploy-clean; behaviour flip-confirmed-only)

### 1 #4+#8 — live-sell result-check + emergency-stop robustness  (`259a20d`, MERGED)
- **Findings:** D02-F1 (most dangerous live defect), D02-F6, D03-F1, D04-F8.
- **Why merged:** #4 changes the failure-raise behaviour #8 depends on. If #4 made `_close_position` *raise* on a failed sell, emergency_stop's unguarded loop would abort on the first un-sellable mint — *worse* than today. So #4 uses **park-and-continue (never raises)** and #8 adds the per-position guard.
- **#4 defect:** `execute_trade` catches `ExecutionError` internally and **returns `success=False`** (it never re-raises), so the `except ExecutionError` in `_close_position` was **dead code** and `result.success` was never checked on the sell path. A failed live sell fell through → decremented `remaining_pct`, booked oracle PnL, wrote `closed_at`, popped the position → **SOL stranded on-chain, fabricated PnL, position never retried.**
- **#4 fix:** new `if not result.success:` check (and the except guard) call a shared `_handle_failed_live_sell()` — increments the sell-storm counter, parks past `SELL_FAIL_THRESHOLD`, records to `live_execution_log`, and **returns WITHOUT booking/decrementing/popping** → the position stays OPEN for `_check_exits` to retry. Never raises. Also protects partial/staged-TP sells (the check precedes any decrement).
- **#8 fix:** emergency_stop wraps each `_close_position` in try/except (one un-sellable mint can't abort the stop), detects "left open" via `key in self.positions` (since #4 leaves failed sells open without raising), sets the **durable Redis `bot:emergency_stop` kill key** (survives restart + cross-service visible), and **always** runs the Discord alert + `bot:status` publish (now reporting `positions_failed`).
- **Verification:** py_compile; `.tmp_phase1/verify_phase1_4_8.py` 10/10 (structural + flow); code review confirmed the success path (counter reset, decrement, price, booking) is intact and the paper branch is untouched.
- **Reviewer check:** trace that a `success=False` sell really returns before L~1442; confirm no other caller relied on the removed raise (`_check_exits` per-position try/except + emergency_stop guard cover it); confirm the durable kill-key requires manual clear (intended).
- **Rollback:** `git revert 259a20d`.

### 1 #6 — buy/sell idempotency + Jito-off + D02-F14  (`29fca1b`)
- **Findings:** D02-F3 (double-spend), D02-F2, D02-F7, D02-F14.
- **D02-F3 defect:** on a confirmation miss, the retry loop `continue`d → re-built + re-broadcast the same tx → **double-spend** risk on a buy that actually landed (no idempotency key, no signature recheck).
- **D02-F3 fix:** new `_get_signature_status()` (`getSignatureStatuses` on the 3-tier Helius RPC → `landed`/`failed`/`unknown`). On a confirm-miss, `execute_trade` polls status (3×/2s) and decides: **landed → success (no resubmit); failed (on-chain err) → resubmit (it did not execute); BUY-unknown → record-pending WITH the signature (never double-buy; reconcile/Path-B/`_check_exits` resolve it); SELL-unknown → failure (caller #4 parks+retries, no maybe-unlanded close booked).**
- **D02-F2/F7 (Jito):** forced `use_jito=False` in `execute_trade`. The Jito bundle path returned the bundle UUID (not a tx sig → broke confirmation + Path B + fed the double-submit) AND added no tip instruction (bundles never land). Now uses the proven local-RPC `_send_transaction` (real sig, 3-tier). Filed `JITO-REIMPLEMENT-001` (real-sig extraction + tip transfer) as the proper future fix.
- **D02-F14:** `_confirm_trade_helius` no longer blind-passes (`confirmed=True`) when `HELIUS_PARSE_TX_URL` is unset — returns `confirmed=False` so the getSignatureStatuses check verifies on-chain. (Env-checked: the URL **is** set on bot_core, so this was latent — but the blind-pass is removed.)
- **Verification:** py_compile; `.tmp_phase1/verify_idempotency.py` 6/6 (`_get_signature_status` landed/failed/unknown parsing + TEST_MODE short-circuit, **unit-tested by mocking the RPC session**); 9/9 structural (use_jito off, status-gated decision, action-differentiated unknown, D02-F14, old resubmit path gone).
- **Reviewer check (highest priority):** the `unknown`-case decisions — is "BUY-unknown → record-pending success=True" the right risk trade (avoids double-spend, accepts a recoverable phantom position) vs "SELL-unknown → failure"? Confirm `getSignatureStatuses` parsing (`value[0].err`) is correct. Confirm disabling Jito is acceptable (loses MEV protection until JITO-REIMPLEMENT-001).
- **Rollback:** `git revert 29fca1b`.

### 1 #5+D02-F8 — partial-sell sizing (both routes)  (`09f71c1`)
- **Findings:** D02-F5 (🔴), D02-F8.
- **Defect:** the pre-grad `_execute_pumpportal_local` SELL hardcoded `"amount":"100%"` → every partial/staged-TP live sell (sell_pct 0.25/0.50/0.95) **dumped the entire position** (then the bot believed it held a phantom remainder). The Jupiter post-grad sell fetched + sold the **full wallet balance** (same bug, other route).
- **Fix:** threaded a `sell_fraction: float = 1.0` param through `execute_trade` → both sell routes. `_close_position` passes `sell_fraction=sell_pct` (fraction of the CURRENT on-chain balance — matches the multiplicative `remaining_pct *= (1-sell_pct)` semantics). Pre-grad sends `"100%"` if fraction≥0.999 else `f"{frac*100:g}%"` (e.g. "25%"); Jupiter sends `int(balance * sell_fraction)`. **Full closes (sell_pct=1.0) are byte-for-byte unchanged.**
- **Verification:** py_compile (both files); fraction→percent + Jupiter-int arithmetic 10/10; 4/4 structural (no hardcoded "100%" left, both routes apply the fraction, param threaded, bot_core passes sell_pct).
- **Reviewer check:** confirm `sell_fraction=sell_pct` is the correct semantic (fraction of *current* balance, not original); confirm full-close path unchanged; confirm the `f"{...:g}%"` format is accepted by PumpPortal Local.
- **Rollback:** `git revert 09f71c1`.

### 1 #7 — unconditional pool-state refresh for live sells  (`94457ef`)
- **Findings:** D02-F4, D03-F3 (EXEC-001/002).
- **Defect:** the EXEC-001 pool-state refresh was gated on `pos.bonding_curve_progress > 0`, so it **skipped** (a) whale/Raydium tokens (bc=0 → 400'd on the pump.fun path) and (b) reconciler-restored positions that lose `bonding_curve_progress` (→0.0) → a pump.fun token that graduated during the hold sold via the dead BC pool.
- **Fix:** removed the gate — `_check_pool_state_fresh` runs for **every** live sell. It returns 1.0 (BC closed → graduated or never-pump.fun → route non-local/Jupiter) or 0.0 (BC live → pre-grad → PumpPortal Local), so refreshing always yields correct routing regardless of the stored/lost value. This also covers the reconcile-lost case **without a schema migration** (D03-F3's alternative). Fail-closed to the stale value on RPC error (no worse than pre-fix; +1 Helius getAccountInfo per live sell). EXEC-002 NameError was already resolved in current code. D03-F8 (force-abandon after N park cycles) deferred → `EXEC-FORCE-ABANDON-001`.
- **Verification:** py_compile; 4/4 structural (gate removed, unconditional refresh + assignment + fail-closed-except intact).
- **Reviewer check:** confirm the extra getAccountInfo per sell is acceptable for the Helius budget; confirm fail-closed-to-stale on RPC error is acceptable (same as pre-fix).
- **Rollback:** `git revert 94457ef`.

---

## PHASE 2 — safety rails (added 2026-06-03; mostly live-only → behaviour flip-confirmed-only)

> **Scoping note:** every Phase-2 fix is **paper-safe by construction** (live-only, or default-preserving). Three sub-items were **deliberately deferred + flagged** because they need decisions I would not make unilaterally under a "no input" mandate (they change paper sizing/caps or risk halting the dead-governance bot). They are filed as follow-ups, not silently skipped.

### 2 #9 — live HIBERNATE veto  (`7e83949`)
- **Findings:** D04-F3 / D07-F2 / D08-F1 / D08-F3 — bot_core had no effective live regime veto (the only HIBERNATE skip was the SA bypass gated on `AGGRESSIVE_PAPER`, not TEST_MODE; the other gate is fail-open governance).
- **Fix:** (A) `signal_aggregator` — HIBERNATE→DEFENSIVE bypass now gated on `AGGRESSIVE_PAPER and TEST_MODE` (live always hard-skips). (B) `bot_core.process_signal` — independent live veto: `not TEST_MODE` → read `market:mode:current` fresh → `return` on HIBERNATE (doesn't trust the SA label or governance).
- **Paper impact: NONE** (paper bypass preserved; veto is live-only). **Verification:** py_compile + 5/5 structural; deploy confirmed clean (paper kept trading). **Reviewer check:** confirm the live veto reads fresh mode and the paper bypass is unchanged. **Rollback:** `git revert 7e83949`.

### 2 #10 — governance CFGI-read fix  (`7fe2ad1`)
- **Findings:** D04-F1 / D09-F2 / BUG-010.
- **Fix:** `governance.py` read `redis.get("market:cfgi")` — a key NOTHING writes → CFGI was permanently the neutral 50 default. Now reads `market:health` (prefers `cfgi_sol`).
- **Verified already-in-place (no change):** bot_core applies `gov.size_multiplier` (CONSERVATIVE→0.8 haircut works); the live regime VETO governance fail-open left missing is now provided by **#9**.
- **🚩 Current-state finding:** `governance:latest_decision = CONSERVATIVE / size_multiplier 0.8` because the LLM is **dead** (Anthropic 400/credits — BUG-010). So **every current paper trade is sized 0.8× base** (silent governance haircut), and governance provides **zero real regime signal** — #9's market:mode veto is the only live regime control. The cfgi fix only takes effect once the LLM is revived. **Verification:** py_compile + 4/4 structural; governance is non-trading (can't break paper). **Rollback:** `git revert 7fe2ad1`.

### 2 #11+#12 — live startup-state: daily-loss persistence + on-chain balance seed  (`78cc45c`, MERGED)
- **Findings:** D04-F4 (#11), D04-F2 (#12). Both in `_load_state`, **both gated `not TEST_MODE` → paper byte-for-byte unchanged.**
- **#11:** `_load_state` hard-zeroed `daily_pnl_sol` on every startup → any restart laundered the daily-loss accumulator → `DAILY_LOSS_LIMIT_SOL` could never accumulate. Fix (live-only): reload TODAY's (UTC) realized PnL from `trades WHERE trade_mode='live' AND closed_at>=midnight` (`pnl_sol`; closed_at epoch float; safe fallback 0.0). Paper keeps the hard-zero.
- **#12:** `_load_state` read the unfiltered latest snapshot → post-flip loaded the ~50 SOL paper balance → exposure/drawdown denominators inflated ~10× vs the real ~5 SOL wallet. Fix (live-only): seed `total_balance_sol` from on-chain `getBalance` (new `_fetch_onchain_balance_sol`); fallback to snapshot w/ warning if RPC down. (Per-trade size was never at risk — the absolute MAX_POSITION_SOL cap floors it.)
- **Verification:** py_compile + 6/6 structural; deploy confirmed clean (paper startup + trading unaffected). **Reviewer check:** confirm `trades` query uses `pnl_sol` (not corrected_pnl_sol — that column doesn't exist on `trades`); confirm both blocks are `not TEST_MODE`. **Rollback:** `git revert 78cc45c`.

### 2 #13 — fill-MC-ceiling fail-CLOSED  (`c70aba1`)  *(partial — sizing-caps deferred)*
- **Finding:** D08-F7. The live fill-MC gate failed OPEN: `_get_token_price`=0 → `fill_mc=0` → `0 > ceiling` False → it **admitted an unbounded-MC live buy**. Fix: `if fill_price <= 0: log + return` (fail CLOSED). Live-only. py_compile + 3/3 structural. **Rollback:** `git revert c70aba1`.
- **DEFERRED + FLAGGED from #13 (need decisions):**
  - **`MAX_SD_POSITIONS` wiring (D04-F7) → `SIZING-CAPS-WIRING-001`:** cap is hardcoded `MAX_CONCURRENT_PER_PERSONALITY=3`; `MAX_SD_POSITIONS` is phantom. **But `MAX_SD_POSITIONS=20` is deployed-but-unread** → wiring it as-is jumps the cap 3→20 in paper. Must land *with* the env set to the V5A-ladder intent (5/7).
  - **Timezone / double time-of-day multiplier (D08-F4 / D11-F2) → `TIMEZONE-SIZING-FIX-001`:** TIME_GOOD/DEAD/SLEEP/WEEKEND fire on a hardcoded UTC+11 clock (off 1h in AEST) AND time-of-day is applied twice on two clocks. Changes *paper* sizing + needs a semantics decision (audit: "confirm with Jay"). CORRECTNESS, not a money-loss 🔴.

### Phase-2 deferred follow-ups (filed, not lost)
`SIZING-CAPS-WIRING-001`, `TIMEZONE-SIZING-FIX-001`, `GOVERNANCE-STALENESS-POLICY-001` (stale/dead-governance posture — halt-risk while dead), plus **BUG-010** (Anthropic credits — governance LLM dead; a real go-live prerequisite for governance to function + the source of the current 0.8× paper haircut).

---

## Cross-cutting decisions & lessons (for the reviewer's context)

1. **Verification strategy shifted at the Phase boundary.** Phase-0 fixes run in paper → observed in prod (and one prod observation caught the connection leak → hotfix). Phase-1 fixes are in the live branch → not paper-observable → verified by tests + review, runtime-confirmed at the flip. This is inherent, not a shortcut.
2. **#4 and #8 are co-dependent** (the merge rationale above) — they were deliberately not shipped separately.
3. **The crash-loop removal (0 #1) de-prioritised the restart-triggered findings** (D03-F3, D04-F4, D04-F10, D03-F7) — they fire on deploys/OOM now, not every 6.7s. D04-F4 (daily-loss reset) and D04-F10 (park persistence) are consequently deferred to Phase 2 / follow-ups.
4. **Idempotency `unknown`-case asymmetry** (#6): BUY-unknown records-pending (avoid double-spend), SELL-unknown returns failure (avoid booking a maybe-unlanded close). Both choose the recoverable failure mode over the unrecoverable one.
5. **Jito was disabled, not fixed** — the existing impl is doubly broken (wrong sig + no tip); the local-RPC path is proven. Re-enabling correctly is `JITO-REIMPLEMENT-001`.

---

## End-to-end validation evidence (Phase-0 chain works)

- After the deploys, `market:health` read: `mode: DEFENSIVE` (was warm-up HIBERNATE), `data_degraded: false`, `dex_volume_24h: $1.65B`, with `market:migration_count_1h` observed climbing **2 → 6 → 10** over the session.
- Interpretation: pubsub fix → pipeline flows → migrations captured; redis-hardening → increments land (no longer dropped); market-mode fix → classifies on real data. The bot correctly left HIBERNATE as the counter passed the DEFENSIVE threshold (≥10). Reaching NORMAL (≥30/hr) depends on the bot's true migration capture rate over a full clean hour → `MARKET-MODE-THRESHOLD-RECALIBRATE-003`.
- bot_core startup after each deploy: "Bot Core ready — managing 3 personalities", paper trades entering with real ML scores (40–78), no tracebacks/import errors.

---

## NOT done yet — remaining before any live flip

**Phase 2 — safety rails — ✅ CODE-COMPLETE & DEPLOY-CLEAN (2026-06-03)**, except 3 decision-gated sub-items deferred-and-flagged (see the Phase-2 section above). Done: #9 (`7e83949`), #10 (`7fe2ad1`), #11+#12 (`78cc45c`), #13 fail-CLOSED (`c70aba1`). Live behaviour is flip-confirmed-only (all live-only/default-preserving). Deferred sub-items needing a Jay decision: `SIZING-CAPS-WIRING-001` (MAX_SD_POSITIONS=20 deployed-but-unread → would jump cap 3→20 in paper), `TIMEZONE-SIZING-FIX-001` (changes paper sizing), `GOVERNANCE-STALENESS-POLICY-001` (halt-risk while governance dead). **BUG-010 (Anthropic credits) is a real go-live prerequisite — governance LLM is dead today.**

**Phase 3 — accounting integrity (so trial PnL is trustworthy) — NOT STARTED (not yet authorized):**
- #14 live staged-TP cumulative PnL (D05-F1) + Path-B multi-exit sum (D05-F2) + in-memory balance reconcile (D02-F12).
- #15 dashboard mode-fidelity (D05-F3/F4) + entry-price sentinel (D02-F13) + **DASH-CORRECTED-PNL-COLUMN-001** (the `corrected_pnl_sol does not exist` DB error).

**Deferred reliability follow-ups (filed, not lost):** `JITO-REIMPLEMENT-001`, `SELL-STORM-PARK-PERSISTENCE-001` (D04-F10), `EXEC-FORCE-ABANDON-001` (D03-F8), `MARKET-MODE-THRESHOLD-RECALIBRATE-003`.

**Existing CLAUDE.md live-flip preconditions remain in force on top of all the above.**

---

## Commit index (pushed, on `origin/main`)

```
f343295  Phase-0 #1  FIX-PUBSUB-ISOLATION (supervise)
9fa45b0  Phase-0 #1b pubsub connection-leak hotfix
e30d41b  Phase-0 #2  FIX-MARKET-MODE-MISCLASSIFICATION
2337565  Phase-0 #2.5 REDIS-CLIENT-HARDENING-001
34f2515  Phase-0 #3  DEPLOY-OBSERVABILITY
1ae988b  (docs)      Phase-0 #3 runtime-confirmed + DASH-CORRECTED-PNL-COLUMN-001 filed
259a20d  Phase-1 #4+#8 live-sell result-check + emergency-stop robustness
29fca1b  Phase-1 #6  buy-idempotency + Jito-off + D02-F14
09f71c1  Phase-1 #5+D02-F8 partial-sell sizing (both routes)
94457ef  Phase-1 #7  unconditional pool-state refresh
9c4f1a9  (docs)      Phase-1 deploy-confirmed + end-to-end validation capstone
7e83949  Phase-2 #9  FIX-HIBERNATE-LIVE-VETO (SA paper-only bypass + bot_core live veto)
7fe2ad1  Phase-2 #10 FIX-GOVERNANCE-CFGI-READ (market:health, not phantom market:cfgi)
78cc45c  Phase-2 #11+#12 live startup-state (daily-loss reload + on-chain balance seed)
c70aba1  Phase-2 #13 fill-MC-ceiling fail-CLOSED (sizing-caps deferred → follow-ups)
```

**Verification scripts** (gitignored scratch, run locally, results in commit messages/STATUS): `.tmp_pubsub_fix/verify_pubsub_isolation.py` (25/25), `.tmp_market_mode/verify_market_mode.py` (10/10), `.tmp_phase1/verify_phase1_4_8.py` (10/10), `.tmp_phase1/verify_idempotency.py` (6/6), `.tmp_phase2/` structural greps (#9 5/5, #10 4/4, #11+#12 6/6, #13 3/3).

---

*Maintained alongside FULL_CODE_AUDIT_001. Phases 0, 1, 2 landed. When Phase-3 fixes land, append their section here so this stays the single oversight record through the go-live.*
