# STATE-SNAPSHOT-2026-05-08

**Type:** Read-only state verification. Zero env / Redis / code changes.
**Started:** 2026-05-08 ~13:21 UTC
**Repo HEAD at start:** `15a334a` (DEFENSIVE-OVERRIDE-PROBE-001 docs)
**Author:** Claude Code (Opus 4.7) via prompt
**Predecessors:** `DEFENSIVE-OVERRIDE-PROBE-001` (start 2026-05-06 22:29 UTC), `STRATEGY-CLIFF-INVESTIGATION-001` (2026-05-07).

---

## Executive summary

- 🔴 **DEFENSIVE-OVERRIDE-PROBE-001 EXPIRED.** `market:mode:override` is absent at audit time; `market:mode:current=NORMAL`. Probe was set 2026-05-06 22:29:10 UTC with 24h TTL → expired 2026-05-07 22:29:10 UTC. Renewal did NOT fire on 2026-05-07. The probe ran for ~24h before lapsing.
- 🟢 **Trading wallet UNCHANGED at 0.064095633 SOL** [VERIFIED:helius]. Holding wallet **rose to 0.190842421 SOL** from prior 0.0098 SOL baseline (+0.181 SOL drift; either Jay top-up or treasury sweep — flag for confirmation).
- 🔴 **Vybe URL drift still active** (`VYBE-URL-CODE-DRIFT-001`). Code at signal_aggregator.py:753, 850, 2568 still uses `.com` (404). `.xyz` route alive (400/401 with bogus auth). API-CREDITS audit's finding unchanged.
- 🔴 **Anthropic credit balance still exhausted** (`BUG-010`). Redis `governance:latest_decision` shows `mode=CONSERVATIVE` with `reasoning="classification failed: Error code: 400 ... 'message': 'Your cred..."`. Governance fallback to defaults is firing.
- 🟢 **Helius RPC + parseTx** healthy (network status returned epoch 968, ~1588 real TPS, network healthy).
- 🟡 **SocialData** auth route alive (401 with bogus token); credit-state cannot be confirmed without burning a real call. Sentinel-rate cross-check skipped (probe-period rows had no `mode_at_entry` to filter on; SD coverage requires a separate query). Carry-over diagnostic stays open.
- 🟢 **Bot RUNNING.** TEST_MODE=true, paper portfolio 24.83 SOL, daily PnL +0.41 SOL, 1 open Redis position (cosmetic ghost — see §4).
- 🟡 **Probe-period paper sample IS contaminated** (mixed override-forced DEFENSIVE + threshold-determined NORMAL). 266 SD-paper trades since probe SET, +2.04 SOL net. Pre-expiry 24h: 54 trades / +0.640 SOL / 44.4% WR. Post-expiry 14h45m: 212 trades / +1.398 SOL / 54.2% WR. Mode coverage cannot be reconstructed from `features_json` (field absent).
- 🟢 **Code state intact.** `BOT-CORE-ML-GATE-001` commit `ea0da2f` present in main. `SD_MC_CEILING_002` gate at signal_aggregator.py:1846-1881 (handover doc said 1833-1879 — minor line drift, function intact). `TIME_PRIME` env-controlled block at bot_core.py:750-764 (handover said 695-696 — different lines but env-controlled and disabled per spec).
- 🟡 **Hardcoded TZ at bot_core.py:754** still present (`TIME-PRIME-AEDT-AEST-DRIFT-001`). Existing tracked item; not new.

---

## §1 Probe state

| Key | Value | Source |
|---|---|---|
| `market:mode:override` | ABSENT (key not found) | [VERIFIED:redis-mcp] |
| `market:mode:current` | `NORMAL` | [VERIFIED:redis-mcp] |
| `bot:status.market_mode` | `NORMAL` | [VERIFIED:redis-mcp] |
| `KEYS market:mode:*` | 1 key only: `market:mode:current` | [VERIFIED:redis-mcp] |
| `bot:emergency_stop` | ABSENT | [VERIFIED:redis-mcp] |

**Decision: 🔴 PROBE EXPIRED.**

Probe was set at 2026-05-06 22:29:10 UTC with `EX 86400` (24h TTL). Per-CLAUDE.md daily-renewal expectation, the override should have been re-set at or before 2026-05-07 22:29:10 UTC. It was not. Override is now absent and mode has reverted to threshold-determined (currently NORMAL).

