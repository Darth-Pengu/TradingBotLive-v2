# DASHBOARD-AUDIT-002 — verdict + enhancement list

**Session:** DASHBOARD-AUDIT-002
**Author:** Claude Code (read-only investigation; NO code change committed)
**Date:** 2026-05-13
**HEAD at audit:** `2c9e47b`
**Predecessors:** `DASHBOARD_REDESIGN_2026_04_19.md`, `DASHBOARD_ANALYSIS_2026_04_19.md`, `DASHBOARD_TESTING_PLAN_2026_04_19.md`
**Reality-shift inputs:** `NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` (C1 deploy), `ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` (ML weakly predictive)

---

## §1 Executive verdict

**REAFFIRM REBUILD.** The 2026-04-19 audit's "rebuild not patch" verdict (DASH-001 Concept C "Unified Cockpit") remains the correct posture in 2026-05-13. All 10 enhancement items identified survive the rebuild and would have to be built there anyway. PATCH-NOW count = 1 (G-01 F1+C1 filter visibility), which by itself is below the §8 threshold (needs ≥3 small items to justify a bundled patch session).

**Open question to flag with Jay:** DASH-001 has been QUEUED for ~4 weeks. The audit recommends Tier 1 promotion (schedule the rebuild) rather than continued queue, given that F1+C1 deploys created an observability gap that the rebuild would naturally close. See §7 and §9.

---

## §2 Inventory summary

- **Widget count:** 14 panels on main `dashboard.html` (unchanged since 2026-04-19)
- **Endpoint count:** 44 routes registered in `services/dashboard_api.py`; 18 consumed by main dashboard; ~20 orphaned or only consumed by `dashboard-analytics.html` / `dashboard-wallet.html` (which remain orphaned per 2026-04-19 §1.2 — no nav links)
- **Source baseline:** **1 commit** since 2026-04-19 audit (`bc622eb` BUG-021 trade_mode filter on `api_paper_stats` + `api_portfolio_history`). STOP-B threshold (≤10 commits) cleanly passed.
- **Health:** rendering OK per `STATUS.md` history; B-007 / B-008 / B-009 not verifiable without Playwright (DASH-T-001 scope)

Full widget × endpoint table in `.tmp_dashboard_audit/01_widget_inventory.md`.

---

## §3 Decision-flow audit results

Eight operator decisions analyzed against existing widgets. Result:

| Decision | Support |
|---|---|
| Is the bot healthy right now? | 🟡 PARTIAL |
| Are filters (F1, C1) working as designed? | ❌ MISSING |
| Is daily PnL on trajectory? | 🟡 PARTIAL |
| Are any rollback triggers firing? | ❌ MISSING |
| Is the strategy regime shifting? | 🟡 PARTIAL |
| Are upcoming sessions ready to run? | ❌ MISSING |
| Should I deploy the next filter/retune? | ❌ MISSING |
| Is the wallet/treasury state stable? | 🟡 PARTIAL |

**0 of 8 fully SUPPORTED.** This is consistent with the 2026-04-19 audit's framing that the dashboard surfaces operational *state* but not operational *decisions*. The new operator workload (deploy verification, audit pipeline tracking, rollback-trigger watching) is uniformly under-served.

Full table in `.tmp_dashboard_audit/03_decision_flow.md`.

---

## §4 Reality-shift gaps (top 7)

| ID | Gap | Severity | Effort | Source-reality |
|---|---|---:|---|---|
| G-01 | F1+C1 filter visibility (rejection rate, top blocked tokens, cumulative blocks) | 5 | M | F1 (2026-05-11) and C1 (2026-05-13) are the bot's primary edge-restoration deploys; verification today requires `railway logs \| grep` |
| G-02 | Exit-reason mix time-series (14d stacked area) | 4 | S | NO_MOMENTUM_90S_AUDIT established exit-mix as leading regime indicator |
| G-03 | MC-band distribution at entry (histogram, 7d) | 4 | S | Post-C1 strategy targets <$1K MC entries; histogram makes this verifiable |
| G-04 | ML gate effectiveness (rejections + kept-WR by band + counterfactual) | 3 | M | ML-SCORE-ATH-VALIDATION found thr=40 sub-optimal vs thr=55; retune in queue |
| G-05 | Paper / live mode separation (badge per widget) | 3 | M | Live mode is now session-gated; mixing risk on every per-mode widget |
| G-06 | Disabled-personality badge (Analyst, Whale Tracker) | 2 | S | Both hard-disabled; widgets show stale 0% rows that mislead |
| G-08 | Rollback trigger surface (consecutive_losses, daily floor, emergency_stop) | 3 | S | Multiple in-flight deploys with rollback triggers; today requires Redis MCP query |

Two additional gaps (G-07 audit-pipeline, G-09 nav, G-10 endpoint debt) are lower-urgency carry-overs from 2026-04-19. Full analysis in `.tmp_dashboard_audit/04_gap_analysis.md`.

