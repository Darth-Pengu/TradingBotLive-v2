# ZMN STATUS — operational journal

> Newest entry at top. Append-only. Never rewrite history.
> Every CC session appends an entry. Upload this to every Claude chat.
>
> See CLAUDE.md § "STATUS.md — single-file state tracker" for the convention.

---

## 2026-04-23 13:02 UTC — BITFOOT-2026-BASELINE (verdict BASELINE-A, caveats)

**Committed (this session):** `<hash>` research(bitfoot): 2026 baseline vs 2025 edge — verdict BASELINE-A. Touches `docs/audits/BITFOOT_2026_BASELINE_2026_04_23.md` (new, committed) + STATUS.md + ZMN_ROADMAP.md. Also local-only under `.tmp_bitfoot2026/`: `sample_2026.py`, `bitfoot2026_sample.csv`, `run_stdout.log` (gitignored dir). No services/, no env vars, no Redis, no Railway deploys.

**State changes:** none (read-only external APIs — GT Demo tier `x-cg-demo-api-key` + Vybe free tier `X-API-KEY`). 0 credits spent. Analyst remains disabled via 08:19 UTC Redis override (will need re-apply before ~12:19 UTC expiration — now ~1h past, governance may have clobbered it; separate check recommended).

**Bot state:** TEST_MODE=true (carried; not re-read this session). Paper position count not re-read. Same as 09:12 UTC entry.

**Blockers cleared:** none strictly — this session is design-input for ANALYST-POST-GRAD-001, doesn't clear a named blocker. Provides concrete 2026 calibration guidance for that work item's upcoming design session.

