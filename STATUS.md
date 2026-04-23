# ZMN STATUS — operational journal

> Newest entry at top. Append-only. Never rewrite history.
> Every CC session appends an entry. Upload this to every Claude chat.
>
> See CLAUDE.md § "STATUS.md — single-file state tracker" for the convention.

---

## 2026-04-23 08:19 UTC — ANALYST-DISABLE (Redis-override stopgap)

**Committed (this session):** docs-only — STATUS.md entry + `session_outputs/ZMN_ANALYST_DISABLE_DONE.md`. No code, no Railway deploy.

**State changes:**
  - Redis `governance:latest_decision` — JSON field `analyst_enabled: true → false`, all other fields preserved; `override_source: ANALYST-DISABLE-2026-04-23` added. TTL 86400s.
  - No env vars touched. No service redeployed. `ANALYST_DISABLED=true` was already set on signal_aggregator (and effective for the normal signal path — the leak is the graduation sniper, which bypasses that gate).

**Bot state:** TEST_MODE=true, 1 paper open (`6aRVmWde98RZ`, analyst, pre-override entry — will exit via existing bot_core logic), 0 live open, consecutive_losses=0. Paper portfolio 21.054 SOL (pre-session).
  - Personalities active: **speed_demon** (analyst gated at bot_core:612 via governance override as of 08:11 UTC).

**Recent trade activity (window: last 10 min since override):**
  - analyst: 0 new entries (prior cadence ~2.5/hr from graduation sniper) — early but consistent with gate working.
  - speed_demon: 0 new entries (signal quality gates binding — unrelated to this session).

**Blockers cleared:**
  - **ANALYST-PNL-INVESTIGATION** — root cause identified and mitigated. The leak path was `_process_graduations` at `services/signal_aggregator.py:2418-2538`, which hardcodes `"personality": "analyst"` at line 2521 and pushes to `signals:scored` without checking `ANALYST_DISABLED`. bot_core's only gate for the graduation-sniper analyst was `gov.get("analyst_enabled", True)` at `services/bot_core.py:612`. Governance service is dead (Anthropic credits exhausted), so the Redis key `governance:latest_decision` had `analyst_enabled: true` by default. Redis override now forces False until governance's next write overwrites it.

**Blockers new/active:**
  - **ANALYST-DISABLE-HALFLIFE (NEW)** — governance service writes `governance:latest_decision` with `ex=28800` (8h) and re-runs every `next_review_hours=4`. When it next runs (even in its LLM-failed fallback branch at `services/governance.py:346`), it will SET the key to `GOVERNANCE_DEFAULTS` which has `analyst_enabled: True`, clobbering this override. **Re-apply the override every ≤4 hours until a proper fix lands.** Proper fix options: (a) add `if ANALYST_DISABLED: continue` at `services/signal_aggregator.py:2428` (after `brpop`); (b) flip `GOVERNANCE_DEFAULTS["analyst_enabled"] = False` in `services/governance.py`; (c) add a new Redis key `bot:personality:analyst:force_disable` and a bot_core check. Scope for follow-up session.
  - HOLDER-DATA-PIPELINE verification window still in progress (ends ~2026-04-23 23:00 UTC).
  - `corrected_pnl_sol` NULL on all post-reset rows (CLEAN-004 correction job not re-wired).
  - `market:mode:override` + `nansen:disabled` TTLs had dropped to <15 min at session start — also need daily renewal.

**Next prompt:** (Jay to decide) — candidates: ANALYST-POST-GRAD-001 design (Bitfoot-inspired rewrite) OR proper code-level fix for the halflife (~10-15m).

**Pending Claude-chat prompts not yet pasted (on Jay's machine in `/mnt/user-data/outputs/`; paste-status unknown to CC):**
  - `SESSION_BITFOOT_DIP_SAMPLE.md` (Bitfoot 71% unflagged question — still queued)
  - `SESSION_ANALYST_POST_GRAD_001_PLAN.md` (Bitfoot-inspired rewrite — being drafted per ANALYST-DISABLE prompt's forward pointer)

---

## 2026-04-23 08:01 UTC — STATUS-CONVENTION-001 (seed first entry)

**Committed (this session):** docs-only — CLAUDE.md "STATUS.md — single-file state tracker" section + STATUS.md + STATUS.md.template. Hash recorded in next session's opening state-read.

**State changes:** none. No env vars, no Redis writes, no deploys. State read-only via Railway / Redis / Postgres.

**Bot state:** TEST_MODE=true (paper), 0 paper open, 0 live open, consecutive_losses=0, emergency_stop=None, paper portfolio=21.054 SOL (Redis), SOL=$85.92.
  - Redis `market:mode:override=NORMAL` TTL 817s (⚠ ~13min — due for daily renewal)
  - Redis `nansen:disabled=true` TTL 817s (⚠ ~13min — due for daily renewal)
  - Railway: `HOLDER_COUNT_MIN=1`, `ML_THRESHOLD_SPEED_DEMON=65`, `PRE_FILTER_SCORE_MIN=1.15`, `BUY_SELL_RATIO_MIN=3.0` (signal_aggregator)

**Recent trade activity (last 24h, paper only; entry_time window):**
  - speed_demon: 150 trades closed, +2.517 SOL, 52.00% WR
  - analyst: 59 trades closed, **-2.478 SOL, 11.86% WR**
  - net: +0.039 SOL across 209 closes
  - Latest entry: ~18 min ago; latest exit: ~2026-04-23 07:53 UTC — pipeline alive.

**Blockers cleared:** none this session.

**Blockers new/active:**
  - **ANALYST-PNL-INVESTIGATION (NEW)** — Analyst personality is executing in paper despite CLAUDE.md / ZMN_ROADMAP.md stating `ANALYST_DISABLED=true` and "hard-disabled". 59 trades / -2.48 SOL / 11.86% WR over last 24h. Either the env flag isn't wired into the path that gates analyst entries, or the flag is unset on the actual running service. Decide: pause, tune, or observe-window.
  - **HOLDER-DATA-PIPELINE-001 (CARRY)** — ZMN_ROADMAP.md marks this ✅ FIXED in `fc87b03` + `4c5508b`, but prior session flag said Speed Demon `holder_count=0` on 100% of pipeline reads was still open as of 2026-04-22. Verify post-fix cadence in 24h observation window (ends ~2026-04-23 ~23:00 UTC).
  - **corrected_pnl_sol NULL on all 215 fresh rows (CARRY from CLEAN-004 reset)** — correction-method job appears not to have run since post-reset rows started landing. CLAUDE.md "Trade P/L Analysis Rule" says use `corrected_pnl_sol`; presently only `realised_pnl_sol` is populated on post-reset rows. Does not block trading; does dirty every downstream P/L query unless callers coalesce.

**Next prompt:** none queued (Jay decides based on chat discussion of the two active blockers).

**Pending Claude-chat prompts not yet pasted (on Jay's machine in `/mnt/user-data/outputs/` — CC cannot inspect that path; list reflects Jay's prior chat messaging; paste-status unknown, Jay to confirm):**
  - `SESSION_BITFOOT_DIP_SAMPLE.md` (resolves Bitfoot 71% unflagged-pings question)
  - `SESSION_ROADMAP_CONSOL_2026_04_22.md` (absorb 2026-04-22 findings into roadmap)
  - `SESSION_HOLDER_DISABLE.md` (paste-status unknown — Jay to confirm)
  - `SESSION_HOLDER_DATA_AUDIT.md` (paste-status unknown — Jay to confirm)

---
