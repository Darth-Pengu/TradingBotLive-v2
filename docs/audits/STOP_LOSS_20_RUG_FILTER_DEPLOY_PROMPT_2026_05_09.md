# SESSION: STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (paste-ready)

**Predecessor:** `STOP-LOSS-20-RUG-INVESTIGATION-001` (audit doc:
`docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md`).
Paste this entire prompt into a NEW Claude Code session after the
investigation has been pushed and pulled.

**Type:** Single-lever code change + Railway env set + redeploy. Bounded and
reversible. Estimated wall clock: 30-45 min.

**Date authored:** 2026-05-09
**Goal:** Deploy filter F1 — fill-time MC ceiling — at default `$3,000` on
bot_core. Default OFF in code; env-active on the deployed service.

---

## §0 PRECEDENCE — read first

1. Read `CLAUDE.md`, `AGENT_CONTEXT.md`, `STATUS.md`, `MONITORING_LOG.md`,
   `docs/audits/STOP_LOSS_20_RUG_INVESTIGATION_001_2026_05_09.md`.
2. If `AGENT_CONTEXT.md` shows another behavioural deploy in flight (concurrent
   session), STOP and write `.tmp_stop_loss_20_rug_deploy/STATE_CONFLICT.md`.
3. The deploy is **paper-only at flip** (TEST_MODE=true unchanged). No live
   wallet exposure.

---

## §1 STOP gates (fail open, return docs-only commit, exit)

- **STOP-A — Predecessor doc absent / outdated.** If the investigation doc
  doesn't exist or is older than 14d, STOP. (At 14d, re-run the investigation
  with fresh data.)
- **STOP-B — Investigation findings stale.** If `git log` shows a behavioural
  change to `services/paper_trader.py:paper_buy` or `services/bot_core.py`
  since the investigation commit (the audit references HEAD `<this-commit>`),
  STOP and re-validate.
- **STOP-C — Sample size collapsed.** Re-run the verify_filter on current data;
  if 7d ROI < +0.50 SOL/day, STOP and request re-investigation.
- **STOP-D — Concurrent deploy.** Another session is mid-deploy. Defer.

A STOP closes cleanly with audit doc explaining why; no code change.

---

## §2 Code change — `services/paper_trader.py:paper_buy`

After `entry_price = price * (1 + slippage / 100)` (currently line 245), before
the INSERT (currently line 260), insert this block. Use **Edit tool**, not
search-and-replace, and preserve exact indentation.

```python
    # F1 — Fill-time MC ceiling (STOP-LOSS-20-RUG-FILTER-DEPLOY-001).
    # Default disabled (env=0). When set, rejects trades whose entry price
    # implies MC > threshold — catches the SA SD_MC_CEILING_002 fail-open
    # mode where signal-time BC reserves report < threshold but bot_core
    # fills at a Jupiter/Gecko-derived price reflecting in-flight pumps.
    # Rollback: set BOT_CORE_FILL_MC_CEILING_USD=0 (no redeploy).
    fill_mc_ceiling = float(os.getenv("BOT_CORE_FILL_MC_CEILING_USD", "0"))
    if fill_mc_ceiling > 0:
        fill_mc = entry_price * 1_000_000_000  # mirrors line 257 supply
        if fill_mc > fill_mc_ceiling:
            logger.info(
                "FILL_MC_CEILING reject: %s mc=$%.0f > ceiling=$%.0f "
                "(slippage_tier=%s, slippage=%.1f%%)",
                mint[:12], fill_mc, fill_mc_ceiling, slippage_tier, slippage,
            )
            # Increment Redis counter for observability
            if redis_conn is not None:
                try:
                    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    await redis_conn.incr(f"bot:filter:fill_mc_ceiling:rejects:{today}")
                    await redis_conn.expire(f"bot:filter:fill_mc_ceiling:rejects:{today}", 86400 * 14)
                except Exception:
                    pass
            return {
                "success": False,
                "error": "fill_mc_ceiling_exceeded",
                "simulated": True,
                "fill_mc": fill_mc,
                "ceiling": fill_mc_ceiling,
            }
```

**Mirror the same gate inside the live-mode branch of `paper_buy`** if/when
called from a live path. (Currently `paper_buy` is only called from the
TEST_MODE=true path of `bot_core.process_signal`; live mode uses
`services/execution.py`. F1 is paper-scoped at this deploy.)

**Compile-check:** `python -m py_compile services/paper_trader.py` must pass.

---

## §3 Verification harness

