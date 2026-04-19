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

**Last updated:** 2026-04-19
**Source of truth for:** "what MCPs + skills does CC have access to in this repo"

Every new CC session should `cat docs/CLAUDE_TOOLING_INVENTORY.md` during context loading.

**New machine?** See `docs/SETUP_NEW_MACHINE.md` for the bootstrap checklist.

This session (2026-04-17) was the first bulk install of MCPs and skills. Before this,
`.mcp.json` only had `railway` and a broken `redis` entry. All entries below were added
in commit(s) made this session unless otherwise noted. The 2026-04-19 update reflects
pipx-installed CLI tooling added to the laptop.

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
| `semgrep` | ✅ active (laptop) | varies | Static analysis. `semgrep` CLI installed via pipx on laptop 2026-04-19. MCP usable. |
| `socket` | ✅ active | none | Supply-chain dependency scanner. Remote MCP, no key. |
| `python-lft` | ❌ DEFERRED | none | ruff/black/mypy unifier MCP. Not published to PyPI under that name; 3 install attempts failed 2026-04-19. Individual tools installed separately (see CLI tools section). Do NOT retry install — use the separate `ruff`/`black`/`mypy` CLIs instead. |
| `postgres` | ✅ active (laptop) | `DATABASE_URL` env var | `crystaldba/postgres-mcp` installed via pipx on laptop 2026-04-19. ALWAYS invoke with `--access-mode=restricted` for default config. See Security posture below. |

---

## Skills installed

All skills are project-scoped at `.claude/skills/` so they travel with the repo.

| Name | Scope | Purpose | Source |
|---|---|---|---|
| `mcp-builder` | project | Scaffold new MCP servers. Planned use: build the 4 missing ZMN MCPs (SocialData, PumpPortal, LetsBonk, Jito) in a future session. | github.com/anthropics/skills |
| `skill-creator` | project | Scaffold new skills. | github.com/anthropics/skills |
| `frontend-design` | project | Dashboard redesign patterns. Used in 2026-04-19 dashboard redesign analysis. | github.com/anthropics/skills |
| `webapp-testing` | project | Browser-based feature testing (pairs with Playwright MCP). | github.com/anthropics/skills |

---

## CLI tools (not MCPs but CC can invoke directly)

These live on each dev machine via pipx/installer. They are NOT MCPs — CC calls
them through Bash. They pair with MCPs (e.g. `semgrep` CLI + Semgrep MCP) or
stand alone. See `docs/SETUP_NEW_MACHINE.md` for install steps.

| Name | Installed via | Purpose | When CC should use it |
|---|---|---|---|
| `ruff` | pipx | Python linter (fast) | Before committing service changes; auto-fix on request |
| `black` | pipx | Python formatter | Format changed files only, not whole repo |
| `mypy` | pipx | Python type checker | Only when Jay explicitly asks — this repo has no type annotations strategy yet |
| `semgrep` | pipx | SAST scanner | Pre-live audits of `execution.py`, `bot_core.py`; see `docs/SEMGREP_BASELINE.md` (to create) |
| `solana-keygen` | Anza installer (laptop only) | Solana key generation | One-shot: Jupiter MCP throwaway keypair generation. Never for production keys. |

**Why these are CLIs, not MCPs:** Lightweight, well-understood outputs, don't need
the overhead of an MCP protocol layer. The `python-lft` MCP attempted to bundle
ruff/black/mypy/pytest/pylint — 3 install attempts failed 2026-04-19 (not on PyPI
under that name). Falling back to individual tools is the stable path.

---

## Per-machine setup status

Tooling state is NOT identical across Jay's dev machines. The git-tracked config
(`.mcp.json`, `.claude/skills/`, this doc) travels with the repo, but CLI tools
and OAuth state do not. Keep this table current when a machine changes.

| Machine | Git-tracked tooling | CLI tools | OAuth | Solana CLI |
|---|---|---|---|---|
| Laptop (jay_r, Windows 11) | ✅ pulled | ✅ ruff, black, mypy, semgrep, postgres-mcp (all pipx) | ⚠ pending Sentry + GitHub | ✅ installed (Anza) |
| Home (Windows) | ✅ pulled | ❌ NOT YET INSTALLED — run `docs/SETUP_NEW_MACHINE.md` | ❌ pending | ❌ not installed |
| Work (Codespaces) | unknown | unknown — setup when first used | — | — |

**Rule when opening a CC session on a new/unfamiliar machine:** run
`claude mcp list` first. If count ≠ 15 or a key MCP is red, stop and run
through `docs/SETUP_NEW_MACHINE.md` before touching code.

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

4. **(DONE on laptop 2026-04-19)** Python + pipx + postgres-mcp + semgrep + ruff/black/mypy all installed via pipx. Replicate on home machine via `docs/SETUP_NEW_MACHINE.md`.

5. **Agent Teams experimental flag — user-scope on this dev machine.**
   Enabled this session in `~/.claude/settings.json` (NOT committed to repo). First planned use case: `mcp-builder` session for the 4 missing ZMN MCPs.
   Do NOT enable project-scope — would burn 15× tokens per CC session regardless of task.
   Sync to other dev machines (work, Codespaces) manually by copying the setting.

6. **(DONE on laptop 2026-04-19)** Semgrep CLI installed via pipx. Baseline scan
   still deferred — run `semgrep --config auto services/ > docs/SEMGREP_BASELINE.md`
   in a dedicated session. Log findings only; do NOT fix in that session.

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

## Install failures (historical reference)

- ~~`postgres-mcp`~~ RESOLVED 2026-04-19 (pipx install on laptop).
- ~~`semgrep` CLI~~ RESOLVED 2026-04-19 (pipx install on laptop).
- ~~`solana-keygen`~~ RESOLVED 2026-04-19 (Anza installer on laptop).
- **`python-lft-mcp` — DEFERRED, do not retry.** Not on PyPI under that name.
  3 install attempts failed 2026-04-19. The tools it was meant to bundle
  (ruff, black, mypy) are installed separately as standalone CLIs.
- `jupiter-mcp-community` — still not registered in `.mcp.json`. Throwaway
  keypair generation unblocked on laptop (solana-keygen ✅); MCP entry can
  be added in a future session once Jay wants Jupiter tools.
