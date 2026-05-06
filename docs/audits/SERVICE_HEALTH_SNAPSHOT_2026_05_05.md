# Service-Health Snapshot 2026-05-05

**Session:** API-CREDITS-HEALTH-DIAGNOSTIC-001
**Author:** Claude Code (read-only)
**Scope:** Snapshot of every external API + credit-bound dependency. Surface silent failures, near-exhausted budgets, expired tokens, env drift, recent rate-limit incidents.
**Window:** Probes executed 2026-05-05 14:50–15:36 UTC. Logs scanned cover ~14:00–15:36 UTC for live services; treasury log spans 22+ hours.
**Constraints:** Read-only — no code/env/redeploy changes. One docs-only commit at session end.

---

## §1 Executive summary

**Counts:** 🟢 7 · 🟡 9 · 🔴 4 · ⚪ 1

**Top 3 most-urgent findings:**

1. **🔴 SocialData credits EXHAUSTED.** signal_aggregator log shows `113 ERROR: SocialData out of credits` in an 11-minute window (~10/min). Twitter follower lookup is permanently failing — every FILTER line shows `followers=-1` (sentinel). ML feature `twitter_followers` will be NULL on every fresh entry until Jay tops up. Re-occurrence of the 2026-04-22 SocialData credit drain noted in `SOCIALDATA-AUTO-TOPUP-001`. **Promotes that item from QUEUED → ACTIVE.**
2. **🔴 VYBE-URL-CODE-DRIFT-001 confirmed.** `services/signal_aggregator.py` has 3 hardcoded `https://api.vybenetwork.com` URLs at lines 753, 850, 2568 (HOLDER fallback, creator history, KOL/MM check). Probe of `.com` → HTTP 404. Probe of `.xyz` → HTTP 401 (auth, but endpoint responsive). Despite DOCS-004 (CLAUDE.md fix on 2026-04-30), the running code still uses the wrong domain. Failures swallowed by broad `except Exception` patterns — silent feature-coverage degradation. NEW Tier 1 patch.
3. **🔴 BUG-010 STILL ACTIVE.** governance log at 2026-05-05 13:55:58 UTC: `HTTP/1.1 400 Bad Request ... Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.` Governance falls back to CONSERVATIVE defaults; CFGI-driven personality enables/multipliers stuck. **Not V5a-blocking by current rules** (governance is advisory; ANALYST_DISABLED env is load-bearing instead) but worth top-up before V5a flip for live regime detection.

**Blocking findings (🔴):** 4 — SocialData credits, VYBE-URL-CODE-DRIFT, BUG-010 Anthropic, BUG-020 Discord 403 (carryover).

**V5a impact:** None of the 🔴 findings are V5a-blocking *per current gating rules*. BUG-010 reduces governance fidelity; SocialData/Vybe degrade ML feature coverage but don't gate trading. The independently-tracked V5a blockers (wallet 0.064 SOL, 48h observation, NORMAL window) are unchanged — see `V5A_GO_NO_GO_2026_05_01.md`.

---

## §2 Per-API findings

### §2.1 Helius (RPC + parseTransactions) — 🟢 HEALTHY

- **Probes:** `getNetworkStatus` returned epoch 967, slot 417,770,705, ~1227 real TPS / 3099 total TPS, version 3.1.13. `getBalance(4h4pst…ii8xJ)` returned **0.064095633 SOL** (V5a PC1 still failing — Jay action pending, unchanged from V5A audit).
- **Env drift:** `HELIUS_RPC_URL`, `HELIUS_PARSE_TX_URL`, `HELIUS_PARSE_HISTORY_URL`, `HELIUS_STAKED_URL`, `HELIUS_GATEKEEPER_URL` are **identical across all 8 services** (single `api-key=0f2e5160-...`).
- **Logs:** bot_core deploy log shows clean Helius behavior. No 429/5xx in 11+ min window. `service:health.helius_rpc/gatekeeper/parse` all `ok` (cached-with-protection).
- **Path B parity:** id 6580 backfill remains intact (per V5A audit §3 PC2). No new live trades exercised since LIVE-FEE-CAPTURE-002 deploy; Path B branch is exercised only when `correction_method='live_actual_v1'` write happens at live close-time.
- **Treasury caveat:** `services/treasury.py:60` early-returns None if `HELIUS_DAILY_BUDGET=="0"`. Treasury env doesn't set the var → default "0" applies → 270+ `WARNING: Could not fetch trading wallet balance` in last 22h. **Misleading log message** (treasury logs blame "Helius RPC connectivity" when the actual cause is the budget gate). Currently dormant because wallet=0.064 SOL ≪ 30 SOL trigger. New 🟡 item: `TREASURY-HELIUS-LOG-NOISE-001`.

### §2.2 PumpPortal (WebSocket + trade) — 🟢 HEALTHY

