\# ZMN Bot — Claude Code Session Rules



\## Read this first, every session

\- Read AGENT\_CONTEXT.md completely before writing any code

\- Check what already exists in services/ before building anything new

\- Never assume a file exists — always check first



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

### Gmail MCP
URL: https://gmail.mcp.claude.com/mcp
Use for: Emailing governance reports or trade summaries to Jay.

### Google Calendar MCP
URL: https://gcal.mcp.claude.com/mcp
Use for: Scheduling governance briefings, paper trading review reminders.

### Solana Developer MCP (install with: claude mcp add --transport http solana-dev https://mcp.solana.com)
Use for: Always query before writing Solana transaction code or RPC calls.
Provides current Solana and Anchor Framework documentation.

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

