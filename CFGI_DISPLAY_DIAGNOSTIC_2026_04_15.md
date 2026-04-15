# CFGI Display Diagnostic — 2026-04-15

## Symptom
Dashboard top bar shows CFGI(BTC) = 45 and CFGI(SOL) = 45.
cfgi.io live values: BTC = 65, SOL = 50.
Two distinct issues:
1. BTC and SOL fields display the same value (should be different)
2. SOL value is 5 points off from cfgi.io website (45 vs 50)

## Layer Analysis

| Layer | BTC value | SOL value | Notes |
|---|---|---|---|
| cfgi.io website | 65 | 50 | Per Jay's screenshots ~19:25 AEDT |
| market_health fetch | not logged | 45 | `cfgi.io SOL CFGI: 45` in logs |
| Redis `cfgi` | — | 45 | Post-Stage-2 holds SOL value |
| Redis `cfgi_btc` | 23 | — | Stage-2 preserved BTC here |
| Redis `cfgi_sol` | — | 45 | Dashboard compat key |
| Dashboard API `fear_greed` | — | 45 | Reads `cfgi` key (now SOL) |
| Dashboard API `cfgi_sol` | — | 45 | Reads `cfgi_sol` key |
| Dashboard render CFGI(BTC) | 45 | — | **BUG: reads `fear_greed` = SOL value** |
| Dashboard render CFGI(SOL) | — | 45 | Correct |

## Diagnosis

### Bug A: BTC/SOL show same value — DASHBOARD DISPLAY BUG

**Root cause:** `dashboard_api.py:375` and `dashboard.html:738`

The chain:
1. `dashboard_api.py:375` sets `status_data["fear_greed"] = mh.get("cfgi")`
2. Pre-Stage-2, `market:health.cfgi` held the BTC value — this was correct
3. Post-Stage-2 (commit eebccf5), `market:health.cfgi` now holds the
   **SOL** value — the swap was intentional for bot_core compatibility
4. Dashboard API was NOT updated during Stage 2 — it still reads `cfgi`
   and labels it as `fear_greed` (implying BTC F&G)
5. Dashboard API **never reads `cfgi_btc`** — this new key has no consumer
6. `dashboard.html:738` renders `data.fear_greed` under the "CFGI(BTC)" label
7. Result: both CFGI(BTC) and CFGI(SOL) display the same SOL value (45)

**Fix:** In `dashboard_api.py:375`, add:
```python
status_data["cfgi_btc"] = float(mh.get("cfgi_btc") or mh.get("cfgi", 0))
```
In `dashboard.html:738`, change the CFGI(BTC) renderer to read
`data.cfgi_btc` instead of `data.fear_greed`.

**Severity:** Cosmetic only. Bot uses `market:health.cfgi` (SOL value,
correct) for mode decisions. The BTC display label is wrong but the
underlying trading data is correct.

### Bug B: SOL value 5 points off from cfgi.io website — API PARAMETER GAP

**Root cause:** `market_health.py:198` uses `period=2` (1-hour granularity)

The chain:
1. cfgi.io website displays a "Now" value (possibly real-time or
   15-min granularity)
2. Our API call uses `period=2` which maps to 1-hour granularity
3. market_health logs confirm the API is returning 45 (not 50)
4. The 5-point gap is between cfgi.io's real-time display and their
   1-hour API value — this is expected behavior for a smoothed index

**Note:** Alternative.me's BTC F&G shows 23 in our Redis, but Jay
saw 65 on cfgi.io's BTC display. This is because cfgi.io has its
OWN Bitcoin CFGI index which differs from Alternative.me's Bitcoin
F&G index. They are different indices with different methodologies.
Our `cfgi_btc` (23) comes from Alternative.me, not cfgi.io.

**Fix options:**
- Change `period=1` (15-min) for more responsive values — minor
- Accept the 1-hour smoothing as a feature not a bug — no change needed
- Add a period parameter to the cfgi.io fetch to experiment

**Severity:** Cosmetic. The 5-point smoothing delay doesn't affect
trading decisions meaningfully.

## Severity Assessment
- Trading impact: NONE — bot reads `market:health.cfgi` correctly
- Decision impact: NONE — mode is volume-driven (HIBERNATE), CFGI
  affects sizing/sentiment only
- User confusion: YES — Jay sees mismatched values, questions data
  integrity

## Fix Plan (NOT executed in this session)

**Bug A fix (display mismatch):**
- Files: `services/dashboard_api.py` (add `cfgi_btc` to response),
  `dashboard/dashboard.html` (read `cfgi_btc` for BTC label)
- Estimated: 10 minutes
- Bundle with B-013 (dashboard token name) for a cleanup session

**Bug B fix (optional, smoothing gap):**
- File: `services/market_health.py` (change `period=2` to `period=1`)
- Estimated: 5 minutes
- Consider whether 1h smoothing is actually better for trading stability

## Data Quality Notes
- Redis values are fresh (timestamp 09:29 UTC, within 5-min cycle)
- market_health is healthy and cycling normally
- cfgi.io API is returning valid data (credits restored)
- The BTC value discrepancy (23 vs 65) is NOT a bug — it's two
  different indices: Alternative.me F&G (23) vs cfgi.io Bitcoin CFGI (65)
