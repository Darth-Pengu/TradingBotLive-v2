"""ML-SCORE-ATH-VALIDATION-001 — fetch 72h post-entry ATH per mint.

Research artefact. NOT scheduled, NOT consumed by production.

For each unique SD-paper mint in the Apr 22 – May 5 2026 window:
  1. Skip if already cached in mint_ath_lookups (idempotent re-run).
  2. GET GeckoTerminal /networks/solana/tokens/{mint}/pools.
  3. If pool found, GET /pools/{addr}/ohlcv/minute?aggregate=5&before={entry+72h}&limit=864.
  4. Extract max(high) within entry_time .. entry_time+72h.
  5. Persist to mint_ath_lookups.
  6. Save .tmp_ml_ath_validation/PROGRESS.md every 50 mints.

Pacing: 2.0s per HTTP call (≈30 req/min — at GeckoTerminal free tier cap).
On 429: exponential backoff 1→2→4→8→16→32→60s, max 10 min per call.
"""
import os, sys, asyncio, aiohttp, asyncpg, json, time, traceback
from pathlib import Path

DB = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB:
    print("ERR: no DATABASE_PUBLIC_URL/DATABASE_URL in env", file=sys.stderr); sys.exit(2)

W_START = 1776816000.0   # 2026-04-22 00:00 UTC
W_END   = 1777990608.0   # 2026-05-05 14:16:48 UTC (BOT-CORE-ML-GATE-001 active)
GT      = "https://api.geckoterminal.com/api/v2"
PACING_S = 5.0
PROGRESS = Path(".tmp_ml_ath_validation/PROGRESS.md")
STATE_LOG = Path(".tmp_ml_ath_validation/fetch_log.txt")

