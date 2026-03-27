"""
ZMN Bot Nansen Wallet Fetcher
===============================
Fetches, scores, and upserts whale/smart money wallets to PostgreSQL.
Replaces whale_wallets.json with PostgreSQL-backed watched_wallets table.

Called by:
- Governance agent (every 48 hours)
- Startup check (if watched_wallets table is empty)
- Manual trigger via Discord (!zmn refresh-wallets) or dashboard POST

Uses existing nansen_client.py for HTTP calls — no duplicate auth/session logic.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

from services.db import get_pool

load_dotenv()

logger = logging.getLogger("nansen_wallet_fetcher")

NANSEN_API_KEY = os.getenv("NANSEN_API_KEY", "")

# --- Whale Tracker criteria ---
NANSEN_WHALE_CRITERIA = {
    "pnl_30d_sol_min": 50.0,
    "win_rate_30d_min": 0.52,
    "trade_count_30d_min": 20,
    "score_min": 45,
    "target_count": 75,
    "fallback_pnl_min": 25.0,
}

# --- Analyst / Smart Money criteria ---
NANSEN_ANALYST_CRITERIA = {
    "win_rate_7d_min": 0.60,
    "win_rate_30d_min": 0.55,
    "trade_count_30d_min": 10,
    "avg_hold_max_min": 240,
    "score_min": 50,
    "target_count": 40,
}


def _score_whale(wallet: dict) -> float:
    """Compute qualification_score for a whale tracker wallet (0-100)."""
    score = 0.0
    pnl = float(wallet.get("pnl_30d_sol", 0) or 0)
    wr30 = float(wallet.get("win_rate_30d", 0) or 0)
    tc30 = int(wallet.get("trade_count_30d", 0) or 0)
    pnl7 = float(wallet.get("pnl_7d_sol", 0) or 0)
    labels = wallet.get("nansen_labels", []) or []

    if pnl >= 500:     score += 30
    elif pnl >= 200:   score += 20
    elif pnl >= 100:   score += 15
    elif pnl >= 50:    score += 10

    if wr30 >= 0.70:   score += 25
    elif wr30 >= 0.60: score += 18
    elif wr30 >= 0.52: score += 10

    if tc30 >= 100:    score += 15
    elif tc30 >= 50:   score += 10
    elif tc30 >= 20:   score += 5

    if pnl7 > 0:       score += 15

    label_str = " ".join(labels).lower()
    if "smart money" in label_str:     score += 15
    elif "fund" in label_str:          score += 10
    elif "dex trader" in label_str:    score += 10

    return round(score, 2)


def _score_analyst(wallet: dict) -> float:
    """Compute qualification_score for an analyst smart money wallet (0-100)."""
    score = 0.0
    wr7 = float(wallet.get("win_rate_7d", 0) or 0)
    wr30 = float(wallet.get("win_rate_30d", 0) or 0)
    hold = float(wallet.get("avg_hold_minutes", 999) or 999)
    pnl7 = float(wallet.get("pnl_7d_sol", 0) or 0)

    if wr7 >= 0.80:    score += 35
    elif wr7 >= 0.70:  score += 25
    elif wr7 >= 0.60:  score += 15

    if wr30 >= 0.75:   score += 25
    elif wr30 >= 0.65: score += 18
    elif wr30 >= 0.55: score += 10

    if hold <= 30:     score += 20
    elif hold <= 60:   score += 15
    elif hold <= 120:  score += 10
    elif hold <= 240:  score += 5

    if pnl7 > 0:       score += 20

    return round(score, 2)


def _passes_exclusion(wallet: dict) -> tuple[bool, str | None]:
    """Returns (passes, reason_if_not). Checks hard exclusion criteria."""
    labels = " ".join(wallet.get("nansen_labels", []) or []).lower()
    wr30 = float(wallet.get("win_rate_30d", 0) or 0)
    tc30 = int(wallet.get("trade_count_30d", 0) or 0)

    if "rug" in labels:
        return False, "rug_pull_label"
    if wr30 < 0.40 and wr30 > 0:
        return False, "win_rate_too_low"
    if tc30 > 500:
        return False, "likely_bot_mev"
    return True, None


async def _fetch_nansen_top_traders(session: aiohttp.ClientSession, redis_conn=None) -> list[dict]:
    """Fetch top traders from Nansen smart money holdings + token PnL leaderboards.
    Maps Nansen response fields to our internal wallet dict format."""
    from services.nansen_client import get_smart_money_holdings, get_wallet_pnl

    wallets = []

    # Source 1: Smart money holdings (top 50 by value)
    try:
        holdings = await get_smart_money_holdings(session, redis_conn)
        for h in holdings:
            addr = h.get("owner", h.get("address", h.get("wallet_address", "")))
            if not addr:
                continue
            labels = h.get("labels", h.get("smart_money_labels", []))
            if isinstance(labels, str):
                labels = [labels]
            wallets.append({
                "address": addr,
                "label": labels[0] if labels else "Smart Money",
                "nansen_labels": labels or ["Smart Money"],
                "pnl_30d_sol": float(h.get("pnl_30d", h.get("total_pnl", 0)) or 0),
                "pnl_7d_sol": float(h.get("pnl_7d", 0) or 0),
                "win_rate_30d": float(h.get("win_rate", h.get("win_rate_30d", 0)) or 0),
                "win_rate_7d": float(h.get("win_rate_7d", 0) or 0),
                "trade_count_30d": int(h.get("trade_count", h.get("trade_count_30d", 0)) or 0),
                "trade_count_7d": int(h.get("trade_count_7d", 0) or 0),
                "avg_hold_minutes": float(h.get("avg_hold_minutes", 0) or 0),
            })
    except Exception as e:
        logger.warning("Nansen smart money holdings fetch failed: %s", e)

    # Enrich with individual PnL data for top wallets (rate-limited)
    for w in wallets[:20]:
        try:
            pnl_data = await get_wallet_pnl(session, w["address"], days=30, redis_conn=redis_conn)
            if pnl_data:
                data = pnl_data.get("data", pnl_data)
                if isinstance(data, dict):
                    w["pnl_30d_sol"] = float(data.get("total_pnl", data.get("pnl", w["pnl_30d_sol"])) or 0)
                    w["win_rate_30d"] = float(data.get("win_rate", w["win_rate_30d"]) or 0)
                    w["trade_count_30d"] = int(data.get("trade_count", data.get("total_trades", w["trade_count_30d"])) or 0)
        except Exception:
            pass

    logger.info("Fetched %d wallets from Nansen smart money", len(wallets))
    return wallets


async def fetch_and_upsert_wallets(trigger: str = "scheduled") -> dict:
    """
    Main entry point. Fetches wallets from Nansen, scores them,
    upserts to watched_wallets table in PostgreSQL.
    """
    pool = await get_pool()
    added = removed = 0

    # Load permanently excluded addresses
    excluded = set()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT address FROM watched_wallets
                   WHERE is_active = FALSE
                   AND deactivated_reason IN ('rug_pull', 'manual_exclusion')"""
            )
            excluded = {r["address"] for r in rows}
    except Exception:
        pass

    redis_conn = None
    try:
        import redis.asyncio as aioredis
        redis_conn = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        await redis_conn.ping()
    except Exception:
        redis_conn = None

    async with aiohttp.ClientSession() as session:
        raw_wallets = await _fetch_nansen_top_traders(session, redis_conn)

    if redis_conn:
        await redis_conn.close()

    # --- Score whale tracker wallets ---
    whale_wallets = []
    for w in raw_wallets:
        addr = w.get("address", "")
        if not addr or addr in excluded:
            continue
        passes, reason = _passes_exclusion(w)
        if not passes:
            continue

        c = NANSEN_WHALE_CRITERIA
        pnl30 = float(w.get("pnl_30d_sol", 0) or 0)
        wr30 = float(w.get("win_rate_30d", 0) or 0)
        tc30 = int(w.get("trade_count_30d", 0) or 0)

        if pnl30 < c["pnl_30d_sol_min"]:
            continue
        if wr30 > 0 and wr30 < c["win_rate_30d_min"]:
            continue
        if tc30 > 0 and tc30 < c["trade_count_30d_min"]:
            continue

        score = _score_whale(w)
        if score < c["score_min"]:
            continue

        w["qualification_score"] = score
        w["personality_route"] = "whale_tracker"
        whale_wallets.append(w)

    whale_wallets.sort(key=lambda x: x["qualification_score"], reverse=True)
    whale_wallets = whale_wallets[:NANSEN_WHALE_CRITERIA["target_count"]]

    # Fallback if too few
    if len(whale_wallets) < 30:
        logger.warning("Only %d whale wallets at full criteria — lowering PnL threshold", len(whale_wallets))
        for w in raw_wallets:
            addr = w.get("address", "")
            if addr in excluded or addr in {ww["address"] for ww in whale_wallets}:
                continue
            passes, _ = _passes_exclusion(w)
            if not passes:
                continue
            pnl30 = float(w.get("pnl_30d_sol", 0) or 0)
            if pnl30 < NANSEN_WHALE_CRITERIA["fallback_pnl_min"]:
                continue
            score = _score_whale(w)
            if score < 30:
                continue
            w["qualification_score"] = score
            w["personality_route"] = "whale_tracker"
            whale_wallets.append(w)
            if len(whale_wallets) >= NANSEN_WHALE_CRITERIA["target_count"]:
                break

    # --- Score analyst wallets ---
    analyst_wallets = []
    whale_addrs = {w["address"] for w in whale_wallets}
    for w in raw_wallets:
        addr = w.get("address", "")
        if not addr or addr in excluded:
            continue
        passes, _ = _passes_exclusion(w)
        if not passes:
            continue

        c = NANSEN_ANALYST_CRITERIA
        wr7 = float(w.get("win_rate_7d", 0) or 0)
        wr30 = float(w.get("win_rate_30d", 0) or 0)
        tc30 = int(w.get("trade_count_30d", 0) or 0)
        hold = float(w.get("avg_hold_minutes", 999) or 999)

        if wr7 > 0 and wr7 < c["win_rate_7d_min"]:
            continue
        if wr30 > 0 and wr30 < c["win_rate_30d_min"]:
            continue
        if tc30 > 0 and tc30 < c["trade_count_30d_min"]:
            continue
        if hold > 0 and hold > c["avg_hold_max_min"]:
            continue

        score = _score_analyst(w)
        if score < c["score_min"]:
            continue

        w["qualification_score"] = score
        w["personality_route"] = "both" if addr in whale_addrs else "analyst"
        analyst_wallets.append(w)

    analyst_wallets.sort(key=lambda x: x["qualification_score"], reverse=True)
    analyst_wallets = analyst_wallets[:NANSEN_ANALYST_CRITERIA["target_count"]]

    # --- Upsert to PostgreSQL ---
    all_wallets = whale_wallets + [
        w for w in analyst_wallets
        if w["address"] not in whale_addrs
    ]

    async with pool.acquire() as conn:
        for w in all_wallets:
            addr = w["address"]
            try:
                result = await conn.fetchrow(
                    """INSERT INTO watched_wallets
                       (address, label, personality_route, source, chain,
                        pnl_30d_sol, pnl_7d_sol, win_rate_30d, win_rate_7d,
                        trade_count_30d, avg_hold_minutes, nansen_labels,
                        qualification_score, last_refreshed_at, is_active,
                        refresh_count)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW(),TRUE,1)
                       ON CONFLICT (address) DO UPDATE SET
                         personality_route   = EXCLUDED.personality_route,
                         pnl_30d_sol         = EXCLUDED.pnl_30d_sol,
                         pnl_7d_sol          = EXCLUDED.pnl_7d_sol,
                         win_rate_30d        = EXCLUDED.win_rate_30d,
                         win_rate_7d         = EXCLUDED.win_rate_7d,
                         trade_count_30d     = EXCLUDED.trade_count_30d,
                         avg_hold_minutes    = EXCLUDED.avg_hold_minutes,
                         nansen_labels       = EXCLUDED.nansen_labels,
                         qualification_score = EXCLUDED.qualification_score,
                         last_refreshed_at   = NOW(),
                         is_active           = TRUE,
                         refresh_count       = watched_wallets.refresh_count + 1,
                         consecutive_fails   = 0
                       RETURNING (xmax = 0) AS inserted""",
                    addr,
                    w.get("label", ""),
                    w["personality_route"],
                    "nansen", "solana",
                    w.get("pnl_30d_sol"),
                    w.get("pnl_7d_sol"),
                    w.get("win_rate_30d"),
                    w.get("win_rate_7d"),
                    w.get("trade_count_30d"),
                    w.get("avg_hold_minutes"),
                    w.get("nansen_labels", []),
                    w["qualification_score"],
                )
                if result and result["inserted"]:
                    added += 1
            except Exception as e:
                logger.warning("Upsert failed for %s: %s", addr[:12], e)

        # Deactivate wallets not seen in this refresh (nansen-sourced only)
        current_addrs = [w["address"] for w in all_wallets]
        if current_addrs:
            deactivated = await conn.execute(
                """UPDATE watched_wallets SET
                   is_active = FALSE,
                   deactivated_reason = 'performance_drop'
                   WHERE source = 'nansen'
                   AND is_active = TRUE
                   AND address != ALL($1::text[])""",
                current_addrs,
            )
            try:
                removed = int(str(deactivated).split()[-1])
            except Exception:
                removed = 0

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM watched_wallets WHERE is_active = TRUE"
        )
        await conn.execute(
            """INSERT INTO wallet_refresh_log
               (wallets_added, wallets_removed, wallets_total, trigger, notes)
               VALUES ($1, $2, $3, $4, $5)""",
            added, removed, total or 0, trigger,
            f"whale={len(whale_wallets)} analyst={len(analyst_wallets)}",
        )

    logger.info(
        "Wallet refresh complete [%s]: +%d -%d total=%d (whale=%d analyst=%d)",
        trigger, added, removed, total or 0,
        len(whale_wallets), len(analyst_wallets),
    )
    return {
        "added": added, "removed": removed, "total": total or 0,
        "whale_count": len(whale_wallets),
        "analyst_count": len(analyst_wallets),
    }


