# TIMEZONE-AUDIT-001 — Repository-wide hardcoded-offset sweep (2026-05-05)

> Single-session read-only audit. NO code/config writes. Scope:
> services/, scripts/ + Scripts/, dashboard/, web/, repo root .py/.js/.ts.
> Excluded: .venv/, __pycache__/, node_modules/, .tmp_*/, data/, share/,
> static/, etc/, catboost_info/, repomix-output.xml, Lib/, Include/.

> **Predecessor:** BOT-CORE-ML-GATE-001 (commit `ea0da2f` + docs `77ac459`,
> verdict 🟢 DEPLOYED, env `ML_THRESHOLD_BOT_CORE_SD=40` active 2026-05-05T14:16:48Z UTC).
> **Successor (queued in same CC session):** MARKET-MODE-001-RE-CALIBRATE
> — touches `services/market_health.py`, which this audit confirms is 🟢 SAFE
> (no timezone-fix bundling required).

---

## §1 Executive verdict

**TL;DR (production code only — services/ + dashboard/ + Scripts/):**

- 🔴 BUG: **2** (both in `services/bot_core.py` lines 754, 776 — same root cause)
- 🔵 MARGINAL: **2** (signal_aggregator ML feature `hour_of_day`/`is_weekend` UTC; risk_manager `_time_of_day_multiplier` UTC)
- 🟡 OK-WITH-CAVEAT: **3** (audit-doc display strings; bot_core `_daily_reset` uses UTC midnight; dashboard tile clocks)
- 🟢 SAFE: **20+** (all `datetime.now(timezone.utc)` uses for storage/timestamps; market_health.py SYDNEY_TZ via pytz; governance.py SYDNEY_TZ via pytz; dashboard widgets `Australia/Sydney` JS toLocaleString; dashboard_api.py `AT TIME ZONE 'Australia/Sydney'` SQL — all DST-aware)

**Top 3 most-critical 🔴 (decision-affecting):**

| # | File:line | Symptom |
|---|---|---|
| 1 | `services/bot_core.py:754` | `aedt_hour = datetime.now(timezone(_td(hours=11))).hour` — TIME_GOOD/TIME_DEAD/TIME_SLEEP all fire 1h earlier than labels in Sydney clock (post-DST 2026-04-05) |
| 2 | `services/bot_core.py:776` | `aedt_weekday = datetime.now(timezone(_td(hours=11))).weekday()` — same hardcoded offset; weekend boost rolls 1h earlier than expected (only material around midnight Sydney on Fri/Sun) |
| 3 | (none material in market_health.py / risk_manager.py — see §4) |

**Predecessor verification:** ✅ — audit doc `docs/audits/BOT_CORE_ML_GATE_001_2026_05_05.md` exists, verdict `🟢 DEPLOYED`, env `ML_THRESHOLD_BOT_CORE_SD=40` set on Railway 2026-05-05T14:16:48Z. Proceed.

---

## §2 Predecessor verification (BOT-CORE-ML-GATE-001)

| Item | Value |
|---|---|
| Audit doc | `docs/audits/BOT_CORE_ML_GATE_001_2026_05_05.md` (present) |
| Verdict | `🟢 DEPLOYED — gate active in paper mode` |
| Code commit | `ea0da2f` (deployed Railway bot_core) |
| Env var | `ML_THRESHOLD_BOT_CORE_SD=40` set 2026-05-05T14:16:48Z |
| Verify-script | 8/8 PASS |
| Outstanding follow-up | MARKET-MODE-001-RE-CALIBRATE (next session, queued) |

PASS — proceed with timezone audit.

---

## §3 Sweep table

### A. Hardcoded-offset patterns (Python)

