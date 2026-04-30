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
# Session 5 v4 rollback finding: absolute MAX_POSITION_SOL can exceed the T5
# 20% wallet-drawdown trigger against small wallets. Cap position at a fraction
# of current wallet to keep T5 semantics meaningful at all wallet sizes.
# Binds as min(MAX_POSITION_SOL, wallet_sol * MAX_POSITION_SOL_FRACTION).
MAX_POSITION_SOL_FRACTION = float(os.getenv("MAX_POSITION_SOL_FRACTION", "0.10"))
_start_time = time.time()

# Personality position size adjustments
PERSONALITY_SIZE_ADJUSTMENT = {
    "speed_demon": 0.7,   # Raised from 0.5 — SD produced +259% winner, needs to trade
    "analyst": 1.3,       # Boost — best personality
    "whale_tracker": 1.0,
}

# Import sibling modules
from services.execution import execute_trade, Token, ExecutionResult, ExecutionError, set_live_log_pool, live_execution_log
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
# --- Staged take-profits (configurable via env var) ---
# Default: bank 25% at +50%, +100%, +200%, +400%
_DEFAULT_STAGED_TPS = [[0.50, 0.25], [1.00, 0.25], [2.00, 0.25], [4.00, 0.25]]
try:
    STAGED_TAKE_PROFITS = json.loads(os.getenv("STAGED_TAKE_PROFITS_JSON", "null")) or _DEFAULT_STAGED_TPS
except (json.JSONDecodeError, TypeError):
    STAGED_TAKE_PROFITS = _DEFAULT_STAGED_TPS

# --- Tiered trailing stop schedule ---
# (min_peak_gain, trail_pct)  — None trail_pct means no trail (hard stop only)
# 0.0 trail_pct means breakeven lock
_DEFAULT_TRAIL_SCHEDULE = [
    [0.30, 0.0],    # +30-50%: breakeven lock
    [0.50, 0.25],   # +50-100%: 25% trail from peak
    [1.00, 0.20],   # +100-200%: 20% trail
    [2.00, 0.15],   # +200-500%: 15% trail
    [5.00, 0.12],   # +500%+: 12% trail (moonshot)
]
try:
    TIERED_TRAIL_SCHEDULE = json.loads(os.getenv("TIERED_TRAIL_SCHEDULE_JSON", "null")) or _DEFAULT_TRAIL_SCHEDULE
except (json.JSONDecodeError, TypeError):
    TIERED_TRAIL_SCHEDULE = _DEFAULT_TRAIL_SCHEDULE


def get_tiered_trail_pct(peak_gain: float) -> float | None:
    """Return trail percentage based on peak gain from entry.
    None = no trail (below +30%), rely on hard stop.
    0.0 = breakeven lock (no trail % yet, just protect entry).
    >0 = trail that % from peak.
    """
    result = None
    for min_gain, trail_pct in TIERED_TRAIL_SCHEDULE:
        if peak_gain >= min_gain:
            result = trail_pct
    return result