---

## §5 Known-bug status (B-001 → B-014 + post-Apr-19)

**Closed since 2026-04-19:**
- B-002 (Recent Trades P/L corrected) — moot via BUG-022 pass-through fix (2026-04-30 `392c928`)
- B-004 (MCAP columns) — confirmed in CLAUDE.md "Dashboard mode filter"
- B-011 (outcome NULL) — RESOLVED 2026-04-15
- B-012 (STAGED_TP_FIRE) — FALSE POSITIVE

**Still applies, defer to DASH-001:** B-001 (CFGI source), B-003 (Open Positions live skip Redis), B-005 (panel alignment), B-006 (treasury chain match), B-010 (governance CFGI hallucination — LLM-side), B-013 (paper_trades.symbol upstream — DEFERRED), B-014 (CFGI BTC vs SOL — QUEUED 10m), DASH-AEDT-LABEL-001 (Sydney label), OBS-012 (ml_score column).

**Open separate fix candidates:** DASHBOARD-CORRECTED-PNL-WARN-001 (127 warns/28min), DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001 (masks BUG-010).

**Not verifiable this session (Playwright needed):** B-007, B-008, B-009 — defer to DASH-T-001 testing suite.

Full table in `.tmp_dashboard_audit/05_bug_status.md`.

---

## §6 Prioritized enhancement list (top 10)

| Rank | Item | Effort | Recommendation |
|---:|---|---|---|
| 1 | G-01 F1+C1 filter visibility | M | **PATCH-NOW (only definitive)** |
| 2 | G-03 MC-band histogram | S | WAIT-FOR-REBUILD |
| 3 | G-02 Exit-reason time-series | S | WAIT-FOR-REBUILD |
| 4 | G-08 Rollback trigger surface | S | PATCH-NOW conditional |
| 5 | G-04 ML gate effectiveness | M | WAIT-FOR-REBUILD (post-retune) |
| 6 | DASHBOARD-CORRECTED-PNL-WARN-001 | S | PATCH-NOW conditional |
| 7 | DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001 | S | WAIT-FOR-REBUILD |
| 8 | G-07 Audit pipeline widget | M | WAIT-FOR-REBUILD |
| 9 | G-06 Disabled-personality badge | S | WAIT-FOR-REBUILD |
| 10 | DASH-B-014 CFGI BTC vs SOL | S | DEFER (10m fold-in) |

**PATCH-NOW count:** 1 definitive + 2 conditional = 3 max. Per §8 decision tree, the conditional items are only PATCH-NOW *if* a session is already being spun for G-01, otherwise WAIT.

Full table + per-item ROI in `.tmp_dashboard_audit/06_prioritized.md`.

---

## §7 Rebuild vs patch decision

Decision tree (§8 of prompt):
- 0-2 PATCH-NOW items → REAFFIRM REBUILD
- 3-5 PATCH-NOW items ≤30min each → BUNDLE DASH-PATCH-001
- >5 OR any single item >2h → ACCELERATE REBUILD

We land at: **1 definitive PATCH-NOW item, M-effort (~2-3h)**. This is neither the small-fast-bundle case (Path B) nor the large-many case (Path C). The single item is itself worth a session but not 3-5 quick wins worth bundling.

**Verdict: REAFFIRM REBUILD with explicit DASH-001 scheduling ask.** Reasoning:

1. The 2026-04-19 audit explicitly cautioned: *"every dashboard bug fixed since 2026-04-13 has been re-introduced or partially reverted by a subsequent session — the cost of debt-paying is now higher than the cost of rebuild."* That logic still holds.
2. The F1+C1 first-post-deploy verification log (`FILL_MC_CEILING reject: 6X5V79NvN85P mc=$10753 > ceiling=$1000` at 2026-05-13 03:41:38Z UTC, per `STATUS.md`) already proved the env-only plumbing works. G-01 is desirable, not decision-blocking.
3. The combined eval at ≥2026-05-27 (NO-MOMENTUM-90S-EVAL + STOP-LOSS-20-RUG-FILTER-EVAL) will compute block-rate, FP-winner count, and W4-rate from DB directly — no dashboard required.
4. STOP-A check (≤2 genuinely new gaps beyond 2026-04-19): we identified G-01 as the one definitive new urgency. STOP-A applies weakly — prior audits cover the rest of the framing.

But: **DASH-001 has been QUEUED for ~4 weeks.** Continuing to queue while observability gaps accumulate at every deploy is a deferred cost that compounds. The audit recommends **promoting DASH-001 to Tier 1** so it has a scheduled start window rather than indefinite queue. Concept C "Unified Cockpit" already exists as design; the build (4-6 sessions × 3h per prior estimate) just needs a queue slot.

Decision rationale fully written up at `.tmp_dashboard_audit/07_decision.md`.

---

## §8 References to prior audits

