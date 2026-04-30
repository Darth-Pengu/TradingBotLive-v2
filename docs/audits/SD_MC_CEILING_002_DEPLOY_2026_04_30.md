# SD_MC_CEILING_002 deploy 2026-04-30

**Session:** SD-MC-CEILING-002-2026-04-30
**Author:** Claude Code
**Predecessor:** `docs/audits/SD_MC_CEILING_DEPLOY_2026_04_30.md` §5 (Session C rollback — design flaw acknowledged).
**Status:** ✅ DEPLOYED — env var `SD_MC_CEILING_USD=3000` (re-enabled from rollback no-op `999999999`) + new BC-reserves-based gate code in `services/signal_aggregator.py`.

---

## §1 Why this session exists

Session C (`282d9df`, 2026-04-30 ~08:01 UTC) deployed SD_MC_CEILING_001 — a gate at `services/signal_aggregator.py:1833-1845` that read `raw_data.get("usdMarketCap", raw_data.get("market_cap_usd", 0))`. Step 5 verification at 08:30 UTC found the gate **structurally inert** for the dominant signal source: `raw_data["usdMarketCap"] == 0` for fresh pump.fun `new_token` events. SA's own FILTER logs confirm `mc=$0` for every fresh signal. Two of 14 fresh SD trades post-deploy entered with `market_cap_at_entry > 3000` (id 7757 at $9.8k, id 7749 at $4.5k — both stop_loss_20% losses). Env var was rolled back to `999999999` at ~08:35 UTC; code remained in place as harmless no-op.

The Session C audit §5 documented two follow-up options:

1. Move gate to bot_core at entry decision point (uses actual MC, but later in pipeline).
2. Compute MC from BC reserves in SA gate (mirrors bot_core's MC calculation, keeps short-circuit before ML scoring).

Recommended option 2 — preserves the chain prompt's intent of filtering at the entry-gate stage. This session implements option 2.

---

## §2 raw_data field investigation result (Step 2)

**Question:** are `vSolInBondingCurve` / `vTokensInBondingCurve` present in `raw_data` at SA's signal evaluation point for fresh `new_token` signals?

**Investigation method:** trace the data flow rather than add a temporary diagnostic log (which would require a deploy and an out-of-scope second push).

**Trace:**

1. `services/signal_listener.py:545` — `_build_signal(mint, "pumpportal", sig_type, data, age)` passes the full PumpPortal event `data` dict as the `raw_data` field of the signal envelope.
2. `services/signal_listener.py:488-489` — for create events, `data.get("vSolInBondingCurve")` and `data.get("vTokensInBondingCurve")` are confirmed populated (used for Redis price caching at L494-495).
3. `services/signal_aggregator.py:1717` and `:1862` — SA already reads `raw_data.get("vSolInBondingCurve", ...)` for KOTH check and FILTER log line. Field is in scope at the gate location.
4. `services/bot_core.py:927` (live) and `services/paper_trader.py:255-257` (paper) — both compute `market_cap_at_entry = entry_price * 1_000_000_000`. For paper, `entry_price` is already USD; for live, `entry_price = price` returned by `_get_token_price` (also USD). For SA's gate, vSol/vTokens gives SOL price per token; multiply by `market:sol_price` (Redis, USD per SOL) to convert. `market:sol_price=83.19` at session start (verified via Redis MCP).

**Verdict:** ✅ PROCEED with option 2. The required fields are present in raw_data for the dominant SD signal source (pump.fun new_token via PumpPortal WS).

---

## §3 Code change (Step 3)

### §3.1 Module-level env var comment refresh (`services/signal_aggregator.py:48-54`)

Updated leading comment so future readers see _002 history at the env-var declaration:

```python
# SD_MC_CEILING_002 (deployed 2026-04-30) — reject SD entries above market-cap ceiling.
# _002 replaces _001's inert gate (which read raw_data["usdMarketCap"]=$0 for fresh
# pump.fun signals — see docs/audits/SD_MC_CEILING_DEPLOY_2026_04_30.md §5). _002
# computes MC from BC reserves to mirror bot_core's market_cap_at_entry calculation.
# Default 3000 USD per 35h post-recovery data: >$3k = -1.77 SOL / 0% WR / n=39.
# Rollback: set SD_MC_CEILING_USD=999999999 to disable without redeploy.
SD_MC_CEILING_USD = float(os.environ.get("SD_MC_CEILING_USD", "3000.0"))
```

### §3.2 Gate replacement (`services/signal_aggregator.py:1833-1879`)

The gate sits in `_process_signals(redis_conn: aioredis.Redis, pool=None)` so `redis_conn` is in scope for the SOL-price lookup. Placed BEFORE the existing `_apply_speed_demon_prefilters` block — same location as _001, so the Twitter API call is still skipped on rejected tokens.

```python
# SD_MC_CEILING_002 (deployed 2026-04-30) — replaces _001 inert gate.
# Computes MC from BC reserves at signal time, mirroring bot_core's
# market_cap_at_entry = entry_price * 1_000_000_000 calculation
# (paper_trader.py:255-257 and bot_core.py:927). Reads
# vSolInBondingCurve + vTokensInBondingCurve from raw_data and
# market:sol_price from Redis. Falls back to NOT-rejecting if any
# field is missing (fail-open — better to take a trade than block a
# legitimate signal because of cache miss). See
# docs/audits/SD_MC_CEILING_002_DEPLOY_2026_04_30.md.
# Rollback: SD_MC_CEILING_USD=999999999 to disable.
if "speed_demon" in targets:
    mc_at_eval_usd = None
    sol_usd_str = None
    try:
        v_sol = float(raw_data.get("vSolInBondingCurve") or 0)
        v_tokens = float(raw_data.get("vTokensInBondingCurve") or 0)
        if v_sol > 0 and v_tokens > 0:
            entry_price_sol_per_token = v_sol / v_tokens
            sol_usd_str = await redis_conn.get("market:sol_price") if redis_conn else None
            if sol_usd_str:
                sol_usd = float(sol_usd_str)
                # 1B total supply matches pump.fun convention used by
                # paper_trader and bot_core entry MC computation.
                mc_at_eval_usd = entry_price_sol_per_token * 1_000_000_000 * sol_usd
    except (ValueError, TypeError) as e:
        logger.debug("SD MC compute failed for %s: %s", mint[:8], e)
        mc_at_eval_usd = None  # explicit fail-open

    if mc_at_eval_usd is not None and mc_at_eval_usd > SD_MC_CEILING_USD:
        logger.info(
            "SD reject %s: MC $%.0f > ceiling $%.0f (vSol=%.2f vTok=%.0f)",
            mint[:8], mc_at_eval_usd, SD_MC_CEILING_USD, v_sol, v_tokens,
        )
        targets = [t for t in targets if t != "speed_demon"]
        if not targets:
            continue
    elif mc_at_eval_usd is None:
        # Fail-open path — log at debug to avoid noise; this is expected
        # for non-pump.fun signals or when SOL price cache is cold.
        logger.debug(
            "SD MC gate fail-open for %s: insufficient data (vSol=%s vTok=%s sol_usd_present=%s)",
            mint[:8],
            raw_data.get("vSolInBondingCurve"),
            raw_data.get("vTokensInBondingCurve"),
            bool(sol_usd_str),
        )
```

**Design decisions** (with their tradeoffs):

- **Fail-open if data missing.** A signal lacking BC reserves OR a missing `market:sol_price` Redis key produces `mc_at_eval_usd = None` and the gate does NOT reject. This is a deliberate choice — block-on-missing risks rejecting legitimate signals from non-pump.fun sources (geckoterminal_trending, dexpaprika, nansen_screener, etc.) that don't carry pumpportal-shaped reserves. The cost: if the fail-open fraction is too high, gate becomes effectively inert again. Step 6 verification will quantify the rate.
- **`market:sol_price` cache miss.** The key has a short TTL set by market_health. If market_health degrades, the gate fails open service-wide. A future hardening would add Binance fallback or read `market:health.sol_price` JSON, but that's a follow-up.
- **1B supply assumption.** Matches pump.fun convention used by both `paper_trader.py:256` and `bot_core.py:927`. Migrated/post-graduation tokens have different supply but those are filtered out by other gates (KOTH zone, bonding curve progress) before reaching here.

### §3.3 Compile check

```
python -m py_compile services/signal_aggregator.py
→ compile OK
```

---

## §4 Env var re-enable (Step 4)

Via Railway MCP `set-variables` on `signal_aggregator`:

```
SD_MC_CEILING_USD=3000
```

(Was `999999999` from Session C rollback; threshold now active.)

Auto-redeploys signal_aggregator.

---

## §5 Deploy timeline

- 2026-04-30 ~12:25 UTC: env var set via Railway MCP (`SD_MC_CEILING_USD=3000`)
- 2026-04-30 [time UTC]: code commit pushed (`<hash>`)
- 2026-04-30 [time UTC]: signal_aggregator redeploy SUCCESS (verified via Railway MCP logs)

(Trailing timestamps to be filled post-redeploy verification.)

---

## §6 Verification (Step 6)

### §6.a — Log-level: gate firing on real signals

(Filled in Step 6a, post-deploy)

Expected within 30 min of deploy with normal signal flow:
- ≥ 1 `SD reject <mint>: MC $<value> > ceiling $3000 (vSol=... vTok=...)` line
- Occasional `SD MC gate fail-open` debug lines (acceptable; expected for non-pump.fun signals)

### §6.b — Database-level: no high-MC entries leak through

```sql
SELECT id, market_cap_at_entry, entry_time, ml_score, exit_reason, mint
FROM paper_trades
WHERE personality='speed_demon'
  AND entry_time > extract(epoch from NOW() - INTERVAL '60 minutes')
ORDER BY market_cap_at_entry DESC
LIMIT 20;
```

Expected: ZERO rows with `market_cap_at_entry > 3000`. Tolerance: 1-2 fail-open leaks/hour with documented explanation acceptable; >5/hr ⇒ ROLLBACK.

(Result filled in Step 6b, post-deploy)

---

## §7 Fail-open ratio in first 30 min

(To be quantified post-deploy from log sample. Method: count `SD reject` info-level lines vs `SD MC gate fail-open` debug-level lines over a 30-min window with normal traffic.)

---

## §8 Open issues / follow-ups

| ID | priority | notes |
|---|---|---|
| `market:sol_price` cache-miss handling | medium | Currently fails open. If observed leak rate >5%/hr, add fallback (read `market:health.sol_price` JSON; or pin a 1-min in-process cache). Defer until empirically measured. |
| 1B-supply assumption | low | Holds for pump.fun. Migrated tokens with different supply should be filtered out before reaching this gate (KOTH-zone / BC-progress gates). Verify in Step 6 rejection log sample. |
| Non-pumpportal source coverage | low | Signals from geckoterminal/dexpaprika/nansen_* sources lack `vSolInBondingCurve` and will fail-open. Acceptable: those sources go through their own enrichment paths and aren't the SD-rejection target population. |
| AGENT_CONTEXT.md SA env shadow | informational | SA env shows `MAX_SD_POSITIONS=3`, `MIN_POSITION_SOL=0.10`, `SPEED_DEMON_BASE_SIZE_SOL=0.45`, `SPEED_DEMON_MAX_SIZE_SOL=0.75` — these are bot_core-owned variables that should NOT be authoritative on SA. Separate cleanup item (TUNE-008-style env hygiene). Not affecting this session. |

---

## §9 Rollback

**Option A (preferred — fast):** env var rollback via Railway MCP:
```
SD_MC_CEILING_USD=999999999
```
Auto-redeploys signal_aggregator (~10-15 min). Code stays — gate becomes a no-op at the absurd threshold.

**Option B:** code revert:
```bash
git revert HEAD
git push
```
Auto-redeploys signal_aggregator.

Prefer Option A — code is structurally sound, env-var lever is the dial.

---

## §10 Reproducibility

```python
# Set env var
mcp__railway__set-variables(
  service="signal_aggregator",
  variables=["SD_MC_CEILING_USD=3000"],
)

# Verify code change
git log -1 services/signal_aggregator.py

# Verify gate firing post-deploy
mcp__railway__get-logs(
  service="signal_aggregator",
  logType="deploy",
  filter="SD reject OR SD MC gate fail-open",
  lines=200,
)

# DB check
import asyncpg
conn = await asyncpg.connect("postgresql://postgres:<REDACTED>@gondola.proxy.rlwy.net:29062/railway")
await conn.fetch("""
  SELECT id, market_cap_at_entry FROM paper_trades
  WHERE personality='speed_demon'
    AND entry_time > extract(epoch from NOW() - INTERVAL '60 minutes')
    AND market_cap_at_entry > 3000
""")
```
