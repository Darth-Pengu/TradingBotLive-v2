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
    """Fetch top traders from Nansen smart money holdings.
    NOTE: Nansen /smart-money/holdings returns HTTP 405 (method/endpoint changed).
    The Nansen MCP tools are all token-specific — they require a tokenAddress and
    cannot return a general list of smart money wallet addresses.
    This function now logs the raw response for debugging and returns whatever it can."""
    from services.nansen_client import get_smart_money_holdings, get_wallet_pnl

    wallets = []

    # Source 1: Smart money holdings (top 50 by value)
    try:
        holdings = await get_smart_money_holdings(session, redis_conn)
        # Debug: log raw response structure
        if holdings:
            logger.warning("NANSEN RESPONSE TYPE: %s", type(holdings))
            if isinstance(holdings, list):
                logger.warning("NANSEN LIST LENGTH: %d", len(holdings))
                if holdings and isinstance(holdings[0], dict):
                    logger.warning("NANSEN FIRST ITEM KEYS: %s", list(holdings[0].keys()))
                    logger.warning("NANSEN FIRST ITEM: %s", str(holdings[0])[:500])
            elif isinstance(holdings, dict):
                logger.warning("NANSEN TOP KEYS: %s", list(holdings.keys()))
                for k, v in list(holdings.items())[:3]:
                    logger.warning("  KEY %s: type=%s val=%s", k, type(v), str(v)[:200])
        else:
            logger.warning("Nansen holdings returned empty/None — endpoint likely 405 (known issue)")

        if isinstance(holdings, list):
            for h in holdings:
                # Try every known field name for wallet address
                addr = (h.get("owner") or h.get("address") or h.get("wallet_address")
                        or h.get("walletAddress") or h.get("owner_address") or "")
                if not addr or len(addr) < 32:
                    continue
                labels = h.get("labels", h.get("smart_money_labels", h.get("label", [])))
                if isinstance(labels, str):
                    labels = [labels]
                wallets.append({
                    "address": addr,
                    "label": labels[0] if labels else "Smart Money",
                    "nansen_labels": labels or ["Smart Money"],
                    "pnl_30d_sol": float(h.get("pnl_30d", h.get("total_pnl", h.get("pnlUsd", 0))) or 0),
                    "pnl_7d_sol": float(h.get("pnl_7d", 0) or 0),
                    "win_rate_30d": float(h.get("win_rate", h.get("win_rate_30d", h.get("winRate", 0))) or 0),
                    "win_rate_7d": float(h.get("win_rate_7d", 0) or 0),
                    "trade_count_30d": int(h.get("trade_count", h.get("trade_count_30d", h.get("totalTrades", 0))) or 0),
                    "trade_count_7d": int(h.get("trade_count_7d", 0) or 0),
                    "avg_hold_minutes": float(h.get("avg_hold_minutes", 0) or 0),
                })
    except Exception as e:
        logger.warning("Nansen smart money holdings fetch failed: %s", e)
        holdings = []

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

    n_holdings = len(holdings) if isinstance(holdings, list) else 0
    if n_holdings > 0 and len(wallets) == 0:
        logger.warning("Nansen holdings returned %d items but 0 wallets mapped — field names may have changed", n_holdings)
    logger.info("Fetched %d wallets from Nansen smart money (from %d holdings)", len(wallets), n_holdings)
    return wallets


