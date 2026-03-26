"""
Shared PostgreSQL connection pool for all ZMN Bot services.
=============================================================
All services import `get_pool()` from here — one pool, one schema.
Tables are created on first connection via `_init_tables()`.

DATABASE_URL must be a PostgreSQL connection string.
Railway provides this automatically when a Postgres plugin is added.
"""

import logging
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("db")

_pool: asyncpg.Pool | None = None


def _get_dsn() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Add a PostgreSQL plugin in Railway or set DATABASE_URL manually."
        )
    # Railway provides postgres:// but asyncpg requires postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("sqlite"):
        raise RuntimeError(
            "SQLite is no longer supported — data is lost on every Railway restart. "
            "Set DATABASE_URL to a PostgreSQL connection string."
        )
    return url


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        dsn = _get_dsn()
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)
        await _init_tables()
        logger.info("PostgreSQL pool ready (%d–%d connections)", 2, 10)
    return _pool


async def _init_tables():
    """Create all tables if they don't exist. Runs once on startup."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                mint TEXT NOT NULL,
                personality TEXT NOT NULL,
                action TEXT NOT NULL,
                amount_sol DOUBLE PRECISION,
                entry_price DOUBLE PRECISION,
                exit_price DOUBLE PRECISION,
                pnl_sol DOUBLE PRECISION,
                pnl_pct DOUBLE PRECISION,
                features_json TEXT,
                outcome TEXT,
                ml_score DOUBLE PRECISION,
                signal_sources TEXT,
                created_at DOUBLE PRECISION NOT NULL,
                closed_at DOUBLE PRECISION
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                total_balance_sol DOUBLE PRECISION,
                open_positions INTEGER,
                daily_pnl_sol DOUBLE PRECISION,
                market_mode TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS treasury_sweeps (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                amount_sol DOUBLE PRECISION NOT NULL,
                balance_before_sol DOUBLE PRECISION NOT NULL,
                balance_after_sol DOUBLE PRECISION NOT NULL,
                signature TEXT,
                status TEXT NOT NULL DEFAULT 'success',
                error_message TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id SERIAL PRIMARY KEY,
                mint TEXT NOT NULL,
                symbol TEXT DEFAULT '',
                personality TEXT NOT NULL,
                entry_price DOUBLE PRECISION,
                exit_price DOUBLE PRECISION,
                amount_sol DOUBLE PRECISION NOT NULL,
                slippage_pct DOUBLE PRECISION DEFAULT 0,
                fees_sol DOUBLE PRECISION DEFAULT 0,
                entry_time DOUBLE PRECISION NOT NULL,
                exit_time DOUBLE PRECISION,
                hold_seconds DOUBLE PRECISION,
                realised_pnl_sol DOUBLE PRECISION,
                realised_pnl_pct DOUBLE PRECISION,
                exit_reason TEXT,
                signal_source TEXT,
                ml_score DOUBLE PRECISION,
                entry_signature TEXT,
                exit_signature TEXT,
                market_mode_at_entry TEXT DEFAULT 'NORMAL',
                fear_greed_at_entry DOUBLE PRECISION
            )
        """)

    logger.info("All database tables verified")
