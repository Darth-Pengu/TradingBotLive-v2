# Smart Money Diagnostic — 2026-04-12 AEDT

## TL;DR

- **Nansen MCP: WORKING — but smart money labels don't exist at pump.fun micro-cap scale**
- Nansen `token_who_bought_sold`: returns buyers with labels (deployer, bot user) — but NOT "Smart Trader" or "Fund" labels for micro-cap tokens
- Wallet PnL history: **EMPTY for micro-cap wallets** — profiler doesn't track them
- SM screener at $10k-$5M: **EMPTY** — smart money doesn't operate here
- SM screener at $100k+: **WORKS** — 25 established memecoins with volume/trader data
- PnL leaderboard for pump.fun tokens: **EMPTY** — below tracking threshold
- Top holders for pump.fun tokens: **EMPTY** — below Nansen indexing threshold
- Helius credits: **EXHAUSTED** (reset April 26). Treasury guard working.
- Last webhook: **CONFIRMED DISABLED**
- Smart money build path: **PARTIALLY FEASIBLE** — wallet curation possible via Nansen on established tokens, but live monitoring of micro-cap pump.fun entries requires Helius webhooks (blocked until Apr 26)

---

## Phase 1 — Nansen Current State

### Configuration

| Service | NANSEN_DRY_RUN | NANSEN_DAILY_BUDGET | NANSEN_API_KEY |
|---------|---------------|---------------------|---------------|
| signal_aggregator | **TRUE** (explicit) | 2000 | Present |
| signal_listener | **TRUE** (explicit) | 2000 | Present |
| ml_engine | (default true) | 2000 | Present |
| bot_core | (default true) | 50 | Present |
| treasury | (default true) | 50 | Present |

### Redis State

| Key | Value |
|-----|-------|
| nansen:emergency_stop | nil |
| nansen:disabled | nil (expired) |
| nansen:circuit_breaker | nil |
| nansen:call_log | empty (dry-run mode, no real calls logged) |

### Code Integration Map

| Location | Type | Description |
|----------|------|-------------|
| signal_aggregator.py:601 | CALLER | `_fetch_nansen_enrichment()` — calls flow_summary, labeled_holders, smart_money_buyers per signal. **Gated by DRY_RUN** |
| signal_aggregator.py:612-658 | HANDLER | Parses Nansen responses into ML features (nansen_sm_count, nansen_sm_inflow_ratio, etc.) |
| signal_aggregator.py:1823-1827 | FEATURE | 6 Nansen-derived ML features in features_json (all default 0 while dry-run) |
| bot_core.py:1484 | CALLER | `_nansen_exit_monitor()` — polls SM DEX sells for open positions. **Gated by DRY_RUN** |
| bot_core.py:1549-1578 | CALLER | `_check_nansen_accumulation()` — checks SM accumulation trend for analyst personality entry |
| governance.py:552-575 | CALLER | Uses Nansen MCP server for weekly meta-reports + wallet scoring |
| dashboard_api.py:1221 | CALLER | Imports `nansen_wallet_fetcher.get_active_wallets` for whale dashboard |
| dashboard_api.py:2223 | HANDLER | `/api/nansen-usage` — credit usage + safeguard status dashboard |
| nansen_wallet_fetcher.py | CALLER | Fetches, scores, upserts whale wallets to PostgreSQL `watched_wallets` |
| db.py:187 | SCHEMA | `watched_wallets` table — has `nansen_labels TEXT[]`, `source` defaults to 'nansen' |

### nansen_client.py Method Inventory (13 public methods)

