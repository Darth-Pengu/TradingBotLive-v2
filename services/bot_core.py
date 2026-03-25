"""
ZMN Bot Core — Personality Coordinator
=============================================
Central trading engine that:
- Manages three concurrent personalities (Speed Demon, Analyst, Whale Tracker)
- Consumes scored signals from Redis "signals:scored"
- Coordinates position entry/exit via execution.py and risk_manager.py
- Implements staged exit strategies per personality
- Handles EMERGENCY_STOP (halts all three simultaneously)
- Waits up to 60s for market:mode key in Redis before starting
- Tracks open positions, P/L, and trade history in SQLite
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp
import aiosqlite
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bot_core")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
_db_url = os.getenv("DATABASE_URL", "toxibot.db")
DATABASE_PATH = _db_url.replace("sqlite:///", "") if _db_url.startswith("sqlite") else _db_url
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
STARTING_CAPITAL_SOL = float(os.getenv("STARTING_CAPITAL_SOL", "20"))
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "").strip()

# Import sibling modules
from services.execution import execute_trade, Token, ExecutionResult
from services.risk_manager import (
    calculate_position_size,
    check_emergency_conditions,
    PortfolioState,
    DAILY_LOSS_LIMIT_SOL,
)

# Paper trading (imported conditionally to avoid circular imports at module level)
if TEST_MODE:
    from services.paper_trader import paper_buy, paper_sell

# --- Exit strategies per personality (Section 3) ---
EXIT_STRATEGIES = {
    "speed_demon": {
        "staged_exits": [
            {"at_multiple": 2.0, "sell_pct": 0.40},   # Sell 40% at 2x
            {"at_multiple": 3.0, "sell_pct": 0.30},   # Sell 30% at 3x
        ],
        "moon_bag_pct": 0.30,
        "moon_bag_trailing_stop": 0.30,
        "time_exit_minutes": 5,       # No movement in 5 min → close all
        "stop_loss_pct": 0.50,        # 50% absolute floor
        "profit_trailing_stop": 0.30, # Switch to trailing after 30% profit
    },
    "analyst": {
        "staged_exits": [
            {"at_multiple": 1.5, "sell_pct": 0.30},
            {"at_multiple": 2.5, "sell_pct": 0.30},
        ],
        "trailing_exit_pct": 0.25,    # 25% trailing from peak for 25%
        "moon_bag_pct": 0.15,
        "moon_bag_trailing_stop": 0.40,
        "time_exit_minutes": 30,
        "max_hold_hours": 2,
        "stop_loss_pct": 0.30,
    },
    "whale_tracker": {
        "staged_exits": [
            {"at_multiple": 2.0, "sell_pct": 0.30},
            {"at_multiple": 5.0, "sell_pct": 0.40},
        ],
        "moon_bag_pct": 0.30,
        "moon_bag_trailing_stop": 0.25,
        "max_hold_hours": 4,
        "stop_loss_pct": 0.30,
    },
}

# --- Signal-based hard exits (Section 3 — Speed Demon) ---
HARD_EXIT_SIGNALS = [
    "dev_wallet_sells_gt_20pct",
    "bundle_dump_detected",
    "buyer_diversity_collapse",
    "rugcheck_risk_spike",
]


@dataclass
class Position:
    mint: str
    personality: str
    entry_price: float
    entry_time: float
    size_sol: float
    remaining_pct: float = 1.0
    peak_price: float = 0.0
    staged_exits_done: list = field(default_factory=list)
    trade_id: int = 0


class BotCore:
    def __init__(self):
        self.positions: dict[str, Position] = {}  # key: f"{personality}:{mint}"
        self.portfolio = PortfolioState(total_balance_sol=STARTING_CAPITAL_SOL, peak_balance_sol=STARTING_CAPITAL_SOL)
        self.emergency_stopped = False
        self.db: aiosqlite.Connection | None = None
        self.redis: aioredis.Redis | None = None

    async def init(self):
        self.db = await aiosqlite.connect(DATABASE_PATH)
        await self._init_db()
        await self._load_state()

    async def _init_db(self):
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mint TEXT NOT NULL,
                personality TEXT NOT NULL,
                action TEXT NOT NULL,
                amount_sol REAL,
                entry_price REAL,
                exit_price REAL,
                pnl_sol REAL,
                pnl_pct REAL,
                features_json TEXT,
                outcome TEXT,
                ml_score REAL,
                signal_sources TEXT,
                created_at REAL NOT NULL,
                closed_at REAL
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_balance_sol REAL,
                open_positions INTEGER,
                daily_pnl_sol REAL,
                market_mode TEXT
            )
        """)
        await self.db.commit()

    async def _load_state(self):
        """Load latest portfolio state from DB."""
        try:
            cursor = await self.db.execute(
                "SELECT total_balance_sol, daily_pnl_sol FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                self.portfolio.total_balance_sol = row[0]
                self.portfolio.daily_pnl_sol = row[1]
                self.portfolio.peak_balance_sol = max(self.portfolio.peak_balance_sol, row[0])
                logger.info("Loaded portfolio state: %.4f SOL", row[0])
        except Exception:
            pass

    async def _save_snapshot(self):
        await self.db.execute(
            "INSERT INTO portfolio_snapshots (timestamp, total_balance_sol, open_positions, daily_pnl_sol, market_mode) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), self.portfolio.total_balance_sol,
             len(self.positions), self.portfolio.daily_pnl_sol, self.portfolio.market_mode),
        )
        await self.db.commit()

    async def _send_discord(self, message: str):
        if not DISCORD_WEBHOOK_URL:
            return
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(DISCORD_WEBHOOK_URL, json={"content": message},
                                   timeout=aiohttp.ClientTimeout(total=10))
        except Exception:
            pass

    async def _get_token_price(self, mint: str) -> float:
        """Get current token price via Jupiter."""
        prices = await self._get_token_prices_batch([mint])
        return prices.get(mint, 0.0)

    async def _get_token_prices_batch(self, mints: list[str]) -> dict[str, float]:
        """Batch-fetch token prices via Jupiter. Returns {mint: price}."""
        if not mints:
            return {}
        try:
            ids = ",".join(set(mints))
            headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.jup.ag/price/v3",
                    params={"ids": ids},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = {}
                        for mint in mints:
                            p = data.get("data", {}).get(mint, {}).get("usdPrice") or data.get("data", {}).get(mint, {}).get("price")
                            result[mint] = float(p) if p else 0.0
                        return result
        except Exception:
            pass
        return {m: 0.0 for m in mints}

    # --- EMERGENCY STOP ---
    async def emergency_stop(self, reason: str):
        """Halt ALL three personalities simultaneously."""
        if self.emergency_stopped:
            return
        self.emergency_stopped = True
        logger.critical("EMERGENCY STOP: %s", reason)

        # Close all open positions
        for key, pos in list(self.positions.items()):
            await self._close_position(pos, "emergency_stop")

        await self._send_discord(f"EMERGENCY STOP: {reason}\nAll positions closed. Manual restart required.")

        if self.redis:
            await self.redis.publish("bot:status", json.dumps({
                "status": "EMERGENCY_STOPPED",
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

    # --- ENTRY ---
    async def process_signal(self, scored_signal: dict):
        """Process a scored signal and potentially enter a position."""
        if self.emergency_stopped:
            return

        mint = scored_signal["mint"]
        personality = scored_signal["personality"]
        ml_score = scored_signal["ml_score"]
        market_mode = scored_signal.get("market_mode", "NORMAL")
        features = scored_signal.get("features", {})

        self.portfolio.market_mode = market_mode

        # Update portfolio with current open positions
        self.portfolio.open_positions = {
            k: {"personality": v.personality, "size_sol": v.size_sol * v.remaining_pct}
            for k, v in self.positions.items()
        }

        # Calculate position size
        size_sol = calculate_position_size(
            personality, mint, self.portfolio,
            ml_score=ml_score,
            volatility_ratio=1.0,
        )

        if size_sol <= 0:
            logger.debug("Risk rejected %s for %s (size=0)", mint[:12], personality)
            return

        # Determine slippage tier
        age = scored_signal.get("signal", {}).get("age_seconds", 0)
        if personality == "speed_demon":
            if age <= 30:
                slippage_tier = "alpha_snipe"
            elif age <= 180:
                slippage_tier = "confirmation"
            else:
                slippage_tier = "post_grad_dip"
        else:
            slippage_tier = "confirmation"

        # Determine token pool type
        raw = scored_signal.get("signal", {}).get("raw_data", {})
        bc_progress = features.get("bonding_curve_progress", 0)
        pool = raw.get("pool", "auto")
        if isinstance(pool, str) and pool in ("pump", "pump-amm", "raydium", "orca", "meteora", "pumpswap", "raydium-cpmm"):
            pass
        else:
            pool = "pump" if bc_progress < 1.0 else "raydium"

        token = Token(
            mint=mint,
            pool=pool,
            bonding_curve_progress=bc_progress,
            liquidity_usd=features.get("market_cap_usd", 0),
        )

        # Execute trade
        logger.info("ENTERING: %s %s %.4f SOL (ML=%.1f, mode=%s)%s",
                     personality, mint[:12], size_sol, ml_score, market_mode,
                     " [PAPER]" if TEST_MODE else "")

        if TEST_MODE:
            # Paper trading: simulate execution, real everything else
            signal_source = scored_signal.get("signal", {}).get("source", "unknown")
            fgi = scored_signal.get("features", {}).get("cfgi_score", 50)
            paper_result = await paper_buy(
                self.db, self.redis, mint, size_sol, personality,
                slippage_tier=slippage_tier, pool=token.pool,
                ml_score=ml_score, signal_source=signal_source,
                market_mode=market_mode, fear_greed=fgi,
            )
            if paper_result["success"]:
                pos = Position(
                    mint=mint, personality=personality,
                    entry_price=paper_result["entry_price"],
                    entry_time=time.time(),
                    size_sol=paper_result["amount_sol"],
                    peak_price=paper_result["entry_price"],
                    trade_id=paper_result["trade_id"],
                )
                key = f"{personality}:{mint}"
                self.positions[key] = pos
                logger.info("PAPER ENTERED: %s %s @ $%.8f, %.4f SOL (sig: %s)",
                             personality, mint[:12], paper_result["entry_price"],
                             paper_result["amount_sol"], paper_result["signature"])
        else:
            result = await execute_trade("buy", token, size_sol, slippage_tier=slippage_tier)

            if result.success:
                price = await self._get_token_price(mint)
                pos = Position(
                    mint=mint, personality=personality,
                    entry_price=price, entry_time=time.time(),
                    size_sol=size_sol, peak_price=price,
                )
                cursor = await self.db.execute(
                    """INSERT INTO trades (mint, personality, action, amount_sol, entry_price,
                       features_json, ml_score, signal_sources, created_at)
                       VALUES (?, ?, 'buy', ?, ?, ?, ?, ?, ?)""",
                    (mint, personality, size_sol, price, json.dumps(features), ml_score,
                     json.dumps(scored_signal.get("sources", [])), time.time()),
                )
                await self.db.commit()
                pos.trade_id = cursor.lastrowid
                key = f"{personality}:{mint}"
                self.positions[key] = pos
                logger.info("ENTERED: %s %s @ $%.8f, %.4f SOL (tx: %s)",
                             personality, mint[:12], price, size_sol, result.signature)
            else:
                logger.warning("ENTRY FAILED: %s %s -- %s", personality, mint[:12], result.error)

    # --- EXIT MONITORING ---
    async def _close_position(self, pos: Position, reason: str, sell_pct: float = 1.0):
        """Close (partial or full) a position."""
        sell_amount = pos.size_sol * pos.remaining_pct * sell_pct
        if sell_amount < 0.001:
            return

        if TEST_MODE:
            # Paper trading: simulate exit
            paper_result = await paper_sell(
                self.db, self.redis, pos.mint, sell_pct, reason, pos.personality,
                trade_id=pos.trade_id, entry_price=pos.entry_price,
                entry_time=pos.entry_time, amount_sol=pos.size_sol * pos.remaining_pct,
            )
            pos.remaining_pct *= (1 - sell_pct)
            if pos.remaining_pct <= 0.01:
                pnl_sol = paper_result.get("pnl_sol", 0)
                pnl_pct = paper_result.get("pnl_pct", 0)
                outcome = paper_result.get("outcome", "loss")
                self.portfolio.daily_pnl_sol += pnl_sol
                self.portfolio.total_balance_sol += pnl_sol
                if outcome == "loss":
                    self.portfolio.consecutive_losses[pos.personality] = \
                        self.portfolio.consecutive_losses.get(pos.personality, 0) + 1
                else:
                    self.portfolio.consecutive_losses[pos.personality] = 0
                key = f"{pos.personality}:{pos.mint}"
                self.positions.pop(key, None)
                logger.info("PAPER CLOSED: %s %s -- %s %.4f SOL (%.1f%%) reason=%s",
                             pos.personality, pos.mint[:12], outcome, pnl_sol, pnl_pct, reason)
                if outcome == "loss" and self.portfolio.consecutive_losses.get(pos.personality, 0) >= 3:
                    if self.redis:
                        await self.redis.publish("streak:loss", json.dumps({
                            "personality": pos.personality,
                            "consecutive_losses": self.portfolio.consecutive_losses[pos.personality],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
            else:
                logger.info("PAPER PARTIAL: %s %s %.0f%% (reason=%s, remaining=%.0f%%)",
                             pos.personality, pos.mint[:12], sell_pct*100, reason, pos.remaining_pct*100)
            return

        token = Token(mint=pos.mint)
        result = await execute_trade("sell", token, sell_amount, slippage_tier="sell")

        pos.remaining_pct *= (1 - sell_pct)
        current_price = await self._get_token_price(pos.mint)

        if pos.remaining_pct <= 0.01:
            pnl_pct = ((current_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
            pnl_sol = sell_amount * (pnl_pct / 100)
            outcome = "profit" if pnl_sol > 0 else "loss"

            self.portfolio.daily_pnl_sol += pnl_sol
            self.portfolio.total_balance_sol += pnl_sol

            if outcome == "loss":
                self.portfolio.consecutive_losses[pos.personality] = \
                    self.portfolio.consecutive_losses.get(pos.personality, 0) + 1
            else:
                self.portfolio.consecutive_losses[pos.personality] = 0

            await self.db.execute(
                """UPDATE trades SET exit_price=?, pnl_sol=?, pnl_pct=?, outcome=?, closed_at=?
                   WHERE id=?""",
                (current_price, pnl_sol, pnl_pct, outcome, time.time(), pos.trade_id),
            )
            await self.db.commit()

            key = f"{pos.personality}:{pos.mint}"
            self.positions.pop(key, None)

            logger.info("CLOSED: %s %s -- %s %.4f SOL (%.1f%%) reason=%s",
                         pos.personality, pos.mint[:12], outcome, pnl_sol, pnl_pct, reason)

            # Publish loss streak event for governance
            if outcome == "loss" and self.portfolio.consecutive_losses.get(pos.personality, 0) >= 3:
                if self.redis:
                    await self.redis.publish("streak:loss", json.dumps({
                        "personality": pos.personality,
                        "consecutive_losses": self.portfolio.consecutive_losses[pos.personality],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
        else:
            logger.info("PARTIAL SELL: %s %s %.1f%% (reason=%s, remaining=%.1f%%)",
                         pos.personality, pos.mint[:12], sell_pct * 100, reason, pos.remaining_pct * 100)

    async def _check_exits(self):
        """Monitor all open positions for exit conditions."""
        while True:
            if self.emergency_stopped:
                await asyncio.sleep(5)
                continue

            # Batch-fetch all position prices in one API call
            open_mints = [pos.mint for pos in self.positions.values()]
            prices = await self._get_token_prices_batch(open_mints) if open_mints else {}

            for key, pos in list(self.positions.items()):
                try:
                    current_price = prices.get(pos.mint, 0.0)
                    if current_price <= 0:
                        continue

                    pos.peak_price = max(pos.peak_price, current_price)
                    strategy = EXIT_STRATEGIES.get(pos.personality, {})
                    entry = pos.entry_price
                    if entry <= 0:
                        continue

                    multiple = current_price / entry
                    elapsed_min = (time.time() - pos.entry_time) / 60
                    elapsed_hrs = elapsed_min / 60

                    # --- Stop loss ---
                    sl_pct = strategy.get("stop_loss_pct", 0.50)
                    if multiple <= (1 - sl_pct):
                        await self._close_position(pos, f"stop_loss_{sl_pct:.0%}")
                        continue

                    # --- Staged exits ---
                    for exit_rule in strategy.get("staged_exits", []):
                        exit_key = f"{exit_rule['at_multiple']}x"
                        if exit_key not in pos.staged_exits_done and multiple >= exit_rule["at_multiple"]:
                            await self._close_position(pos, f"staged_{exit_key}", sell_pct=exit_rule["sell_pct"])
                            pos.staged_exits_done.append(exit_key)

                    # --- Moon bag trailing stop ---
                    if pos.remaining_pct <= strategy.get("moon_bag_pct", 0.30) + 0.05:
                        ts_pct = strategy.get("moon_bag_trailing_stop", 0.30)
                        if pos.peak_price > 0:
                            drop_from_peak = (pos.peak_price - current_price) / pos.peak_price
                            if drop_from_peak >= ts_pct:
                                await self._close_position(pos, "trailing_stop")
                                continue

                    # --- Time-based exit ---
                    time_exit = strategy.get("time_exit_minutes")
                    if time_exit and elapsed_min >= time_exit and multiple <= 1.05:
                        await self._close_position(pos, "time_exit_no_movement")
                        continue

                    # --- Max hold time ---
                    max_hold = strategy.get("max_hold_hours")
                    if max_hold and elapsed_hrs >= max_hold:
                        await self._close_position(pos, "max_hold_time")
                        continue

                    # --- Profit trailing stop (Speed Demon) ---
                    profit_ts = strategy.get("profit_trailing_stop")
                    if profit_ts and multiple > (1 + profit_ts):
                        drop = (pos.peak_price - current_price) / pos.peak_price if pos.peak_price > 0 else 0
                        if drop >= profit_ts:
                            await self._close_position(pos, "profit_trailing_stop")
                            continue

                except Exception as e:
                    logger.error("Exit check error for %s: %s", key, e)

            # Check emergency conditions
            triggered = await check_emergency_conditions(self.portfolio, self.redis)
            if triggered:
                await self.emergency_stop("Risk limits breached")

            # Save periodic snapshot
            await self._save_snapshot()

            await asyncio.sleep(10)  # Check every 10 seconds

    # --- Signal consumer ---
    async def _consume_signals(self):
        """Consume scored signals from Redis."""
        if not self.redis:
            logger.warning("No Redis — signal consumption disabled")
            return

        while True:
            if self.emergency_stopped:
                await asyncio.sleep(5)
                continue

            try:
                result = await self.redis.brpop("signals:scored", timeout=5)
                if not result:
                    continue
                _, raw = result
                signal = json.loads(raw)
                await self.process_signal(signal)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error("Signal consumption error: %s", e)
                await asyncio.sleep(1)

    # --- Emergency listener ---
    async def _emergency_listener(self):
        """Listen for emergency alerts from other services."""
        if not self.redis:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe("alerts:emergency")
        logger.info("Listening for emergency alerts")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                reason = data.get("reason", "Unknown emergency")
                await self.emergency_stop(reason)
            except Exception as e:
                logger.error("Emergency listener error: %s", e)

    # --- Smart money exit check subscriber ---
    async def _exit_check_listener(self):
        """Subscribe to alerts:exit_check — force-exit any position holding the flagged token."""
        if not self.redis:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe("alerts:exit_check")
        logger.info("Listening for smart money exit alerts on alerts:exit_check")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                mint = data.get("mint", "")
                reason = data.get("reason", "smart_money_exit_alert")
                if not mint:
                    continue

                # Check all three personalities for this token
                for key, pos in list(self.positions.items()):
                    if pos.mint == mint:
                        logger.warning(
                            "FORCED EXIT: %s %s — reason=%s (smart money selling)",
                            pos.personality, mint[:12], reason,
                        )
                        await self._close_position(pos, reason)
            except Exception as e:
                logger.error("Exit check listener error: %s", e)

    # --- Whale exit monitor ---
    async def _whale_exit_monitor(self):
        """Monitor for whale sells on tokens we hold (Whale Tracker exit signal)."""
        if not self.redis:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe("signals:raw")

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                signal = json.loads(message["data"])
                if signal.get("signal_type") != "account_trade":
                    continue
                raw = signal.get("raw_data", {})
                if raw.get("txType") != "sell":
                    continue

                mint = signal.get("mint", "")
                key = f"whale_tracker:{mint}"
                if key in self.positions:
                    logger.info("Whale selling %s — immediate exit for whale_tracker", mint[:12])
                    await self._close_position(self.positions[key], "whale_selling")
            except Exception:
                continue

    # --- Daily P/L reset ---
    async def _daily_reset(self):
        """Reset daily P/L at midnight UTC."""
        while True:
            now = datetime.now(timezone.utc)
            # Sleep until next midnight
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if now.hour > 0 or now.minute > 0:
                tomorrow = tomorrow.replace(day=now.day + 1)
            sleep_seconds = (tomorrow - now).total_seconds()
            await asyncio.sleep(max(sleep_seconds, 60))

            self.portfolio.daily_pnl_sol = 0.0
            logger.info("Daily P/L reset to 0")

    # --- Status publisher ---
    async def _status_publisher(self):
        """Publish bot status to Redis for dashboard consumption."""
        while True:
            if self.redis:
                status = {
                    "status": "EMERGENCY_STOPPED" if self.emergency_stopped else "RUNNING",
                    "portfolio_balance": self.portfolio.total_balance_sol,
                    "daily_pnl": self.portfolio.daily_pnl_sol,
                    "open_positions": len(self.positions),
                    "market_mode": self.portfolio.market_mode,
                    "positions": {k: {
                        "mint": v.mint,
                        "personality": v.personality,
                        "size_sol": v.size_sol,
                        "remaining_pct": v.remaining_pct,
                        "entry_time": v.entry_time,
                    } for k, v in self.positions.items()},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                try:
                    await self.redis.set("bot:status", json.dumps(status), ex=30)
                    await self.redis.publish("bot:status", json.dumps(status))
                except Exception:
                    pass
            await asyncio.sleep(5)


async def main():
    logger.info("Bot Core starting (TEST_MODE=%s)", TEST_MODE)

    bot = BotCore()
    await bot.init()

    # Connect Redis
    try:
        bot.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        await bot.redis.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s — running in degraded mode", e)
        bot.redis = None

    # Wait up to 60s for market:mode (Section 14)
    if bot.redis:
        logger.info("Waiting for market:mode from market_health service...")
        for i in range(60):
            mode = await bot.redis.get("market:mode:current")
            if mode:
                bot.portfolio.market_mode = mode
                logger.info("Market mode received: %s", mode)
                break
            await asyncio.sleep(1)
        else:
            logger.warning("market:mode not received after 60s — defaulting to DEFENSIVE")
            bot.portfolio.market_mode = "DEFENSIVE"

    logger.info("Bot Core ready — managing 3 personalities")

    await asyncio.gather(
        bot._consume_signals(),
        bot._check_exits(),
        bot._emergency_listener(),
        bot._exit_check_listener(),
        bot._whale_exit_monitor(),
        bot._daily_reset(),
        bot._status_publisher(),
    )


if __name__ == "__main__":
    asyncio.run(main())
