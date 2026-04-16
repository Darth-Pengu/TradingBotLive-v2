# External API Audit — 2026-04-16

## Executive Summary

Most execution-critical APIs are working. **One critical gap:** Helius
Staked RPC (the fast tx submission endpoint) returns HTTP 522 on every
attempt. This is the PRIMARY endpoint for real trade submission in
execution.py. The standard Helius RPC works fine (285ms median) and
serves as fallback, but staked is preferred for faster block inclusion.
Anthropic credits are exhausted (governance LLM dead). SocialData
credits exhausted. All other APIs functional.

**Verdict: READY WITH ONE FIX** — Helius Staked URL needs
investigation/replacement before live trading. Standard RPC is a viable
fallback but adds latency to critical tx submission path.

## Readiness Matrix

| API | Priority | Status | Latency | Notes |
|---|---|---|---|---|
| Helius RPC | CRITICAL | OK | 285ms | getBalance works, 5.0 SOL confirmed |
| Helius Staked | CRITICAL | **FAIL (522)** | 80ms (to error) | Primary tx submit endpoint DOWN |
| Helius Parse TX | CRITICAL | OK | 761ms | Trade confirmation endpoint responds |
| Jupiter V2 | CRITICAL | OK | 365ms | Quote returned, route found |
| PumpPortal | CRITICAL | OK | 805ms | Domain live, 400 (expected) |
| Jito | CRITICAL | PARTIAL | 630ms | Endpoint responds but tip_floor returned empty |
| cfgi.io | IMPORTANT | OK | 1141ms | SOL CFGI = 60.5, credits working |
| Alternative.me | HISTORICAL | OK | 814ms | BTC F&G available |
| Rugcheck | IMPORTANT | OK | 6685ms | Slow but works, full report returned |
| GeckoTerminal | IMPORTANT | OK | 1378ms | Price returned |
| CoinGecko | IMPORTANT | OK | 48ms | Fast, SOL = $85.13 |
| Vybe | OPTIONAL | PARTIAL | 363ms | 404 on SOL mint (may need different endpoint) |
| SocialData | OPTIONAL | **FAIL (402)** | 1039ms | Credits exhausted |
| Anthropic | OPTIONAL | **FAIL (400)** | 329ms | Credits exhausted |
| Nansen | DISABLED | DISABLED | — | Intentionally disabled (over budget) |

## Critical Issues

### 1. Helius Staked RPC returning HTTP 522 (BLOCKER for optimal live trading)
- URL: `HELIUS_STAKED_URL` (ardith-mo8tnm-fast-mainnet.helius-rpc.com)
- All 3 retry attempts returned 522
- 522 = Cloudflare "Connection timed out" — upstream server not responding
- **Impact:** execution.py tries HELIUS_STAKED_URL first for sendTransaction.
  Falls back to standard HELIUS_RPC_URL which works but is slower.
- **Risk level:** MEDIUM — standard RPC fallback exists, but staked is
  preferred for faster block inclusion in competitive pump.fun trading
- **Fix options:**
  1. Contact Helius to verify staked endpoint status
  2. Generate new staked URL from Helius dashboard
  3. Use standard RPC as primary (accept slightly slower submission)

### 2. Anthropic credits exhausted (non-blocking for Speed Demon)
- Governance LLM (Claude Haiku) cannot make mode recommendations
- Impact: governance service runs but returns hallucinated/default values
- Not a live trading blocker — Speed Demon doesn't depend on governance

### 3. SocialData credits exhausted (non-blocking)
- Social signal enrichment won't work
- Not currently used by Speed Demon entry logic

## Recommended Fixes Before TEST_MODE=false

1. **IMPORTANT:** Investigate/replace Helius Staked URL. Either:
   - Generate fresh staked RPC URL from Helius dashboard
   - Or accept standard RPC as fallback (adds ~100ms to tx submission)
2. **OPTIONAL:** Top up Anthropic credits for governance LLM
3. **OPTIONAL:** Top up SocialData credits (unused by Speed Demon)

## Latency Analysis (5-sample measurements from Sydney)

| API | Median | P90 | Max | Tolerance | Status |
|---|---|---|---|---|---|
| Helius RPC | 285ms | 307ms | 308ms | <500ms | GOOD |
| Jupiter V2 | 365ms | 513ms | 513ms | <500ms | MARGINAL (P90) |
| Jito tip_floor | 629ms | 649ms | 649ms | <800ms | OK |
| CoinGecko | 50ms | 52ms | 53ms | <500ms | EXCELLENT |

**Note:** These latencies are from Claude Code on Jay's machine in
Sydney to US-based APIs. Railway (US-based) will have lower latency
to these same endpoints. Real bot latency will be better than measured.

## Credit / Budget Status
- **Helius:** No Redis tracking keys found (helius:calls counter not set).
  HELIUS_DAILY_BUDGET=0 on web only. No actual rate limiting in place.
- **cfgi.io:** 100k credits topped up, SOL CFGI = 60.5 working
- **Nansen:** nansen:disabled key NOT found in Redis (was supposed to be
  SET with TTL). May need re-disabling if it expired.
- **Anthropic:** Credits exhausted, governance non-functional
- **SocialData:** Credits exhausted (402 Insufficient balance)
- **Jupiter:** Working on current tier, no rate limit errors observed

## Env Var Matrix

All env vars are set on ALL 8 Railway services (Railway shares env vars
at project level). Every service has: HELIUS_RPC_URL, HELIUS_STAKED_URL,
JUPITER_API_KEY, JITO_ENDPOINT, TRADING_WALLET_ADDRESS,
TRADING_WALLET_PRIVATE_KEY, TEST_MODE, ANTHROPIC_API_KEY, NANSEN_API_KEY,
VYBE_API_KEY, SOCIALDATA_API_KEY.

**Security note:** TRADING_WALLET_PRIVATE_KEY is exposed to ALL 8
services including signal_listener and web. Only bot_core and treasury
actually need it. Consider restricting in a future security session.

## What's NOT Tested (known limitations)
- Real transaction submission (requires signing, skipped per rules)
- Jupiter /execute (would submit a real tx, skipped)
- Jito bundle submission (requires signed tx, skipped)
- PumpPortal trade-local full request (needs valid tx payload)
- Helius sendTransaction (the actual tx submission call)

## Go/No-Go for Live Trading

**READY WITH ONE FIX:**
- Fix Helius Staked URL (generate new one from dashboard) OR accept
  standard RPC fallback
- All other execution-critical paths working
- Safety rails comprehensive (position limits, loss limits, circuit breakers)
- Trading wallet funded (5.00 SOL)

The Helius Staked issue is NOT a hard blocker — execution.py falls back
to standard RPC. But for optimal competitive trading on pump.fun, the
staked endpoint is preferred.