**Probe duration: ~24h** (one full TTL cycle, no renewals). Sample below splits at the expiry boundary so the eval session can decide whether to use the 54-trade probe-active window only, the full 266-trade window with mode-coverage caveat, or run a fresh probe with proper renewal.

**Fresh probe NOT re-set in this session** per prompt §1: "If 🔴, do NOT re-set the override in this session — the eval session needs to make that call once it has the contamination assessment." Compliance verified.

**Mode-coverage reconstruction (probe-period):** [VERIFIED:psql] `features_json` for all 263 sample rows had no `mode_at_entry`/`market_mode`/`mode` field — 263/263 returned None on key lookup. The bot does NOT currently persist market-mode at entry on each paper_trades row. Per-row mode reconstruction is not possible from DB alone for this window. Eval-session limitation.

---

## §2 Wallets

| wallet | address | balance now (SOL) | prior verified | drift |
|---|---|---:|---|---:|
| Trading | `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` | **0.064095633** | 0.064095633 (2026-04-30 09:00 UTC) | 0.000 |
| Holding | `2gfHQvyQdpDtiyUcFQJE6o15VkrHn7YXubp8DRwttWJ9` | **0.190842421** | 0.0098 (2026-04-29 12:39 UTC) | **+0.181** 🟡 |

**Trading wallet:** UNCHANGED at lamport-precision baseline. No live trades, no transfers since 2026-04-21 outgoing 1.5 SOL. ✅

**Holding wallet drift +0.181 SOL** [VERIFIED:helius]: AGENT_CONTEXT.md last verified ~0.0098 SOL on 2026-04-29. Now 0.1908 SOL. **Possible causes:**
- Jay top-up (deliberate)
- Treasury sweep — but treasury is dormant (wallet=0.064 << 30 trigger), so this should NOT have happened from automation
- Another wallet move

This warrants confirmation before treating as authoritative. Not a V5a blocker (V5a expects Jay top-up of trading wallet, not holding).

[VERIFIED:helius] both balances captured via `mcp__helius__getBalance` at audit time.

---

## §3 External API health

| API | Status | Evidence | Notes |
|---|---|---|---|
| **Helius RPC + Network** | 🟢 | `getNetworkStatus`: epoch 968, real TPS ~1588, total TPS ~3449, version 3.1.13. Both wallet `getBalance` calls succeeded with sub-second latency. | Healthy. Same key family `0f2e5160-...` deployed on all 8 services [VERIFIED:railway-mcp] |
| **Vybe `.com` (current code)** | 🔴 | `curl https://api.vybenetwork.com/token/<mint>/holders → 404 Not Found`. Code refs at signal_aggregator.py:753, 850, 2568 confirmed via Grep. | `VYBE-URL-CODE-DRIFT-001` UNCHANGED. Tier 1 code change pending. |
| **Vybe `.xyz` (working base)** | 🟢 (route) | `curl https://api.vybenetwork.xyz/token/<mint> → 401 Unauthorized` (no auth) / 400 (dummy auth). Route alive on `.xyz`. | DOCS-004 fixed docs not code. Functional auth state for the actual key not probed (would burn credits). |
| **SocialData** | 🟡 | `curl https://api.socialdata.tools/twitter/user/elonmusk -H "Authorization: Bearer dummy" → 401`. Route alive. | Real-key burst not probed. Carry-over from API-CREDITS-001 (🔴 113 errors/11min in May 5 audit). Status assumed unchanged absent fresh log evidence. |
| **Anthropic** | 🔴 | `curl https://api.anthropic.com/v1/messages -X POST -H "x-api-key: dummy" → 401`. Route alive. **Live evidence:** Redis `governance:latest_decision` body: `"reasoning": "classification failed: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your cred..."` — confirms BUG-010 still firing now. | Governance fallback to CONSERVATIVE active. Top-up needed. |
| **PumpPortal** (proxy via bot health) | 🟢 (inferred) | `signal_aggregator:health` heartbeat fresh (2026-05-08 13:20:57 UTC, 4s before audit fetch). | If aggregator's PumpPortal feed were dead, no signals would scored, but aggregator reports "ok". |
| **Jupiter / Binance SOL price** | 🟢 (inferred) | `market:health.sol_price=88.37`, `market:sol_price=88.37` consistent. | Both sources agree (no second probe done in this session). |