| Method | Endpoint | Cache TTL | Used by | Status |
|--------|----------|-----------|---------|--------|
| `get_wallet_pnl` | `/profiler/address/pnl-summary` | 6hr | wallet_fetcher | ACTIVE (dry-run) |
| `get_smart_money_buyers` | `/tgm/who-bought-sold` (BUY) | none | signal_aggregator | ACTIVE (dry-run) |
| `get_smart_money_sellers` | `/tgm/who-bought-sold` (SELL) | none | - | UNUSED |
| `screen_new_tokens` | `/token-screener` | none | - | UNUSED |
| `get_smart_money_holdings` | `/smart-money/holdings` | none | governance | ACTIVE (dry-run) |
| `get_token_flow_summary` | `/tgm/token-recent-flows-summary` | 5min | signal_aggregator | ACTIVE (dry-run) |
| `get_token_quant_scores` | - | - | - | UNUSED |
| `get_labeled_top_holders` | `/tgm/token-current-top-holders` | 15min | signal_aggregator | ACTIVE (dry-run) |
| `get_smart_money_discovery` | `/smart-money/token-balances` | none | - | UNUSED |
| `get_nansen_top_tokens` | `/nansen-scores/top-tokens` | none | governance | ACTIVE (dry-run) |
| `get_whale_portfolio` | `/address/portfolio` | 6hr | governance | ACTIVE (dry-run) |
| `get_token_flows_granular` | custom | - | bot_core | ACTIVE (dry-run) |
| `get_token_pnl_leaderboard` | `/tgm/token-pnl-leaderboard` | none | governance | ACTIVE (dry-run) |
| `get_smart_money_dex_sells` | `/tgm/token-dex-trades` | per-mint | bot_core exit monitor | ACTIVE (dry-run) |

---

## Phase 2 — Nansen Capability Test Results

### Test calls on DS3m72L2tmYX (+319% winner, pump.fun token)

| # | Endpoint | Status | Result |
|---|----------|--------|--------|
| 1 | `token_who_bought_sold` (all buyers) | 200 | **24 buyers** with labels: deployer tags, "GMGN Trading Bot User". NO smart money labels. |
| 2 | `token_pnl_leaderboard` | 200 | **EMPTY** — no PnL data for this micro-cap token |
| 3 | `token_current_top_holders` | 200 | **EMPTY** — Nansen doesn't index holders for pump.fun tokens |
| 4 | `token_discovery_screener` (SM filter, $10k-$5M) | 200 | **EMPTY** — zero SM activity at this market cap |
| 5 | `wallet_pnl_summary` (GMGN bot user, 30d) | 200 | **EMPTY** — 0 PnL, 0 trades. Profiler doesn't track this wallet |
| 6 | `token_who_bought_sold` (SM label filter) | 200 | **EMPTY** — zero smart money bought this winning token |
| 7 | `token_discovery_screener` (no SM filter, $100k+) | 200 | **25 memecoins** with volume, traders, mcap data. Works at larger scale |

### Capability Matrix

| Need | Endpoint | Available | Quality | Notes |
|------|----------|-----------|---------|-------|
| Identify who bought a token | `token_who_bought_sold` | **YES** | Labels: deployer, bot user. No SM labels at micro-cap. | Works for all tokens. Labels are generic at pump.fun scale. |
| Get wallet labels (SM/fund/whale) | via `who_bought_sold` | **PARTIAL** | SM labels only appear on $100k+ tokens | Labels ARE rich for established tokens (fund, smart trader) |
| Wallet historical PnL | `wallet_pnl_summary` | **NO** | Empty for micro-cap wallets | Only works for wallets Nansen tracks (likely $1M+ portfolio) |
| Real-time SM token screener | `token_discovery_screener` | **YES at $100k+** | Good: volume, traders, mcap, age, inflow | Empty with SM filter at micro-cap. Works without SM filter. |
| Top holder concentration | `token_current_top_holders` | **NO** | Empty for pump.fun tokens | Works for established tokens only |
| Real-time wallet alerts | None | **NO** | N/A | Nansen has no push/webhook mechanism |
| SM DEX trades on a token | `token_dex_trades` (via client) | **LIKELY YES** | SM sells for exit monitoring | Not tested via MCP; client code exists and is wired |

### What IS available and valuable

1. **`token_who_bought_sold` (unfiltered):** Returns 25+ buyer wallets with labels for ANY Solana token, even micro-cap. Labels include bot identity (GMGN, BloomBot), deployer history, and sometimes entity labels. This is the best data source for identifying serial pump.fun traders.

2. **`token_discovery_screener` at $100k+ mcap:** Works well for finding trending memecoins with high trader count, volume, and price movement. Could feed the Analyst personality with higher-quality token candidates.

