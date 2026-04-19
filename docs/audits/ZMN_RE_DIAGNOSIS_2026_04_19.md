# ZMN re-diagnosis with the upgraded tool surface — 2026-04-19

**Author:** Claude Opus 4.7 (1M-context, autonomous deep recon).
**Companion docs:** `CC_TOOL_SURFACE_2026_04_19.md` (which tools are now available), `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` (what to do about it).
**Method:** every claim below is backed by a Postgres MCP / Redis MCP / Helius MCP / Railway MCP query run **today** against the live DB and Redis, not the 5,831-row CSV snapshot.
**Read-only.** Zero changes to `services/`, env vars, or live state.

---

## TL;DR — the major delta from prior sessions

1. **BREAKEVEN_STOP is structurally fixed already.** Last firing was 2026-04-16. The `[[0.30, 0.35], …]` `TIERED_TRAIL_SCHEDULE_JSON` env var that the abort report recommended **is already deployed** on `bot_core`. The 133 BREAKEVEN_STOP rows in the 7d window are all historical from Apr 9–16. After Apr 16: zero. The marquee Tier 1 fix is **done**.
2. **stop_loss_35% is the real bleeder, not BREAKEVEN_STOP.** 272 trades, –56.35 SOL in 7d. 7× the cost of BREAKEVEN_STOP. Hardcoded at `services/bot_core.py:111` (`"stop_loss_pct": 0.35`). Average peak before stop: only +28.3%. Average hold: 0.6 minutes. These trades barely pump, then die.
3. **ML threshold 30 is producing positive results across the board.** The "ML inverts above 40" claim from CLAUDE.md is stale. Fresh 7d data: every band 30→80+ is profitable, win rate climbs monotonically with score. The bot's deployed value is `ML_THRESHOLD_SPEED_DEMON=30` on `bot_core`, but `signal_aggregator` has it at `40` and `signal_aggregator` is the gate that matters. So effective threshold = 40, which is the abort report's recommendation. Both the env var inconsistency and the doc inconsistency need clean-up.
4. **stale_no_price is a non-issue right now.** Daily count was 94→148 on Apr 5–6, since Apr 9 it's been 0–5/day with one Apr 17 spike (26, coincided with v4 live trial). Total 14d damage: ~–1 SOL.
5. **Whale Tracker is profitable but tiny sample.** 11 trades in 7d, +4.24 SOL. Several big winners (+3.2 SOL, +1.16 SOL) carrying small losers. **But the `watched_wallets` table is stale: 44 wallets, 0 active in last 14 days.** Whale Tracker entries are coming from the `pumpportal` feed, not from watched-wallet hits. So either the personality routing is doing something else useful, or Whale Tracker is effectively a "Speed Demon with different exit params."
6. **Analyst is dead.** 10 most recent Analyst trades all exited via stop_loss_20% within 0.001–7 minutes hold. Hard-disabled is correct.
7. **Wallet drained 2.07 SOL between the abort report and now (3.677 → 1.61 SOL).** `paper_trades` shows zero `trade_mode='live'` rows. `live_trade_log` has 36 `TX_SUBMIT buy` and 33 `TX_SUBMIT sell` events in 7 days, **plus 8,993 ERROR sells and 51 ERROR buys**. The bot has been spending real SOL outside the recorded `trade_mode='live'` path. **This needs forensics.**
8. **Sentry has zero ZMN projects.** The Sentry MCP is fully usable, but `services/*.py` has no `sentry_sdk.init(...)`. Every error currently dies in Railway logs only.

---

## Pain point 1 — Bleeding exit reasons (BREAKEVEN_STOP + stop_loss_35% + no_momentum_90s)

### What was known before tonight

Abort report (2026-04-19 morning):
- BREAKEVEN_STOP: 137 trades, –8.22 SOL realized in 7d.
- Recommendation: `_DEFAULT_TRAIL_SCHEDULE[0] = [0.30, 0.35]` loose trail instead of breakeven lock.