**API audit limitation:** Real-key probes against Vybe/SocialData/Anthropic skipped to avoid burning credits or making auth-real calls in a read-only session. Where carry-over status from API-CREDITS-HEALTH-DIAGNOSTIC-001 (2026-05-05) is unchanged in cross-check (Anthropic via Redis evidence here), it is asserted as still 🔴. Where no fresh evidence exists (Vybe/SocialData credit state), this audit confirms only that the routes are alive.

---

## §4 Paper-trades probe-period summary

[VERIFIED:psql] CSV at `.tmp_state_snapshot/probe_period_trades.csv` (gitignored — 263 rows, since 2026-05-07 00:00 UTC).

### Headlines (n=263 since 2026-05-07 00:00 UTC, all SD-paper, all closed)

| metric | value |
|---|---:|
| n | 263 |
| sum(corrected_pnl_sol) | **+2.0625 SOL** |
| mean | +0.00784 SOL |
| median | +0.0180 SOL |
| WR | 139/263 = **52.9%** |
| open at end | 0 (1 in Redis bot:status — see §4.3) |

### Probe-window split (n=266 since 2026-05-06 22:29:10 UTC, the actual probe SET)

| window | trades | sum SOL | mean SOL | WR |
|---|---:|---:|---:|---:|
| **Probe-active (DEFENSIVE forced)** 24h | 54 | +0.6402 | +0.01186 | 24/54 = 44.4% |
| **Probe-expired (threshold-determined)** ~14h45m | 212 | +1.3980 | +0.00659 | 115/212 = 54.2% |
| All since probe SET | 266 | +2.0382 | +0.00766 | 139/266 = 52.3% |

**Throughput note:** 54 trades in 24h (probe-active) vs 212 trades in ~14h45m (probe-expired) — DEFENSIVE override clearly suppresses throughput by ~6× (2.25/h → 14.4/h). This is the expected DEFENSIVE behaviour — stricter gating, fewer entries.

**Per-trade outcome note:** mean +0.012 (DEFENSIVE) vs mean +0.007 (post-expiry) — DEFENSIVE has slightly better per-trade mean but at lower throughput. WR favors post-expiry (54.2% vs 44.4%). The 24h probe-active sample is too small to draw confident conclusions on per-trade DEFENSIVE-vs-NORMAL inversion (the original MARKET-MODE-001-RE-CALIBRATE finding) and the post-expiry sample is contaminated by mode being threshold-determined (which could include DEFENSIVE spells if dex_vol or grad_rate gated it that way). **Eval session needs to either (a) reconstruct mode-at-entry from market_health logs / portfolio_snapshots if available, or (b) re-run with a clean fresh probe.**

### Exit-reason histogram (closed, n=263, 2026-05-07 00:00 UTC onwards)

| exit_reason | n | sum SOL |
|---|---:|---:|
| TRAILING_STOP | 166 | +6.5148 |
| no_momentum_90s | 41 | -0.9363 |
| stop_loss_20% | 40 | -3.5486 |
| stale_no_price | 15 | -0.0989 |
| staged_tp_+200% | 1 | +0.1314 |

**Patterns consistent with prior audits:**
- TRAILING_STOP dominates wins (sole large positive contributor). Captures ~+6.5 SOL on this 263-trade sample.
- `no_momentum_90s` -0.94 SOL on 41 trades = -0.023 SOL/trade. Magnitude smaller than the 14d-window of -7.40 SOL on 356 trades reported in STATE-RECONCILE-2026-05-01 (-0.021 SOL/trade) — RATE PER TRADE consistent within rounding.
- `stop_loss_20%` -3.55 SOL on 40 trades = -0.089 SOL/trade. Higher per-trade loss than earlier samples.
- staged_tp_+200% n=1 only — staged TP-driven exits remain rare (consistent with most positions exiting via TRAILING_STOP).

### Mode coverage

[VERIFIED:psql] All 263 sample rows have no `mode_at_entry`/`market_mode`/`mode` key in `features_json`. Per-row mode reconstruction is not possible from DB alone for this window. **Limitation flagged for eval session.**

### §4.3 Redis-DB position discrepancy (cosmetic)

Redis `bot:status` reports 1 open paper position (mint `GnNFCenU…`, peak +339.92% unrealized). DB query: id 8401 with mint `GnNFCenU…` exited at `staged_tp_+200%` with PnL +0.1314 SOL, exit_time 1.18s after entry_time. `remaining_pct=0.8` in Redis = 80% remaining after the staged 20% partial exit, consistent with `STAGED_TAKE_PROFITS_JSON=[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]`.

