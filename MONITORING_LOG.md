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

---

## 2026-03-27 — Full Diagnostic + Multi-Fix Session

### Session 1: Discord error floods + SOL balance issues (commit a3d4703)
7 bugs fixed:
1. **Treasury EMERGENCY_STOP loop** — was halting → restarting → Discord alert every 15min. Now rate-limited to 1/hour, keeps running.
2. **bot_core `_daily_reset` crash on month-end** — `day+1` overflows on 31st. Fixed with `timedelta(days=1)`.
3. **ML feature mismatch** — ml_engine expected `creator_dead_tokens_30d` but signal_aggregator sends `creator_rug_count`/`creator_prev_tokens_count`/`creator_graduation_rate`. Aligned all features.
4. **railway.toml missing healthcheck** — added `/api/health`.
5. **execution.py missing pool types** — `launchlab`/`bonk` not routed to PumpPortal.
6. **Helius webhook signals dropped in TEST_MODE** — dashboard_api skipped Redis push.
7. **main.py crash-restart spam** — added exponential backoff (5s→300s cap).

### Session 2: PostgreSQL migration (commit 3f1466e)
- SQLite was wiped on every Railway restart (ephemeral filesystem).
- New `services/db.py` — shared asyncpg pool, creates all 4 tables.
- All 8 files migrated: aiosqlite → asyncpg, `?` → `$1/$2/$3`, `lastrowid` → `RETURNING id`.
- `aiosqlite` removed from requirements, `asyncpg` added.
- Railway setup: add PostgreSQL plugin → `DATABASE_URL` auto-injected.

### Session 3: Paper trading not firing (commit eb7a2ba)

#### Issue 1: ML gate blocking ALL signals
- **Issue:** Untrained ML model returns score 50.0. All personality thresholds require 65-80. Every signal rejected.
- **Fix:** `predict()` now returns `(score, is_trained)` tuple. Signal aggregator bypasses ML threshold when model is untrained, allowing signals to flow for data collection.
- **File:** `services/ml_engine.py`, `services/signal_aggregator.py`
- **Result:** Signals now pass ML gate when model has no training data.

#### Issue 2: bot_core defaulting to DEFENSIVE mode
- **Issue:** After 60s timeout waiting for market_health, bot_core defaults to DEFENSIVE. This raised ML thresholds by +10 (65→75, 70→80), further blocking signals.
- **Fix:** Default changed from DEFENSIVE to NORMAL.
- **File:** `services/bot_core.py`
- **Result:** Bot starts in NORMAL mode, uses standard thresholds.

#### Issue 3: MIN_POSITION_SOL too high for compounding multipliers
- **Issue:** With DEFENSIVE mode × dead zone time × correlation haircut, positions could fall below 0.10 SOL floor and get rejected.
- **Fix:** MIN_POSITION_SOL lowered from 0.10 to 0.05 SOL.
- **File:** `services/risk_manager.py`
- **Result:** Smaller paper positions allowed during unfavorable conditions.

### Expected Signal Flow After Deploy
```
signal_listener → signals:raw → signal_aggregator → [ML bypass] → signals:scored → bot_core → PAPER ENTERED
```

### Verification Checklist
- [ ] market_health: "SOL: $XXX.XX" (real number not None)
- [ ] signal_aggregator: "ML untrained — bypassing threshold" in logs
- [ ] signal_aggregator: "SCORED:" lines appearing
- [ ] bot_core: "PAPER ENTERED" at least once
- [ ] Paper trades appearing in PostgreSQL paper_trades table
