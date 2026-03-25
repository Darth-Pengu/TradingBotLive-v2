# ZMN Bot v3.0 — Build Summary

## Files Created

### Services (8 files)
| File | Lines | Purpose |
|------|-------|---------|
| `services/__init__.py` | 1 | Package init |
| `services/signal_listener.py` | ~270 | PumpPortal WS + GeckoTerminal polling + DexPaprika SSE |
| `services/market_health.py` | ~230 | Composite sentiment, market modes, emergency detection |
| `services/treasury.py` | ~210 | SOL sweep to holding wallet (30 SOL trigger / 25 SOL target) |
| `services/execution.py` | ~310 | PumpPortal Local + Jupiter Ultra + Jito MEV + retry |
| `services/risk_manager.py` | ~250 | Quarter-Kelly, drawdown scaling, time-of-day, hard limits |
| `services/ml_engine.py` | ~300 | CatBoost + LightGBM ensemble, 26 features, weekly retrain |
| `services/signal_aggregator.py` | ~350 | Dedup, multi-source confidence, Rugcheck, ML gate, routing |
| `services/bot_core.py` | ~400 | 3-personality coordinator, staged exits, EMERGENCY_STOP |
| `services/governance.py` | ~310 | Claude API governance agent (scheduled + triggered) |
| `services/dashboard_api.py` | ~300 | aiohttp web server, REST API, WebSocket |

### Dashboard (3 files)
| File | Purpose |
|------|---------|
| `dashboard/dashboard.html` | Bot Overview — treasury panel, personality leaderboard, market mode, EMERGENCY STOP |
| `dashboard/dashboard-analytics.html` | Performance & ML — per-personality stats, drawdown, ML distribution, governance notes |
| `dashboard/dashboard-wallet.html` | Live Trade Feed — signal feed, active positions, closed trades, whale activity |

### Config & Data (5 files)
| File | Purpose |
|------|---------|
| `.env.example` | All environment variables with descriptions |
| `Procfile` | Railway process definitions (8 services) |
| `railway.toml` | Railway build/deploy config |
| `data/whale_wallets.json` | Empty array (schema for whale wallet list) |
| `data/governance_notes.md` | Header for governance agent output |

### Documentation (2 files)
| File | Purpose |
|------|---------|
| `README.md` | Complete deployment guide |
| `BUILD_SUMMARY.md` | This file |

### Updated (1 file)
| File | Change |
|------|--------|
| `requirements.txt` | Replaced old deps (telethon, Flask) with new stack (solders, catboost, anthropic, etc.) |

---

## Decisions Made (Not Explicitly Specified)

1. **PumpPortal WS message classification**: Classified messages by checking `txType`, `bondingCurveKey`, and `pool` fields since the exact message schema wasn't documented. Left comments explaining the heuristic.

2. **Pump.fun volume estimation**: In `market_health.py`, estimated pump.fun volume as ~15% of total Solana DEX volume from DefiLlama since there's no direct pump.fun volume API. Comment added explaining this can be refined with PumpPortal stats.

3. **Graduation rate default**: Defaulted to 1.0% (NORMAL range) since there's no direct API for pump.fun graduation rate. This should be refined by counting `subscribeMigration` events in `signal_listener` and feeding them to `market_health`.

4. **ML model serialization**: Used pickle for CatBoost/LightGBM model persistence to `data/models/`. Standard approach for sklearn-compatible models.

5. **ML neutral score**: When model isn't trained yet (< 50 samples), returns 50.0 (neutral) to allow the system to operate in data-collection mode.

6. **Dashboard CSS**: Built custom TRON glassmorphism theme inline (no external framework dependency). Dark background with neon green accents.

7. **WebSocket client management**: Simple set-based tracking with automatic cleanup on disconnect.

8. **Treasury DB path**: Used `DATABASE_PATH` env var defaulting to `toxibot.db` for both treasury sweeps and trades tables in the same SQLite file.

9. **DexPaprika SSE URL**: Used `https://api.dexpaprika.com/v1/solana/events/stream` — may need adjustment based on actual API docs. Wrapped in robust reconnection logic.

10. **Bot core imports**: `bot_core.py` imports from `services.execution` and `services.risk_manager` as sibling modules. This works when run as `python services/bot_core.py` from the project root, or with proper Python path setup on Railway.

11. **Emergency stop double-confirmation**: Dashboard EMERGENCY STOP button requires two `confirm()` dialogs before triggering.

12. **Portfolio snapshot frequency**: Saves every 10 seconds (aligned with exit check loop).

---

## What You Need to Do Before Deploying

### Required (Must have)
- [ ] **Helius API key** — Sign up at helius.dev, Developer tier ($49/mo). Set `HELIUS_API_KEY` and `HELIUS_RPC_URL`
- [ ] **Trading wallet** — Generate a Solana keypair. Set `TRADING_WALLET_PRIVATE_KEY` (base58) and `TRADING_WALLET_ADDRESS`
- [ ] **Holding wallet** — Create in Phantom. Set `HOLDING_WALLET_ADDRESS` (public key ONLY)
- [ ] **Redis** — Add Redis plugin in Railway dashboard. `REDIS_URL` auto-set by Railway
- [ ] **Discord webhook** — Create in Discord server settings. Set `DISCORD_WEBHOOK_URL`
- [ ] **Fund trading wallet** — Transfer 20+ SOL to the trading wallet
- [ ] **Set `TEST_MODE=true`** — Already the default. Do NOT change until paper trading is validated

### Required for Governance Agent
- [ ] **Anthropic API key** — Get from console.anthropic.com. Set `ANTHROPIC_API_KEY`

### Optional (Improve signal quality)
- [ ] **Vybe Network API key** — Free tier at vybenetwork.xyz. Set `VYBE_API_KEY`
- [ ] **Nansen API key** — Pro tier ($49/mo) at nansen.ai. Set `NANSEN_API_KEY`

### Post-Deploy Checklist
- [ ] Verify `market_health` is publishing market mode (check logs)
- [ ] Verify `signal_listener` is receiving PumpPortal WS messages
- [ ] Verify `treasury` is reading wallet balance correctly
- [ ] Test EMERGENCY STOP from dashboard
- [ ] Run `TEST_MODE=true` for minimum 48 hours
- [ ] Review first governance daily briefing
- [ ] Test treasury sweep with small amount (temporarily lower threshold)
- [ ] After 20+ successful paper trades, consider switching to live

---

## Service Startup Order on Railway

Railway starts all Procfile services simultaneously. The built-in startup dependencies:

1. **market_health** — Publishes `market:mode` to Redis on startup
2. **bot_core** — Waits up to 60s for `market:mode` key before starting (falls back to DEFENSIVE)
3. **signal_aggregator** — Requires Redis (exits if Redis unavailable)
4. All other services start independently

For manual/local testing, start in this order:
```
1. market_health
2. signal_listener
3. ml_engine
4. signal_aggregator
5. treasury
6. bot_core
7. governance
8. dashboard_api
```
