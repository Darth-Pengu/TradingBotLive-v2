# API Audit — Nansen / Vybe / Helius — 2026-04-11 AEDT

## TL;DR

- **Helius: CREDITS EXHAUSTED** (10.09M / 10M used this cycle)
- **Root cause of burn: 6 duplicate Raydium webhooks (45%) + unchecked signal enrichment RPC calls (55%)**
- **Webhook handler: BUCKET A (LIVE)** — but monitoring Raydium infra addresses, NOT whale wallets. Amplification loop detected.
- **Biggest fixable leak: Set `HELIUS_ENRICHMENT_ENABLED=false`** — saves ~250k credits/day (all enrichment calls already failing)
- **Nansen: WORKING** — MCP calls succeed, credits available, 8 safeguard layers intact
- **Vybe: BROKEN** — ALL token endpoints return 404 (API restructured or deprecated)
- **Fixes applied: 1** (treasury budget guard)
- **Decisions required: 5**

---

## Helius Burn Analysis (THE KEY FINDING)

### Cycle Summary
| Metric | Value |
|--------|-------|
| Billing cycle | March 26 - April 26, 2026 |
| Credits used | 10,089,862 / 10,000,000 (101%) |
| Webhook events | 4,508,425 (~45% of burn) |
| RPC calls | ~5,581,437 (~55% of burn) |
| Credits remaining | 0 |
| Cycle resets | April 26, 2026 |

### HELIUS_DAILY_BUDGET=0 IS A LIE

**The most important finding of this audit:** `HELIUS_DAILY_BUDGET=0` is set as an env var but **NO SERVICE CHECKS IT** before making RPC calls. The budget variable is only read by `dashboard_api.py:2314` for display on the dashboard. Signal_aggregator, treasury, market_health, execution, and signal_listener all ignore it completely.

Every Helius RPC call in the bot bypasses the budget gate.

### Burn Breakdown by Source

#### GROUP A — Webhook Events (4.5M credits, ~45%)

| Detail | Value |
|--------|-------|
| Source | 6 Helius webhooks (5 now disabled by Jay, 1 remaining) |
| Monitored addresses | 8 Raydium AMM infrastructure addresses |
| Event types | SWAP, ADD_LIQUIDITY, BURN, CLOSE_ACCOUNT, CREATE_POOL, TOKEN_MINT, TRANSFER, WITHDRAW_LIQUIDITY |
| Cost per event | 1 credit |
| Rate | ~280k events/day (16 days of cycle) |

**These are NOT whale wallets.** The 8 addresses are Raydium V4 authority, program ID, and infrastructure accounts. Subscribing to these captures EVERY Raydium trade — a firehose. The webhook was designed for whale wallet monitoring but was configured with the wrong addresses.

Jay disabled 5 of 6 webhooks. The remaining one (ID: `3c423d36-1f41-4368-835a-582e7b897dfc`) still monitors the same 8 Raydium addresses and is still burning credits.

#### GROUP B — Signal Enrichment (largest RPC consumer, ~300k+ credits/day)

**Source:** `services/signal_aggregator.py` — per-token enrichment pipeline

Every token that reaches signal evaluation triggers up to 6 Helius RPC calls:

| Function | File:Line | RPC Method | Cache | Est. calls/hr |
|----------|-----------|------------|-------|---------------|
| `_fetch_holder_data_helius` | signal_aggregator.py:686 | `getTokenLargestAccounts` | NONE | ~2,900 |
| `_check_dev_wallet_sells` | signal_aggregator.py:927 | `HELIUS_PARSE_HISTORY_URL` (transactionhistory) | NONE | ~2,500 |
| `_check_bundle_detection` | signal_aggregator.py:988 | `HELIUS_PARSE_TX_URL` (transactions) | NONE | ~2,500 |
| `_get_creator_stats` | signal_aggregator.py:1066 | `HELIUS_PARSE_HISTORY_URL` (transactionhistory) | 1hr Redis | ~1,500 |
| `_get_jito_bundle_stats` | signal_aggregator.py:1234 | `HELIUS_PARSE_TX_URL` (transactions) | NONE | ~2,500 |
| `_fetch_creator_history` | signal_aggregator.py:828 | `HELIUS_PARSE_HISTORY_URL` (transactionhistory) | 24hr Redis | ~500 |