3. **Nansen wallet labels in `who_bought_sold`:** Even without "Smart Trader" labels, the deployer labels are useful: "FCANCER Token Deployer", "GENESIS Token Deployer" etc. This identifies serial token creators who are buying other tokens — which is ANTI-signal (degenerate/sybil behavior).

### What's NOT in Nansen (gaps)

1. **No SM labels at pump.fun micro-cap scale.** Nansen's "30D Smart Trader", "Fund", "All Time Smart Trader" labels don't appear on tokens below ~$100k mcap.
2. **No wallet PnL for micro-cap traders.** The profiler doesn't track wallets that only trade pump.fun tokens.
3. **No holder data for pump.fun tokens.** `token_current_top_holders` returns empty.
4. **No push/webhook mechanism.** All monitoring requires polling.
5. **No win rate / track record for individual wallets** at the micro-cap scale.

---

## Phase 3 — Helius Health

### getBalance test
- HTTP: **429** — "max usage reached"
- Latency: 104ms
- Credits: EXHAUSTED. Reset April 26.

### Budget enforcement

| Service | Checks HELIUS_DAILY_BUDGET? | Call gated? |
|---------|---------------------------|-------------|
| treasury.py | **YES** (line 60, from API audit fix) | YES — returns None immediately |
| dashboard_api.py | Display only (line 2314) | NO — still makes getBalance calls |
| signal_aggregator.py | NO | Gated by HELIUS_ENRICHMENT_ENABLED=false instead |
| bot_core.py | NO | Nansen exit monitor has own budget gate; Helius calls have none |
| market_health.py | NO | getPriorityFeeEstimate has no budget check |
| execution.py | NO | TEST_MODE prevents most calls |

### Treasury spam status

**FIXED.** Treasury logs show "Could not fetch trading wallet balance" (budget guard returning None) instead of "getBalance failed on all Helius endpoints" (HTTP calls failing). No Helius HTTP calls being made from treasury. Warning is expected — treasury can't get balance data when Helius is disabled.

### Webhook status

**CONFIRMED DISABLED.** Zero `/helius-webhook` POST requests in web service logs. Jay's manual disable via Helius dashboard was effective.

---

## Phase 4 — Smart Money Architecture Recommendation

### 4.1 — Wallet curation path

**The core problem:** Jay's vision requires 20-40 consistently profitable whale wallets. Nansen can't identify these at the pump.fun micro-cap scale because:
- SM labels don't exist at this market cap
- Wallet profiler doesn't track micro-cap-only traders
- PnL leaderboard returns empty for pump.fun tokens

**What CAN work:**

**Option A — Build-your-own whale list (RECOMMENDED)**
1. Use `token_who_bought_sold` on the bot's own winning trades (28 winners with 15.8% WR)
2. For each winner: get the list of wallets that bought early
3. Cross-reference: find wallets that appear on MULTIPLE winners
4. A wallet that bought 3+ of the bot's 28 winners is a candidate whale
5. Verify manually or via on-chain PnL (Helius when available)

This is a **data mining approach** using the bot's own trade history as ground truth. No Nansen SM labels needed.

**Option B — Nansen for $100k+ tokens, manual for micro-cap**
Use Nansen `token_discovery_screener` to find established memecoins where SM labels DO appear. Track those wallets' activity on pump.fun via Helius (after credit reset). Hybrid approach.

**Recommendation: Option A first, then layer Option B.** The bot has 28 winning trades — enough data to find repeating early buyers.

### 4.2 — Wallet monitoring path

**Next 14 days (before Helius reset):**
- **Nansen polling background job** — poll `token_who_bought_sold` for each new PumpPortal signal, checking if any of the 20-40 curated wallets appear as buyers
- Cost: 1 Nansen call per signal × ~500 signals/hr = **too expensive** (12k calls/day)
- **Better: Redis lookup.** Maintain a Redis set of watched wallet addresses. When `token_who_bought_sold` returns buyers (already called in `_fetch_nansen_enrichment`), check if any buyer is in the watched set
- Cost: 0 additional Nansen calls (piggybacks on existing enrichment flow)
- **Caveat:** Requires NANSEN_DRY_RUN=false on signal_aggregator