async def fetch_vybe_top_traders(session: aiohttp.ClientSession, redis_conn=None) -> list[dict]:
    """Fetch top Solana traders from Vybe Network API.
    Primary wallet source — Vybe returns real scored wallets with PnL data."""
    vybe_key = os.getenv("VYBE_API_KEY", "")
    if not vybe_key:
        logger.warning("VYBE_API_KEY not set — Vybe wallet fetch skipped")
        return []

    # Vybe domain is .xyz with X-API-Key auth (not .com, not Bearer)
    url = "https://api.vybenetwork.xyz/v4/wallets/top-traders"
    headers = {"X-API-Key": vybe_key}
    params = {
        "resolution": "30d",
        "limit": 50,
        "sortByDesc": "realizedPnlUsd",
        "chain": "solana",
    }
    try:
        async with session.get(url, headers=headers, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raw = await resp.text()
                logger.warning("Vybe top traders HTTP %d: %s", resp.status, raw[:300])
                return []
            data = await resp.json()
            traders = data if isinstance(data, list) else data.get("data", data.get("results", data.get("items", [])))
            if not isinstance(traders, list):
                logger.warning("Vybe unexpected response type: %s — keys: %s",
                               type(data), list(data.keys()) if isinstance(data, dict) else "n/a")
                return []

            wallets = []
            for t in traders:
                address = (t.get("ownerAddress") or t.get("accountAddress")
                           or t.get("address") or t.get("wallet") or "")
                if not address or len(address) < 32:
                    continue
                metrics = t.get("metrics", t)
                win_rate = float(metrics.get("winRate", 0) or 0)
                pnl = float(metrics.get("realizedPnlUsd", metrics.get("pnl", 0)) or 0)
                trade_count = int(metrics.get("tradeCount", metrics.get("totalTrades", 0)) or 0)
                # Normalize win_rate: if > 1 assume it's a percentage, else fraction
                if win_rate > 1:
                    wr_frac = win_rate / 100.0
                else:
                    wr_frac = win_rate
                score = min(100, int(wr_frac * 100))
                wallets.append({
                    "address": address,
                    "label": t.get("label", "Vybe Top Trader"),
                    "nansen_labels": ["Vybe Top Trader"],
                    "pnl_30d_sol": round(pnl / 150.0, 2),  # rough USD->SOL conversion
                    "pnl_7d_sol": 0,
                    "win_rate_30d": round(wr_frac, 4),
                    "win_rate_7d": 0,
                    "trade_count_30d": trade_count,
                    "trade_count_7d": 0,
                    "avg_hold_minutes": 0,
                    "source": "vybe",
                    "personality_route": "whale_tracker",
                    "qualification_score": max(score, 50),
                })
            logger.info("Vybe: fetched %d top traders", len(wallets))
            return wallets
    except Exception as e:
        logger.warning("Vybe top traders error: %s", e)
        return []


async def fetch_and_upsert_wallets(trigger: str = "scheduled") -> dict:
    """
    Main entry point. Fetches wallets from Nansen, scores them,
    upserts to watched_wallets table in PostgreSQL.
    """
    # Distributed lock — only one service runs wallet fetch at a time
    import redis.asyncio as _aioredis
    try:
        _redis = _aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True, max_connections=2)
        lock_key = f"nansen:fetch:lock:{trigger}"
        lock_acquired = await _redis.set(lock_key, "1", ex=300, nx=True)
        if not lock_acquired:
            logger.info("Nansen fetch lock held by another service — skipping")
            return {"added": 0, "removed": 0, "total": 0, "whale_count": 0, "analyst_count": 0, "skipped": True}
    except Exception:
        _redis = None  # No Redis — proceed without lock

    try:
        return await _fetch_and_upsert_inner(trigger)
    finally:
        if _redis:
            try:
                await _redis.delete(f"nansen:fetch:lock:{trigger}")
                await _redis.aclose()
            except Exception:
                pass


async def _fetch_and_upsert_inner(trigger: str) -> dict:
    """Inner implementation of wallet fetch — called under distributed lock."""
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
        redis_conn = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True, max_connections=2)
        await redis_conn.ping()
    except Exception:
        redis_conn = None

    async with aiohttp.ClientSession() as session:
        raw_wallets = await _fetch_nansen_top_traders(session, redis_conn)
        vybe_wallets = await fetch_vybe_top_traders(session, redis_conn)

    if redis_conn:
        await redis_conn.close()

    # --- Upsert Vybe wallets directly (pre-scored, skip criteria filtering) ---
    vybe_upserted = 0
    if vybe_wallets:
        async with pool.acquire() as conn:
            for w in vybe_wallets:
                addr = w["address"]
                if addr in excluded:
                    continue
                try:
                    await conn.execute(
                        """INSERT INTO watched_wallets
                           (address, label, personality_route, source, chain,
                            pnl_30d_sol, win_rate_30d, trade_count_30d,
                            qualification_score, last_refreshed_at, is_active,
                            refresh_count)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),TRUE,1)
                           ON CONFLICT (address) DO UPDATE SET
                             is_active = TRUE,
                             score = EXCLUDED.score,
                             qualification_score = EXCLUDED.qualification_score,
                             source = EXCLUDED.source,
                             pnl_30d_sol = EXCLUDED.pnl_30d_sol,
                             win_rate_30d = EXCLUDED.win_rate_30d,
                             trade_count_30d = EXCLUDED.trade_count_30d,
                             last_refreshed_at = NOW(),
                             refresh_count = watched_wallets.refresh_count + 1""",
                        addr,
                        w.get("label", "Vybe Top Trader"),
                        w.get("personality_route", "whale_tracker"),
                        "vybe", "solana",
                        w.get("pnl_30d_sol"),
                        w.get("win_rate_30d"),
                        w.get("trade_count_30d"),
                        w.get("qualification_score", 50),
                    )
                    vybe_upserted += 1
                except Exception as e:
                    logger.warning("Vybe upsert failed for %s: %s", addr[:12], e)
        logger.info("Vybe: upserted %d wallets into watched_wallets", vybe_upserted)

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


