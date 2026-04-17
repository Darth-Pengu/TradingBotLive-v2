> **Every CC session must read this file during Step 0 context loading.**
>
> Before reaching for a generic tool (bash, web search, etc.), check if one of
> the registered MCPs below is the better fit. Prefer Helius over curl-to-RPC,
> prefer Postgres MCP over raw `psql`, prefer Playwright MCP over Python
> `requests` for dashboard scraping.
>
> If an MCP is marked ⚠ stubbed, it's registered but needs auth/config before use.
> If a capability you need is missing, check "Requires Jay's attention" before
> building a workaround.

# ZMN Claude Code Tooling Inventory

**Last updated:** 2026-04-17
**Source of truth for:** "what MCPs + skills does CC have access to in this repo"

Every new CC session should `cat docs/CLAUDE_TOOLING_INVENTORY.md` during context loading.

This session (2026-04-17) was the first bulk install of MCPs and skills. Before this,
`.mcp.json` only had `railway` and a broken `redis` entry. All entries below were added
in commit(s) made this session unless otherwise noted.

---

## MCP servers registered in `.mcp.json`

Legend: ✅ active (installed + smoke-testable) · ⚠ stubbed (registered but needs auth/config) · ❌ failed (cannot install in this environment)

### Group A — Crypto / Solana

| Name | Status | Auth | Purpose |
|---|---|---|---|
| `helius` | ⚠ stubbed | `HELIUS_API_KEY` env var | Solana RPC, DAS, priority fees. Replaces curl-to-RPC. |
| `nansen` | ⚠ stubbed | `NANSEN_API_KEY` env var | Smart-money labels, DEX trades, top tokens. NOTE: CLAUDE.md says Nansen is disabled via Redis (budget 508% over). Keep MCP registered but gate usage. |
| `vybe` | ⚠ stubbed | `VYBE_API_KEY` env var | Token holders (labeled), wallet PnL, token balances. 25K credits/mo free tier. |
| `coingecko` | ✅ active | none (free tier) | Token prices, market data. Paid tier would use `COINGECKO_API_KEY`. |
| `dexpaprika` | ✅ active | none | DEX aggregator data. Remote MCP, no key required. |
| `defillama` | ✅ active | none | Protocol TVL, yields. Remote MCP, no key. |
| `rugcheck` | ⚠ stubbed | varies | Token rug score. Community MCP; needs smoke test. |
| `jupiter` | ❌ not installed | requires Solana keypair + `solana-keygen` | Community MCP; `solana-keygen` not installed on this dev machine. See "Requires Jay's attention" below. |
| `birdeye` | ⚠ stubbed | `BIRDEYE_API_KEY` env var | Beta remote MCP. Not on ZMN critical path. |

### Group B — Infra / observability / data

| Name | Status | Auth | Purpose |
|---|---|---|---|
| `railway` | ✅ active | Railway CLI login | Was already present before this session. Deploys, logs, env vars. |
| `postgres` | ❌ not installed | `DATABASE_URL` env var | `crystaldba/postgres-mcp` requires Python+pipx. Neither installed on this dev machine (Windows-store Python stub only). Stub retained for future install; see "Requires Jay's attention". |
| `redis` | ⚠ stubbed | `REDIS_URL` env var | Pre-existing entry was failing connection. Updated to use `REDIS_URL` env placeholder. |
| `sentry` | ⚠ stubbed | OAuth (browser) | Error tracking. Jay needs to run OAuth flow. |
| `github` | ⚠ stubbed | OAuth (browser) | Issues, PRs, code search. Jay needs to run OAuth flow. |
| `gmail` | ⚠ stubbed | OAuth (browser) | Pre-existing. Needs authentication per `claude mcp list`. |
| `gcal` | ⚠ stubbed | OAuth (browser) | Pre-existing (Google Calendar). Needs authentication. |

### Group C — Dev loop

| Name | Status | Auth | Purpose |
|---|---|---|---|
| `playwright` | ✅ active | none | Headed browser tests for the zmnbot.com dashboard. |
| `shadcn` | ✅ active | none | shadcn/ui component registry. For future dashboard refresh. |
| `semgrep` | ⚠ stubbed | varies | Static analysis. Registered; baseline scan deferred — Semgrep CLI not on this dev machine. |
| `socket` | ✅ active | none | Supply-chain dependency scanner. Remote MCP, no key. |
| `python-lft` | ❌ not installed | none | ruff/black/mypy/pytest/pylint unifier. Needs Python. Not installed on this dev machine. |