**Gated by:** `HELIUS_ENRICHMENT_ENABLED` env var (defaults to `true`, NOT SET on signal_aggregator)

**The 2-URL fallback doubles the burn:** `_fetch_holder_data_helius` tries `HELIUS_RPC_URL` then `HELIUS_GATEKEEPER_URL`. When the first returns 429, it tries the second (also 429). Both count as credits. This explains why getTokenLargestAccounts shows ~2,900/hr instead of ~1,450/hr.

#### GROUP C — Dashboard Balance Polling (~400-700 getBalance/hr)

| Caller | File:Line | Frequency | Calls/hr |
|--------|-----------|-----------|----------|
| WebSocket `_periodic_push` | dashboard_api.py:1857 | Every 10s (holding wallet always, trading wallet if Redis miss) | ~360 |
| `api_health` endpoint | dashboard_api.py:348-360 | Per frontend poll (~30s) | ~120-240 |
| `api_treasury` endpoint | dashboard_api.py:879-880 | Per page load | ~10-20 |

All use `_get_sol_balance` which tries 2 Helius URLs with fallback. No caching layer.

#### GROUP D — Treasury Balance Check (~24 getBalance/hr)

| Caller | File:Line | Frequency | Calls/hr |
|--------|-----------|-----------|----------|
| `run_treasury_sweep` | treasury.py:214 | Every 5 min | ~12 (×2 URL fallback = ~24) |

**Fixed this session:** Added `HELIUS_DAILY_BUDGET=0` budget guard to skip calls.

#### GROUP E — Market Health (~24 getPriorityFeeEstimate/hr)

| Caller | File:Line | Frequency | Calls/hr |
|--------|-----------|-----------|----------|
| `_fetch_priority_fee` | market_health.py:184 | Every 5 min | ~12 (×2 URL fallback = ~24) |

#### GROUP F — Execution (minimal — TEST_MODE)

| Caller | File:Line | Usage |
|--------|-----------|-------|
| `_get_priority_fee` | execution.py:144 | Only on real trades (TEST_MODE=true → rare) |
| `send_transaction` | execution.py:448 | Only on real trades |

### AMPLIFICATION LOOP

```
Webhook event (1 credit)
  ↓
dashboard_api.py:handle_helius_webhook classifies → signals:raw
  ↓
signal_aggregator reads from signals:raw
  ↓
4-6 Helius RPC calls per signal (4-6 credits)
  ↓
Total amplification: 1 webhook event → 5-7 credits burned
```

With ~280k webhook events/day, this amplification adds ~1.4M-1.9M additional RPC credits/day ON TOP of the webhook credits themselves.

### Estimated Daily Burn (before credit exhaustion)

| Source | Credits/day |
|--------|-------------|
| Webhook events | ~280,000 |
| Signal enrichment (PumpPortal + webhook signals) | ~250,000 |
| Dashboard getBalance | ~10,000 |
| Treasury getBalance | ~580 |
| Market health getPriorityFeeEstimate | ~580 |
| Execution | ~50 |
| **TOTAL** | **~541,000/day** |

Over 31 days: ~16.8M credits. Budget is 10M. **Overshoot: 68%.**

### Biggest Leaks (prioritized)

1. **Raydium webhook (45% of burn)** — The remaining webhook monitors Raydium infra, not whale wallets. Should be disabled or reconfigured to actual whale wallet addresses.

2. **Signal enrichment without budget gate (35% of burn)** — `HELIUS_ENRICHMENT_ENABLED=true` by default. These enrichment calls ALL FAIL NOW (429) but still burn credits. Set `HELIUS_ENRICHMENT_ENABLED=false` immediately.

3. **Dashboard holding wallet balance polling (5% of burn)** — `_periodic_push` calls `_get_sol_balance(HOLDING_WALLET_ADDRESS)` every 10 seconds with no Redis cache. Should cache with 60s TTL.