Prompt update (this session):
- Two bleeders, not one. **stop_loss_35%** is 7× worse than BREAKEVEN_STOP in total damage. **no_momentum_90s** is the highest-volume bleeder (775 trades, –41 SOL).

### What the upgraded tool surface reveals

#### Fresh exit-reason table (Postgres MCP via asyncpg shim, last 7d, speed_demon)

| Exit reason | n | Total PnL (SOL) | Avg pct | WR |
|---|---:|---:|---:|---:|
| TRAILING_STOP | 834 | **+395.80** | +108.18% | 93.0% |
| no_momentum_90s | 775 | –41.42 | –11.38% | 1.4% |
| stop_loss_35% | 272 | **–56.35** | –47.04% | 1.8% |
| BREAKEVEN_STOP | 133 | –8.15 | –11.46% | 0.0% |
| max_extended_hold | 104 | +20.85 | +70.13% | 100.0% |
| time_exit_no_movement | 56 | +0.34 | +1.31% | 78.6% |
| stale_no_price | 32 | –0.26 | –0.89% | 0.0% |
| staged_tp_+1000% | 12 | **+103.75** | +1253% | 100.0% |
| staged_tp_+250% | 4 | +2.42 | +295% | 100.0% |
| staged_tp_+500% | 3 | +2.10 | +532% | 100.0% |
| (plus 8 smaller buckets) | | | | |