**After April 26 (Helius reset):**
- **Helius webhooks on curated wallets** (NOT Raydium infra addresses)
- Configure webhook for 20-40 specific wallet addresses
- Events: SWAP only (not all 8 event types)
- Each wallet swap → update Redis counter: `sm:buys:{mint}` INCR + EXPIRE 300s
- At signal evaluation time: `sm_buy_count = GET sm:buys:{mint}`
- Estimated cost: ~500 webhook events/day (20 wallets × ~25 trades/day each)

**Recommendation: Redis lookup via existing Nansen flow (now) + Helius webhooks (after April 26).**

### 4.3 — Trade-time evaluation path

**Recommended approach: Redis counter checked at signal evaluation time**

```
Signal arrives → [existing enrichment] → nansen who_bought_sold →
  check each buyer against Redis SET "sm:watched_wallets" →
  count matches → store as features["sm_buy_count"]

Entry rule: if sm_buy_count >= 3, boost confidence by +30
```

This piggybacks on the EXISTING `_fetch_nansen_enrichment` flow. No new API calls. Just a Redis SET membership check per buyer address (~24 checks per signal, sub-millisecond).

### 4.4 — Build Sequence

| Step | What | Blocker | When |
|------|------|---------|------|
| 1 | **Mine winning trades for repeating wallets** | None | Tomorrow |
| 2 | **Curate 20-40 wallets into `watched_wallets` table** | Step 1 data | Tomorrow |
| 3 | **Enable Nansen on signal_aggregator** (DRY_RUN=false, budget=200/day) | Jay approval | This week |
| 4 | **Add Redis SET lookup in `_fetch_nansen_enrichment`** | Step 2 + Step 3 | This week |
| 5 | **Add hardcoded entry rule: sm_buy_count >= 3 → confidence boost** | Step 4 | This week |
| 6 | **Configure Helius webhooks on curated wallets** | Helius credit reset (Apr 26) | Apr 26+ |
| 7 | **Switch from Nansen polling to Helius webhook-driven counters** | Step 6 | Apr 26+ |

Steps 1-2 can start **immediately** with zero API costs (uses existing DB data).
Steps 3-5 require Nansen enablement (~200 calls/day, within 2000 budget).
Steps 6-7 require Helius credit reset (April 26).

---

## Decisions Required From Jay

### Decision 1: Enable Nansen for live use?

- Current: DRY_RUN=true on all services
- Safeguards: All 8 layers confirmed active
- Risk: Low (budget=2000/day, circuit breaker, kill switch)
- **Recommendation: YES — enable on signal_aggregator only, budget=200/day initially**
  ```
  railway variables --set "NANSEN_DRY_RUN=false" -s signal_aggregator
  railway variables --set "NANSEN_DAILY_BUDGET=200" -s signal_aggregator
  ```
- Monitor via `/api/nansen-usage` dashboard panel and `nansen:call_log` Redis list
- Keep DRY_RUN=true on all other services

### Decision 2: Wallet curation strategy

The bot's 28 winning trades contain the ground truth for identifying profitable early buyers.

**Recommendation: Algorithmic mining first, then manual review.**
1. Script queries `token_who_bought_sold` via Nansen MCP for each of the top 10 winners
2. Cross-references buyer lists to find wallets appearing on 3+ winners
3. Jay reviews the shortlist manually
4. Shortlist goes into `watched_wallets` PostgreSQL table

Estimated Nansen calls: 10 (one per winner). Well within budget.

### Decision 3: Bridge architecture for next 14 days

Without Helius webhooks, smart money checks piggyback on existing Nansen enrichment flow:
- `_fetch_nansen_enrichment` already calls `get_smart_money_buyers` per signal
- Add Redis SET check: is any buyer in our watched_wallets?
- Zero additional API cost

**Recommendation: Redis SET lookup in existing Nansen flow.** Requires enabling Nansen (Decision 1).

### Decision 4: First smart money rule to deploy

Based on confirmed Nansen data availability:

**Rule: "If 2+ curated wallets bought this token (from Nansen who_bought_sold), add +30 confidence boost"**

- Format: hardcoded rule in signal_aggregator, NOT an ML feature
- Trigger: `nansen_sm_buy_count >= 2` (using real wallet matches from our curated list)
- Action: confidence boost of +30 (same mechanism as Helius webhook boost at line 1760)
- Kill switch: env var `SM_ENTRY_RULE_ENABLED=false`

