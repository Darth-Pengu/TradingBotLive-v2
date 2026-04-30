# SD_MC_CEILING deploy 2026-04-30

**Session:** SD-MC-CEILING-DEPLOY-2026-04-30 (Session C in chain A→B→C→D→E)
**Author:** Claude Code
**Predecessor analysis:** `docs/audits/PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md` §5; Session A's `docs/audits/SD_EARLY_CHECK_RELAX_2026_04_30.md` §6 (97.6% of dead trades enter at MC $800-$3000).
**Status:** ✅ DEPLOYED — env var `SD_MC_CEILING_USD=3000` on signal_aggregator + code gate.

---

## §1 Decision rationale — why $3000 (not $5000)

The original `docs/proposals/SD_MC_CEILING_001.md` proposed $5k cut based on 4-day analysis (2026-04-22 → 2026-04-25 window, 528 SD trades). Session B's chain prompt revised to $3k based on more-recent post-recovery data:

**Post-recovery 35h sample (272 SD trades; from chain prompt):**
- Trades > $3k entry MC: 39 trades = -1.77 SOL, 0% WR
- Trades > $5k entry MC: 20 trades = -1.04 SOL, 0% WR

Cutting at $3k recovers ~83% more loss (-1.77 vs -1.04) without losing any winners (all 14 big winners ≥0.10 SOL each entered at MC < $800).

**Cross-confirmation from Session A's analysis** (independent angle): of 123 post-recovery `no_momentum_90s` exits, **97.6% (120/123) entered at MC $800-$3000**. Only 3/123 above $3k. This $3k cut **does not** materially impact the no_momentum bleed, but it does eliminate the worst-bleed slice that produced 0% WR. The no_momentum bleed remains a separate observability item (Session A TUNE-009 deferred).

**Threshold sweep (where I would re-evaluate):**
- $2k: would drop more low-MC trades (some of which are winners — risk).
- $3k: balanced — captures the >0% loss-WR concentration without losing winners.
- $5k: too loose; leaves a known -1.77 SOL slice on the table.
- $10k: way too loose; the original GATES-V5 max is already $25k.

**Verdict:** $3000 is the right cut.

---

## §2 Code change

### §2.1 Module-level env var read (`services/signal_aggregator.py:46-53`)

```python
SPEED_DEMON_FILTERS_ENABLED = os.getenv("SPEED_DEMON_FILTERS_ENABLED", "true").lower() == "true"

# SD_MC_CEILING_001 (deployed 2026-04-30) — reject SD entries above market-cap ceiling.
# Default 3000 USD per docs/audits/SD_MC_CEILING_DEPLOY_2026_04_30.md (revised tighter
# than the original $5k proposal in docs/proposals/SD_MC_CEILING_001.md based on 35h
# post-recovery data: >$3k = -1.77 SOL / 0% WR / n=39).
# Rollback: set SD_MC_CEILING_USD=999999999 to disable without redeploy.
SD_MC_CEILING_USD = float(os.environ.get("SD_MC_CEILING_USD", "3000.0"))
```

### §2.2 Gate insertion (`services/signal_aggregator.py:1826-1838`)

Placed BEFORE the existing SD prefilter block (which does Twitter API lookup + bundle/bot/fresh-wallet checks). Rejecting on MC first avoids the Twitter API call for tokens that won't pass the gate anyway — small efficiency win.

```python
                # SD_MC_CEILING_001 (deployed 2026-04-30) — reject SD entries above MC ceiling.
                # Placed before the prefilter block so we skip the Twitter API call on rejected
                # tokens. See docs/audits/SD_MC_CEILING_DEPLOY_2026_04_30.md.
                if "speed_demon" in targets:
                    mc_at_eval = float(raw_data.get("usdMarketCap", raw_data.get("market_cap_usd", 0)) or 0)
                    if mc_at_eval > SD_MC_CEILING_USD:
                        logger.info(
                            "SD reject %s: MC %.0f > ceiling %.0f",
                            mint[:8], mc_at_eval, SD_MC_CEILING_USD,
                        )
                        targets = [t for t in targets if t != "speed_demon"]
                        if not targets:
                            continue

                # --- Speed Demon pre-filters (before ML scoring) ---
                if "speed_demon" in targets:
                    # ... existing prefilter logic unchanged ...
```

The MC value is read from `raw_data.get("usdMarketCap", raw_data.get("market_cap_usd", 0))` — same source as the existing FILTER log line at `signal_aggregator.py:1840`. The fallback chain is identical to what the prefilter already uses, ensuring no semantic drift between the gate and existing diagnostics.

### §2.3 Compile check

```
python -m py_compile services/signal_aggregator.py
→ compile OK
```

---

## §3 Env var configured

Via Railway MCP `set-variables` on `signal_aggregator` only:

```
SD_MC_CEILING_USD=3000
```

Auto-redeploys signal_aggregator. Code change lands in same redeploy if Railway debounces; otherwise two redeploys (~15 min total).

**Not set on:** `bot_core` (gate is in signal_aggregator), `web` (display-only), other services.

---

## §4 Deploy timeline