---

## Skills installed

All skills are project-scoped at `.claude/skills/` so they travel with the repo.

| Name | Scope | Purpose | Source |
|---|---|---|---|
| `mcp-builder` | project | Scaffold new MCP servers. Planned use: build the 4 missing ZMN MCPs (SocialData, PumpPortal, LetsBonk, Jito) in a future session. | github.com/anthropics/skills |
| `skill-creator` | project | Scaffold new skills. | github.com/anthropics/skills |
| `frontend-design` | project | Dashboard redesign patterns. | github.com/anthropics/skills |
| `webapp-testing` | project | Browser-based feature testing (pairs with Playwright MCP). | github.com/anthropics/skills |

---

## Requires Jay's attention

Items needing manual auth / config / install before first use:

1. **Export local env vars** so MCPs with `${VAR}` placeholders resolve. In your shell profile:
   ```bash
   export HELIUS_API_KEY=<from Railway>
   export NANSEN_API_KEY=<from Railway>
   export VYBE_API_KEY=<from Railway>
   export COINGECKO_API_KEY=<optional, only if paid tier>
   export BIRDEYE_API_KEY=<optional>
   export DATABASE_URL=<Railway DATABASE_PUBLIC_URL — gondola.proxy.rlwy.net:29062>
   export REDIS_URL=<Railway REDIS_PUBLIC_URL>
   ```
   Pull current values with `railway variables -s bot_core --kv` (after `railway login`).
   **Never commit these values.** The `.mcp.json` uses `${VAR}` placeholders and resolves at runtime.

2. **OAuth flows — run when online:**
   - `sentry` — first tool call triggers browser flow
   - `github` — first tool call triggers browser flow
   - `gmail`, `gcal` — first tool call triggers browser flow