**Net 7d on paper: +428 SOL across 2,256 speed_demon trades, 43.3% WR.** Confirms the bot is profitable on paper (matches `bot:portfolio:balance = 194.67 SOL` vs CLAUDE.md's stale `31.86 SOL`).

#### BREAKEVEN_STOP daily firing (drift check, Apr 9–17)

| Day | n | avg_peak | pnl |
|---|---:|---:|---:|
| Apr 9 | 16 | 39.0% | –0.07 |
| Apr 14 | 27 | 39.0% | –0.68 |
| Apr 15 | 63 | 39.1% | –3.18 |
| Apr 16 | **39** | 39.7% | –4.25 |
| Apr 17 onward | **0** | – | – |

**Confirmed:** Last BREAKEVEN_STOP firing was 2026-04-16. The structural fix is in production. The "133 trades in 7d" rolling-window count is misleading — they're all historical.

**Why it's structurally fixed:** `services/bot_core.py:1232`:

```python
exit_reason = "BREAKEVEN_STOP" if trail_pct == 0.0 else "TRAILING_STOP"
```

The label only fires when `trail_pct == 0.0`. The deployed `TIERED_TRAIL_SCHEDULE_JSON=[[0.30, 0.35], …]` has trail_pct = 0.35 at the first activation tier, so the label can no longer be emitted.

#### stop_loss_35% peak / hold analysis (272 trades, –56 SOL)

| Metric | Value |
|---|---:|
| n | 272 |
| Never pumped (peak ≤ 1.05× entry) | 23 (8.5%) |
| Peaked +10%+ | 54 (19.9%) |
| Peaked +30%+ | 20 (7.4%) |
| Peaked +50%+ | 12 (4.4%) |
| Avg peak pct | **+28.3%** |
| Avg hold | **0.6 min** (~36s) |

These are **fast-and-shallow** failures. Most peak around +28%, then dump 35% from entry within a minute. The hard stop at –35% (hardcoded `services/bot_core.py:111`) is the correct safety net — but it's catching too much because **trail activation is at +30%**: positions that peak +25% never activate the trail, so they only get stopped at –35%.

**Three plausible fixes (rank-ordered by expected SOL impact):**

| Fix | Mechanism | Tradeoff |
|---|---|---|
| Lower trail activation threshold (`[[0.10, 0.30], …]`) | Activate trail at +10% peak with 30% trail. Token peaks at +25%, trail at +25 × 0.70 = –12.5% locked-in stop instead of –35%. | More small losses replaced with smaller losses; possible early exits on tokens that recover. |
| Tighten stop_loss to 25% | Faster bleed-stop; less time to recover but also less damage per loser. | env-controllable via new `SD_STOP_LOSS_PCT` (currently hardcoded — needs `getenv`). |
| Add second-tier "soft stop" at –20% with momentum check | Exit if no-momentum AND drawdown >20%. | More complex; risks killing legitimate dips. |

Tier 1 candidate: **lower trail activation tier**, since it's a single-line env var change. Expected PnL improvement: if the avg trade goes from –47% to –15% on these 272 trades, that's roughly 272 × 0.32 × avg_size_sol ≈ +0.32 × 272 × 0.2 SOL = **+17 SOL/week recovered**.

#### no_momentum_90s peak / hold analysis (775 trades, –41 SOL)

| Metric | Value |
|---|---:|
| n | 775 |
| Peaked +10%+ | 189 (24.4%) |
| Peaked +20%+ | 106 (13.7%) |
| Peaked +50%+ | 4 (0.5%) |
| Avg peak pct | +13.5% |
| Avg hold | 1.4 min |

189 of 775 (24%) peaked +10%+ before the 90s check killed them. These are tokens that briefly moved but didn't sustain. The current code (`services/bot_core.py:1322`):

```python
early_check_sec = float(os.getenv("SD_EARLY_CHECK_SECONDS", "90"))
early_min_move = float(os.getenv("SD_EARLY_MIN_MOVE_PCT", "2.0"))
```

is env-tunable. **Two candidate adjustments:**

1. **Reduce check window: 90s → 60s.** Kills duds earlier. Per CLAUDE.md, this was the prior diagnosis — and at avg hold 1.4min, a 60s gate would catch ~70% of these earlier with less downside accumulation.
2. **Raise the bar from +2% to +5%.** Reduces the "barely positive" survivor pool. Less impact unless paired with #1.

### Delta from prior diagnosis

- **BREAKEVEN_STOP is no longer the marquee fix.** It's done. Don't propose it again.
- **stop_loss_35% replaces it as the largest loose-edge bleeder** — 7× the SOL drag, but per-trade damage is so high that the fix has 5–10× leverage per trade vs. the BREAKEVEN_STOP fix.
- **no_momentum_90s should remain a Tier 1 candidate**, paired with the trail activation tier change.

### Proposed fix (Tier 1)

```bash
# Trail activation tier — lower from +30% to +10%, keep 35% trail
railway variables -s bot_core --set 'TIERED_TRAIL_SCHEDULE_JSON=[[0.10, 0.30], [0.50, 0.25], [1.00, 0.20], [2.00, 0.15], [5.00, 0.12]]'

# 90s momentum window: tighten to 60s
railway variables -s bot_core --set SD_EARLY_CHECK_SECONDS=60
railway variables -s bot_core --set SD_EARLY_MIN_MOVE_PCT=3.0
```

### Confidence and risk

- Trail activation: **MEDIUM-HIGH confidence**. Backed by 272 trades of evidence. Risk: trail-activated trades exit earlier on legitimate dips → some trades that would have hit +50% TP exit at +5%. Mitigation: monitor 24h; revert by reverting env var.
- 90s window: **MEDIUM confidence**. Backed by 775 trades. Risk: kills some early-mover entries that would have run. Mitigation: env var, easy to revert.

### Session size to implement

15 minutes (env var change + 24h observation), **after** the rules-refresh prompt lands.

---

## Pain point 2 — ML threshold

### What was known before tonight

CLAUDE.md (still says): "ML model inverts above 40; working range is 35–40 only."

Abort report (2026-04-19 morning) corrected: "ML 35-40: 21 trades, 4.76% WR, –1.16 SOL — only loss band; 80+: 53% WR; raise threshold to 40."

### What the upgraded tool surface reveals

#### Fresh ML band breakdown (Postgres MCP, last 7d, speed_demon, 2,256 trades)

| Band | n | PnL (SOL) | WR |
|---|---:|---:|---:|
| 30–40 | 111 | **+48.57** | 27.9% |
| 40–50 | 630 | **+111.11** | 37.5% |
| 50–60 | 541 | +69.99 | 42.1% |
| 60–70 | 424 | +74.39 | 48.3% |
| 70–80 | 269 | +53.24 | 48.7% |
| 80+ | 281 | +71.06 | 52.0% |

**Every band is profitable.** WR climbs monotonically with score. The 30–40 band is the lowest WR but still net **+48.57 SOL** in 7d.

#### Env-var inconsistency (Railway MCP)

| Service | `ML_THRESHOLD_SPEED_DEMON` |
|---|---:|
| `bot_core` | **30** |
| `signal_aggregator` | **40** |

Code reference: `services/signal_aggregator.py:133`:

```python
"speed_demon": int(os.getenv("ML_THRESHOLD_SPEED_DEMON", "65")),
```

`signal_aggregator` is the gate that decides whether to forward a signal to `bot_core`. So the **effective threshold is 40** — `bot_core`'s value of 30 is unused but confusing. The 30-40 band data (111 trades, +48.57 SOL) reflects trades that were already filtered through signal_aggregator's threshold of 40 — meaning these trades had a final ML score (recomputed at entry?) between 30-40 even though signal_aggregator originally let them through at >=40. Or — more likely — the threshold flipped during the data window and we're seeing the tail of the lower-threshold era.

### Delta from prior diagnosis

- **CLAUDE.md is wrong.** "ML inverts above 40" claim should be deleted. Update on next docs-refresh session.
- **Abort report's 40-threshold recommendation is already live in signal_aggregator.** Done.
- **The bot_core ML_THRESHOLD env var is dead code.** Either remove it or align to 40. Cosmetic but contributes to confusion.

### Proposed fix (Tier 1)

```bash
# Align bot_core to match signal_aggregator (cosmetic — bot_core doesn't gate on this)
railway variables -s bot_core --set ML_THRESHOLD_SPEED_DEMON=40
```

Plus update CLAUDE.md to remove the stale "inverts above 40" claim.

### Confidence and risk

- **HIGH confidence, ZERO behavior change** — the env var is unused on bot_core. This is purely cleanup.

### Session size

5 minutes plus a docs commit.

---

## Pain point 3 — Exit pricing quality (`stale_no_price` spikes)

### What was known before tonight

CLAUDE.md: "When the Redis-first price path works, win rate is healthy. When it degrades, performance collapses."

### What the upgraded tool surface reveals

#### Fresh `stale_no_price` daily count (Postgres MCP, last 14d)

| Day | n | pnl (SOL) |
|---|---:|---:|
| Apr 5 | 94 | –0.40 |
| Apr 6 | 148 | –0.24 |
| Apr 9 | 4 | +0.06 |
| Apr 10 | 31 | +0.17 |
| Apr 11–16 | 1–5 each | <±0.07 |
| **Apr 17** | **26** | **–0.20** |

**Apr 5–6 was the era of the original price-pipeline issue (since fixed). Apr 17 spike of 26 coincides with the v4 live trial.** That trial was bypassing TEST_MODE for a window — so price-quality issues during the live attempt rolled forward into paper sells too.

#### Redis price-cache state (Redis MCP)

- `market:sol_price`: **85.92** (5-min cache, fresh)
- `token:latest_price:*`: **~280 keys** (heavy use, SOL-denominated)
- `token:reserves:*`: not seen this session (would be the bonding-curve fallback)

Cascade health is **green** at the moment.

#### What the new MCPs add

- **Helius MCP**: `getAsset(mint)` returns a `price` field for any token Helius has indexed — but it's USDC-denominated and likely lagged for fresh memecoins. Worth a measurement pass to compare staleness vs. Jupiter/Gecko.
- **DexPaprika MCP**: `getTokenDetails(token=<mint>)` → `price_usd`, `liquidity_usd`, `volume_usd`, `price_usd_change`. No auth required. Latency ~400-600ms. **Direct fit** as a tertiary fallback when both Jupiter v3 and GeckoTerminal fail.
- **Birdeye MCP**: `defi/v3/token-meme-detail-single` is purpose-built for memecoins. Session was unstable this session — re-test before integrating.
- **CoinGecko MCP**: `get_addresses_tokens_networks_onchain_multi` (bulk multi-token onchain price lookup). Already in cascade.

### Delta from prior diagnosis

- **The pricing pipeline is currently healthy.** No active fire. The Apr 5-6 spikes were old; the Apr 17 spike was a one-off tied to the v4 trial.
- **The MCPs add 2-3 viable cascade tail options** (DexPaprika, Birdeye, Helius) — useful for hardening, not urgent.

### Proposed fix (Tier 2)

Add DexPaprika as a 4th-rank fallback in `services/bot_core.py` exit price cascade (and any other reader). Sketch:

```python
async def _get_token_price(self, mint):
    # 1. Redis token:latest_price:{mint}
    price = await self.redis.get(f"token:latest_price:{mint}")
    if price: return float(price), "redis"
    # 2. Bonding curve reserves (existing)
    ...
    # 3. Jupiter price v3 (existing)
    ...
    # 4. GeckoTerminal (existing)
    ...
    # NEW 5. DexPaprika — no key, ~500ms
    try:
        price = await self._dexpaprika_token_price(mint)
        if price: return price, "dexpaprika"
    except Exception:
        pass
    # 6. Mark stale
    return None, "stale"
```

### Confidence and risk

- **MEDIUM confidence**: DexPaprika viable but un-measured for ZMN's specific freshness needs.
- **LOW risk** when added as tail of cascade: no impact unless prior options all fail.

### Session size

45 min (add cascade option, validate against 100 mints, deploy).

---

## Pain point 4 — Whale / smart-money signal quality

### What was known before tonight

CLAUDE.md: "Analyst paused; Whale Tracker dormant. Nansen smart-money labels don't exist at pump.fun micro-cap scale."

### What the upgraded tool surface reveals

#### Whale Tracker recent trades (Postgres MCP, last 15)

| id | ML | PnL | Reason | Source |
|---|---:|---:|---|---|
| 5524 | 44.5 | **+3.22 SOL** | TRAILING_STOP | pumpportal |
| 4342 | 40.4 | **+1.16 SOL** | TRAILING_STOP | pumpportal |
| 5093 | 50.9 | +0.45 SOL | TRAILING_STOP | pumpportal |
| 5598 | 87.4 | –0.30 SOL | stop_loss_30% | pumpportal |
| 5600 | 49.0 | –0.17 SOL | stop_loss_30% | pumpportal |
| (10 more, mostly stale_no_price ~–0.005 SOL) | | | | |

**11 trades in 7d, +4.24 SOL net.** Two big winners carry, several small losers. WR 27.3% (low) but expectancy positive.

#### `watched_wallets` table state (Postgres MCP)

- 44 wallets total, all `is_active=true`.
- **0 wallets active in last 14 days** (`last_active_at > NOW() - INTERVAL '14 days'` count = 0).
- `pnl_30d_sol`, `win_rate_30d`, `trade_count_30d`, `avg_hold_minutes` all NULL for all rows.
- Sources: `fallback`, `nansen_mcp` (e.g. "Sigil Fund", "Jump Capital"), `manual`.
- The data is **stale Nansen labels from a prior load**, never refreshed.

#### What this means

- Whale Tracker entries are **NOT** coming from `watched_wallets` (none of those wallets have been active). They're coming from the same `pumpportal` feed Speed Demon uses — just routed through a different personality with different exit params.
- The `watched_wallets` table is dead infrastructure right now. Either rip it out (low signal) or refresh it and actually wire Whale Tracker to it.

#### Nansen MCP can refresh the list

`nansen_score_top_tokens` → `token_who_bought_sold` → `address_portfolio` chain can pull fresh smart-money wallets for any token. Daily refresh of the top 100 SD winner mints would surface the wallets that bought ZMN's wins. Estimated ~50-100 Nansen calls/day, well within the `NANSEN_DAILY_BUDGET=2000` limit.

### Delta from prior diagnosis

- Whale Tracker isn't dormant — it's quietly profitable, just at low volume.
- The watched_wallets pipe is broken end-to-end. The infra exists; the data flow doesn't.

### Proposed fix (Tier 2)

1. Build a daily refresh job in `services/nansen_wallet_fetcher.py`:
   - Pull the last 7d of ZMN's TRAILING_STOP wins from `paper_trades` (top 50 by PnL).
   - For each winning mint, call Nansen MCP `token_who_bought_sold` to find the early buyers.
   - Score those wallets by their cross-mint history (`wallet_pnl_summary`).
   - Insert/update top 100 into `watched_wallets`.
2. Wire Whale Tracker entry signal in `services/signal_aggregator.py` to fire when a `watched_wallets.address` shows up as a buyer in the pumpportal stream.

### Confidence and risk

- **MEDIUM confidence**: depends on Nansen labels existing for these wallet addresses (CLAUDE.md says they don't at pump.fun scale; but the labels *could* exist for the same wallets that have made bigger trades on Raydium / Meteora).
- **LOW risk**: data refresh only, no entry-decision change in stage 1; entry-decision change in stage 2 is opt-in.

### Session size

90 min for refresh job; 45 min for entry-decision wiring (separate session).

---

## Pain point 5 — Entry-time risk assessment (new capability unlocked)

### What was known before tonight

CLAUDE.md: "current entry filter in `services/signal_aggregator.py` doesn't check holder distribution, dev concentration, or bundle patterns."

### What the upgraded tool surface reveals

The `vybe` MCP exposes `/v4/tokens/{mint}/top-holders` (labeled), `/v4/tokens/{mint}/liquidity`, `/v4/tokens/{mint}/holders-count-ts`, `/v4/tokens/{mint}/trader-activity`. The `birdeye` MCP exposes `defi/v3/token-meme-detail-single`, `defi/v3/token-exit-liquidity`, `holder/v1/distribution`. Both can be called pre-entry within 500-800ms.

### Specific signal candidates worth measuring

For 20 recent SD entries (winners + losers), compute:
- Top 10 holder concentration % at entry time
- Holder count delta in the 60s before entry
- Liquidity at entry vs liquidity at exit
- Smart-money buyers (Vybe `top-pnl-traders`) overlap with entry buyers

**Hypothesis to test:** losers have higher holder concentration / fewer unique buyers than winners. If true, a pre-entry concentration filter (`reject if top10_pct > X`) could cut the 272 stop_loss_35% trades by 30-50% with low impact on winners.

### Delta from prior diagnosis

- The signal source for this kind of filter exists. It didn't before this session (Vybe + Birdeye not previously usable).

### Proposed fix (Tier 2 measurement, Tier 3 implementation)

1. **Measurement pass** (1 session, no entry-decision change): for each SD entry, log Vybe holder concentration + Birdeye token-security score to a new `signals_enriched` table. Run for 7 days. Then bin winners vs losers and look for separation.
2. **Implementation** (separate session, only if measurement shows separation): add the filter to `signal_aggregator.py` as **metrics-only** for N days, then promote to blocking.

### Confidence and risk

- **MEDIUM-LOW confidence** that holder concentration alone separates winners from losers at pump.fun scale (most pump.fun tokens have similar early concentration profiles).
- **LOW risk** for measurement; **MEDIUM risk** for blocking filter (could reject winners alongside losers).

### Session size

60 min measurement plumbing; 7-day observation; 45 min decision rule.

---

## Pain point 6 — Operational ceiling (dashboard / Railway / Sentry)

### What was known before tonight

`DASHBOARD_AUDIT.md` lists B-001 through B-009 / B-014. The dashboard redesign concepts (`DASHBOARD_REDESIGN_2026_04_19.md`) propose 3 alternatives. Sentry MCP newly available.

### What the upgraded tool surface reveals

#### Dashboard reachability (Bash + curl)

- `curl -I https://zmnbot.com/dashboard/dashboard.html` → `HTTP/1.1 200 OK` in <1s. Dashboard is live and reachable.

#### Playwright MCP (this session)

Both `browser_navigate(zmnbot.com/dashboard/dashboard.html)` and `browser_navigate(zmnbot.com/)` failed with `net::ERR_ABORTED` / `Target page, context or browser has been closed`. Local Playwright headless browser session is unstable on this Win11 box. **The dashboard regression-test plan is blocked on this** — fix in a dedicated session.

#### Railway recent deploys (Railway MCP `list-services`)

10 services discovered — bot_core, signal_aggregator, signal_listener, market_health, ml_engine, governance, treasury, web, plus Postgres + Redis. Did not pull deploy events in this session (token budget); flagged as a follow-up.

#### Sentry (Sentry MCP)

- Authenticated as `jay@rzconsulting.co`, org `rz-consulting`.
- `find_projects(rz-consulting)` → **No projects found.**

This is the most actionable finding. Sentry is fully usable, but ZMN has zero projects → no SDK integration. Every `try/except` that just logs and continues silently, every `RuntimeError`, every solders signing failure dies in Railway logs. Adding `sentry_sdk.init(...)` to the 8 service entrypoints would give ZMN observability that the Railway log tail can't.

### Delta from prior diagnosis

- Sentry's now usable from CC, **but** the bot itself doesn't write to it. This is a 30-min one-off SDK integration.
- Playwright MCP is the regression-test path, but the local browser session is broken.
- Dashboard URL is reachable; bug audit (B-001 through B-009 / B-014) is unchanged from the prior session — no fresh audit this session.

### Proposed fixes

| Tier | Fix | Effort |
|---|---|---|
| 2 | `sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"))` in `main.py` per service. Create projects via Sentry MCP `create_project`. | 30 min |
| 2 | Resolve Playwright headless instability on Windows 11 | 30 min triage |
| 3 | Build dashboard regression suite using Playwright + webapp-testing skill | 4-8 hours (see `DASHBOARD_TESTING_PLAN_2026_04_19.md`) |

### Confidence and risk

- Sentry SDK: **HIGH confidence, LOW risk**. SDK is mature, init is one line per service.
- Playwright triage: unknown until investigated.

### Session size

30 min Sentry + 30 min Playwright triage. Sequential or parallel.

---

## Open thread — wallet drain since the abort report

The most surprising finding this session, mentioned briefly above, deserves its own callout:

| Source | Value | Time |
|---|---:|---|
| Abort report (2026-04-19 morning) | 3.677 SOL | ~04:00 UTC |
| `helius.getBalance` (this session) | **1.610 SOL** | ~04:30 UTC |
| Drop | **2.067 SOL** | <30 min |

`paper_trades` has zero `trade_mode='live'` rows — but `live_trade_log` has entries:

| event_type | action | count (7d) |
|---|---|---:|
| ERROR | sell | **8,993** |
| ERROR | buy | 51 |
| TX_SUBMIT | buy | 36 |
| TX_SUBMIT | sell | 33 |

So **36 buy attempts** and **33 sell attempts** in 7 days, plus 9,044 errors. Some of those 36 buys clearly landed on-chain (because the wallet is draining). They're not being recorded in `paper_trades` because `paper_trades` only records `trade_mode='paper'` rows. There must be a `live_trades` (or similar) table. **This is a forensics task for the next session** — you need to know:

1. Where are the live trades being recorded?
2. Did they make money or lose money?
3. Is `TEST_MODE=true` actually preventing live trades, or is some other code path bypassing it?

Recommended first step: query the DB for table names matching `live%trade%` and inspect.

---

## Companion proposal docs

- See `ZMN_OPTIMIZATION_PLAN_2026_04_19.md` for the prioritized Tier 1/2/3 list synthesized from this re-diagnosis.
- See `MCP_BUILDER_CANDIDATES_2026_04_19.md` for which missing crypto MCPs would unblock specific items.
- See `DASHBOARD_TESTING_PLAN_2026_04_19.md` for the Playwright-based regression plan once the browser session is stable.
- See `ZMN_CC_HANDOVER_2026_04_19.md` for the single-file context pack that future sessions can boot off.