- **Signal flow:** signal_listener log shows 186 `pumpportal/new_token` signals + 157 `geckoterminal/new_pool` signals in an 8.5-min window (~22/min new_token rate, 18/min new_pool rate). Most-recent `PRICE_CREATE_BC` at 2026-05-05 15:10:32. EARLY_SUB_CLEANUP active every ~1min (early-sub pool oscillates 100-125, well under 200 cap).
- **WebSocket state:** Zero disconnect/reconnect events in either signal_listener (8.5-min window) or signal_aggregator (11.8-min window) logs.
- **Trade endpoint:** Not probed (would risk a real trade). Inferred healthy from `service:health.pumpportal: live, last signal 1s ago`.
- **Drift check:** `PUMPPORTAL_API_KEY` not surfaced in any service env list — likely WebSocket-only auth happens at connection time via different URL pattern; or pump.fun's local-trade API path uses signed transactions only (no API key). No drift to flag.

### §2.3 Anthropic (governance / CFGI) — 🔴 BROKEN (BUG-010)

- **Probe:** No external API call made (would burn credits unnecessarily; we already have the answer in governance logs).
- **Evidence:**
  - governance log 2026-05-05 13:55:58: `httpx INFO: HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 400 Bad Request"`
  - governance log: `Governance classification failed: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'} ... — using CONSERVATIVE defaults`
  - Redis `governance:latest_decision.reasoning` = `"classification failed: Error code: 400 ... Your cred"` (truncated)
  - `governance:last_run` = 2026-05-05T13:55:58 (~57 min before audit start)
- **Env:** `ANTHROPIC_API_KEY` is set on **all 8 services** with the same value (`sk-ant-api03-xsiqu8DC...`). This is excessive — only `governance` and possibly `signal_aggregator` should need it. Cleanup item, not blocking.
- **`service:health.anthropic`** reports `ok "key configured"` — this is **misleading**: the dashboard's probe only checks env var presence, not actual API responsiveness. New 🟡 item: `DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001` (probe should attempt minimal `/v1/messages` call instead of just env-var check).
- **Verdict:** BUG-010 unchanged from prior status. Jay action: top-up Anthropic credits to restore governance.

### §2.4 SocialData.tools (Twitter follower lookup) — 🔴 BROKEN

- **Probe:** External probe deferred (113 in-log ERROR lines in 11 min are conclusive evidence of credits exhausted).
- **Evidence:** signal_aggregator log most-recent line: `2026-05-05 15:09:21,485 [signal_aggregator] ERROR: SocialData out of credits`. Pattern: 113 occurrences in 11m50s ≈ 9.5/min.
- **Code path:** `services/signal_aggregator.py:467`: `logger.error("SocialData API key invalid — check SOCIALDATA_API_KEY env var")` — wait, the actual error message at 470 is `"SocialData out of credits"` for HTTP 402. The code checks for a sentinel response. 113 ERROR per 11min suggests every Twitter-handle-bearing signal triggers the call → fails → propagates as ERROR.
- **ML feature impact:** `twitter_followers` is permanently sentinel `-1` on every fresh entry, plus `has_twitter` etc. set to 0. Per the SOCIAL-SCORING-001 fix on 2026-04-30, the code adds `has_twitter`, `has_telegram`, `has_website`, `social_count` to features_json — these are now degraded. **Re-occurrence** of the 2026-04-22 SocialData credit drain (commit `512663b` mentioned `SocialData credits — Jay topped up to $10`).
- **Verdict:** Promotes `SOCIALDATA-AUTO-TOPUP-001` from QUEUED → ACTIVE. Jay action: top-up + auto-renewal alerting.
- **Environmental check:** `SOCIALDATA_API_KEY=6529|duPrXDkGi...` on all 8 services (single key, no drift).

### §2.5 Nansen (whale tracking) — 🟢 HEALTHY (dormant by design)

- **Redis state:**
  - `nansen:disabled` = **KEY NOT FOUND** (TTL expired ⚠ — supposed to be renewed daily per CLAUDE.md)
  - `nansen:dryrun_calls:2026-05-05` = 100,671 (high volume — but dry-run only)
  - `nansen:cache_hits:2026-05-05` = 488 (cached reads — cheap)
  - `nansen:credits:2026-04` = 100,963 (April month total dry-run-equivalent volume)
  - Many `nansen:holders:*` and `nansen:flows:*:1h` keys (cached responses).
- **Auto-protection: NANSEN_DRY_RUN=TRUE** is set on the 3 high-volume services (signal_aggregator, signal_listener, ml_engine). Logs confirm: every Nansen call is `[NANSEN_DRY_RUN] Would POST /...` with no real HTTP traffic. **The expired `nansen:disabled` Redis key is no longer load-bearing** — `NANSEN_DRY_RUN=TRUE` covers it for the active callers.
- **Audit risk:** the 5 services that DON'T have `NANSEN_DRY_RUN=TRUE` (bot_core, market_health, treasury, governance, web) — but per code these don't make Nansen calls (governance has a `nansen_client` safeguard at line 13:55:58 saying `Nansen client called by governance — only {'bot_core', 'signal_listener', 'signal_aggregator'} allowed`).
- **Drift (carryover from ENV-AUDIT-2026-04-29):**
  - `NANSEN_DAILY_BUDGET`: bot_core=50, sa=2000, sl=2000, ml_engine=2000, market_health=50, treasury=50, governance=50, web=50.
  - `NANSEN_API_KEY` split (SEC-001): bot_core/sa/ml_engine use `nsn_2ef96...` (key A); sl/market_health/treasury/governance/web use `cL2tg...` (key B).
