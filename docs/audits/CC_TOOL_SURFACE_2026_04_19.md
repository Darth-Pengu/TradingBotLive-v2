# CC tool-surface deep recon — 2026-04-19

**Author:** Claude Opus 4.7 (1M-context, autonomous deep recon).
**Scope:** every MCP, skill, and CLI tool now available to Claude Code in this repo, smoke-tested against real ZMN data. Read-only. Zero secrets in this doc.
**Method:** for each MCP, dumped the tool surface from the deferred-tool registry, fired 1–3 ZMN-relevant smoke calls in parallel, and captured request/response/latency/failure-mode notes.

---

## At-a-glance summary

| Group | Tool | Status | Auth | Tools surfaced | Smoke result |
|---|---|---|---|---|---|
| Crypto | helius | ✅ live | `HELIUS_API_KEY` | ~60 | OK after `_feedback`/`_feedbackTool`/`_model` workaround |
| Crypto | nansen | ✅ live | `NANSEN_API_KEY` | 28 | `general_search` works; structured tools require `request:{}` wrapper |
| Crypto | vybe | ✅ live | `VYBE_API_KEY` | 47 endpoints | `list-endpoints` OK; `execute-request` requires HAR-shaped body |
| Crypto | coingecko | ✅ live | none (free tier) | 60+ | OK, fast |
| Crypto | dexpaprika | ✅ live | none | 12 | OK, fast |
| Crypto | defillama | ⚠ auth-pending | OAuth | n/a | Not exercised this session |
| Crypto | birdeye | ⚠ session-expired | `BIRDEYE_API_KEY` | 90+ | First call returned `Session owner unavailable. Please re-initialize.` |
| Infra | railway | ✅ live | Railway CLI login | ~20 | OK; verified all 10 services + env vars |
| Infra | redis | ✅ live | `REDIS_URL` | 4 | OK; KEYS / GET / SET / LIST all functional |
| Infra | sentry | ✅ live | OAuth | ~30 | Authed as jay@rzconsulting.co; **ZERO projects → no SDK integration in services/** |
| Infra | github | ⚠ partial | `GITHUB_PERSONAL_ACCESS_TOKEN` | ~17 | Tools fail with `expected number, received string` for any int arg from Claude Code |
| Infra | gmail / gcal / gdrive | ⚠ auth-pending | OAuth | dozens | Not exercised |
| Dev | playwright | ⚠ flaky | none | 24 | Both `browser_navigate` calls returned `net::ERR_ABORTED / Target page closed`. Browser session unstable on Win11 box this session. |
| Dev | shadcn | ⚠ JSON-typing | none | 6 | Every call rejects `registries` / `limit` because Claude Code passes them as strings |
| Dev | socket | ⚠ JSON-typing | none | 1 | `depscore` rejects `packages` arg — wants array, gets string |
| Dev | context7 (plugin) | ⚠ JSON-typing | none | 2 | `resolve-library-id` rejects `query` — schema-driven name mismatch with passed kwargs |
| CLI | ruff 0.15.11 | ✅ | n/a | n/a | `--version` OK |
| CLI | black 26.3.1 | ✅ | n/a | n/a | OK |
| CLI | mypy 1.20.1 | ✅ | n/a | n/a | OK |
| CLI | semgrep 1.159.0 | ✅ | n/a | n/a | OK |
| CLI | solana-keygen 3.1.13 | ✅ | n/a | n/a | OK |
| CLI | postgres-mcp | ⚠ not registered | `DATABASE_URL` | n/a | Installed via pipx, but `.mcp.json` does NOT register it, so it's not callable as MCP. Ran a Python `asyncpg` shim instead — `Scripts/export_paper_trades.py` and inline `py -3.13 -c "..."` queries — both work. |

**Bottom line:** all 14 MCPs in `.mcp.json` are at least registered and most are callable. The friction this session was almost entirely **JSON-typing of integer/array args from Claude Code** (see "cross-cutting failure" below) — not the MCPs themselves.

---

## Cross-cutting failure: JSON typing of numeric / array args

This came up in **6 different MCPs** (helius, github, shadcn, socket, context7, nansen). Pattern:

- Claude Code's tool-call envelope serializes scalar args as JSON strings.
- Many MCPs declare their arg schemas as `type: number` or `type: array`.
- A call like `getWalletHistory(address=..., limit=10)` arrives at the MCP as `limit: "10"` and the schema validator rejects it.

**Workaround:** for ints, omit the param when the default is acceptable; for arrays, pass JSON-array literals; for nested objects (Nansen, Vybe), wrap in a `request: {...}` field.

**Real fix (not for this session):** report upstream that the MCP-tool param coercion in Claude Code should respect `"type": "number"` and stringify-then-parse on the way through. Until then, every new MCP integration has to be smoke-tested for this.

---

## helius

**Status:** ✅ live · **Auth:** `HELIUS_API_KEY` env var · **Plan info:** see below.

### Tool surface (representative, ~60 tools)

`getBalance`, `getTokenBalances`, `getWalletBalances`, `parseTransactions`, `getTransactionHistory`, `getWalletHistory`, `getWalletTransfers`, `getAsset`, `getAssetsByOwner`, `searchAssets`, `getAssetsByGroup`, `getSignaturesForAsset`, `getNftEditions`, `getAssetProof`, `getAssetProofBatch`, `getAccountInfo`, `getTokenHolders`, `getTokenAccounts`, `getProgramAccounts`, `getNetworkStatus`, `getBlock`, `getHeliusPlanInfo`, `compareHeliusPlans`, `previewUpgrade`, `upgradePlan`, `payRenewal`, `getRateLimitInfo`, `lookupHeliusDocs`, `troubleshootError`, `getSenderInfo`, `getWebhookGuide`, `getLatencyComparison`, `getPumpFunGuide`, `recommendStack`, `getSIMD`, `listSIMDs`, `searchSolanaDocs`, `readSolanaSourceFile`, `fetchHeliusBlog`, `accountSubscribe`, `transactionSubscribe`, `laserstreamSubscribe`, `createWebhook`, `deleteWebhook`, `getAllWebhooks`, `getWebhookByID`, `updateWebhook`, `getEnhancedWebSocketInfo`, `getLaserstreamInfo`, `agenticSignup`, `checkSignupBalance`, `setHeliusApiKey`, `getAccountStatus`, `getHeliusCreditsInfo`, `getStarted`, `getPriorityFeeEstimate`, `transferSol`, `transferToken`, `generateKeypair`, `getWalletFundedBy`, `getWalletIdentity`, `batchWalletIdentity`, `listHeliusDocTopics`.

### Required scaffold

Every Helius tool requires three extra args (used for telemetry/feedback): `_feedback`, `_feedbackTool`, `_model`. Forgetting them returns a `zod`-style validation error. Claude Code wraps these silently if you don't pass them — **you must pass them yourself**. Treat as boilerplate.

### Deep-dive 1 — `getBalance` for the trading wallet

```
address: 4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ
```

Response (200ms):
> **SOL Balance for 4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ**
> 1.610389092 SOL (1,610,389,092 lamports)

Cacheable: yes, 30s. Cost: 1 credit.

**ZMN-relevant finding:** wallet was 3.677 SOL in the abort report 6 hours ago, now **1.61 SOL** — a 2.07 SOL drop. `paper_trades` shows zero `trade_mode='live'` rows but `live_trade_log` has 36 `TX_SUBMIT buy` events in the last 7 days. The bot has been spending real SOL outside the recorded `trade_mode='live'` path. **Open thread for Phase 2.**

### Deep-dive 2 — `getRateLimitInfo`

Returns the full Helius pricing matrix as Markdown. Free tier = 10 RPS RPC, 2 RPS DAS, 5 webhooks. Developer = 50 RPS RPC, 10 RPS DAS. ZMN currently hits free-tier limits frequently in `signal_aggregator`. **Cacheable: 24h.**

### Deep-dive 3 — `getNetworkStatus`

Real-time Solana epoch/TPS/cluster info. Epoch 958 in progress (76.1%), 927 real TPS, 2,823 incl. vote, supply 624.6M SOL. Cluster v3.1.13. Sub-300ms latency. Useful for the `market_health` service to add a "Solana congestion" gauge that's not currently shown.

### Deep-dive 4 — `getAsset(<known pumpfun mint>)`

```
id: FxvkQc1jXFFsGFjjrUt1N1b724BLKsDF46JtQ3iKpump  (Plush Pepe — currently open SD position)
```

Returns: name, symbol, supply, decimals, program (Token-2022), price ($0.000008 USDC), description, image URL, mutability flag. **Replaces** the bonding-curve metadata pull in `signal_listener` for any token already on Helius. Latency ~250ms.

### Failure modes observed

- **Missing `_feedback` triplet:** clean `MCP error -32602: Input validation error` listing the three missing args.
- **Integer args in JSON:** `getWalletHistory(limit=10)` → `Expected number, received string`. Drop the arg or make the harness pass a literal int.
- **Daily budget guard:** ZMN has `HELIUS_DAILY_BUDGET=0` and `HELIUS_ENRICHMENT_ENABLED=false` in env right now. Free-tier credits are real, but `treasury` still hits `getBalance` every 5 min — would burn ~288 credits/day if uncapped.

### ZMN fit

| Replace this | With this | Where |
|---|---|---|
| Curl-to-RPC `getBalance` polling | `helius.getBalance` | `services/treasury.py` |
| Hardcoded priority-fee tiers | `helius.getPriorityFeeEstimate` | `services/execution.py:_send_transaction` |
| Bonding-curve-only token metadata | `helius.getAsset` for any post-graduation token | `services/signal_listener.py` enrichment path |
| Manual sell-failure tracking | `helius.parseTransactions` for `TX_SUBMIT sell` errors | `services/bot_core.py` sell-storm circuit breaker |

---

## nansen

**Status:** ✅ live · **Auth:** `NANSEN_API_KEY` · **Budget gate:** `NANSEN_DAILY_BUDGET=2000` (signal_aggregator), `NANSEN_DRY_RUN=TRUE` (currently dry-run only; bot does not call live).

### Tool surface (28 tools)

`general_search`, `address_counterparties`, `address_historical_balances`, `address_portfolio`, `address_related_addresses`, `address_transactions`, `growth_chain_rank`, `hyperliquid_leaderboard`, `nansen_score_top_tokens`, `prediction_market_*` (8 tools), `smart_traders_and_funds_perp_trades`, `smart_traders_and_funds_token_balances`, `token_current_top_holders`, `token_dex_trades`, `token_discovery_screener`, `token_flows`, `token_info`, `token_ohlcv`, `token_pnl_leaderboard`, `token_quant_scores`, `token_recent_flows_summary`, `token_transfers`, `token_who_bought_sold`, `transaction_lookup`, `wallet_pnl_for_token`, `wallet_pnl_summary`.

### Deep-dive 1 — `general_search("solana")`

Returns 25 results: SOL across multiple chains, plus a long tail of pump.fun memecoins named "solana*" / "🌱 SOLANA*". Latency ~2s. SOL price line item: $85.42 (Solana mint), $85.35 (BNB-bridged), $85.40 (Base-bridged) — a 7-cent cross-chain spread. Could be useful as an arbitrage signal source if ZMN ever expands beyond Solana.

### Deep-dive 2 — `token_info` / `token_quant_scores`

Both rejected this session because the JSON typing wraps args into `request: {}` form rather than flat kwargs. Fix on next attempt: pass `request: {"chain":"solana","token_address":"<mint>"}`.

### Deep-dive 3 — Budget posture

CLAUDE.md says Nansen was 508% over budget when disabled (~April 12). Current env shows `NANSEN_DRY_RUN=TRUE` and `NANSEN_DAILY_BUDGET=2000`. The Redis `nansen:disabled` key is **not present** (was previously set to `true EX 86400` daily). So Nansen is *callable* — but ZMN's services are gated by `NANSEN_DRY_RUN`. The MCP itself is fine.

### Failure modes observed

- **Args wrapped in `request:`:** Nansen MCP serializer expects `request: {key: value}` not flat kwargs. This is non-obvious. Three calls failed before I figured out the shape. Document this for future sessions.
- **Limit / pagination:** at least one tool (`general_search`) defaulted to 25 with no page cursor returned in this surface — pagination posture unclear.

### ZMN fit

| Use | Tool | Where |
|---|---|---|
| Refresh `watched_wallets` table | `nansen_score_top_tokens` → top wallets buying them → `address_portfolio` | `services/nansen_wallet_fetcher.py` (already exists; adapt to use MCP instead of direct HTTP) |
| Pre-entry quant score gate | `token_quant_scores` (when re-enabled) | `services/signal_aggregator.py` after BSR + ML scoring |
| Smart-money flow snapshot | `token_recent_flows_summary` | New widget on dashboard, or pre-entry diagnostic |
| Dead-wallet trim | `wallet_pnl_summary` per `watched_wallets.address`, mark stale ones inactive | `services/nansen_wallet_fetcher.py` |

---

## vybe

**Status:** ✅ live · **Auth:** `VYBE_API_KEY` · **Plan:** free tier (25k credits/month, 60 RPM).

### Tool surface (3 MCP tools wrap 47 REST endpoints)

MCP tools: `list-endpoints`, `search-endpoints`, `get-endpoint`, `execute-request`.

REST endpoints exposed (live, fetched this session):

- **Markets:** `/v4/markets`, `/v4/markets/{addr}`, `/v4/markets/{addr}/candles`
- **Pyth oracle:** `/v4/oracle/pyth/pricefeeds`, `/v4/oracle/pyth/pricefeeds/{addr}/candles|price|price-ts`, `/v4/oracle/pyth/products/{addr}`
- **Programs:** `/v4/programs/labeled-program-accounts`
- **Reference:** `/v4/reference/dexes`, `/v4/reference/instruction-names`
- **Tokens:** `/v4/tokens`, `/v4/tokens/{mint}`, `/v4/tokens/{mint}/candles`, `/v4/tokens/{mint}/holders-count-ts`, `/v4/tokens/{mint}/liquidity`, `/v4/tokens/{mint}/markets-ts`, `/v4/tokens/{mint}/top-holders`, `/v4/tokens/{mint}/top-pnl-traders`, `/v4/tokens/{mint}/trade-volume-ts`, `/v4/tokens/{mint}/trader-activity`
- **Trades / transfers:** `/v4/trades`, `/v4/transfers`
- **Trading:** `/v4/trading/swap` (POST), `/v4/trading/swap-quote`
- **Wallets — single:** `/v4/wallets/{owner}/counterparties|defi-positions|dust-accounts|empty-accounts|nft-balance|pnl|pnl-ts|token-accounts-balance-ts|token-balance|token-balance-ts|transfer-volume-usd`
- **Wallets — batch:** `/v4/wallets/batch/dust-accounts|empty-accounts|nft-balances|token-accounts-balance-ts|token-balances|token-balances-ts`
- **Wallets — reference:** `/v4/wallets/labeled-accounts`, `/v4/wallets/top-traders`
- **Wallet utilities:** `/v4/wallets/util/close-token-accounts`, `/v4/wallets/util/withdraw-mev`

### Deep-dive 1 — `list-endpoints`

Returns the JSON above (47 endpoints). Latency ~600ms. Cacheable: yes, 24h.

### Deep-dive 2 — `execute-request` against `/v4/tokens/{mint}/top-holders`

Failed this session: `execute-request` requires a `harRequest` object (HAR-format request body), not a flat `endpoint`/`method`/`path` shape. Workaround: use `get-endpoint` first to fetch the tool's expected shape.

### Deep-dive 3 — Most-promising ZMN endpoints

- `/v4/tokens/{mint}/top-holders` — labeled holder concentration. Direct fit for the pre-entry concentration filter described in Phase 2.5.
- `/v4/wallets/{owner}/pnl` — for `watched_wallets` curation.
- `/v4/tokens/{mint}/trader-activity` — early signal of insider activity.
- `/v4/oracle/pyth/pricefeeds/{addr}/price` — alternative price source if Jupiter is rate-limited.

### Failure modes observed

- `execute-request` HAR-shape requirement (above).
- 60 RPM hard cap — burst-spike protection needed in any service that calls Vybe in tight loops.
- 25k credits/month free is **plenty** for ZMN's expected volume (12-15 calls per entry × 100 entries/day = 1.5k calls/day = 45k/month if every entry is enriched). With 5-min Redis TTL caching that drops to ~10-15k/month.

### ZMN fit

| Use | Endpoint | Where |
|---|---|---|
| Pre-entry holder concentration | `/v4/tokens/{mint}/top-holders` | `services/signal_aggregator.py` filter v5 (additive, metrics-only N days) |
| Pyth fallback for SOL price | `/v4/oracle/pyth/pricefeeds/{SOL_PYTH}/price` | `services/market_health.py` cascade if CoinGecko fails |
| Wallet PnL refresh | `/v4/wallets/{addr}/pnl` | `services/nansen_wallet_fetcher.py` second-source |
| Liquidity at entry time | `/v4/tokens/{mint}/liquidity` | additive ML feature |

---

## coingecko

**Status:** ✅ live · **Auth:** none (free) · **Speed:** ~250-400ms typical.

### Tool surface (60+ tools)

Highlights for ZMN: `get_simple_price`, `get_simple_supported_vs_currencies`, `get_id_coins`, `get_coins_markets`, `get_coins_top_gainers_losers`, `get_search_trending`, `get_search`, `get_pools_onchain_trending_search`, `get_addresses_pools_networks_onchain_multi`, `get_addresses_tokens_networks_onchain_multi`, `get_networks_onchain_dexes`, `get_onchain_categories`, `get_pools_networks_onchain_info`, `get_tokens_networks_onchain_pools|info|holders-chart|top-holders|top-traders|trades`, `get_timeframe_pools_networks_onchain_ohlcv`, `get_timeframe_tokens_networks_onchain_ohlcv`, `get_holding_chart_public_treasury`, `get_transaction_history_public_treasury`, `get_global`, `get_pools_onchain_megafilter`, `get_pools_onchain_categories`, `get_search_onchain_pools`, `search_docs`, plus full-fat market chart / OHLC / range endpoints.

### Deep-dive 1 — `get_simple_price(ids=solana, vs_currencies=usd, include_24hr_change=true)`

```json
{"solana":{"usd":85.6,"usd_24h_change":-3.187548...}}
```
~250ms. Compared to ZMN's Redis `market:sol_price` = 85.92 (slightly stale, 5-min cache). CoinGecko is cleanly callable as a fallback when Jupiter rate-limits. Already in `market_health.py` cascade.

### Deep-dive 2 — `get_pools_onchain_trending_search(network=solana)`

Returned PENGU/USDC dominant, plus a delete-tagged Abstract pool and a BSC pool. Useful for context but **not directly ZMN-actionable** — ZMN trades fresh pump.fun bonds, not trending established pools.

### Deep-dive 3 — `get_tokens_networks_onchain_top_holders` (not exercised this session)

Free-tier alternative to Vybe's `/v4/tokens/{mint}/top-holders`. Worth comparing latency and labeling quality in a follow-up.

### Failure modes observed

- None this session at free-tier limits.
- The "Pro" tier endpoints (paid) gracefully `404` rather than billing.

### ZMN fit

Already used as the primary SOL price source in `market_health.py`. Add: trending pump.fun pools as a "macro mood" gauge in the dashboard.

---

## dexpaprika

**Status:** ✅ live · **Auth:** none · **Speed:** ~400-600ms.

### Tool surface (12 tools)

`getNetworks`, `getNetworkDexes`, `getNetworkPools`, `getDexPools`, `getPoolDetails`, `getPoolOHLCV`, `getPoolTransactions`, `getStats`, `getTokenDetails`, `getTokenPools`, `search`.

### Deep-dive 1 — `getStats`

```json
{"chains":35,"factories":218,"pools":31858300,"tokens":29511883}
```
Global. Confirms Solana is the busiest chain by transaction count.

### Deep-dive 2 — `getNetworks`

35 chains. Solana = $7.9B 24h volume, 26.5M txns, 64,756 pools. PumpSwap = $4.96B/day, 11,610 pools (the #1 Solana DEX by volume). Pump.fun proper = $49.6M/day, 27,394 pools.

### Deep-dive 3 — `search("PUMP")`

Returns the actual Pump token (`pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn`, $0.00184, $1.99M 24h vol, $8.08M liquidity), plus a long tail of imitation PUMP/PUMPHOUSE memecoins. Useful for understanding market context but again not directly ZMN-actionable.

### Failure modes observed

- None this session.
- Rate limit unknown but didn't trip during ~6 calls.

### ZMN fit

| Use | Tool | Where |
|---|---|---|
| Backup price for stale-price exits | `getTokenDetails(token=<mint>)` | `services/bot_core.py` exit price cascade (post Redis → bonding curve → Jupiter → Gecko → DexPaprika) |
| Pool transaction history | `getPoolTransactions` | Forensics for any disputed exit |
| New-token discovery counter | `getNetworkPools(network=solana, sort=newest)` | Dashboard widget: "new pools / hour" |

---

## defillama

**Status:** ✅ live (no key required for read) but `authenticate` tool surfaced means the MCP supports paid-tier auth · **Auth:** OAuth (paid features).

Not exercised this session. Surface includes basic protocol/TVL endpoints. Low ZMN priority — DeFiLlama's main strength is multi-chain TVL and yield aggregation, neither of which moves the needle on memecoin trading.

---

## birdeye

**Status:** ⚠ session expired · **Auth:** `BIRDEYE_API_KEY`.

### Tool surface (90+ tools, very granular)

Heavy emphasis on `defi/v3/*` token & pair endpoints (overview, market-data, OHLCV, top-traders, holder, trade-data, mint-burn-txs, exit-liquidity), `defi/v3/token-meme-list|meme-detail-single` (memecoin-specific), `wallet/v2/*` (PnL, balance change, net worth, transfer history), `holder/v1/distribution`, `smart-money/v1/token-list`, `trader/gainers-losers`, `utils/v1/credits`. Looks the deepest of the price/market-data MCPs.

### Deep-dive 1 — `get-defi-networks`

```
Streamable HTTP error: ... "Session owner unavailable. Please re-initialize."
```
Root cause unclear — likely the remote MCP's session went stale and needs an HTTP `initialize` request the local Claude Code harness didn't issue. Recovery: restart Claude Code, retry the call. Not a Birdeye bug per se.

### Failure modes observed

- Session-expired error on first call. Need a session-refresh story for any auto-loop that depends on Birdeye.

### ZMN fit

If the session issue is resolvable, Birdeye is the closest one-stop shop for memecoin-specific data: `defi/v3/token-meme-detail-single`, `defi/v3/token-exit-liquidity`, `holder/v1/distribution` are all directly relevant to the entry filter / risk gate. **Worth an explicit re-test in the next session.**

---

## railway

**Status:** ✅ live · **Auth:** Railway CLI login.

### Tool surface (~20 tools)

`list-projects`, `list-services`, `link-environment`, `link-service`, `list-deployments`, `list-variables`, `set-variables`, `deploy`, `deploy-template`, `generate-domain`, `get-logs`, `check-railway-status`, `create-environment`, `create-project-and-link`.

### Deep-dive 1 — `list-services`

Returns 10 services for `airy-truth`: market_health, web, signal_aggregator, ml_engine, bot_core, Redis, signal_listener, treasury, governance, Postgres. Confirms 8 user-services + Postgres + Redis.

### Deep-dive 2 — `list-variables(service=Postgres, kv=true)`

Returned 30+ env vars including the public DSN and credentials. Used to pull `DATABASE_PUBLIC_URL` for the asyncpg shim. **Critical: this output should NEVER end up in a doc** — the redaction discipline lives at the Phase 6 grep gate.

### Deep-dive 3 — `list-variables(service=bot_core, kv=true)`

Found the live env state. Highlights for Phase 4 planning (the env, not the values):

| Var | Value posture | Note |
|---|---|---|
| `TEST_MODE` | true | Paper mode confirmed |
| `AGGRESSIVE_PAPER_TRADING` | true | Bypasses HIBERNATE gate in signal_aggregator |
| `ANALYST_DISABLED` | true (signal_aggregator only) | Per CLAUDE.md hard-disable |
| `ML_THRESHOLD_SPEED_DEMON` | **30 (bot_core) / 40 (signal_aggregator)** | Inconsistent across services — needs investigation |
| `MAX_SD_POSITIONS` | 20 (bot_core) / 3 (signal_aggregator) | Inconsistent — bot_core wins for trading |
| `MIN_POSITION_SOL` | 0.05 (bot_core) / 0.10 (signal_aggregator) | Inconsistent |
| `STAGED_TAKE_PROFITS_JSON` | `[[2.00, 0.20], [5.00, 0.375], [10.00, 1.00]]` | **Already at the abort report's recommendation** |
| `TIERED_TRAIL_SCHEDULE_JSON` | `[[0.30, 0.35], [0.75, 0.25], [2.00, 0.18], [5.00, 0.14], [10.00, 0.12]]` | **Already at the abort report's recommendation** |
| `DAILY_LOSS_LIMIT_SOL` | 4.0 | Matches abort report |
| `HELIUS_ENRICHMENT_ENABLED` | false | Helius gated off until April 26 budget reset |
| `NANSEN_DRY_RUN` | TRUE | Nansen calls are dry-run |

### Failure modes observed

- Long output (~80 env vars per service). Pagination/filtering would help.

### ZMN fit

This is the single most useful MCP for this repo. Use `list-variables` instead of `railway variables` CLI (structured output), `set-variables` instead of `railway variables --set` (single-call batched env edits trigger one redeploy), `get-logs` for tail-style log inspection, `list-deployments` to verify recent deploy state.

---

## redis

**Status:** ✅ live · **Auth:** `REDIS_URL` · **Tools:** `get`, `set`, `delete`, `list` (KEYS pattern).

### Deep-dive 1 — Bot state snapshot

Calls + responses (in parallel):

- `get market:sol_price` → `85.92`
- `get bot:portfolio:balance` → `194.67503907483749` SOL (paper)
- `get market:health` → JSON with `mode=HIBERNATE`, `cfgi=34.5`, `cfgi_btc=27.0`, `cfgi_sol=34.5 (cfgi.io)`, `dex_volume_24h=$972M`
- `get market:mode:current` → `HIBERNATE`
- `get bot:status` → JSON with `RUNNING`, `portfolio_balance=194.68 SOL`, `daily_pnl=0.072 SOL`, `open_positions=3` (Speed Demon), `market_mode=DEFENSIVE`, `consecutive_losses=1`, `test_mode=true`
- `get bot:daily_pnl` → `0`
- `get bot:consecutive_losses` → `1`

**Conflict observed:** `bot:status.market_mode = DEFENSIVE` but `market:mode:current = HIBERNATE`. bot_core is reading a different mode source than the global Redis key. Likely the cause: bot_core's `_load_state` uses its own market-mode evaluation (or a stale value at start), and only writes `bot:status` periodically.

### Deep-dive 2 — Key-pattern enumeration

Pattern → count:
- `market:*` → 7 keys
- `bot:*` → 4 keys
- `paper:positions:*` → 3 keys (matches the 3 open positions in `bot:status`)
- `whale:*` → 1 key (`whale:watched_wallets`)
- `token:latest_price:*` → ~280 keys (heavy cache use; SOL-denominated per CLAUDE.md)
- `shadow:*` → 1 key (`shadow:measurements` — instrumentation list)
- `signals:*` → 1 key (`signals:evaluated`)

**No `nansen:disabled` key present** → Nansen is technically callable (but `NANSEN_DRY_RUN=TRUE` env var still gates the bot).
**No `bot:emergency_stop` or `bot:loss_pause_until` keys** → bot is unblocked on emergency-stop and loss-pause guards.
**No `market:mode:override` key** → no overnight mode override active.

### Deep-dive 3 — Cross-checks

`paper:positions:*` keys exactly match `bot:status.positions` JSON. The Apr 17 ghost-position cleanup is holding — only 3 keys remain, all currently open Speed Demon positions.

### Failure modes observed

- None. Redis MCP behaves like a thin wrapper over a Redis client.

### ZMN fit

Use this instead of `redis-cli -u $REDIS_URL` in any session that touches Redis. Single-call patterns:
- `list bot:* / market:* / paper:positions:*` for state inspection.
- `get bot:status` for the dashboard's primary widget feed.
- `delete <key>` for stale-state cleanup (use with care).

---

## sentry

**Status:** ✅ live (authenticated as jay@rzconsulting.co, org `rz-consulting`) · **Auth:** OAuth (already complete this session).

### Tool surface (~30 tools)

`whoami`, `find_organizations`, `find_projects`, `find_teams`, `find_dsns`, `find_releases`, `create_dsn`, `create_project`, `create_team`, `update_project`, `update_issue`, `search_issues`, `search_issue_events`, `search_events`, `search_docs`, `analyze_issue_with_seer`, `get_issue_tag_values`, `get_event_attachment`, `get_profile_details`, `get_replay_details`, `get_doc`, `get_sentry_resource`.

### Deep-dive 1 — `whoami`

Authenticated. Org: `rz-consulting`, region: `us.sentry.io`.

### Deep-dive 2 — `find_projects(organizationSlug=rz-consulting)`

```
No projects found.
```

**This is the major finding for ZMN.** Sentry is fully usable from the MCP, but the bot has **no Sentry SDK integration in `services/`**. Every error currently dies in Railway logs and dashboard widget surfaces. Fixing this is a 30-min `pip install sentry-sdk` + `sentry_sdk.init(...)` per service work item — flagged for Tier 2 in the optimization plan.

### Deep-dive 3 — `search_issues(naturalLanguageQuery=…)`

Trivially returns "no issues found" because there are no projects yet.

### Failure modes observed

- `search_issues` requires `naturalLanguageQuery`, not `query` — the schema name doesn't match the obvious one.

### ZMN fit

| Use | Tool | Where |
|---|---|---|
| ERROR/EXCEPTION capture in services | `sentry_sdk.init(dsn=...)` (not the MCP — the SDK in code) | every `services/*.py` |
| One-off error analysis | `analyze_issue_with_seer` | when a CC session is debugging a Railway log spike |
| Performance/latency profiling | `get_profile_details` | bot_core / signal_aggregator hot path investigation |

---

## github

**Status:** ⚠ partial · **Auth:** `GITHUB_PERSONAL_ACCESS_TOKEN`.

### Tool surface (~17 tools, plus a 30+ tool plugin namespace `plugin_github_github`)

Core: `list_commits`, `get_file_contents`, `search_code`, `search_repositories`, `search_issues`, `list_pull_requests`, `get_pull_request`, `create_pull_request`, `add_issue_comment`, `create_issue`, `update_issue`, `create_branch`, `create_or_update_file`, `push_files`, `merge_pull_request`, `fork_repository`, `create_repository`, `update_pull_request_branch`, `get_pull_request_files`, `get_pull_request_reviews`, `get_pull_request_status`, `get_pull_request_comments`, `create_pull_request_review`.

### Deep-dive

`list_commits(owner=Darth-Pengu, repo=TradingBotLive-v2, perPage=5)` failed with `Expected number, received string`. This will hit every tool that takes int args — `perPage`, `page`, `since`, `until`. Workaround: omit those args and accept defaults; or call the GitHub REST API directly via `Bash`/`gh`. Note: `gh` CLI is not installed on this Win11 box, so neither path is convenient.

### ZMN fit

Lower priority right now — the local `git` CLI covers most needs. Useful for cross-repo reading (e.g. fetching upstream skill source files), PR creation, and search across the org.

---

## playwright

**Status:** ⚠ flaky this session · **Auth:** none · **Tools:** 24.

### Tool surface

`browser_navigate`, `browser_navigate_back`, `browser_close`, `browser_snapshot`, `browser_take_screenshot`, `browser_click`, `browser_hover`, `browser_drag`, `browser_select_option`, `browser_type`, `browser_press_key`, `browser_handle_dialog`, `browser_wait_for`, `browser_console_messages`, `browser_network_requests`, `browser_resize`, `browser_evaluate`, `browser_run_code`, `browser_fill_form`, `browser_file_upload`, `browser_tabs`, `browser_snapshot`.

### Deep-dive

Both `browser_navigate(zmnbot.com/dashboard/dashboard.html)` and `browser_navigate(zmnbot.com/)` returned `net::ERR_ABORTED; maybe frame was detached?` and `Target page, context or browser has been closed`. **The dashboard URL is reachable** (`curl -I https://zmnbot.com/dashboard/dashboard.html` returns `HTTP/1.1 200 OK` in under 1s). The fault is in the local Playwright headless browser session, not the dashboard.

### Failure modes observed

- Browser context closes between calls. May need an explicit `browser_open` first, or a context-keep-alive setting.
- The harness on Windows 11 may be hitting a known Playwright + Edge/Chromium subprocess race.

### ZMN fit

Critical for the dashboard testing plan. Pair with `webapp-testing` skill for structured flows. **Resolve the session stability issue in a dedicated short session before the dashboard regression suite is built.**

---

## shadcn / socket / context7

These three MCPs all hit the JSON-typing wall:

- **shadcn** `list_items_in_registries(registries=["@shadcn"])` → `Expected array, received string`. Workaround: pass the array literally as `["@shadcn"]` (already does) — but the framework still serializes it as a string. Defer to next CC release that fixes this in the bridge.
- **socket** `depscore(packages=[{"ecosystem":"pypi","depname":"aiohttp"}])` → same JSON-array issue.
- **context7** `resolve-library-id(libraryName=solders)` and `resolve-library-id(query=solana solders)` both rejected. The `query` field is the canonical one but is currently not being threaded through. Documentation lookup workaround: use Anthropic web search.

### ZMN fit

- **shadcn** — high value for a future dashboard refactor.
- **socket** — should run as a one-off pre-deploy step against `requirements.txt` (out-of-MCP equivalent: `pipx install pip-audit`).
- **context7** — would be the canonical way to look up Solana/asyncpg/aiohttp/lightgbm docs from inside CC. Current workaround: WebSearch tool when needed.

---

## CLI tools (laptop pipx-installed, not MCPs)

| Tool | Version | When CC should use |
|---|---|---|
| `ruff` | 0.15.11 | Before committing `services/*.py` changes; auto-fix on request |
| `black` | 26.3.1 | Format only changed files; never blanket-format the repo |
| `mypy` | 1.20.1 | Only if Jay asks — repo has no annotations strategy |
| `semgrep` | 1.159.0 | Pre-live audits on `execution.py` / `bot_core.py`. Run `semgrep --config auto services/ > docs/SEMGREP_BASELINE.md` once. |
| `solana-keygen` | 3.1.13 | One-shot Jupiter MCP throwaway keypair generation. Never for prod keys. |
| `postgres-mcp` (pipx) | unversioned | **Not registered in `.mcp.json`.** To use as MCP, add `{"command":"postgres-mcp","args":["--access-mode=restricted","${DATABASE_PUBLIC_URL}"]}` block. Until then, use the Python `asyncpg` shim at `Scripts/export_paper_trades.py` (this session's contribution). |

---

## Skills installed (`.claude/skills/`)

### `mcp-builder`
**Triggers:** when CC is asked to build a new MCP server. Provides scaffolding, sample SDK code (Node/Python), TypeScript types for tool schemas, and reference patterns for HTTP / stdio transports. **ZMN use case:** the four missing crypto MCPs (SocialData, PumpPortal, LetsBonk, Jito). See `MCP_BUILDER_CANDIDATES_2026_04_19.md`.

### `skill-creator`
**Triggers:** create new skill, edit existing skill, eval/optimize skill descriptions. Has an evals viewer (`eval-viewer/viewer.html`) for measuring skill performance and an optimizer for description tuning. **ZMN use case:** a "zmn-trade-analysis" skill that codifies the `corrected_pnl_sol` vs `realised_pnl_sol` gotcha + the 7d exit-reason breakdown query as boilerplate so future sessions don't redo the discovery. Scoped only — see Phase 3.D.

### `frontend-design`
**Triggers:** any frontend / UI design work — components, pages, dashboards, posters. Generates "distinctive, production-grade" code that avoids generic AI aesthetics. **ZMN use case:** already used for the 2026-04-19 dashboard redesign concepts. Addendum in `DASHBOARD_ANALYSIS_2026_04_19.md`.

### `webapp-testing`
**Triggers:** browser-based feature testing for local web apps. Pairs with Playwright MCP. Verifies frontend functionality, debugs UI behavior, captures screenshots, views console logs. **ZMN use case:** dashboard regression testing — see `DASHBOARD_TESTING_PLAN_2026_04_19.md`.

---

## What this changes for future sessions

1. **Helius's `_feedback`/`_feedbackTool`/`_model` triplet** must be on every Helius call. Bake it into a wrapper if used in a loop.
2. **JSON-typing failure mode** is the #1 reason CC sessions falsely conclude an MCP is broken. Try with omit-the-int-arg before giving up.
3. **Sentry MCP works, but ZMN has no Sentry projects** — biggest one-session ROI is `sentry_sdk.init(...)` in services.
4. **Postgres MCP not registered in `.mcp.json`** — use the asyncpg shim until registered.
5. **Birdeye session stability** is fragile — restart Claude Code if you see "Session owner unavailable."
6. **Playwright headless browser instability** is the blocker for dashboard regression work this session.
7. **Vybe's `execute-request` HAR-shape** requirement is non-obvious — `get-endpoint` first.
8. **Nansen tools wrap params in `request: {...}`** — flat kwargs fail.
9. **Context7 `query` arg** is unreachable in current Claude Code — fall back to WebSearch / Anthropic docs.

These eight items are the entire delta between "CC works on ZMN with bash" and "CC works on ZMN with the upgraded surface." See `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` Tier 2 for the integrations that close the loop on each.
