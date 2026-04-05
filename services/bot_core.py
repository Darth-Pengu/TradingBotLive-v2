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
- Tracks open positions, P/L, and trade history in PostgreSQL
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import aiohttp
import redis.asyncio as aioredis
from dotenv import load_dotenv

from services.db import get_pool

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bot_core")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
STARTING_CAPITAL_SOL = float(os.getenv("STARTING_CAPITAL_SOL", "20"))
HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "")
TRADING_WALLET_ADDRESS = os.getenv("TRADING_WALLET_ADDRESS", "")
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "").strip()
NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")
NANSEN_DAILY_BUDGET = int(os.getenv("NANSEN_DAILY_BUDGET", "50"))
_start_time = time.time()

# Personality position size adjustments
PERSONALITY_SIZE_ADJUSTMENT = {
    "speed_demon": 0.7,   # Raised from 0.5 — SD produced +259% winner, needs to trade
    "analyst": 1.3,       # Boost — best personality
    "whale_tracker": 1.0,
}

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
# --- Exit strategies per personality (Section 3) ---
# Trailing stop is handled exclusively by _evaluate_trailing_stop() with
# per-personality config in risk_manager.py TRAILING_STOP_CONFIG.
EXIT_STRATEGIES = {
    "speed_demon": {
        "staged_exits": [
            {"at_multiple": 2.0, "sell_pct": 0.40},
            {"at_multiple": 3.0, "sell_pct": 0.30},
        ],
        "time_exit_minutes": 10,
        "stop_loss_pct": 0.40,
    },
    "analyst": {
        "staged_exits": [
            {"at_multiple": 1.5, "sell_pct": 0.30},
            {"at_multiple": 2.5, "sell_pct": 0.30},
        ],
        "time_exit_minutes": 45,
        "max_hold_hours": 3,
        "stop_loss_pct": 0.25,
    },
    "whale_tracker": {
        "staged_exits": [
            {"at_multiple": 2.0, "sell_pct": 0.30},
            {"at_multiple": 5.0, "sell_pct": 0.40},
        ],
        "max_hold_hours": 6,
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
    trade_id: int = 0          # paper_trades.id
    trades_ml_id: int = 0      # trades.id (ML training record)
    ml_score: float = 0.0      # ML score at entry time
    signal_source: str = ""    # Signal source for per-source stats
    bonding_curve_progress: float = 0.0  # For PumpPortal Local routing on sells
    # Trailing stop state (persisted to PostgreSQL, mirrored to Redis)
    trailing_stop_active: bool = False
    trailing_stop_price: float = 0.0
    trailing_stop_pct: float = 0.0
    rugcheck_risk_level: str = "unknown"
    signal_type: str = "standard"  # "standard" or "graduation"


class BotCore:
    def __init__(self):
        self.positions: dict[str, Position] = {}  # key: f"{personality}:{mint}"
        self.portfolio = PortfolioState(total_balance_sol=STARTING_CAPITAL_SOL, peak_balance_sol=STARTING_CAPITAL_SOL)
        self.emergency_stopped = False
        self.pool = None
        self.redis: aioredis.Redis | None = None

    async def init(self):
        self.pool = await get_pool()
        await self._load_state()
        await self._reconcile_positions()

    async def _reconcile_positions(self):
        """Log open positions on startup for manual review."""
        try:
            table = "paper_trades" if TEST_MODE else "trades"
            exit_col = "exit_time" if TEST_MODE else "closed_at"
            rows = await self.pool.fetch(
                f"SELECT mint, personality FROM {table} WHERE {exit_col} IS NULL"
            )
            db_mints = {r["mint"] for r in rows}
            logger.info("Startup reconciliation: %d open positions in DB", len(db_mints))
            if db_mints:
                logger.info("Open positions: %s", ", ".join(m[:12] for m in db_mints))
        except Exception as e:
            logger.warning("Startup reconciliation failed: %s", e)

    async def _load_state(self):
        """Load portfolio state + open positions from PostgreSQL (source of truth).
        Trailing stop state comes from DB, not Redis — survives restarts."""
        try:
            row = await self.pool.fetchrow(
                "SELECT total_balance_sol, daily_pnl_sol FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
            )
            if row:
                self.portfolio.total_balance_sol = row["total_balance_sol"]
                # Reset daily P&L on startup — stale negative values
                # from previous session trigger false emergency stops
                self.portfolio.daily_pnl_sol = 0.0
                # In paper trading, reset peak to current balance to prevent
                # accumulated paper losses from permanently triggering emergency stop
                if TEST_MODE:
                    self.portfolio.peak_balance_sol = self.portfolio.total_balance_sol
                    logger.info("Paper mode: peak_balance reset to current %.4f SOL", self.portfolio.total_balance_sol)
                else:
                    self.portfolio.peak_balance_sol = max(
                        self.portfolio.peak_balance_sol,
                        self.portfolio.total_balance_sol
                    )
                logger.info("Loaded portfolio state: %.4f SOL (daily P&L reset to 0.0)", row["total_balance_sol"])
            else:
                logger.warning("No portfolio snapshots found — using defaults")
                if TEST_MODE:
                    # Use Redis balance if available, else starting capital
                    pass
        except Exception as e:
            logger.warning("Portfolio state load error: %s", e)

        # In paper mode, always reset peak to current to prevent permanent emergency stop
        if TEST_MODE:
            self.portfolio.peak_balance_sol = self.portfolio.total_balance_sol
            logger.info("Paper mode: peak_balance set to %.4f SOL (prevents false drawdown stop)", self.portfolio.total_balance_sol)

        # Reload open positions from DB (with trailing stop state)
        try:
            table = "paper_trades" if TEST_MODE else "trades"
            exit_col = "exit_time" if TEST_MODE else "closed_at"
            rows = await self.pool.fetch(
                f"SELECT * FROM {table} WHERE {exit_col} IS NULL ORDER BY id ASC"
            )
            restored = 0
            for r in rows:
                mint = r.get("mint", "")
                personality = r.get("personality", "")
                key = f"{personality}:{mint}"
                if key in self.positions:
                    continue  # Already tracked
                entry_price = float(r.get("entry_price", 0) or 0)
                # Restore staged exits done
                staged_raw = r.get("staged_exits_done", "[]")
                try:
                    staged_exits = json.loads(staged_raw) if staged_raw else []
                except Exception:
                    staged_exits = []
                pos = Position(
                    mint=mint,
                    personality=personality,
                    entry_price=entry_price,
                    entry_time=float(r.get("entry_time", r.get("created_at", 0)) or 0),
                    size_sol=float(r.get("amount_sol", 0) or 0),
                    peak_price=float(r.get("peak_price") or entry_price or 0),
                    staged_exits_done=staged_exits,
                    trade_id=r.get("id", 0),
                    trades_ml_id=int(r.get("trades_ml_id", 0) or 0),
                    ml_score=float(r.get("ml_score", r.get("ml_score_at_entry", 0)) or 0),
                    signal_source=r.get("signal_source", ""),
                    trailing_stop_active=bool(r.get("trailing_stop_active", False)),
                    trailing_stop_price=float(r.get("trailing_stop_price") or 0),
                    trailing_stop_pct=float(r.get("trailing_stop_pct") or 0),
                )
                self.positions[key] = pos
                restored += 1
            if restored:
                logger.info("Restored %d open positions from PostgreSQL (trailing stop state preserved)", restored)
        except Exception as e:
            logger.warning("Failed to restore open positions: %s", e)

        # Restore consecutive losses from PostgreSQL
        try:
            from services.db import get_bot_state
            saved_consec = await get_bot_state("consecutive_losses", 0)
            if saved_consec and isinstance(saved_consec, int) and saved_consec > 0:
                # Safety cap — prevent stale loss counter from triggering crash loop
                if saved_consec > 10:
                    logger.warning("AUDIT: consecutive_losses=%d in DB — resetting to 0 (stale value)", saved_consec)
                    saved_consec = 0
                    await set_bot_state("consecutive_losses", 0)
                if self.redis:
                    await self.redis.set("bot:consecutive_losses", str(saved_consec))
                if saved_consec > 0:
                    logger.info("Restored consecutive_losses=%d from PostgreSQL", saved_consec)
        except Exception as e:
            logger.debug("Could not restore consecutive_losses: %s", e)

    async def _save_snapshot(self):
        await self.pool.execute(
            "INSERT INTO portfolio_snapshots (timestamp, total_balance_sol, open_positions, daily_pnl_sol, market_mode) VALUES ($1, $2, $3, $4, $5)",
            datetime.now(timezone.utc).isoformat(), self.portfolio.total_balance_sol,
            len(self.positions), self.portfolio.daily_pnl_sol, self.portfolio.market_mode,
        )

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
        """Batch-fetch token prices. Jupiter primary (with auth), Binance fallback for SOL."""
        if not mints:
            return {}
        result = {m: 0.0 for m in mints}
        # Primary: Jupiter V3
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
                        for mint in mints:
                            p = data.get("data", {}).get(mint, {}).get("usdPrice") or data.get("data", {}).get(mint, {}).get("price")
                            result[mint] = float(p) if p else 0.0
                        return result
        except Exception:
            pass
        # Fallback: Binance for SOL (no auth needed)
        sol_mint = "So11111111111111111111111111111111111111112"
        if sol_mint in result:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.binance.com/api/v3/ticker/price",
                        params={"symbol": "SOLUSDT"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            result[sol_mint] = float(data.get("price", 0))
            except Exception:
                pass
        # GeckoTerminal fallback for non-SOL mints still at 0.0
        zero_mints = [m for m in mints if result.get(m, 0.0) == 0.0
                      and m != "So11111111111111111111111111111111111111112"]
        if zero_mints:
            for mint in zero_mints[:5]:  # cap at 5 to avoid rate limiting
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}",
                            headers={"Accept": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=8),
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                price_str = data.get("data", {}).get("attributes", {}).get("price_usd")
                                if price_str:
                                    result[mint] = float(price_str)
                except Exception:
                    pass

        # Redis cached price fallback (from PumpPortal trade stream via signal_listener)
        still_zero = [m for m in mints if result.get(m, 0.0) == 0.0
                      and m != "So11111111111111111111111111111111111111112"]
        if still_zero and self.redis:
            for mint in still_zero:
                try:
                    cached = await self.redis.get(f"token:price:{mint}")
                    if cached:
                        cached_price = float(cached)
                        # Convert SOL price to USD for consistency
                        sol_price = result.get("So11111111111111111111111111111111111111112", 0)
                        if sol_price > 0:
                            result[mint] = cached_price * sol_price
                        else:
                            result[mint] = cached_price * 80.0  # fallback SOL price
                        logger.debug("Using Redis cached price for %s: %.10f", mint[:12], result[mint])
                except Exception:
                    pass

        # Track price fetch failures in Redis
        failed = [m for m in mints if result.get(m, 0.0) == 0.0
                  and m != "So11111111111111111111111111111111111111112"]
        if failed and self.redis:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try:
                await self.redis.incrby(f"price:fetch:failures:{date_str}", len(failed))
                await self.redis.expire(f"price:fetch:failures:{date_str}", 86400)
            except Exception:
                pass
            for m in failed:
                logger.warning("SKIP_NO_PRICE: %s — no price source available", m[:12])

        return result

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

        # FIX 19: Consecutive loss circuit breaker
        if self.redis:
            try:
                pause_until = await self.redis.get("bot:loss_pause_until")
                if pause_until and time.time() < float(pause_until):
                    remaining = int(float(pause_until) - time.time())
                    logger.debug("Loss pause active — %ds remaining, skipping signal", remaining)
                    return
            except Exception:
                pass
            # Check emergency stop key
            try:
                estop = await self.redis.get("bot:emergency_stop")
                if estop:
                    logger.warning("Emergency stop active — skipping all new signals")
                    return
            except Exception:
                pass

        mint = scored_signal["mint"]
        personality = scored_signal["personality"]
        ml_score = scored_signal["ml_score"]
        market_mode = scored_signal.get("market_mode", "NORMAL")
        features = scored_signal.get("features", {})

        # Hourly trade cap — limit bleeding in bad markets while collecting data
        max_trades_per_hour = int(os.getenv("MAX_TRADES_PER_HOUR", "10"))
        if self.redis and max_trades_per_hour > 0:
            try:
                hour_key = f"trades:count:{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H')}"
                count = int(await self.redis.get(hour_key) or 0)
                if count >= max_trades_per_hour:
                    logger.debug("Hourly trade cap reached (%d/%d) — skipping %s",
                                count, max_trades_per_hour, mint[:12])
                    return
            except Exception:
                pass

        # Guard: skip if position already open for this personality+mint
        pos_key = f"{personality}:{mint}"
        if pos_key in self.positions:
            logger.debug("Already holding %s — skipping duplicate signal", pos_key)
            return

        # Guard: skip if mint traded within 2h cooldown
        if self.redis:
            try:
                already_traded = await self.redis.sismember("traded:mints", mint)
                if already_traded:
                    logger.debug("Skipping recently traded mint %s (cooldown active)", mint[:12])
                    return
            except Exception:
                pass

        self.portfolio.market_mode = market_mode

        # Governance mode check — read structured JSON decision from Redis
        gov = {"mode": "NORMAL", "size_multiplier": 1.0, "max_concurrent_positions": 10,
               "speed_demon_enabled": True, "analyst_enabled": True, "whale_tracker_enabled": True}
        if self.redis:
            try:
                gov_raw = await self.redis.get("governance:latest_decision")
                if gov_raw:
                    gov = json.loads(gov_raw)
            except Exception:
                pass

        if gov.get("mode") in ("HIBERNATE", "PAUSE"):
            logger.info("Governance: %s — skipping trade (%s)", gov["mode"], gov.get("reasoning", ""))
            return

        if personality == "speed_demon" and not gov.get("speed_demon_enabled", True):
            logger.info("Governance disabled Speed Demon")
            return
        if personality == "analyst" and not gov.get("analyst_enabled", True):
            logger.info("Governance disabled Analyst")
            return
        if personality == "whale_tracker" and not gov.get("whale_tracker_enabled", True):
            logger.info("Governance disabled Whale Tracker")
            return

        if len(self.positions) >= gov.get("max_concurrent_positions", 10):
            logger.info("Governance: max positions %d reached", gov["max_concurrent_positions"])
            return

        gov_size_mult = gov.get("size_multiplier", 1.0)

        # CFGI market fear gating — reduce exposure in extreme fear
        cfgi = float(features.get("cfgi_score", 50))
        if cfgi < 10 and personality == "speed_demon" and not os.getenv("AGGRESSIVE_PAPER_TRADING", "").lower() == "true":
            logger.info("CFGI=%d — Speed Demon paused in extreme fear", int(cfgi))
            return
        cfgi_mult = 1.0
        if cfgi < 10:
            cfgi_mult = 0.5
        elif cfgi < 20:
            cfgi_mult = 0.75

        # Update portfolio with current open positions
        self.portfolio.open_positions = {
            k: {"personality": v.personality, "size_sol": v.size_sol * v.remaining_pct, "mint": v.mint}
            for k, v in self.positions.items()
        }

        # Calculate position size (with pre-filter multiplier for speed_demon)
        base_size = calculate_position_size(
            personality, mint, self.portfolio,
            ml_score=ml_score,
            volatility_ratio=1.0,
        )
        conf_mult = scored_signal.get("position_size_multiplier", 1.0)
        if personality == "speed_demon" and conf_mult > 1.0:
            base_size = min(
                base_size * conf_mult,
                self.portfolio.total_balance_sol * 0.10,  # never > 10% of balance
            )

        # Apply personality size adjustment
        pers_adj = PERSONALITY_SIZE_ADJUSTMENT.get(personality, 1.0)
        base_size *= pers_adj
        if pers_adj != 1.0:
            logger.info("Personality sizing: %s x %.1f -> %.4f SOL", personality, pers_adj, base_size)

        # Apply rugcheck risk multiplier
        rc_mult = float(scored_signal.get("rugcheck_multiplier", 1.0))
        size_sol = base_size * rc_mult
        if rc_mult < 1.0:
            logger.info("Rugcheck risk: %s x %.2f -> %.4f SOL (risk=%s)",
                        mint[:12], rc_mult, size_sol, scored_signal.get("rugcheck_risk_level", "?"))

        # Apply dynamic win rate multiplier (if exists)
        wr_mult = 1.0
        if self.redis:
            try:
                wr_raw = await self.redis.get(f"position:multiplier:{personality}")
                if wr_raw:
                    wr_mult = float(wr_raw)
            except Exception:
                pass
        size_sol = size_sol * wr_mult * cfgi_mult * gov_size_mult

        # If risk manager returned 0 (max concurrent, max exposure, etc.), respect it
        if base_size <= 0:
            logger.debug("Risk manager rejected %s for %s (size=0)", mint[:12], personality)
            return

        # Enforce min/max limits only if risk manager approved
        size_sol = max(0.08, min(size_sol, 0.75))

        logger.info(
            "POSITION SIZE: %s base=%.2f conf_mult=%.2f rc_mult=%.2f "
            "wr_mult=%.2f final=%.2f SOL",
            mint[:8], base_size,
            conf_mult, rc_mult, wr_mult, size_sol,
        )

        if size_sol <= 0:
            logger.debug("Risk rejected %s for %s (size=0)", mint[:12], personality)
            return

        # P2: Analyst pre-entry granular flow check (24h smart money accumulation)
        if personality == "analyst" and NANSEN_API_KEY:
            flow_ok = await self._analyst_flow_check(mint, self.redis)
            if not flow_ok:
                logger.info("Analyst REJECTED %s: smart money distribution pattern", mint[:12])
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
            # Compute bonding curve price fallback for new tokens
            v_sol = float(raw.get("vSolInBondingCurve", 0) or 0)
            v_tokens = float(raw.get("vTokensInBondingCurve", 0) or 0)
            bc_price = (v_sol / v_tokens) if v_sol > 0 and v_tokens > 0 else 0.0
            # Convert bonding curve price (in SOL) to USD
            sol_price = features.get("sol_price_usd", 0) or 80.0
            bc_price_usd = bc_price * sol_price if bc_price > 0 else 0.0

            paper_result = await paper_buy(
                self.pool, self.redis, mint, size_sol, personality,
                slippage_tier=slippage_tier, pool=token.pool,
                ml_score=ml_score, signal_source=signal_source,
                market_mode=market_mode, fear_greed=fgi,
                rugcheck_risk=scored_signal.get("rugcheck_risk_level", "unknown"),
                bonding_curve_price=bc_price_usd,
            )
            if paper_result["success"]:
                paper_trade_id = paper_result["trade_id"]
                # Update paper_trades row with features_json for audit
                try:
                    await self.pool.execute(
                        "UPDATE paper_trades SET features_json=$1, ml_score_at_entry=$2 WHERE id=$3",
                        json.dumps(features), ml_score, paper_trade_id,
                    )
                except Exception as e:
                    logger.warning("AUDIT: features_json write failed for paper_trade_id=%d: %s",
                                   paper_trade_id, e)
                # Write to trades table with features_json for ML training
                trades_ml_id = await self.pool.fetchval(
                    """INSERT INTO trades (mint, personality, action, amount_sol, entry_price,
                       features_json, ml_score, signal_sources, created_at)
                       VALUES ($1, $2, 'buy', $3, $4, $5, $6, $7, $8) RETURNING id""",
                    mint, personality, paper_result["amount_sol"], paper_result["entry_price"],
                    json.dumps(features), ml_score,
                    json.dumps(scored_signal.get("sources", [])), time.time(),
                )
                logger.info("AUDIT: ML training record written trades.id=%d mint=%s personality=%s score=%.1f",
                            trades_ml_id, mint[:12], personality, ml_score)
                pos = Position(
                    mint=mint, personality=personality,
                    entry_price=paper_result["entry_price"],
                    entry_time=time.time(),
                    size_sol=paper_result["amount_sol"],
                    peak_price=paper_result["entry_price"],
                    trade_id=paper_trade_id,      # paper_trades.id
                    trades_ml_id=trades_ml_id,    # trades.id for ML training
                    ml_score=ml_score,
                    signal_source=signal_source,
                    bonding_curve_progress=bc_progress,
                    rugcheck_risk_level=scored_signal.get("rugcheck_risk_level", "unknown"),
                    signal_type=scored_signal.get("signal_type", "standard"),
                )
                # Persist trades_ml_id to paper_trades for restart recovery
                try:
                    await self.pool.execute(
                        "UPDATE paper_trades SET trades_ml_id = $1 WHERE id = $2",
                        trades_ml_id, paper_trade_id,
                    )
                except Exception:
                    pass
                key = f"{personality}:{mint}"
                self.positions[key] = pos
                # Subscribe to per-token trade stream for live exit pricing
                if self.redis:
                    try:
                        await self.redis.publish("token:subscribe", json.dumps({"mint": mint, "action": "subscribe"}))
                    except Exception:
                        pass
                logger.info("PAPER ENTERED: %s %s @ $%.8f, %.4f SOL (sig: %s)",
                             personality, mint[:12], paper_result["entry_price"],
                             paper_result["amount_sol"], paper_result["signature"])
                try:
                    await self.redis.hincrby("filter:stats:today", "trades_entered", 1)
                    # Increment hourly trade counter for rate limiting
                    hour_key = f"trades:count:{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H')}"
                    await self.redis.incr(hour_key)
                    await self.redis.expire(hour_key, 7200)
                except Exception:
                    pass
                # FIX 21: Publish trade_entered for dashboard signal feed
                if self.redis:
                    await self.redis.publish("bot:status", json.dumps({
                        "_type": "trade_entered",
                        "mint": mint, "personality": personality, "ml_score": ml_score,
                        "source": scored_signal.get("signal", {}).get("source", "unknown"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
        else:
            signal_type = scored_signal.get("signal", {}).get("type", "")
            result = await execute_trade(
                "buy", token, size_sol, slippage_tier=slippage_tier,
                bonding_curve_progress=bc_progress, signal_type=signal_type,
            )

            if result.success:
                price = await self._get_token_price(mint)
                if not price or price <= 0:
                    logger.warning("SKIP_NO_PRICE: %s — trade executed but no price for tracking, using fallback", mint[:12])
                    # Fallback: estimate from size_sol and typical token amount
                    price = 0.000001  # sentinel — will be updated on next price check
                signal_source = scored_signal.get("signal", {}).get("source", "unknown")
                pos = Position(
                    mint=mint, personality=personality,
                    entry_price=price, entry_time=time.time(),
                    size_sol=size_sol, peak_price=price,
                    ml_score=ml_score, signal_source=signal_source,
                    bonding_curve_progress=bc_progress,
                )
                trade_id = await self.pool.fetchval(
                    """INSERT INTO trades (mint, personality, action, amount_sol, entry_price,
                       features_json, ml_score, signal_sources, created_at)
                       VALUES ($1, $2, 'buy', $3, $4, $5, $6, $7, $8) RETURNING id""",
                    mint, personality, size_sol, price, json.dumps(features), ml_score,
                    json.dumps(scored_signal.get("sources", [])), time.time(),
                )
                pos.trade_id = trade_id
                key = f"{personality}:{mint}"
                self.positions[key] = pos
                # Subscribe to per-token trade stream for live exit pricing
                if self.redis:
                    try:
                        await self.redis.publish("token:subscribe", json.dumps({"mint": mint, "action": "subscribe"}))
                    except Exception:
                        pass
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
                self.pool, self.redis, pos.mint, sell_pct, reason, pos.personality,
                trade_id=pos.trade_id, entry_price=pos.entry_price,
                entry_time=pos.entry_time, amount_sol=pos.size_sol * pos.remaining_pct,
                signal_source=pos.signal_source,
            )
            pos.remaining_pct *= (1 - sell_pct)
            if pos.remaining_pct <= 0.01:
                pnl_sol = paper_result.get("pnl_sol", 0)
                pnl_pct = paper_result.get("pnl_pct", 0)
                outcome = paper_result.get("outcome", "loss")
                self.portfolio.daily_pnl_sol += pnl_sol
                self.portfolio.total_balance_sol += pnl_sol

                # Sync balance to Redis for dashboard
                if self.redis:
                    try:
                        await self.redis.set("bot:portfolio:balance", str(self.portfolio.total_balance_sol))
                    except Exception:
                        pass

                if outcome == "loss":
                    self.portfolio.consecutive_losses[pos.personality] = \
                        self.portfolio.consecutive_losses.get(pos.personality, 0) + 1
                else:
                    self.portfolio.consecutive_losses[pos.personality] = 0
                key = f"{pos.personality}:{pos.mint}"
                self.positions.pop(key, None)
                # Unsubscribe from token trade stream if no other personality holds this mint
                if self.redis and not any(p.mint == pos.mint for p in self.positions.values()):
                    try:
                        await self.redis.publish("token:subscribe", json.dumps({"mint": pos.mint, "action": "unsubscribe"}))
                    except Exception:
                        pass
                logger.info("PAPER CLOSED: %s %s -- %s %.4f SOL (%.1f%%) reason=%s",
                             pos.personality, pos.mint[:12], outcome, pnl_sol, pnl_pct, reason)

                # Publish outcome for ADWIN drift detection
                if self.redis:
                    await self.redis.publish("trades:outcome", json.dumps({
                        "mint": pos.mint,
                        "ml_score": pos.ml_score,  # real score from position, not locals()
                        "outcome": outcome,
                        "pnl_pct": pnl_pct,
                        "personality": pos.personality,
                        "timestamp": time.time(),
                    }))
                    # Write ML outcome to trades table using trades_ml_id
                    if pos.trades_ml_id:
                        try:
                            await self.pool.execute(
                                """UPDATE trades SET exit_price=$1, pnl_sol=$2, pnl_pct=$3,
                                   outcome=$4, closed_at=$5 WHERE id=$6""",
                                current_price, pnl_sol, pnl_pct, outcome,
                                time.time(), pos.trades_ml_id,
                            )
                        except Exception as e:
                            logger.debug("ML trades update error: %s", e)
                    # FIX 18: Add to traded mints set (2h TTL)
                    await self.redis.sadd("traded:mints", pos.mint)
                    await self.redis.expire("traded:mints", 7200)
                    # Consecutive loss counter (Redis + PostgreSQL)
                    aggressive_paper = os.getenv("AGGRESSIVE_PAPER_TRADING", "").lower() == "true"
                    if outcome == "loss":
                        consec = await self.redis.incr("bot:consecutive_losses")
                        if not aggressive_paper:
                            # Only pause entries in non-aggressive mode
                            if consec >= 3:
                                pause_until = time.time() + 900
                                await self.redis.set("bot:loss_pause_until", str(pause_until), ex=1800)
                                logger.warning("3+ consecutive losses (%d) — pausing entries 15min", consec)
                            if consec >= 5:
                                await self.redis.set("market:loss_override", "DEFENSIVE", ex=3600)
                                logger.warning("5+ consecutive losses — overriding market mode to DEFENSIVE")
                        try:
                            from services.db import set_bot_state
                            await set_bot_state("consecutive_losses", int(consec))
                        except Exception:
                            pass
                    else:
                        await self.redis.set("bot:consecutive_losses", "0")
                        try:
                            from services.db import set_bot_state
                            await set_bot_state("consecutive_losses", 0)
                        except Exception:
                            pass

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

        token = Token(mint=pos.mint, bonding_curve_progress=pos.bonding_curve_progress)
        result = await execute_trade(
            "sell", token, sell_amount, slippage_tier="sell",
            bonding_curve_progress=pos.bonding_curve_progress,
        )

        pos.remaining_pct *= (1 - sell_pct)
        current_price = await self._get_token_price(pos.mint)

        if pos.remaining_pct <= 0.01:
            pnl_pct = ((current_price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
            pnl_sol = (current_price - pos.entry_price) / pos.entry_price * sell_amount if pos.entry_price > 0 else 0
            outcome = "profit" if pnl_sol > 0 else "loss"

            self.portfolio.daily_pnl_sol += pnl_sol
            self.portfolio.total_balance_sol += pnl_sol

            if outcome == "loss":
                self.portfolio.consecutive_losses[pos.personality] = \
                    self.portfolio.consecutive_losses.get(pos.personality, 0) + 1
            else:
                self.portfolio.consecutive_losses[pos.personality] = 0

            await self.pool.execute(
                """UPDATE trades SET exit_price=$1, pnl_sol=$2, pnl_pct=$3, outcome=$4, closed_at=$5
                   WHERE id=$6""",
                current_price, pnl_sol, pnl_pct, outcome, time.time(), pos.trade_id,
            )

            key = f"{pos.personality}:{pos.mint}"
            self.positions.pop(key, None)
            # Unsubscribe from token trade stream if no other personality holds this mint
            if self.redis and not any(p.mint == pos.mint for p in self.positions.values()):
                try:
                    await self.redis.publish("token:subscribe", json.dumps({"mint": pos.mint, "action": "unsubscribe"}))
                except Exception:
                    pass

            logger.info("CLOSED: %s %s -- %s %.4f SOL (%.1f%%) reason=%s",
                         pos.personality, pos.mint[:12], outcome, pnl_sol, pnl_pct, reason)

            # Publish outcome for ADWIN drift detection
            if self.redis:
                await self.redis.publish("trades:outcome", json.dumps({
                    "mint": pos.mint,
                    "ml_score": pos.ml_score,  # real score from position
                    "outcome": outcome,
                    "pnl_pct": pnl_pct,
                    "personality": pos.personality,
                    "timestamp": time.time(),
                }))
                # FIX 18: Add to traded mints set (2h TTL)
                await self.redis.sadd("traded:mints", pos.mint)
                await self.redis.expire("traded:mints", 7200)
                # Consecutive loss counter (Redis + PostgreSQL)
                aggressive_paper = os.getenv("AGGRESSIVE_PAPER_TRADING", "").lower() == "true"
                if outcome == "loss":
                    consec = await self.redis.incr("bot:consecutive_losses")
                    if not aggressive_paper:
                        if consec >= 3:
                            pause_until = time.time() + 900
                            await self.redis.set("bot:loss_pause_until", str(pause_until), ex=1800)
                            logger.warning("3+ consecutive losses (%d) — pausing entries 15min", consec)
                        if consec >= 5:
                            await self.redis.set("market:loss_override", "DEFENSIVE", ex=3600)
                            logger.warning("5+ consecutive losses — overriding market mode to DEFENSIVE")
                    try:
                        from services.db import set_bot_state
                        await set_bot_state("consecutive_losses", int(consec))
                    except Exception:
                        pass
                else:
                    await self.redis.set("bot:consecutive_losses", "0")
                    try:
                        from services.db import set_bot_state
                        await set_bot_state("consecutive_losses", 0)
                    except Exception:
                        pass

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

    async def _evaluate_trailing_stop(self, pos: Position, current_price: float) -> str | None:
        """Evaluate trailing stop for a position. Returns exit reason or None.
        State persisted to PostgreSQL (source of truth), mirrored to Redis for dashboard."""
        from services.risk_manager import TRAILING_STOP_CONFIG, TRAILING_STOP_MARKET_MULTIPLIERS
        from services.db import update_trailing_stop

        config = TRAILING_STOP_CONFIG.get(pos.personality, TRAILING_STOP_CONFIG["analyst"])
        activation_pct = config["activation_pct"]
        base_trail_pct = config["trail_pct"]

        # Market-adaptive trail distance
        market_mode = self.portfolio.market_mode or "NORMAL"
        trail_mult = TRAILING_STOP_MARKET_MULTIPLIERS.get(market_mode, 1.0)
        trail_pct = base_trail_pct * trail_mult
        entry = pos.entry_price
        table = "paper_trades" if TEST_MODE else "trades"

        if not current_price or current_price <= 0 or entry <= 0:
            return None  # Fail safe — never trigger on bad price data

        state_changed = False

        # 1. Update peak price
        if current_price > pos.peak_price:
            pos.peak_price = current_price
            state_changed = True

        # 2. Check activation
        pnl_pct = (current_price - entry) / entry * 100
        if not pos.trailing_stop_active and pnl_pct >= activation_pct:
            pos.trailing_stop_active = True
            pos.trailing_stop_price = pos.peak_price * (1 - trail_pct / 100)
            pos.trailing_stop_pct = trail_pct
            state_changed = True
            logger.info("Trailing stop ACTIVATED — %s up %.1f%% | peak=%.8f stop=%.8f",
                         pos.mint[:12], pnl_pct, pos.peak_price, pos.trailing_stop_price)
            await self._send_discord(
                f"🎯 Trailing stop ACTIVATED\n"
                f"Token: {pos.mint[:12]}...\n"
                f"Up: +{pnl_pct:.1f}%\n"
                f"Stop set at: {pos.trailing_stop_price:.8f}\n"
                f"Personality: {pos.personality}"
            )

        # 3. Update trailing stop level (only moves up, never down)
        if pos.trailing_stop_active:
            new_stop = pos.peak_price * (1 - trail_pct / 100)
            if new_stop > pos.trailing_stop_price:
                pos.trailing_stop_price = new_stop
                state_changed = True

        # 4. Persist to PostgreSQL if anything changed
        if state_changed and pos.trade_id:
            try:
                await update_trailing_stop(
                    pos.trade_id, table, pos.peak_price,
                    pos.trailing_stop_active,
                    pos.trailing_stop_price if pos.trailing_stop_active else None,
                )
            except Exception as e:
                logger.debug("Trailing stop DB update error: %s", e)

        # 5. Check if trailing stop is triggered
        if pos.trailing_stop_active and pos.trailing_stop_price > 0 and current_price <= pos.trailing_stop_price:
            pnl_sol = (current_price - entry) / entry * pos.size_sol
            logger.info("Trailing stop HIT — %s | peak=%.8f stop=%.8f current=%.8f",
                         pos.mint[:12], pos.peak_price, pos.trailing_stop_price, current_price)
            await self._send_discord(
                f"📉 Trailing stop HIT\n"
                f"Token: {pos.mint[:12]}...\n"
                f"Peak: {pos.peak_price:.8f} | Stop: {pos.trailing_stop_price:.8f} | Exit: {current_price:.8f}\n"
                f"Est P/L: {'+' if pnl_sol >= 0 else ''}{pnl_sol:.4f} SOL\n"
                f"Personality: {pos.personality}"
            )
            return "TRAILING_STOP"

        return None

    async def _check_exits(self):
        """Monitor all open positions for exit conditions."""
        while True:
            if self.emergency_stopped:
                await asyncio.sleep(5)
                continue

            # Batch-fetch all position prices in one API call
            open_mints = [pos.mint for pos in self.positions.values()]
            prices = await self._get_token_prices_batch(open_mints) if open_mints else {}
            self._last_prices = prices  # Store for status publisher

            # Refresh cooldown set so open positions can't be re-entered mid-hold
            if self.redis and open_mints:
                try:
                    pipe = self.redis.pipeline()
                    for m in open_mints:
                        pipe.sadd("traded:mints", m)
                    pipe.expire("traded:mints", 7200)
                    await pipe.execute()
                except Exception:
                    pass

            for key, pos in list(self.positions.items()):
                try:
                    current_price = prices.get(pos.mint, 0.0)
                    strategy = EXIT_STRATEGIES.get(pos.personality, {})
                    entry = pos.entry_price
                    elapsed_min = (time.time() - pos.entry_time) / 60
                    elapsed_hrs = elapsed_min / 60

                    # Log when price is missing — critical for diagnosing missed exits
                    if current_price <= 0 and elapsed_min > 1:
                        logger.warning("NO_PRICE: %s %s — held %.1fm, price=0 (exits disabled)",
                                      pos.personality, pos.mint[:12], elapsed_min)

                    # Update peak_price and persist to DB for staged exit tracking
                    if current_price > 0 and current_price > pos.peak_price:
                        pos.peak_price = current_price
                        if pos.trade_id:
                            try:
                                table = "paper_trades" if TEST_MODE else "trades"
                                await self.pool.execute(
                                    f"UPDATE {table} SET peak_price = $1 WHERE id = $2",
                                    current_price, pos.trade_id,
                                )
                            except Exception:
                                pass

                    # 90-second momentum check for speed_demon
                    early_check_sec = float(os.getenv("SD_EARLY_CHECK_SECONDS", "90"))
                    early_min_move = float(os.getenv("SD_EARLY_MIN_MOVE_PCT", "2.0"))
                    if pos.personality == "speed_demon" and current_price > 0 and entry > 0:
                        hold_sec = time.time() - pos.entry_time
                        if early_check_sec - 10 < hold_sec < early_check_sec + 30:
                            pnl_pct = (current_price - entry) / entry * 100
                            if pnl_pct < early_min_move:
                                logger.info("NO MOMENTUM 90s: %s %.1f%%", pos.mint[:8], pnl_pct)
                                await self._close_position(pos, "no_momentum_90s")
                                continue

                    # Graduation-specific exit strategy (overrides standard exits)
                    if getattr(pos, "signal_type", None) == "graduation":
                        grad_time_limit = 20  # 20-minute survival window
                        grad_stop_loss = 0.20  # -20% hard stop
                        grad_tp = 1.30  # +30% take profit

                        if elapsed_min >= grad_time_limit and current_price > 0 and entry > 0:
                            if current_price <= entry * 1.05:
                                await self._close_position(pos, "graduation_time_exit")
                                continue

                        if current_price > 0 and entry > 0:
                            if current_price <= entry * (1 - grad_stop_loss):
                                await self._close_position(pos, "graduation_stop_loss")
                                continue
                            if current_price >= entry * grad_tp:
                                # Sell 95% at +30%, keep 5% moonbag
                                await self._close_position(pos, "graduation_tp_30pct", sell_pct=0.95)
                                # Remaining 5% gets 15% trailing stop
                                pos.trailing_stop_active = True
                                pos.trailing_stop_pct = 0.15
                                pos.peak_price = current_price
                                pos.trailing_stop_price = current_price * (1 - 0.15)
                                continue

                    # --- PRICE-BASED EXITS (priority order) ---
                    # 1. Stop loss  2. Staged TPs  3. Trailing stop  4. Time exit
                    if current_price > 0 and entry > 0:
                        multiple = current_price / entry

                        # 1. Hard stop loss — highest priority, every cycle
                        sl_pct = strategy.get("stop_loss_pct", 0.50)
                        if multiple <= (1 - sl_pct):
                            await self._close_position(pos, f"stop_loss_{sl_pct:.0%}")
                            continue

                        # 2. Staged take-profits — checked BEFORE time_exit
                        for exit_rule in strategy.get("staged_exits", []):
                            exit_key = f"{exit_rule['at_multiple']}x"
                            if exit_key not in pos.staged_exits_done and multiple >= exit_rule["at_multiple"]:
                                logger.info("STAGED_TP: %s hit %s (%.1fx) — selling %d%%",
                                           pos.mint[:12], exit_key, multiple, int(exit_rule["sell_pct"] * 100))
                                await self._close_position(pos, f"staged_{exit_key}", sell_pct=exit_rule["sell_pct"])
                                pos.staged_exits_done.append(exit_key)
                                if pos.trade_id:
                                    try:
                                        table = "paper_trades" if TEST_MODE else "trades"
                                        await self.pool.execute(
                                            f"UPDATE {table} SET staged_exits_done = $1 WHERE id = $2",
                                            json.dumps(pos.staged_exits_done), pos.trade_id,
                                        )
                                    except Exception:
                                        pass

                        # 3. Trailing stop — checked every cycle
                        ts_exit = await self._evaluate_trailing_stop(pos, current_price)
                        if ts_exit:
                            await self._close_position(pos, ts_exit)
                            continue

                    # 4. Time-based exit (lowest priority)
                    time_exit = strategy.get("time_exit_minutes")
                    if time_exit and elapsed_min >= time_exit:
                        if current_price > 0 and entry > 0 and current_price > entry * 1.01:
                            if not pos.trailing_stop_active:
                                pos.trailing_stop_active = True
                                pos.peak_price = max(pos.peak_price, current_price)
                                pos.trailing_stop_price = pos.peak_price * 0.85
                                logger.info("TIME_EXIT_SKIP: %s up %.1f%% — activating trailing stop",
                                           pos.mint[:12], (current_price/entry - 1)*100)
                        else:
                            await self._close_position(pos, "time_exit_no_movement")
                            continue

                    max_hold = strategy.get("max_hold_hours")
                    if max_hold and elapsed_hrs >= max_hold:
                        await self._close_position(pos, "max_hold_time")
                        continue

                except Exception as e:
                    logger.error("Exit check error for %s: %s", key, e)

            # Skip emergency check on first 3 iterations (30s grace)
            # Prevents stale portfolio state from triggering false stop
            if not hasattr(self, '_exit_check_count'):
                self._exit_check_count = 0
            self._exit_check_count += 1

            if self._exit_check_count > 3:
                triggered = await check_emergency_conditions(self.portfolio, self.redis)
                if triggered:
                    await self.emergency_stop("Risk limits breached")

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

        _startup_time = time.time()

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                if time.time() - _startup_time < 10:
                    logger.info("Ignoring pre-startup emergency message (grace period)")
                    continue
                try:
                    data = json.loads(message["data"])
                    reason = data.get("reason", "Unknown emergency")
                    await self.emergency_stop(reason)
                except Exception as e:
                    logger.error("Emergency listener error: %s", e)
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    # --- Smart money exit check subscriber ---
    async def _exit_check_listener(self):
        """Subscribe to alerts:exit_check — force-exit any position holding the flagged token."""
        if not self.redis:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe("alerts:exit_check")
        logger.info("Listening for smart money exit alerts on alerts:exit_check")

        _startup_time = time.time()

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                if time.time() - _startup_time < 10:
                    logger.info("Startup grace — ignoring stale exit_check message")
                    continue
                try:
                    data = json.loads(message["data"])
                    mint = data.get("mint", "")
                    reason = data.get("reason", "smart_money_exit_alert")
                    if not mint:
                        continue

                    for key, pos in list(self.positions.items()):
                        if pos.mint == mint:
                            if pos.personality == "whale_tracker":
                                logger.info("WHALE PRIMARY EXIT: %s — tracked wallet selling", pos.mint[:12])
                                await self._close_position(pos, f"whale_primary_exit: {reason}")
                            else:
                                if pos.remaining_pct > 0.50:
                                    await self._close_position(pos, f"smart_money_exit: {reason}", sell_pct=0.50)
                                else:
                                    logger.warning(
                                        "FORCED EXIT: %s %s — reason=%s (smart money selling)",
                                        pos.personality, mint[:12], reason,
                                    )
                                    await self._close_position(pos, reason)
                except Exception as e:
                    logger.error("Exit check listener error: %s", e)
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    # --- Whale exit monitor ---
    # _whale_exit_monitor REMOVED: subscribed to signals:raw LIST via pubsub
    # (which never receives data — lists use BRPOP not pubsub). The
    # _nansen_exit_monitor() covers whale sell detection via Nansen API.

    # --- Nansen smart money exit monitor ---
    async def _nansen_exit_monitor(self):
        """Monitor open positions for smart money sells. Budget-gated."""
        if not NANSEN_API_KEY:
            logger.info("Nansen exit monitor disabled (no API key)")
            return
        from services.nansen_client import get_smart_money_dex_sells

        while True:
            if self.emergency_stopped or not self.positions:
                await asyncio.sleep(60)
                continue

            # Check if Nansen is disabled via Redis
            try:
                if self.redis:
                    disabled = await self.redis.get("nansen:disabled")
                    if disabled:
                        await asyncio.sleep(300)
                        continue
            except Exception:
                pass

            # Budget gate
            today_key = f"nansen:calls:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
            try:
                if self.redis:
                    calls_today = int(await self.redis.get(today_key) or 0)
                    if calls_today >= NANSEN_DAILY_BUDGET:
                        logger.debug("Nansen budget exhausted (%d/%d)", calls_today, NANSEN_DAILY_BUDGET)
                        await asyncio.sleep(300)
                        continue
            except Exception:
                pass

            try:
                async with aiohttp.ClientSession() as session:
                    positions_to_check = list(self.positions.items())[:3]
                    for key, pos in positions_to_check:
                        try:
                            sells = await get_smart_money_dex_sells(session, pos.mint, self.redis)
                            # Track call count
                            try:
                                if self.redis:
                                    await self.redis.incr(today_key)
                                    await self.redis.expire(today_key, 86400)
                            except Exception:
                                pass

                            if sells and len(sells) > 0:
                                sig_sells = [s for s in sells
                                             if float(s.get("valueUsd", s.get("value_usd", 0)) or 0) > 1000]
                                if sig_sells:
                                    total_sell_usd = sum(
                                        float(s.get("valueUsd", s.get("value_usd", 0)) or 0) for s in sig_sells
                                    )
                                    if self.redis:
                                        await self.redis.publish("alerts:exit_check", json.dumps({
                                            "mint": pos.mint,
                                            "reason": f"nansen_smart_money_selling ({len(sig_sells)} sells, ${total_sell_usd:.0f})",
                                        }))
                        except Exception as e:
                            logger.debug("Nansen exit check error: %s", e)
            except Exception as e:
                logger.error("Nansen exit monitor error: %s", e)

            await asyncio.sleep(300)  # Every 5 minutes, not 60 seconds

    # --- Analyst pre-entry granular flow check ---
    async def _analyst_flow_check(self, mint: str, redis_conn) -> bool:
        """
        P2: Before Analyst enters a position, check 24h granular smart money flows.
        Returns True if accumulation trend is positive (>60% inflow hours).
        Returns True by default if Nansen unavailable (non-blocking).
        """
        if not NANSEN_API_KEY:
            return True

        try:
            from services.nansen_client import get_token_flows_granular, parse_granular_flows

            async with aiohttp.ClientSession() as session:
                flow_data = await get_token_flows_granular(
                    session, mint, hours_back=24, segment="smart_money", redis_conn=redis_conn,
                )
                parsed = parse_granular_flows(flow_data)

                trend = parsed.get("nansen_accumulation_trend", 0)
                hours = parsed.get("nansen_accumulation_hours", 0)

                if trend == -1:
                    logger.info("Analyst flow check REJECT %s: distribution trend (%d inflow hours)",
                                mint[:12], hours)
                    return False

                logger.info("Analyst flow check PASS %s: trend=%d, inflow_hours=%d",
                            mint[:12], trend, hours)
                return True

        except Exception as e:
            logger.debug("Analyst flow check error for %s: %s — allowing entry", mint[:12], e)
            return True  # Non-blocking: allow entry if Nansen fails

    # --- Daily P/L reset ---
    async def _portfolio_snapshot_task(self):
        """Write portfolio snapshot every 5 minutes for equity chart."""
        while True:
            await asyncio.sleep(300)
            try:
                balance = self.portfolio.total_balance_sol
                table = "paper_trades" if TEST_MODE else "trades"
                exit_col = "exit_time" if TEST_MODE else "closed_at"
                pnl_col = "realised_pnl_sol" if TEST_MODE else "pnl_sol"
                row = await self.pool.fetchrow(
                    f"""SELECT COUNT(*) as total, COALESCE(SUM({pnl_col}), 0) as pnl
                        FROM {table} WHERE {exit_col} IS NOT NULL"""
                )
                await self.pool.execute(
                    """INSERT INTO portfolio_snapshots
                       (timestamp, total_balance_sol, open_positions, daily_pnl_sol, market_mode)
                       VALUES ($1, $2, $3, $4, $5)""",
                    datetime.now(timezone.utc).isoformat(),
                    balance,
                    len(self.positions),
                    float(row["pnl"] if row else 0),
                    self.portfolio.market_mode,
                )
            except Exception as e:
                logger.debug("Portfolio snapshot error: %s", e)

    async def _daily_reset(self):
        """Reset daily P/L at midnight UTC."""
        while True:
            now = datetime.now(timezone.utc)
            # Sleep until next midnight (timedelta handles month rollover safely)
            tomorrow_midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                                 + timedelta(days=1))
            sleep_seconds = (tomorrow_midnight - now).total_seconds()
            await asyncio.sleep(max(sleep_seconds, 60))

            self.portfolio.daily_pnl_sol = 0.0
            logger.info("Daily P/L reset to 0")

    # --- Status publisher ---
    async def _status_publisher(self):
        """Publish bot status to Redis for dashboard consumption."""
        while True:
            if self.redis:
                # FIX 19: Read consecutive losses from Redis
                consec_losses = 0
                try:
                    cl = await self.redis.get("bot:consecutive_losses")
                    consec_losses = int(cl) if cl else 0
                except Exception:
                    pass
                # Write balance to dedicated Redis key for dashboard fallback
                try:
                    await self.redis.set("bot:portfolio:balance", str(self.portfolio.total_balance_sol))
                except Exception:
                    pass

                status = {
                    "status": "EMERGENCY_STOPPED" if self.emergency_stopped else "RUNNING",
                    "portfolio_balance": self.portfolio.total_balance_sol,
                    "trading_balance": self.portfolio.total_balance_sol,
                    "daily_pnl": self.portfolio.daily_pnl_sol,
                    "open_positions": len(self.positions),
                    "market_mode": self.portfolio.market_mode,
                    "consecutive_losses": consec_losses,
                    "test_mode": TEST_MODE,
                    "positions": {k: {
                        "mint": v.mint,
                        "personality": v.personality,
                        "size_sol": v.size_sol,
                        "remaining_pct": v.remaining_pct,
                        "entry_time": v.entry_time,
                        "entry_price": v.entry_price,
                        "current_price": getattr(self, "_last_prices", {}).get(v.mint, 0),
                        "unrealised_pnl_sol": (getattr(self, "_last_prices", {}).get(v.mint, 0) - v.entry_price) / v.entry_price * v.size_sol * v.remaining_pct if v.entry_price > 0 and getattr(self, "_last_prices", {}).get(v.mint, 0) > 0 else None,
                        "unrealised_pnl_pct": (getattr(self, "_last_prices", {}).get(v.mint, 0) - v.entry_price) / v.entry_price * 100 if v.entry_price > 0 and getattr(self, "_last_prices", {}).get(v.mint, 0) > 0 else None,
                        "peak_price": v.peak_price,
                        "trailing_stop_active": v.trailing_stop_active,
                        "trailing_stop_price": v.trailing_stop_price,
                        "trailing_stop_pct": v.trailing_stop_pct,
                        "rugcheck_risk_level": v.rugcheck_risk_level,
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
        bot.redis = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5)
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
            logger.warning("market:mode not received after 60s — defaulting to NORMAL")
            bot.portfolio.market_mode = "NORMAL"

    # Auto-subscribe to token trade streams for all restored open positions
    if bot.redis and bot.positions:
        subscribed_mints = set()
        for pos in bot.positions.values():
            if pos.mint not in subscribed_mints:
                try:
                    await bot.redis.publish("token:subscribe", json.dumps({"mint": pos.mint, "action": "subscribe"}))
                    subscribed_mints.add(pos.mint)
                except Exception:
                    pass
        if subscribed_mints:
            logger.info("Auto-subscribed to %d token trade streams for open positions", len(subscribed_mints))

    logger.info("Bot Core ready — managing 3 personalities")

    async def _heartbeat():
        while True:
            try:
                if bot.redis:
                    await bot.redis.set("service:bot_core:heartbeat", json.dumps({
                        "status": "alive",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "uptime_seconds": round(time.time() - _start_time),
                        "positions": len(bot.positions),
                        "emergency": bot.emergency_stopped,
                    }), ex=90)
            except Exception:
                pass
            await asyncio.sleep(30)

    await asyncio.gather(
        bot._consume_signals(),
        bot._check_exits(),
        bot._emergency_listener(),
        bot._exit_check_listener(),
        bot._nansen_exit_monitor(),
        bot._daily_reset(),
        bot._portfolio_snapshot_task(),
        bot._status_publisher(),
        _heartbeat(),
    )


if __name__ == "__main__":
    asyncio.run(main())