- `docs/audits/DASHBOARD_REDESIGN_2026_04_19.md` (Concept A/B/C design exercise; Concept C = Unified Cockpit = target build)
- `docs/audits/DASHBOARD_ANALYSIS_2026_04_19.md` (frontend-design skill lens, rebuild-not-patch verdict)
- `docs/audits/DASHBOARD_TESTING_PLAN_2026_04_19.md` (DASH-T-001 Playwright regression suite plan)
- `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` (C1 deploy origin; +1.49 SOL/d projection)
- `docs/audits/ML_SCORE_ATH_VALIDATION_001_2026_05_12.md` (ML AUC=0.5361; thr=40 vs thr=55)
- `docs/audits/SERVICE_HEALTH_SNAPSHOT_2026_05_05.md` (DASHBOARD-CORRECTED-PNL-WARN-001, DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001 origins)
- `docs/audits/TIMEZONE_AUDIT_2026_05_05.md` (DASH-AEDT-LABEL-001 origin)

---

## §9 Open questions / limitations

1. **DASH-001 scheduling** — should the rebuild move from QUEUED to scheduled Tier 1? See §7. This is the actual operator-facing decision arising from this audit.
2. **G-01 patch interim** — if DASH-001 cannot be scheduled in 2-4 weeks, revisit Path B (focused observability micro-session adding a `bot:fill_reject_count` Redis counter + a `/api/fill-reject-stats` endpoint). Not recommended this session but a reasonable contingency.
3. **B-007 / B-008 / B-009 verification** — `DASH-T-001` Playwright suite remains BLOCKED on `OBS-004` Win11 Playwright stability fix. Independent of this audit.
4. **DASHBOARD-CORRECTED-PNL-WARN-001 query path** — not grepped this session. A 30-minute follow-up could identify the offending query in `dashboard_api.py` and ship a quiet-the-noise fix. Optional, low priority.
5. **WS handler** — `/ws` is registered but no visible `new WebSocket(...)` in main `dashboard.html`. May be wired only in `dashboard-analytics.html` / `dashboard-wallet.html` (out of scope). DASH-001 should decide whether dashboard is poll-based (current) or WS-based (future).
6. **No live verification** — §3.3 of prompt (live endpoint probes) was skipped because Playwright is blocked. Endpoint response shapes assumed correct from source-code reading; live behavior may differ. If Playwright unblocks, re-run §3.3 against the deployed dashboard.

---

## §10 Decision Log entry (for ZMN_ROADMAP.md)

```
2026-05-13 DASHBOARD-AUDIT-002 ✅ AUDIT COMPLETE (read-only) — Re-evaluation of 2026-04-19 dashboard audits against current bot reality (F1 deploy 2026-05-11, C1 deploy 2026-05-13, ML weakly-predictive finding 2026-05-12, Analyst hard-disabled). HEAD `2c9e47b`; only 1 commit on dashboard files since 2026-04-19 (`bc622eb` BUG-021 trade_mode filter fix). STOP-B PASS. **Verdict: REAFFIRM REBUILD (DASH-001).** Decision-flow audit: 0 of 8 operator decisions fully SUPPORTED, 4 PARTIAL (#1/#3/#5/#8), 4 MISSING (#2 filter visibility / #4 rollback triggers / #6 pipeline state / #7 deploy decisions). Gap analysis surfaced 10 enhancement items; PATCH-NOW count = 1 definitive (G-01 F1+C1 filter visibility, M-effort ~2-3h) + 2 conditional. Below the §8 BUNDLE threshold (needs 3-5 small items). All 10 gaps survive DASH-001 rebuild and would be built there anyway. Bug status: 4 closed since 2026-04-19 (B-002 via BUG-022 pass-through, B-004 confirmed, B-011 + B-012 already closed), 9 still apply (defer to rebuild), 2 separate fix candidates (DASHBOARD-CORRECTED-PNL-WARN-001, DASHBOARD-HEALTH-CHECK-PROBE-DEPTH-001), 3 unverified (B-007/B-008/B-009 need Playwright via DASH-T-001). **STOP-A applies weakly:** prior audits cover everything except G-01 urgency. **Recommendation: promote DASH-001 from QUEUED → Tier 1 scheduled.** DASH-001 has been QUEUED for ~4 weeks; F1+C1 deploys + ML retune queue + audit-pipeline-tracking need create accumulating observability gaps that the rebuild naturally closes. ⛔ DASH-PATCH stays deferred (rebuild-not-patch). Audit: `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md`. NO services/* code change, NO env change, NO Redis writes.
```

---

## §11 Files committed this session

1. `docs/audits/DASHBOARD_AUDIT_002_2026_05_13.md` — this doc
2. `ZMN_ROADMAP.md` — Decision Log entry (above)
3. `AGENT_CONTEXT.md` — header date refresh
4. `MONITORING_LOG.md` — append entry
5. `STATUS.md` — prepend entry

**Not committed:** any code/env change. `.tmp_dashboard_audit/` artifacts are untracked.
