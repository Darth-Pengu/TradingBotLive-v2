# ANALYST-DISABLE-002 — Code-level fix for the graduation-sniper bypass

**Date:** 2026-04-28
**Commit:** `9d6e95c` (signal_aggregator)
**Companion runtime action:** governance:latest_decision Redis override re-applied (band-aid, analyst_enabled=false, TTL=86400s, override_source=ANALYST-DISABLE-REAPPLY-2026-04-28)
**Closes:** ANALYST-DISABLE-001 halflife concern (tracked as resolved when this fix is verified live)

---

## §1 Problem statement

The pre-existing `analyst` personality leaked paper trades from **2026-04-22 14:11 UTC through 2026-04-25 21:47 UTC** despite a 2026-04-23 ANALYST-DISABLE session that landed:
- Env: `ANALYST_DISABLED=true` on `signal_aggregator` (was already there, confirmed 2026-04-28)
- Redis: `governance:latest_decision.analyst_enabled = false` (TTL 86400s)

**Quantified damage** (from `session_outputs/paper_trades_export_2026_04_28.csv`):

| Window | Analyst trades | PnL | WR |
|---|---:|---:|---:|
| Pre-disable (≤2026-04-23 08:19 UTC) | 60 | (in original -2.48 SOL figure) | 11.9% |
| **Post-disable → 2026-04-25 21:47 UTC** | **241** | **−12.502 SOL** | 17.0% |
| **Total Analyst** | **301** | **−15.034 SOL** | 15.9% |

For comparison, Speed Demon over the same window: 534 trades, **+6.064 SOL**, 44.6% WR.

The leak reactivated **6 minutes after the first Redis override was applied** (first post-disable analyst entry at 08:24:45 UTC) and ran continuously for ~2.5 days unsupervised.

## §2 Root-cause diagnosis

The leak path was **`_process_graduations`** at `services/signal_aggregator.py:2421-2542`. This function:
1. Reads from `signals:graduated` Redis queue
2. Fetches enrichment (Rugcheck, GeckoTerminal holders, Vybe KOL labels, ML score via pubsub)
3. **Hardcodes** `"personality": "analyst"` at line 2521
4. Pushes the signal to `signals:scored` at line 2534

It **never** read the module-level `ANALYST_DISABLED` constant (defined at line 145, enforced at line 1810 for the main signal path).

The downstream gate in bot_core (`services/bot_core.py:612`) does check `gov.get("analyst_enabled", True)`, but this defaults to `True` when governance state is unavailable. Because:
- The governance service has been failing on Anthropic creds-out (`bot:status` reasoning field shows `"classification failed: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your cred...'}"`)
- Governance falls back to `GOVERNANCE_DEFAULTS` (`services/governance.py:331-340`), which has `analyst_enabled: True`
- Governance writes `governance:latest_decision` every `next_review_hours=4` with `ex=28800` (8h TTL)

Net effect of the halflife: every Redis-only override survives ≤4h before the next governance write clobbers it back to `analyst_enabled: True`. Without an env-var or constant code path enforcing the disable, the leak is destined to resume.

## §3 Fix (commit `9d6e95c`)

Extend the existing `ANALYST_DISABLED` env-var pattern (line 1810 prior art) to the graduation sniper. Drain the queue silently when disabled — function stays alive so re-enable via env + container restart resumes processing immediately.

```python
async def _process_graduations(redis_conn: aioredis.Redis, pool=None):
    # ... docstring with full ANALYST-DISABLE-002 rationale ...
    logger.info("Graduation sniper processor started (ANALYST_DISABLED=%s)", ANALYST_DISABLED)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                result = await redis_conn.brpop("signals:graduated", timeout=5)
                if not result:
                    continue
                if ANALYST_DISABLED:
                    continue  # ANALYST-DISABLE-002 (2026-04-28): drain silently
                _, raw = result
                # ... rest unchanged ...
```

