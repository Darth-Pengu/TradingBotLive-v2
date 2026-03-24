# ToxiBot v3.0 — Solana Memecoin Trading Bot

Autonomous Solana memecoin trading bot with three concurrent AI personalities, ML scoring, market health detection, agent governance, and a real-time web dashboard.

## Architecture

8 independent services running on Railway:

| Service | Purpose |
|---------|---------|
| `signal_listener` | PumpPortal WS + GeckoTerminal + DexPaprika signal ingestion |
| `market_health` | Composite sentiment scoring, market mode detection, emergency alerts |
| `signal_aggregator` | Dedup, multi-source confidence, Rugcheck gate, ML gate, personality routing |
| `ml_engine` | CatBoost + LightGBM ensemble scoring, weekly retrain |
| `bot_core` | 3-personality coordinator, staged exits, EMERGENCY_STOP |
| `execution` | PumpPortal Local API + Jupiter Ultra API + Jito MEV protection |
| `treasury` | Auto-sweep excess SOL to holding wallet |
| `governance` | Claude API strategic oversight (daily briefings, wallet rescoring) |
| `dashboard_api` | Web dashboard + REST API + WebSocket real-time updates |

## Three Personalities

- **Speed Demon** — Ultra-early pump.fun sniper with tiered entries (0-30s, 30s-3min, post-grad dip)
- **Analyst** — Data-driven researcher, medium-term positions (5min-2hr), multi-source signal confirmation
- **Whale Tracker** — Smart money copy-trading with scored wallet list (50-100 wallets)

## Execution Layer

No Telegram dependency. Two clean REST APIs:
- **PumpPortal Local API** — bonding curve tokens, Jito MEV-protected
- **Jupiter Ultra API** — graduated AMM tokens, built-in MEV protection

## Deploy to Railway

### 1. Prerequisites

- Railway account with Redis plugin
- Helius Developer tier ($49/mo)
- Anthropic API key (for governance agent)
- Discord webhook URL (for alerts)
- Solana trading wallet keypair
- Separate holding wallet (Phantom — public key only)

### 2. Setup

```bash
# Clone
git clone https://github.com/Darth-Pengu/TradingBotLive-v2.git
cd TradingBotLive-v2

# Copy env template
cp .env.example .env
# Fill in all values in .env
```

### 3. Required Environment Variables

See `.env.example` for the full list. Critical ones:

```
HELIUS_API_KEY=           # Helius Developer tier
HELIUS_RPC_URL=           # Helius RPC endpoint
TRADING_WALLET_PRIVATE_KEY=  # Base58 — NEVER commit
TRADING_WALLET_ADDRESS=   # Public key
HOLDING_WALLET_ADDRESS=   # Public key ONLY
REDIS_URL=                # Railway Redis plugin
ANTHROPIC_API_KEY=        # For governance agent
DISCORD_WEBHOOK_URL=      # Alert notifications
TEST_MODE=true            # KEEP TRUE until ready
```

### 4. Railway Deployment

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and link
railway login
railway link

# Add Redis plugin in Railway dashboard

# Deploy
git push origin main  # Railway auto-deploys from main
```

### 5. Service Startup Order

Railway starts all services simultaneously, but `bot_core` waits up to 60s for `market_health` to publish the initial market mode. Recommended manual startup order for testing:

1. **market_health** — must publish market mode first
2. **signal_listener** — starts ingesting signals
3. **ml_engine** — loads/trains ML models
4. **signal_aggregator** — processes and scores signals
5. **treasury** — starts balance monitoring
6. **bot_core** — starts trading (waits for market mode)
7. **governance** — scheduled/triggered tasks
8. **dashboard_api** (web) — serves dashboard

### 6. Testing Protocol

1. Set `TEST_MODE=true` and `ENVIRONMENT=development`
2. Start services and verify signals are being detected (check logs)
3. Test treasury sweep with 0.001 SOL transfers
4. Test governance with `max_tokens=100`
5. Paper trade for minimum 48 hours
6. Start live with 0.1 SOL test positions
7. Scale to full sizing after 20+ successful trades
8. Only then set `TEST_MODE=false`

## Dashboard

- **Overview** (`/dashboard/dashboard.html`) — wallet balances, treasury sweep, personality leaderboard, market mode, EMERGENCY STOP
- **Analytics** (`/dashboard/dashboard-analytics.html`) — per-personality stats, portfolio chart, ML distribution, governance notes
- **Trade Feed** (`/dashboard/dashboard-wallet.html`) — live signals, active positions, closed trades, whale activity

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Bot status overview |
| `/api/market-health` | GET | Current market mode and sentiment |
| `/api/trades` | GET | Recent trades (last 50) |
| `/api/trades/active` | GET | Open positions |
| `/api/personality-stats` | GET | Per-personality performance |
| `/api/treasury` | GET | Treasury sweep data and history |
| `/api/governance` | GET | Latest governance notes |
| `/api/portfolio-history` | GET | Portfolio snapshots |
| `/api/emergency-stop` | POST | Trigger EMERGENCY_STOP |
| `/ws` | WS | Real-time WebSocket updates |

## Safety

- `TEST_MODE=true` = zero trades (not reduced)
- 25% max portfolio exposure
- 60% reserve floor
- 1.0 SOL daily loss limit → EMERGENCY_STOP
- 20% drawdown → STOP ALL TRADING
- Treasury sweep: one-directional (trading → holding only)
- Holding wallet private key never enters the system
- Jito tip hard cap: 0.1 SOL
