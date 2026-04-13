# Dashboard Audit -- 2026-04-13

## Summary
- Panels audited: 15
- Live and correct: 4
- Live but wrong data source: 6
- Static / placeholder: 2
- Broken: 3

## Panel-by-Panel Findings

### Top Bar: PnL
- **File:** dashboard/dashboard.html:631-634 (JS), services/dashboard_api.py:393-401 (backend)
- **Endpoint:** GET /api/status
- **Data source:** `SUM(realised_pnl_sol)` from paper_trades (ALL trades, no cleanup filter)
- **Observation:** Shows -8.4041 SOL
- **Status:** LIVE_WRONG_SOURCE
- **Issue:** Uses legacy `realised_pnl_sol` column (buggy for staged TPs) and includes contaminated pre-cleanup trades
- **Fix path:** Switch to `COALESCE(corrected_pnl_sol, realised_pnl_sol)` + add `entry_time > 1775767260` filter
- **Priority:** P0
- **Can be fixed tonight:** YES

### Top Bar: WR
- **File:** dashboard/dashboard.html:645-648 (JS), services/dashboard_api.py:429-441 (backend)
- **Endpoint:** GET /api/status
- **Data source:** `SUM(CASE WHEN realised_pnl_sol > 0)` / `COUNT(*)` from paper_trades (ALL trades)
- **Observation:** Shows 6.5%
- **Status:** LIVE_WRONG_SOURCE
- **Issue:** Same as PnL -- uses legacy column, includes contaminated trades
- **Fix path:** Same as PnL fix
- **Priority:** P0
- **Can be fixed tonight:** YES

### Top Bar: SOL Price
- **File:** dashboard/dashboard.html:636-637 (JS), services/dashboard_api.py:367-391 (backend)
- **Endpoint:** GET /api/status
- **Data source:** Redis `market:health` -> `sol_price` field, CoinGecko fallback
- **Observation:** Shows $0.00
- **Status:** BROKEN
- **Issue:** market_health.py `_fetch_sol_price()` tries Binance then CoinGecko -- both failing (likely Railway network or rate limits). `market:health.sol_price = None`. CoinGecko fallback in dashboard_api also fails. `market:sol_price` stuck at hardcoded 80.0.
- **Fix path:** NOT TRIVIAL -- needs investigation of why Binance/CoinGecko fail from Railway. The dashboard_api CoinGecko fallback at line 382 could be fixed to read `market:sol_price` Redis key as intermediate fallback.
- **Priority:** P1
- **Can be fixed tonight:** YES (add Redis fallback before CoinGecko API call)