| File:line | Pattern | Code excerpt | Class | Reason |
|---|---|---|---|---|
| `services/bot_core.py:754` | `timezone(_td(hours=11))` | `aedt_hour = datetime.now(timezone(_td(hours=11))).hour` | 🔴 BUG | Decision logic — drives TIME_GOOD/TIME_DEAD/TIME_SLEEP/TIME_PRIME hour-of-day sizing branches. Hardcoded UTC+11 (AEDT) but Sydney is AEST/UTC+10 since 2026-04-06 → all branches fire 1h earlier in Sydney clock. |
| `services/bot_core.py:776` | `timezone(_td(hours=11))` | `aedt_weekday = datetime.now(timezone(_td(hours=11))).weekday()` | 🔴 BUG | Same root cause; weekend boost. Material only at the Sydney-Fri/Sun midnight transition. |
| `Scripts/*` (audit, env_audit, continuous_audit, health_check, paper_summary, rebaseline_paper_edge) | `datetime.now(timezone.utc)` only | various | 🟢 SAFE | All scripts use `timezone.utc` exclusively. 0 hits for `timezone(timedelta(hours=...))`. |
| `services/*` (other than bot_core.py) | none | n/a | 🟢 SAFE | 0 hits for `timezone(timedelta(...))` outside bot_core.py. |

Total prod-code hardcoded-offset hits: **2** (both in bot_core.py, both 🔴).

### B. ISO offset strings (Python/JS/TS)

| File:line | Pattern | Code excerpt | Class | Reason |
|---|---|---|---|---|
| `dashboard/*.html` | none | n/a | 🟢 SAFE | All HTML uses `timeZone:'Australia/Sydney'` (DST-aware), not literal `+10:00` or `+11:00`. |
| `services/*` | none | n/a | 🟢 SAFE | 0 hits for `"+10:00"` or `"+11:00"` literal strings. |
| `session_outputs/ZMN_LIVE_ROLLBACK.md:186` | `[T+11:00]` | display token in log timestamp | 🟡 OK | Doc-only display; not decision logic. |

### C. Timezone names

| File:line | Pattern | Code excerpt | Class | Reason |
|---|---|---|---|---|
| `services/market_health.py:77` | `Australia/Sydney` | `SYDNEY_TZ = pytz.timezone("Australia/Sydney")` | 🟢 SAFE | Auto-DST via pytz. Used by all market_health scheduling/session functions. |
| `services/governance.py:59` | `Australia/Sydney` | `SYDNEY_TZ = pytz.timezone("Australia/Sydney")` | 🟢 SAFE | Auto-DST via pytz. Drives daily/weekly/monthly schedule branches at gov:1009/1018/1027/1032. |
| `services/dashboard_api.py:2306-2311` | `Australia/Sydney` | `DATE(to_timestamp(exit_time) AT TIME ZONE 'Australia/Sydney')` | 🟢 SAFE | Postgres TZ name (DST-aware). |
| `dashboard/dashboard.html:658,695,696` | `Australia/Sydney` | `toLocaleString('en-AU',{timeZone:'Australia/Sydney',...})` | 🟢 SAFE | Browser DST-aware. Display layer. |
| `dashboard/dashboard-wallet.html:270,332,353` | `Australia/Sydney` | same pattern | 🟢 SAFE | Same — display + day-boundary calc for sydNow uses Australia/Sydney. |
| `dashboard/dashboard-analytics.html:272,302,439` | `Australia/Sydney` | same pattern | 🟢 SAFE | Display only. |
| `services/bot_core.py:748,763,767,770,773,779` | `AEDT` (string label) | log lines like `"TIME_PRIME: hour=%d AEDT — ..."` | 🟡 OK | String label is misleading (says "AEDT" while Sydney is AEST), but it's log text only. The decision uses a separate hardcoded offset (rows in §3.A — 🔴). |
| `dashboard/dashboard.html:529,544,559` | `AEDT` (header label) | `<th>Time (AEDT)</th>` | 🟡 OK | Static UI header label. Underlying timestamps render in Australia/Sydney via JS so timezone is correct; label cosmetic-stale only (says AEDT but renders AEST in winter). |

### D. Dynamic resolution usage (SAFE)

| File:line | Code | Class |
|---|---|---|
| `services/market_health.py:77,80-107` | pytz Australia/Sydney + helper fns get_sydney_time / sydney_to_utc / get_current_session_sydney | 🟢 |
| `services/governance.py:59,70-71,229,593,1005` | pytz Australia/Sydney + scheduled-loop hour/weekday/day branches | 🟢 |