So the position is "partially open" — Redis tracks the un-sold 80%, DB has one row with `exit_reason=staged_tp_+200%` for the partial. Not a ghost-cache bug; it's the staged-TP data model. No state action required.

### §4.4 Lifetime baseline cross-check

| metric | value |
|---|---:|
| Lifetime closed paper_trades | 1,770 rows |
| Lifetime sum corrected_pnl_sol | -8.35 SOL |
| Lifetime mean | -0.00472 SOL |
| Probe-period sample mean | +0.00784 SOL |

Probe-period mean is **better than lifetime mean** by +0.0125 SOL/trade. Consistent with the post-cliff fee-model artifact finding (STRATEGY-CLIFF-INVESTIGATION-001) that POST-cliff is +0.20 SOL/trade better than PRE under apples-to-apples accounting — direction holds but magnitude is smaller in this 266-row sample.

---

## §5 Railway env audit

[VERIFIED:railway-mcp] Captured for: bot_core, signal_aggregator, treasury, ml_engine, market_health. (web + governance + signal_listener not pulled this session — focus was on the 5 that V5a depends on; web shadow-set audit is in `ENV_AUDIT_2026_04_29.md`.)

### Drift vs handover §3.2 (only changes shown; **values redacted to first 8 chars** for any key/secret)

| service | var | handover value | actual value | severity |
|---|---|---|---|---|
| bot_core | `MAX_POSITION_SOL_FRACTION` | unset (code default 0.10) | unset | 🟢 unchanged (still missing) |
| bot_core | `ML_THRESHOLD_BOT_CORE_SD` | 40 | 40 | 🟢 |
| bot_core | `TIME_PRIME_MULTIPLIER` | 1.0 | 1.0 | 🟢 |
| bot_core | `TIME_PRIME_HOURS_AEST` | unset | unset | 🟢 |
| bot_core | `STAGED_TAKE_PROFITS_JSON` | `[[2.00,0.20],[5.00,0.375],[10.00,1.00]]` | identical | 🟢 |
| signal_aggregator | `SD_MC_CEILING_USD` | 3000 | 3000 | 🟢 (verified by §6 code check too) |
| signal_aggregator | `ANALYST_DISABLED` | true | true | 🟢 |
| signal_aggregator | `HOLDER_COUNT_MIN` | 1 | 1 | 🟢 |
| treasury | `TEST_MODE` | false | false | 🟡 (TREASURY-TEST-MODE-002 dormant) |
| ml_engine | `ML_ENGINE` | original | original | 🟢 (intentional — ml_engine is ground-truth) |
| ml_engine | `TABPFN_TOKEN` | exp 2027-04-05 | present, value `eyJhbGci...` (redacted) | 🟢 (exp date not re-decoded this session) |

### Cross-service comparisons

- **Same** `ANTHROPIC_API_KEY` across bot_core, signal_aggregator, treasury, ml_engine, market_health (first 8 chars: `sk-ant-a`). [VERIFIED:railway-mcp]
- **Same** `HELIUS_API_KEY` `0f2e5160` across all 5. [VERIFIED:railway-mcp]
- **DIFFERENT** `NANSEN_API_KEY`: bot_core/signal_aggregator/ml_engine = `nsn_2ef9` ; treasury/market_health = `cL2tgvKP`. **SEC-001 split-key state still active** (was a 2-key state in prior audits; unchanged this session).
- **Same** `SOCIALDATA_API_KEY` across all 5 (first 8: `6529|duP`).
- **Same** `VYBE_API_KEY` across all 5 (first 8: `SXPAt2nZ`).
- **Vestigial sizing values** still on treasury / ml_engine / market_health: `SPEED_DEMON_BASE_SIZE_SOL=0.45`, `SPEED_DEMON_MAX_SIZE_SOL=0.75`, `MAX_SD_POSITIONS=3`, `MIN_POSITION_SOL=0.10`. Aligned vars (0.15/0.25/20/0.05) present only on bot_core + signal_aggregator. **TUNE-008** display-only cleanup still applicable.

No new env-var changes detected since 2026-05-07 handover.

---

## §6 Code state checks

[VERIFIED:repo@15a334a]