async def get_active_wallets(personality_route: str | None = None) -> list[dict]:
    """Load active wallets from PostgreSQL. Used by signal_listener and governance."""
    pool = await get_pool()
    if personality_route:
        rows = await pool.fetch(
            """SELECT address, label, personality_route, qualification_score,
                      nansen_labels, pnl_30d_sol, win_rate_30d
               FROM watched_wallets
               WHERE is_active = TRUE
               AND (personality_route = $1 OR personality_route = 'both')
               ORDER BY qualification_score DESC""",
            personality_route,
        )
    else:
        rows = await pool.fetch(
            """SELECT address, label, personality_route, qualification_score,
                      nansen_labels, pnl_30d_sol, win_rate_30d
               FROM watched_wallets
               WHERE is_active = TRUE
               ORDER BY qualification_score DESC"""
        )
    return [dict(r) for r in rows]


async def ensure_wallets_populated():
    """On startup, ensure watched_wallets has data. If empty, do initial fetch."""
    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM watched_wallets WHERE is_active = TRUE"
    )
    if count == 0:
        logger.info("No wallets in DB — running initial Nansen fetch...")
        try:
            result = await fetch_and_upsert_wallets(trigger="startup")
            logger.info("Initial wallet fetch: %d wallets loaded", result["total"])
        except Exception as e:
            logger.error("Initial wallet fetch failed: %s", e)
            logger.warning("Falling back to whale_wallets.json for this session")
    else:
        logger.info("Wallet DB populated: %d active wallets", count)