### E. Naive datetime suspects

| File:line | Pattern | Class | Reason |
|---|---|---|---|
| `session_outputs/state_check.py:419` | `datetime.utcnow()` | 🟡 OK | Out-of-tree audit script (not a service). Display only. Mark for cleanup if revived. |
| `services/*` | 0 occurrences of `datetime.utcnow()` or naive `datetime.now()` | 🟢 SAFE | All Python service code uses `datetime.now(timezone.utc)` consistently. |
| `Scripts/*` | 0 occurrences of `datetime.utcnow()` or naive `datetime.now()` | 🟢 SAFE | All scripts use `datetime.now(timezone.utc)` (≥10 instances across audit.py, continuous_audit.py, health_check.py). |

### F. Cron / schedule

| File:line | Pattern | Class | Reason |
|---|---|---|---|
| `services/governance.py:996-1037` | `_scheduled_loop` — Sydney 7am, Mon 6am, 1st of month 7am | 🟢 SAFE | Branches use `get_sydney_time()` (pytz Australia/Sydney). Auto-DST. |
| `services/bot_core.py:2173-2184` | `_daily_reset` — UTC midnight | 🟡 OK-WITH-CAVEAT | `daily_pnl_sol` resets at UTC midnight (10:00 Sydney AEST / 11:00 AEDT). Not a hardcoded-offset bug, just a convention choice. **DAILY_LOSS_LIMIT_SOL window is therefore the UTC day**, not the Sydney day. See §4 Suspect 3. |
| Repo root `*.toml` / `*.yaml` / `*.yml` | 0 hits | 🟢 SAFE | No cron declarations in config files. |

### G. Daily-window/midnight

| File:line | Pattern | Class | Reason |
|---|---|---|---|
| `services/bot_core.py:2174,2177-2178` | `"Reset daily P/L at midnight UTC"` + `now.replace(hour=0,...)+timedelta(days=1)` | 🟡 OK-WITH-CAVEAT | UTC midnight (consistent with comment). Not a 🔴 — design choice — but worth noting that the daily loss-limit "day" runs UTC, not local. See §4 Suspect 3. |
| (no other matches) | n/a | 🟢 | n/a |

---

## §4 Suspect findings

### Suspect 1 — TIME_PRIME logic (services/bot_core.py:754,776)

- TIME_PRIME multiplier: env-controlled, defaults to `1.0` (`os.environ.get("TIME_PRIME_MULTIPLIER", "1.0")`). TIME_PRIME hours: env-controlled, defaults to `""` (empty set → branch never fires). **Multiplier disabled by default → moot in production today.**
- Timezone: still **hardcoded** `timezone(_td(hours=11))` at lines 754 and 776. Code comment at line 748 explicitly acknowledges the bug. **NOT YET FIXED.**
- Existing roadmap item: `TIME-PRIME-AEDT-AEST-DRIFT-001` (📋 PLANNED 🟢 LOW) — confirmed live in `ZMN_ROADMAP.md:93`. Covers this exact issue. **Not addressed in code.**
- Classification: 🔴 BUG (decision logic). Material for the active TIME_GOOD (7,8,9,21), TIME_DEAD (11-16), TIME_SLEEP (2-5), and WEEKEND_BOOST (≥5 weekday) branches **even though TIME_PRIME is disabled** — these other branches still fire and use the same wrong `aedt_hour`.
- Impact under current state: TIME_GOOD/TIME_DEAD/TIME_SLEEP windows fire 1h earlier than their labels claim. e.g. log "TIME_GOOD hour=7 AEDT" actually fires at Sydney clock 6:00. Sizing multipliers (1.5×, 0.3×, 0.3×) are mis-aligned with the data on which they were tuned (which uses Postgres `AT TIME ZONE 'Australia/Sydney'` = correct).

### Suspect 2 — Other time-of-day branches in bot_core.py

Same `aedt_hour` / `aedt_weekday` variable used at lines 765, 768, 771, 777 for TIME_GOOD, TIME_DEAD, TIME_SLEEP, WEEKEND_BOOST. Single root cause; fixing lines 754 + 776 fixes all four downstream branches at once. No additional 🔴 hits in this file.