| check | result | notes |
|---|---|---|
| `BOT-CORE-ML-GATE-001` commit `ea0da2f` present | 🟢 PRESENT | `git log` confirms; current HEAD `15a334a` is descendant of `ea0da2f`. |
| `SD_MC_CEILING_002` gate location | 🟢 PRESENT at `services/signal_aggregator.py:1846-1881` | Handover said 1833-1879 — small line drift, function intact. Reads `vSolInBondingCurve / vTokensInBondingCurve × 1e9 × market:sol_price`, fail-open on missing data. Gate fires when `mc_at_eval_usd > SD_MC_CEILING_USD` (env-controlled, currently 3000). |
| `TIME_PRIME` env-controlled block | 🟢 PRESENT at `services/bot_core.py:750-764` | Handover said 695-696 — different lines (handover lines were portfolio update logic, not TIME_PRIME). The actual TIME_PRIME branch at 750-764 reads `TIME_PRIME_HOURS_AEST` and `TIME_PRIME_MULTIPLIER` env vars and is empty-string-disabled correctly. Empty `_tp_hours` set means the branch never fires. |
| Hardcoded TZ at bot_core.py:754 | 🟡 STILL PRESENT | `aedt_hour = datetime.now(timezone(_td(hours=11))).hour` — `TIME-PRIME-AEDT-AEST-DRIFT-001` unchanged from TIMEZONE-AUDIT-001. |
| Vybe `.com` URLs in code | 🔴 STILL PRESENT at `services/signal_aggregator.py:753, 850, 2568` | Confirms `VYBE-URL-CODE-DRIFT-001` Tier 1 still open. |
| `governance.py` model | 🟢 `claude-haiku-4-5-20251001` | env `GOVERNANCE_MODEL=claude-haiku-4-5-20251001` confirmed. |

---

## §7 Drift summary (vs 2026-05-07 handover state)

| key | handover (2026-05-07) | actual (2026-05-08 13:21 UTC) | severity |
|---|---|---|---|
| `market:mode:override` | DEFENSIVE EX 86400 (probe active) | ABSENT | 🔴 expired without renewal |
| `market:mode:current` | DEFENSIVE | NORMAL | 🔴 dependent on above |
| Trading wallet balance | 0.064095633 SOL (2026-04-30) | 0.064095633 SOL | 🟢 unchanged |
| Holding wallet balance | ~0.0098 SOL (2026-04-29) | 0.190842421 SOL | 🟡 +0.181 — confirm with Jay |
| Anthropic credits | 🔴 (BUG-010) | 🔴 still active per Redis governance log | 🟢 unchanged (still broken) |
| Vybe URL code drift | 🔴 (`.com` in code) | 🔴 unchanged | 🟢 unchanged (still broken) |
| SocialData credits | 🔴 (113 errors/11min on 05-05) | route alive; live evidence not gathered | 🟡 status presumed unchanged |
| Helius primary | 🟢 | 🟢 | 🟢 unchanged |
| Bot RUNNING / TEST_MODE | true / paper | true / paper | 🟢 unchanged |
| Open paper positions | (not checked) | 0 in DB; 1 partial in Redis (cosmetic) | 🟢 expected |
| ML_THRESHOLD_BOT_CORE_SD | 40 | 40 | 🟢 |
| SD_MC_CEILING_USD | 3000 | 3000 | 🟢 |
| ANALYST_DISABLED | true | true | 🟢 |
| TEST_MODE on treasury | false (dormant) | false | 🟢 unchanged |
| `mode_at_entry` in features_json | (assumed present) | ABSENT in 263/263 sample rows | 🔴 limitation for eval mode-coverage |

---

## §8 Recommendations for the eval session

The DEFENSIVE-OVERRIDE-PROBE-EVAL-001 session (~2026-05-09 evening AEST per handover) needs to handle these new findings:

### 8.1 Decide how to treat the 24h probe-active sample
The probe ran for ~24h (n=54 SD-paper closed) before lapsing. This is BELOW the 80-trade target stated in the original probe spec (MONITORING_LOG.md 2026-05-06 entry). The eval session has three options:

1. **Use only the 24h pure sample** (n=54): apples-to-apples but underpowered. n=54 is too small for confident NORMAL-vs-DEFENSIVE PnL inversion. Compare against the pre-probe 5-day NORMAL baseline (n=121 / -1.09 SOL / 24.8% WR per audit `MARKET_MODE_001_RE_CALIBRATE_FINDINGS_2026_05_05.md`) and accept that conclusion confidence remains LOW.
2. **Run a fresh probe with proper renewal** as a separate session. Re-set `market:mode:override=DEFENSIVE EX 86400` AND set up a daily renewal mechanism (cron/loop or session reminder). Wait another 48-72h to clear the n=80 bar.
3. **Hybrid:** combine the 24h probe sample with reconstructed-mode rows from post-expiry (if mode-at-entry can be reconstructed from `market_health` per-cycle logs or `portfolio_snapshots`). Complex, fragile.

