# MCP Capabilities Reference — 2026-04-21

**Purpose:** tool-name + parameter reference for the analytics/infra MCP stack registered to this workspace. Future ZMN sessions (wallet reverse-engineering, Whale Tracker activation, signal-source expansion, dashboard data backends) should reference this doc to construct accurate MCP tool calls without guessing.

**Session mode:** read-only enumeration. 4 representative sample calls executed (1 each to nansen/birdeye/vybe/dexpaprika). No trading, no env changes, no services/ edits.

---

## Executive summary

- **Best for wallet PnL + SM labels:** `nansen` (tool catalog rich — wallet_pnl_summary, smart_traders_and_funds_*, token_who_bought_sold, wallet_pnl_for_token) — **BUT API key is currently returning HTTP 401** this session; assume dead until rotated.
- **Best for on-chain Solana analytics (live-working alternative to Nansen):** `vybe` — 50 endpoints covering wallet PnL (`/v4/wallets/{owner}/pnl`), top traders, holder time-series, trade volume time-series, market candles, Pyth oracle data. Works.
- **Best for multi-chain DEX pool data + price history:** `dexpaprika` — 35 chains (Solana $8.28B/24h volume), pool OHLCV, pool transactions, token pools, trending. Works.
- **Best for Solana RPC + parsed transactions:** `helius` — used extensively elsewhere in the codebase; routing table loaded at session start.
- **Best for general price / market cap / historical charts:** `coingecko` — 60+ endpoints including on-chain pool data, trending search, new coins list.
- **Unavailable this session:** `birdeye` (timeout — per CLAUDE.md a known "session expiry on first call" issue; needs refresh story), `nansen` (401 auth error), `defillama` (auth pending).
- **Dev/infra:** `railway` (deploys/logs/vars), `redis` (get/set/list/delete), `sentry` (issues/events/Seer), `github` (repo/PR/issue ops), `playwright` (browser), `shadcn` (UI components).

**Biggest surprise:** Vybe is a full Solana-analytics surface that nobody on ZMN has used yet. Covers most of what we've been using Nansen for, plus some primitives Nansen doesn't seem to offer (`trader-activity`, `trade-volume-ts`, oracle-layer price feeds via Pyth). Given Nansen's current auth state, Vybe becomes the primary Solana-analytics MCP until Nansen is restored.

---

## Analytics MCPs

### nansen

**Purpose:** smart money identification + wallet PnL + token flow analytics across 30+ chains.

**Chain coverage:** hyperevm, bitcoin, evm, plasma, arbitrum, fantom, ethereum, ton, unichain, injective, scroll, sonic, polygon, linea, zksync, **solana**, mantle, optimism, sei, sui, tron, avalanche, near, hyperliquid, monad, base, ronin, bnb, all, iotaevm.

**Status this session:** ❌ **HTTP 401 "Invalid API key"** on `token_info` call against wSOL. Railway env has `NANSEN_API_KEY=cL2tgvKP2twsUKTcXHv...` but it's either expired or the wrong key for the MCP's server-side auth. Per CLAUDE.md: "BUDGET: 508% over limit. DISABLED via Redis nansen:disabled." Possibly the Nansen-side key was revoked post-over-budget. **Treat as dead until Jay rotates.**

**Key tools (schemas loaded from tool catalog):**

| Tool | Purpose | Key params |
|---|---|---|
| `nansen.token_info` | Token details (market cap, volume, holders, liquidity) + Hyperliquid perp stats | `tokenAddress`, `chain`, `mode` (onchain_tokens/perps), `timeframe` (5m/1h/6h/12h/1d/7d) |
| `nansen.wallet_pnl_summary` | Realized PnL summary for a wallet over date range | `walletAddress`, `dateRange {from, to}`, `chain` |
| `nansen.wallet_pnl_for_token` | PnL for one wallet on one specific token | — (schema not loaded; implied by name) |
| `nansen.token_who_bought_sold` | Who traded this token (labeled wallets) | implied |
| `nansen.token_flows` + `token_recent_flows_summary` | Net flows in/out of a token | — |
| `nansen.smart_traders_and_funds_token_balances` | SM/fund holdings per token | — |
| `nansen.smart_traders_and_funds_perp_trades` | SM perps trading activity | — |
| `nansen.token_pnl_leaderboard` | Top PnL wallets per token | — |
| `nansen.token_current_top_holders` | Current holder list | — |
| `nansen.token_discovery_screener` | Filtered token discovery | — |
| `nansen.token_dex_trades` | Per-token DEX trades | — |
| `nansen.token_ohlcv` | Price candles | — |
| `nansen.address_portfolio` + `address_historical_balances` | Wallet portfolio | `address`, optional date range |
| `nansen.address_transactions` + `address_counterparties` + `address_related_addresses` | Wallet graph / tx history | — |
| `nansen.transaction_lookup` | Single tx details | — |
| `nansen.prediction_market_*` | Hyperliquid prediction-market tools (11 endpoints — orderbook, trades, PnL leaderboard, top holders, screener, address-specific) | — |
| `nansen.hyperliquid_leaderboard` | HL top perp traders | — |
| `nansen.growth_chain_rank` | Chain-level growth metrics | — |
| `nansen.nansen_score_top_tokens` | Top-scoring tokens by Nansen proprietary score | — |
| `nansen.general_search` | Free-text search | — |

