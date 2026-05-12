# NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001 — paste-ready deploy prompt

**Type:** Single env-var change on `bot_core`. No code change.
**Wall-clock budget:** ~20 min (env set → 1 redeploy → verify clean startup → verify no winner FP in first hour).
**Rollback:** Instant — set env back to `3000`. No code revert.
**Source:** `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md`.

---

## Scope

Tighten `BOT_CORE_FILL_MC_CEILING_USD` on `bot_core` Railway service from `3000` to `1000`. This is a **retune of the same env var** as STOP-LOSS-20-RUG-FILTER-DEPLOY-001 (deployed 2026-05-11 12:30 UTC, observation period to 2026-05-25). The deploy advances the eval window because the data shows the next loss tier ($1k–$3k MC) is the immediate bleed.

## Pre-deploy gates (any fail → STOP and report)

1. **Read** `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` and `.tmp_no_momentum_90s/T0_BASELINE.json`.
2. **STOP-A retest** — re-run `.tmp_no_momentum_90s/verify_intervention.py` against fresh data; confirm C1 W3+W4 ROI ≥ +1.0 SOL/d AND `false positives (winners blocked) = 0`. If FP > 0 (a new trail_win at MC > $1000 has landed since 2026-05-12), STOP.
3. **STOP-B no-behavioural-change** — `git log services/paper_trader.py services/bot_core.py | head -3` shows last touch ≤ `0f37e82` (STOP-LOSS-20-RUG-FILTER-DEPLOY). If a new commit changed the fill path, re-run audit first.
4. **STOP-C scope-collision** — no other concurrent session is deploying to `bot_core` (`STATUS.md` newest entry shows no in-flight deploy).
5. **Jay authorization in session prompt.** This is an early-eval retune; Jay must explicitly name `BOT_CORE_FILL_MC_CEILING_USD` and request the threshold change. Generic "tighten the filter" is NOT sufficient.

## Deploy step

Single command via Railway MCP or CLI:

```
railway variables --set "BOT_CORE_FILL_MC_CEILING_USD=1000" -s bot_core
```

Triggers one auto-redeploy. No code push, no `railway up`. Wait ≈90s for container to start.

## Post-deploy verification (T+2 min, T+30 min, T+24h)

**T+2 min:**

- Container start clean: `Starting SINGLE service: bot_core` → `Startup reconciliation: N open positions in DB` → `Listening for emergency alerts`. No RuntimeError, no import error.
- Redis counter `bot:filter:fill_mc_ceiling:rejects:<date>` should start incrementing within a few minutes (W4 rate was ~209 rejections/day at $1000 = 1 every ~7 min).
- No `EMERGENCY_STOP` set.

**T+30 min:**

- Check trade flow rate. Pre-deploy W4 rate was ~12/h; post-deploy expected ~3/h (only $0–$1k MC tokens get through). If 0 trades in 30 min, investigate signal pipeline (don't auto-rollback yet).
- Spot-check first 3 entered trades: all should have `market_cap_at_entry ≤ 1000`.
- Spot-check 3 rejected mints from Redis counter (if logged): all should have entry-price-derived MC > $1000.

**T+24h:**

- Query `paper_trades` SD-paper since deploy: WR target ≥ 60% (vs W4 14.4%), nm90_rate target ≤ 30% (vs 76.5%), sum_pnl target ≥ +0.5 SOL.
- If WR < 30% or sum_pnl ≤ −0.5 SOL → rollback (regime not what audit predicted).
- If trade flow < 50 trades/24h → consider intermediate ceiling C2 ($1500) to restore volume.

## Rollback triggers

ANY of these within the first 24h → revert `BOT_CORE_FILL_MC_CEILING_USD=3000` immediately (single env command, no code revert):

1. Bot_core fails to start (RuntimeError, import error).
2. SD-paper trade rate < 1/h for 2 consecutive hours.
3. **A TRAILING_STOP winner with `realised_pnl_sol > 0.10 SOL` gets blocked** by the new ceiling (this would be a regime-shift FP not seen in W3+W4).
4. Sum_pnl on kept slice ≤ −0.5 SOL within first 24h (audit's lower bound implied +0.5 SOL/d gain, so net negative would indicate regime divergence).
5. `bot:emergency_stop` set, or `consecutive_losses` increment by ≥ +5 within 24h.

## Doc updates required (same commit)

1. `AGENT_CONTEXT.md` — §2 `bot_core` table: update `BOT_CORE_FILL_MC_CEILING_USD` from 3000 → 1000 with deploy timestamp. §6.5 `no_momentum_90s` row: update status to MITIGATED with deploy ref.
2. `ZMN_ROADMAP.md` Decision Log — new row at top.
3. `STATUS.md` — prepend deploy entry per CLAUDE.md template.
4. `MONITORING_LOG.md` — entry.
5. Update STOP-LOSS-20-RUG-FILTER-EVAL-001 in `ZMN_ROADMAP.md`: eval queue date pushed to ≥2026-05-26 (or +14d from this deploy, whichever later).

## Single push, no `railway up`

Per CLAUDE.md deploy discipline. `git push` only after env set + 90s redeploy confirms clean startup. Use `git commit --amend` to backfill commit hash into STATUS.md before pushing.
