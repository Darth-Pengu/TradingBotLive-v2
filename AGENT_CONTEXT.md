# AGENT_CONTEXT — current bot state

**Last updated:** 2026-04-30 ~12:30 UTC by SD-MC-CEILING-002-DEPLOY (post Session E chain).
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
| ML_THRESHOLD_SPEED_DEMON | 40 | drifts vs SA=65 vs web=45 — see ML-THRESHOLD-DRIFT-2026-04-29 🟡 |
| ML_THRESHOLD_ANALYST | 35 | drifts |
| ML_THRESHOLD_WHALE_TRACKER | 35 | drifts |
| STAGED_TAKE_PROFITS_JSON | `[[2.00,0.20],[5.00,0.375],[10.00,1.00]]` | |
| TIERED_TRAIL_SCHEDULE_JSON | `[[0.10,0.30],[0.50,0.25],[1.00,0.20],[2.00,0.15],[5.00,0.12]]` | |
| STOP_LOSS_PCT | 0.20 | |
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
| Trading | `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` | **0.064095633 SOL** | 2026-04-30 ~09:00 UTC via Helius `getBalance` |
| Holding | `2gfHQvyQdpDtiyUcFQJE6o15VkrHn7YXubp8DRwttWJ9` | ~0.0098 SOL | 2026-04-29 12:39 UTC via ENV_AUDIT |

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

- [ ] **~3 SOL transfer to trading wallet** (Jay action). Top-up to ≥1.5-2.5 SOL minimum so MIN_POSITION_SOL × MAX_POSITION_SOL_FRACTION = effective 0.05+ SOL.
- [ ] **24-48h paper observation** with current config (Sessions A-D landed). 24h window opens at last meaningful change (LIVE-FEE-CAPTURE Path A landed 2026-04-30 ~08:50 UTC).
- [ ] **Confirm SD_EARLY_CHECK relax verdict** holds in observation (Session A TUNE-009 deferred; re-evaluate if conditions in audit §10 emerge).
- [x] **Resolve SD_MC_CEILING_002** ✅ DEPLOYED 2026-04-30 ~12:30 UTC via Option 2 (BC-reserves MC compute in SA gate). Verification (Step 6 immediate + 24h ~2026-05-01) queued. See `docs/audits/SD_MC_CEILING_002_DEPLOY_2026_04_30.md`.
- [ ] **Land LIVE-FEE-CAPTURE-002 (Path B)** — Helius parseTransactions for actual fill data. Path A undercorrects by ~12× on the only live data point (id 6580). V5a-blocking-but-degradable.
- [ ] **Renew Redis daily TTLs** before V5a flip: `market:mode:override=NORMAL EX 86400`, `nansen:disabled=true EX 86400`. Both expired at session-E snapshot time.
- [ ] **V5a flip:** `TEST_MODE=false` on bot_core per CLAUDE.md "Live trading mode — session-gated" rule (§Operating Principles).

---

## §7 Known unresolved (Tier-1 carry)

| ID | status | notes |
|---|---|---|
| ML-THRESHOLD-DRIFT-2026-04-29 | 🟡 | SA=65 / bot_core=40 / web=45; effective gate < 40 due to AGGRESSIVE_PAPER bypass. 44 of last 100 closes have ml_score ∈ (0,40]. |
| TREASURY-TEST-MODE-002 | 🟡 | treasury alone has TEST_MODE=false. Dormant but latent. |
| LIVE-FEE-CAPTURE-002 (Path B) | 📋 | V5a-blocking-but-degradable. Helius parseTransactions for actual fill data. |
| LIVE-CLOSE-FALLBACK-INSERT-001 | 📋 | bot_core.py:1318 legacy 21-column INSERT not extended with new columns. Low-traffic path. |
| TUNE-009 (SD_EARLY_CHECK relax) | ⏸ DEFERRED | empirical data does not support relax — see audit §6 conditions for re-evaluation. |
| SD_MC_CEILING_001 | ⚠️ SUPERSEDED | _002 replaces inert gate. Keep marker for git-history reference. |
| SD_MC_CEILING_002 | ✅ DEPLOYED 2026-04-30 ~12:30 UTC | BC-reserves MC compute in SA gate. Step 6 + 24h verification queued. |
| TIME_PRIME-CONTRADICTION-001 | 📋 | bot_core upsizes 2× at AEDT 18-20, contradicting SD_DEAD_ZONE_001 finding. |
| TUNE-006 (other components) | 📋 | SD_DEAD_ZONE_001, SD_ML_THRESHOLD_LIFT 40→50 — deferred from chain A-D. |
| TUNE-005-ROLLBACK validation | 📋 | 24h window closes ~2026-04-30 09:34 UTC. Decide codify-rollback vs reapply. |
| SILENCE-RECOVERY (post-2026-04-25 EMERGENCY_STOP) | ✅ CLEARED | bot recovered between 2026-04-28 13:02 UTC (first close) and 2026-04-30 (current). |

For the full Tier-1/2/3 list see `ZMN_ROADMAP.md`.

---

## §8 Recent Redis state snapshot (2026-04-30 ~08:52 UTC)

| key | value | TTL |
|---|---|---:|
| bot:status | RUNNING, portfolio 23.97 SOL, daily_pnl=0.0, test_mode=true | 27s |
| bot:emergency_stop | (none) | -2 |
| bot:loss_pause_until | (none) | -2 |
| bot:consecutive_losses | 1 | -1 |
| market:mode:current | **HIBERNATE** | -1 |
| market:mode:override | (none — TTL expired) | -2 |
| market:sol_price | (none — TTL expired) | -2 |
| governance:latest_decision | CONSERVATIVE; all personalities `enabled=true` (Redis override clobbered as expected — env-vars load-bearing) | 28518s |
| nansen:disabled | (none — TTL expired) | -2 |
| signal_aggregator:health | ok at 08:52:34 UTC | 99s |
| **bot_core:health** | **(absent — OBS-014)** | -2 |

**Action items from snapshot:**
- Renew `market:mode:override=NORMAL EX 86400` daily (currently expired; AGGRESSIVE_PAPER_TRADING masks effect for paper but blocks live entries).
- Renew `nansen:disabled=true EX 86400` daily (currently expired; combined with NANSEN_DAILY_BUDGET=2000 on SA/ml_engine/signal_listener, Nansen calls may fire).
- bot_core lacks heartbeat key — OBS-014 cleanup.

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
Vybe    ONLINE    VYBE_API_KEY    Holder labels (CEX/KOL/MM), wallet PnL. Base URL: api.vybenetwork.com
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
- Base: https://api.vybenetwork.com (NOT .xyz)
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