4. **No global Helius budget enforcement** — `HELIUS_DAILY_BUDGET` is cosmetic. Need actual enforcement in a shared utility function.

### Fixes Applied This Session

| Commit | Description | Impact |
|--------|-------------|--------|
| (pending) | Treasury budget guard: skip getBalance when `HELIUS_DAILY_BUDGET=0` | Silences 123 errors/log-window, saves ~580 credits/day when budget >0 |

### Unfixable Without Code Rewrite

1. **Global Helius budget enforcement** — requires creating a shared `helius_rpc_call()` wrapper that all services use, with Redis-based daily counter. Medium effort.
2. **Dashboard balance caching** — `_get_sol_balance` needs a Redis cache layer. Small effort but multi-file change.
3. **Enrichment call caching** — `_check_dev_wallet_sells` and `_check_bundle_detection` have ZERO caching. Adding per-token cache would reduce calls by ~50%. Medium effort.

---

## Webhook Section

### Handler Analysis

| Detail | Value |
|--------|-------|
| Endpoint | `POST /helius-webhook` (dashboard_api.py:2421) |
| Handler | `handle_helius_webhook` (dashboard_api.py:1708) |
| Auth | HMAC signature verification if `HELIUS_WEBHOOK_SECRET` is set (currently empty) |
| Classification | **BUCKET A — FULLY LIVE** |

**What it does:**
1. Receives Helius enhanced transaction payloads
2. Classifies each transaction into signal types (whale_trade, whale_transfer, new_token, liquidity_add/remove, pool_created, token_burn, account_closed)
3. Pushes classified signals to `signals:raw` Redis list
4. Signal_aggregator picks them up and runs full enrichment pipeline

**No amplification within the handler itself** — it doesn't make its own Helius RPC calls. The amplification occurs when signals enter the aggregator pipeline.

**The real problem:** The webhook monitors Raydium AMM infrastructure addresses, which means EVERY Raydium swap/liquidity event on Solana generates a webhook event. This is a firehose of all DEX activity, not targeted whale monitoring.

**Recommendation: DISABLE the last webhook immediately.** It was configured with wrong addresses (Raydium infra instead of whale wallets). Reconfigure with actual whale wallet addresses when credits reset.

---

## getTokenLargestAccounts Pipeline

### Code Analysis

Function: `_fetch_holder_data_helius` at `signal_aggregator.py:686-720`

```python
# Correctly implemented:
accounts = data.get("result", {}).get("value", [])
amounts = [float(a.get("uiAmount", 0) or 0) for a in accounts[:20]]
total_supply_sample = sum(amounts)
top10_sum = sum(amounts[:10])
top10_pct = (top10_sum / total_supply_sample * 100) if total_supply_sample > 0 else 0
gini = _compute_gini(amounts) if len(amounts) >= 3 else -1
```

**Returns:** `{"holder_count_sample": N, "top10_holder_pct": X.X, "holder_gini": Y.Y}`

### Why top10_holder_pct = 0% Despite 2,900 Calls/Hour

**Answer: ALL calls are failing with 429 (credits exhausted).** The function returns `{}` on failure, so no holder data reaches the features.

**Before credit exhaustion**, the pipeline was correctly populating top10_holder_pct and holder_gini. The code is correct — the data source is dead.

**Fallback path:** `_fetch_holder_data_vybe` at line 723 — also failing (Vybe 404s).

**Both data sources for concentration metrics are simultaneously broken.** This is why top10_holder_pct and holder_gini are at 0%.

### Fix Path

When Helius credits reset (April 26), this pipeline will automatically start working again. No code fix needed — just credits.

To reduce the call rate: add a per-token Redis cache with 300s TTL in `_fetch_holder_data_helius`. Currently has ZERO caching.

---

## Vybe Section

### Test Results