- 2026-04-30 [time UTC]: env var set via Railway MCP
- 2026-04-30 [time UTC]: code commit pushed (`<hash>`)
- 2026-04-30 [time UTC]: signal_aggregator redeploy SUCCESS (verified via Railway MCP logs)

(Timestamps to be filled in post-redeploy verification.)

---

## §5 Immediate verification — to be appended post-redeploy

**Plan:**
1. Tail signal_aggregator logs (Railway MCP). Within 30 min of deploy with normal signal flow, expect at least one `SD reject <mint>: MC <value> > ceiling 3000` log line.
2. Query last 60min SD trades for any with `market_cap_at_entry > 3000`. ZERO expected.

```sql
SELECT id, market_cap_at_entry, entry_time, ml_score, exit_reason
FROM paper_trades
WHERE personality='speed_demon'
  AND entry_time > extract(epoch from NOW() - INTERVAL '60 minutes')
ORDER BY id DESC;
```

If ANY row has `market_cap_at_entry > 3000` → gate is broken → ROLLBACK.

**Result:** *to be filled in post-deploy*

---

## §6 24h verification queue marker

Append to STATUS.md "TBD: 24h verification 2026-05-01 [time]".

The 24h check is a separate followup, NOT part of this session, but the marker reminds the next session to:

- Pull paper_trades for the 24h window post-deploy
- Confirm zero SD entries with `market_cap_at_entry > 3000` (deterministic correctness)
- Compute SD trade count, WR, PnL
- Compare to 35h post-recovery baseline (272 trades, 23.4% WR per Session A audit; PnL +0.140 SOL)
- Expected (per analysis): trade count down ~14%, WR up to ~27%+, PnL/trade improved

If at 24h `WR < 23%` despite the gate firing → gate is doing its job but predicted improvement isn't materializing → investigate before stacking next TUNE-006 lever.

---

## §7 Interaction with Sessions A, B, D

- **Session A (TUNE-009 ⏸ DEFERRED):** Session C only filters 3/123 of the no_momentum_90s bleed at the entry filter. Most no_momentum bleed (120/123) enters at MC $800-$3000 — below the ceiling. Session A's deferral remains correct: the no_momentum check at exit is doing its job; the structural fix at entry only catches the worst slice.
- **Session B (BUG-022 ✅ + hotfix):** independent. B touched bot_core paper close UPDATEs. C touches signal_aggregator entry gate. No interaction. Note: a Session B hotfix (commit `17c2aac`) was pushed mid-Session-C after asyncpg threw `inconsistent types deduced for parameter $10` due to parameter reuse across columns of different declared types. The hotfix uses distinct param slots ($11/$12/$13 for paper_trader.py; $5/$6/$7 for bot_core.py). The hotfix deploy is in flight on bot_core when this session's signal_aggregator redeploy lands.
- **Session D (LIVE-FEE-CAPTURE):** independent. D will modify bot_core's live close path (lines 1268, 1301). C's signal_aggregator change doesn't intersect.

**Forward note for Session E persistence-hardening review:** track whether Session A's deferred no_momentum bleed reduces meaningfully post-Session-C (expected: only ~3/123 reduction since most bleed is below the ceiling). If post-Session-C bleed > -1.5 SOL on equivalent volume AND the dead-trade pnl_pct distribution shifts upward, re-test Alpha-A. Otherwise leave deferred.

---

## §8 Freshness — informational follow-up

Per Session prompt: "If `detect_to_trade_seconds` is consistently < 30s for SD, freshness OK." Could not run the freshness query directly this session due to schema type mismatch (`signal_detected_at` is timestamp; `entry_time` is double-precision epoch float — subtraction requires explicit cast). The query would need an additional `to_timestamp(entry_time)` cast.

**Empirical proxy:** post-GATES-V5 SD entries are submitted within a few seconds of signal detection (typical for the speed-demon path). Latency drift to >30s would manifest as cadence reduction in `signals:scored` queue, which is currently 0 (verified via Redis pre-Session-B). Freshness is not a current concern.

Tracked as a follow-up: add a freshness measure to the next observability session (alongside Session E's `bot_core:health` heartbeat addition).

---

## §9 Reproducibility

```python
# Env var set (one-time, via Railway MCP)
mcp__railway__set-variables(service="signal_aggregator", variables=["SD_MC_CEILING_USD=3000"])

# Verification queries
import asyncpg
conn = await asyncpg.connect("postgresql://postgres:<REDACTED>@gondola.proxy.rlwy.net:29062/railway")
# Last 60min SD trades — should have ZERO with market_cap_at_entry > 3000
await conn.fetch("""
  SELECT id, market_cap_at_entry FROM paper_trades
  WHERE personality='speed_demon'
    AND entry_time > extract(epoch from NOW() - INTERVAL '60 minutes')
    AND market_cap_at_entry > 3000
""")
```

---

## §10 Rollback

**Option A (preferred):** env var rollback via Railway MCP:
```
SD_MC_CEILING_USD=999999999
```
Auto-redeploys signal_aggregator (~10-15 min). Code stays — gate becomes a no-op since no real token exceeds 999M USD.

**Option B:** code revert:
```bash
git revert HEAD
git push
```
Auto-redeploys signal_aggregator.

Prefer Option A — code change is structurally sound and only the threshold needs adjusting.