3. **Install `solana-cli` to unblock Jupiter MCP** (optional; community MCP requires throwaway keypair):
   - `winget install Solana.Solana-Installer` (or https://docs.solana.com/cli/install)
   - Then generate throwaway keypair:
     ```bash
     mkdir -p .claude/keys
     solana-keygen new --no-bip39-passphrase --force --outfile .claude/keys/jupiter_mcp_throwaway.json
     # NEVER FUND THIS WALLET. Paper-trading-only.
     ```
   - Confirm pubkey has zero balance. Export private key as base58 to a local env var `JUPITER_THROWAWAY_KEY`.
   - Add Jupiter MCP entry to `.mcp.json` (see A9 in tooling install prompt).
   - `.claude/keys/` is already gitignored.

4. **Install Python + pipx to unblock Postgres MCP and python-lft MCP:**
   - Install Python 3.11+ from python.org (not the Windows Store stub currently on this machine)
   - Then: `python -m pip install --user pipx && pipx ensurepath`
   - Then: `pipx install postgres-mcp`
   - Re-add postgres block to `.mcp.json` with `--access-mode=restricted` (NEVER `unrestricted` for default config)

5. **Agent Teams experimental flag — user-scope on this dev machine.**
   Enabled this session in `~/.claude/settings.json` (NOT committed to repo). First planned use case: `mcp-builder` session for the 4 missing ZMN MCPs.
   Do NOT enable project-scope — would burn 15× tokens per CC session regardless of task.
   Sync to other dev machines (work, Codespaces) manually by copying the setting.

6. **Semgrep CLI install** (needed before Semgrep MCP can scan):
   - `python -m pip install semgrep` (needs Python)
   - Then run baseline: `semgrep --config auto services/ > docs/SEMGREP_BASELINE.md`
   - Log findings only; do NOT fix in that session.

---

## Explicit non-installs this session

- **The four missing crypto MCPs** (SocialData, PumpPortal, LetsBonk, Jito) — multi-day build each. Use `mcp-builder` skill in a dedicated session.
- **Community skill collections** (`obra/superpowers`, `VoltAgent/awesome-agent-skills`, etc.) — need `snyk agent-scan` set up first. Research cites 36.82% malicious rate on community skills.
- **Figma Dev Mode MCP** — requires paid Figma seat; out of scope.
- **Datadog MCP** — overkill/costly for this project.
- **Glean upload** — Jay's call.

---

## Security posture (this session)

- All API keys in `.mcp.json` are `${ENV_VAR}` placeholders. No values committed.
- `.claude/keys/` is gitignored (for future throwaway Jupiter keypair).
- Postgres MCP deliberately NOT installed (needs Python). When installed in future session, `--access-mode=restricted` is mandatory for default config. The ZMN bot writes to `paper_trades` and `live_trade_log` continuously during live trading — an accidental UPDATE/DELETE from CC would corrupt live state.
  - **Migration-session escape hatch**: for legitimate schema migrations, Jay manually edits `.mcp.json` to `--access-mode=unrestricted`, runs the migration in a dedicated CC session, then reverts `.mcp.json` before any other work. Never commit the unrestricted config. Never use unrestricted mode in an autonomous session.
- Snyk agent-scan NOT run this session — `snyk` CLI not installed. Only Anthropic first-party skills installed, so audit is low-risk but pending.

---

## MCP usage cheat sheet

Tells future CC sessions WHEN to reach for each MCP, not just that they exist.

### Helius (`helius`)
- Typical invocation: "use Helius to get the token accounts for <wallet>" or "fetch asset metadata for <mint>"
- Best tools: `getTokenAccountsByOwner`, `getAsset`, `getPriorityFeeEstimate`
- Avoid: DAS queries on 10k+ token wallets (rate limits). Avoid using for price feeds (use `coingecko`/`dexpaprika` instead — ZMN explicitly disabled Helius for pricing via `HELIUS_DAILY_BUDGET=0`).

### Nansen (`nansen`)
- Typical invocation: "check smart-money activity for <mint> in the last 24h"
- **Budget-gated**: CLAUDE.md says max 50 calls/day when re-enabled. Check `nansen:disabled` Redis key before calling.
- Best tools: `/smart-money/dex-trades`, `/smart-money/top-tokens`, `/profiler/address/labels`

### Vybe (`vybe`)
- Typical invocation: "get labeled holders for <mint>" or "PnL for wallet <addr>"
- 60 RPM, 25K credits/mo free. Cache in Redis with 5-min TTL (per CLAUDE.md cost control rules).

### CoinGecko (`coingecko`)
- Typical invocation: "SOL price right now" or "get 7d price history for <coin>"
- Free tier generous. Good fallback if Jupiter price v3 rate-limits.

### DexPaprika (`dexpaprika`)
- Typical invocation: "pools for token <mint>" or "DEX volume for <pair>"
- Zero friction — no key.

### DefiLlama (`defillama`)
- Typical invocation: "TVL for Raydium" or "yields on Solana"
- Good for sanity-checking external DeFi metrics.

### Railway (`railway`)
- Typical invocation: "show me logs for bot_core" or "what env vars does signal_aggregator have?"
- Best tools: `get-logs`, `list-services`, `list-variables`, `deploy`, `list-deployments`
- Use this INSTEAD OF `railway` CLI in bash — MCP gives structured output.

### Redis (`redis`)
- Typical invocation: "what's in key `bot:status`?" or "scan keys matching `paper:positions:*`"
- Use for cache inspection, queue depths, state fixes.
- **Read-oriented**; mutation commands supported but use with care.

### Playwright (`playwright`)
- Typical invocation: "open zmnbot.com, screenshot the Speed Demon panel"
- Pairs with `webapp-testing` skill for structured test flows.
- Best for: dashboard regression checks, DOM inspection, visual verification.

### shadcn (`shadcn`)
- Typical invocation: "add a shadcn Dialog component to this file"
- For future dashboard refresh work. Not useful until frontend refactor.

### Socket.dev (`socket`)
- Typical invocation: "check if <npm package> has any supply-chain risks"
- Use before adding any new npm dep.

### Semgrep (`semgrep`) — stubbed
- Not usable until `semgrep` CLI installed locally. When ready: "run Semgrep on services/execution.py"

### Skill: `mcp-builder`
- Use in a dedicated future session to build the 4 missing ZMN MCPs (SocialData, PumpPortal, LetsBonk, Jito).

### Skill: `webapp-testing`
- Use with Playwright MCP for dashboard testing scenarios.

### Skill: `frontend-design`
- Use when refreshing dashboard UI patterns.

### Skill: `skill-creator`
- Use when creating a new project-scoped skill (e.g., "ZMN trade replay").

---

## Install failures (for next session)

- `postgres-mcp` — pipx required, pipx requires Python. Windows-store Python is a stub. Need real Python install.
- `python-lft-mcp` — same Python dependency.
- `jupiter-mcp-community` — `solana-keygen` not installed. See Jay's attention item 3.
- `semgrep` CLI — Python dependency.

All four are resolvable by installing a real Python 3.11+ from python.org (not the Windows Store shortcut).