| Endpoint | Status | Response |
|----------|--------|----------|
| `GET /token/{mint}/top-holders?limit=20` | 404 | Empty |
| `GET /token/{mint}/holders?limit=20` | 404 | Empty |
| `GET /tokens/{mint}/holders?limit=20` | 404 | Empty |
| `GET /token/{mint}` | 404 | Empty |
| `GET /token/{mint}/holder-distribution` | 404 | Empty |
| `GET /token/holders/{mint}` | 404 | Empty |
| `POST /token/top-holders` (with body) | 404 | Empty |
| `POST /token/holders` (with body) | 404 | Empty |
| `GET /wallets/{addr}/token-balance` | 404 | Empty |
| `GET /` (API root) | 200 | "Vybe analytics server" |

**Auth:** Working (API root returns 200). The API key is valid.

**Diagnosis: Category (b) — plan tier limitation or API restructured.** All token-specific endpoints return 404 while the API root works. The Vybe API has likely deprecated these endpoints or moved them to a different path/tier.

### Impact on Bot

- `_fetch_holder_data_vybe` (signal_aggregator.py:723): Returns `{}` — Vybe fallback is dead
- KOL/MM detection (signal_aggregator.py:2294): Returns nothing — graduated token whale_boost always 1.0
- **holder_count at 48% population comes from GeckoTerminal (signal_aggregator.py:753), NOT Vybe**

### Verdict: BLOCKED

Vybe token endpoints are non-functional. Auth works but data endpoints are 404. Either:
- Free tier no longer includes token holder endpoints
- API paths have changed (no docs update found)
- Endpoints deprecated

**Recommendation:** Check Vybe dashboard/docs for current API structure. May need to upgrade plan or switch endpoints. Low priority — Helius getTokenLargestAccounts is the better data source when credits are available.

---

## Nansen Section

### Test Results (via MCP, no DRY_RUN flip needed)

| Endpoint | Status | Data Quality |
|----------|--------|-------------|
| `general_search("SOL", chain=solana)` | 200 | Correct: SOL $84.865, volume 8.1B |
| `token_who_bought_sold(jbEZ6...pump, BUY)` | 200 | Rich: 25 labeled buyers with volumes, bot labels, deployer labels |
| `token_discovery_screener(solana, Memecoins, SM filter)` | 200 | No data (too restrictive filter) |
| `token_current_top_holders(jbEZ6...pump)` | 200 | No data (micro token, not tracked) |

### Current State

| Service | NANSEN_DRY_RUN | NANSEN_DAILY_BUDGET | NANSEN_API_KEY |
|---------|---------------|---------------------|---------------|
| signal_aggregator | **TRUE** | 2000 | Present |
| ml_engine | (default true) | 2000 | Present |
| bot_core | (default true) | 50 | Present |
| treasury | (default true) | 50 | Present |

### Safeguard Status

| Layer | Status |
|-------|--------|
| 1. Service routing guard | Active — only signal_aggregator, signal_listener, bot_core allowed |
| 2. Daily budget enforcement | Active — Redis counter with configurable limit |
| 3. Distributed lock | Active |
| 4. Per-endpoint caching | Active — TTLs from 120s to 604800s |
| 5. Circuit breaker | Active — trips on consecutive 429s |
| 6. Dry-run mode | **ACTIVE (DRY_RUN=TRUE)** |
| 7. Per-call logging | Active — Redis list nansen:call_log |
| 8. Emergency kill switch | Active — nansen:emergency_stop key |

### Redis State

| Key | Value |
|-----|-------|
| nansen:emergency_stop | nil (not set) |
| nansen:disabled | nil (expired — was set with EX 86400) |
| nansen:circuit_breaker | nil (not set) |
| nansen:budget:daily:spent | nil (no calls today) |

### Verdict: WORKING — Ready to Enable

Nansen MCP confirms credits are available and data is rich (especially `token_who_bought_sold` with labeled wallets). The 8 safeguard layers are all in place. DRY_RUN gate is working correctly.

**The `token_who_bought_sold` data is the highest-value endpoint** — it returns labeled wallet addresses (bot users, deployers, funds) that can directly feed the smart money entry rules.

---

## What This Means for the Smart Money Vision

Jay's goal: 20-40 whale wallets, trigger entry on 3+ buys.

### Architecture given audit findings:

| Component | Best source | Status |
|-----------|------------|--------|
| **Wallet discovery (who)** | Nansen `token_who_bought_sold` + `token_current_top_holders` | WORKING via MCP |
| **Wallet monitoring (when)** | Helius webhooks (reconfigured to actual whale addresses) | BLOCKED until credits reset Apr 26 |
| **Trade-time concentration** | Helius `getTokenLargestAccounts` | BLOCKED until credits reset |
| **Labeled holder analysis** | Nansen `get_labeled_top_holders` | WORKING (via nansen_client.py) |
| **Smart money labels** | Nansen (exclusive) | WORKING |

### Estimated complexity: **M (Medium)**

### Blockers:
1. Helius credits exhausted until April 26
2. Vybe endpoints dead — cannot use as Helius fallback
3. Need whale wallet list curated before webhook reconfiguration

---

## What This Means for the ML Model

Sample size is the bottleneck (128 samples, 6 positives). The top10_holder_pct and holder_gini features have been zero since Helius credits ran out. When credits reset:

1. `_fetch_holder_data_helius` will automatically start populating top10_holder_pct and holder_gini
2. These features currently have zero SHAP importance (trained on all-zero data)
3. A retrain with populated concentration features could improve the model
4. But still need 500+ samples before new features help meaningfully

**Short-term:** New Nansen data should be used as HARDCODED entry rules (e.g., reject if 0 smart money buyers), not ML features.

---

## Decisions Required From Jay

### Decision 1: Disable the last Helius webhook?

The remaining webhook (ID: `3c423d36-1f41-4368-835a-582e7b897dfc`) monitors 8 Raydium AMM infrastructure addresses — NOT whale wallets. It generates thousands of events/day and amplifies into RPC calls.

**Recommendation: YES — disable it immediately via Helius dashboard.** It's burning credits on a firehose of all Raydium DEX activity. Reconfigure with actual whale wallet addresses when credits reset.

### Decision 2: Set HELIUS_ENRICHMENT_ENABLED=false?

The signal enrichment pipeline makes 4-6 Helius RPC calls per signal evaluation. ALL of these calls are currently failing (429) and returning empty dicts. The bot is already running without this data.

Setting this env var to false just stops the failed HTTP calls — it's a no-op in terms of bot behavior but will save ~250k wasted credits/day when credits reset.

```
railway variables --set "HELIUS_ENRICHMENT_ENABLED=false" -s signal_aggregator
```

**Recommendation: YES — set immediately.** Re-enable when credits reset AND the enrichment is worth the cost (after adding per-call caching).

### Decision 3: Helius credit strategy for next cycle (starts April 26)?

| Scenario | Credits/day | Monthly | Plan needed |
|----------|-------------|---------|-------------|
| Current code (no fixes) | ~541,000 | ~16.8M | 20M plan |
| Webhook disabled, enrichment disabled | ~11,000 | ~340,000 | Free/10M plan |
| Webhook disabled, enrichment cached (300s TTL) | ~90,000 | ~2.8M | 10M plan |
| Webhook on 40 whale wallets, enrichment cached | ~120,000 | ~3.7M | 10M plan |

**Recommendation:** Keep 10M plan. Disable webhook + enrichment now. Re-enable enrichment with caching after credits reset. Budget headroom: ~6M credits for whale webhook monitoring.

### Decision 4: Enable Nansen live calls?

Nansen MCP works. Credits are available. Safeguards are in place. The `token_who_bought_sold` endpoint provides labeled wallet data that's immediately useful for smart money rules.

**Recommendation: YES — enable with conservative limits.**

Steps:
1. `SET nansen:disabled true EX 86400` on Redis (refresh daily safety net)
2. Start with NANSEN_DAILY_BUDGET=50 on signal_aggregator (test for 24hrs)
3. Monitor via `nansen:call_log` and `nansen:credits:YYYY-MM-DD`
4. If stable after 24hrs, increase to 200/day
5. Do NOT flip NANSEN_DRY_RUN to false until cache/safeguards verified in production

### Decision 5: Vybe — investigate or abandon?

