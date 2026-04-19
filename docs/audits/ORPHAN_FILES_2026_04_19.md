# ZMN repo — orphan file audit

> **STATUS (2026-04-19):** This audit's actionable items are consolidated in `ZMN_ROADMAP.md`. Refer there for current status, priority, and dependencies. This doc is retained as evidence / deep-dive detail.


**Date:** 2026-04-19
**Scope:** tracked files only (git ls-files). Untracked template leftovers
(`components/`, `css/`, `pages/`, `sections/`, `static/`, `svg/`,
`templates/`, `img/`, `share/`, `etc/`) are analyzed separately in
`DASHBOARD_REDESIGN_2026_04_19.md`.
**Method:** size + reference-graph. A file is "orphan" if it's tracked,
it's non-empty, and nothing else in the tracked repo references it.

---

## Confirmed dead weight (staged for deletion this session)

Located in `js/` at repo root — Webpixels Satoshi DeFi template leftovers
(`pages/dashboard.html` header confirms the template identity).

| File | Bytes | Notes |
|---|---|---|
| `js/main.js.map` | 3,578,158 | Sourcemap; no runtime consumer |
| `js/main.js` | 729,968 | Minified theme JS |
| `js/switcher.js.map` | 8,218 | Sourcemap; no runtime consumer |
| `js/switcher.js` | 1,968 | Theme light/dark switcher |
| **Total** | **4,318,312 bytes (~4.2MB)** | |

**Reference check (tracked-files-only scope):**

```
git ls-files | xargs grep -l -E 'js/main|switcher' --include="*.py" \
    --include="*.html" --include="*.js" --include="*.md" \
    --include="*.toml" --include="*.json" --include="*.yml"
```

Returns zero hits in `services/`, `dashboard/`, `scripts/`, `tests/`,
`main.py`, `CLAUDE.md`, `AGENT_CONTEXT.md`, `ZMN_ROADMAP.md`, `.mcp.json`,
`railway.toml`, `nixpacks.toml`.

**Untracked-file references (non-blocking for deletion):**

- `docs/about.html`, `docs/components.html`, `docs/customize.html`,
  `docs/index.html`, `docs/styleguide.html` — all untracked Satoshi theme
  docs pages, each loads `<script src="/js/main.js">`.
- `pages/*.html`, `templates/*.html`, `static/js/switcher.js` — all
  untracked template files, same references.
- `repomix-output.xml` — untracked scan artifact, irrelevant.

The Satoshi theme files that reference js/ are themselves untracked
and not deployed. They are a local preview of the purchased theme, not
part of the ZMN web app. Deleting `js/` breaks local preview of those
pages — which is acceptable because Jay is not running that preview.