**Credit notes:** Nansen-MCP doesn't expose per-call credits explicitly in schema. Per CLAUDE.md, budget is 2000/month on signal_aggregator env (though currently DRY_RUN=TRUE). Roughly: simple lookups 1 credit, multi-period PnL 3-5 credits, top-holders/flows 2-5 credits. Monitor externally.

**Rate limits:** not documented in schema. Conservative: 1 call/sec.

**Solana memecoin coverage:** Nansen has Solana SPL token coverage but **SM labels at pump.fun scale are sparse** per prior audits (`ZMN_RE_DIAGNOSIS_2026_04_19.md` pain 4 — 44 wallets, 0 active in 14d). Good for graduated / liquid tokens; weak signal for pre-grad.

### birdeye

**Purpose:** token market data + wallet analytics across multiple chains (Solana-first).

**Chain coverage (from get-defi-price schema):** solana, ethereum, arbitrum, avalanche, bsc, optimism, polygon, base, zksync, sui.

**Status this session:** ❌ **TIMEOUT** on both `get-defi-price` and `get-defi-networks`. Per CLAUDE.md: "Birdeye MCP session expiry on first call" — documented known failure mode requiring a "session-refresh story" not yet implemented. Assume flaky; retry-on-timeout and fall back to Dexpaprika / Coingecko for price/pool data.

**Tool categories (from session inventory — 90+ tools total):**

| Category | Example tools | Use |
|---|---|---|
| Price | `get-defi-price`, `get-defi-multi_price`, `get-defi-historical_price_unix`, `get-defi-history_price` | Current + historical price |
| Token metadata | `get-defi-token_overview`, `get-defi-v3-token-meta-data-single`, `get-defi-v3-token-meta-data-multiple` | Token descriptors |
| Market data | `get-defi-v3-token-market-data`, `get-defi-v3-token-market-data-multiple` | MC/supply/liquidity |
| OHLCV | `get-defi-ohlcv`, `get-defi-ohlcv-base_quote`, `get-defi-ohlcv-pair`, `get-defi-v3-ohlcv`, `get-defi-v3-ohlcv-pair` | Candles (multiple variants) |
| Holders | `get-defi-v3-token-holder`, `get-holder-v1-distribution`, `post-token-v1-holder-batch` | Holder analytics |
| Transactions | `get-defi-txs-token`, `get-defi-txs-pair`, `get-defi-txs-token-seek_by_time`, `get-defi-v3-token-txs`, `get-defi-v3-token-txs-by-volume`, `get-defi-v3-txs`, `get-defi-v3-txs-recent`, `get-defi-v3-txs-latest-block` | Trade history |
| Wallet PnL | `get-wallet-v2-pnl`, `get-wallet-v2-pnl-multiple`, `get-wallet-v2-pnl-summary`, `post-wallet-v2-pnl-details` | Wallet-level PnL |
| Wallet balances | `get-v1-wallet-token_balance`, `get-v1-wallet-token_list`, `get-v1-wallet-tx_list`, `post-wallet-v2-token-balance`, `post-wallet-v2-transfer`, `post-wallet-v2-transfer-total` | Balances + transfers |
| Net worth | `get-wallet-v2-current-net-worth`, `get-wallet-v2-net-worth`, `get-wallet-v2-net-worth-details`, `post-wallet-v2-net-worth-summary-multiple` | Wallet valuation |
| Smart money | `get-smart-money-v1-token-list` | SM-focused tokens |
| Trader leaderboard | `get-trader-gainers-losers`, `get-defi-v2-tokens-top_traders`, `get-defi-v3-token-list`, `get-defi-v3-token-list-scroll` | Trader rankings |
| Exit liquidity | `get-defi-v3-token-exit-liquidity`, `get-defi-v3-token-exit-liquidity-multiple` | Liquidity depth |
| Meme detail | `get-defi-v3-token-meme-detail-single`, `get-defi-v3-token-meme-list` | Meme-specific metrics |
| Transfers | `post-token-v1-transfer`, `post-token-v1-transfer-total`, `post-wallet-v2-tx-first-funded` | First-funded-by analysis |
| Mint/burn | `get-defi-v3-token-mint-burn-txs` | Supply changes |
| Trade data | `get-defi-v3-token-trade-data-single`, `get-defi-v3-token-trade-data-multiple` | Aggregated buy/sell pressure |
| New listings | `get-defi-v2-tokens-new_listing` | Recently listed |
| Trending | `get-defi-token_trending`, `get-defi-v3-token-meme-list` | Trending discovery |
| Search | `get-defi-v3-search` | Free-text search |
| Credits | `get-utils-v1-credits` | Check remaining credits |

