"""
ZMN Bot Risk Manager
=====================
Quarter-Kelly position sizing with drawdown scaling, time-of-day multipliers,
streak multipliers, and hard portfolio limits.

Hard rules from AGENT_CONTEXT Section 4 — never overridden in code:
- 25% max portfolio exposure
- 60% reserve floor
- 1.0 SOL daily loss limit → EMERGENCY_STOP
- 20% drawdown → STOP ALL TRADING
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("risk_manager")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STARTING_CAPITAL_SOL = float(os.getenv("STARTING_CAPITAL_SOL", "20"))

# --- Quarter-Kelly parameters (Section 4) ---
KELLY_PARAMS = {
    "speed_demon":   {"win_rate": 0.35, "avg_win": 2.00, "avg_loss": 0.50},
    "analyst":       {"win_rate": 0.45, "avg_win": 1.00, "avg_loss": 0.30},
    "whale_tracker": {"win_rate": 0.40, "avg_win": 1.50, "avg_loss": 0.40},
}

# --- Hard position limits (Section 4) ---
MAX_POSITION_PCT = {
    "speed_demon":   0.03,   # 3% of portfolio
    "analyst":       0.05,   # 5%
    "whale_tracker": 0.04,   # 4%
}
# Per AGENT_CONTEXT: below 0.10 SOL, transaction fees destroy edge
MIN_POSITION_SOL = float(os.getenv("MIN_POSITION_SOL", "0.10"))
MAX_CONCURRENT_PER_PERSONALITY = 3
MAX_CONCURRENT_WHALE = 2
PORTFOLIO_MAX_EXPOSURE = 0.25   # 25% total — never exceed
RESERVE_FLOOR_PCT = 0.60        # Always keep 60% in reserve
DAILY_LOSS_LIMIT_SOL = float(os.environ.get("DAILY_LOSS_LIMIT_SOL", "1.0"))  # Triggers EMERGENCY_STOP
CORRELATION_HAIRCUT = 0.70       # pump.fun tokens ~70% correlated

# --- Drawdown-based position scaling (Section 4) ---
DRAWDOWN_MULTIPLIERS = {
    (0.00, 0.05): 1.00,
    (0.05, 0.10): 0.75,
    (0.10, 0.15): 0.50,
    (0.15, 0.20): 0.25,
    (0.20, 1.00): 0.00,   # >20% drawdown: STOP ALL TRADING
}

CONSECUTIVE_LOSS_MULTIPLIERS = {0: 1.0, 1: 1.0, 2: 0.85, 3: 0.65, 4: 0.50, 5: 0.25}

# --- Time-of-day multipliers (Section 4, UTC) ---
TIME_OF_DAY_MULTIPLIERS = {
    (0, 4):   0.70,   # Asia
    (4, 8):   0.55,   # Dead zone
    (8, 12):  0.90,   # EU opens
    (12, 17): 1.00,   # Peak: EU+US overlap
    (17, 21): 0.90,   # US afternoon
    (21, 24): 0.70,   # Declining
}
WEEKEND_MULTIPLIER = 0.70  # Fri eve–Sun

# --- Market mode sizing multipliers (Section 8) ---
MARKET_MODE_MULTIPLIERS = {
    "HIBERNATE":  0.00,
    "DEFENSIVE":  0.50,
    "NORMAL":     1.00,
    "AGGRESSIVE": 1.25,
    "FRENZY":     1.50,
}

# --- Trailing stop configuration (per personality) ---
# activation_pct: profit % above entry at which trailing stop activates
# trail_pct: % below peak price at which trailing stop triggers exit
# Overridable via env vars so governance agent can tune without redeploy
# Market-adaptive trailing stop distance multipliers
TRAILING_STOP_MARKET_MULTIPLIERS = {
    "HIBERNATE":  0.50,   # Very tight — barely active
    "DEFENSIVE":  0.70,   # Tighter — protect gains quickly
    "NORMAL":     1.00,
    "AGGRESSIVE": 1.20,   # Looser — let winners run
    "FRENZY":     1.50,   # Much looser — extreme volatility expected
}

TRAILING_STOP_CONFIG = {
    "speed_demon": {
        "activation_pct": float(os.getenv("TS_SPD_ACTIVATION", "15")),
        "trail_pct": float(os.getenv("TS_SPD_TRAIL", "8")),
    },
    "analyst": {
        "activation_pct": float(os.getenv("TS_ANL_ACTIVATION", "25")),
        "trail_pct": float(os.getenv("TS_ANL_TRAIL", "12")),
    },
    "whale_tracker": {
        "activation_pct": float(os.getenv("TS_WHL_ACTIVATION", "20")),
        "trail_pct": float(os.getenv("TS_WHL_TRAIL", "10")),
    },
}


@dataclass
class PortfolioState:
    """Current portfolio state for risk calculations."""
    total_balance_sol: float = 0.0
    peak_balance_sol: float = 0.0
    daily_pnl_sol: float = 0.0
    open_positions: dict = field(default_factory=dict)  # mint -> {personality, size_sol, entry_price}
    consecutive_losses: dict = field(default_factory=lambda: {"speed_demon": 0, "analyst": 0, "whale_tracker": 0})
    market_mode: str = "NORMAL"


def _quarter_kelly(personality: str) -> float:
    """Calculate quarter-Kelly fraction for a personality."""
    p = KELLY_PARAMS[personality]
    win_rate = p["win_rate"]
    avg_win = p["avg_win"]
    avg_loss = p["avg_loss"]
    b = avg_win / avg_loss  # odds ratio
    q = 1 - win_rate
    kelly_full = (b * win_rate - q) / b
    return max(0, kelly_full * 0.25)


def _drawdown_multiplier(portfolio: PortfolioState) -> float:
    """Get drawdown-based position scaling multiplier."""
    if portfolio.peak_balance_sol <= 0:
        return 1.0
    drawdown = (portfolio.peak_balance_sol - portfolio.total_balance_sol) / portfolio.peak_balance_sol
    drawdown = max(0, drawdown)
    for (low, high), mult in DRAWDOWN_MULTIPLIERS.items():
        if low <= drawdown < high:
            return mult
    return 0.0  # >20% drawdown — stop trading


def _streak_multiplier(personality: str, portfolio: PortfolioState) -> float:
    """Get consecutive loss multiplier."""
    losses = portfolio.consecutive_losses.get(personality, 0)
    losses = min(losses, max(CONSECUTIVE_LOSS_MULTIPLIERS.keys()))
    return CONSECUTIVE_LOSS_MULTIPLIERS.get(losses, 0.25)


def _time_of_day_multiplier() -> float:
    """Get time-of-day sizing multiplier (UTC)."""
    now = datetime.now(timezone.utc)
    hour = now.hour
    # Weekend check (Friday 21:00 UTC through Sunday 23:59 UTC)
    weekday = now.weekday()
    if weekday == 4 and hour >= 21:  # Friday evening
        return WEEKEND_MULTIPLIER
    if weekday in (5, 6):  # Saturday, Sunday
        return WEEKEND_MULTIPLIER

    for (start, end), mult in TIME_OF_DAY_MULTIPLIERS.items():
        if start <= hour < end:
            return mult
    return 0.70


def _total_exposure(portfolio: PortfolioState) -> float:
    """Calculate total open position exposure in SOL."""
    return sum(pos.get("size_sol", 0) for pos in portfolio.open_positions.values())


def _personality_position_count(personality: str, portfolio: PortfolioState) -> int:
    """Count open positions for a personality."""
    return sum(1 for pos in portfolio.open_positions.values() if pos.get("personality") == personality)


def _tokens_with_personality(mint: str, portfolio: PortfolioState) -> list[str]:
    """Return which personalities already hold a token.
    Keys in open_positions are f'{personality}:{mint}', so compare pos['mint']."""
    return [pos["personality"] for key, pos in portfolio.open_positions.items()
            if pos.get("mint") == mint]


def calculate_position_size(
    personality: str,
    mint: str,
    portfolio: PortfolioState,
    ml_score: float = 0.0,
    volatility_ratio: float = 1.0,
) -> float:
    """
    Calculate position size in SOL.
    Returns 0.0 if trade should be rejected.

    Formula: quarterKelly x volatilityRatio x drawdownMultiplier x streakMultiplier x timeOfDayMultiplier
    Capped at per-personality max AND portfolio limits.
    """
    # --- HARD BLOCKS (return 0 immediately) ---

    # Daily loss limit check
    if portfolio.daily_pnl_sol <= -DAILY_LOSS_LIMIT_SOL:
        logger.warning("DAILY LOSS LIMIT reached (%.2f SOL) — rejecting all trades", portfolio.daily_pnl_sol)
        return 0.0

    # Drawdown check
    dd_mult = _drawdown_multiplier(portfolio)
    if dd_mult == 0.0:
        logger.warning("Drawdown >20%% — STOP ALL TRADING")
        return 0.0

    # Market mode check
    mode_mult = MARKET_MODE_MULTIPLIERS.get(portfolio.market_mode, 1.0)
    if mode_mult == 0.0:
        logger.info("HIBERNATE mode — no new positions")
        return 0.0

    # Concurrent position limits
    max_concurrent = MAX_CONCURRENT_WHALE if personality == "whale_tracker" else MAX_CONCURRENT_PER_PERSONALITY
    if _personality_position_count(personality, portfolio) >= max_concurrent:
        logger.info("%s at max concurrent positions (%d)", personality, max_concurrent)
        return 0.0

    # Max 2 personalities in same token
    existing_personalities = _tokens_with_personality(mint, portfolio)
    if len(existing_personalities) >= 2:
        logger.info("Max 2 personalities already in %s — rejecting", mint)
        return 0.0

    # Portfolio max exposure check
    current_exposure = _total_exposure(portfolio)
    max_new_exposure = (portfolio.total_balance_sol * PORTFOLIO_MAX_EXPOSURE) - current_exposure
    if max_new_exposure <= 0:
        logger.info("Portfolio at 25%% max exposure — rejecting")
        return 0.0

    # Reserve floor check
    available = portfolio.total_balance_sol - current_exposure
    reserve_required = portfolio.total_balance_sol * RESERVE_FLOOR_PCT
    available_after_reserve = available - reserve_required
    if available_after_reserve <= 0:
        logger.info("Reserve floor (60%%) would be breached — rejecting")
        return 0.0

    # --- CALCULATE SIZE ---
    qk = _quarter_kelly(personality)
    streak_mult = _streak_multiplier(personality, portfolio)
    tod_mult = _time_of_day_multiplier()

    # Full formula from Section 4
    position = (
        qk
        * volatility_ratio
        * dd_mult
        * streak_mult
        * tod_mult
        * mode_mult
        * portfolio.total_balance_sol
    )

    # If another personality already holds this token, halve position (Section 3)
    if existing_personalities:
        position *= 0.50
        logger.info("Another personality in %s — halving position", mint)

    # Apply correlation haircut
    position *= CORRELATION_HAIRCUT

    # HARD CAP: per-personality maximum — never exceeded regardless of Kelly result
    max_pos = portfolio.total_balance_sol * MAX_POSITION_PCT[personality]
    position = min(position, max_pos)

    # Cap at available exposure
    position = min(position, max_new_exposure)
    position = min(position, available_after_reserve)

    # Floor check
    if position < MIN_POSITION_SOL:
        logger.info("Position %.4f SOL below minimum %.2f — rejecting", position, MIN_POSITION_SOL)
        return 0.0

    return round(position, 4)


# --- Emergency check ---
async def check_emergency_conditions(portfolio: PortfolioState, redis_conn: aioredis.Redis | None = None) -> bool:
    """
    Returns True if EMERGENCY_STOP should be triggered.
    Publishes to alerts:emergency if triggered.
    """
    reasons = []

    if portfolio.daily_pnl_sol <= -DAILY_LOSS_LIMIT_SOL:
        reasons.append(f"Daily loss limit: {portfolio.daily_pnl_sol:.2f} SOL")

    if portfolio.peak_balance_sol > 0:
        dd_pct = (portfolio.peak_balance_sol - portfolio.total_balance_sol) / portfolio.peak_balance_sol
        if dd_pct >= 0.20:
            reasons.append(f"Drawdown: {dd_pct:.1%}")

    if reasons:
        msg = "EMERGENCY_STOP: " + "; ".join(reasons)
        logger.critical(msg)
        if redis_conn:
            await redis_conn.publish("alerts:emergency", json.dumps({
                "reason": msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        return True

    return False


# --- Standalone test ---
async def main():
    logger.info("Risk Manager module loaded — running self-test")

    portfolio = PortfolioState(
        total_balance_sol=20.0,
        peak_balance_sol=20.0,
        daily_pnl_sol=0.0,
        market_mode="NORMAL",
    )

    for personality in ["speed_demon", "analyst", "whale_tracker"]:
        qk = _quarter_kelly(personality)
        size = calculate_position_size(personality, "TestMint123", portfolio)
        logger.info("%s: quarter-Kelly=%.4f, position=%.4f SOL", personality, qk, size)

    logger.info("Risk Manager self-test complete")


if __name__ == "__main__":
    asyncio.run(main())