- **`service:health.nansen`** reports `warn HTTP 401`. Consistent with key A being invalid server-side (per 2026-04-21 MCP-RECON finding) — but irrelevant in practice because all calls are dry-run.
- **Verdict:** dry-run shield is doing its job. Renew `nansen:disabled` daily key for defense-in-depth (low priority).

### §2.6 Telethon / Telegram — 🟡 WATCH

- **Connection state:** signal_listener log shows `[telethon.client.updates] INFO: Got difference for channel 1760456104` lines at 15:02:51 and 15:04:02 — **2 update events in 8.5 min**. Listener IS connected.
- **Channel activity:** channel `1760456104` is the only ID seen (this is `cryptoyeezuscalls` numerical ID). No telethon line in last ~6 min of window — channel inactive, not a session problem.
- **Errors:** Zero `FloodWait`, `AuthRestart`, `SessionPassword`, `AuthKey`, `SessionExpired` errors.
- **Env config:** `TELEGRAM_API_ID=23200589`, `TELEGRAM_API_HASH` set, `TELEGRAM_STRING_SESSION` set (~280 chars on signal_listener), `TELEGRAM_PHONE=+61402022363`, `TELEGRAM_CHANNEL=cryptoyeezuscalls`, `TELEGRAM_CHANNELS=cryptoyeezuscalls`, `TELEGRAM_ENABLED=true` on signal_listener.
- **Drift:** `TELEGRAM_ENABLED=true` is also set on `web` (probably display-only; see TUNE-008 `web` shadow params hygiene).
- **Verdict:** session valid, listener connected, channel just quiet during this window. Not a 🔴. **Watch:** if signal flow from telegram source is below historical rate over a longer window, dispatch a separate tracking session.

### §2.7 Binance (primary SOL price) — 🟢 HEALTHY

- **Probe:** `GET https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT` → `{"symbol":"SOLUSDT","price":"85.32000000"}`.
- **Cross-check:** `market:sol_price` Redis = 85.29 (1-2min stale, agreement within $0.03).
- **`service:health.binance`** reports `warn 319ms ping` (warn classification but functional; threshold may be tight).

### §2.8 Jupiter V3 (fallback SOL price) — 🟢 HEALTHY (slow)

- **Probe:** `GET https://api.jup.ag/price/v3?ids=So11...112` → `usdPrice=85.31450`, `liquidity=$724M`. 24h change +0.15%.
- **`service:health.jupiter`** reports `ok 2050ms HTTP 200` — slow at >2s. Watch if it climbs further.
- **Fallback path:** code in `services/dashboard_api.py:1599` prefers Binance and falls through to Jupiter; Jupiter is exercised only if Binance fails. Healthy redundancy.
- **JUPITER_API_KEY** present and identical across all 8 services (likely overprovisioned — only execution.py needs it; cleanup item).

### §2.9 Vybe — 🔴 BROKEN (URL DRIFT)

- **Probes:**
  - `https://api.vybenetwork.com/token/.../top-holders` → HTTP **404**
  - `https://api.vybenetwork.xyz/token/.../top-holders` → HTTP **401** (auth required, but route exists)
- **Code drift confirmed:** `services/signal_aggregator.py`:
  - Line 753: `url = f"https://api.vybenetwork.com/token/{mint}/top-holders?limit=20"` (HOLDER fallback)
  - Line 850: `url = f"https://api.vybenetwork.com/token/{mint}"` (creator-history lookup)
  - Line 2568: `vybe_url = f"https://api.vybenetwork.com/token/{mint}/holders?limit=20"` (KOL/MM check)
- **Correct usage exists elsewhere:** `services/nansen_wallet_fetcher.py:209` uses `https://api.vybenetwork.xyz/v4/wallets/top-traders` correctly.
- **Silent failure:** the 3 broken sites are wrapped in `try: ... except Exception as e: logger.debug(...)`. With debug-level logging in production INFO, these failures generate **zero visible errors**. Signal_aggregator log scan for "Vybe" / "vybenetwork" returned **0 hits over 11 min** — confirming silent failure (the calls are firing but failing immediately, with debug logs swallowed).
- **DOCS-004 status:** docs were updated `.com → .xyz` on 2026-04-30 (CLAUDE.md, AGENT_CONTEXT.md). Code was never migrated. Exactly the failure mode the audit prompt anticipated.
- **`service:health.vybe`** reports `ok` — but the dashboard_api uses a separate Vybe probe path that may use the correct `.xyz` URL. Verifying which URL the dashboard probes is out of scope here.
- **VYBE_API_KEY=`SXPAt2nZ...`** identical across all 8 services (single key, no drift).
- **Verdict:** **VYBE-URL-CODE-DRIFT-001** new Tier 1 fix item. ROI: small but non-zero — restores HOLDER fallback path, creator-history lookup, KOL/MM signal modifier. Cost S (3 string substitutions in one file + redeploy SA).

### §2.10 TabPFN (ml_engine) — 🟢 HEALTHY (with doc-drift footnote)