**What serves js/ currently:** nothing. `services/dashboard_api.py:184-187`
only serves paths under `/dashboard/`. Railway uploads `js/` on every
deploy (it's in git), but no route serves it, so it's dead weight on
every build and in every container.

---

## Probably-dead, worth deleting in a later session (NOT this commit)

None found. The `data/models/` directory is 162MB on disk but every file
inside appears to be actively consumed by the ML engine. The `catboost_info/`
directory (64K) is untracked and gitignored already. `.git/` is 75MB —
normal for a repo with this many small commits and a 162MB working tree.

### Archive candidates at repo root — 30 of 35 `.md` files

35 `.md` files at root. By convention, only these 5 belong at root:

- `CLAUDE.md`
- `README.md`
- `AGENT_CONTEXT.md`
- `MONITORING_LOG.md`
- `ZMN_ROADMAP.md`

The other 30 are session-specific reports that make the root directory
hard to scan. Proposal: create `docs/archive/` in a dedicated follow-up
session and move them. Do NOT delete — they're the audit trail Jay relies
on for session-to-session continuity.

Full list (by size descending):

| File | Bytes |
|---|---|
| `DASHBOARD_AUDIT.md` | large |
| `API_AUDIT_REPORT.md` | medium |
| `BUILD_SUMMARY.md` | small |
| `CFGI_DISPLAY_DIAGNOSTIC_2026_04_15.md` | small |
| `DIAGNOSTIC_SNAPSHOT.md` | small |
| `ENTRY_FILTER_REPORT.md` | small |
| `ENTRY_FILTER_v4_REPORT.md` | small |
| `EXECUTION_AUDIT_2026_04_16.md` | medium |
| `EXIT_STRATEGY_FIX_REPORT.md` | small |
| `EXTERNAL_API_AUDIT.md` | small |
| `FEATURE_DEFAULT_FIX_REPORT.md` | small |
| `FIX_CASCADE_REPORT.md` | small |
| `FIX_NO_TRADES_REPORT.md` | small |
| `LIBGOMP_FIX_REPORT.md` | small |
| `OVERNIGHT_REPORT_2026-04-08.md` | small |
| `PAPER_TRADER_PRICE_FIX_REPORT.md` | small |
| `POST_RECOVERY_REVIEW_2026_04_14.md` | medium |
| `REVIEW.md` | small |
| `SHADOW_ANALYSIS_2026_04_16.md` | small |
| `SHADOW_MEASUREMENT_PLAN.md` | small |
| `SMART_MONEY_DIAGNOSTIC.md` | small |
| `SNAPSHOT.md` | small |
| `STAGED_TP_BACKFILL_REPORT.md` | medium |
| `STAGED_TP_FIX_REPORT.md` | small |
| `STATE_AUDIT_2026_04_14.md` | small |
| `TIER2_FOLLOWUPS.md` | small |
| `TIER2_OVERNIGHT_REPORT.md` | small |
| `TP_BASELINE_2026_04_15.md` | small |
| `ZMN_HELIUS_URL_FIX_REPORT.md` | small |
| `ZMN_LIVE_TRIAL_V4_RESULT.md` | small |

Cumulative size: ~400-600KB total. Out of scope for today's commit.

### Sourcemap sweep

`*.map` files are build artifacts. Current inventory after removing js/*.map:

```
git ls-files "*.map"
```

Nothing else. (The two `.map` files in js/ are the only tracked sourcemaps.)

### Binary artifact sweep

Top 20 largest tracked files:

```
data/models/accelerated_model.pkl     311,857 bytes
dashboard/dashboard.html               45,840
.claude/skills/skill-creator/eval-viewer/viewer.html  46,323
dashboard/dashboard-wallet.html        41,858
dashboard/dashboard-analytics.html     41,286
services/signal_aggregator.py         118,563
services/dashboard_api.py             115,693
services/bot_core.py                   95,078
AGENT_CONTEXT.md                       87,463
services/signal_listener.py            69,873
MONITORING_LOG.md                      61,031
... (all appropriate, leave alone)
```

None are orphans. `data/models/accelerated_model.pkl` is actively loaded
by the ML engine; `.claude/skills/skill-creator/eval-viewer/viewer.html` is
part of the installed skill.

---

## Not touching

- `data/models/*` — ML model persistence. Regenerating requires a retrain.
  Needs ML engineer consent to touch.
- `catboost_info/` — already gitignored, not tracked.
- `.git/` — 75MB of history, obviously keep.
- `dashboard/dashboard-analytics.html` / `dashboard/dashboard-wallet.html` —
  served by `dashboard_api.py:184` passthrough route; not orphans.
  See `DASHBOARD_REDESIGN_2026_04_19.md`.

---

## Action summary

- **This commit (Phase 4):** delete `js/main.js`, `js/main.js.map`,
  `js/switcher.js`, `js/switcher.js.map`. Net: ~4.2MB off every Railway
  deploy and every local clone.
- **Next session candidate:** move 30 root-level `.md` reports into
  `docs/archive/` (one dedicated session, no code changes). Cleans up
  root directory without losing audit trail.
- **Nothing else** qualifies as orphan this session.

---

## Methodology notes

**What "orphan" means here:** tracked by git + not referenced by any other
tracked file. Untracked referrers don't count because they're not part
of the deployed app or the CI graph.

**Why this is safe:** `railway.toml` sets `startCommand = "python main.py"`.
`main.py` dispatches by `SERVICE_NAME` env var. No service reads from `js/`.
The dashboard service (`dashboard_api.py`) only serves files under the
`dashboard/` directory. Removing `js/` cannot affect any runtime path.

**What would make this unsafe:** if `dashboard_api.py` grew a static
passthrough for `/js/*` — it hasn't, grep confirms zero occurrences.
Re-run the grep before every future deletion commit.