# Nansen-verified smart money wallets extracted via MCP token_current_top_holders
# across JUP, PENGU, FARTCOIN, BONK, MOODENG, PUMP (March 2026)
NANSEN_MCP_SEED_WALLETS = [
    # --- Funds ---
    ("5sZKTZ6j5UgQqVvWa8VBvxYLtD43dW8VG7ZBuMjPQrBt", "Sigil Fund", 85),
    ("5CmWF9DMrcCtpuw3g1rnx9zYLX39bNwEX7dSEeaKFPPf", "Jump Capital", 90),
    ("69GA1mJCEqyYxj57CCeamy2WGx7wM3ABEwuUFMmatu2d", "Jump Capital", 90),
    ("6v3snejEvRsTzeUZV2yKAcRgbxRz3iMJJgpeqJ1CxM6P", "Jump Capital", 85),
    ("EmhH92KmdXmFEHE4AWZgwbigb4pFnbvB9cc2EFo9cB1g", "Defiance Capital", 88),
    ("5pU7WKL47At6rHLM4CmFCSPRdT32J1LHSgPFhWGuXZqc", "Jump Capital", 85),
    ("39K7QEaZDix2XGTzUaYMwVGrQp2Kaoi2uTuDp2R3zCS7", "LVT Capital", 75),
    ("HYv9xRtTBYfDEiNm77HCtaG4teeuq1t3aDnXqEXwfNhj", "Arche Fund", 70),
    ("FGgSRDZ49jALiaBkmPxEqJ3e3zm3G8e15nuiwy6pF8iK", "Defiance Capital", 85),
    ("NTmngBUcT84deqwGLV6hBFCU8eoi1M593XJjTV85uN5", "LVT Capital", 75),
    ("DJwPBhtiPQXKjTY2RzH6DgJ2eqU3uBTfLuLXoUL9D4dK", "LVT Capital", 75),
    ("4DPxYoJ5DgjvXPUtZdT3CYUZ3EEbSPj4zMNEVFJTd1Ts", "Sigil Fund", 85),
    ("GRowGA1cq9abztLhXJykXoD7sAnxUARQap2sRX2CZgpv", "Big Brain Holdings", 80),
    ("6jMQdtwEAfoBvKdE4HYGTdHCRSxYfCrgPmjQ6rnGr5mn", "Sigil Fund", 85),
    ("EJiSzS1MUVNwmohP3NcS1TZ9hYxguG2oaZeuGTbeVaPC", "Digital Finance Group", 85),
    ("HfkVTCtjS7ahgHarPLd63nez927zFCZqR9Jih9jEyQE", "Shima Capital", 80),
    ("5fd1DvDqwaP9n4FBMh3ePDHaB6Bc9z7FoKvikWztKSFZ", "Moonrock Capital", 80),
    ("H5biaZ2G1xU6hBHVbgzaqN3KuRvdwXmWxhxh5YN8QPuZ", "Borderless Capital", 85),
    ("K1EmQH2KhE7k8TYcvb7kpnStecfVXRy1HWKLPeJ8tjF", "Borderless Capital", 80),
    # --- Smart Traders ---
    ("5bFi2MNTzcSwPg3Hy5rb5db6Nr9g5qtNwJnTfE4Kb9iS", "All Time Smart Trader", 80),
    ("FEeSRuEDk8ENZbpzXjn4uHPz3LQijbeKRzhqVr5zPSJ9", "DevmonsGG", 70),
    ("6MZ1ZnnDMX9FadzFjGAnYKjGqSkRfhDhLuwGawniAWry", "Smart Trader", 65),
    ("Aqa8H5hmHe9MFY9sW6widbqEuaYv7q2KnRo25ApPhWhA", "bluemoon97", 60),
    ("Gf9XgdmvNHt8fUTFsWAccNbKeyDXsgJyZN8iFJKg5Pbd", "Smart Trader", 60),
    ("A2QeYEF9G7Gm6rvEB2JkgMNHzN7XSs9JbtreD7jSJ4m1", "Smart Trader", 65),
    ("2QUfGV4R3bDmKEDenmfCquumP5bWtRhyC94DBVQyzRuR", "Charles", 65),
    ("J6RVc1kqErGzx9z3qdnfL9RpMu86jLgfSpYEqLjhpzod", "Smart Trader", 60),
    ("GjRacG5qhTwQfUd5r8qAYdiUEVpArJt1T3VcYJh9SWR4", "commwealth.eth", 70),
    ("WVP9dmT87EKugPH9q7pkkxGdKgHH1NSyErrzNoz1Pxs", "Smart Trader", 65),
    ("ZT2qpqVCAy4hESALMbfBMkHVDztRcJXU5hngAge3hYy", "kapitaljapan.eth", 65),
    ("4daxRFKDKpnAj7eUKivevh3hKD6k1MbNeAwKo29u9cz5", "30D Smart Trader", 60),
    ("5t6PV94bXpjc6xd9cHe9CXo9eE37bwcvJWPNzKbymt4H", "180D Smart Trader", 65),
    ("8UKmoBC5vcJpjPDYL9wa6nTacCN83hwp6gvxnhdHFDhS", "Smart Trader", 65),
    ("HTf5vRAM579SKZSYRWBq9T8QPCBLNBrduLdx38aMnFRy", "Smart Trader", 60),
    ("GscdcAbdsaecVVtPsnaWMUMaLTRVHErxfjhtmQr1pYzh", "Smart Trader", 60),
    ("EVCwZrtPFudcjw69RZ9Qogt8dW2HjBp6EiMgv1ujdYuJ", "180D Smart Trader", 60),
]