Two checks now defend against analyst leaks:
- **Env-var (deterministic):** signal_aggregator.py:1810 (main path) + 2443 (graduation path, NEW)
- **Governance (dynamic):** bot_core.py:612 — still defaults to `True` if governance is unavailable; not strengthened in this fix

The env-var gate is now the durable enforcer; the governance gate remains as a soft toggle for online flipping when governance is healthy.

## §4 Why we didn't strengthen bot_core.py:612

`bot_core.py:612` reads `gov.get("analyst_enabled", True)` — a fail-open default. Changing the default to `False` (fail-closed) would make Speed Demon and Whale Tracker also subject to the same flip if governance goes unavailable, which is too broad a blast radius for a session scoped to fixing the analyst leak.

A future hardening session could:
- Replace the per-personality bool fallback with a per-personality env-var equivalent of `ANALYST_DISABLED` (i.e. `SPEED_DEMON_DISABLED`, `WHALE_TRACKER_DISABLED`)
- Or move the personality enable map into env vars only, dropping the governance dimension for this knob

Tracked separately as a future hardening item; out of scope for ANALYST-DISABLE-002.

## §5 Verification plan

1. **Deploy:** Railway auto-deploys signal_aggregator on push of `9d6e95c`. Expected ~2–3 min.
2. **Startup-log check:** new container logs `Graduation sniper processor started (ANALYST_DISABLED=True)` at boot. Confirms the gate is live and seeing the env var.
3. **Behavior check:** zero `GRAD_ACCEPT` / `GRAD_REJECT` lines in subsequent logs (function silently drains). The pre-fix pattern was occasional `GRAD_ACCEPT: <mint> score=70 holders=N` lines.
4. **Trade-side check (deferred):** zero new `personality=analyst` rows in `paper_trades`. Cannot be measured cleanly during the current bot silence (bot_core is EMERGENCY_STOPPED — see §6) — re-verify during the first 30 min after silence-recovery executes.

## §6 Bot silence diagnosis (separate root cause, escalated)

**The bot has been emergency-stopped for 67h** as of 2026-04-28 12:50 UTC. This is **separate** from the analyst leak (which the code fix above addresses) but **caused by it**.

### §6.1 Trigger sequence

```
2026-04-25 21:52:50 UTC: risk_manager CRITICAL EMERGENCY_STOP:
                         "Daily loss limit: -4.05 SOL"
2026-04-25 21:52:50 UTC: bot_core CRITICAL EMERGENCY STOP:
                         "Risk limits breached"
```

The trigger was the daily-loss limit (`DAILY_LOSS_LIMIT_SOL=4.0`) being exceeded by the analyst leak's accumulated daily losses. This was a correctly-firing safety rail, NOT a bug. The fix here addresses the upstream cause (analyst leak) so the rail won't trip again from this source.

### §6.2 Current state (Redis snapshot 2026-04-28 12:50 UTC)

| Key | Value | Notes |
|---|---|---|
| `bot:status` | `{"status": "EMERGENCY_STOPPED", "consecutive_losses": 7, "portfolio_balance": 24.33, "open_positions": 0, ...}` | TTL=28s — bot_core IS heartbeating still, just stuck in emergency state |
| `bot:consecutive_losses` | `7` | TTL=-1 (persistent), exceeds the 5+ trigger |
| `market:mode:current` | `HIBERNATE` | TTL=-1 — set by market_health |
| `market:mode:override` | (NOT SET) | 24h TTL has expired; market_health auto-tripped to HIBERNATE |
| `signals:scored` | 337 entries | bot_core has not consumed since 2026-04-25 |
| `paper:positions:*` | 0 keys | clean (no zombie positions) |
| `bot:open_positions:*` | 0 keys | clean |
| `bot:emergency_stop` | (NOT SET) | per CLAUDE.md, in-memory only — restart clears this |
| `bot:loss_pause_until` | (NOT SET) | clean |
| `signal_aggregator:health` | TTL 104s, status ok | signal_aggregator is healthy (still producing signals) |
| `bot_core:health` | (NOT SET) | bot_core is not writing this key (no equivalent heartbeat) |