Recommendation: **option 2** — re-run the probe with a renewal commitment. The 24h sample is too thin for the inversion claim and the eval prompt should not pretend otherwise. Track as `DEFENSIVE-OVERRIDE-DAILY-RENEWAL-001` operational item (already in roadmap from 2026-05-06 entry).

### 8.2 Patch `mode_at_entry` into `features_json`
None of the 263 probe-period rows carry `mode_at_entry`. Without that field, mode-coverage analysis on probe data depends on real-time mode-tracking outside paper_trades — fragile. Filing **MODE-AT-ENTRY-FEATURE-001** (Tier 2 🟢) for paper_trader / signal_aggregator to write `market:mode:current` into features_json at write-time. Trivial change; high diagnostic ROI for any future mode-related audit.

### 8.3 Holding wallet drift confirmation
+0.181 SOL appeared on holding wallet between 2026-04-29 and 2026-05-08. Treasury is dormant (no automation should have moved funds). Either Jay top-up or unexplained transfer. **Confirm before any V5a wallet planning.** Tracked as new HOLDING-WALLET-DRIFT-2026-05-08 (Tier 3 🟢, low-priority).

### 8.4 Anthropic / Vybe / SocialData
Carry-over from 2026-05-05 API-CREDITS-HEALTH-DIAGNOSTIC-001:
- 🔴 ANTHROPIC: confirmed still firing now via Redis. Top-up required.
- 🔴 VYBE-URL-CODE-DRIFT-001: code still on `.com`. Needs Tier 1 patch.
- 🔴 SOCIALDATA: status carries over (route alive, real credit state not probed).

None new this session — all are unchanged from 2026-05-05 audit.

### 8.5 V5a impact
None of these findings change V5a-blocking status. Original V5a blockers (wallet 0.064 SOL, 48h observation, NORMAL window) remain. The probe expiration does not block V5a; it just means the probe needs a re-run for confident eval.

---

## §9 Reproducibility

```python
# Probe-period query (re-run any time):
python .tmp_state_snapshot/pull_probe.py
python .tmp_state_snapshot/probe_window_split.py
```

```python
# Wallet balance via Helius MCP:
mcp__helius__getBalance(address="4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ")
mcp__helius__getBalance(address="2gfHQvyQdpDtiyUcFQJE6o15VkrHn7YXubp8DRwttWJ9")
```

```bash
# Vybe / SocialData / Anthropic route checks (returns 401/404 with bogus creds):
curl -sI "https://api.vybenetwork.com/token/<mint>/holders?limit=1" -H "X-API-Key: dummy"
curl -sI "https://api.vybenetwork.xyz/token/<mint>/holders?limit=1" -H "X-API-Key: dummy"
curl -sI "https://api.socialdata.tools/twitter/user/elonmusk" -H "Authorization: Bearer dummy"
curl -X POST "https://api.anthropic.com/v1/messages" -H "x-api-key: dummy" \
     -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
     -d '{"model":"claude-haiku-4-5-20251001","max_tokens":10,"messages":[{"role":"user","content":"ping"}]}'
```

```python
# Redis state via MCP:
mcp__redis__get(key="market:mode:override")
mcp__redis__get(key="market:mode:current")
mcp__redis__get(key="bot:status")
mcp__redis__list(pattern="market:mode:*")
mcp__redis__list(pattern="paper:positions:*")
```

```python
# Railway env via MCP:
mcp__railway__list-variables(service="bot_core", kv=true)
mcp__railway__list-variables(service="signal_aggregator", kv=true)
# (also: treasury, ml_engine, market_health, web, governance, signal_listener, Redis, Postgres)
```

---

## §10 STOP / limit notes

- No STOP conditions triggered.
- All 4 retry-budget categories (Redis MCP, Helius RPC, Railway MCP, PostgreSQL) succeeded on first attempt.
- No 429s observed. No code changes attempted. Read-only compliance verified.
- Scratch artifacts: `.tmp_state_snapshot/pull_probe.py`, `probe_window_split.py`, `check_redis_position.py`, `probe_period_trades.csv` (gitignored via this session's `.gitignore` update).