### Suspect 3 — Daily PnL / DAILY_LOSS_LIMIT_SOL reset

- Reset: `services/bot_core.py:2173-2184` `_daily_reset` — sleeps until next UTC midnight, then sets `self.portfolio.daily_pnl_sol = 0.0`.
- Check: `services/risk_manager.py:211-212` and `:302-303` — fires `EMERGENCY_STOP` when `portfolio.daily_pnl_sol <= -DAILY_LOSS_LIMIT_SOL`.
- Window semantics: the loss-limit "day" is the **UTC day**, not the Sydney day. UTC midnight = AEST 10:00 (or AEDT 11:00). Not a hardcoded-offset bug — the code is internally consistent; comment at line 2174 says "midnight UTC" explicitly.
- Classification: 🟡 OK-WITH-CAVEAT. The audit prompt warned of the failure mode "1h drift means trading past loss-limit for 1h every day"; that drift does NOT occur here. The risk is more subtle: a Sydney-evening loss accumulation crosses UTC midnight before the loss-limit fires for the new day. This is a design choice (UTC-day window) not a timezone bug. No code change recommended unless a session re-decides loss-window semantics.

### Suspect 4 — Portfolio snapshot timestamps

- Writes: `services/bot_core.py:362-364, 1538, 2162-2164` and `services/treasury.py:182` all use `datetime.now(timezone.utc).isoformat()`.
- Schema: `portfolio_snapshots.timestamp` is `TEXT NOT NULL` (`services/db.py:92`), receiving a UTC ISO string.
- Classification: 🟢 SAFE. UTC throughout. No drift risk.

### Suspect 5 — Trading-hour gates outside TIME_PRIME

- `services/risk_manager.py:160-174` (`_time_of_day_multiplier`): uses **pure UTC** for sizing windows labeled `(0,4)=Asia 0.70`, `(4,8)=Dead 0.55`, `(8,12)=EU 0.90`, `(12,17)=Peak 1.00`, `(17,21)=US-aft 0.90`, `(21,24)=Decline 0.70`, plus weekend Fri 21:00 UTC – Sun. Code is internally consistent (comment line 161: `(UTC)`).
  - **Finding:** This multiplier is invoked by `risk_manager.calculate_position_size` (line 257) and the result `tod_mult` is multiplied into the position size. **`bot_core._compute_position_size_for_signal` in lines 699-746 calls `calculate_position_size` first, then applies its own `aedt_hour`-based multipliers (TIME_GOOD/TIME_DEAD/TIME_SLEEP/TIME_PRIME) on top.** So sizing is double-multiplied: once by UTC bands (risk_manager) and once by hardcoded-AEDT bands (bot_core).
  - The labels Asia/EU/US in risk_manager describe global market sessions (which are UTC-anchored, not Sydney-anchored), so the UTC choice is defensible there. The fact that bot_core then layers Sydney-clock multipliers on top is fine in design but exposed to the Sydney offset bug.
  - Classification: 🔵 MARGINAL — UTC choice is defensible but fragile under reasoning. Document the convention.
- `services/governance.py:1009,1018,1027,1032`: Sydney-time scheduling — uses `get_sydney_time()` (pytz). 🟢 SAFE.
- `services/treasury.py`: 0 hour-based decision branches. 🟢 SAFE.
- `services/signal_aggregator.py:1968-1969` (ML feature derivation): `"hour_of_day": datetime.now(timezone.utc).hour, "is_weekend": 1 if datetime.now(timezone.utc).weekday() >= 5 else 0`.
  - **Finding:** UTC hour-of-day is fed into the ML feature vector. Sydney weekend starts ~14:00 UTC Saturday. Feature is internally consistent with itself across train+predict (both run in UTC), but if any other consumer compares this `hour_of_day` to a Sydney clock value (e.g. dashboard tile) it would be off by 10-11 hours. No such cross-comparison found in current code. ML interpretation may also be misleading — "hour_of_day=20" in training rows means UTC 20 = Sydney 6-7am, not the Sydney evening that "hour 20" might suggest in a chat or doc.
  - Classification: 🔵 MARGINAL. Not a P&L bug today; documentation hazard.