**NOTE:** This rule won't fire for most pump.fun tokens because Nansen's who_bought_sold takes 1-5 minutes to index trades. It will fire for tokens that our watched wallets buy and then PumpPortal picks up a few minutes later. This is actually the ideal scenario — we're following proven wallets with a slight delay.

### Decision 5: Treasury spam fix priority

**ALREADY FIXED.** The budget guard from the API audit is working. Treasury logs show "Could not fetch balance" (no HTTP calls) instead of "getBalance failed on all Helius endpoints" (failed HTTP calls). No action needed.

---

## To Build — Step by Step

### Phase A: Wallet curation (tomorrow, zero API cost)

1. Query paper_trades for top 20 winners (realised_pnl_pct > 30%)
2. For each winner, call Nansen MCP `token_who_bought_sold` (20 calls)
3. Cross-reference: find wallet addresses appearing as buyers on 3+ winners
4. Score candidates by: frequency × avg PnL of tokens they bought
5. Insert top 20-40 into `watched_wallets` table with source='nansen_mining'
6. Load into Redis SET `sm:watched_wallets` on signal_listener startup

### Phase B: Nansen enablement + Redis lookup (this week, ~200 calls/day)

1. Set `NANSEN_DRY_RUN=false` on signal_aggregator (Decision 1)
2. In `_fetch_nansen_enrichment`: after `get_smart_money_buyers` returns, check each buyer against `sm:watched_wallets` Redis SET
3. Store match count as `nansen_watched_wallet_matches` in features
4. Add confidence boost rule: if matches >= 2, boost +30

### Phase C: Helius webhook architecture (after April 26)

1. Configure Helius webhook for 20-40 watched wallet addresses (SWAP events only)
2. Webhook handler in dashboard_api.py: on SWAP event, INCR `sm:buys:{mint}` with 300s TTL
3. Signal_aggregator reads `sm:buys:{mint}` at evaluation time
4. Entry rule: if count >= 3 from different watched wallets, boost confidence

### Phase D: Feedback loop (ongoing)

1. Track which watched wallet trades led to profitable bot entries
2. Monthly rescore: wallets that correlated with wins get score++, losers get score--
3. Auto-remove wallets below score threshold
4. Re-mine winners for new wallet candidates quarterly

---

## Test Calls Made

| # | Endpoint | Status | Latency | Notes |
|---|----------|--------|---------|-------|
| 1 | Nansen `token_who_bought_sold` (all buyers) | 200 | ~2s | 24 buyers with labels |
| 2 | Nansen `token_pnl_leaderboard` | 200 | ~1s | EMPTY for pump.fun token |
| 3 | Nansen `token_current_top_holders` | 200 | ~1s | EMPTY for pump.fun token |
| 4 | Nansen `token_discovery_screener` (SM filter, micro-cap) | 200 | ~1s | EMPTY |
| 5 | Nansen `wallet_pnl_summary` (GMGN bot user) | 200 | ~1s | EMPTY — wallet not tracked |
| 6 | Nansen `token_who_bought_sold` (SM label filter) | 200 | ~1s | EMPTY — no SM at this scale |
| 7 | Nansen `token_discovery_screener` (no SM filter, $100k+) | 200 | ~2s | 25 memecoins with data |
| 8 | Helius `getBalance` | 429 | 104ms | Credits exhausted |

**Nansen MCP calls used: 7 of 8 budget**

---

## Next Session Candidates

1. **HIGHEST: Mine winning trades for repeating wallets** — Phase A above. Zero API cost, uses existing DB data. Can start immediately.
2. **HIGH: Enable Nansen on signal_aggregator** — flip DRY_RUN=false, budget=200/day. Required for Phase B.
3. **HIGH: Fix entry filter** — separate prompt handles the v3 `> 0` vs `!= -1` bug.
4. **MEDIUM: Add Nansen SM lookup to enrichment flow** — Phase B step 2-4.
5. **MEDIUM: Prune FEATURE_COLUMNS** — model has 42 zero-valued features.
6. **LOW: Helius budget enforcement** — add global wrapper (not urgent until Apr 26 reset).