In the same commit, add `.tmp_stop_loss_20_rug_deploy/post_deploy_verify.py`
that:

1. Reads `BOT_CORE_FILL_MC_CEILING_USD` from Railway env on bot_core (via
   Railway MCP).
2. Reads `bot:filter:fill_mc_ceiling:rejects:<today>` Redis counter (via Redis
   MCP).
3. Reads count of new SD-paper trades in last 1h post-redeploy and verifies
   none have `market_cap_at_entry > 3000`.
4. Outputs PASS/FAIL.

Run the harness ~10 minutes after redeploy completes. Save output to
`.tmp_stop_loss_20_rug_deploy/post_deploy_check.txt`.

---

## §4 Railway env + deploy steps

```bash
# 1. Commit code change.
git add services/paper_trader.py docs/audits/STOP_LOSS_20_RUG_FILTER_DEPLOY_PROMPT_2026_05_09.md
# also include the canonical-doc updates per §6
git commit -m "feat(filter): F1 fill-time MC ceiling (default disabled, env-controlled)"

# 2. Push (auto-deploys on Railway via webhook). NO `railway up`.
git pull --rebase origin main
git push origin main

# 3. Wait for bot_core deploy to land + container start (~3-4 min).
# Use Railway MCP `check-railway-status` until SUCCESS, then sleep ~90s.

# 4. Set env on bot_core ONLY.
railway variables --set "BOT_CORE_FILL_MC_CEILING_USD=3000" -s bot_core
# This triggers ANOTHER auto-redeploy. Wait for SUCCESS + ~90s.

# 5. Run post-deploy verification harness.
python .tmp_stop_loss_20_rug_deploy/post_deploy_verify.py
```

**DO NOT** set the env on signal_aggregator, web, ml_engine, or any other
service. F1 is a bot_core-only filter (paper_trader.paper_buy is only invoked
from bot_core.process_signal).

**Rollback:** `railway variables --set "BOT_CORE_FILL_MC_CEILING_USD=0" -s bot_core`
— takes effect on next paper_buy call (~few seconds), no redeploy required.

---

## §5 Rollback triggers (any one ends deploy early)

- Bot_core fails to start with the new code (RuntimeError at import).
- New SD-paper trade rate drops below 50% of pre-deploy rate within 30 min
  (suggests gate is over-rejecting).
- Any `staged_tp_+1000%` or `TRAILING_STOP` winner with realised_pnl_sol > 0.5
  SOL gets blocked in first 24h (would be a ~5% winner FP — unexpected given
  0% on 17d historical).
- `bot:emergency_stop` set OR consecutive_losses crosses 5 within 24h.

Rollback procedure: env to 0; document outcome in MONITORING_LOG.

---

## §6 Canonical doc updates (in same commit)

- `STATUS.md` (prepend new entry: deploy + verify outcome)
- `ZMN_ROADMAP.md` (Decision Log entry; status FILTER-F1-DEPLOYED)
- `AGENT_CONTEXT.md` (§2 bot_core block: add `BOT_CORE_FILL_MC_CEILING_USD=3000`
  row; §6.5 leaks: update `stop_loss_20%` row to ⏸ MITIGATED via F1)
- `MONITORING_LOG.md` (deploy event + observed Redis counter at +1h, +24h)

---

## §7 Re-evaluation milestone (queue for ≥2026-05-23)

Run `STOP-LOSS-20-RUG-FILTER-EVAL-001` at +14d post-deploy:
- Verify cumulative `fill_mc_ceiling:rejects` counter matches expected ~25/day rate.
- Re-run `verify_filter.py` with corrected `kept_pnl` against actual paper_trades — confirm forward ROI tracks the +0.80-0.93 SOL/day projection.
- Decide: keep at $3k / tighten to $2k / loosen to $5k.
- Decide: enable in live-mode branch of `services/execution.py` (subject to
  V5a-go-no-go preconditions).

---

## §8 Closing

Verdict possibilities:

- **DEPLOYED-VERIFIED:** code lands, env set, Redis counter > 0 within 24h,
  no rollback triggers fired. STATUS marked DEPLOY-COMPLETE.
- **STOP-PRE-DEPLOY:** investigation findings stale or sample collapsed; no
  code change.
- **DEPLOYED-ROLLED-BACK:** code lands but rollback trigger fires; env set to
  0; MONITORING_LOG records the trigger.

Single push, no `railway up`. Per RAILWAY-REDEPLOY-DISCIPLINE-001: docs
commits may trigger Railway redeploys; accept this. The CC session that runs
this should NOT also run any other session in parallel.