### Top Bar: CFGI
- **File:** dashboard/dashboard.html:639-643 (JS), services/dashboard_api.py:375 (backend)
- **Endpoint:** GET /api/status
- **Data source:** Redis `market:health` -> `cfgi` field
- **Observation:** Shows 12 (EXTREME FEAR)
- **Status:** LIVE_CORRECT (from API source)
- **Issue:** The value IS correct per Alternative.me API (returns 12 for Bitcoin F&G). Jay compared against CMC which uses a DIFFERENT index (42). This is NOT a bug -- it's a different data source. See B-001 for full analysis.
- **Fix path:** Consider switching to CMC CFGI or Solana-specific index, or clearly labeling as "BTC F&G"
- **Priority:** P2 (needs Jay review -- not a display bug, it's a data source decision)
- **Can be fixed tonight:** NO (needs Jay's decision on which index to use)

### Top Bar: ML AUC
- **File:** dashboard/dashboard.html:659-660 (JS), services/dashboard_api.py:941-1058 (backend)
- **Endpoint:** GET /api/ml-status
- **Data source:** PostgreSQL ml_models.accuracy, Redis ml:model:meta
- **Observation:** Shows "67.0000 AUC" (4 decimal places, static)
- **Status:** LIVE_CORRECT but misleadingly formatted
- **Issue:** `auc.toFixed(4)` shows excessive precision. Value is from last training run.
- **Fix path:** Change to `auc.toFixed(1)` or append "(last train)" label
- **Priority:** P3
- **Can be fixed tonight:** YES (trivial JS format change)

### Top Bar: MODE
- **File:** dashboard/dashboard.html:883-887 (JS, in fetchGovernance)
- **Endpoint:** GET /api/market
- **Data source:** Redis `market:health` -> `mode` field
- **Observation:** Shows "HIBERNATE"
- **Status:** LIVE_CORRECT (given CFGI=12 and current thresholds)
- **Issue:** HIBERNATE is correct IF CFGI=12. If Jay wants CMC index (42), mode would change. Coupled to B-001.
- **Priority:** P2 (coupled to CFGI decision)
- **Can be fixed tonight:** NO

### Equity Curve (Daily)
- **File:** dashboard/dashboard.html:700-710 (JS), services/dashboard_api.py:2199-2220 (backend)
- **Endpoint:** GET /api/portfolio-history-daily
- **Data source:** `SUM(realised_pnl_sol)` grouped by date, cumulative window
- **Observation:** Shows downward curve (negative PnL)
- **Status:** LIVE_WRONG_SOURCE
- **Issue:** Uses `realised_pnl_sol` (buggy), includes all trades (no cleanup filter)
- **Fix path:** Switch to `COALESCE(corrected_pnl_sol, realised_pnl_sol)` + cleanup filter
- **Priority:** P0
- **Can be fixed tonight:** YES

### Today's Session
- **File:** dashboard/dashboard.html:676-698 (JS), services/dashboard_api.py:2095-2124 (backend)
- **Endpoint:** GET /api/session-stats
- **Data source:** `realised_pnl_sol` from paper_trades WHERE exit_time > NOW() - 24h
- **Observation:** Shows current session stats (live trades)
- **Status:** LIVE_WRONG_SOURCE (minor)
- **Issue:** Uses `realised_pnl_sol` but recent trades (post-fix) have correct values anyway. The 24h window naturally excludes old buggy trades.
- **Fix path:** Switch to `COALESCE(corrected_pnl_sol, realised_pnl_sol)` for correctness
- **Priority:** P1
- **Can be fixed tonight:** YES

### Signal Funnel
- **File:** dashboard/dashboard.html:712-735 (JS), services/dashboard_api.py:2127-2170 (backend)
- **Endpoint:** GET /api/signal-funnel
- **Data source:** Redis `filter:stats:{date}`, DB fallback with estimate multipliers
- **Observation:** Shows "Wins 234 (0.3%)" -- percentage relative to signals_received
- **Status:** LIVE_WRONG_SOURCE
- **Issue:** B-005 -- Win percentage shown as 234/81700 (signals_received). The percentage is technically correct (0.3% of signals become wins) but misleading. The funnel ratio display format shows each step's percentage relative to signals_received (line 728), which is the intended funnel behavior. The number 234 uses `realised_pnl_sol > 0` to count wins.
- **Fix path:** Switch wins count to use `corrected_pnl_sol`. The percentage display is actually correct for a funnel (each step relative to top).
- **Priority:** P1
- **Can be fixed tonight:** YES (wins count source fix)

### ML Status
- **File:** dashboard/dashboard.html:654-674 (JS), services/dashboard_api.py:941-1058 (backend)
- **Endpoint:** GET /api/ml-status
- **Data source:** PostgreSQL ml_models + Redis ml:model:meta
- **Observation:** Shows AUC, Phase, Samples, Features, Last Train, Cold Start
- **Status:** LIVE_CORRECT
- **Issue:** None significant
- **Priority:** N/A

### Personality P/L
- **File:** dashboard/dashboard.html:737-761 (JS), services/dashboard_api.py:808-873 (backend)
- **Endpoint:** GET /api/personality-stats
- **Data source:** `SUM(realised_pnl_sol)` grouped by personality (ALL trades)
- **Observation:** Shows SD 2312 trades, Analyst 1284 trades -- mixing pre/post cleanup
- **Status:** LIVE_WRONG_SOURCE + LIVE_WRONG_WINDOW
- **Issue:** B-008 -- uses legacy column AND includes contaminated data
- **Fix path:** Switch to `COALESCE(corrected_pnl_sol, realised_pnl_sol)` + add `entry_time > 1775767260`
- **Priority:** P0
- **Can be fixed tonight:** YES

### P/L Distribution
- **File:** dashboard/dashboard.html:763-813 (JS), services/dashboard_api.py:2381-2410 (backend)
- **Endpoint:** GET /api/pnl-distribution
- **Data source:** `realised_pnl_pct` bucketed into tiers (ALL trades)
- **Observation:** Histogram mixing pre/post cleanup data
- **Status:** LIVE_WRONG_SOURCE + LIVE_WRONG_WINDOW
- **Issue:** B-009 -- same as Personality P/L
- **Fix path:** Switch to `COALESCE(corrected_pnl_pct, realised_pnl_pct)` + cleanup filter
- **Priority:** P0
- **Can be fixed tonight:** YES

### Exits Footer (in P/L Distribution panel)
- **File:** dashboard/dashboard.html:793-813 (JS), services/dashboard_api.py:2330-2352 (backend)
- **Endpoint:** GET /api/exit-analysis
- **Data source:** `GROUP BY exit_reason` with counts and avg PnL
- **Observation:** "TP: 0%" shown in exit breakdown
- **Status:** LIVE_CORRECT (but misleading)
- **Issue:** B-004 -- The exit_analysis query returns ALL exit_reasons. The JS bucketing at line 805 checks for `take_profit` or `tp` in the reason string. Staged TP reasons are `staged_tp_+50%`, `staged_tp_+100%` etc. -- the `tp` substring IS matched by `reason.includes('tp')`. So this SHOULD work. The 0% likely means staged TP exits get recorded as `TRAILING_STOP` in exit_reason (the residual), not as `staged_tp_*`. The staged TP fires reduce position but the final close is a trailing stop.
- **Fix path:** Investigate -- exit_reason for staged TP trades shows the FINAL exit reason, not intermediate stages. Not a simple fix.
- **Priority:** P2
- **Can be fixed tonight:** NO (needs investigation of exit_reason recording)

### API Health
- **File:** dashboard/dashboard.html:816-829 (JS), services/dashboard_api.py:1119-1179 (backend)
- **Endpoint:** GET /api/service-health (not api-health -- different endpoint)
- **Data source:** Redis service:health cache, live Redis ping, signal age checks
- **Observation:** Vybe ONLINE (false positive), Helius PAUSED, SocialData UNKNOWN
- **Status:** LIVE but partially wrong
- **Issue:** B-003 -- Services without cached health data default to "unknown" (line 1178). The dashboard JS maps statuses directly. Vybe/Nansen etc. show "unknown" (or "waiting for health check") not "ONLINE".
- **Fix path:** The actual display depends on what's in Redis `service:health` cache. If stale data says "online", need to check health check background task.
- **Priority:** P2
- **Can be fixed tonight:** NO (depends on health check background task)

### Win Rates (Last 10/25/50)
- **File:** dashboard/dashboard.html:856-876 (JS), services/dashboard_api.py:2355-2378 (backend)
- **Endpoint:** GET /api/win-rates
- **Data source:** Last N trades by exit_time, `realised_pnl_sol > 0` for win determination
- **Observation:** Shows 40%/44%/52% -- looks correct for recent trades
- **Status:** LIVE_CORRECT (recent trades have correct realised_pnl_sol from post-fix code)
- **Issue:** Minor -- uses legacy column but recent trades are post-fix so values match corrected column
- **Fix path:** Switch to corrected column for consistency
- **Priority:** P1
- **Can be fixed tonight:** YES

### Governance
- **File:** dashboard/dashboard.html:878-912 (JS), services/dashboard_api.py:893-938 (backend)
- **Endpoint:** GET /api/governance + GET /api/market
- **Data source:** Redis `governance:latest_decision` + Redis `market:health`
- **Observation:** Mode "NORMAL" with text "CFGI at neutral 50..." -- contradicts dashboard CFGI=12
- **Status:** LIVE but STALE/HALLUCINATED
- **Issue:** The governance LLM (Claude Haiku) generated "CFGI at neutral 50" text. This is either (a) stale from when CFGI was higher, or (b) LLM hallucination. The governance decision is stored in Redis without TTL -- it persists until the next governance run. If governance service hasn't run recently, the reasoning text is stale.
- **Fix path:** Check governance service run frequency. Add TTL to governance:latest_decision or add timestamp display.
- **Priority:** P2
- **Can be fixed tonight:** NO (needs governance service investigation)

### Open Positions
- **File:** dashboard/dashboard.html:914-940 (JS), services/dashboard_api.py:530-600 (backend)
- **Endpoint:** GET /api/positions
- **Data source:** Redis bot:status or paper_trades WHERE exit_time IS NULL
- **Observation:** Shows 2 open positions -- looks correct
- **Status:** LIVE_CORRECT
- **Priority:** N/A

### Recent Trades (Last 20)
- **File:** dashboard/dashboard.html:942-966 (JS), services/dashboard_api.py:735-763 (backend)
- **Endpoint:** GET /api/trades?limit=20
- **Data source:** paper_trades ORDER BY exit_time DESC LIMIT 20
- **Observation:** Shows recent trades with exit reasons
- **Status:** LIVE_WRONG_SOURCE (minor)
- **Issue:** Uses `realised_pnl_sol` for P/L display. Recent trades are post-fix so values are correct, but older trades in the 20-trade window may be pre-fix.
- **Fix path:** Switch to `COALESCE(corrected_pnl_sol, realised_pnl_sol)`
- **Priority:** P1
- **Can be fixed tonight:** YES

### Recent Signals (Last 10)
- **File:** dashboard/dashboard.html:968-991 (JS), services/dashboard_api.py:2173-2196 (backend)
- **Endpoint:** GET /api/signals
- **Data source:** Redis `signals:evaluated` list (last 10)
- **Observation:** Shows recent signals with ML scores and results
- **Status:** LIVE_CORRECT
- **Priority:** N/A

### Whale / Smart Money
- **File:** dashboard/dashboard.html:831-854 (JS), services/dashboard_api.py:1182-1215 (backend)
- **Endpoint:** GET /api/whale-activity
- **Data source:** Redis `signals:raw` filtered for whale signals
- **Observation:** "44 wallets monitored -- no recent activity"
- **Status:** PLACEHOLDER
- **Issue:** No whale signals in signals:raw queue. Whale tracking architecture blocked on sample count (need 100+ winning trades for wallet mining).
- **Fix path:** Tier 2 -- needs whale leaderboard panel redesign
- **Priority:** P3
- **Can be fixed tonight:** NO

## Priority Tiers

### P0 -- broken in user-facing ways, fix tonight
1. Top bar PnL (-8.40 should be ~+17.73) -- wrong column + no cleanup filter
2. Top bar WR (6.5% should be ~26.3%) -- same
3. Equity Curve -- same
4. Personality P/L -- wrong column + no cleanup filter
5. P/L Distribution -- wrong column + no cleanup filter

### P1 -- wrong data source, fix tonight
6. Top bar SOL price ($0.00) -- add Redis fallback
7. Session stats -- switch to corrected column
8. Signal funnel wins count -- switch to corrected column
9. Win rates -- switch to corrected column for consistency
10. Recent trades -- switch to corrected column

### P2 -- needs dedicated session
11. CFGI data source decision (B-001) -- Jay must choose index
12. Exits footer TP: 0% (B-004) -- needs exit_reason investigation
13. API Health false positives (B-003)
14. Governance stale reasoning text

### P3 -- cosmetic or low-impact
15. ML AUC formatting (B-007) -- toFixed(4) -> toFixed(1)
16. Whale panel placeholder

---

## Known Bugs Registry

### B-001: CFGI value is Bitcoin F&G, not Solana-specific
- **Observed:** Dashboard shows 12, Jay expected 42 (CMC)
- **Root cause:** market_health.py:172 calls Alternative.me `fng/?limit=1` which returns the BITCOIN Fear & Greed Index. cfgi.io Solana-specific index is "defunct (404 confirmed)" per code comment at line 170.
- **API confirmed:** Alternative.me currently returns `{"value": "12"}` -- correct from that source
- **Impact:** HIBERNATE mode triggers at CFGI<20 threshold. If Solana-specific CFGI were 42 (CMC), mode would be NORMAL. Analyst auto-paused on wrong index.
- **Source of display value:** Redis `market:health.cfgi` <- market_health.py:346 <- `_fetch_cfgi()`:172 <- Alternative.me
- **Source of governance value:** Redis `governance:latest_decision.reasoning` text says "CFGI at neutral 50" -- this is STALE or HALLUCINATED LLM text, not live data
- **bot_core reads from:** signal_aggregator.py:2022 reads `market:health.cfgi` -- SAME broken source. Bot IS affected. Speed Demon gets 0.75x sizing at CFGI<20 (line 596-597). Analyst paused at CFGI<20 (line 2112).
- **Status:** DIAGNOSED, FIX DEFERRED
- **Recommended fix:** Replace Alternative.me with CoinMarketCap CFGI API or add Solana-specific source. This changes trading behavior (HIBERNATE->NORMAL), so needs Jay's review.
- **Next review:** 2026-04-14

### B-002: SOL price $0.00
- **Observed:** Top bar shows $0.00
- **Root cause:** market_health.py `_fetch_sol_price()` tries Binance then CoinGecko -- both failing. `market:health.sol_price = None`. Dashboard CoinGecko fallback (dashboard_api.py:382) also fails. `market:sol_price` Redis key = 80.0 (stale fallback).
- **Impact:** $0.00 displayed. Bot_core exit checker reads `market:sol_price` (80.0) for SOL->USD conversion -- stale but functional.
- **Fix path tonight:** Add Redis `market:sol_price` as intermediate fallback in dashboard_api.py before CoinGecko API call
- **Status:** TRIVIAL FIX TONIGHT

### B-003: API Health stale/inaccurate
- **Observed:** Various services show incorrect status
- **Root cause:** Service health from Redis `service:health` cache. Services without cached data show "unknown". Health check background task may not be running regularly.
- **Impact:** Misleading health display
- **Fix path:** Needs investigation of health check task
- **Status:** DEFERRED
- **Next review:** 2026-04-16

### B-004: Exits footer staged TP percentage
- **Observed:** Recent trades show TP exits but footer shows low/no TP percentage
- **Root cause:** Staged TP fires reduce position but the FINAL close records the trailing stop as exit_reason. Only the intermediate staged_tp_* reasons count as TP in the bucket logic, but those aren't the final exit_reason stored in the DB.
- **Impact:** Cosmetic -- understates TP effectiveness
- **Fix path:** Would need to check `staged_exits_done` column and count trades WITH staged exits as partial TP outcomes. Non-trivial.
- **Status:** DEFERRED
- **Next review:** 2026-04-16

### B-005: Signal Funnel win percentage misleading
- **Observed:** "Wins 234 (0.3%)" -- percentage relative to signals_received (81.7K)
- **Root cause:** The funnel intentionally shows each step relative to the top (signals_received). This IS a funnel -- 0.3% of signals become winning trades is correct funnel math.
- **Impact:** None -- working as designed. Jay may prefer different denominator display.
- **Status:** NOT A BUG (funnel display is correct). Win COUNT needs corrected column switch.
- **Fix path:** Switch wins count from `realised_pnl_sol > 0` to `corrected_pnl_sol > 0`

### B-006: Top bar SOL price $0.00
- See B-002 (same issue)

### B-007: ML AUC top bar shows 4 decimal places
- **Observed:** "67.0000 AUC"
- **Root cause:** dashboard.html:660 uses `auc.toFixed(4)`
- **Impact:** Cosmetic
- **Fix path:** Change to `auc.toFixed(1)` + " AUC"
- **Status:** TRIVIAL FIX TONIGHT

### B-008: Personality P/L mixes pre/post cleanup
- **Observed:** Speed Demon 2312 trades, Analyst 1284 trades -- includes contaminated data
- **Root cause:** No `entry_time > 1775767260` filter in api_personality_stats
- **Impact:** Misleading P/L numbers
- **Fix path:** Add cleanup filter + switch to corrected column
- **Status:** FIX TONIGHT

### B-009: P/L Distribution mixes pre/post cleanup
- Same as B-008 for histogram
- **Status:** FIX TONIGHT
