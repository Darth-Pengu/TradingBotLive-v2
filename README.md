# ToxiBot Trading Bot - JSON API

A high-frequency Solana trading bot with advanced ML scoring, whale monitoring, and protection systems.

## API Endpoints

### Main Status
- `GET /` - API information and available endpoints
- `GET /api/bot-status` - Comprehensive bot status and real-time data

### Trading Data
- `GET /api/positions` - Current trading positions
- `GET /api/activity` - Recent bot activity log
- `GET /api/activity/stream` - Server-Sent Events stream of activity (for dashboards)
- `GET /api/performance` - Detailed trading performance metrics

### Bot Control
- `POST /api/bot/start` - Start the trading bot
- `POST /api/bot/stop` - Stop the trading bot

## Example Response from `/api/bot-status`

```json
{
  "bot_status": {
    "status": "active",
    "uptime_hours": 12.5,
    "last_update": "2025-08-10T16:30:00",
    "trading_enabled": true
  },
  "wallet": {
    "current_balance_sol": 0.5847,
    "daily_starting_balance_sol": 0.6000,
    "daily_pl_sol": -0.0153,
    "daily_pl_percent": -2.55,
    "wallet_exposure_percent": 45.2,
    "daily_loss_limit_percent": 1.0
  },
  "trading": {
    "active_positions": 3,
    "total_positions": 15,
    "watchlist_tokens": 8,
    "tokens_checked_today": 127,
    "pump_fun_monitoring": 5
  },
  "performance": {
    "total_trades": 45,
    "total_wins": 32,
    "win_rate_percent": 71.11,
    "ultra_early": {
      "trades": 18,
      "wins": 13,
      "pl": 0.0234
    },
    "analyst": {
      "trades": 15,
      "wins": 11,
      "pl": 0.0187
    },
    "community": {
      "trades": 12,
      "wins": 8,
      "pl": 0.0123
    }
  },
  "market_sentiment": {
    "sentiment_score": 68.5,
    "volatility_index": 1.2,
    "bull_market": true,
    "recent_performance_count": 45
  },
  "protection_systems": {
    "blacklisted_tokens": 23,
    "blacklisted_developers": 7,
    "fake_volume_tokens": 15,
    "mev_protection_enabled": true,
    "circuit_breakers_active": 2
  },
  "api_status": {
    "failures": {},
    "circuit_breakers": {}
  },
  "recent_activity": [
    "🐋 Whale 5Q544f... bought Unknown (B88rK4Y1) - $0.00",
    "✅ RUG CHECK PASSED: B88rK4Y1 (Score: 87/100)",
    "📈 COMMUNITY TOKEN DETECTED: B88rK4Y1, passing to Analyst handler"
  ]
}
```

## Features

- **Ultra-Early Strategy**: Ultra-fast entry on new tokens with ML scoring
- **Analyst Strategy**: Trending token analysis with surge detection
- **Community Strategy**: Whale wallet monitoring and community signals
- **Advanced Protection**: MEV protection, fake volume detection, token blacklisting
- **ML Scoring**: Multi-factor analysis with market sentiment tracking
- **Real-time Monitoring**: Pump.fun token monitoring with immediate rug checking

## Deployment

The bot runs on Railway with:
- Flask JSON API on port 8080
- WebSocket server on port 8081
- SQLite database for position management
- Telegram integration via ToxiBot

## Environment Variables

Required environment variables:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH` 
- `TELEGRAM_STRING_SESSION`
- `HELIUS_API_KEY`
- `BITQUERY_API_KEY` (optional)