# Force UTF-8 stdout/stderr so log lines with non-ASCII don't blow up on Windows cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # py3.7+
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Log function: ASCII-only output (avoid Unicode arrows so cp1252 consoles never break).
def L(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        # last-ditch: strip non-ascii and try again
        try: print(line.encode("ascii", "replace").decode("ascii"), flush=True)
        except Exception: pass
    try:
        with STATE_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

async def gt_get(session, url, max_retries=8):
    backoff = 1
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=20) as r:
                if r.status == 429:
                    L(f"429 sleep {backoff}s ({url[-80:]})")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue
                if r.status == 404:
                    return {"_status": 404}
                if r.status != 200:
                    return {"_status": r.status, "_url": url}
                return await r.json()
        except asyncio.TimeoutError:
            L(f"timeout sleep {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception as e:
            L(f"exception {type(e).__name__}: {e} sleep {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
    return {"_status": "max_retries"}

async def fetch_one(session, mint, entry_epoch):
    """Returns dict suitable for upsert into mint_ath_lookups."""
    out = {
        "mint": mint,
        "ath_price_usd": None,
        "ath_timestamp": None,
        "ath_mc_usd": None,
        "data_source": None,
        "ohlcv_point_count": 0,
        "fetch_window_start": entry_epoch,
        "fetch_window_end": entry_epoch + 72*3600,
    }
    # 1. pool lookup
    j = await gt_get(session, f"{GT}/networks/solana/tokens/{mint}/pools")
    await asyncio.sleep(PACING_S)
    if j.get("_status"):
        out["data_source"] = f"gt_pool_http_{j['_status']}"
        return out
    data = j.get("data") or []
    if not data:
        out["data_source"] = "no_pool"
        return out
    pool = (data[0].get("id") or "")
    pool_addr = pool.split("_", 1)[-1] if "_" in pool else pool
    # 2. ohlcv
    before = int(entry_epoch + 72*3600)
    url = f"{GT}/networks/solana/pools/{pool_addr}/ohlcv/minute?aggregate=5&before_timestamp={before}&limit=864"
    j2 = await gt_get(session, url)
    await asyncio.sleep(PACING_S)
    if j2.get("_status"):
        out["data_source"] = f"gt_ohlcv_http_{j2['_status']}"
        return out
    ohlcv = (((j2.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
    out["ohlcv_point_count"] = len(ohlcv)
    # 5m candles span [c[0], c[0]+300). Include any candle that overlaps
    # [entry_epoch, entry_epoch+72h] — i.e. the candle containing entry counts.
    # Note: the entry-spanning candle's high MAY include pre-entry trades within
    # the same 5min bucket; we accept this as a known caveat to avoid undercounting
    # post-entry peaks that occur in the same bucket as entry.
    win_lo, win_hi = entry_epoch, entry_epoch + 72*3600
    win = [c for c in ohlcv if (c[0] + 300) > win_lo and c[0] < win_hi]
    if not win:
        out["data_source"] = "gt_no_ohlcv_in_window"
        return out
    ath = max(c[2] for c in win)  # high
    ath_ts = next(c[0] for c in win if c[2] == ath)
    out["ath_price_usd"] = float(ath)
    out["ath_timestamp"] = float(ath_ts)
    out["ath_mc_usd"] = float(ath) * 1_000_000_000  # pump.fun supply convention
    out["data_source"] = "gecko_terminal"
    return out

def write_progress(processed, total, start_t, last_mint, breakdown):
    elapsed = time.time() - start_t
    rate = processed / max(elapsed, 1)
    remaining = (total - processed) / max(rate, 1e-6)
    PROGRESS.write_text(
        f"# ML-ATH fetch progress\n\n"
        f"- processed: {processed}/{total}\n"
        f"- last_mint: {last_mint}\n"
        f"- elapsed: {elapsed:.0f}s\n"
        f"- rate: {rate*60:.1f} mints/min\n"
        f"- eta: {remaining:.0f}s ({remaining/60:.1f} min)\n"
        f"- source breakdown:\n"
        + "\n".join(f"  - {k}: {v}" for k,v in sorted(breakdown.items()))
    )

async def main():
    pool = await asyncpg.create_pool(DB, min_size=1, max_size=2)
    try:
        async with pool.acquire() as c:
            # Only fetch rows where paper peak_price is NULL (~635 of 1097).
            # For the other 462 (TRAILING_STOP, stale_no_price, staged_tp), paper has
            # intra-second peak_price from the PumpPortal price-monitor loop which is
            # higher-resolution than GT 5m OHLCV — use that directly in §5.x analysis.
            mints = await c.fetch("""
                SELECT DISTINCT ON (mint) mint, entry_time
                FROM paper_trades
                WHERE personality='speed_demon'
                  AND trade_mode='paper'
                  AND entry_time >= $1
                  AND entry_time <  $2
                  AND peak_price IS NULL
                ORDER BY mint, entry_time ASC
            """, W_START, W_END)
            already = await c.fetch("SELECT mint FROM mint_ath_lookups")
            already_set = {r["mint"] for r in already}
        L(f"loaded {len(mints)} unique mints; {len(already_set)} already cached")
        todo = [(r["mint"], float(r["entry_time"])) for r in mints if r["mint"] not in already_set]
        L(f"todo this run: {len(todo)}")
        if not todo:
            L("nothing to do — already complete")
            return

        breakdown = {}
        start_t = time.time()
        async with aiohttp.ClientSession(headers={"User-Agent":"zmn-ml-ath-validation/1"}) as sess:
            for i, (mint, et) in enumerate(todo, 1):
                try:
                    rec = await fetch_one(sess, mint, et)
                except Exception as e:
                    L(f"fatal on mint {mint}: {type(e).__name__}: {e}")
                    rec = {"mint": mint, "ath_price_usd": None, "ath_timestamp": None,
                           "ath_mc_usd": None, "data_source": f"exception_{type(e).__name__}",
                           "ohlcv_point_count": 0,
                           "fetch_window_start": et, "fetch_window_end": et + 72*3600}
                # upsert
                async with pool.acquire() as c:
                    await c.execute("""
                        INSERT INTO mint_ath_lookups (
                          mint, ath_price_usd, ath_timestamp, ath_mc_usd,
                          fetch_window_start, fetch_window_end,
                          data_source, ohlcv_point_count, fetched_at)
                        VALUES ($1,$2, to_timestamp($3), $4, to_timestamp($5), to_timestamp($6), $7, $8, NOW())
                        ON CONFLICT (mint) DO UPDATE SET
                          ath_price_usd=EXCLUDED.ath_price_usd,
                          ath_timestamp=EXCLUDED.ath_timestamp,
                          ath_mc_usd=EXCLUDED.ath_mc_usd,
                          data_source=EXCLUDED.data_source,
                          ohlcv_point_count=EXCLUDED.ohlcv_point_count,
                          fetched_at=NOW()
                    """, rec["mint"], rec["ath_price_usd"], rec["ath_timestamp"],
                          rec["ath_mc_usd"], rec["fetch_window_start"], rec["fetch_window_end"],
                          rec["data_source"], rec["ohlcv_point_count"])
                src = rec["data_source"] or "unknown"
                breakdown[src] = breakdown.get(src, 0) + 1
                if i % 50 == 0:
                    write_progress(i, len(todo), start_t, mint, breakdown)
                    L(f"... {i}/{len(todo)}  rate={i/(time.time()-start_t)*60:.1f}/min  sources={breakdown}")
            write_progress(len(todo), len(todo), start_t, todo[-1][0], breakdown)
            L(f"DONE. final breakdown: {breakdown}")
    finally:
        await pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        L("KeyboardInterrupt — exiting cleanly")