### Suspect 6 — Dashboard / web layer timezone use

- `services/dashboard_api.py:2306-2311`: SQL `DATE(to_timestamp(exit_time) AT TIME ZONE 'Australia/Sydney')` — Postgres handles DST. 🟢 SAFE.
- `dashboard/dashboard.html:529,544,559`: column headers `<th>Time (AEDT)</th>` — static label, **misleading in winter** (currently AEST). 🟡 OK-WITH-CAVEAT (cosmetic; underlying values render in Australia/Sydney correctly).
- `dashboard/dashboard.html:658,695,696`, `dashboard-wallet.html:270,332,353`, `dashboard-analytics.html:272,302,439`: all use `toLocaleString('en-AU',{timeZone:'Australia/Sydney',...})`. Browser handles DST. 🟢 SAFE.
- `dashboard-wallet.html:332-334`: day-boundary calc for "today PnL" uses Australia/Sydney — `sydNow.setHours(0,0,0,0)` = Sydney midnight. **Display-decision (which trades count as today)**: 🟡 OK-WITH-CAVEAT — using `Australia/Sydney` is DST-correct, but: (a) `new Date(now.toLocaleString('en-US',{timeZone:'Australia/Sydney'}))` is a known JS anti-pattern that loses the timezone tag in some edge cases; (b) the resulting "today PnL" boundary is Sydney-midnight while the bot's `_daily_reset` runs UTC midnight — UI vs core daily-PnL boundary mismatch (UI shows 0 SOL until Sydney midnight rolls; bot's loss-limit window resets at UTC midnight). Worth a doc note; not a P&L decision bug today.
- No alert thresholds in dashboard\* gated on hour-of-day directly. 🟢 for the main decision surface.

### Suspect 7 — Audit doc / log timestamps

- `session_outputs/ZMN_LIVE_ROLLBACK.md:186` `[T+11:00]` — display only. 🟡 OK-WITH-CAVEAT.
- All canonical log writes in services/ use `datetime.now(timezone.utc)`. 🟢 SAFE.

### Suspect 8 — services/market_health.py (BLOCKING-CHECK for next session)

- Lines 76-107: `SYDNEY_TZ = pytz.timezone("Australia/Sydney")` + DST-aware helpers `get_sydney_time()`, `sydney_to_utc()`, `get_current_session_sydney()`.
- Hour-of-day decision: line 95 `h = get_sydney_time().hour` — DST-aware via pytz. 🟢 SAFE.
- Line 162 use: `session_name, session_quality = get_current_session_sydney()` and `syd = get_sydney_time()` — published to Redis `market:session`. 🟢 SAFE.
- 0 hardcoded offsets, 0 naive datetime, 0 fixed-offset timezones in this file.
- **Verdict:** market_health.py is **CLEAN**. **No 🔴.** **NOT BLOCKING for MARKET-MODE-001-RE-CALIBRATE.** That session can proceed without bundling a timezone fix.

---

## §5 Aggregate counts (production code only)

Counts limited to in-tree production code: `services/`, `dashboard/`, `Scripts/`, repo root. Excludes `.tmp_*/`, `repomix-output.xml`, `session_outputs/*.md`, `docs/`, audit/proposal docs.

