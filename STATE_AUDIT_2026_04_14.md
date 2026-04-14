# State Audit -- 2026-04-14

## Executive Summary

signal_aggregator crashed at 13:38:16 UTC on April 13 due to a transient Redis DNS resolution failure during deploy (`Error -3 connecting to redis.railway.internal:6379. Temporary failure in name resolution`). It exited cleanly and never restarted -- Railway marked it "Completed." This killed the entire scoring pipeline: signal_listener is alive and pumping 1.5M+ raw signals into Redis, but nothing is scoring them. bot_core is alive but starved of scored signals. The bot has not traded for ~21 hours. No shadow mode exists anywhere in committed code. The two unknown Railway services (`query-redis-keys`, `redis-query`) were one-shot diagnostic scripts created by a Railway agent, not part of the bot architecture.

## Phase 1: Git State

### Commits since 2026-04-12 18:00 AEDT

| Hash | Timestamp (AEDT) | Message | Key Files |
|------|-------------------|---------|-----------|
| a8a390b | Apr 12 22:53 | fix: feature defaults -1 not 0 | services/signal_aggregator.py |
| 5b608ca | Apr 12 23:42 | docs: feature default fix report | FEATURE_DEFAULT_FIX_REPORT.md, MONITORING_LOG.md, SNAPSHOT.md |
| 5b92226 | Apr 13 08:44 | fix: staged TP P/L sums across all exits | services/bot_core.py |
| 6e5047e | Apr 13 09:22 | docs: staged TP reporting bug findings | MONITORING_LOG.md, STAGED_TP_FIX_REPORT.md |
| cf16627 | Apr 13 22:33 | backfill: add corrected_pnl columns | migrations/001_add_corrected_pnl_columns.sql |
| 2f76a91 | Apr 13 22:33 | docs: staged TP backfill session | AGENT_CONTEXT.md, CLAUDE.md, MONITORING_LOG.md, etc. |
| dbbffd3 | Apr 13 23:36 | dashboard: corrected_pnl columns + filter | dashboard/dashboard.html, services/dashboard_api.py |
| 40dadb6 | Apr 13 23:36 | bot_core: staged TP instrumentation | services/bot_core.py |
| cac5202 | Apr 13 23:36 | docs: dashboard audit report | DASHBOARD_AUDIT.md, MONITORING_LOG.md, etc. |

### Shadow mode references in repo

**0 matches in committed code.** The only references are in `ZMN_ROADMAP_v3.md` (an uncommitted file) at lines 212-231, where shadow mode is listed as future item #9.6, explicitly marked BLOCKED on #9.5 (execution path audit). No prompt was written, no code exists.

### Files touched that weren't expected

**None.** All 9 commits match the two planned sessions:
- Backfill session: cf16627, 2f76a91 (schema + docs)
- Dashboard Tier 1: dbbffd3, 40dadb6, cac5202 (P/L source fix, TP instrumentation, docs)
- Prior commits: a8a390b (feature defaults fix), 5b92226 (staged TP P/L fix)

No commit touched execution.py, main.py, Railway config, or any shadow/live execution path.

## Phase 2: Railway Services State

### Known services

| Service | State | Last Log Activity | Notes |
|---------|-------|-------------------|-------|
| Postgres | Online | -- | Database, healthy |
| Redis | Online | -- | Cache, healthy |
| signal_listener | **Online** | 2026-04-14 11:00 UTC | Actively receiving PumpPortal signals |
| signal_aggregator | **Completed (CRASHED)** | 2026-04-13 13:38 UTC | Redis DNS failure on startup, exited |
| bot_core | Online | 2026-04-14 00:00 UTC | Running but idle -- no scored signals to process |
| ml_engine | Online | -- | Not checked (not in critical path for this audit) |
| market_health | **Online** | 2026-04-14 10:40 UTC | Every 5min, HIBERNATE mode, SOL price working |
| governance | Online | 2026-04-14 09:38 UTC | Every 4h, says NORMAL mode (contradicts HIBERNATE) |
| treasury | Online | -- | Not checked |
| web | Online | -- | Dashboard serving |

