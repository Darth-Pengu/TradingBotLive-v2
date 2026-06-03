# FULL-CODE-AUDIT-001 — Comprehensive read-only pre-flip codebase audit

**Date:** 2026-06-02/03 (Sydney) · **Mode:** READ-ONLY (findings only; no code/state changes)
**Method:** Opus 4.8 + multi-agent workflow — recon (KNOWN-ISSUES INDEX, 54 items) → 12 dimension
auditors (exhaustive enumeration, evidence-cited) → adversarial verification (every load-bearing
NEW blocker independently challenged-to-refute). Two workflows: `wf_0d7b9f6b-970` (recon+12 dims+verify),
`wf_bcc00321-6df` (focused re-verification of 13 NEW blockers).
**Scope:** services/*, execution path, market_health, signal_listener/aggregator, bot_core, ml_engine,
governance, treasury, web/dashboard, scripts/, migrations/, db layer, config. ~18,100 LOC across 22 service files.

> **Boundary:** this session FINDS and RANKS. It does not FIX. Every fix is a separate verified
> session (see §B). The only writes this session made are this report, the canonical-doc updates,
> the `.gitignore` scratch entry, and one git push. No code edits, no deploys, no env/Redis/DB-row writes.

---

## Executive summary

The audit confirms the headline known issue (the **dual-service pubsub crash loop**,
`PIPELINE-PUBSUB-ISOLATION-001`) and substantially **extends** it — the same crash class exists in
**five** services, not two, and there is a second structural amplifier nobody had named (the
single-service `main.py` entrypoint has no supervised restart; the resilient wrapper that exists is
wired only to dead legacy code). It then found a **cluster of previously-undiscovered live-execution
and accounting defects** that were masked because the only validated live trade (id 6580) was a
single full round-trip with no staged exits.

**Net flip-blocker picture (post adversarial verification):**

- **9 money/crash 🔴 blockers** that can lose money, hang a position, crash a process, or disable a
  live safety mechanism — most are NEW in the execution/safety path.
- **5 availability/visibility 🔴 flip-blockers** — the bot is currently DOWN (crash-loop →
  HIBERNATE-misclassification), and a live outage would be **invisible** on the dashboard (heartbeat
  keys have no readers; the only liveness alerter is undeployed). This is why the ~05-28 outage went
  unnoticed.
- A large 🟠 correctness tier dominated by **live-mode accounting** (staged-TP PnL mis-booked, Path B
  on-chain truth corrupted on multi-sell trades, safety-rail denominators inflated by stale balance) —
  not capital-fatal, but it corrupts exactly the data a live trial uses to decide go/no-go.

**Two reassuring NON-findings (verified):**
1. **TEST_MODE money-path gating is correct and defense-in-depth.** No path was found where a real
   on-chain send can fire in paper mode (execution.py early-returns a simulated sig in all 3 routes
   *and* bot_core branches paper/live cleanly; both must agree to send). (D08)
2. **The wallet private key is not leaked anywhere in code** — empirically verified, even `repr(Keypair)`
   redacts the secret seed. (D10)

**Counts (final, post-verify):** 🔴 14 · 🟠 ~33 · 🟡 ~26 · 🟢 ~17 (≈90 substantive findings; a handful
are CONFIRMED-OK/RESOLVED non-defects recorded for the register).

---

## Per-dimension narrative

### D01 — Async resilience / crash surface  (7 findings; 3 🔴)
Exhaustively enumerated every `asyncio.gather`, `create_task`, `async for pubsub.listen()`, and
`while True` loop across 9 service files. **Confirmed both known crash surfaces** (signal_listener
`_token_subscribe_listener` L335 + gather L1395; bot_core `_emergency_listener` L2067 / `_exit_check_listener`
L2096 + gather L2410) and **found three more** of the identical class: ml_engine (3 listeners, L771/972/1007 +
gathers L1075/1123), governance (`_trigger_listener` L1047 + gather L1265), dashboard_api (`_redis_broadcaster`
L1919). Root structural amplifier: **all six top-level gathers omit `return_exceptions=True`** (D01-F6) — and
even that flag is insufficient; the correct fix is self-healing listeners + a supervised restart pattern. The
robust pattern already exists in-repo (signal_listener `dexpaprika_listener`, `signal_aggregator._request_ml_score`)
— the crash-prone listeners simply don't use it.

### D02 — Live execution path  (14 findings; 3 🔴 after verify, +2 downgraded)
Traced the live money path end-to-end through all three execution routes. **NEW blockers:** failed live
sells are booked as successful closes (F1 — the `except ExecutionError` at bot_core:1366 is *dead code*
because `execute_trade` returns `success=False` rather than raising, and `result.success` is never checked
on the sell path); buy double-submit on a confirmation timeout with no idempotency (F3); and the pre-grad
`pumpportal_local` sell hardcodes `"amount":"100%"`, so **every partial/staged-TP live sell dumps the entire
position** (F5). Verified-real-but-downgraded: Jito returns a bundle UUID that's mistaken for a tx signature
(F2, secondary path); Jupiter sell ignores size but is **not live-reachable** as wired (F8). Confirmed-OK:
solders signing API correct on all routes (F10); EXEC-002 Jupiter NameError is **fixed** in current code (F9).

### D03 — Position lifecycle & reconciliation  (8 findings; 1 🔴)
emergency_stop's close loop has no per-position guard and is unreliable in exactly the mass-dump scenario it
exists for (F1). Reconciled positions lose `bonding_curve_progress` → stale sell routing on restart (F3,
EXTENDS EXEC-001). `trades_ml_id==0` orphan accumulation confirmed (F4). `stale_no_price` records a synthetic
breakeven for dead/rugged tokens, understating downside in the ML corpus (F5). Graduation moonbag trailing
state is set in-memory but never persisted (F7). **Verified-safe (non-findings):** staged-TP fire-once
idempotency, trailing-stop ratchet arithmetic, REFACTOR-001 id-space handling, and the V5A trade_mode
reconcile filter are all correct.

### D04 — Safety systems: do they fail SAFE?  (11 findings; 4 🔴)
Governance veto **fails OPEN** on credit exhaustion (NORMAL/CONSERVATIVE never blocked by bot_core's
HIBERNATE/PAUSE-only gate → zero live regime veto, F1, CONFIRMS BUG-010). The AGGRESSIVE_PAPER HIBERNATE
bypass lets **live trades fire in a true-HIBERNATE market** and disables the consecutive-loss pause (F3).
Stale paper balance inflates the exposure/drawdown safety-rail denominators ~10× until the first live close
(F2, downgraded from a sizing-blowout claim — the absolute `MAX_POSITION_SOL` cap actually floors per-trade
size). Daily-loss accumulator zeroed on every restart (F4). `MAX_SD_POSITIONS` is a **phantom env var** (only
a comment; real cap is hardcoded 3 — the V5A 5/7 ladder is unenforceable, F7). emergency_stop never sets the
Redis kill key (F8). CFGI fails open to neutral 50 (F9).

### D05 — Money-accuracy / accounting  (10 findings; 0 🔴 after verify, 2 high-🟠)
The live close branch **never accumulates `cumulative_pnl_sol`** (paper-only), so a multi-staged-TP live
winner books only its final residual slice (F1). Path B `live_actual_v1` pairs the **full-position** entry
native-delta with the **final-partial** exit delta → grossly wrong on any staged-TP trade, and it overwrites
the `corrected_pnl_sol` the dashboard treats as truth (F2). Both verified live-reachable; both downgraded to
🟠 because they corrupt reporting/attribution but not capital safety (F1 understates *wins* only; F2 leaves
`realised_pnl_sol`+balance on the uncorrupted Path A value). Portfolio-snapshot daily_pnl in live is a
lifetime sum of the whole paper+live corpus (F3); `api_analytics` is unfiltered + uncorrected (F4). Paper fee
model structurally under-counts live cost ~17.6× (F5, CONFIRMS COST_FIDELITY_GAP). `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS`
wrong-year constant **confirmed NOT in shipping code** — docs/roadmap only (F9).

### D06 — State management discipline  (8 findings; 1 🔴)
Independently re-derived the daily_pnl reset blocker (F1 = D04-F4). Confirmed `signals:raw` unbounded on
consumer downtime (F2) and `paper:positions:*` / `paper:stats:daily:*` no-TTL leaks (F3/F4). Two divergent
consecutive-loss counters; the per-personality dict isn't restored on restart (F5). Migration counter is
durable-less cross-service Redis state (F6). **Connection/pool handling audited clean** — single asyncpg pool
with `async with` acquire, Redis created once per service, pubsubs `aclose`d; no leaks.

### D07 — Market classification  (7 findings; 2 🔴)
The active outage's other half: `_determine_market_mode` ANDs three legs and a starved `grad_rate=0`
single-leg-vetoes a healthy $1.75B market to HIBERNATE (F1). bot_core has no independent HIBERNATE veto
(F2). `pumpfun_vol = dex_vol*0.15` is a fabricated placeholder used as a hard gate leg (F3). DefiLlama
failure returns 0.0 → forces HIBERNATE (F4). Override 24h TTL silently expires → reverts to misclassified
HIBERNATE mid-trial (F6). No graceful-degradation / partial-data state (F7).

### D08 — Config/env correctness + TEST_MODE gating  (7 findings; 2 🔴)
**Headline reassurance: TEST_MODE money-path gating is correct, defense-in-depth — no real send can fire in
paper mode.** Real risks are the *opposite*: AGGRESSIVE_PAPER HIBERNATE bypass reaches the live path (F1);
DAILY_LOSS_LIMIT_SOL default 1.0 + reset-on-restart (F2). EXTENDS the timezone finding: the
TIME_GOOD/DEAD/SLEEP/WEEKEND sizing branches fire **unconditionally** on a hardcoded UTC+11 clock (only the
TIME_PRIME branch is env-disabled), scaling live size on a wrong clock (F4). ML-threshold sprawl: the
documented "only paper-effective filter" (`ML_THRESHOLD_BOT_CORE_SD`) ships default-0 = disabled (F5). Live
fill-MC-ceiling gate fails open on a zero price (F7).

### D09 — External dependencies & rate-limits  (11 findings; 2 🔴)
Governance fail-open + a sharp catch: governance reads `market:cfgi`, **a key no service writes**, so its
sentiment input is permanently the neutral default (F2). ML-engine-down fails OPEN (default score 50 passes
the 40 floor → trades blind, F4). Vybe `.com` URL drift at 3 sites silently kills 3 features (F5). Market-mode
feed down → SA defaults to NORMAL (F7). SOL-crash halt silently disabled while the SOL feed is down (F8).
**Verified-robust:** PumpPortal WS reconnect, execute_trade bounded retry, Helius 3-tier resolver on submit
paths, GeckoTerminal holders isinstance guard, SocialData credit handling. **D09-F3 ($80 SOL fallback)
REFUTED** — bot_core refreshes `market:sol_price` every 2s and re-multiplies by its own `sol_usd`; the
divide/multiply cancel → not a real defect (🟢).

### D10 — Security  (5 findings; 0 🔴)
**Private key NOT leaked (empirically verified).** Redis URL incl. password logged at INFO on every startup
(F1) — actively re-emitted every ~6.7s during the crash-loop; concrete basis for SEC-001. Dashboard auth
**fails open** if `DASHBOARD_SECRET` is unset → unauthenticated state-changing POSTs (emergency-stop,
market-mode-override) on a live-money bot (F2). Sentry locals not hardened (defense-in-depth, F3).
`repomix-output.xml` (36MB) untracked but not gitignored (F4).

### D11 — Dead code / drift / placeholders  (9 findings)
Confirmed TIME-PRIME drift, pinned to L773/795 (line drift from the cited 754/776) (F1). **Dead safety path:**
`market:loss_override` has 3 writers (rug-cascade + 5-loss throttle) and **0 readers** — the DEFENSIVE cap is
silently lost while the log claims it applied (F3/F4). Double time-of-day multiplier on two conflicting tz
conventions (UTC in risk_manager + UTC+11 in bot_core, both applied) (F2). Stale CLAUDE.md claim: the
`AcceleratedMLEngine` is **not** removed — it's live behind `ML_ENGINE=accelerated` (F9).

### D12 — Test & observability coverage  (7 findings; 3 🔴)
**Test coverage of money/safety paths is effectively zero** (only the disabled Nansen client has tests; F1).
The outage-detection mechanism does not exist: heartbeat keys are **write-only with zero readers** (F2); the
dashboard health surface has **no internal-service rows** — a crashed bot_core shows up only as "PumpPortal
DEGRADED", mislabeling an internal crash as an external-API issue (F3); the only liveness alerter
(`continuous_audit.py`) is **undeployed** — the proximate reason the ~05-28 outage was silent (F4). The
single-service `main.py` path has no crash wrapper — the resilient `run_service()` is used only in dead legacy
mode (F5, the second structural amplifier of the crash-loop). Fill-latency columns never written (F7).

---

## §A — FINDINGS REGISTER

Severity post adversarial verification where re-verified. `flip` = flip-blocking. `conf` = confidence.
Tags: `[NEW]` / `[C=CONFIRMS]` / `[E=EXTENDS]` a known-issue id.

### 🔴 BLOCKER — money / crash / disabled safety (must fix before flip)

| ID | sev | flip | conf | file:line | tag | finding → fix |
|---|---|---|---|---|---|---|
| D02-F1 | 🔴 | Y | 0.92 | execution.py:758,773; bot_core.py:1362-1389,1430,1645 | [E EXEC-001] | **Failed live sell booked as a successful close.** `execute_trade` returns `success=False` (never raises); the sell path never checks `result.success` → decrements remaining_pct, books oracle PnL, writes closed_at, pops position. SOL stranded, accounting falsified, no retry, sell-storm park bypassed. **Fix:** add `if not result.success:` guard mirroring the BUY path (don't book/pop/decrement); route to park/retry. (M) |
| D02-F5 | 🔴 | Y | 0.90 | execution.py:334-344 | [NEW] | **Partial/staged-TP live sell dumps the ENTIRE position.** `_execute_pumpportal_local` SELL hardcodes `"amount":"100%"`, ignoring `amount_sol`. Pre-grad is the primary SD path; staged TPs (0.25), grad TP (0.95), smart-money (0.50) all dump 100%. Bot then thinks it holds a phantom remainder. **Fix:** compute token amount for the requested fraction, pass real `amount` + `denominatedInSol=false`. (M) |
| D02-F3 | 🔴 | Y | 0.82 | execution.py:702,737-748 | [NEW] | **Buy double-submit on confirm timeout.** On `confirmed=False` (incl. Helius slow/down/timeout) the retry loop re-builds+re-submits a fresh tx with no idempotency / no `getSignatureStatuses` recheck → a landed-but-unconfirmed buy spends 2× SOL on one tracked position. **Fix:** poll signature status before re-submit; treat submitted-unconfirmed as pending, not retry. (M) |
| D03-F1 | 🔴 | Y | 0.90 | bot_core.py:581-593,1362-1385 | [NEW] | **emergency_stop is unreliable in a mass-dump.** No per-position guard in the close loop. Combined with D02-F1, failed live sells are silently booked closed (positions removed, SOL on-chain) so the stop liquidates nothing yet reports success; and any genuine raise in the close bookkeeping (DB/network) aborts remaining closes and skips the Discord alert + EMERGENCY_STOPPED publish (L585-587). The `emergency_stopped` latch then blocks retry. **Fix:** wrap the per-position close in try/except; ensure alert/publish always run; gate on `result.success`. (S) |
| D04-F1 / D09-F2 | 🔴 | Y | 0.97 | governance.py:329,343-347,449-452; bot_core.py:674 | [C BUG-010] | **Governance veto fails OPEN.** No-key → NORMAL(1.0×); API/credit failure → CONSERVATIVE(0.8×). bot_core only vetoes {HIBERNATE,PAUSE} → on the documented credit-exhausted state there is ZERO live market-regime veto. (Also: governance reads `market:cfgi`, a key nothing writes → sentiment permanently neutral.) **Fix:** treat CONSERVATIVE + stale `governance:last_run` as a hard cap/PAUSE bot_core honours; fix the CFGI read. (S-M) |
| D04-F3 / D07-F2 / D08-F1 / D11-F7 | 🔴 | Y | 0.95 | signal_aggregator.py:1741-1746,152; bot_core.py:674 | [C AGGRESSIVE_PAPER bypass] | **Live trades fire in true-HIBERNATE.** HIBERNATE→DEFENSIVE downgrade is gated on `AGGRESSIVE_PAPER_TRADING` (not TEST_MODE); bot_core has no independent HIBERNATE veto. A bot_core-only flip with AGGRESSIVE_PAPER still true → live trades in a dead/outage market at 0.5×, and the consecutive-loss pause is disabled. **Fix:** gate the bypass on `AGGRESSIVE_PAPER and TEST_MODE`; add an independent fresh `market:mode:current=="HIBERNATE"` hard-return in bot_core; add `AGGRESSIVE_PAPER_TRADING=false` to the flip runbook. (S) |
| D01-F1 / D03-F2 / D04-F5 / D09-F1 | 🔴 | Y | 0.97 | signal_listener.py:335,1395 | [C PIPELINE-PUBSUB-ISOLATION-001] | **Unguarded pubsub `.listen()` crashes the signal pipeline.** Transient redis TimeoutError escapes the bare `async for`, propagates through the no-`return_exceptions` gather → process exit → crash-loop → migration-counter starvation → HIBERNATE. The active 06-02 outage. **Fix:** outer `while True: try/except + backoff + re-subscribe` (mirror `dexpaprika_listener`). (S) |
| D01-F2 | 🔴 | Y | 0.97 | bot_core.py:2067,2096,2410 | [C BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001] | **bot_core `_emergency_listener` + `_exit_check_listener` crash the trade engine.** try/**finally** (not except) around `.listen()` → exception re-raises into the gather → bot_core dies. Mid-live-position crash = exits unmonitored = unbounded downside until restart; crashes a safety listener. **Fix:** convert to reconnect-with-backoff loop; supervise the gather. (S) |
| D01-F6 / D12-F5 | 🔴 | Y | 0.95 | bot_core.py:2410; signal_listener.py:1395; ml_engine.py:1075,1123; signal_aggregator.py:2687; market_health.py:548; governance.py:1265; main.py:117-118 | [E PIPELINE-PUBSUB-ISOLATION-001] | **Structural crash amplifiers.** (a) all 6 top-level gathers omit `return_exceptions=True`; (b) the single-service `main.py` entrypoint `await mod.main()` has **no supervised restart** — the resilient `run_service()` (backoff + CancelledError handling) is wired only to dead legacy mode. Together these turn any single-coro exception into a CRASHED container. **Fix:** route single-service through `run_service()`; add a `supervise(coro,name)` restart wrapper to all gathers (return_exceptions alone is insufficient). (M) |

### 🔴 BLOCKER — availability / visibility (flip-blocking; bot is currently DOWN / outage invisible)

| ID | sev | flip | conf | file:line | tag | finding → fix |
|---|---|---|---|---|---|---|
| D07-F1 / D11-F6 | 🔴 | Y | 0.97 | market_health.py:282,396 | [C HIBERNATE-MISCLASSIFICATION] | **Single-leg `grad_rate=0` veto HIBERNATEs a healthy market.** Three ANDed legs; missing `market:migration_count_1h` (TTL-expired when the pipeline is down) defaults grad_rate to 0, failing every tier. Missing-data conflated with dead-market. **Fix:** sentinel for absent counter (don't veto on a missing leg); or ≥2-of-3; or age-bypass. Folds into MARKET-MODE-001-RE-CALIBRATE-002. (M) |
| D12-F4 | 🔴 | Y | 0.90 | scripts/continuous_audit.py; main.py:31-40 | [E PIPELINE-PUBSUB-ISOLATION-001] | **The only liveness alerter is undeployed.** `continuous_audit.py` checks `bot:status` (ex=30) + signal staleness and Discord-alerts — but it is not in SERVICE_MAP or any Railway service. The detection logic is correct; it simply isn't running. **This is the proximate reason the ~05-28 outage was silent.** **Fix:** deploy as a Railway worker; set DISCORD_WEBHOOK_URL. (S) |
| D12-F2 | 🔴 | Y | 0.97 | bot_core.py:2399; signal_aggregator.py:2637 | [E LATENCY-OBSERVABILITY-001] | **Heartbeat keys are write-only.** `service:bot_core:heartbeat` (ex=90) and `signal_aggregator:health` (ex=120) have **zero readers** repo-wide despite the docstring "so dashboard can detect outages." **Fix:** dashboard health checker reads each heartbeat, computes age vs TTL, alerts on stale/absent. (M) |
| D12-F3 | 🔴 | Y | 0.95 | dashboard_api.py:1215-1274,2002-2131 | [E PIPELINE-PUBSUB-ISOLATION-001] | **Dashboard health surface is external-API-only** — no rows for bot_core/aggregator/listener/ml/governance/treasury. A crashed bot_core appears only as "PumpPortal DEGRADED", mislabeling an internal crash as an external problem. Undermines the V5A 4-6h supervised watch. **Fix:** internal-service liveness rows driven by F2 heartbeats. (M) |
| D08-F2 / D04-F4 / D06-F1 | 🔴→🟠 | Y | 0.85 | bot_core.py:282-284; risk_manager.py:55,211 | [E PIPELINE-PUBSUB-ISOLATION-001] | **Daily-loss limit laundered by restart.** `daily_pnl_sol=0.0` set unconditionally on every startup; never reloaded intra-day → DAILY_LOSS_LIMIT_SOL only sees losses since the last restart; under a crash-loop it never accumulates. Default 1.0 binds if the env var is dropped. *Verified 🟠 not 🔴: the peak-balance 20%-drawdown stop survives restart in live as a partial backstop.* **Fix:** reload today's realized loss from a same-UTC-day snapshot; don't hard-zero in live. (M) — **treat as must-fix-before-flip.** |

### 🟠 CORRECTNESS — wrong numbers / wrong behaviour (fix before or alongside flip)

| ID | sev | flip | conf | file:line | tag | finding |
|---|---|---|---|---|---|---|
| D05-F1 | 🟠 | Y | 0.90 | bot_core.py:1197,1201,1392,1416-1418 | [NEW] | Live close books only the **final-partial** PnL across staged TPs (paper-only `cumulative_pnl_sol`); non-terminal partials write no row. Understates multi-TP **winners** in realised/corrected/daily_pnl/balance. (loss exits are single full closes → daily-loss halt still sees full downside). **Fix:** port the paper cumulative accumulation to live. (M) |
| D05-F2 | 🟠 | Y | 0.85 | bot_core.py:1448,1473-1476 | [E LIVE-PATH-B-SLIPPAGE-DERIVATION-001] | Path B `live_actual_v1` pairs the **full-position** entry native-delta with only the **final-partial** exit sig → grossly wrong PnL on staged-TP trades, overwriting `corrected_pnl_sol` (treated as on-chain truth). Corrupts the go/no-go data; realised/balance use uncorrupted Path A. **Fix:** collect `pos.exit_signatures: list`, sum all exit deltas; or disable Path B for >1-exit positions. (M) |
| D02-F12 | 🟠 | Y | 0.90 | bot_core.py:1390,1416-1422,1519 | [E COST_FIDELITY_GAP] | Live in-memory daily_pnl/balance (which drive the kill-switch) updated from the **oracle estimate**, not on-chain proceeds; Path B corrects the DB only. Optimistic oracle PnL can delay the halt. **Fix:** reconcile in-memory balance to on-chain snapshot / Path B native delta. (M) |
| D02-F13 | 🟠 | N | 0.83 | bot_core.py:1006-1010 | [NEW] | Live entry price falls back to sentinel `0.000001` on a price miss → every exit computes a fabricated giant win; breaks trailing/TP math. **Fix:** derive entry from buy-tx fill / BC reserves; never use 1e-6 for a real position. (S) |
| D04-F2 | 🟠 | Y | 0.82 | bot_core.py:277-281,762-765,1611 | [NEW; rel OBS-010] | After a flip+restart, stale ~50 SOL paper snapshot seeds `total_balance_sol` (no startup on-chain getBalance, no mode filter) → **25% exposure ceiling + 20% drawdown denominator inflated ~10×** until the first live close self-corrects. (Per-trade size is safe — floored by absolute MAX_POSITION_SOL.) **Fix:** seed from on-chain getBalance at live startup; or filter snapshot read by `market_mode='LIVE_ONCHAIN'`. (M) |
| D02-F2 | 🟠 | N | 0.85 | execution.py:289-293,504-526,738-740 | [NEW] | Jito `_send_jito_bundle` returns a **bundle UUID** that flows back as the tx "signature" → confirm fails → retry/double-submit; bundle_id stored as entry/exit_signature breaks Path B. Secondary path (primary pre-grad uses `pumpportal_local`, no Jito). **Fix:** confirm via `getBundleStatuses`→landed sig, or disable Jito for live. (M) |
| D02-F7 | 🟠 | N | 0.60 | execution.py:504-526 | [NEW, SUSPECTED] | `_send_jito_bundle` adds **no tip instruction** to the bundle (Jito requires a tip transfer); bundles likely accepted (UUID) but never land. Compounds F2. **Fix:** prepend tip transfer, or disable Jito. (M) |
| D02-F4 | 🟠 | N | 0.70 | bot_core.py:1340; execution.py:1114-1163 | [E EXEC-001] | EXEC-001 refresh is one-directional (never demotes) and skips bc=0 (whale/Raydium) tokens → stale-route 400 persists for that class. **Fix:** refresh unconditionally for live sells; store `pool_route`. (S) |
| D02-F6 | 🟠 | Y | 0.75 | bot_core.py:1389 | [NEW] | `remaining_pct` decremented before the sell is confirmed (compounds F1/F5) → in-memory holdings desync from on-chain. **Fix:** mutate only after a confirmed-landed sell of the intended size. (S) |
| D03-F3 | 🟠 | Y | 0.85 | bot_core.py:337-352,1340 | [E EXEC-001] | Reconciled positions don't restore `bonding_curve_progress` (default 0.0) → EXEC-001 freshness gate (`>0`) skipped → unconditional stale pre-grad routing after restart (frequent under crash-loop). **Fix:** persist+restore bc_progress / pool_route; refresh unconditionally when reconciled. (M) |
| D03-F4 | 🟠 | N | 0.80 | bot_core.py:927-932,1274 | [C PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001] | `trades.closed_at` set only when `trades_ml_id` truthy; a silent persist-UPDATE failure (`except: pass` L931) → `trades_ml_id=0` after restart → trades-ML row never closed → orphan accumulation. **Fix:** log persist failures; close orphan by mint+entry lookup. (S) |
| D03-F5 | 🟠 | N | 0.85 | bot_core.py:1845; paper_trader.py:392-394 | [E COST_FIDELITY_GAP] | `stale_no_price` force-close records synthetic breakeven (≈ -fees) for dead/rugged tokens (true value ≈ 0). Systematically understates downside in the ML corpus. **Fix:** record at a haircut / distinct `correction_method='stale_synthetic'`. (S/M) |
| D05-F3 | 🟠 | N | 0.90 | bot_core.py:2242-2254 | [C PORTFOLIO-SNAPSHOT-MODE-FILTER-001/OBS-010] | Live `portfolio_snapshots.daily_pnl_sol` = lifetime SUM of the whole paper+live `trades` corpus (no trade_mode filter, no time window). **Fix:** add trade_mode + midnight-UTC window, or use in-memory daily_pnl. (S) |
| D05-F4 | 🟠 | N | 0.85 | dashboard_api.py:1462-1515 | [NEW] | `api_analytics` (equity/WR/expectancy) has no trade_mode filter and uses uncorrected `realised_pnl_sol` → mixes paper+live in live view, overstating live edge. **Fix:** thread `_mode_filter` + COALESCE(corrected,realised). (S) |
| D05-F5 | 🟠 | N | 0.85 | paper_trader.py:70-78,161-213 | [C COST_FIDELITY_GAP] | Paper fee/slippage model ~1.46% modelled vs ~25.8% Path-B truth → paper PnL not bankable. **Fix:** PAPER-FEE-MODEL-CALIBRATION-001 once ≥10 Path-B rows; label paper PnL on dashboard until then. (env, gated) |
| D07-F3 / D11-F5 | 🟠 | Y | 0.92 | market_health.py:390 | [C PLACEHOLDER-PUMPFUN-VOL] | `pumpfun_vol = dex_vol*0.15` placeholder is a hard gate leg (collinear with dex_vol; thresholds inconsistent across tiers). **Fix:** real pump.fun volume source, or drop the leg until one exists. (M) |
| D07-F4 | 🟠 | N | 0.85 | market_health.py:176-186 | [E MARKET-MODE-001-RE-CALIBRATE-002] | DefiLlama failure returns 0.0 → zeroes both dex and pumpfun legs → guaranteed HIBERNATE. **Fix:** None-sentinel + last-good + isinstance/raw-shape logging. (S) |
| D07-F5 | 🟠 | N | 0.80 | market_health.py:397-403 | [E MARKET-MODE-001-RE-CALIBRATE-002] | migration_count read swallows all errors silently (absent/parse/redis-error all → 0). **Fix:** distinguish + log; feed sentinel. (S) |
| D08-F4 / D11-F1 / D11-F2 | 🟠 | N | 0.90 | bot_core.py:773,784-798,795; risk_manager.py:162,257 | [E TIME-PRIME-AEDT-AEST-DRIFT-001] | Hardcoded UTC+11 in TIME_GOOD/DEAD/SLEEP/WEEKEND sizing branches (fire **unconditionally**, not just env-disabled TIME_PRIME) → live size on a wrong clock during AEST; AND time-of-day counted twice on two different clocks (risk_manager UTC + bot_core UTC+11). **Fix:** `ZoneInfo("Australia/Sydney")`; de-duplicate the two multipliers (confirm semantics w/ Jay). (S/M) |
| D08-F3 | 🟠 | Y | 0.80 | bot_core.py:664,674 | [C BUG-010] | bot_core's only entry-regime veto is the fail-open governance gate; never reads `market:mode:current` directly. **Fix:** add a fresh market-mode hard-return at entry. (S) |
| D08-F5 / D09-F4 | 🟠 | N | 0.80 | bot_core.py:60,147-150; signal_aggregator.py:1478 | [E BOT-CORE-ML-GATE-001] | ML gate fails OPEN (default score 50 ≥ floor 40 on timeout/None); the documented "only paper-effective filter" ships default-0=disabled. **Fix:** ML-unavailable default below floor; precondition `ML_THRESHOLD_BOT_CORE_SD>=40` before flip. (S) |
| D08-F7 | 🟠 | N | 0.70 | bot_core.py:982-999 | [C LIVE-MODE-FILTER-PARITY] | Live fill-MC-ceiling gate fails OPEN when price=0 (fill_mc=0<ceiling) → admits an unbounded-MC live buy. **Fix:** treat price<=0 as fail-CLOSED in live. (S) |
| D09-F5 | 🟠 | N | 0.90 | signal_aggregator.py:753,850,2568 | [C VYBE-URL-CODE-DRIFT-001] | 3 Vybe calls use `api.vybenetwork.com` (404s) → holder-fallback, creator-rug, KOL/MM features silently inert. **Fix:** `.xyz` base (verify shape). (S) |
| D09-F7 | 🟠 | N | 0.80 | signal_aggregator.py:1736 | [E HIBERNATE cluster] | Market-mode feed absent → SA defaults to NORMAL (fail-open, no regime gate). **Fix:** missing/stale mode → DEFENSIVE/HIBERNATE behind a freshness check. (S-M) |
| D09-F8 | 🟠 | N | 0.75 | market_health.py:373,461 | [NEW] | SOL-crash emergency halt silently disabled while the SOL price feed is down (deltas stay 0.0). **Fix:** carry last-good w/ age cap; degraded-feed posture. (S) |
| D04-F6 | 🟠 | N | 0.85 | market_health.py:507-515; bot_core.py:1890 | [E rug-cascade] | Rug-cascade SQL `LIKE 'stop_loss%'` misses `graduation_stop_loss`; no trade_mode filter. **Fix:** `'%stop_loss%'`/IN-list + mode filter. (S) |
| D04-F7 | 🟠 | N | 0.95 | bot_core.py:310; risk_manager.py:51 | [NEW] | `MAX_SD_POSITIONS` is a phantom env var (comment only); real cap hardcoded 3 → the V5A 5/7 position ladder is unenforceable. **Fix:** env-read `MAX_CONCURRENT_PER_PERSONALITY`/`MAX_SD_POSITIONS`, wire to ladder. (S) |
| D06-F5 | 🟠 | N | 0.80 | bot_core.py:235,1248,1425,365 | [E] | Two divergent consecutive-loss counters; per-personality dict not restored on restart → governance/sizing streak under-counts across restarts. **Fix:** persist+restore, or collapse to one source. (S/M) |
| D06-F6 | 🟠 | Y | 0.90 | market_health.py:396-401 | [E HIBERNATE-MISCLASSIFICATION] | Migration counter is durable-less Redis-only (3600 TTL); producer downtime / Redis wipe → 0 → HIBERNATE. **Fix:** sentinel for absent; optional Postgres backing. (M) |

### 🟡 RELIABILITY — degrades robustness, recoverable

| ID | sev | conf | file:line | tag | finding (terse) |
|---|---|---|---|---|---|
| D01-F3 | 🟡 | 0.95 | ml_engine.py:771,972,1007,1123 | [E PIPELINE-PUBSUB] | ml_engine 3 listeners try/finally + gather → crash (degrades to default-score-50, not halt). Fix in same sweep. |
| D01-F4 | 🟡 | 0.90 | governance.py:1047,1265 | [E PIPELINE-PUBSUB] | governance `_trigger_listener` unguarded → crash (non-money). Fix in same sweep. |
| D01-F5 | 🟡 | 0.88 | dashboard_api.py:1919,2161 | [NEW] | `_redis_broadcaster` dies silently on pubsub timeout (no reconnect/done-callback) → stale dashboard during the watch window. |
| D02-F11 | 🟡 | 0.70 | execution.py:228,642; bot_core.py:1135 | [E] | `_get_dynamic_priority_fee`/`_get_token_balance`/`_check_pool_state_fresh` omit STAKED tier → break under STAKED-only config. |
| D02-F14 | 🟡 | 0.60 | execution.py:579-580,127 | [NEW, SUSPECTED] | If `HELIUS_PARSE_TX_URL` unset, `_confirm_trade_helius` returns confirmed=True without verifying → submitted-but-failed tx recorded as success. Make it a hard live precondition. |
| D03-F6 | 🟡 | 0.60 | bot_core.py:1212 | [NEW, SUSPECTED] | Terminal cumulative-pnl correction gated on `staged_exits_done`; a non-staged partial (smart-money 0.50) then terminal close → DB shows only last leg. Gate on `remaining_pct<1.0`. |
| D03-F7 | 🟡 | 0.75 | bot_core.py:1896-1900 | [NEW] | Graduation moonbag trailing state set in-memory, never persisted → lost on restart, residual rides down. |
| D03-F8 | 🟡 | 0.70 | bot_core.py:2013-2014 | [E EXEC-001] | Per-position exit errors only logged → permanently-broken-sell position retried each cycle (bounded by park); counts against MAX_SD_POSITIONS. Land EXEC-001+002; add force-abandon after N park cycles. |
| D04-F8 | 🟡 | 0.90 | bot_core.py:572-592 | [NEW] | emergency_stop never sets Redis `bot:emergency_stop` → not durable across restart, not seen cross-service. Fix: set Redis key + persist. |
| D04-F9 | 🟡 | 0.85 | market_health.py:189-202; bot_core.py:702 | [C BUG-010 CFGI] | CFGI fails OPEN to neutral 50 → extreme-fear (<10) gate silently off when feed down. Fix: sentinel/None. |
| D04-F10 | 🟡 | 0.80 | bot_core.py:241-242,1327-1385 | [E sell-storm] | Sell-storm park state in-memory → never accumulates under crash-loop; parked position can't exit for 5min. Fix: Redis-persist park w/ TTL. |
| D06-F2 | 🟡 | 0.95 | signal_listener.py:169 (+telegram/governance/dashboard producers) | [C signals:raw leak] | `signals:raw` LPUSH no LTRIM/EXPIRE → unbounded when aggregator down. Fix: LTRIM 0 N. |
| D06-F3 | 🟡 | 0.90 | paper_trader.py:306 | [C paper:positions leak] | `paper:positions:{mint}` hset no TTL; orphans on non-paper_sell close. Fix: TTL + delete on every close. |
| D06-F7 | 🟡 | 0.60 | bot_core.py:1300,1679 | [E market:mode:override] | `market:loss_override` cache-only (ex=3600); lost on Redis wipe (also see D11-F3 dead-reader). |
| D07-F6 | 🟡 | 0.88 | dashboard_api.py:1423; market_health.py:409 | [E MARKET-MODE-OVERRIDE] | `market:mode:override` 24h TTL silently expires → reverts to misclassified HIBERNATE mid-trial. Fix: sticky override + banner, or fix the root misclassification. |
| D07-F7 | 🟡 | 0.82 | market_health.py:266-284 | [E] | All-AND thresholds, no partial-data DEGRADED state → any data hiccup → HIBERNATE-by-default. Fix: scored/voting classifier. |
| D09-F10 | 🟡 | 0.80 | market_health.py:331-333 | [NEW] | No last-good / staleness guard on `market:sol_price`; consumers fall to defaults when all sources fail. |
| D09-F11 | 🟡 | 0.70 | signal_aggregator.py:2687 | [E PIPELINE-PUBSUB] | SA top-level gather unguarded (lower risk — inner loops self-heal). Fix for parity. |
| D10-F2 | 🟡 | 0.90 | dashboard_api.py:195-197 | [NEW] | Dashboard auth fails OPEN if `DASHBOARD_SECRET` unset → unauthenticated emergency-stop / market-mode-override POSTs. Fix: fail-closed; verify deployed secret pre-flip. |
| D10-F5 | 🟡 | 0.80 | SEC-001; market_health.py:543 | [C SEC-001] | Credential rotation outstanding; F1 is the concrete leak. Sequence after F1 redaction + log purge. (V5d gate; v5a-c waiver). |
| D12-F1 | 🟡 | 0.98 | tests/ | [NEW] | No tests for execution/sell/safety paths (only disabled Nansen client). Add routing/signing/loss-limit unit tests + import smoke tests. |
| D12-F6 | 🟡 | 0.85 | bot_core.py:2319 | [C] | `bot:status` has correct ex=30 (valid liveness signal) but only the undeployed script reads it. Cheap win: dashboard treats absent bot:status as down. |

### 🟢 HYGIENE — dead code / drift / cosmetic

| ID | conf | file:line | finding |
|---|---|---|---|
| D09-F3 | 0.82 | signal_listener.py:1307 | **REFUTED as a defect.** `$80` SOL fallback never bites (bot_core refreshes `market:sol_price` every 2s; divide/multiply cancel). Hardcoded `"80"` is a smell only — replace with a live fetch / no-write-on-absent. |
| D01-F7 | 0.80 | governance.py:183 | Fire-and-forget `create_task(_write())` swallows DB-write exceptions (no done-callback). |
| D02-F9 | 0.95 | execution.py:421-425 | **EXEC-002 CONFIRMED FIXED** (action/amount_sol hoisted above TEST_MODE). Index stale — mark resolved. |
| D02-F10 | 0.98 | execution.py:285,361,470 | **Solders signing API CONFIRMED CORRECT** on all 3 routes (constructor form). |
| D05-F6 | 0.80 | dashboard_api.py:818-819 | Python `or` falsy-zero: legit `corrected_pnl_sol==0.0` falls through to realised. Use explicit None-check. |
| D05-F8 | 0.75 | paper_trader.py:298 vs bot_core.py:1074 | `amount_sol` column semantics differ (paper net-of-fees vs live gross). Standardize. |
| D05-F9 | 0.90 | (docs only) | `BIGGEST_WINS_CLEAN_DATA_FLOOR_TS` wrong-year **not in shipping code**; only a hazard if DASH-001 Card 7 ships with the bad literal. Use 1778642961. |
| D05-F10 | 0.70 | bot_core.py:1416 vs 1477-1479 | `corrected_pnl_pct` denominator differs Path A (price-ratio) vs Path B (size). Standardize. |
| D06-F4 | 0.95 | paper_trader.py:318,456 | `paper:stats:daily:{today}` no-TTL → one permanent key/day. Add ex. |
| D06-F8 | 0.99 | paper_trader.py:9 | Stale docstring "SQLite paper_trades" (is Postgres). |
| D08-F6 | 0.80 | risk_manager.py:50 vs bot_core.py:760 | `MIN_POSITION_SOL` default drift (0.10 vs 0.15). Single source. |
| D09-F6 | 0.85 | signal_aggregator.py:2582 | Bare `except: pass` zeroes Vybe KOL/MM feature silently (HOLDER-DATA class). Log + isinstance. |
| D10-F1 | 0.97 | market_health.py:543; signal_listener.py:1373 | **Redis URL incl. password logged at INFO** every startup (re-emitted every ~6.7s under crash-loop). Redact host:port only. |
| D10-F3 | 0.85 | sentry_init.py:43-50 | Sentry locals not hardened (`include_local_variables=False` absent) — defense-in-depth on key-signing services. |
| D10-F4 | 0.80 | repomix-output.xml; .gitignore | 36MB full-repo dump untracked but not gitignored. Add to .gitignore (+ `*.bak`). |
| D11-F3 / D11-F4 | 0.97 | market_health.py:522; bot_core.py:1300,1679 | **Dead safety path:** `market:loss_override` 3 writers, 0 readers → rug-cascade + 5-loss DEFENSIVE cap silently lost; log falsely claims it applied. Wire a reader or remove writers+logs. |
| D11-F9 | 0.90 | ml_engine.py:1035; ml_model_accelerator.py:114 | Stale CLAUDE.md: `AcceleratedMLEngine` NOT removed — live behind `ML_ENGINE=accelerated`. Correct the doc or remove the module. |
| D11-F8 | 0.85 | ml_engine.py:771,1123 | ml_engine pubsub not isolated (= D01-F3). |
| D12-F7 | 0.90 | execution.py/paper_trader.py | Fill-latency columns never written (blocks PAPER-LATENCY-MODEL-001). Instrument round-trip timing. |

---

## §B — PRE-FLIP REMEDIATION SEQUENCE

Each item is a **separate verified fix-session** (own TDD/verify/deploy). One lever per session. Ordered by
dependency. Severity is post-verification.

### Phase 0 — RESTORE the bot (the bot is DOWN; nothing else matters until this is green)

1. **FIX-PUBSUB-ISOLATION** (🔴 D01-F1, D01-F2, D01-F6, D12-F5; CONFIRMS PIPELINE-PUBSUB-ISOLATION-001).
   Self-heal every `pubsub.listen()` loop (outer reconnect+backoff) in signal_listener, bot_core (both
   listeners), ml_engine (3), governance, dashboard; add a `supervise(coro,name)` restart wrapper to all 6
   top-level gathers; **route the single-service `main.py` path through `run_service()`**. This is the
   single highest-priority fix — it restores signal flow, which un-starves the migration counter, which
   clears the HIBERNATE misclassification. *Depends on: nothing.*
2. **FIX-MARKET-MODE-MISCLASSIFICATION** (🔴 D07-F1/D11-F6, 🟠 D06-F6/D07-F3/F4/F5/F7;
   MARKET-MODE-001-RE-CALIBRATE-002). Sentinel for absent migration counter (don't veto on a missing leg);
   None-sentinel on DefiLlama; replace/neuter the `pumpfun_vol` placeholder leg; add a DEGRADED state.
   *Depends on: #1 (verify mode is correct only once flow is restored). Do NOT mask via override.*
3. **DEPLOY-OBSERVABILITY** (🔴 D12-F4, D12-F2, D12-F3; 🟡 D12-F6, D01-F5). Deploy `continuous_audit.py`
   as a Railway worker; add internal-service heartbeat reads + dashboard rows + stale-alerting. **Must
   precede any live flip** — the V5A supervised watch is meaningless if an outage is invisible.
   *Depends on: nothing (parallelizable with #1/#2).*

### Phase 1 — LIVE EXECUTION CORRECTNESS (must be green before TEST_MODE=false)

4. **FIX-LIVE-SELL-RESULT-CHECK** (🔴 D02-F1, 🟠 D02-F6). Check `result.success` on the live sell path;
   don't book/pop/decrement on failure; route to park/retry. *The single most dangerous live defect.*
5. **FIX-PARTIAL-SELL-SIZING** (🔴 D02-F5; 🟠 D02-F8 latent). `_execute_pumpportal_local` must sell the
   requested fraction, not 100%. Without this, the entire staged-TP strategy is broken in live.
   *Depends on: pairs with #4 (both touch the sell path).*
6. **FIX-BUY-IDEMPOTENCY** (🔴 D02-F3, 🟠 D02-F2/F7). Re-check signature status before re-submit on a
   confirmation timeout; fix Jito bundle confirmation (or disable Jito for live); add the Jito tip or use the
   working local-RPC path. Make `HELIUS_PARSE_TX_URL` a hard live precondition (D02-F14).
7. **FIX-EXEC-001/002-ROUTING** (🟠 D02-F4, D03-F3, D03-F8; EXEC-001/EXEC-002). Refresh pool state
   unconditionally for live sells; persist/restore `bonding_curve_progress`+`pool_route`; add
   force-abandon after N park cycles. *Land EXEC-001 + EXEC-002 together (already a paired requirement).*
8. **FIX-EMERGENCY-STOP-ROBUSTNESS** (🔴 D03-F1; 🟡 D04-F8, D04-F10). Per-position try/except in the
   close loop; always run alert+publish; set Redis `bot:emergency_stop`; persist sell-storm park.
   *Depends on: #4 (the success-check changes the loop's behaviour).*

### Phase 2 — LIVE SAFETY RAILS (must be green before TEST_MODE=false)

9. **FIX-HIBERNATE-LIVE-VETO** (🔴 D04-F3/D07-F2/D08-F1/D11-F7, 🟠 D08-F3). Gate the AGGRESSIVE_PAPER
   bypass on `and TEST_MODE`; add an independent fresh `market:mode:current` hard-return in bot_core;
   add `AGGRESSIVE_PAPER_TRADING=false` to the flip runbook. *Depends on: #2 (mode must be trustworthy).*
10. **FIX-GOVERNANCE-FAIL-OPEN** (🔴 D04-F1/D09-F2, 🟠 D08-F5/D09-F4, 🟡 D04-F9; BUG-010). Treat
    CONSERVATIVE + stale governance as a hard cap bot_core honours; fix the `market:cfgi` read; ML-unavailable
    default below floor; CFGI sentinel. (Anthropic-credit dependency noted.)
11. **FIX-DAILY-LOSS-PERSISTENCE** (🔴→🟠 D08-F2/D04-F4/D06-F1). Reload today's realized loss on
    startup (same-UTC-day); don't hard-zero in live; tighten the default. *Depends on: #1 (restart cadence).*
12. **FIX-LIVE-BALANCE-SEED** (🟠 D04-F2). Seed `total_balance_sol` from on-chain getBalance at live
    startup (un-inflates exposure/drawdown denominators).
13. **FIX-SIZING-CAPS-WIRING** (🟠 D04-F7, D08-F7, D08-F4/D11-F1/F2, D08-F6, D04-F6). Real
    `MAX_SD_POSITIONS` env; fill-MC-ceiling fail-CLOSED; `ZoneInfo("Australia/Sydney")` for all sizing
    branches + de-duplicate the double time multiplier; align MIN_POSITION_SOL; rug-cascade predicate.

### Phase 3 — LIVE ACCOUNTING INTEGRITY (must be green before trusting trial PnL for go/no-go)

14. **FIX-LIVE-STAGED-TP-PNL** (🟠 D05-F1, D05-F2, D02-F12). Port cumulative PnL accumulation to live;
    collect all exit signatures and sum Path B native deltas; reconcile in-memory balance to on-chain.
    *Without this, the trial's own PnL data lies on every multi-TP trade.*
15. **FIX-DASHBOARD-MODE-FIDELITY** (🟠 D05-F3, D05-F4, 🟢 D05-F6/F8/F10, D02-F13). Mode-filter +
    COALESCE on analytics/snapshot; fix entry-price sentinel; standardize column semantics.

### Phase 4 — SECURITY / HYGIENE (before V5d unsupervised; mostly waived for supervised v5a-c)

16. **FIX-SECRET-LOGGING** (🟢 D10-F1) → then **SEC-001 rotation** (🟡 D10-F5) → **HARDEN-SENTRY**
    (🟢 D10-F3) → **DASHBOARD-AUTH-FAIL-CLOSED** (🟡 D10-F2, verify deployed `DASHBOARD_SECRET`).
17. **HYGIENE SWEEP** (🟢 D11-F3/F4 dead loss-override, D11-F9 doc, D06-F2/F3/F4 Redis leaks, D09-F5/F6
    Vybe, D12-F1 tests, D12-F7 latency, D03-F4/F5/F7 lifecycle, D02-F9 mark EXEC-002 resolved).

### Go-live gate (the §B deliverable for the flip plan)

**Must be GREEN before any `TEST_MODE=false`:** Phase 0 (#1-3), Phase 1 (#4-8), Phase 2 (#9-13), Phase 3
(#14). Phase 4 may follow under the documented supervised-v5a-c waiver, except DASHBOARD-AUTH-FAIL-CLOSED
(verify the deployed secret is set as a flip pre-flight). The existing CLAUDE.md live-flip preconditions
remain in force on top of this.

---

## §C — COVERAGE STATEMENT

| Dimension | Coverage | Notes |
|---|---|---|
| D01 Async/crash | **Full** | All 9 primary files; every gather/listener/loop enumerated. Did not runtime-verify that aioredis `listen()` raises TimeoutError (taken from prod evidence + known index). |
| D02 Live execution | **Full** | All 3 routes + both bot_core branches traced to on-chain submit + DB write. Idempotency/confirm/Jito analyzed. 5 of the 6 high-sev findings independently re-verified. |
| D03 Position lifecycle | **Full** | bot_core lifecycle spans + paper_trader complete. Not runtime-executed. |
| D04 Safety systems | **Full** | All 7 named systems traced to live-reachable code; 3 of the 5 blockers re-verified. |
| D05 Money-accuracy | **Full** | Every PnL write + every dashboard PnL read enumerated; both blockers re-verified. |
| D06 State management | **Full** | 5 primary files; connection/pool audit clean. Runtime Redis key sizes not inspected (read-only). |
| D07 Market classification | **Full** | 4-service classification call path traced. Not runtime-verified (current crash state from index). |
| D08 Config/TEST_MODE | **Full (code)** | Every execute_trade/_execute_*/_send_transaction call site traced. Deployed Railway env *values* not read (read-only). |
| D09 External deps | **High** | 7 primary files; live exit-price + market-mode feeds traced end-to-end; D09-F3 refuted on re-verification. |
| D10 Security | **Full** | Key lifecycle + secret-logging surfaces + dashboard auth. Deployed env values (e.g. is `DASHBOARD_SECRET` set) not verified — flagged SUSPECTED. Empirical solders repr/str leak tests run locally. |
| D11 Dead code/drift | **Full (mode/money paths)** | Primary files fully; dashboard_api/governance/treasury internals spot-grepped for markers only. |
| D12 Test/observability | **Full** | scripts/, tests/, heartbeat/health surfaces. (D11/D12 agents completed analysis + wrote files but failed the workflow's final StructuredOutput call — findings recovered from their durable files.) |

**Verification:** the recon→12-dimension workflow's automated adversarial pass populated only 6/51 verdicts
(StructuredOutput-completion flakiness). A **focused re-verification workflow** then independently
challenged-to-refute the 13 NEW load-bearing blockers; all 13 returned verdicts. Result: 4 survived 🔴, 6
downgraded 🔴→🟠 (real but not capital-safety-critical), 1 refuted to 🟢 (D09-F3), 2 confirmed 🟠. The
crash/availability blockers are accepted on **cross-dimension convergence** (the daily-loss reset surfaced
independently in D04/D06/D08; the pubsub crash in D01/D03/D04/D07/D09/D11/D12) plus the known-issues index.
Findings tagged CONFIRMS a known item carry the index's confidence.

**Not covered / out of scope:** runtime confirmation reads against Railway/Redis/DB on-chain (this was a
static source audit; a few findings are flagged SUSPECTED pending runtime/env checks at flip pre-flight).
Tier-3 dimensions (D10-D12) are fully covered. No coverage was fabricated.