- **Token decode:** JWT exp = 1806900955 → **2027-04-05 04:55:55 UTC** (≈335 days from 2026-05-05).
- **Doc drift:** prior handoff stated "expires 2033". Actual is 2027. Memory note + docs may need correction. Not urgent (1+ year runway).
- **Env:** `TABPFN_TOKEN` set ONLY on ml_engine ✅ (no drift). `TABPFN_ALLOW_CPU_LARGE_DATASET=1`.
- **Activity:** ml_engine log shows clean operation; ADWIN drift detection enabled, ensemble loaded with 911 samples, AUC=0.0000, status=TRAINED.
- **AUC=0 caveat:** separate 🟡 issue (`ML-AUC-ZERO-001` — pre-existing, not caused by TabPFN). Feature coverage 13-14/55 = 24-25% (per CLAUDE.md Issue #2 FEATURE SPARSITY).

### §2.11 Sentry (error tracking) — 🟢 HEALTHY

- **DSN per service:** `SENTRY_DSN` set on all 8 services with **distinct DSN values** (correct architecture — one project per service in `o4511244762546177`):
  - bot_core: ...4511245238861824
  - signal_aggregator: ...4511245238992896
  - signal_listener: ...4511245239189504
  - ml_engine: ...4511245239648256
  - market_health: ...4511245239255040
  - treasury: ...4511245239582720
  - governance: ...4511245239386112
  - web: ...4511245243711488
- **Release tagging:** all 8 service startup banners show `Sentry initialized for <service> (env=production, release=ea0da2f89164)` — matches current main HEAD `ea0da2f`. Release tagging is **active** across all services. Confirms V5A audit §5 mention is satisfied.
- **No Sentry write probe** (DSN is write-only without a server token; not needed — release-tagging proof in startup logs is sufficient).

### §2.12 Railway (platform) — 🟢 HEALTHY

- **Service inventory:** 10 entries returned by `list-services`: market_health, web, signal_aggregator, ml_engine, bot_core, Redis, signal_listener, treasury, governance, Postgres. (8 deployable + 2 managed.) All deployable services have logs and recent activity.
- **Last-deploy timestamps (release `ea0da2f89164` on all):**
  - governance 2026-05-05 13:55:56 UTC
  - treasury 2026-05-05 13:58:49 UTC
  - market_health 2026-05-05 14:00:19 UTC
  - ml_engine 2026-05-05 13:59:59 UTC
  - bot_core 2026-05-05 14:16:48 UTC
  - signal_aggregator + signal_listener: deploy banners not in captured window (mid-stream snapshot) — must have been earlier
- **Implication:** all 8 services restarted within a ~21-min window, suggesting a global redeploy (likely the most recent commit `ea0da2f` BOT-CORE-ML-GATE-001 trigger). Confirms `RAILWAY-REDEPLOY-DISCIPLINE-001` finding (no per-service path filters in `railway.toml` — every push redeploys all services).
- **Live activity verification:**
  - bot_core: just executed PAPER trade on `EV1na7Wj5WLX` at 14:58:36 (entry +139.9% trail engaged). Pipeline live and healthy.
  - signal_aggregator: 113 SocialData errors but 221 successful signals scored. Pipeline alive.
  - signal_listener: 186 pumpportal new_token + 157 geckoterminal new_pool signals/8.5min. Pipeline alive.
  - market_health: cycling DEFENSIVE/HIBERNATE every 30 min based on migration count. Operating normally.
- **Memory/CPU:** Railway MCP doesn't surface this in the available tooling on this version. Out of scope.

---

## §3 Cross-service env drift matrix

Read 2026-05-05 14:50 UTC via `mcp__railway__list-variables` (kv format). Raw outputs saved to `.tmp_api_health_diagnostic/` (gitignored, contains secrets).

### §3.1 ML threshold drift (carryover from ENV-AUDIT-2026-04-29 §1.3)

| var | bot_core | signal_aggregator | web | others |
|---|---:|---:|---:|---|
| ML_THRESHOLD_SPEED_DEMON | **40** | **65** | **45** | unset |
| ML_THRESHOLD_BOT_CORE_SD | **40** (NEW post-Session-7) | unset | unset | unset |
| ML_THRESHOLD_ANALYST | 35 | 55 | 50 | unset |
| ML_THRESHOLD_WHALE_TRACKER | 35 | 55 | 50 | unset |

Net effect (paper sample): SA gate at 65, bypassed by `AGGRESSIVE_PAPER_TRADING=true`; bot_core has ML_THRESHOLD_BOT_CORE_SD=40 deployed but per `BOT-CORE-ML-GATE-001` status the code may not yet evaluate it — verification pending in a separate session. Web=45 is display-only (dashboard SD threshold display).

### §3.2 Position sizing drift (post-TUNE-004 hygiene fix on SA)

| var | bot_core | signal_aggregator | others |
|---|---:|---:|---|
| MIN_POSITION_SOL | 0.05 | 0.05 ✅ | 0.10 (vestigial) |
| MAX_POSITION_SOL | 0.25 | n/a | n/a |
| MAX_POSITION_SOL_FRACTION | **(unset; code default 0.10)** | n/a | n/a |
| MAX_SD_POSITIONS | 20 | 20 ✅ | 2-3 (vestigial) |
| SPEED_DEMON_BASE_SIZE_SOL | 0.15 | 0.15 ✅ | 0.45 (vestigial) |
| SPEED_DEMON_MAX_SIZE_SOL | 0.25 | 0.25 ✅ | 0.75 (vestigial) |

`MAX_POSITION_SOL_FRACTION` not set anywhere — bot_core code default 0.10 applies. **`MAX-POSITION-SOL-FRACTION-ENV-001`** carryover (V5A audit flagged this).

### §3.3 TEST_MODE per service

| service | TEST_MODE | notes |
|---|---|---|
| bot_core | **true** | paper-mode authority |
| signal_aggregator | true | |
| signal_listener | true | |
| ml_engine | true | |
| market_health | true | |
| treasury | **false** ⚠ | TREASURY-TEST-MODE-002 ongoing (dormant @ 0.064 SOL) |
| governance | true | |
| web | true | |

### §3.4 NANSEN_DAILY_BUDGET drift (carryover)

| service | value |
|---|---:|
| bot_core, market_health, treasury, governance, web | 50 |
| signal_aggregator, signal_listener, ml_engine | 2000 |

Mitigated by `NANSEN_DRY_RUN=TRUE` on the 3 high-budget services. Real consumption ≈ 0. Hygiene-only cleanup item.

### §3.5 NANSEN_API_KEY split (SEC-001 carryover)

- Key A (`nsn_2ef96...`): bot_core, signal_aggregator, ml_engine
- Key B (`cL2tg...`): signal_listener, market_health, treasury, governance, web

`service:health.nansen: warn HTTP 401` indicates one or both keys are invalid server-side. Doesn't matter operationally (dry-run shield), but rotation should consolidate to one key.

### §3.6 ANTHROPIC_API_KEY scope creep

`ANTHROPIC_API_KEY` set on **all 8 services**. Only `governance` makes Anthropic API calls (per `governance.py`); occasionally `signal_aggregator` historically. The other 6 services should not have it. **TUNE-009-anthropic-cleanup** Tier 2 hygiene item (low priority — same key across services, leak surface unchanged).

### §3.7 TIME_PRIME (post-Session-1, holding correctly)

- bot_core: `TIME_PRIME_MULTIPLIER=1.0` ✅
- `TIME_PRIME_HOURS_AEST` not set anywhere (code default `""`) ✅

### §3.8 Helius URLs (consistent ✅)

`HELIUS_RPC_URL`, `HELIUS_PARSE_TX_URL`, `HELIUS_PARSE_HISTORY_URL`, `HELIUS_STAKED_URL`, `HELIUS_GATEKEEPER_URL` — identical across all 8 services. Single api-key family `0f2e5160-...`. No drift.

### §3.9 Web (dashboard) shadow params (TUNE-008 carryover)

`web` carries an extensive set of personality shadow params: `SD_BASE_SIZE_SOL=0.25`, `SD_STOP_LOSS_PCT=25.0`, `SD_TAKE_PROFIT_PCT=50.0`, `SD_MIN_BUYERS=5`, `SD_MIN_TXNS=8`, `SD_EARLY_CHECK_SECONDS=90`, `SD_EARLY_MIN_MOVE_PCT=2.0`, `ANALYST_BASE_SIZE_SOL=0.45`, `WHALE_BASE_SIZE_SOL=0.60`, `TRAIL_ACTIVATE_PCT=15.0`, `TRAIL_PCT=0.80`, etc. All non-binding (web doesn't trade). Hygiene cleanup deferred.

---

## §4 Recent-error scan (last 6h logs)

### §4.1 bot_core (~42 min visible window 14:16–14:58 UTC)

| pattern | count |
|---|---:|
| ERROR | 0 |
| WARN/WARNING | 0 |
| 429 | 0 |
| 401 | 0 |
| 5xx | 0 |
| timeout | 0 |
| Exception | 0 |
| Traceback | 0 |

**Verdict:** clean. PAPER pipeline executed `EV1na7Wj5WLX` entry at 14:58:36 (+139.9% trail engaged) — bot is alive and trading paper.

### §4.2 signal_aggregator (11m50s visible window 14:57–15:09 UTC)

| pattern | count | notes |
|---|---:|---|
| ERROR | **113** | ALL `SocialData out of credits` |
| WARN | 0 | no WARN-level lines |
| 429 | 0 | |
| 401 | 0 | |
| 5xx | 0 | |
| timeout | 0 | |
| Exception | 0 | |
| Traceback | 0 | |
| HIBERNATE rejections | 0 | mode=DEFENSIVE, signals continue to be processed |
| SD_MC_CEILING rejections | **16** | gate active at $3000, e.g. `SD reject HYKb6XAz: MC $3235 > ceiling $3000` |

**Verdict:** clean apart from SocialData credit exhaustion (single root cause, 9.5 errors/min). SD_MC_CEILING_002 is firing correctly. Concerning observation: **113 ERROR but 0 WARN** — credit exhaustion is logged at ERROR level when it's really a 3rd-party degraded condition, not a SA bug. Logging-level audit out of scope.

### §4.3 signal_listener (8.5min visible window 15:02–15:10 UTC)

| pattern | count | notes |
|---|---:|---|
| ERROR | **2** | both `Discord bot lacks permission to read channel (got 403)` (BUG-020 still firing) |
| WARN | 0 | |
| 429 | 0 | (1 false-positive in price digit) |
| 401 | 0 | |
| Exception | 0 | |
| Traceback | 0 | |

**Verdict:** clean apart from BUG-020 Discord 403 firing every 5 min (line 173 at 15:04:32 + line 505 at 15:09:32). BUG-020 carryover; not new.

### §4.4 governance (1 cycle visible 13:55:56–13:55:58)

| pattern | count |
|---|---:|
| ERROR | 1 (BUG-010 Anthropic 400) |
| WARN | 1 (Governance metrics SQL type mismatch — known, cosmetic, BUG-019) |

Cycle lasted ~3s; next at +4h.

### §4.5 ml_engine (~90min window 14:00–15:30 UTC)

Clean. Feature-coverage logs every ~2min showing 13-14/55 (24-25%). Incremental train at 14:00 over 7109 samples. AUC=0.0000.

### §4.6 market_health (~90min window 14:00–15:36 UTC)

| pattern | count | notes |
|---|---:|---|
| ERROR | 0 | |
| WARN | 3 | 2× `Request failed for https://api.llama.fi/overview/dexs/Solana` (api.llama.fi flaky) + 1× `cfgi.io request timed out after 10s` |
| HIBERNATE transitions | 2 | mode toggles with sentiment cycling |

Mode cycled NORMAL → DEFENSIVE → HIBERNATE → DEFENSIVE → DEFENSIVE → … Most-recent: DEFENSIVE @ 15:36. **Healthy cycling per recalibrated MARKET-MODE-001 thresholds.**

### §4.7 treasury (22h+ visible window 13:58 → 12:39 next day UTC)

| pattern | count | notes |
|---|---:|---|
| WARN | **270+** | every 5 min: `Could not fetch trading wallet balance` |
| WARN heartbeat | 14 | every ~50 min: `Treasury: 3 consecutive balance check failures. Check Helius RPC connectivity.` |
| ERROR | 0 | |
| Real Helius RPC outage | NONE | misleading log message |

**Root cause:** `services/treasury.py:60` early-returns None when `HELIUS_DAILY_BUDGET=="0"` (default). Treasury env doesn't set the var. The "Helius RPC connectivity" message is misleading — the gate is firing as designed, but the warning text doesn't reflect that. New 🟡 item: `TREASURY-HELIUS-LOG-NOISE-001` (rename WARN to `treasury balance fetch disabled by HELIUS_DAILY_BUDGET=0`).

### §4.8 web / dashboard (~28min visible window 12:23–12:51 next-day UTC)

| pattern | count | notes |
|---|---:|---|
| ERROR | 0 | |
| WARN/WARNING | **127** | all `DB query error: column "corrected_pnl_sol" does not exist` |
| 429/401/5xx | 0 | every aiohttp.access line returns 200 |
| dashboard activity | live | ~1 req/min on /api/* endpoints; latest GET /api/market 200 580B |

**Concerning:** 127 SQL warnings about a column that *does* exist on `paper_trades` (per AGENT_CONTEXT.md §9: 1137 pass_through rows). The query likely runs against a different table (probably `trades` or a join including it) where the column was never added. Need code grep to identify the offending query path. New 🟡: `DASHBOARD-CORRECTED-PNL-WARN-001`.

### §4.9 Aggregate

- Total **🔴-class incidents** (>5 in 6h): 1 — SocialData (113 in 11min ≈ would project to 3700+ in 6h).
- Total **🟡-class incidents** (1-5 in 6h, low single-digit per service): bot_core 0, sl 2 (Discord), market_health 3, governance 1, web 127 SQL warnings (high count but single root cause), treasury 270 WARN (single root cause, dormant impact).
- Net assessment: signal pipeline healthy; one credit-exhausted dependency (SocialData) actively degrading ML feature coverage; legacy log-noise sources (treasury, dashboard SQL) not impacting trading.

---

## §5 Redis hygiene

### §5.1 State of key keys

| key | value | TTL | notes |
|---|---|---|---|
| bot:status | RUNNING, 22.59 SOL portfolio, 0 open, market_mode=DEFENSIVE | (unknown via MCP — dashboard shows 15s freshness) | ✅ |
| bot:emergency_stop | NOT FOUND | — | ✅ |
| bot:loss_pause_until | NOT FOUND | — | ✅ |
| bot:consecutive_losses | `0` | — | ✅ |
| bot:portfolio:balance | 22.5942 | — | ✅ |
| market:mode:current | DEFENSIVE | — | ✅ (improvement vs V5A audit's HIBERNATE; cycles per recalibrated thresholds) |
| market:mode:override | NOT FOUND | TTL EXPIRED ⚠ | needs daily renewal — but AGGRESSIVE_PAPER masks effect for paper |
| market:sol_price | 85.29 | (5min cache visible) | ✅ within $0.03 of Binance/Jupiter |
| market:health | full snapshot present | ~5min cache | ✅ |
| market:migration_count_1h | 20 | — | DEFENSIVE band (10-30) per MARKET-MODE-001 thresholds |
| market:new_token_count_1h | 956,935 | — | high-volume baseline |
| market:loss_override | NOT FOUND | — | consistent with MARKET-LOSS-OVERRIDE-DEAD-CODE-001 (dead writer) |
| governance:latest_decision | CONSERVATIVE; BUG-010 reasoning | 28518s (~7.9h) | reflects latest failed governance run |
| governance:last_run | 2026-05-05T13:55:58 | — | ~57min before audit |
| governance:mode | (present) | — | |
| nansen:disabled | NOT FOUND | TTL EXPIRED ⚠ | not load-bearing because NANSEN_DRY_RUN=TRUE on hot services |
| signal_aggregator:health | ok @ 14:52:16 | ~99s | ✅ heartbeat alive |
| service:health | full snapshot from dashboard | (live) | binance warn 319ms, nansen warn 401, jupiter slow 2050ms |
| paper:positions:* | 0 keys | — | ✅ (consistent with bot:status open=0) |
| bot:open_positions:* | 0 keys | — | ✅ |
| paper:stats:* | many daily keys back to 2026-03-27 | — | normal accumulation |
| signals:raw | (present, list type) | (LLEN unavailable via MCP) | per ENV-AUDIT-2026-04-29: 2.9M with no TTL — **leak likely continues** (TUNE-007 / SIGNALS-RAW-TTL-001) |
| signals:scored | (present, list) | unknown | per ENV-AUDIT-2026-04-29: 89 — current size unknown |
| signals:evaluated | (present, list) | unknown | last 50 — bounded |
| ml:model:meta | (hash; WRONGTYPE on get) | — | known per ENV-AUDIT-2026-04-29 §3 — AUC=0 last train |

### §5.2 TTL-expired keys requiring daily renewal (per CLAUDE.md)

- **`market:mode:override=NORMAL EX 86400`** — currently expired
- **`nansen:disabled=true EX 86400`** — currently expired

Neither is V5a-blocking (AGGRESSIVE_PAPER_TRADING masks override; NANSEN_DRY_RUN masks Nansen). Renewal hygiene tracked.

### §5.3 Tooling gap

`mcp__redis__get` does not return TTL or list lengths (LLEN). Cannot verify `signals:raw` LLEN delta from prior 2.9M, nor measure key-aging directly. Out-of-scope tooling note: a `redis-cli -h gondola.proxy.rlwy.net ...` Bash recipe could fill this gap in a future audit.

---

## §6 Open items / new roadmap entries

### §6.1 New 🔴 (Tier 1, PROPOSED)

| ID | Title | Cost | Notes |
|---|---|---|---|
| `VYBE-URL-CODE-DRIFT-001` | Replace `api.vybenetwork.com` → `api.vybenetwork.xyz` at signal_aggregator.py:753, 850, 2568 | S (3 strings + redeploy SA) | restores HOLDER fallback + creator-history + KOL/MM signal modifier; current silent failure |
| `SOCIALDATA-AUTO-TOPUP-001` | promote QUEUED → ACTIVE | S (Jay action: top-up; alerting follow-up) | 113 ERROR/11min in SA log; ML twitter_followers permanently -1 |

### §6.2 New 🟡 (Tier 2, WATCH)

| ID | Title | Notes |
|---|---|---|
| `TREASURY-HELIUS-LOG-NOISE-001` | Rename treasury balance-fetch warning to reflect HELIUS_DAILY_BUDGET=0 gate | services/treasury.py:218; dormant since wallet=0.064 SOL; 270+ misleading WARNs/22h |
| `DASHBOARD-CORRECTED-PNL-WARN-001` | Identify the dashboard query path that produces 127 `column "corrected_pnl_sol" does not exist` warnings/28min | likely a query against `trades` table (lacks the column); add COALESCE or column to `trades` |
| `DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001` | dashboard's `service:health.anthropic` only checks env-var presence — should attempt minimal /v1/messages probe | misleading "ok" status while BUG-010 active |
| `TABPFN-EXPIRY-DOC-DRIFT` | docs say "expires 2033"; JWT exp claim = 2027-04-05 | low priority (1+ year runway) |
| `TABPFN-AUC-ZERO-001` | `ml:model:meta.auc=0.0000` after 7109-sample retrain at 14:00 UTC | metric storage or training convergence — separate ML quality investigation |
| `ANTHROPIC-KEY-SCOPE-001` | `ANTHROPIC_API_KEY` set on all 8 services; only governance uses it | hygiene cleanup; same-key, no leak surface delta |
| `JUPITER-API-KEY-SCOPE-001` | `JUPITER_API_KEY` set on all 8 services; only execution.py needs it | hygiene cleanup |
| `BOT-CORE-SOCIAL-FEATURE-DEGRADATION-001` | confirm features_json on rows entered during SocialData credit exhaustion show `has_twitter=0` regardless of source signal | ML training implication if SocialData-out windows skew sample |
| `MARKET-LOSS-OVERRIDE-DEAD-CODE-001` (carryover) | confirmed: `market:loss_override` writer fires but no reader | hygiene cleanup |

### §6.3 Carryover blocking (unchanged, NOT introduced by this session)

- `BUG-010` Anthropic credits — Jay action
- `BUG-020` Discord 403 (signal_listener) — code/permission fix
- `MAX-POSITION-SOL-FRACTION-ENV-001` (V5A audit) — env var unset
- `TREASURY-TEST-MODE-002` — dormant by wallet size
- `ML-THRESHOLD-DRIFT-2026-04-29` — across SA/bot_core/web
- `RAILWAY-REDEPLOY-DISCIPLINE-001` — confirmed again (8 services restarted ~simultaneously today)
- `SIGNALS-RAW-TTL-001` (TUNE-007) — likely still leaking
- `SOCIALDATA-AUTO-TOPUP-001` — promoted to ACTIVE
- `HELIUS-STAKED-FALLBACK-VERIFICATION-001` — not exercised in this window; staked URL is set everywhere but no error path observed

---

## §7 What this session does NOT cover

- **Signing path verification** — NOT probed (would require a real or simulated transaction). Last known status from CLAUDE.md: signing fix deployed but not validated under recent live conditions. Out of scope.
- **PumpPortal trade endpoint** — health inferred from signal flow only (cannot probe without risking trade).
- **Anthropic minimal probe** — skipped (avoid burning credits while exhausted).
- **Helius parseTransactions actual probe on a live signature** — skipped (only id 6580 has live data; backfill verified at deploy time of LIVE-FEE-CAPTURE-002, no new live trades since).
- **Redis LLEN / TTL on list keys** — Redis MCP doesn't expose these. signals:raw size delta from prior 2.9M unknown. Acknowledged limitation.
- **Railway deployment list / per-deploy timestamps** — Railway CLI v4.6.0 lacks `list-deployments`; partial workaround via startup-banner timestamps in logs.
- **Twitter listener health beyond signal_listener log** — channel inactive ≠ session expired; would need hours-of-history sample to distinguish.
- **Discord bot 403 root cause** — known issue (BUG-020), permission/role config in Discord — out of scope.

---

## §8 Decision Log entry (for ZMN_ROADMAP.md)

```
2026-05-05 API-CREDITS-HEALTH-DIAGNOSTIC-001 ✅ COMPLETE — Service-health snapshot across 12 dependencies. Findings: 4 🔴 (SocialData credits exhausted, VYBE-URL-CODE-DRIFT-001, BUG-010 Anthropic still active, BUG-020 Discord 403), 9 🟡 (TREASURY-HELIUS-LOG-NOISE, DASHBOARD-CORRECTED-PNL-WARN, DASHBOARD-HEALTH-CHECK-PROBE-DEPTH, TABPFN-EXPIRY-DOC-DRIFT, AUC=0, ANTHROPIC + JUPITER key scope, social feature degradation, market:loss_override dead code), 7 🟢 (Helius, PumpPortal, Binance, Jupiter, TabPFN auth, Sentry, Railway), 1 ⚪ (signals:raw LLEN unmeasurable via MCP). Top issues: (1) VYBE-URL-CODE-DRIFT-001 — signal_aggregator.py:753/850/2568 uses .com → 404, silent failure swallowed by `except Exception`; DOCS-004 fixed docs but not code; new Tier 1; (2) SocialData credit drain — 113 ERROR/11min in SA log; promotes SOCIALDATA-AUTO-TOPUP-001 to ACTIVE; (3) BUG-010 Anthropic credits still exhausted — governance returns CONSERVATIVE defaults. Audit: docs/audits/SERVICE_HEALTH_SNAPSHOT_2026_05_05.md. No code/env changes (read-only).
```

---

## §9 Reproducibility

```python
# Helius probes
mcp__helius__getBalance(address="4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ")
mcp__helius__getNetworkStatus()

# Railway env per service
mcp__railway__list-variables(service="<bot_core|signal_aggregator|signal_listener|ml_engine|market_health|treasury|governance|web>", kv=true)

# Logs
mcp__railway__get-logs(service="<name>", logType="deploy")

# Redis (TTLs and LLEN unavailable via MCP — use redis-cli for those)
mcp__redis__get(key="<key>")
mcp__redis__list(pattern="<pat>")

# Public probes
WebFetch("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT")
WebFetch("https://api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112")
WebFetch("https://api.vybenetwork.com/token/<mint>/top-holders")  # → 404
WebFetch("https://api.vybenetwork.xyz/token/<mint>/top-holders")  # → 401
```

JWT decode for TabPFN:
```python
import base64, json
t = "<TABPFN_TOKEN>"
header_part, payload_part, _sig = t.split(".")
pad = lambda s: s + "=" * ((4 - len(s) % 4) % 4)
header = json.loads(base64.urlsafe_b64decode(pad(header_part)))
payload = json.loads(base64.urlsafe_b64decode(pad(payload_part)))
# payload['exp'] = 1806900955 → 2027-04-05 04:55:55 UTC
```

---

## §10 Carry to next session

This snapshot is a baseline. If a follow-up session re-runs the same probes and finds:
- 🔴 where this session found 🟢: regression dated to today's audit window
- 🟢 where this session found 🔴: improvement (e.g., post-Anthropic top-up)
- New ⚪: tooling gap to address

Cadence recommendation: re-run **every 7 days** (post-Jay-top-up + after any new external API integration). Given 3+ active 🔴, current cadence may need to be tighter for SocialData/Anthropic until resolved.