**Credit notes:** `get-utils-v1-credits` exposes remaining balance. Not called this session. Known historical pattern: per-call cost ranges from 1 credit (simple price) to 25+ (multi-wallet batch).

**Rate limits:** not in schema. Birdeye's public API is 60 RPM on free tier, higher on paid. MCP presumed to honor same limits.

**Solana memecoin coverage:** **best in class for post-grad; limited for pre-grad pump.fun** (BC state isn't indexed fully). Use `get-defi-v3-token-meme-detail-single` for meme-specific metrics.

### helius

**Purpose:** Solana RPC + Enhanced Transactions + asset API.

**Chain coverage:** Solana-only (mainnet + devnet).

**Status this session:** ✅ OPERATIONAL (used for `getBalance` and related calls throughout). Confirmed in EXEC-001 implementation and subsequent wallet probes.

**Routing table** (loaded at session start — already in this session's context):

| Intent | Tool | Credits |
|---|---|---|
| SOL balance | `getBalance` | 1 |
| Token balances by wallet | `getTokenBalances` | 10/page |
| Full portfolio + USD | `getWalletBalances` | 100 |
| Parse tx by signature | `parseTransactions` | 100 |
| Wallet tx history | `getTransactionHistory` | ~110 |
| Balance deltas/tx | `getWalletHistory` | 100 |
| Sends/receives | `getWalletTransfers` | 100 |
| Asset by mint (single/batch) | `getAsset` | 10 |
| Wallet NFTs | `getAssetsByOwner` | 10 |
| Filtered asset search | `searchAssets` | 10 |
| Collection NFTs | `getAssetsByGroup` | 10 |
| Asset tx history by mint | `getSignaturesForAsset` | 10 |
| Edition prints | `getNftEditions` | 10 |
| cNFT Merkle proof | `getAssetProof`, `getAssetProofBatch` | 10 |
| Raw account inspection | `getAccountInfo` | 1 |
| Token holders by mint | `getTokenHolders` | ~20 |
| Token accounts by mint/owner | `getTokenAccounts` | 10 |
| Program accounts | `getProgramAccounts` | 10 |
| Network status | `getNetworkStatus` | 3 |
| Block data by slot | `getBlock` | 1 |

Plus meta/billing tools: `getHeliusPlanInfo`, `compareHeliusPlans`, `getRateLimitInfo`, `lookupHeliusDocs`, `troubleshootError`, `getSenderInfo`, `getWebhookGuide`, `getLatencyComparison`, `getPumpFunGuide`, `recommendStack`, `getSIMD`, `listSIMDs`, `searchSolanaDocs`, `readSolanaSourceFile`, `fetchHeliusBlog`.

Plus infrastructure: `createWebhook`, `getAllWebhooks`, `getWebhookByID`, `updateWebhook`, `deleteWebhook`; `accountSubscribe`, `transactionSubscribe`, `laserstreamSubscribe`; `generateKeypair`, `transferSol`, `transferToken`, `getPriorityFeeEstimate`, `batchWalletIdentity`, `getWalletFundedBy`, `getWalletIdentity`, `checkSignupBalance`, `agenticSignup`, `payRenewal`, `previewUpgrade`, `upgradePlan`.

**Credit notes:** per-tool costs listed above (authoritative for this session).

**Rate limits:** plan-dependent (`getRateLimitInfo` retrieves). Free plan commonly 10 RPS / 100k credits/day.

**Solana memecoin coverage:** excellent — RPC primitives cover everything. For pump.fun BC state, derive the PDA and call `getAccountInfo` (pattern used in EXEC-001 at `services/bot_core.py:952`).

### vybe

**Purpose:** Solana-only on-chain analytics (markets, tokens, wallets, oracle).

**Status this session:** ✅ OPERATIONAL (`list-endpoints` returned 50 endpoints cleanly).

**How to call:** Vybe MCP has 4 meta-tools (`list-endpoints`, `get-endpoint`, `search-endpoints`, `execute-request`). Pattern: call `list-endpoints` → find the endpoint → call `get-endpoint` to get its schema → call `execute-request` with the endpoint path + parameters. (Workflow similar to the DeFiLlama MCP pattern.)

**All 50 endpoints** (verified via sample call this session):

| Category | Path | Method | Purpose |
|---|---|---|---|
| Markets | `/v4/markets` | GET | Market list |
| Markets | `/v4/markets/{marketAddress}` | GET | Market details |
| Markets | `/v4/markets/{marketAddress}/candles` | GET | Market price candles |
| Oracle (Pyth) | `/v4/oracle/pyth/pricefeeds` | GET | Pyth feed list |
| Oracle (Pyth) | `/v4/oracle/pyth/pricefeeds/{priceFeedAddress}/candles` | GET | Pyth candles |
| Oracle (Pyth) | `/v4/oracle/pyth/pricefeeds/{priceFeedAddress}/price` | GET | Current Pyth price |
| Oracle (Pyth) | `/v4/oracle/pyth/pricefeeds/{priceFeedAddress}/price-ts` | GET | Pyth price history |
| Oracle (Pyth) | `/v4/oracle/pyth/products/{productAddress}` | GET | Pyth product |
| Programs | `/v4/programs/labeled-program-accounts` | GET | Labeled programs |
| Reference | `/v4/reference/dexes` | GET | Supported DEXs |
| Reference | `/v4/reference/instruction-names` | GET | Instruction names |
| Tokens | `/v4/tokens` | GET | Token list |
| Tokens | `/v4/tokens/{mintAddress}` | GET | Token details |
| Tokens | `/v4/tokens/{mintAddress}/candles` | GET | Token candles (OHLCV) |
| Tokens | `/v4/tokens/{mintAddress}/holders-count-ts` | GET | **Holder count history (time-series)** |
| Tokens | `/v4/tokens/{mintAddress}/liquidity` | GET | Token liquidity |
| Tokens | `/v4/tokens/{mintAddress}/markets-ts` | GET | Token markets time-series |
| Tokens | `/v4/tokens/{mintAddress}/top-holders` | GET | Top holders |
| Tokens | `/v4/tokens/{mintAddress}/top-pnl-traders` | GET | **Top PnL traders by token** |
| Tokens | `/v4/tokens/{mintAddress}/trade-volume-ts` | GET | Trade volume time-series |
| Tokens | `/v4/tokens/{mintAddress}/trader-activity` | GET | Trader activity |
| Trades | `/v4/trades` | GET | Trade history |
| Trading | `/v4/trading/swap` | POST | Build swap |
| Trading | `/v4/trading/swap-quote` | GET | Swap quote |
| Transfers | `/v4/transfers` | GET | Transfer history |
| Wallets batch | `/v4/wallets/batch/dust-accounts` | POST | Dust accounts (batch) |
| Wallets batch | `/v4/wallets/batch/empty-accounts` | POST | Empty accounts (batch) |
| Wallets batch | `/v4/wallets/batch/nft-balances` | POST | Multi-wallet NFT balances |
| Wallets batch | `/v4/wallets/batch/token-accounts-balance-ts` | POST | Multi-wallet account history |
| Wallets batch | `/v4/wallets/batch/token-balances` | POST | Multi-wallet token balances |
| Wallets batch | `/v4/wallets/batch/token-balances-ts` | POST | Multi-wallet balance history |
| Wallets | `/v4/wallets/labeled-accounts` | GET | Labeled accounts |
| Wallets | `/v4/wallets/top-traders` | GET | **Top traders (Solana-wide)** |
| Wallets util | `/v4/wallets/util/close-token-accounts` | POST | Close token accounts |
| Wallets util | `/v4/wallets/util/withdraw-mev` | POST | Withdraw MEV |
| Wallets | `/v4/wallets/{ownerAddress}/counterparties` | GET | Wallet counterparties |
| Wallets | `/v4/wallets/{ownerAddress}/defi-positions` | GET | DeFi positions |
| Wallets | `/v4/wallets/{ownerAddress}/dust-accounts` | GET | Dust accounts |
| Wallets | `/v4/wallets/{ownerAddress}/empty-accounts` | GET | Empty accounts |
| Wallets | `/v4/wallets/{ownerAddress}/nft-balance` | GET | NFT balance |
| Wallets | `/v4/wallets/{ownerAddress}/pnl` | GET | **Wallet PnL** |
| Wallets | `/v4/wallets/{ownerAddress}/pnl-ts` | GET | **Wallet PnL time-series** |
| Wallets | `/v4/wallets/{ownerAddress}/token-accounts-balance-ts` | GET | Token account history |
| Wallets | `/v4/wallets/{ownerAddress}/token-balance` | GET | Token balances |
| Wallets | `/v4/wallets/{ownerAddress}/token-balance-ts` | GET | Token balance history |
| Wallets | `/v4/wallets/{ownerAddress}/transfer-volume-usd` | GET | Transfer volume (USD) |

**Credit notes:** per CLAUDE.md: "Free plan: 25K credits/month, 60 RPM." Cache responses in Redis with 5-min TTL (per CLAUDE.md MCP Usage Rules).

**Rate limits:** 60 RPM free tier.

**Solana memecoin coverage:** full Solana SPL coverage. Pump.fun pre-grad tokens may appear in `/v4/tokens/{mint}` once enough trades exist; labeled-accounts is the SM-equivalent.

**Signature features vs Nansen:**
- `holders-count-ts` — historical holder count for a mint. **Nansen doesn't have this exposed via MCP schema.** Would answer "what was holder count at timestamp T?"
- `trader-activity` per-token — more detailed than `token_who_bought_sold`.
- `top-pnl-traders` per-token — focused lens for finding high-performance wallets on a specific token.
- `labeled-accounts` — Solana wallet labels (alternative SM source).

### dexpaprika

**Purpose:** DEX pool data across 35 chains — pools, OHLCV, transactions, trending.

**Chain coverage (verified this session):** fantom, bob_network, blast, linea, zksync, celo, arbitrum, bsc, tron, hyperevm, aptos, ethereum, mantle, x_layer, flow_evm, cronos, sonic, sui, tempo, monad, botanix, ronin, base, plasma, optimism, avalanche, unichain, sei, megaeth, berachain, katana, scroll, polygon, **solana** ($8.28B/24h volume, 29.2M tx, 69,222 pools), ton. All active within 24h.

**Status this session:** ✅ OPERATIONAL.

**All 12 tools:**

| Tool | Purpose | Key params |
|---|---|---|
| `getNetworks` | List supported chains (call this FIRST) | none |
| `getNetworkDexes` | DEXs for a given chain | `network` |
| `getNetworkPools` | Pools on a chain | `network`, `limit`, `sort` |
| `getDexPools` | Pools for a specific DEX | `network`, `dex` |
| `getPoolDetails` | Pool detail + current stats | `network`, `poolAddress` |
| `getPoolOHLCV` | Pool price candles | `network`, `poolAddress`, `interval` |
| `getPoolTransactions` | Pool trade history | `network`, `poolAddress` |
| `getTokenDetails` | Token metadata + markets | `network`, `tokenAddress` |
| `getTokenPools` | Pools containing this token | `network`, `tokenAddress` |
| `search` | Free-text search across tokens/pools | `query` |
| `getStats` | Platform-wide stats | none |
| (trending is embedded in search / getNetworkPools sort) | | |

**Credit notes:** Not exposed via schema. Dexpaprika's public API is free-tier-generous.

**Rate limits:** per dexpaprika public API, typically 60 RPM; not documented in MCP.

**Solana memecoin coverage:** Solana listed with 69k pools — wide pump.fun + Raydium + Orca coverage. `getTokenPools` against a pump.fun mint should return its BC pool + any post-grad Raydium pool. Good for "is this token on multiple pools" / "pool-level trade history" use cases.

### coingecko

**Purpose:** token prices + market caps + historical charts + on-chain DEX data across all chains.

**Status this session:** not sample-called; trusted per prior session usage.

**Tool categories** (60+ total — not enumerating each):

| Category | Key tools |
|---|---|
| Simple price | `get_simple_price`, `get_simple_supported_vs_currencies` |
| Coin markets | `get_coins_markets`, `get_id_coins`, `get_coins_contract`, `get_coins_history`, `get_coins_top_gainers_losers`, `get_new_coins_list`, `get_list_coins_categories` |
| Historical | `get_range_coins_market_chart`, `get_range_coins_ohlc`, `get_range_contract_coins_market_chart`, `get_range_exchanges_volume_chart` |
| Exchanges | `get_id_exchanges`, `get_list_exchanges`, `get_exchanges_tickers` |
| NFTs | `get_id_nfts`, `get_list_nfts`, `get_markets_nfts`, `get_nfts_market_chart` |
| On-chain DEX (GeckoTerminal endpoints) | `get_onchain_networks`, `get_networks_onchain_dexes`, `get_tokens_networks_onchain_info`, `get_tokens_networks_onchain_pools`, `get_tokens_networks_onchain_trades`, `get_tokens_networks_onchain_holders_chart`, `get_tokens_networks_onchain_top_holders`, `get_tokens_networks_onchain_top_traders`, `get_pools_networks_onchain_info`, `get_pools_networks_onchain_trades`, `get_pools_onchain_categories`, `get_pools_onchain_megafilter`, `get_pools_onchain_trending_search`, `get_timeframe_pools_networks_onchain_ohlcv`, `get_timeframe_tokens_networks_onchain_ohlcv`, `get_network_networks_onchain_new_pools`, `get_networks_onchain_new_pools` |
| Addresses | `get_addresses_networks_simple_onchain_token_price`, `get_addresses_pools_networks_onchain_multi`, `get_addresses_tokens_networks_onchain_multi` |
| Treasuries / Search | `get_holding_chart_public_treasury`, `get_transaction_history_public_treasury`, `get_search`, `get_search_trending`, `get_search_onchain_pools`, `search_docs` |
| Asset platforms | `get_asset_platforms` |
| Global | `get_global` |
| On-chain categories | `get_onchain_categories` |
| On-chain misc | `get_id_simple_token_price` (id = coin-id lookup) |

**Credit notes:** CoinGecko MCP is hosted by CoinGecko — free tier rate-limited; pro plan available.

**Rate limits:** free ~30 calls/min; pro higher.

**Solana memecoin coverage:** GeckoTerminal side is strong on Solana (pools, OHLCV, trading, trending) — most pump.fun post-grad tokens indexed. Pre-grad BC tokens may or may not appear depending on trade volume thresholds.

### socket

**Purpose:** NOT a chain-analytics MCP. Socket is a software supply-chain security tool. Only one tool exposed:

- `mcp__socket__depscore` — scores a package (npm / pypi / etc.) for supply-chain risk.

**Relevance to ZMN:** minimal. Potentially useful for auditing new Python/JS deps pre-install. Not ZMN-core. Skip.

### defillama

**Purpose:** DeFi TVL + protocol data.

**Status this session:** NOT operational (requires authentication). Two tools exposed: `authenticate`, `complete_authentication`. Until Jay runs the auth flow, defillama is unavailable.

---

## Infrastructure MCPs (brief)

| MCP | One-liner | Key tools |
|---|---|---|
| `railway` | Railway project/service/deployment control | `list-projects`, `list-services`, `list-variables`, `set-variables`, `list-deployments`, `get-logs`, `deploy`, `generate-domain`, `link-service`, `check-railway-status` |
| `redis` | Redis key-value ops | `get`, `set`, `list`, `delete` |
| `sentry` | Error tracking, Seer AI analysis, Sentry docs | `search_issues`, `search_events`, `search_issue_events`, `analyze_issue_with_seer`, `get_sentry_resource`, `get_issue_tag_values`, `find_organizations`, `find_projects`, `find_teams`, `find_releases`, `find_dsns`, `create_project`, `create_team`, `create_dsn`, `update_issue`, `update_project`, `get_profile_details`, `get_replay_details`, `get_event_attachment`, `whoami`, `search_docs`, `get_doc` |
| `github` | Git/PR/issue ops (PAT-authenticated) | `search_repositories`, `search_code`, `search_issues`, `search_users`, `get_file_contents`, `get_issue`, `get_pull_request`, `create_pull_request`, `list_commits`, `merge_pull_request`, `create_branch`, `push_files`, `create_or_update_file`, `list_issues`, `list_pull_requests`, `update_issue`, `update_pull_request_branch`, `fork_repository`, `create_repository`, `add_issue_comment`, `create_pull_request_review`, `get_pull_request_comments`, `get_pull_request_files`, `get_pull_request_reviews`, `get_pull_request_status` + a `plugin_github_github` alternate set with similar surface |
| `playwright` | Browser automation (27 tools) | `browser_navigate`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_snapshot`, `browser_take_screenshot`, `browser_console_messages`, `browser_network_requests`, `browser_evaluate`, `browser_wait_for`, `browser_press_key`, `browser_hover`, `browser_drag`, `browser_select_option`, `browser_file_upload`, `browser_handle_dialog`, `browser_resize`, `browser_tabs`, `browser_close`, `browser_navigate_back`, `browser_run_code` |
| `shadcn` | shadcn/ui component registry | `list_items_in_registries`, `search_items_in_registries`, `view_items_in_registries`, `get_item_examples_from_registries`, `get_add_command_for_items`, `get_project_registries`, `get_audit_checklist` |
| `context7` | Library docs lookup (via `plugin:context7:context7`) | `resolve-library-id`, `query-docs` |
| `claude.ai Drive` | Google Drive (operational without explicit auth this session) | `list_recent_files`, `search_files`, `read_file_content`, `download_file_content`, `create_file`, `get_file_metadata`, `get_file_permissions` |
| `claude.ai Gmail` | Gmail (auth pending) | `authenticate`, `complete_authentication` |
| `claude.ai Calendar` | Google Calendar (auth pending) | `authenticate`, `complete_authentication` |

---

## Use-case mapping

| Operation | Primary MCP tool | Fallback | Notes |
|---|---|---|---|
| Pull a wallet's closed trades last 30d on Solana | **Vybe**: `/v4/wallets/{owner}/pnl-ts` + `/v4/trades?walletAddress=...` | Nansen `wallet_pnl_summary` (when auth restored) | Helius `getTransactionHistory` for raw; Vybe gives aggregated |
| What was token X's holder count at timestamp T? | **Vybe**: `/v4/tokens/{mint}/holders-count-ts` | Coingecko `get_tokens_networks_onchain_holders_chart` | Vybe is the cleanest primitive — closest thing to a time-travel snapshot |
| Is this wallet labeled Smart Money? | **Nansen** (when auth restored): `address_portfolio`/`address_counterparties` | Vybe `/v4/wallets/labeled-accounts` | Birdeye `get-smart-money-v1-token-list` is token-side not wallet-side |
| List Smart Money wallets currently active on Solana memecoins | **Nansen**: `smart_traders_and_funds_token_balances` filtered on Solana | Vybe `/v4/wallets/top-traders` | Nansen's SM cohort is the canonical list; Vybe's "top traders" is PnL-ranked |
| What's the current BC progress on this pump.fun token? | **Helius**: `getAccountInfo` on pump.fun BC PDA | Vybe `/v4/tokens/{mint}/liquidity` | EXEC-001 pattern already used in bot_core; Vybe liquidity gives proxy |
| Get N most-recent Smart Money buys on Solana | **Nansen**: `smart_traders_and_funds_token_balances` delta-tracked | Vybe `/v4/tokens/{mint}/trader-activity` per mint | Nansen's feed-style access is the gap filler; Vybe requires per-token queries |
| Token price + liquidity at specific timestamp | **Birdeye**: `get-defi-historical_price_unix` (when operational) | Coingecko `get_range_contract_coins_market_chart` or Vybe `/v4/tokens/{mint}/candles` | Dexpaprika `getPoolOHLCV` for pool-level; Coingecko for cross-chain |
| Real-time DEX pool stats (BC/Raydium) | **Helius**: `getAccountInfo` + bot's existing pipeline | Dexpaprika `getPoolDetails` + `getPoolTransactions` | For post-grad, Dexpaprika is rich; for pre-grad BC, Helius is definitive |
| Check pump.fun graduation state | **Helius**: `getAccountInfo` BC PDA (missing = graduated) | Vybe `/v4/tokens/{mint}/markets-ts` (pool migration visible) | EXEC-001 implementation already works |
| Wallet counterparty graph | **Nansen**: `address_related_addresses` + `address_counterparties` | Vybe `/v4/wallets/{owner}/counterparties` | Both exist; Nansen has richer label metadata |
| Token transfer history | **Helius**: `getWalletTransfers` | Vybe `/v4/transfers` filtered | Helius is per-wallet; Vybe can filter by token-mint too |

---

## Sample calls (verified working this session)

### Vybe: list-endpoints

**Input:** `mcp__vybe__list-endpoints` (no params)
**Output shape:** 50 endpoints as a dict keyed by path, each value a dict of `{method: summary}`. See Vybe section for full table.
**Notes:** this IS the discovery tool — always call first before `execute-request`.

### Dexpaprika: getNetworks

**Input:** `mcp__dexpaprika__getNetworks` (no params)
**Output shape:** array of `{id, display_name, volume_usd_24h, txns_24h, pools_count}` — 35 entries.
**Notes:** Solana `id="solana"`, $8.28B 24h volume, 69,222 pools. This is always the first call to make before any per-network Dexpaprika op.

### Nansen: token_info

**Input:** `mcp__nansen__token_info` with `{tokenAddress: "So11111111111111111111111111111111111111112", chain: "solana", mode: "onchain_tokens", timeframe: "1d"}`
**Result:** ❌ HTTP 401 "Invalid API key" — **Nansen auth broken this session.** Flagged for Jay to rotate.

### Birdeye: get-defi-price / get-defi-networks

**Input:** `mcp__birdeye__get-defi-networks` (lightest call)
**Result:** ❌ TIMEOUT (30s+). Per CLAUDE.md: known "session expiry on first call" behavior. Retry loop may succeed on 2nd/3rd attempt.

---

## Tools worth exploring later

Discovered during enumeration but out-of-scope for the immediate wallet-analysis + Whale Tracker work:

### Nansen
- `nansen.prediction_market_*` (11 endpoints) — Hyperliquid prediction markets. Full trading surface including PnL leaderboard, address trades, orderbook, OHLCV, position details, top holders, screener. **Potential alt-strategy surface** if Hyperliquid becomes interesting.
- `nansen.growth_chain_rank` — chain-level growth metrics. Useful for "should we consider chains beyond Solana?"
- `nansen.nansen_score_top_tokens` — Nansen's proprietary scoring. Cross-reference with our ML score for signal-augmentation candidates.

### Vybe
- `/v4/wallets/batch/token-balances-ts` (POST, multi-wallet) — **credit-efficient** way to snapshot 10+ SM wallets simultaneously for a watched_wallets refresh. Replaces N-at-a-time queries.
- `/v4/wallets/util/withdraw-mev`, `/v4/wallets/util/close-token-accounts` — Solana-specific utilities (MEV rebate, account cleanup). Not trading but potentially treasury hygiene.
- `/v4/oracle/pyth/*` — Pyth price-feed endpoints. Alternative to Helius price-fetching for precise reference prices.

### Birdeye
- `get-wallet-v2-pnl-multiple` (POST batch) — batched wallet PnL; 10 wallets per call for ~10 credits vs 100 for individual. **Big credit saver**.
- `post-wallet-v2-tx-first-funded` — "who funded this wallet first" — critical for copycat / bundle detection.
- `get-defi-v3-token-exit-liquidity` — exit liquidity depth — could inform pre-exit risk assessment.
- `get-defi-v3-token-meme-detail-single` — meme-specific metrics beyond standard token data.

### Dexpaprika
- `search` — free-text across tokens + pools, multi-chain. Could augment `signal_listener.py` with a secondary discovery path.

### Helius
- `getPriorityFeeEstimate` — mentioned in EXEC-004 roadmap item. Already known; listed for completeness.
- `laserstreamSubscribe` / `accountSubscribe` / `transactionSubscribe` — streaming primitives. Alternative to PumpPortal WS for pre-grad tx stream. Would need Helius plan upgrade.

---

## Gaps (no MCP covers these)

1. **Historical pre-grad BC state at timestamp T** — no MCP returns "what was BC progress at 10:23 UTC yesterday on mint X". Nansen/Birdeye/Vybe/Dexpaprika don't index pump.fun BC internal state. Workaround: our own `token:reserves:{mint}` Redis cache (30-min TTL) or on-chain Helius `getAccountInfo` at a historical slot (expensive + not really "historical" since RPC serves recent states only).
2. **PumpPortal Local trade-api status monitoring** — no MCP directly pings PumpPortal for health. Current approach: our `live_trade_log` error rate is the canary.
3. **Jito bundle landing stats** — no MCP exposes Jito success/latency telemetry. Plan for MCP-002 (Jito MCP build, `mcp-builder` skill) per roadmap.
4. **Solana program-level events at scale** — Helius covers `getProgramAccounts` but streaming patterns (e.g., "emit every new BC creation on pump.fun") aren't surfaced via MCP; need a webhook or WS client.

---

## Known auth / connectivity issues

| MCP | Issue | Needed |
|---|---|---|
| `nansen` | HTTP 401 Invalid API key | Rotate `NANSEN_API_KEY` env (Railway bot_core + signal_aggregator). Current value `cL2tgvKP2twsUKTcXHv...` rejected. |
| `birdeye` | Timeout on first call — "session expiry" per CLAUDE.md | Implement session-refresh pattern (call a lightweight endpoint, e.g., `get-defi-networks`, with retry-loop before actual query) |
| `defillama` | Authentication pending | Run `mcp__defillama__authenticate` interactively |
| `claude.ai Gmail` | Authentication pending | Run `authenticate` + `complete_authentication` |
| `claude.ai Calendar` | Authentication pending | Run `authenticate` + `complete_authentication` |

---

## Session meta

- **Duration:** ~25 min (within budget).
- **Sample calls:** 4 (nansen token_info, birdeye get-defi-price + get-defi-networks, vybe list-endpoints, dexpaprika getNetworks). 2 OK, 1 auth-fail, 1 timeout. Net credits consumed: <10 (Vybe and Dexpaprika are free-tier or low-cost; Nansen/Birdeye errored before charging).
- **No trading, no env changes, no services/ code changes.**