| Class | Count | Files |
|---|---:|---|
| 🔴 BUG | 2 | services/bot_core.py:754, services/bot_core.py:776 (single root cause) |
| 🔵 MARGINAL | 2 | services/risk_manager.py:160-174 (UTC time-of-day multipliers); services/signal_aggregator.py:1968-1969 (UTC hour_of_day ML feature) |
| 🟡 OK-WITH-CAVEAT | 5 | services/bot_core.py:2173-2184 daily_reset UTC; services/bot_core.py:763-779 log-string "AEDT"; dashboard/dashboard.html `<th>Time (AEDT)</th>` cols (≥3); dashboard-wallet.html sydNow today-boundary; session_outputs/ZMN_LIVE_ROLLBACK.md (doc only) |
| 🟢 SAFE | 20+ | services/market_health.py (full file); services/governance.py SYDNEY_TZ + scheduled_loop; services/dashboard_api.py SQL; dashboard/*.html clocks (Australia/Sydney); all `datetime.now(timezone.utc)` storage timestamps in bot_core, dashboard_api, governance, ml_engine, ml_model_accelerator, nansen_client, nansen_client_v2, paper_trader, risk_manager, signal_aggregator, signal_listener, telegram_listener, treasury, market_health (≥80 distinct call sites) |

---

## §6 Per-🔴 fix proposal (DO NOT IMPLEMENT)

| # | File:line | Mechanism | Complexity |
|---|---|---|---|
| 1 | `services/bot_core.py:754` | Replace `from datetime import timedelta as _td` block + `aedt_hour = datetime.now(timezone(_td(hours=11))).hour` with `from zoneinfo import ZoneInfo` (or `import pytz`) and `sydney_hour = datetime.now(ZoneInfo("Australia/Sydney")).hour`. Rename the local `aedt_hour` to `sydney_hour` (or keep alias). Update log strings from `"AEDT"` to `"AEST/AEDT"` or just `"Sydney"`. | **S** |
| 2 | `services/bot_core.py:776` | Same swap for `aedt_weekday`. | **S** (paired with #1) |

Both fixes are in the same function (`_compute_position_size_for_signal`, ~30 lines apart), use the same imports, and have a single behavioral effect: shifting all hour-windowed multipliers by +1h in Sydney clock terms (back to where their labels claim they fire). Combined complexity: **S** — 6-10 line diff, ~5min code review, ~5min py_compile + smoke test of `_compute_position_size_for_signal`.

Both already covered by existing roadmap item `TIME-PRIME-AEDT-AEST-DRIFT-001` (no expansion needed). See §8 below.

---

## §7 Recommended convention

**One short rule for the codebase:**

> All time-based **decision** logic (entry filters, sizing multipliers, gates, scheduled-task firing branches, daily/weekly window rollovers) MUST resolve the timezone dynamically via `zoneinfo.ZoneInfo("Australia/Sydney")` (preferred, stdlib in 3.9+) or `pytz.timezone("Australia/Sydney")` (existing convention in market_health.py + governance.py). All **storage** timestamps MUST use `datetime.now(timezone.utc)`. All **display** layers SHOULD use `Australia/Sydney` (Postgres `AT TIME ZONE`, JS `toLocaleString` with `timeZone:'Australia/Sydney'`). **Hardcoded fixed offsets** (`timezone(timedelta(hours=N))`, `+10:00`, `+11:00`, `_td(hours=11)`, etc.) are **NEVER** acceptable for any of these uses.

The only legitimate use of UTC for decision logic is when the decision is genuinely UTC-anchored (e.g. risk_manager.py global-session multipliers). Such uses must be commented as `# UTC by design` with a one-line rationale.

---

## §8 Roadmap entries — proposed updates

### Existing item — confirmed coverage, no expansion needed

| ID | Status | Coverage check |
|---|---|---|
| `TIME-PRIME-AEDT-AEST-DRIFT-001` | 📋 PLANNED 🟢 LOW (per ZMN_ROADMAP.md:93) | **Covers both bot_core.py:754 and :776** (single fix-point in `_compute_position_size_for_signal`). No expansion needed — the existing description already says "All TIME_GOOD/TIME_DEAD/TIME_SLEEP windows fire 1h earlier in Sydney clock than their labels suggest. Fix: replace with `zoneinfo.ZoneInfo('Australia/Sydney')`." which exactly captures this audit's 🔴 findings. |

### Proposed new items (LOW priority — neither is decision-affecting today)

| ID (proposed) | Tier | Description |
|---|---|---|
| `TZ-CONVENTION-DOC-001` | 🟢 LOW | Codify §7 convention statement in `CLAUDE.md` Operating Principles. Add a "use ZoneInfo for decisions; UTC for storage; no hardcoded offsets" bullet. |
| `RISK-MGR-TZ-COMMENT-001` | 🟢 LOW | Add `# UTC by design — global market session bands` comment block to `services/risk_manager.py:69-78` (TIME_OF_DAY_MULTIPLIERS) so future readers don't mistake it for a candidate to "Sydney-ize". Optional: rename windows from "Asia/EU/US" labels to explicit UTC band labels. |
| `SIGAGG-ML-HOUR-LABEL-001` | 🟢 LOW | Document in code/AGENT_CONTEXT.md that `hour_of_day` ML feature at signal_aggregator:1968 is **UTC hour**, not Sydney hour. Helps future ML feature-importance analyses interpret "hour_of_day=20" correctly (=Sydney 6-7am, not Sydney evening). |
| `DASH-AEDT-LABEL-001` | 🟢 LOW | Replace static `<th>Time (AEDT)</th>` headers in `dashboard/dashboard.html` (lines 529, 544, 559) with `<th>Time (Sydney)</th>` or dynamic-label JS that renders the live abbreviation. |

### Items NOT to file

- The 🟡 daily_reset UTC-midnight choice is a design decision, not a bug. Don't file unless a session re-decides loss-window semantics.

---

## §9 Carry to next session

**MARKET-MODE-001-RE-CALIBRATE** — `services/market_health.py` has **0 🔴 timezone bugs**. The file is fully DST-aware via `pytz.timezone("Australia/Sydney")`. No timezone-fix bundling required for that session. Proceed as scoped.

**For any future session that touches `services/bot_core.py` lines 700-800:** consider folding the `TIME-PRIME-AEDT-AEST-DRIFT-001` fix into the same edit. The hardcoded offset is a 6-10 line diff in the function being touched.

---

## Notes / Caveats

- This is a sweep, not a complete audit. Greps used breadth coverage with head-limits up to 100. Pattern coverage was high enough to surface the 2 in-prod 🔴 hits with confidence; no patterns truncated.
- `repomix-output.xml`, `.tmp_*/`, and `session_outputs/*.md` files are excluded from production-code counts — they are tooling/audit artifacts.
- Did not deep-read `services/ml_engine.py`, `services/ml_model_accelerator.py`, `services/nansen_client*.py`, `services/paper_trader.py`, `services/signal_listener.py`, `services/telegram_listener.py` line-by-line — all surveyed via grep and confirmed to use only `datetime.now(timezone.utc)` (no hardcoded offsets, no naive datetime, no hour-based decision branches found by grep).
- Did not run any Redis/DB writes; this audit is read-only as scoped.

---

## §10 Decision Log entry (paste into ZMN_ROADMAP.md)

```
2026-05-05 TIMEZONE-AUDIT-001 ✅ AUDIT COMPLETE — Repository-wide read-only sweep for hardcoded TZ offsets. Findings (production code): 2 🔴 BUG (services/bot_core.py:754,776 — both covered by existing TIME-PRIME-AEDT-AEST-DRIFT-001 follow-up; single fix-point in `_compute_position_size_for_signal`), 2 🔵 MARGINAL (risk_manager UTC-by-design; sigagg ML hour_of_day in UTC), 5 🟡 OK-WITH-CAVEAT (daily_reset UTC midnight design choice; AEDT log/UI labels), 20+ 🟢 SAFE. **services/market_health.py is CLEAN** — fully DST-aware via `pytz.timezone("Australia/Sydney")`; **NOT BLOCKING for MARKET-MODE-001-RE-CALIBRATE**. Class of bug verdict: contained — single root cause already on the roadmap; no new 🔴 surfaced. New LOW-priority items proposed: TZ-CONVENTION-DOC-001, RISK-MGR-TZ-COMMENT-001, SIGAGG-ML-HOUR-LABEL-001, DASH-AEDT-LABEL-001 (all hygiene). Recommended convention: decision logic uses `ZoneInfo("Australia/Sydney")` or pytz; storage uses UTC; no hardcoded offsets anywhere except UTC-by-design global-session bands (which must be commented). Audit: `docs/audits/TIMEZONE_AUDIT_2026_05_05.md`.
```

**Carry to next session (MARKET-MODE-001-RE-CALIBRATE):** ✅ no timezone-fix bundling required; `services/market_health.py` is clean.
