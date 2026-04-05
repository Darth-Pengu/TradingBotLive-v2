# ZMN Bot — Claude Code Instructions

## CRITICAL BUG — EXIT PRICING (April 5, 2026)

### Exit Checker Cannot See Prices During Hold Period
100% of exits are "stale_no_price" or "time_exit_no_movement".
ZERO take-profits, ZERO stop-losses, ZERO trailing stops have EVER fired in 1,800+ trades.
Root cause: `_get_token_prices_batch()` tries Jupiter (10s timeout) then GeckoTerminal (8s timeout)
BEFORE checking Redis cached prices. These ALWAYS fail for bonding curve tokens.
By the time it reaches Redis, 18+ seconds wasted. With 5 positions, cycle takes 90+ seconds.

**FIX: Check Redis cached prices FIRST (instant), then Jupiter/Gecko only for uncached mints.**
Also: store bonding curve reserves (vSol/vTokens) from PumpPortal events in Redis for fallback pricing.

### Architecture: SERVICE_NAME Routing (FIXED April 3)
Each Railway service runs ONLY its assigned service via SERVICE_NAME env var.
The 8x duplicate bug is fixed. Do NOT revert main.py to asyncio.gather all services.

---

## Project
Solana memecoin trading bot. GitHub: airy-truth/TradingBotLive-v2
Domain: zmnbot.com. Railway: 8 services. PostgreSQL + Redis.
Currently TEST_MODE=true (paper trading). Balance: ~16.42 SOL.

## Services (each is a SEPARATE Railway service)
- signal_listener → services/signal_listener.py (PumpPortal WS, trade subscriptions, telegram)
- signal_aggregator → services/signal_aggregator.py (scoring, KOTH, enrichment, momentum gates)
- bot_core → services/bot_core.py (position management, exits, governance reading)
- ml_engine → services/ml_engine.py (CatBoost + LightGBM ensemble, Phase 3)
- market_health → services/market_health.py (CFGI, SOL price, market mode)
- governance → services/governance.py (JSON classification via Haiku, needs Anthropic credits)
- treasury → services/treasury.py (balance tracking)
- web → services/dashboard_api.py + dashboard/*.html (14-panel retro green dashboard)

## Current State (April 5, 2026)
- 1,800+ paper trades, ~59 wins (~3.2% WR overall)
- WR last 10: 20% | WR last 25: 12.8% | WR last 50: 10% (IMPROVING)
- Total PnL: -20.40 SOL | Last 2 sessions: NET POSITIVE (+1.06, +1.78 SOL)
- Best single trade: +1.33 SOL (+1672.9%) — Speed Demon
- ML AUC: 0.889 on 1,729 samples | Features: 20/58 populated
- CFGI: 12 (extreme fear) — market not conducive to memecoins
- Dashboard: 14/14 panels showing data (some need data fixes)
- Speed Demon: 511 trades, 19 wins, -9.25 SOL
- Analyst: 1,206 trades, 35 wins, -11.05 SOL
- Whale Tracker: 2 trades, 0 wins (44 wallets in DB, 0 in Redis — broken)

## Known Issues (Priority Order)
1. EXIT PRICING: Redis checked LAST instead of FIRST — 18s wasted per token
2. Whale wallet Redis cache: 44 in PostgreSQL, 0 loaded to Redis
3. ML metadata not in Redis — dashboard shows AUC/Features as "--"
4. Anthropic credits exhausted — governance dead
5. TABPFN_TOKEN not set on ml_engine
6. Telegram code ready but TELEGRAM_ENABLED=false
7. 38/58 ML features still zero
8. Dashboard: open positions empty, trades missing market cap

## Read this first, every session
- Read AGENT_CONTEXT.md completely before writing any code
- Check what exists in services/ before building anything new
- Never assume a file exists — always check first
- Auto-accept all tool use and terminal commands

## API reference rule
- Before fixing any API integration, check Section 21 of AGENT_CONTEXT.md

## Non-negotiable rules
- All Python is async/await — no sync blocking calls
- Never hardcode API keys, private keys, or wallet addresses
- TEST_MODE=true means paper trades only
- MAX_WALLET_EXPOSURE is 0.25 (25%)
- Run python -m py_compile services/<file>.py before committing

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
token:latest_price:{mint} (SOL, 300s TTL), token:price:{mint} (legacy)
token:subscribed:{mint}, token:reserves:{mint} (vSol/vTokens)
token:stats:{mint} (buys/sells/bsr/unique_buyers)
whale:watched_wallets (set — RELOAD FROM DB ON STARTUP)
nansen:disabled, nansen:calls:{date}
signals:evaluated (last 50), signals:raw, signals:scored

## Emergency Stop Reset
1. Redis: SET bot:consecutive_losses 0
2. Redis: DEL bot:emergency_stop
3. Redis: DEL bot:loss_pause_until
4. Redis: SET market:mode:override NORMAL EX 86400
5. Restart bot_core

## Times
All times in Sydney AEDT. Jay is in Sydney, Australia.