### §6.3 Recovery recipe (NOT executed this session — escalated)

Per CLAUDE.md "Emergency Stop Reset" + adapted to current state:

```bash
# 1) Reset the loss counter
redis-cli SET bot:consecutive_losses 0
redis-cli DEL bot:emergency_stop      # not set anyway, defensive
redis-cli DEL bot:loss_pause_until    # not set anyway, defensive

# 2) Renew the market-mode override (auto-renewal lapsed)
redis-cli SET market:mode:override NORMAL EX 86400

# 3) Drain the stale signals queue (337 entries piled up over 67h —
#    re-running them risks bot_core opening positions on stale prices)
redis-cli DEL signals:scored

# 4) Restart bot_core to clear in-memory `self.emergency_stopped`
#    (CLAUDE.md notes the rug-cascade emergency stop is in-memory only)
railway up -s bot_core
# OR alternative: trigger a redeploy via env-var no-op:
# railway variables --set "RECOVERY_RESTART_TS=$(date +%s)" -s bot_core
```

### §6.4 Why escalated rather than executed inline

The session prompt's STOP rule:
> "If silence has a complex cause (data pipeline broken, ML model errored, multiple services degraded) STOP, document, escalate to me."

This silence has **three parallel state issues** (consecutive_losses, market:mode:override, signals:scored backlog). Each is individually documented in CLAUDE.md as a known recipe, but the **combination** is more than a single env flag. Particular concerns:

- The 337-entry queue has stale prices from up to 67h ago. Replaying them post-restart risks bot_core opening positions on tokens that have already pumped/dumped. Draining first is safer.
- `consecutive_losses=7` is high enough that even ONE additional bad trade post-recovery could re-trip the breaker before any winners can offset.
- Restarting bot_core mid-session needs Jay's explicit go-ahead (live infrastructure, hard-to-reverse if it misbehaves).

### §6.5 Verification post-recovery (for the next session)

After the recipe lands:
1. Confirm `bot:consecutive_losses=0` in Redis
2. Confirm `market:mode:override=NORMAL` with TTL ~86400
3. Confirm `signals:scored` is being drained (depth shrinks back toward 0)
4. Confirm `bot_core` log shows fresh INFO entries (not stuck in 24h heartbeats)
5. Within 30 min: check `paper_trades` for any new entries — should be Speed Demon only (analyst gated by ANALYST-DISABLE-002), and at the prevailing per-minute rate from signal_aggregator

## §7 Tracking

- **ANALYST-DISABLE-001** (✅ COMPLETED 2026-04-23, `cc8e5c9`) — band-aid Redis override; halflife caveat realized in this session as predicted.
- **ANALYST-DISABLE-002** (✅ COMPLETED 2026-04-28, `9d6e95c`) — this fix; durable code-level gate.
- **SILENCE-RECOVERY-2026-04-28** (📋 NEW — escalated to Jay) — execute the §6.3 recipe to bring the bot back online. Out of scope for this session.
- **GOVERNANCE-RESILIENCE** (📋 NEW — soft) — reduce dependency on Anthropic-creds healthy governance. Either move personality toggles entirely to env, or change the bot_core fallback default from `True` to `False`. Out of scope; deferred.

## §8 Session ledger

- API calls: ~5 Redis ops (band-aid override) + ~150 Railway log lines collected for diagnosis
- Files committed: `services/signal_aggregator.py` (+17/-2 lines)
- Files written (local-only): `.tmp_silence_diag/sigagg_logs.txt`, `.tmp_silence_diag/botcore_logs.txt`, `.tmp_silence_diag/post_fix_logs.txt`
- Audit doc: this file (committed)
- STATUS.md + ZMN_ROADMAP.md updates: pending in same commit batch
