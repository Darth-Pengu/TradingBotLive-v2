# Dashboard regression-testing plan — Playwright + webapp-testing skill

> **STATUS (2026-04-19):** This audit's actionable items are consolidated in `ZMN_ROADMAP.md`. Refer there for current status, priority, and dependencies. This doc is retained as evidence / deep-dive detail.


**Author:** Claude Opus 4.7 · **Date:** 2026-04-19 · **Status:** plan only, blocked on Playwright headless stability fix.
**Skill reference:** `.claude/skills/webapp-testing/SKILL.md` — uses native Python Playwright scripts, has `scripts/with_server.py` helper for server lifecycle, recommends "reconnaissance-then-action" pattern (navigate → wait for `networkidle` → screenshot → identify selectors → execute).

---

## Why this plan exists

`DASHBOARD_AUDIT.md` lists bugs B-001 through B-009 and B-014. Several have been "fixed" in code but no automated check verifies they stay fixed. Manual visual inspection on each session-end is unreliable and not catching regressions (B-014 was discovered weeks after its root cause shipped).

The Playwright MCP is now installed and the `webapp-testing` skill is now available — together they enable structured regression tests against `https://zmnbot.com/dashboard/dashboard.html`.

---

## Gating issue: Playwright session instability

This session, both `browser_navigate(zmnbot.com/dashboard/dashboard.html)` and `browser_navigate(zmnbot.com/)` returned `net::ERR_ABORTED; maybe frame was detached?` and `Target page, context or browser has been closed`.

The dashboard URL itself is fine — `curl -I https://zmnbot.com/dashboard/dashboard.html` returns `HTTP/1.1 200 OK` in under 1s.

**This is a Win11 Claude Code + Playwright headless browser issue.** Resolve before building the suite. Triage steps:

1. Try a `browser_open` call before `browser_navigate` (some Playwright wrappers require an explicit context init).
2. Check whether the browser binary is installed under the Playwright cache (`%USERPROFILE%\AppData\Local\ms-playwright\`).
3. Try the `webapp-testing` skill's native Python script approach (`with_server.py`) bypassing the MCP entirely.

Estimated triage: 30 min.

---

## Once unblocked: regression suite scope

### Tests to write (one per registered dashboard bug)

| Bug | Test name | Behavior verified |
|---|---|---|
| B-001 | `test_cfgi_source_label` | The CFGI panel labels its source ("cfgi.io SOL" vs "Alternative.me BTC"); both values present and differ. |
| B-002 | `test_recent_trades_pl_uses_corrected` | Recent Trades widget P/L for trade id <= 3564 matches `corrected_pnl_sol` not `realised_pnl_sol`. |
| B-003 | `test_open_positions_skips_redis_in_live_mode` | When mode=live filter is active, OPEN POSITIONS shows zero entries (no paper-only Redis fallback). |
| B-004 | `test_mcap_columns_present` | Recent Trades + Open Positions both have MCAP columns (USD-denominated). |
| B-005 | `test_speed_demon_panel_aligned` | Speed Demon panel + Analyst panel + Whale Tracker panel have aligned column widths and headers. |
| B-006 | `test_treasury_balance_matches_chain` | Treasury balance widget reads from `bot:status.trading_balance`, not stale Redis. |
| B-007 | `test_no_console_errors` | Page loads with zero JS console errors. |
| B-008 | `test_websocket_connects` | Dashboard's WS connection (if any) opens and exchanges at least one message in 5s. |
| B-009 | `test_no_404_assets` | All `<script>` and `<link>` URLs return HTTP 200. |
| B-014 | `test_btc_cfgi_field` | Dashboard shows distinct values for BTC CFGI vs SOL CFGI; no value duplication. |

### Smoke tests (always run first)

- `test_dashboard_loads_under_3s` — wall-clock budget
- `test_login_redirects_unauth_user` — check `DASHBOARD_SECRET` gate works
- `test_dashboard_has_14_panels` — sanity count (CLAUDE.md says 14-panel retro green dashboard)

### Visual regression tests (lower priority)

Snapshot screenshots at fixed viewport (1920×1080), diff against committed reference PNGs. Catches CSS drift.

---

## Suite structure (Python + Playwright)

Per the `webapp-testing` skill's pattern:

```
tests/dashboard/
├── conftest.py                  # Playwright browser fixture, auth helper
├── test_smoke.py                # Load + login + panel count
├── test_known_bugs.py           # B-001 through B-014, one test each
├── test_visual_regression.py    # Snapshot diffs (later)
└── fixtures/
    ├── reference_dashboard_1920x1080.png
    └── ...
```

Use the skill's `scripts/with_server.py` only if Jay wants to run against a local dev server (currently not set up).

For prod regression, point Playwright at `https://zmnbot.com/dashboard/dashboard.html` and authenticate via the dashboard's existing form-post flow using `DASHBOARD_SECRET`.

---

## Run cadence

- **On every CC session that touches `dashboard/*.html` or `services/dashboard_api.py`**: pre-commit, run the suite locally.
- **Weekly cron**: GitHub Actions or a local cron-job runner — alert via Discord webhook if any test fails.
- **Pre-deploy gate**: not feasible without CI; but a CC pre-commit hook in `.claude/hooks/` could enforce locally.

---

## Estimated build time

- Triage + unblock Playwright session: 30 min
- Conftest + smoke suite (3 tests): 60 min
- Known-bugs suite (10 tests): 90-120 min
- Visual regression infrastructure (later): 90 min

**Total for first useful coverage:** 3-4 hours. Worth it because every B-bug not caught early costs hours of session time later.

---

## Out of scope this session

- Not writing the suite this session (per parent prompt).
- Not fixing B-001 through B-014 — separate dashboard sessions.
- Not modifying `services/dashboard_api.py` to expose test-friendly endpoints (e.g. `/healthz`).

This is a plan, not an implementation. The implementation needs Playwright stability first.