async def _seed_nansen_mcp_wallets(pool) -> int:
    """Upsert Nansen MCP-verified smart money wallets into watched_wallets."""
    inserted = 0
    async with pool.acquire() as conn:
        for addr, label, score in NANSEN_MCP_SEED_WALLETS:
            try:
                await conn.execute(
                    """INSERT INTO watched_wallets
                       (address, label, personality_route, source, chain,
                        qualification_score, last_refreshed_at, is_active,
                        refresh_count)
                       VALUES ($1,$2,$3,$4,$5,$6,NOW(),TRUE,1)
                       ON CONFLICT (address) DO UPDATE SET
                         is_active = TRUE,
                         qualification_score = GREATEST(watched_wallets.qualification_score, EXCLUDED.qualification_score),
                         last_refreshed_at = NOW(),
                         refresh_count = watched_wallets.refresh_count + 1""",
                    addr, label, "whale_tracker", "nansen_mcp", "solana", score,
                )
                inserted += 1
            except Exception as e:
                logger.warning("MCP seed upsert failed for %s: %s", addr[:12], e)
    logger.info("Nansen MCP seed: upserted %d wallets", inserted)
    return inserted


async def ensure_wallets_populated():
    """On startup, ensure watched_wallets has data. If empty or low, seed from all sources."""
    pool = await get_pool()
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM watched_wallets WHERE is_active = TRUE"
    )
    if count < 20:
        logger.info("Only %d active wallets (need 20+) — seeding from Nansen MCP + API sources", count)

        # Phase 1: Seed hardcoded Nansen MCP-verified wallets (always works)
        mcp_count = await _seed_nansen_mcp_wallets(pool)

        # Phase 2: Try live API fetch (Nansen direct + Vybe) for additional wallets
        try:
            result = await fetch_and_upsert_wallets(trigger="startup")
            logger.info("Live API fetch: +%d wallets (total=%d)", result["added"], result["total"])
        except Exception as e:
            logger.warning("Live API wallet fetch failed: %s — using MCP seed only", e)

        total = await pool.fetchval(
            "SELECT COUNT(*) FROM watched_wallets WHERE is_active = TRUE"
        )
        logger.info("Wallet population complete: %d active wallets (MCP=%d)", total, mcp_count)
    else:
        logger.info("Wallet DB populated: %d active wallets", count)