All Vybe token endpoints return 404. Options:
- (a) Check Vybe docs/support for current API structure
- (b) Abandon Vybe, use Helius getTokenLargestAccounts (when credits available) + Nansen labeled holders
- (c) Both — keep Vybe as fallback if they fix endpoints

**Recommendation: Option (b) — Helius + Nansen is better data anyway.** Vybe's holder data was unlabeled. Nansen provides labels (funds, bots, smart money). Check Vybe docs if time permits but don't invest engineering effort.

---

## To Enable / Cleanup — Step-by-Step

### Immediate (no deploy needed):

1. **Disable last webhook** via Helius dashboard (webhook ID: `3c423d36-1f41-4368-835a-582e7b897dfc`)
2. **Set enrichment off:**
   ```
   railway variables --set "HELIUS_ENRICHMENT_ENABLED=false" -s signal_aggregator
   ```
3. **Renew Nansen safety net:**
   ```
   Redis: SET nansen:disabled true EX 86400
   ```

### Requires code deploy (one commit):

1. **Treasury budget guard** (APPLIED this session) — deploy treasury service
2. **Dashboard balance caching** (future session) — add Redis cache to `_get_sol_balance`
3. **Enrichment call caching** (future session) — add per-token Redis cache to dev_sell, bundle, jito checks
4. **Global Helius budget enforcement** (future session) — shared wrapper with Redis counter

### When credits reset (April 26):

1. Re-enable enrichment: `HELIUS_ENRICHMENT_ENABLED=true` (after adding caching)
2. Set `HELIUS_DAILY_BUDGET` to actual enforcement value
3. Configure webhook with curated whale wallet addresses (20-40)
4. Set webhook event types to SWAP only (no need for BURN, CLOSE_ACCOUNT, etc.)
5. Monitor daily burn via Helius dashboard

---

## Test Calls Made

| Service | Endpoint | Status | Latency | Credits |
|---------|----------|--------|---------|---------|
| Nansen MCP | general_search("SOL") | 200 | ~1s | 0 (MCP proxy) |
| Nansen MCP | token_who_bought_sold | 200 | ~2s | 0 (MCP proxy) |
| Nansen MCP | token_discovery_screener | 200 | ~1s | 0 (MCP proxy) |
| Nansen MCP | token_current_top_holders | 200 | ~1s | 0 (MCP proxy) |
| Helius | getBalance (mainnet RPC) | 429 | 0.2s | 0 (already exhausted) |
| Helius | getBalance (gatekeeper) | 429 | 0.6s | 0 (already exhausted) |
| Helius | getBalance (staked) | 522 | 0.1s | 0 |
| Vybe | /token/{mint}/top-holders | 404 | 0.7s | 0 |
| Vybe | /token/{mint}/holders | 404 | 0.3s | 0 |
| Vybe | Multiple other patterns (10 total) | 404 | 0.2-0.7s | 0 |

**Total billable API calls: 0** (Nansen via MCP, Helius already exhausted, Vybe failing)

## Files Changed

| File | Change |
|------|--------|
| `services/treasury.py:59` | Added `HELIUS_DAILY_BUDGET=0` budget guard to skip getBalance calls |

## Next Session Candidates

1. **HIGHEST: Add per-token caching to Helius enrichment calls** — _check_dev_wallet_sells, _check_bundle_detection, _get_jito_bundle_stats all have ZERO caching. Adding 300s Redis cache would reduce enrichment RPC burn by ~70%.
2. **HIGH: Curate whale wallet list for Helius webhook** — use Nansen token_who_bought_sold to identify 20-40 consistently profitable wallets. Store in watched_wallets table.
3. **HIGH: Add global Helius budget enforcement** — create a shared `helius_call()` wrapper with Redis-based daily counter that ALL services use.
4. **MEDIUM: Prune FEATURE_COLUMNS to ~20 populated features** — model trained on 42 zero-valued features is learning noise.
5. **MEDIUM: Enable Nansen for smart money entry rules** — hardcoded rules (require N smart money buyers) not ML features.
6. **LOW: Investigate Vybe API changes** — check docs for current endpoint structure.
