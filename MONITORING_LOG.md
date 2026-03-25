# ZMN Bot Monitoring Log

## 2026-03-25 12:30 UTC — Initial Check

### Status
- Dashboard: UP (200 OK)
- Redis: Connected (0ms ping)
- Bot status: RUNNING
- Market mode: DEFENSIVE
- SOL price: **null** (critical — Jupiter 401, Binance fallback not deployed yet)
- Signals raw: unknown (can't check Redis directly)
- Signals scored: unknown
- Paper trades: 0
- Active positions: 0

### Root Cause Analysis
1. `sol_price: null` — Jupiter V3 returns 401 without API key. Binance fallback code pushed (commit ba7be9f + 46c07fc) but Railway may not have redeployed yet.
2. `JUPITER_API_KEY` not set as Railway env var — needs to be added: `333f75b5-6ca6-4864-9d82-fcfc65b1882f`
3. Zero signals flowing — likely because signal_listener was blocking Redis pushes in TEST_MODE (fixed in commit 3105289) but may not be deployed yet.
4. MARKET_MODE_ENCODING was undefined (fixed in commit 5887ce0) — would crash signal_aggregator on every signal.

### Fixes Pushed (awaiting Railway deploy)
- ba7be9f: Binance as primary SOL price (no auth needed)
- 46c07fc: Jupiter x-api-key headers across all services
- 5887ce0: MARKET_MODE_ENCODING added to signal_aggregator
- 3105289: Signal flow enabled in TEST_MODE

### Action Items
- [ ] Add JUPITER_API_KEY to Railway env vars
- [ ] Verify Railway redeploy completed
- [ ] Check if signals start flowing after deploy
- [ ] Monitor for paper trades appearing