**Blockers new/active:**
  - **BITFOOT-2026-BASELINE survivorship caveat (NEW)** — hit rates from this session's trending_pools sample (88.9% 2x+, 0% rug on n=18) are bias-inflated. Real-world forward hit rate lies between the dip-sample's 20.5% (biased low) and this session's 88.9% (biased high). Point estimate cannot be derived from either. Forward ROI must be calibrated via live paper observation (BITFOOT-MONITOR-001), not retrospective math.
  - **CLAUDE.md Vybe URL inverted (NEW)** — `CLAUDE.md` line under "Vybe Network MCP" says `API base: https://api.vybenetwork.com (NOT .xyz)`. This is **backwards** — every endpoint on `.com` returns 404; `.xyz` works. Verified on `/v4/tokens/{mint}/top-holders`. Needs a CLAUDE.md fix in a follow-up session.
  - **Raydium post-grad absent in 2026 trending (STRUCTURAL finding)** — 0 of 42 phase-1 candidates on Raydium; 2025 dataset had 39% Raydium. Pump.fun graduations now route pumpswap-first, meteora-second in 2026. Not a blocker, but ANALYST-POST-GRAD-001 execution planning must account for this (and for Meteora's larger winner share — 44% of 2-filter matches vs 10% of 2025 dataset).
  - **ANALYST-DISABLE-HALFLIFE (CARRY from 08:19 UTC)** — governance re-apply needed every ≤4h. Override was set at 08:19 UTC, now ~5h past; likely clobbered. Re-apply should run before next Analyst-related session. (No new action this session.)
  - All other carry blockers unchanged (HOLDER-DATA-PIPELINE verification window, corrected_pnl_sol NULL, SocialData outage auto-topup).

**Next prompt:** SESSION_ANALYST_POST_GRAD_001_PLAN.md (pending from Jay). Must incorporate BOTH DIP-D verdict (from 09:12 UTC session) AND this session's 2026 baseline findings — specifically: (a) drop `dex_paid` rule (untestable on current stack); (b) drop pre-grad `vol/MC < 1.5` gate (un-replicable without pre-grad visibility); (c) expect Meteora to be a meaningful fraction of entries; (d) ROI estimate is un-pinned and must come from paper window.

**Pending Claude-chat prompts not yet pasted:**
  - SESSION_ANALYST_POST_GRAD_001_PLAN.md — now blocked on Jay pasting; should be ready given both prerequisite sessions (dip-sample + 2026-baseline) are complete.

**Verdict:** **BASELINE-A (directionally)** — 2-filter Bitfoot still concentrates winners in 2026 trending post-grad data (16 of 18 hit 2x+). Absolute hit rates inflated by trending_pools survivorship. Design proceeds with revisions.

---

## 2026-04-23 09:12 UTC — BITFOOT-DIP-SAMPLE-001-RETRY (verdict DIP-D)

**Committed (this session):** docs-only — `session_outputs/bitfoot_analysis/BITFOOT_DIP_SAMPLE_DONE.md` + `fetch_dip_peaks.py` (auth header + 180d pre-filter + 401 escalation) + `analyze_dip_results.py` + `bitfoot_dip_results.csv` (99 rows, 39 with data) + `bitfoot_dip_progress.log` + STATUS.md + ZMN_ROADMAP.md. No services/, no env vars, no Redis writes, no Railway deploys.

**State changes:** none (read-only external API — authenticated GeckoTerminal Demo tier, zero credits). ANALYST-DISABLE Redis override from 08:19 UTC entry is still active (TTL expires ~12:19 UTC) — not touched this session.

**Bot state:** TEST_MODE=true (carried from 08:19 UTC; not re-read this session). Paper position count not re-read. Analyst remains disabled via Redis override.

**Blockers cleared:**
  - **BITFOOT-DIP-SAMPLE-001** — verdict **DIP-D**: 8 of 39 retrievable-data rows (20.5%) hit 2x+ post-ping, 4× above the 5% DIP-D threshold. Bitfoot's "unflagged" label is NOT reliable ground-truth for non-winners. Zero losses observed in 39 data rows is almost certainly survivorship bias in the retrievable subset, not signal — 55 of 100 sample rows were unreachable on Demo tier (180-day data retention cap), and GT's pool index curation filters out delisted pools before we see them. Full analysis at `session_outputs/bitfoot_analysis/BITFOOT_DIP_SAMPLE_DONE.md`.

**Blockers new/active:**
  - **ANALYST-POST-GRAD-001 REFRAME (NEW)** — strategy design cannot condition on Bitfoot label output (flagged/unflagged) as an entry filter. Three feature filters (top-10 ≥30% / vol-MC <1.5 / Dex Paid=🔴) remain candidate gates but must be validated prospectively via paper observation, not retroactively against Bitfoot flags. ROI estimate is currently un-pinned and must come from paper window, not historical Bitfoot math. Next design session prompt should incorporate this into §2 (design assumptions) + §6 (ROI framing).
  - **BITFOOT-DIP-SAMPLE-001 bias caveat (carry for future re-derivation)** — zero-losses finding is survivorship bias. If calibrated ROI is required before ANALYST-POST-GRAD-001 goes live, options are (a) CoinGecko Analyst tier subscription (~$150/mo) to recover the 55 unreachable rows, or (b) a second data source (Birdeye with credits; Helius on-chain reconstruction) to capture delisted pools. Neither fit this session's zero-credit scope.
  - **ANALYST-DISABLE-HALFLIFE (CARRY from 08:19 UTC)** — governance service will clobber the Redis override on next write; re-apply every ≤4 hours until proper fix lands.
  - **HOLDER-DATA-PIPELINE verification window (CARRY)** — still in progress (ends ~2026-04-23 23:00 UTC).
  - **corrected_pnl_sol NULL on post-reset rows (CARRY)** — CLEAN-004 correction job not re-wired.

**Next prompt:** SESSION_ANALYST_POST_GRAD_001_PLAN.md (Jay to paste when ready; must incorporate DIP-D verdict into design-assumptions + ROI framing).

**Pending Claude-chat prompts not yet pasted (in `/mnt/user-data/outputs/`; paste-status unknown to CC):**
  - SESSION_ANALYST_POST_GRAD_001_PLAN.md (drafting per prior session's forward pointer; must incorporate DIP-D)

**Verdict:** **DIP-D** — Bitfoot's unflagged label is not reliable ground-truth; 20.5% of unflagged retrievable pings actually hit 2x+.

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
