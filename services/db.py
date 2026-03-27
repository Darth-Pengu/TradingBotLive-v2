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
    # Railway PostgreSQL plugin injects DATABASE_URL automatically.
    # But if a manual DATABASE_URL=sqlite:///... exists, it overrides the plugin.
    # Check multiple env vars to find the PostgreSQL URL.
    candidates = [
        os.getenv("DATABASE_URL", ""),
        os.getenv("DATABASE_PRIVATE_URL", ""),
        os.getenv("DATABASE_PUBLIC_URL", ""),
        os.getenv("POSTGRES_URL", ""),
    ]

    for url in candidates:
        if not url:
            continue
        if url.startswith("sqlite"):
            logger.warning("Skipping SQLite URL: %s — looking for PostgreSQL", url[:30])
            continue
        # Railway provides postgres:// but asyncpg requires postgresql://
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return url

    raise RuntimeError(
        "No PostgreSQL DATABASE_URL found. "
        "Add a PostgreSQL plugin in Railway (it auto-injects DATABASE_URL). "
        "If you have a manual DATABASE_URL=sqlite:///... variable, DELETE it "
        "so the PostgreSQL plugin's URL takes effect."
    )


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

        # --- ML training data on paper_trades ---
        for col, coltype in [
            ("features_json", "TEXT"),
            ("ml_score_at_entry", "DOUBLE PRECISION"),
        ]:
            try:
                await conn.execute(
                    f"ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS {col} {coltype}"
                )
            except Exception:
                pass

        # --- Trailing stop columns (Step 1 migration) ---
        for table in ("paper_trades", "trades"):
            for col, coltype in [
                ("peak_price", "DOUBLE PRECISION DEFAULT NULL"),
                ("trailing_stop_active", "BOOLEAN DEFAULT FALSE"),
                ("trailing_stop_price", "DOUBLE PRECISION DEFAULT NULL"),
                ("trailing_stop_pct", "DOUBLE PRECISION DEFAULT NULL"),
            ]:
                try:
                    await conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}"
                    )
                except Exception:
                    pass  # Column already exists or table doesn't exist yet

        # --- watched_wallets table (PostgreSQL-backed wallet management) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS watched_wallets (
                id                  SERIAL PRIMARY KEY,
                address             TEXT NOT NULL UNIQUE,
                label               TEXT,
                personality_route   TEXT NOT NULL,
                source              TEXT NOT NULL DEFAULT 'nansen',
                chain               TEXT NOT NULL DEFAULT 'solana',
                pnl_30d_sol         NUMERIC,
                pnl_7d_sol          NUMERIC,
                win_rate_30d        NUMERIC,
                win_rate_7d         NUMERIC,
                trade_count_30d     INTEGER,
                trade_count_7d      INTEGER,
                avg_hold_minutes    NUMERIC,
                nansen_labels       TEXT[],
                qualification_score NUMERIC,
                first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_refreshed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_active_at      TIMESTAMPTZ,
                is_active           BOOLEAN NOT NULL DEFAULT TRUE,
                deactivated_reason  TEXT,
                refresh_count       INTEGER NOT NULL DEFAULT 0,
                consecutive_fails   INTEGER NOT NULL DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watched_wallets_route
                ON watched_wallets(personality_route) WHERE is_active = TRUE
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watched_wallets_score
                ON watched_wallets(qualification_score DESC) WHERE is_active = TRUE
        """)

        # --- wallet_refresh_log table (governance audit trail) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_refresh_log (
                id              SERIAL PRIMARY KEY,
                refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                wallets_added   INTEGER NOT NULL DEFAULT 0,
                wallets_removed INTEGER NOT NULL DEFAULT 0,
                wallets_total   INTEGER NOT NULL DEFAULT 0,
                trigger         TEXT NOT NULL,
                notes           TEXT
            )
        """)

        # --- ml_models table (persist ML models to PostgreSQL) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_models (
                id              SERIAL PRIMARY KEY,
                model_name      TEXT NOT NULL,
                model_data      BYTEA NOT NULL,
                meta_json       JSONB,
                trained_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                sample_count    INTEGER,
                accuracy        NUMERIC,
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_models_active
                ON ml_models(model_name, trained_at DESC) WHERE is_active = TRUE
        """)

        # --- governance_state + governance_notes_log (replaces flat files) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS governance_state (
                id              SERIAL PRIMARY KEY,
                decision        TEXT NOT NULL,
                reason          TEXT,
                notes           TEXT,
                market_mode     TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                session         TEXT,
                triggered_by    TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS governance_notes_log (
                id              SERIAL PRIMARY KEY,
                content         TEXT NOT NULL,
                appended_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # --- bot_state table (persistent counters — not Redis) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key             TEXT PRIMARY KEY,
                value_text      TEXT,
                value_int       INTEGER,
                value_float     NUMERIC,
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # --- portfolio_snapshots index for time-series queries ---
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time
                    ON portfolio_snapshots(timestamp DESC)
            """)
        except Exception:
            pass

    logger.info("All database tables verified")


async def get_bot_state(key: str, default=None):
    """Read persistent bot state from PostgreSQL."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT value_text, value_int, value_float FROM bot_state WHERE key = $1", key
    )
    if not row:
        return default
    if row["value_int"] is not None:
        return row["value_int"]
    if row["value_float"] is not None:
        return row["value_float"]
    return row["value_text"]


async def set_bot_state(key: str, value):
    """Write persistent bot state to PostgreSQL."""
    pool = await get_pool()
    if isinstance(value, int):
        await pool.execute(
            """INSERT INTO bot_state (key, value_int, updated_at) VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value_int = $2, updated_at = NOW()""",
            key, value,
        )
    elif isinstance(value, float):
        await pool.execute(
            """INSERT INTO bot_state (key, value_float, updated_at) VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value_float = $2, updated_at = NOW()""",
            key, value,
        )
    else:
        await pool.execute(
            """INSERT INTO bot_state (key, value_text, updated_at) VALUES ($1, $2, NOW())
               ON CONFLICT (key) DO UPDATE SET value_text = $2, updated_at = NOW()""",
            key, str(value),
        )


async def update_trailing_stop(
    trade_id: int,
    table: str,
    peak_price: float,
    trailing_stop_active: bool,
    trailing_stop_price: float | None,
) -> None:
    """Persist trailing stop state to PostgreSQL (source of truth)."""
    pool = await get_pool()
    exit_col = "exit_time" if table == "paper_trades" else "closed_at"
    await pool.execute(
        f"""UPDATE {table} SET
            peak_price = $1,
            trailing_stop_active = $2,
            trailing_stop_price = $3
            WHERE id = $4 AND {exit_col} IS NULL""",
        peak_price, trailing_stop_active, trailing_stop_price, trade_id,
    )