EXIT_STRATEGIES = {
    "speed_demon": {
        "staged_exits": [{"at_gain": g, "sell_pct": s} for g, s in STAGED_TAKE_PROFITS],
        "time_exit_minutes": 15,
        # GATES-V5 (2026-04-21): tightened 0.35 -> 0.20 default, env-configurable.
        # Rationale: 7d CSV showed 21/105 gated trades hit stop_loss_35%, median
        # hold 2.9s (instant dumps, not recoverable). Tightening caps per-trade
        # loss at ~20% of position vs 35%. Winners never touch stop (exit via
        # TRAILING_STOP), so impact is loss-floor only. Expected save ~1.5 SOL/wk
        # at 0.25 SOL position sizing.
        "stop_loss_pct": float(os.getenv("STOP_LOSS_PCT", "0.20")),
    },
    "analyst": {
        "staged_exits": [{"at_gain": g, "sell_pct": s} for g, s in STAGED_TAKE_PROFITS],
        "time_exit_minutes": 30,
        "max_hold_hours": 2,
        "stop_loss_pct": 0.20,
    },
    "whale_tracker": {
        "staged_exits": [{"at_gain": g, "sell_pct": s} for g, s in STAGED_TAKE_PROFITS],
        "max_hold_hours": 24,
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
    trade_id: int = 0          # paper mode: paper_trades.id; live mode: trades.id (id-space overlap hazard — see REFACTOR-001)
    trades_ml_id: int = 0      # paper mode only: trades.id (ML training record). Unused in live mode.
    paper_trade_id: int | None = None  # Session 2b (DASH-ENTRY-001): live-mode paper_trades.id — entry INSERT target, close UPDATE by this id.
    ml_score: float = 0.0      # ML score at entry time
    signal_source: str = ""    # Signal source for per-source stats
    bonding_curve_progress: float = 0.0  # For PumpPortal Local routing on sells
    # Trailing stop state (persisted to PostgreSQL, mirrored to Redis)
    trailing_stop_active: bool = False
    trailing_stop_price: float = 0.0
    trailing_stop_pct: float = 0.0
    rugcheck_risk_level: str = "unknown"
    signal_type: str = "standard"  # "standard" or "graduation"
    cumulative_pnl_sol: float = 0.0  # Accumulated P/L across all staged exits


SELL_FAIL_THRESHOLD = int(os.getenv("SELL_FAIL_THRESHOLD", "8"))
SELL_PARK_DURATION_SEC = int(os.getenv("SELL_PARK_DURATION_SEC", "300"))


class BotCore:
    def __init__(self):
        self.positions: dict[str, Position] = {}  # key: f"{personality}:{mint}"
        self.portfolio = PortfolioState(total_balance_sol=STARTING_CAPITAL_SOL, peak_balance_sol=STARTING_CAPITAL_SOL)
        self.emergency_stopped = False
        self.pool = None
        self.redis: aioredis.Redis | None = None
        # Sell-storm circuit breaker: park a mint after N consecutive live-sell failures.
        # Prevents same-mint retry loops from generating thousands of identical errors.
        self._sell_failure_counts: dict[str, int] = {}
        self._parked_mints: dict[str, float] = {}  # mint -> unix_ts when parked

    async def init(self):
        self.pool = await get_pool()
        set_live_log_pool(self.pool)
        await self._load_state()
        await self._reconcile_positions()

    async def _reconcile_positions(self):
        """Log open positions on startup for manual review."""
        try:
            table = "paper_trades" if TEST_MODE else "trades"
            exit_col = "exit_time" if TEST_MODE else "closed_at"
            current_mode = "paper" if TEST_MODE else "live"
            mode_clause = f" AND trade_mode = '{current_mode}'" if table == "paper_trades" else ""
            rows = await self.pool.fetch(
                f"SELECT mint, personality FROM {table} WHERE {exit_col} IS NULL{mode_clause}"
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
        # Filter by trade_mode so paper positions don't block live MAX_SD_POSITIONS
        try:
            table = "paper_trades" if TEST_MODE else "trades"
            exit_col = "exit_time" if TEST_MODE else "closed_at"
            current_mode = "paper" if TEST_MODE else "live"
            mode_clause = f" AND trade_mode = '{current_mode}'" if table == "paper_trades" else ""
            rows = await self.pool.fetch(
                f"SELECT * FROM {table} WHERE {exit_col} IS NULL{mode_clause} ORDER BY id ASC"
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

    async def _shadow_log(self, event: str, trade_id: int = 0, **data):
        """Shadow measurement logging — paper mode only, no trading impact."""
        payload = {"ts": time.time(), "event": event, "trade_id": trade_id, **data}
        logger.info("SHADOW_MEASURE %s %s", event, json.dumps(payload))
        try:
            await self.redis.rpush("shadow:measurements", json.dumps(payload))
            await self.redis.ltrim("shadow:measurements", -10000, -1)
            await self.redis.expire("shadow:measurements", 86400 * 2)
        except Exception:
            pass

    async def _get_token_price(self, mint: str) -> float:
        """Get current token price via Jupiter."""
        prices = await self._get_token_prices_batch([mint])
        return prices.get(mint, 0.0)

    async def _get_token_prices_batch(self, mints: list[str]) -> dict[str, float]:
        """Batch-fetch token prices. Redis FIRST (instant), then API for uncached."""
        if not mints:
            return {}
        result = {m: 0.0 for m in mints}
        sol_mint = "So11111111111111111111111111111111111111112"

        # STEP 0: Get SOL/USD price (needed to convert Redis SOL prices to USD)
        sol_usd = 0.0
        if self.redis:
            try:
                cached_sol = await self.redis.get("market:sol_price")
                if cached_sol:
                    sol_usd = float(cached_sol)
            except Exception:
                pass
            # Also try market:health JSON (market_health service stores SOL price here)
            if sol_usd <= 0:
                try:
                    mh_raw = await self.redis.get("market:health")
                    if mh_raw:
                        mh = json.loads(mh_raw)
                        sp = mh.get("sol_price") or mh.get("sol_usd", 0)
                        if sp:
                            sol_usd = float(sp)
                except Exception:
                    pass

        # STEP 1: Redis cached prices FIRST (from PumpPortal trade stream — instant)
        redis_hits = {}
        if self.redis:
            for mint in mints:
                if mint == sol_mint:
                    continue
                try:
                    cached = await self.redis.get(f"token:latest_price:{mint}")
                    if not cached:
                        cached = await self.redis.get(f"token:price:{mint}")
                    if cached:
                        redis_hits[mint] = float(cached)
                except Exception:
                    pass

        # STEP 2: Bonding curve reserves from Redis (fallback for tokens with no trades)
        bc_hits = {}
        if self.redis:
            still_need = [m for m in mints if m not in redis_hits and m != sol_mint]
            for mint in still_need:
                try:
                    reserves = await self.redis.hgetall(f"token:reserves:{mint}")
                    if reserves:
                        v_sol = float(reserves.get(b"vSol", 0) or reserves.get("vSol", 0))
                        v_tokens = float(reserves.get(b"vTokens", 0) or reserves.get("vTokens", 0))
                        if v_sol > 0 and v_tokens > 0:
                            bc_hits[mint] = v_sol / v_tokens  # SOL per token
                except Exception:
                    pass

        # STEP 3: Jupiter for mints NOT in Redis cache + SOL price refresh
        mints_needing_api = [m for m in mints if m not in redis_hits and m not in bc_hits and m != sol_mint]
        if sol_usd <= 0:
            mints_needing_api.append(sol_mint)

        if mints_needing_api:
            try:
                ids = ",".join(set(mints_needing_api))
                headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.jup.ag/price/v3",
                        params={"ids": ids},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in mints_needing_api:
                                p = (data.get("data", {}).get(m, {}).get("usdPrice") or
                                     data.get("data", {}).get(m, {}).get("price"))
                                if p:
                                    result[m] = float(p)
                            sol_p = (data.get("data", {}).get(sol_mint, {}).get("usdPrice") or
                                     data.get("data", {}).get(sol_mint, {}).get("price"))
                            if sol_p:
                                sol_usd = float(sol_p)
            except Exception:
                pass

        # SOL price fallback: Binance
        if sol_usd <= 0:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.binance.com/api/v3/ticker/price",
                        params={"symbol": "SOLUSDT"},
                        timeout=aiohttp.ClientTimeout(total=3),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            sol_usd = float(data.get("price", 0))
            except Exception:
                pass
        if sol_usd <= 0:
            sol_usd = 80.0  # last resort fallback

        # Cache SOL price for other services
        if self.redis and sol_usd > 0:
            try:
                await self.redis.set("market:sol_price", str(sol_usd), ex=60)
            except Exception:
                pass

        # STEP 4: Convert Redis SOL prices to USD and apply to result
        for mint, sol_price_per_token in redis_hits.items():
            if result[mint] <= 0:
                result[mint] = sol_price_per_token * sol_usd
                logger.debug("EXIT_PRICE: %s via Redis cache %.10f SOL × $%.2f = $%.10f",
                            mint[:12], sol_price_per_token, sol_usd, result[mint])

        # STEP 4b: Convert bonding curve SOL prices to USD
        for mint, sol_price_per_token in bc_hits.items():
            if result[mint] <= 0:
                result[mint] = sol_price_per_token * sol_usd
                logger.debug("EXIT_PRICE: %s via bonding curve %.10f SOL × $%.2f = $%.10f",
                            mint[:12], sol_price_per_token, sol_usd, result[mint])

        # STEP 5: GeckoTerminal ONLY for mints still at 0 (max 2, short timeout)
        zero_mints = [m for m in mints if result.get(m, 0) <= 0 and m != sol_mint]
        for mint in zero_mints[:2]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}",
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=3),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            ps = data.get("data", {}).get("attributes", {}).get("price_usd")
                            if ps:
                                result[mint] = float(ps)
                                logger.debug("EXIT_PRICE: %s via GeckoTerminal $%.10f", mint[:12], result[mint])
            except Exception:
                pass

        # Track failures
        failed = [m for m in mints if result.get(m, 0) <= 0 and m != sol_mint]
        if failed and self.redis:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try:
                await self.redis.incrby(f"price:fetch:failures:{date_str}", len(failed))
                await self.redis.expire(f"price:fetch:failures:{date_str}", 86400)
            except Exception:
                pass
            for m in failed:
                logger.warning("NO_EXIT_PRICE: %s — all sources failed (Redis/BC/Jupiter/Gecko)", m[:12])

        return result

    # --- EMERGENCY STOP ---
    async def emergency_stop(self, reason: str):
        """Halt ALL three personalities simultaneously."""
        if self.emergency_stopped:
            return
        self.emergency_stopped = True
        logger.critical("EMERGENCY STOP: %s", reason)

        # Close all open positions — use last known prices
        last_prices = getattr(self, "_last_prices", {})
        for key, pos in list(self.positions.items()):
            price = last_prices.get(pos.mint, 0.0)
            await self._close_position(pos, "emergency_stop", current_price=price)

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

        # Guard: skip if ANY personality already holds this token (no cross-personality dupes)
        for key, pos in self.positions.items():
            if pos.mint == mint:
                logger.debug("SKIP_DUPE: %s already held by %s — %s blocked",
                            mint[:12], pos.personality, personality)
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
        _min_pos = float(os.environ.get("MIN_POSITION_SOL", "0.15"))
        _max_pos_abs = float(os.environ.get("MAX_POSITION_SOL", "1.50"))
        _wallet_now = max(self.portfolio.total_balance_sol, 0.0)
        _max_pos_frac = _wallet_now * MAX_POSITION_SOL_FRACTION if _wallet_now > 0 else _max_pos_abs
        _max_pos = min(_max_pos_abs, _max_pos_frac) if _max_pos_frac > 0 else _max_pos_abs
        size_sol = max(_min_pos, min(size_sol, _max_pos))

        # CHANGE 4: Time-of-day sizing (AEDT — Sydney) — data-driven from 426-trade analysis
        from datetime import timedelta as _td
        aedt_hour = datetime.now(timezone(_td(hours=11))).hour
        if aedt_hour in (18, 19, 20):
            size_sol *= 2.0
            logger.info("TIME_PRIME: hour=%d AEDT — 2.0x sizing (peak WR hours)", aedt_hour)
        elif aedt_hour in (7, 8, 9, 21):
            size_sol *= 1.5
            logger.info("TIME_GOOD: hour=%d AEDT — 1.5x sizing", aedt_hour)
        elif aedt_hour in (11, 12, 13, 14, 15, 16):
            size_sol *= 0.3
            logger.info("TIME_DEAD: hour=%d AEDT — 0.3x sizing (0%% WR zone)", aedt_hour)
        elif aedt_hour in (2, 3, 4, 5):
            size_sol *= 0.3
            logger.info("TIME_SLEEP: hour=%d AEDT — 0.3x sizing (dead zone)", aedt_hour)

        # CHANGE 6: Weekend sizing boost (50% of big winners on weekends)
        aedt_weekday = datetime.now(timezone(_td(hours=11))).weekday()
        if aedt_weekday >= 5:  # Saturday=5, Sunday=6
            size_sol *= 1.25
            logger.info("WEEKEND_BOOST: day=%d — 1.25x sizing", aedt_weekday)

        # Re-enforce limits after multipliers (same abs + fractional cap as above)
        size_sol = max(_min_pos, min(size_sol, _max_pos))

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
        entry_decision_ts = time.time()

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
                bonding_curve_progress=bc_progress,  # FEE-MODEL-001: pre-grad vs post-grad tiering
            )
            if paper_result["success"]:
                paper_trade_id = paper_result["trade_id"]
                # Shadow measurement: entry fill
                age = scored_signal.get("signal", {}).get("age_seconds", 0)
                await self._shadow_log("ENTRY_FILL", trade_id=paper_trade_id,
                    mint=mint[:12], personality=personality,
                    signal_age_s=age, ml_score=ml_score,
                    paper_fill_price=paper_result["entry_price"],
                    bc_price_usd=bc_price_usd,
                    decision_to_fill_ms=round((time.time() - entry_decision_ts) * 1000),
                    size_sol=paper_result["amount_sol"])
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
                    # Seed initial BC price so exit checker has data before first trade arrives
                    if bc_price > 0:
                        try:
                            await self.redis.set(f"token:latest_price:{mint}", str(bc_price), ex=600)
                            await self.redis.hset(f"token:reserves:{mint}", mapping={
                                "vSol": str(v_sol), "vTokens": str(v_tokens),
                            })
                            await self.redis.expire(f"token:reserves:{mint}", 600)
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

                # === Session 2b (DASH-ENTRY-001): live-mode entry write to paper_trades ===
                # Mirrors paper_buy() semantics so dashboard Open Positions widget
                # surfaces live trades during their lifetime (not just after close).
                # All signal metadata is available in local scope (scored_signal /
                # features / market_mode) — same sources the paper branch uses at
                # L754-769 — so no Redis reads / no flat defaults for fear_greed /
                # market_mode / rugcheck (Phase 1.3 decision: ML-POSITION-FEATURES-001
                # wart does NOT propagate to live rows).
                try:
                    _pe_fgi = float(features.get("cfgi_score", 50))
                    _pe_rugcheck = scored_signal.get("rugcheck_risk_level", "unknown")
                    _pe_market_cap = price * 1_000_000_000 if price > 0 else 0
                    paper_trade_row_id = await self.pool.fetchval(
                        """INSERT INTO paper_trades
                           (mint, personality, entry_price, amount_sol, entry_time,
                            signal_source, ml_score, entry_signature,
                            market_mode_at_entry, fear_greed_at_entry, rugcheck_risk,
                            market_cap_at_entry, trade_mode)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                           RETURNING id""",
                        mint, personality, price, size_sol, pos.entry_time,
                        signal_source, ml_score, getattr(result, "signature", None),
                        market_mode or "NORMAL", _pe_fgi, _pe_rugcheck,
                        _pe_market_cap, "live",
                    )
                    pos.paper_trade_id = paper_trade_row_id
                    logger.info("LIVE entry paper_trades row created id=%d mint=%s",
                                paper_trade_row_id, mint[:12])
                except Exception as e:
                    logger.error("LIVE entry paper_trades INSERT failed mint=%s: %s",
                                 mint, e)
                    try:
                        import sentry_sdk
                        sentry_sdk.capture_exception(e)
                    except Exception:
                        pass
                    # Do NOT raise — on-chain buy succeeded; dashboard degradation
                    # beats a crash. pos.paper_trade_id stays None and the close
                    # path falls through to Session 2 v2's defensive INSERT.

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

    # --- EXEC-001: pool routing state refresh ---
    # pump.fun canonical bonding-curve program ID (verified 2026-04 via public
    # program metadata + on-chain transaction inspection). PDA seed is the
    # literal byte string b"bonding-curve" concatenated with the mint pubkey.
    _PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

    async def _check_pool_state_fresh(self, mint: str) -> float:
        """Query current pump.fun bonding-curve state for a mint via Helius getAccountInfo.

        Returns:
            0.0 if BC account exists (token still pre-graduation — stay on PumpPortal Local).
            1.0 if BC account missing/closed (token graduated or was never on pump.fun — route to Jupiter).

        Raises:
            On RPC failure, timeout (>2s), or parse error — caller falls back to stale value.

        EXEC-001: called from _close_position before execute_trade to avoid stale
        routing on tokens that graduated during the hold. Addresses the likely
        root cause of the 261 historical HTTP 400 sells (v3/v4 trial). See
        CLAUDE.md Operating Principle "Routing state must be fresh at execute_trade
        call time" and ZMN_ROADMAP.md EXEC-001.
        """
        from solders.pubkey import Pubkey  # local import — avoids module-level cost
        mint_pk = Pubkey.from_string(mint)
        program_pk = Pubkey.from_string(self._PUMP_FUN_PROGRAM_ID)
        bc_pda, _bump = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)

        rpc_url = HELIUS_RPC_URL
        if not rpc_url:
            raise RuntimeError("EXEC-001 refresh: HELIUS_RPC_URL not configured")

        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [str(bc_pda), {"encoding": "base64"}],
        }

        async def _query():
            async with aiohttp.ClientSession() as s:
                async with s.post(rpc_url, json=payload,
                                  timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}")
                    return await resp.json()

        try:
            result = await asyncio.wait_for(_query(), timeout=2.0)
        except asyncio.TimeoutError:
            raise RuntimeError("EXEC-001 refresh: getAccountInfo timeout (>2s)")

        if "error" in result:
            raise RuntimeError(f"EXEC-001 refresh: RPC error {result['error']}")

        value = result.get("result", {}).get("value")
        # Null value = account doesn't exist = graduated (or never on pump.fun).
        # Non-null value = BC account still active = pre-graduation.
        return 1.0 if value is None else 0.0

    # --- EXIT MONITORING ---
    async def _close_position(self, pos: Position, reason: str, sell_pct: float = 1.0, current_price: float = 0.0):
        """Close (partial or full) a position."""
        sell_amount = pos.size_sol * pos.remaining_pct * sell_pct
        if sell_amount < 0.001:
            return

        # Shadow measurement: exit decision
        peak_gap = ((pos.peak_price - current_price) / pos.peak_price * 100) if pos.peak_price > 0 and current_price > 0 else 0
        await self._shadow_log("EXIT_DECISION", trade_id=pos.trade_id or 0,
            mint=pos.mint[:12], reason=reason, sell_pct=sell_pct,
            decision_price=current_price, entry_price=pos.entry_price,
            peak_price=pos.peak_price, peak_gap_pct=round(peak_gap, 2),
            remaining_pct=pos.remaining_pct,
            hold_s=round(time.time() - pos.entry_time, 1))

        if TEST_MODE:
            # Paper trading: simulate exit
            paper_result = await paper_sell(
                self.pool, self.redis, pos.mint, sell_pct, reason, pos.personality,
                trade_id=pos.trade_id, entry_price=pos.entry_price,
                entry_time=pos.entry_time, amount_sol=pos.size_sol * pos.remaining_pct,
                signal_source=pos.signal_source,
                exit_price_override=current_price,
                # FEE-MODEL-001: pre-grad vs post-grad fee/slippage tiering.
                # pos.bonding_curve_progress is the signal-time value; Position dataclass
                # doesn't carry pool, so pass sentinel "auto" (_simulate_fees infers from
                # bc_progress: <0.95 with "auto" = pre-grad pump.fun path).
                bonding_curve_progress=pos.bonding_curve_progress,
                pool="auto",
            )
            # Accumulate P/L across all partial exits (staged TPs + residual)
            pos.cumulative_pnl_sol += paper_result.get("pnl_sol", 0)
            pos.remaining_pct *= (1 - sell_pct)
            if pos.remaining_pct <= 0.01:
                # Use cumulative P/L across ALL exits, not just this last one
                pnl_sol = pos.cumulative_pnl_sol
                pnl_pct = (pnl_sol / pos.size_sol) * 100 if pos.size_sol > 0 else 0
                outcome = "win" if pnl_sol > 0 else "loss"
                # Correct the DB row — paper_sell wrote only this exit's P/L.
                # BUG-022 fix (2026-04-30): keep corrected_* columns aligned with
                # the cumulative realised_pnl_sol value written here. The TEST_MODE
                # branch enclosing this code guarantees `table == paper_trades`,
                # which is the only table carrying corrected_* columns.
                # Distinct param slots ($5-$7) for corrected_* — asyncpg's
                # prepared statement protocol can't deduce a single type when
                # the same param appears in columns of different declared types.
                if pos.trade_id and pos.staged_exits_done:
                    try:
                        table = "paper_trades" if TEST_MODE else "trades"
                        if TEST_MODE:
                            await self.pool.execute(
                                f"""UPDATE {table} SET realised_pnl_sol=$1, realised_pnl_pct=$2, outcome=$4,
                                    corrected_pnl_sol=$5, corrected_pnl_pct=$6, corrected_outcome=$7,
                                    correction_method='pass_through', correction_applied_at=NOW()
                                   WHERE id=$3""",
                                pnl_sol, pnl_pct, pos.trade_id, outcome,
                                pnl_sol, pnl_pct, outcome,
                            )
                        else:
                            await self.pool.execute(
                                f"UPDATE {table} SET realised_pnl_sol=$1, realised_pnl_pct=$2, outcome=$4 WHERE id=$3",
                                pnl_sol, pnl_pct, pos.trade_id, outcome,
                            )
                    except Exception:
                        pass
                logger.info("PAPER_EXIT mint=%s staged=%s cumulative_pnl=%.4f SOL (%.2f%%) residual_mult=%.3f",
                            pos.mint[:8], pos.staged_exits_done, pnl_sol, pnl_pct,
                            current_price / pos.entry_price if pos.entry_price > 0 else 0)
                self.portfolio.daily_pnl_sol += pnl_sol
                self.portfolio.total_balance_sol += pnl_sol

                # Sync balance to Redis for dashboard
                if self.redis:
                    try:
                        await self.redis.set("bot:portfolio:balance", str(self.portfolio.total_balance_sol))
                    except Exception:
                        pass

                # Don't count stale_no_price exits as consecutive losses
                # (dead tokens being cleaned up, not real trading losses)
                is_stale = reason in ("stale_no_price", "stale_force_closed")
                if outcome == "loss" and not is_stale:
                    self.portfolio.consecutive_losses[pos.personality] = \
                        self.portfolio.consecutive_losses.get(pos.personality, 0) + 1
                elif outcome != "loss":
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
                    # Don't count stale exits as consecutive losses
                    aggressive_paper = os.getenv("AGGRESSIVE_PAPER_TRADING", "").lower() == "true"
                    is_stale_exit = reason in ("stale_no_price", "stale_force_closed")
                    if outcome == "loss" and not is_stale_exit:
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

        park_ts = self._parked_mints.get(pos.mint)
        if park_ts is not None:
            if (time.time() - park_ts) < SELL_PARK_DURATION_SEC:
                return  # silently skip — avoids log spam during the cool-off window
            # cool-off expired: unpark and allow one retry
            self._parked_mints.pop(pos.mint, None)
            self._sell_failure_counts[pos.mint] = 0

        # EXEC-001: refresh pool state before routing decision. Fail closed on error
        # (use stale pos.bonding_curve_progress, no worse than pre-fix behavior).
        # Scope-gated: only refresh for pump.fun-origin tokens (stored bc_progress > 0).
        # Whale-tracker Raydium tokens carry bc_progress=0 and keep existing routing.
        # Paper mode already returned above (L1083), so this live-branch code is paper-safe.
        if pos.bonding_curve_progress > 0:
            try:
                fresh_bc = await self._check_pool_state_fresh(pos.mint)
                if fresh_bc != pos.bonding_curve_progress:
                    logger.info(
                        "EXEC-001 refresh: mint=%s bc_progress %.3f -> %.3f",
                        pos.mint[:12], pos.bonding_curve_progress, fresh_bc,
                    )
                    pos.bonding_curve_progress = fresh_bc
            except Exception as e:
                logger.warning(
                    "EXEC-001 refresh failed for %s, using stale bc_progress=%.3f: %s",
                    pos.mint[:12], pos.bonding_curve_progress, e,
                )
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(e)
                except Exception:
                    pass

        token = Token(mint=pos.mint, bonding_curve_progress=pos.bonding_curve_progress)
        try:
            result = await execute_trade(
                "sell", token, sell_amount, slippage_tier="sell",
                bonding_curve_progress=pos.bonding_curve_progress,
            )
        except ExecutionError as e:
            err_class = f"{type(e).__name__}:{str(e)[:40]}"
            fails = self._sell_failure_counts.get(pos.mint, 0) + 1
            self._sell_failure_counts[pos.mint] = fails
            if fails >= SELL_FAIL_THRESHOLD:
                self._parked_mints[pos.mint] = time.time()
                logger.error(
                    "PARK mint=%s after %d consecutive sell failures (last: %s). Cooling off %ds.",
                    pos.mint[:12], SELL_FAIL_THRESHOLD, err_class, SELL_PARK_DURATION_SEC,
                )
                try:
                    await live_execution_log(
                        event_type="ERROR", mint=pos.mint, action="sell",
                        error_msg=f"PARKED after {SELL_FAIL_THRESHOLD} failures: {err_class}",
                        extra={"parked": True, "consecutive_failures": SELL_FAIL_THRESHOLD,
                               "last_error": err_class},
                    )
                except Exception:
                    pass
            raise
        # success — reset the counter for this mint
        self._sell_failure_counts.pop(pos.mint, None)

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

            # === Session 2b (DASH-ENTRY-001): close-path UPDATE if entry row exists ===
            # Lifecycle: Session 2b's entry INSERT (above in process_signal live
            # branch) creates a paper_trades row and stores its id on
            # pos.paper_trade_id. Close path UPDATEs that row to set exit fields.
            # If pos.paper_trade_id is None (entry INSERT failed, or position
            # pre-dates Session 2b deploy), fall through to Session 2 v2's
            # defensive INSERT — preserves the safety net for edge cases.
            _pt_outcome = "win" if pnl_sol > 0 else "loss"
            _pt_exit_time = time.time()
            _pt_hold = max(0.0, _pt_exit_time - pos.entry_time) if pos.entry_time > 0 else 0.0
            _pt_mcap_entry = pos.entry_price * 1_000_000_000 if pos.entry_price > 0 else 0
            _pt_mcap_exit = current_price * 1_000_000_000 if current_price > 0 else 0
            _pt_exit_sig = getattr(result, "signature", None)

            if pos.paper_trade_id is not None:
                # Entry row exists — UPDATE it (correct lifecycle semantics).
                try:
                    await self.pool.execute(
                        """UPDATE paper_trades SET
                            exit_price=$1, exit_time=$2, hold_seconds=$3,
                            realised_pnl_sol=$4, realised_pnl_pct=$5,
                            exit_reason=$6, exit_signature=$7,
                            market_cap_at_exit=$8, outcome=$9
                           WHERE id=$10""",
                        current_price, _pt_exit_time, _pt_hold,
                        pnl_sol, pnl_pct, reason, _pt_exit_sig,
                        _pt_mcap_exit, _pt_outcome, pos.paper_trade_id,
                    )
                    logger.info("LIVE paper_trades UPDATE id=%d mint=%s outcome=%s pnl=%.4f",
                                pos.paper_trade_id, pos.mint[:12], _pt_outcome, pnl_sol)
                except Exception as e:
                    logger.error("LIVE close paper_trades UPDATE failed id=%d mint=%s: %s",
                                 pos.paper_trade_id, pos.mint, e)
                    try:
                        import sentry_sdk
                        sentry_sdk.capture_exception(e)
                    except Exception:
                        pass
            else:
                # Fallback: Session 2 v2 defensive INSERT (unchanged behavior).
                # Reached only if entry INSERT failed or position pre-dates Session 2b.
                # Live entry inserts only into `trades`, not paper_trades — so dashboard
                # queries `SELECT * FROM paper_trades WHERE trade_mode='live'` return
                # nothing. Fix: INSERT a full paper_trades row at terminal close.
                # We INSERT (not UPDATE) because:
                #   (a) no matching paper_trades row exists for live trades, and
                #   (b) pos.trade_id in live mode refers to trades.id; the id-spaces
                #       overlap with paper_trades.id, so UPDATE WHERE id=pos.trade_id
                #       would touch an unrelated paper row and corrupt its data.
                try:
                    await self.pool.execute(
                        """INSERT INTO paper_trades
                           (mint, personality, entry_price, amount_sol, entry_time,
                            exit_price, exit_time, hold_seconds,
                            realised_pnl_sol, realised_pnl_pct, exit_reason, exit_signature,
                            market_cap_at_entry, market_cap_at_exit, outcome,
                            signal_source, ml_score, rugcheck_risk,
                            market_mode_at_entry, fear_greed_at_entry, trade_mode)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                   $13, $14, $15, $16, $17, $18, $19, $20, $21)""",
                        pos.mint, pos.personality, pos.entry_price, pos.size_sol, pos.entry_time,
                        current_price, _pt_exit_time, _pt_hold,
                        pnl_sol, pnl_pct, reason, _pt_exit_sig,
                        _pt_mcap_entry, _pt_mcap_exit, _pt_outcome,
                        pos.signal_source or "unknown", pos.ml_score or 0.0,
                        pos.rugcheck_risk_level or "unknown",
                        self.portfolio.market_mode or "NORMAL", 50.0, "live",
                    )
                    logger.info("LIVE paper_trades fallback INSERT mint=%s outcome=%s pnl=%.4f (entry INSERT had failed or pos predates Session 2b)",
                                pos.mint[:12], _pt_outcome, pnl_sol)
                except Exception as e:
                    logger.error("LIVE close paper_trades fallback INSERT failed mint=%s: %s",
                                 pos.mint, e)
                    try:
                        import sentry_sdk
                        sentry_sdk.capture_exception(e)
                    except Exception:
                        pass

            # === Session 2 v2: on-chain balance snapshot (market_mode='LIVE_ONCHAIN') ===
            # Future sessions inheriting a stale paper-snapshot figure as "wallet
            # balance" caused the phantom 2.07 SOL drain investigation — this row
            # explicitly marks the on-chain truth at close time.
            try:
                _rpc_url = (os.getenv("HELIUS_STAKED_URL") or
                            os.getenv("HELIUS_GATEKEEPER_URL") or
                            os.getenv("HELIUS_RPC_URL") or "")
                if _rpc_url and TRADING_WALLET_ADDRESS:
                    async with aiohttp.ClientSession() as _oc_session:
                        _oc_payload = {
                            "jsonrpc": "2.0", "id": 1, "method": "getBalance",
                            "params": [TRADING_WALLET_ADDRESS],
                        }
                        async with _oc_session.post(
                            _rpc_url, json=_oc_payload,
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as _oc_resp:
                            _oc_data = await _oc_resp.json()
                            _lamports = (_oc_data.get("result") or {}).get("value", 0)
                            _onchain_sol = _lamports / 1_000_000_000
                    await self.pool.execute(
                        """INSERT INTO portfolio_snapshots
                           (timestamp, total_balance_sol, open_positions, daily_pnl_sol, market_mode)
                           VALUES ($1, $2, $3, $4, $5)""",
                        datetime.now(timezone.utc).isoformat(),
                        _onchain_sol, len(self.positions),
                        float(self.portfolio.daily_pnl_sol), "LIVE_ONCHAIN",
                    )
                    if self.redis:
                        await self.redis.set("bot:onchain:balance", str(_onchain_sol))
                        await self.redis.set("bot:onchain:balance:ts", str(time.time()))
                    logger.info("LIVE onchain snapshot: %.4f SOL (wallet=%s)",
                                _onchain_sol, TRADING_WALLET_ADDRESS[:8])
                else:
                    logger.warning("LIVE onchain snapshot skipped: no Helius URL or wallet addr")
            except Exception as e:
                logger.error("LIVE onchain snapshot failed: %s", e)
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(e)
                except Exception:
                    pass

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
        """Evaluate tiered trailing stop for a position. Returns exit reason or None.
        Trail tightens as peak gain grows: None→breakeven→25%→20%→15%→12%.
        State persisted to PostgreSQL (source of truth), mirrored to Redis for dashboard."""
        from services.db import update_trailing_stop

        entry = pos.entry_price
        table = "paper_trades" if TEST_MODE else "trades"

        if not current_price or current_price <= 0 or entry <= 0:
            return None  # Fail safe — never trigger on bad price data

        state_changed = False

        # 1. Update peak price
        if current_price > pos.peak_price:
            pos.peak_price = current_price
            state_changed = True

        # 2. Compute peak gain and get tiered trail percentage
        peak_gain = (pos.peak_price - entry) / entry  # 0.0=breakeven, 1.0=+100%
        trail_pct = get_tiered_trail_pct(peak_gain)

        if trail_pct is None:
            # Below +30% peak: no trail active, rely on hard stop only
            if state_changed and pos.trade_id:
                try:
                    await update_trailing_stop(pos.trade_id, table, pos.peak_price, False, None)
                except Exception:
                    pass
            return None

        # 3. Activate or update trailing stop
        if not pos.trailing_stop_active:
            pos.trailing_stop_active = True
            state_changed = True
            logger.info("Trail ACTIVATED — %s peak_gain=+%.0f%% tier=%.0f%%",
                        pos.mint[:12], peak_gain * 100, trail_pct * 100)

        # 4. Compute stop level based on tier
        if trail_pct == 0.0:
            # Breakeven lock: stop at entry price
            new_stop = entry
        else:
            # Trail from peak
            new_stop = pos.peak_price * (1 - trail_pct)

        # Stop only moves up, never down
        if new_stop > pos.trailing_stop_price:
            pos.trailing_stop_price = new_stop
            pos.trailing_stop_pct = trail_pct * 100  # store as percentage for DB
            state_changed = True

        # 5. Persist to PostgreSQL if anything changed
        if state_changed and pos.trade_id:
            try:
                await update_trailing_stop(
                    pos.trade_id, table, pos.peak_price,
                    pos.trailing_stop_active,
                    pos.trailing_stop_price if pos.trailing_stop_active else None,
                )
            except Exception as e:
                logger.debug("Trailing stop DB update error: %s", e)

        # 6. Check if trailing stop / breakeven is triggered
        if pos.trailing_stop_active and pos.trailing_stop_price > 0 and current_price <= pos.trailing_stop_price:
            pnl_sol = (current_price - entry) / entry * pos.size_sol
            exit_reason = "BREAKEVEN_STOP" if trail_pct == 0.0 else "TRAILING_STOP"
            logger.info("Trail HIT — %s | peak=%.8f stop=%.8f cur=%.8f tier=%.0f%%",
                         pos.mint[:12], pos.peak_price, pos.trailing_stop_price,
                         current_price, trail_pct * 100)
            await self._send_discord(
                f"Trail {exit_reason}\n"
                f"Token: {pos.mint[:12]}...\n"
                f"Peak: {pos.peak_price:.8f} | Stop: {pos.trailing_stop_price:.8f} | Exit: {current_price:.8f}\n"
                f"Est P/L: {'+' if pnl_sol >= 0 else ''}{pnl_sol:.4f} SOL\n"
                f"Personality: {pos.personality}"
            )
            return exit_reason

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

                    # EXIT_EVAL: Log every position check for debugging
                    if current_price > 0 and entry > 0:
                        multiple = current_price / entry
                        pnl_pct = (multiple - 1) * 100
                        logger.info("EXIT_EVAL: %s %s price=$%.8f entry=$%.8f %.2fx (%+.1f%%) held=%.1fm",
                                    pos.personality, pos.mint[:12], current_price, entry,
                                    multiple, pnl_pct, elapsed_min)

                    # Log when price is missing — critical for diagnosing missed exits
                    if current_price <= 0 and elapsed_min > 1:
                        logger.warning("NO_PRICE: %s %s — held %.1fm, price=0 (exits disabled)",
                                      pos.personality, pos.mint[:12], elapsed_min)
                        # Force close stale positions after 5 min with no price
                        # Dead tokens with no trading activity are pure loss
                        stale_threshold = 5.0 if pos.personality == "speed_demon" else 10.0
                        if elapsed_min >= stale_threshold:
                            # One last try before giving up
                            last_try = await self._get_token_price(pos.mint)
                            if last_try > 0:
                                current_price = last_try
                                logger.info("STALE_RECOVERY: %s got price $%.8f on final try",
                                           pos.mint[:12], last_try)
                                # Fall through to normal exit logic below
                            else:
                                logger.info("STALE_EXIT: %s %s — no price for %.1fm, force closing",
                                           pos.personality, pos.mint[:12], elapsed_min)
                                await self._close_position(pos, "stale_no_price", current_price=pos.entry_price)
                                continue

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
                    # Skip if staged exits already fired (token proved itself)
                    early_check_sec = float(os.getenv("SD_EARLY_CHECK_SECONDS", "90"))
                    early_min_move = float(os.getenv("SD_EARLY_MIN_MOVE_PCT", "2.0"))
                    if pos.personality == "speed_demon" and current_price > 0 and entry > 0:
                        if pos.staged_exits_done:
                            pass  # Already hit TP — let trailing ride, skip momentum check
                        else:
                            hold_sec = time.time() - pos.entry_time
                            if early_check_sec - 10 < hold_sec < early_check_sec + 30:
                                pnl_pct = (current_price - entry) / entry * 100
                                if pnl_pct < early_min_move:
                                    logger.info("NO MOMENTUM 90s: %s %.1f%%", pos.mint[:8], pnl_pct)
                                    await self._close_position(pos, "no_momentum_90s", current_price=current_price)
                                    continue

                    # Graduation-specific exit strategy (overrides standard exits)
                    if getattr(pos, "signal_type", None) == "graduation":
                        grad_time_limit = 20  # 20-minute survival window
                        grad_stop_loss = 0.20  # -20% hard stop
                        grad_tp = 1.30  # +30% take profit

                        if elapsed_min >= grad_time_limit and current_price > 0 and entry > 0:
                            if current_price <= entry * 1.05:
                                await self._close_position(pos, "graduation_time_exit", current_price=current_price)
                                continue

                        if current_price > 0 and entry > 0:
                            if current_price <= entry * (1 - grad_stop_loss):
                                await self._close_position(pos, "graduation_stop_loss", current_price=current_price)
                                continue
                            if current_price >= entry * grad_tp:
                                # Sell 95% at +30%, keep 5% moonbag
                                await self._close_position(pos, "graduation_tp_30pct", sell_pct=0.95, current_price=current_price)
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
                            await self._close_position(pos, f"stop_loss_{sl_pct:.0%}", current_price=current_price)
                            continue

                        # 2. Staged take-profits — checked BEFORE time_exit
                        gain = multiple - 1.0  # 0.0 = breakeven, 0.50 = +50%, etc.
                        for exit_rule in strategy.get("staged_exits", []):
                            at_gain = exit_rule.get("at_gain", exit_rule.get("at_multiple", 99) - 1)
                            exit_key = f"+{int(at_gain * 100)}%"
                            if exit_key not in pos.staged_exits_done and gain >= at_gain:
                                remaining_before = pos.remaining_pct
                                logger.info("STAGED_TP: %s hit %s (%.1fx) — selling %d%%",
                                           pos.mint[:12], exit_key, multiple, int(exit_rule["sell_pct"] * 100))
                                await self._close_position(pos, f"staged_tp_{exit_key}", sell_pct=exit_rule["sell_pct"], current_price=current_price)
                                logger.info(
                                    "STAGED_TP_FIRE mint=%s stage=%s nominal_trigger=%.2fx actual_sell_price=%.10f "
                                    "actual_sell_mult=%.2fx sell_frac_of_remaining=%.4f remaining_before=%.4f "
                                    "remaining_after=%.4f cumulative_pnl_sol=%.6f",
                                    pos.mint[:8], exit_key, 1.0 + at_gain, current_price,
                                    current_price / pos.entry_price if pos.entry_price > 0 else 0,
                                    exit_rule["sell_pct"], remaining_before, pos.remaining_pct,
                                    pos.cumulative_pnl_sol,
                                )
                                # Shadow measurement: staged TP hit
                                overshoot = ((multiple - (1.0 + at_gain)) / (1.0 + at_gain)) * 100 if (1.0 + at_gain) > 0 else 0
                                await self._shadow_log("STAGED_TP_HIT", trade_id=pos.trade_id or 0,
                                    mint=pos.mint[:12], stage=exit_key,
                                    nominal_trigger_x=round(1.0 + at_gain, 2),
                                    actual_mult_x=round(multiple, 3),
                                    overshoot_pct=round(overshoot, 2),
                                    sell_frac=exit_rule["sell_pct"],
                                    remaining_before=round(remaining_before, 4),
                                    remaining_after=round(pos.remaining_pct, 4))
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
                            await self._close_position(pos, ts_exit, current_price=current_price)
                            continue

                    # 4. Time-based exit (lowest priority) with momentum extension
                    time_exit = strategy.get("time_exit_minutes")
                    if time_exit and elapsed_min >= time_exit:
                        # Hard ceiling: never extend beyond 2x original time_exit
                        max_extended = time_exit * 2
                        if elapsed_min >= max_extended:
                            await self._close_position(pos, "max_extended_hold", current_price=current_price)
                            continue

                        if current_price > 0 and entry > 0:
                            pnl_pct = (current_price / entry - 1) * 100

                            if pnl_pct > 5.0:
                                # MOMENTUM EXTENSION: profitable at time_exit — let it ride
                                if not pos.trailing_stop_active:
                                    pos.trailing_stop_active = True
                                    pos.peak_price = max(pos.peak_price or 0, current_price)
                                    pos.trailing_stop_pct = 0.10
                                    pos.trailing_stop_price = current_price * 0.90
                                    # Never below entry +1% (always lock SOME profit)
                                    pos.trailing_stop_price = max(pos.trailing_stop_price, entry * 1.01)
                                    logger.info(
                                        "MOMENTUM_EXTEND: %s %s held %.1fm at +%.1f%% — "
                                        "trail activated at %.10f (locked +%.1f%%)",
                                        pos.personality, pos.mint[:12], elapsed_min, pnl_pct,
                                        pos.trailing_stop_price,
                                        (pos.trailing_stop_price / entry - 1) * 100,
                                    )
                                    if pos.trade_id:
                                        try:
                                            table = "paper_trades" if TEST_MODE else "trades"
                                            await self.pool.execute(
                                                f"UPDATE {table} SET trailing_stop_active=$1, trailing_stop_price=$2, trailing_stop_pct=$3 WHERE id=$4",
                                                True, pos.trailing_stop_price, pos.trailing_stop_pct, pos.trade_id,
                                            )
                                        except Exception:
                                            pass
                                continue  # Let trailing stop manage from here

                            elif pnl_pct < -5.0:
                                await self._close_position(pos, "time_exit_loss", current_price=current_price)
                                continue
                            else:
                                await self._close_position(pos, "time_exit_no_movement", current_price=current_price)
                                continue
                        else:
                            await self._close_position(pos, "time_exit_no_movement", current_price=current_price)
                            continue

                    max_hold = strategy.get("max_hold_hours")
                    if max_hold and elapsed_hrs >= max_hold:
                        await self._close_position(pos, "max_hold_time", current_price=current_price)
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

            await asyncio.sleep(2)  # Check every 2 seconds (Redis-first pricing is instant)

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

                    last_prices = getattr(self, "_last_prices", {})
                    for key, pos in list(self.positions.items()):
                        if pos.mint == mint:
                            price = last_prices.get(mint, 0.0)
                            if pos.personality == "whale_tracker":
                                logger.info("WHALE PRIMARY EXIT: %s — tracked wallet selling", pos.mint[:12])
                                await self._close_position(pos, f"whale_primary_exit: {reason}", current_price=price)
                            else:
                                if pos.remaining_pct > 0.50:
                                    await self._close_position(pos, f"smart_money_exit: {reason}", sell_pct=0.50, current_price=price)
                                else:
                                    logger.warning(
                                        "FORCED EXIT: %s %s — reason=%s (smart money selling)",
                                        pos.personality, mint[:12], reason,
                                    )
                                    await self._close_position(pos, reason, current_price=price)
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

            # Budget gate — uses same key as nansen_client v3
            today_key = f"nansen:credits:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
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
                            # nansen_client v3 handles budget increment internally
                            sells = await get_smart_money_dex_sells(session, pos.mint, self.redis)

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
    from services.sentry_init import init_sentry
    init_sentry("bot-core")
    logger.info("Bot Core starting (TEST_MODE=%s)", TEST_MODE)
    logger.info(
        "Position sizing caps: MIN=%s SOL, MAX_ABS=%s SOL, MAX_FRAC=%.4f of wallet",
        os.environ.get("MIN_POSITION_SOL", "0.15"),
        os.environ.get("MAX_POSITION_SOL", "1.50"),
        MAX_POSITION_SOL_FRACTION,
    )

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

    # Load whale wallets from PostgreSQL into Redis cache
    if bot.redis and bot.pool:
        try:
            rows = await bot.pool.fetch(
                "SELECT address FROM watched_wallets WHERE is_active = TRUE"
            )
            if rows:
                await bot.redis.delete("whale:watched_wallets")
                addresses = [r["address"] for r in rows]
                for addr in addresses:
                    await bot.redis.sadd("whale:watched_wallets", addr)
                logger.info("Loaded %d whale wallets into Redis cache", len(addresses))
            else:
                logger.warning("No active whale wallets in PostgreSQL")
        except Exception as e:
            logger.warning("Whale wallet Redis cache load failed: %s", e)

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
