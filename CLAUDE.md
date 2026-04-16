# ZMN Bot — Claude Code Instructions

## Resolved Bugs (reference only — see MONITORING_LOG.md for details)
Key fixes: exit pricing pipeline (26e19b4), paper_trader price pass-through (9b880e1), HIBERNATE bypass (47de1fa), SERVICE_NAME routing (April 3). Do NOT revert main.py to asyncio.gather all services.

## Trade P/L Analysis Rule (added 2026-04-13)

When analyzing trade performance from paper_trades, ALWAYS use the
`corrected_pnl_sol` and `corrected_pnl_pct` columns, NOT `realised_pnl_sol`
or `realised_pnl_pct`. The latter are historically buggy for trades
with staged take-profits (44 trades affected, all with id <= 3564).

For ML retraining: use corrected_pnl_sol to determine win/loss labels.
For reporting: use corrected_pnl_sol for aggregate numbers.
For forensic trade inspection: compare both columns to understand
what the bug was hiding.

Post-fix trades (id > 3564) have identical values in both columns --
correction_method = 'pass_through' confirms this.

---

## Project
Solana memecoin trading bot. GitHub: Darth-Pengu/TradingBotLive-v2
Domain: zmnbot.com. Railway: 8 services. PostgreSQL + Redis.
Currently TEST_MODE=true (paper trading). Balance: 31.86 SOL.