### Unknown services

#### `query-redis-keys`
- **State:** Completed (one-shot)
- **What it does:** A Bun/TypeScript script that connects to Redis and dumps specific keys (`market:mode:current`, `market:health:cfgi`, `market:health`)
- **Technology:** TypeScript (`index.tsx`), auto-generated `package.json` with `redis` dependency
- **When created:** ~2026-04-14 00:18 UTC (based on log timestamps)
- **Created by:** A Railway agent (visible in Jay's screenshot sidebar: "Staged service update -> redis-query -> Failed -> Let me try a completely different approach")
- **Resource consumption:** None -- completed, not running
- **Risk:** None -- it only reads Redis keys, doesn't write

#### `redis-query`
- **State:** Completed (one-shot)
- **What it does:** Same purpose as `query-redis-keys` -- dumps Redis key values
- **Technology:** Appears to be the first attempt before `query-redis-keys`
- **When created:** ~2026-04-14 00:18 UTC
- **Created by:** Same Railway agent session
- **Resource consumption:** None

#### `redis-api` (referenced in agent sidebar)
- **State:** Does not exist as a service (`Service 'redis-api' not found`)
- **Was likely attempted but either deleted or never successfully created

**Verdict:** These are harmless one-shot diagnostic scripts created by a Railway agent trying to inspect Redis state. They read keys, printed output, and exited. They did NOT modify any data, did NOT affect the trading pipeline, and are NOT part of the bot architecture. They can be safely deleted whenever convenient -- but this audit does not delete them.

### signal_aggregator deep-dive

**Root cause of crash:**
```
2026-04-13 13:38:16 [signal_aggregator] ERROR: Redis connection REQUIRED for aggregator: Error -3 connecting to redis.railway.internal:6379. Temporary failure in name resolution.
2026-04-13 13:38:16 [signal_aggregator] ERROR: Signal aggregator cannot run without Redis — exiting
```

signal_aggregator started at 13:38:13 UTC. Within 3 seconds, it tried to connect to Redis via the Railway internal DNS (`redis.railway.internal:6379`). DNS resolution failed -- this is a transient Railway networking issue that sometimes occurs during deploys when services start before the internal DNS is fully propagated. The aggregator has a hard requirement on Redis (no retry logic on startup) and exited cleanly.

Because Railway saw a clean exit (no crash, just process exit), it marked the service "Completed" instead of retrying. This is the expected Railway behavior for a process that exits with code 0.

**The fix is a restart.** signal_aggregator just needs to be redeployed or restarted. The Redis DNS issue was transient -- bot_core, market_health, and signal_listener all connected successfully within seconds of signal_aggregator's failure. A startup retry loop would prevent this in the future.

**Last successful deploy:** Commit a8a390b (feature defaults fix, Apr 12 22:53 AEDT). This was the last commit that touched signal_aggregator.py and would have triggered a Railway redeploy.

## Phase 3: Redis State

### Market state
| Key | Value | TTL |
|-----|-------|-----|
| market:mode:current | HIBERNATE | no TTL (persistent) |
| market:sol_price | 86.17 | ~69s (refreshed every 5min by market_health) |
| market:health.cfgi | 21.0 | ~5min TTL (from Alternative.me Bitcoin F&G) |
| market:health.mode | HIBERNATE | same blob |
| market:health.sol_price | 86.17 | same blob |
| market:health.timestamp | 2026-04-14T10:55:47 UTC | same blob |
| bot:emergency_stop | NULL (not set) | -- |
| bot:portfolio:balance | 31.8592 | no TTL |

**SOL price is now working** -- market_health fetching successfully from Binance/CoinGecko. The $0.00 issue from yesterday was transient.

### Signal pipeline queues
| Queue | Type | Length | Most Recent Entry |
|-------|------|--------|-------------------|
| signals:raw | list | 1,530,398 | 2026-04-14T10:59:39 UTC (seconds ago) |
| signals:scored | does not exist | 0 | -- |
| signals:evaluated | list | 50 | 2026-04-13T13:38:34 UTC (21h ago) |

**signals:raw is massive** (1.5M entries) because signal_listener has been pumping new_token events continuously for 21 hours with no consumer. signals:evaluated stopped at 13:38 UTC -- exactly when signal_aggregator crashed.

### Governance state
- Mode: NORMAL
- Reasoning: "CFGI at midpoint (50) with positive PnL (10.241 SOL) and 52% win rate supports NORMAL mode"
- TTL: ~24000s (~6.7h remaining)

**The "CFGI at neutral 50" text is from the governance LLM (Claude Haiku).** It does NOT read CFGI directly -- it gets a text summary of performance metrics and generates a mode recommendation. The LLM is consistently outputting "CFGI at 50" regardless of actual CFGI value. This is either (a) the prompt template feeds it a hardcoded/default CFGI value, or (b) the LLM is hallucinating a neutral value. See governance logs: both 05:37 and 09:38 runs say "CFGI at neutral/midpoint 50" while actual CFGI was 21.

### Unexpected keys
| Pattern | Matches |
|---------|---------|
| shadow:* | 0 |
| execution:* | 0 |
| real:* | 0 |
| live:* | 0 |

**Zero shadow-mode-related keys in Redis.**

### bot:status
```
status: RUNNING
portfolio_balance: 31.8592 SOL
daily_pnl: 0.0
open_positions: 0
market_mode: HIBERNATE
consecutive_losses: 1
test_mode: True
timestamp: 2026-04-14T10:59:43 UTC
```

bot_core is alive and updating its status every few seconds. Zero open positions. It's simply not receiving any scored signals because signal_aggregator is dead.

### service:health (dashboard API Health source)
| Service | Status |
|---------|--------|
| pumpportal | live (last signal 0s ago) |
| redis | ok |
| jupiter | ok (HTTP 200) |
| rugcheck | ok |
| vybe | ok |
| nansen | warn (HTTP 405) |
| anthropic | ok |
| binance | warn |
| helius_* | ok (cached) |

**Note:** This cache does NOT track whether signal_aggregator is running. There's no aggregator health check in the service:health system. This is a gap -- the most critical service in the pipeline has no health monitoring.

## Phase 4: Trading Pipeline Verification

### Is the bot trading?

**NO.** Zero trades in the last 12 hours. Zero trades in the last 1 hour.

The last trade was ID 3630, entered at 2026-04-13T13:37:07 UTC (about 21.5 hours ago). signal_aggregator crashed 1 minute later.

### 24h trade summary (the burst before the crash)

30 trades between 11:08-13:37 UTC on April 13:
- 15 wins, 15 losses
- +5.4432 SOL total P/L
- 15 trades hit staged TPs (all 4 stages in many cases)
- All Speed Demon personality
- Excellent performance: 50% WR, +0.18 SOL avg per trade

**This was a productive trading window.** The bot was performing well when the pipeline died.

### Service activity in last 12 hours

| Service | Active | Evidence |
|---------|--------|----------|
| signal_listener | YES | Logs show continuous signal receipt, latest at 11:00 UTC today |
| signal_aggregator | **NO -- DEAD** | Crashed at 13:38 UTC Apr 13, no logs since |
| market_health | YES | Logs every 5min, latest at 10:40 UTC today |
| bot_core | YES (idle) | Running, status updates every few sec, no trades because no scored signals |
| governance | YES | Ran at 05:37 and 09:38 UTC today |

### STAGED_TP_FIRE instrumentation

The TP instrumentation log line (commit 40dadb6) was committed but NOT deployed. bot_core is running the pre-instrumentation code from its last deploy. The instrumentation will appear in logs after the next bot_core deploy.

### Where is the pipeline broken?

```
signal_listener (ALIVE) --> signals:raw (1.5M entries, growing)
    |
    v
signal_aggregator (DEAD since 13:38 UTC Apr 13)
    |
    X (no scored signals produced)
    |
    v
bot_core (ALIVE but starved -- nothing to process)
```

**The single point of failure is signal_aggregator.** Fix is: restart it.

## Phase 5: Dashboard Cross-check

### What the dashboard shows

The dashboard is showing REAL data from Postgres, not cached/ghost data:
- **Recent trades:** The last 20 trades from paper_trades (IDs 3611-3630), all from Apr 13 11:08-13:37 UTC
- **Session stats:** Whatever falls in the 24h window. As trades age past 24h, session stats will show zero.
- **Positions:** 0 open (correct)
- **Status:** Online, balance 31.86 SOL, HIBERNATE mode

The dashboard is NOT showing phantom data. It's showing the real last trades before the pipeline died. As those trades age past the 24h window, the "Today's Session" panel will show zeros.

### corrected_pnl_sol is NULL on new trades

The 30 trades from the Apr 13 burst (IDs 3601-3630) all have `corrected_pnl_sol = NULL`. The backfill session only populated corrected columns for trades up to ID ~3605 (the pass-through covered clean trades at that time). Trades entered AFTER the backfill (3606-3630) don't have corrected values yet.

**Impact:** The dashboard now uses `COALESCE(corrected_pnl_sol, realised_pnl_sol)`. For these 30 trades, it falls back to `realised_pnl_sol`, which IS correct for post-fix trades (commit 5b92226 ensures cumulative P/L). So the display is correct, but the corrected column isn't populated for consistency.

**Fix needed:** Either (a) run another pass-through for trades > 3605, or (b) modify bot_core to write corrected_pnl_sol directly on new trades. Neither is urgent since COALESCE handles it.

## The Answer to "Is Shadow Trading Affecting Output?"

**No.** Shadow mode does not exist in the codebase. Zero matches in committed code. The only references are in an uncommitted roadmap file (ZMN_ROADMAP_v3.md) listing it as future item #9.6, explicitly BLOCKED on #9.5. No shadow-related Redis keys exist. No shadow-related services exist. No shadow-related code has been committed.

The "shadow trading" Jay was concerned about is not a real thing. The bot was trading normally (30 trades, good performance) until signal_aggregator crashed.

## The Answer to "Why Has bot_core Been Idle for 11+ Hours?"

**signal_aggregator crashed at 13:38:16 UTC on April 13** due to a transient Railway internal DNS resolution failure (`Error -3 connecting to redis.railway.internal:6379`). It exited cleanly and Railway marked it "Completed" (not restarted).

With signal_aggregator dead:
- Signals pile up in `signals:raw` (now 1.5M entries) but never get scored
- bot_core receives no scored signals on its Redis pubsub subscription
- bot_core sits idle, updating its status but never entering trades

All other services are healthy. The fix is a single service restart.

## The Answer to "What Were Those Unknown Railway Services?"

`query-redis-keys` and `redis-query` are one-shot diagnostic scripts created by a Railway AI agent. They connect to Redis, dump specific key values, print the output, and exit. They were created around 00:18 UTC on April 14 (visible in the Railway sidebar as "Staged service update -> redis-query -> Failed -> Let me try a completely different approach"). They:
- Read Redis keys only (no writes)
- Are "Completed" (not running, not consuming resources)
- Are NOT part of the bot architecture
- Can be safely deleted whenever convenient

## Recommended Next Session

**Restart signal_aggregator.** This is a 2-minute operation, not a full session. After restart, the trading pipeline will resume immediately. Then:

1. **Deploy bot_core + dashboard_api** (commits dbbffd3, 40dadb6) -- these have the TP instrumentation and dashboard P/L fixes from last night that haven't been deployed yet
2. **Add startup retry logic to signal_aggregator** -- the Redis connection should retry 3-5 times with backoff instead of hard-exiting on first DNS failure
3. **Drain or trim signals:raw** -- 1.5M entries is excessive. Consider LTRIM to keep last 1000.
4. **Run corrected_pnl pass-through** for trades 3606-3630 (10-second SQL UPDATE)

## Things Left Alone

This audit made ZERO changes:
- No service restarts
- No service deletions (query-redis-keys and redis-query left as-is)
- No Redis writes
- No code changes
- No deployments
- No database modifications
- No Railway configuration changes
- Read-only investigation only
