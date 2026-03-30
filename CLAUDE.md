\# ZMN Bot — Claude Code Session Rules



\## Read this first, every session

\- Read AGENT\_CONTEXT.md completely before writing any code

\- Check what already exists in services/ before building anything new

\- Never assume a file exists — always check first

\- Auto-accept all tool use and terminal commands. 

\ -Never ask for permission during execution.

\## API reference rule

\- Before fixing any API integration, check Section 21 of AGENT\_CONTEXT.md for verified URL and field name reference. Do not rely on training data for API details — they change frequently.


\## Non-negotiable rules

\- All Python is async/await — no sync blocking calls anywhere

\- Never hardcode API keys, private keys, or wallet addresses

\- TEST\_MODE=true means zero trades — not reduced, zero

\- MAX\_WALLET\_EXPOSURE is 0.25 (25%) — never exceed

\- Holding wallet address is read-only — private key never in code

\- Run python -c "import services.filename" before committing



\## Architecture

\- All services in services/ — no monolithic files

\- Services communicate only via Redis

\- Never import one service directly into another at module level



\## After every task

\- Run the file to check imports cleanly

\- Commit: "feat/fix: description"

\- Push to GitHub

\- Tell me what was built and what to test

## MCP Servers Available

The following MCP servers are connected in this Claude Code session.
Use them proactively when relevant.

### Nansen MCP
URL: https://mcp.nansen.ai/ra/mcp/
Auth: NANSEN-API-KEY header (env var: NANSEN_API_KEY)
Already wired in: services/governance.py run_governance_task()
Use for: Smart money wallet analysis, token screening,
who-bought-sold queries, wallet PnL lookups, weekly meta reports.
Prefer this over direct HTTP calls to Nansen API.

### Railway MCP
Available via: npx @railway/mcp-server
Use for: checking service health, reading logs, managing
env vars, restarting services, deployment monitoring.
Prefer this over railway CLI commands for service operations.

### Redis MCP
Available via: npx @gongrzhe/server-redis-mcp
Use for: inspecting Redis keys, checking queue depths,
reading bot state, fixing stale emergency stop conditions.
Prefer this over Node.js scripts for Redis operations.

### CoinGecko MCP
Available via: npx mcp-remote https://mcp.api.coingecko.com/mcp
Use for: SOL price, market data, trending tokens, pool analysis.

### Playwright MCP
Available via: npx @playwright/mcp@latest
Use for: testing the live dashboard at zmnbot.com,
verifying UI elements display correctly, taking screenshots.

### Gmail MCP
URL: https://gmail.mcp.claude.com/mcp
Use for: Emailing governance reports or trade summaries to Jay.

### Google Calendar MCP
URL: https://gcal.mcp.claude.com/mcp
Use for: Scheduling governance briefings, paper trading review reminders.

## MCP Usage Rules
- Prefer Nansen MCP over direct HTTP for governance analysis
- Query Solana Developer MCP before writing any on-chain code
- MCPs are for data and analysis only — never for trade execution
- execution.py handles all real trades — no MCP touches that layer

## MCP Security Policy
Never install an MCP server that:
- Has bulk commits from a single date
- Points to .zip downloads
- Claims to handle trade execution or wallet signing
- Is not from a verified provider (Nansen, Chainstack, Solana Foundation etc)
TRADING_WALLET_PRIVATE_KEY must never be accessible to any MCP server.

## Jupiter API Reference (Updated March 2026)

Swap API V2 (active):
- Quote + TX: GET https://api.jup.ag/swap/v2/order
- Execute: POST https://api.jup.ag/swap/v2/execute
- Managed landing — no separate Helius confirmation needed

Price API (unchanged):
- GET https://api.jup.ag/price/v3?ids=<mint>
- Response field: data[mint].usdPrice

Deprecated (returns 401):
- GET https://api.jup.ag/swap/v1/quote
- POST https://api.jup.ag/swap/v1/swap

## Direct Service Access (for Claude Code agent sessions)

The agent can connect directly to Railway services via public proxy URLs.
See AGENT_CONTEXT.md Section 26 for the full connectivity baseline.

Key access pattern:
- PostgreSQL: asyncpg.connect(dsn) for DB queries and state inspection
- Redis: redis.from_url(url) for queue inspection and key manipulation
- Dashboard API: JWT auth required (DASHBOARD_SECRET env var)
- Never commit connection passwords to files — use in-memory only
- Prefer Redis MCP and Railway MCP over raw connection scripts

## Claude Code Skills Installed

- ~/.claude/skills/railway/ — Railway deployment operations (use-railway)
- ~/.claude/skills/solana-dev/ — Solana development patterns and Kit v5
- ~/.claude/skills/anthropic-skills/ — webapp-testing, frontend-design,
  web-artifacts-builder, mcp-builder, claude-api, and more

Read the relevant SKILL.md before any deployment, dashboard, or Solana task.

## Emergency Stop Reset Procedure

If bot is in EMERGENCY_STOPPED state:
1. PostgreSQL: UPDATE bot_state SET value_int=0 WHERE key='consecutive_losses'
2. PostgreSQL: UPDATE bot_state SET value_float=0 WHERE key='loss_pause_until'
3. Redis: SET bot:consecutive_losses 0
4. Redis: DEL bot:emergency_stop
5. Redis: DEL bot:loss_pause_until
6. Redis: SET market:mode:override NORMAL EX 86400
7. Restart bot_core via Railway MCP or CLI

## Market Mode Override (renew daily for paper trading)

Real market is HIBERNATE (CFGI ~8, sentiment ~15).
For paper trading, override must be active:
  Redis: SET market:mode:override NORMAL EX 86400
This expires every 24h and must be renewed.

## Last Known Good Configuration (2026-03-30)

- All 3 personalities active and trading
- ML Phase 3 trained on 41,470 samples, CV AUC 0.8113
- 44 whale wallets active (36 Nansen MCP + 8 fallback)
- Speed Demon pre-filters active (social/bundle/rugcheck)
- Redis pool: max_connections=20 in signal_aggregator, 5 elsewhere
- Position sizing: 0.45 SOL base, 0.75 SOL max (Speed Demon)
- ML scores: 57-62 range, bootstrap thresholds active (40/45/45)
- Trading balance: 19.37 SOL