## Services (each is a SEPARATE Railway service)
- signal_listener → services/signal_listener.py (PumpPortal WS, trade subscriptions, telegram)
- signal_aggregator → services/signal_aggregator.py (scoring, KOTH, enrichment, momentum gates)
- bot_core → services/bot_core.py (position management, exits, governance reading)
- ml_engine → services/ml_engine.py (CatBoost + LightGBM ensemble, Phase 3)
- market_health → services/market_health.py (CFGI, SOL price, market mode)
- governance → services/governance.py (JSON classification via Haiku, needs Anthropic credits)
- treasury → services/treasury.py (balance tracking)
- web → services/dashboard_api.py + dashboard/*.html (14-panel retro green dashboard)

## Current State (April 16, 2026)

### Financial state
- ~4,945 paper trades total
- Paper balance: ~50.95 SOL
- Trading wallet: 5.00 SOL real SOL on mainnet (for trial trading)

### Live trading preparation
- Shadow analysis: 90.9% winner survival rate, STRONG edge assessment
- Execution audit: ALL infrastructure exists, 0 code gaps
- 1 minor config gap: position floor hard-coded at 0.15 SOL, need 0.05
- IMPORTANT: TEST_MODE is still true. Do NOT change without explicit
  Jay approval in a dedicated live-trading session.

### Pipeline state (as of 2026-04-15)
- signal_listener: ALIVE
- signal_aggregator: ALIVE, hardened (Redis retry + health heartbeat),
  **ANALYST_DISABLED=true** env var set
- bot_core: ALIVE, trading Speed Demon only, **TP redesign experiment
  LIVE** (Option B2, observation ends 2026-04-17 ~11:32 UTC),
  **shadow measurement logging active** (SHADOW_MEASURE events to
  Redis shadow:measurements). DO NOT modify exit strategy.
- market_health: ALIVE, **Stage 2 CFGI cutover deployed** (cfgi.io SOL
  primary, credits topped up, SOL CFGI = 41.5 active).
- governance: ALIVE but **Anthropic credits exhausted** — LLM non-functional

### ML state
- CatBoost + XGBoost ensemble, 128 clean training samples
- LightGBM not loading (ensemble runs 2/3 models)
- WARNING: ML score inversion at 70+ bucket. See POST_TIER2_DIAGNOSIS.md.
- 685 pre-fix trades excluded from ML training via contamination filter

### CFGI state
- Primary source: **cfgi.io Solana** — NOW ACTIVE (credits topped up)
- market:health.cfgi = 41.5 (cfgi.io SOL, primary)
- market:health.cfgi_btc = 23.0 (Alternative.me BTC, preserved)
- Stage 2 cutover code deployed (commit eebccf5)

### Personality state
- Speed Demon: sole active personality, 38.6% WR post-recovery
- Analyst: **HARD DISABLED** via ANALYST_DISABLED=true env var.
  0/3 WR with 0-2s holds pending investigation.
- Whale Tracker: dormant

### External API readiness (2026-04-16)
- Execution APIs: ALL working EXCEPT **Helius Staked RPC (522)**
- Helius standard RPC: OK (285ms), fallback viable for live
- Jupiter V2: OK (365ms), Jito: OK (629ms), PumpPortal: OK
- **Anthropic: CREDITS EXHAUSTED** — governance non-functional
- **SocialData: CREDITS EXHAUSTED** — social enrichment dead
- Go/No-Go: **READY WITH ONE FIX** (Helius Staked URL)

### Known blockers
- **Helius Staked URL returning 522** — needs new URL from Helius
  dashboard or accept standard RPC fallback for tx submission
- TP redesign experiment active (ends 2026-04-17 ~11:32 UTC)
- B-013: DEFERRED — symbol column empty, needs paper_trader fix
- ML retrain blocked on 500+ clean samples
- Anthropic credits exhausted (governance dead)

## Known Issues (Priority Order, April 11)
1. ML SCORE INVERSION: 70+ scores have 0% WR, -12.62% avg P/L. Model trained on 128 samples (6 positives) memorized spurious patterns (hour_of_day, sol_price). See POST_TIER2_DIAGNOSIS.md.
2. FEATURE SPARSITY: 42 of 55 FEATURE_COLUMNS are permanently zero. Only ~13 features populated per prediction. Model trained to ignore dead features = noise. Consider pruning to ~20 populated features.
3. no_momentum_90s BLEED: 51% of trades (88/171) exit via no_momentum_90s at -11.98% avg. Signal quality bottleneck.
4. LightGBM NOT LOADING: NIXPACKS_APT_PKGS=libgomp1 is set but ml_engine needs fresh deploy to pick it up. Ensemble runs 2/3 models.
5. Governance SQL type mismatch: `double precision > timestamp` in metrics query (cosmetic, governance still works).
6. Analyst paused in extreme fear: CFGI < 20 auto-pauses analyst. Zero training data during fear markets.
7. Treasury Helius errors: getBalance fails every 5min (HELIUS_DAILY_BUDGET=0 but treasury still calls).
8. Telegram: code ready but TELEGRAM_ENABLED=false

## Operating Principles for Claude Code Sessions

These were learned through several sessions in April 2026. Follow by
default unless Jay explicitly overrides.

- **One lever per session.** Each session changes ONE thing. Multiple
  parallel changes make failure attribution impossible.
- **Gated phases.** Multi-phase sessions have explicit pass/fail
  conditions between phases. If Phase N fails, later phases skip.
- **Always update all four canonical docs.** Every session that changes
  state must update MONITORING_LOG.md, ZMN_ROADMAP.md, CLAUDE.md, and
  AGENT_CONTEXT.md.
- **Auto-revert on failure.** `git revert <hash>` only. Never
  force-push, never rebase, never delete commits.
- **No agent loops on live services.** Single-pass, bounded,
  reversible deployments only.
- **Speed Demon trading logic is sacred.** Do not modify entry filter,
  ML scoring, position sizing, or exit strategy unless the session is
  specifically scoped to that change AND backed by data analysis.
- **Read-only diagnostic before write prompts.** When state is
  ambiguous, run a read-only audit BEFORE modifying anything.
- **Verify before shipping.** Don't ship optimization based on
  simulation alone. Always have actual instrumentation data.
- **Bounded scope, hard stops.** Every prompt has a max wall clock.
  When reached, commit whatever's done and stop. No "while we're here."
- **Paper mode is non-negotiable.** TEST_MODE=true stays true.
- **Trust the data.** Speed Demon +22 SOL in 36h = real edge.
  Analyst 0/3 in 0-2s = real problem.

## Read this first, every session
- Read AGENT_CONTEXT.md completely before writing any code
- Check what exists in services/ before building anything new
- Never assume a file exists — always check first
- Auto-accept all tool use and terminal commands
- If you hit rate limits or token limits: pause, wait until reset plus 5 minutes, then resume from exactly where you left off. Do not start over. Do not ask whether to continue.

## API reference rule
- Before fixing any API integration, check Section 21 of AGENT_CONTEXT.md

## Non-negotiable rules
- All Python is async/await — no sync blocking calls
- Never hardcode API keys, private keys, or wallet addresses
- TEST_MODE=true means paper trades only
- MAX_WALLET_EXPOSURE is 0.25 (25%)
- Run python -m py_compile services/<file>.py before committing

## Data persistence rules — NEVER VIOLATE

PostgreSQL is the ONLY permanent storage. Redis is a CACHE.
Railway Redis CAN be wiped on restart. PostgreSQL survives everything.

RULE: If data needs to survive a service restart, it goes in PostgreSQL FIRST.
Redis is only a fast-access cache that gets reloaded from PostgreSQL on startup.

| Data Type | PostgreSQL (permanent) | Redis (cache) |
|---|---|---|
| Trade records | paper_trades / trades table | paper:positions:{mint} (temporary) |
| Portfolio balance | portfolio_snapshots table | bot:portfolio:balance |
| ML model metadata | bot_state key='ml_model_meta' | ml:model:meta (hash) |
| Winner analysis | bot_state key='winner_analysis' | ml:winner_analysis |
| Whale wallets | watched_wallets table | whale:watched_wallets (set) |
| Whale patterns | bot_state key='whale_patterns' | whale:pattern_analysis |
| Governance decisions | bot_state key='governance_latest' | governance:latest_decision |
| Signal evaluations | Logged to signals table if needed | signals:evaluated (list, last 50) |
| Consecutive losses | bot_state key='consecutive_losses' | bot:consecutive_losses |
| Emergency stop | bot_state key='emergency_stop' | bot:emergency_stop |

PATTERN — every time you store analytical/state data:
```python
# 1. PostgreSQL FIRST (permanent)
await pool.execute(
    "INSERT INTO bot_state (key, value_text, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (key) DO UPDATE SET value_text=$2, updated_at=NOW()",
    key_name, json.dumps(data)
)
# 2. Redis SECOND (cache for fast reads)
await redis.set(f"cache:{key_name}", json.dumps(data), ex=86400)
```

PATTERN — every time you read analytical/state data:
```python
# 1. Try Redis first (fast)
cached = await redis.get(f"cache:{key_name}")
if cached:
    return json.loads(cached)
# 2. Fall back to PostgreSQL (permanent)
row = await pool.fetchval("SELECT value_text FROM bot_state WHERE key=$1", key_name)
if row:
    # Repopulate Redis cache
    await redis.set(f"cache:{key_name}", row, ex=86400)
    return json.loads(row)
return None
```

NEVER store important data in Redis only. NEVER assume Redis survives restarts.
Token prices and trade stats are OK in Redis-only (they're ephemeral by nature).
Everything else: PostgreSQL first, Redis cache second.

## Architecture
- All services in services/ — no monolithic files
- Services communicate only via Redis
- Never import one service directly into another
- Each Railway service runs only its own code via SERVICE_NAME env var

## After every task
- Compile check, commit, push, report

## MCP Servers Available

### Nansen MCP
URL: https://mcp.nansen.ai/ra/mcp/
Auth: NANSEN-API-KEY header (env var: NANSEN_API_KEY)
BUDGET: 508% over limit. DISABLED via Redis nansen:disabled.
When re-enabled: max 50 calls/day. Cache aggressively.
Key endpoints: POST /api/v1/smart-money/dex-trades,
POST /api/v1/smart-money/top-tokens, POST /profiler/address/labels

### Vybe Network MCP
URL: https://docs.vybenetwork.com/mcp
Auth: X-API-KEY header (env var: VYBE_API_KEY)
API base: https://api.vybenetwork.com (NOT .xyz)
Free plan: 25K credits/month, 60 RPM.
Key endpoints: GET /tokens/{mint}/holders (labeled),
GET /v4/wallets/{addr}/pnl, GET /wallets/{addr}/token-balance

### Railway MCP
Available via: npx @railway/mcp-server
Use for: deploys, logs, env vars, service health.

### Redis MCP
Available via: npx @gongrzhe/server-redis-mcp
Use for: key inspection, queue depths, state fixes.

### CoinGecko MCP
Available via: npx mcp-remote https://mcp.api.coingecko.com/mcp

### Playwright MCP
Available via: npx @playwright/mcp@latest
Use for: testing dashboard at zmnbot.com.

### Gmail MCP
URL: https://gmail.mcp.claude.com/mcp

### Google Calendar MCP
URL: https://gcal.mcp.claude.com/mcp

## MCP Usage Rules
- MCPs are for data and analysis only — never trade execution
- execution.py handles all real trades
- TRADING_WALLET_PRIVATE_KEY must never be accessible to any MCP

## Jupiter API Reference
Price: GET https://api.jup.ag/price/v3?ids=<mint> (REQUIRES x-api-key header)
Swap: GET https://api.jup.ag/swap/v2/order + POST /v2/execute
Deprecated: /swap/v1/* returns 401

## Price Pipeline (critical)
- Entry prices: USD (from Jupiter/GeckoTerminal/bonding curve × SOL price)
- PumpPortal trade prices: SOL (sol_amount / token_amount)
- Redis token:latest_price:{mint}: SOL denomination
- Exit checker MUST convert SOL→USD via market:sol_price before comparing to entry
- Bonding curve: price_sol = vSolInBondingCurve / vTokensInBondingCurve
- Price fetch order should be: Redis → bonding curve reserves → Jupiter → Gecko

## Railway CLI Reference
- Logs (streams, needs timeout): `timeout 15 railway logs -s {service} 2>&1 | tail -100`
- Set env var: `railway variables --set "KEY=VALUE" -s {service}`
- Read env vars: `railway variables -s {service}` or `--kv` for parseable format
- Deploy: `railway up -s {service}` (build ~60s, container start ~60-90s after)
- Build logs: `railway logs -s {service} -b`
- Setting env vars triggers auto-redeploy

## Deploy Rules
- Each service deploys separately: railway up -s {service_name}
- Deploy takes 5-15 min. Poll Railway MCP until SUCCESS, wait 90s after.
- NEVER deploy multiple services simultaneously
- Batch ALL changes per service into ONE commit

## Cost Control
- GOVERNANCE_MODEL=claude-haiku-4-5-20251001 (NOT Sonnet)
- Helius: HELIUS_DAILY_BUDGET=0 (disabled — NOT used for pricing)
- Nansen: disabled via Redis (renew daily: SET nansen:disabled true EX 86400)
- Vybe: cache responses in Redis with 5-min TTL

## Key Redis Keys
bot:portfolio:balance, bot:consecutive_losses, bot:emergency_stop
market:mode:override (renew daily), market:sol_price, market:health
governance:latest_decision, ml:model:meta
token:latest_price:{mint} (SOL, 1800s TTL), token:price:{mint} (legacy, 1800s TTL)
token:subscribed:{mint}, token:reserves:{mint} (vSol/vTokens)
token:stats:{mint} (buys/sells/bsr/unique_buyers)
whale:watched_wallets (set — RELOAD FROM DB ON STARTUP)
nansen:disabled, nansen:calls:{date}
signals:evaluated (last 50), signals:raw, signals:scored

## Database Access (local machine)
- Internal URL (Railway network only): DATABASE_URL on any service
- Public URL: `railway variables -s Postgres --kv | grep DATABASE_PUBLIC_URL`
- Public host: gondola.proxy.rlwy.net:29062
- paper_trades has no `created_at` column. Primary time columns: `entry_time` (epoch float), `exit_time` (epoch float). `traded_at` exists but is often NULL.
- Use `id` ordering for recent trades, or `entry_time` for time-based queries.

## Architectural Gotchas (updated April 11)
- Emergency stop from rug cascade is IN-MEMORY only (`self.emergency_stopped`). Restarting bot_core clears it. No Redis key needed.
- `market:mode:current == HIBERNATE` blocks ALL signals in signal_aggregator:1669 unless AGGRESSIVE_PAPER bypasses it.
- ML scoring goes through Redis pubsub to ml_engine service (original 55-feature engine). The inline AcceleratedMLEngine was removed in commit 629c740. signal_aggregator has a 3s timeout + circuit breaker (5 timeouts/60s → default score 50.0).
- signal_listener early-subscribes to PumpPortal trades on createEvent (5-min TTL, max 200 concurrent). This populates token:stats for ML feature derivation before scoring.
- Rug cascade detector is in market_health.py (not bot_core). Threshold configurable via RUG_CASCADE_THRESHOLD env var (default 5, paper mode uses 15).
- Exit strategy: tiered trailing stops + staged TPs at +50/100/200/400% (25% each). Configurable via STAGED_TAKE_PROFITS_JSON and TIERED_TRAIL_SCHEDULE_JSON env vars on bot_core. Staged TPs fire at 100% rate (verified 20/20).
- paper_sell requires `exit_price_override` from caller (bot_core). If missing, falls back to Redis then entry_price with warning log. Never re-fetches from Jupiter/Gecko.
- Position sizing multiplier stack: personality(0.7) × rugcheck(0.35-0.60) × confidence × base. MIN_POSITION_SOL=0.05 on bot_core.
- ML training excludes pre-9b880e1 contaminated rows via WHERE NOT clause. Cutoff configurable: ML_TRAINING_CONTAMINATION_CUTOFF env var (default 1775767260.0 = 2026-04-09 20:41 UTC).

## Emergency Stop Reset
1. Redis: SET bot:consecutive_losses 0
2. Redis: DEL bot:emergency_stop
3. Redis: DEL bot:loss_pause_until
4. Redis: SET market:mode:override NORMAL EX 86400
5. Restart bot_core
(Note: rug cascade emergency stop is in-memory only — restart alone clears it without Redis changes)

## Times
All times in Sydney AEDT. Jay is in Sydney, Australia.
