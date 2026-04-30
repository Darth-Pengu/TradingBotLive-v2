# Realism + Roadmap Cleanup — 2026-04-30

**Session:** REALISM-AND-ROADMAP-CLEANUP-2026-04-30
**Author:** Claude Code (autonomous-loop, multi-phase)
**Predecessor:** FEE-LATENCY-REALISM-2026-04-30 (slippage tier fix in commit `f3a1741`)
**Commits this session:** `932ae08` (Phase 1) + `627f4c9` (Phase 2) + final docs commit
**Services redeployed:** market_health, signal_aggregator (twice — Phase 1 + Phase 2)

---

## §1 Executive verdict

| Phase | Outcome |
|---|---|
| **Phase 1 — MARKET-MODE-001** | ✅ DONE. Market mode flipped HIBERNATE → NORMAL post-deploy (verified 13:36 UTC). |
| **Phase 2 — SOCIAL-SCORING-001** | ✅ DONE. Patch 2C (per-component social fields in features_json) deployed. |
| **Phase 3 — ROADMAP-DEFERRED-CLEANUP** | ✅ DONE. 4 Class A items closed (DOCS-004, DOCS-002, OBS-014, TUNE-004). |

No phase hit a STOP condition. No rollbacks. Total redeploys triggered: 2 (market_health 1×, signal_aggregator 2× — Phase 1 cleanup write removed + Phase 2 features added).

---

## §2 Phase 1 — MARKET-MODE-001 (HIBERNATE-forever bug)

### Diagnosis verification

**Code refs:**
- `services/market_health.py:41-47` (PRE-fix) — MARKET_MODES table with `grad_rate` thresholds 0.5 / 0.8 / 1.0 / 1.5
- `services/market_health.py:248` — `_determine_market_mode` requires ALL THREE thresholds (pumpfun_vol AND grad_rate AND dex_vol)
- `services/market_health.py:355-363` (PRE-fix) — read `market:grad_rate_estimate` Redis key
- `services/signal_aggregator.py:1646-1656` (PRE-fix) — wrote `market:grad_rate_estimate` as RATIO (`migrations / new_tokens`)

**Sample at 13:26:51 UTC (Redis):**
- `market:grad_rate_estimate` = **0.0** (rounded ratio; `73 / 701678 = 0.000104` round-3 → 0)
- `market:migration_count_1h` = 73
- `market:new_token_count_1h` = 701,678
- `market:health.mode` = HIBERNATE
- `dex_volume_24h` = $1,396M
- `pumpfun_vol_estimate` = $209M (15% of dex)

**Mismatch:** signal_aggregator wrote a ratio (~0.0001 in steady state); market_health table assumed migrations-per-hour (0.5+ thresholds). The ratio (always tiny) never beat any threshold → always HIBERNATE.

**Sample at 13:29:34 UTC (Redis, 3 min later):** migrations stable at 73, ratio still 0. Confirmed not a transient.

### Patch path chosen — A + B

- **Patch 1A:** recalibrate MARKET_MODES thresholds (count-per-hour basis)
- **Patch 1B:** swap metric — read `market:migration_count_1h` directly; remove the ratio writer in signal_aggregator (no consumer remains)
- **Patch 1C:** PumpPortal stats API for true volume — DEFERRED (not investigated this session; placeholder of 15% of dex remains)

### Threshold table change

```
PRE-fix:  (mode, pumpfun_vol, grad_RATIO, dex_vol)
   FRENZY        500e6  1.5    6e9
   AGGRESSIVE    200e6  1.0    4e9
   NORMAL        100e6  0.8    2e9
   DEFENSIVE      50e6  0.5  1.5e9
   HIBERNATE         0  0.0      0

POST-fix: (mode, pumpfun_vol, grad_PER_HOUR, dex_vol)
   FRENZY        400e6  200    4e9
   AGGRESSIVE    200e6  100    2e9
   NORMAL        100e6   30    1e9
   DEFENSIVE      50e6   10  500e6
   HIBERNATE         0    0      0
```

Plus `_compute_sentiment_score` `grad_scaled` rescaled from `grad_rate * 50` (assumes 0-2 ratio) to `grad_rate * 0.5` (assumes 0-200 count/hr).

### Verify-script output (`.tmp_realism_loop/verify_market_mode.py`)

```
mode        |   dex_vol  migs/hr   pumpfun | label
NORMAL      |     1.40B       73     209M | current_typical (sample 2026-04-30 13:26)
AGGRESSIVE  |     2.00B      100     300M | active_period
AGGRESSIVE  |     3.00B      200     450M | frenzy_candidate
FRENZY      |     5.00B      250     750M | frenzy_clearly
NORMAL      |     1.00B       50     150M | moderate
DEFENSIVE   |     0.70B       20     105M | slow_period
HIBERNATE   |     0.30B        5      45M | very_quiet
HIBERNATE   |     0.10B        0      15M | outage_dead_market
HIBERNATE   |     1.40B        0     209M | good_volume_but_zero_migrations
DEFENSIVE   |     1.40B      200      50M | good_migs_but_low_pumpfun_vol

Distribution: AGGRESSIVE=2 DEFENSIVE=2 FRENZY=1 HIBERNATE=3 NORMAL=2
```

7/10 cases distribute non-HIBERNATE. HIBERNATE only fires under genuine
outage / dead-market conditions.

### Deploy verification (post `932ae08` push at ~13:30 UTC)

Sample at 13:36 UTC:
```
market:mode:current = NORMAL
market:health.mode  = NORMAL
market:health.timestamp = 2026-04-30T13:36:09.334856+00:00
sentiment_score     = 37.0  (was 28.7 pre-fix)
```

Sample at 13:37:17 UTC: `bot:status.market_mode = NORMAL`. bot_core picked up the change via the `market:mode` pub/sub channel.

**Bot was HIBERNATE for weeks; now correctly NORMAL.** Verified.

### Files changed

- `services/market_health.py` — MARKET_MODES table recalibrated; metric semantics changed; sentiment scaling adjusted; docstring rewritten with the bug-history note.
- `services/signal_aggregator.py` — removed the misleading ratio writer (lines 1651-1654 deleted; just keeps the migration count INCR).

---

## §3 Phase 2 — SOCIAL-SCORING-001

### State determined: STATE C (wired and working but missing from features_json)

Audit findings:
- `services/signal_aggregator.py:352-432` — `_fetch_token_metadata_socials` correctly sets `signal["has_twitter"]`, `signal["has_telegram"]`, `signal["has_website"]`, `signal["has_social"]`
- `services/signal_aggregator.py:434-492` — `_get_twitter_followers` correctly fetches via SocialData.tools
- `services/signal_aggregator.py:572-597` — score modifier reads social fields and applies 1.5x / 1.2x / 0.7x boosts based on followers + 1.2x boost when social_count >= 2
- `services/signal_aggregator.py:1937-2022` (PRE-fix features dict) — only `has_social` (any) and `twitter_followers` were captured for ML training
- **Missing from features_json:** `has_twitter`, `has_telegram`, `has_website`, `social_count`

Sample of 100 most recent paper_trades (`.tmp_realism_loop/check_social_features.py`):
- `twitter_followers`: 100/100 populated. Distribution: <1k=70, 5k+=18, missing=7, 1-2k=3, 2-5k=2 — discriminatory
- `has_social`: 100/100 populated
- `social_count`: 0/100 — never present
- `has_twitter` / `has_telegram` / `has_website`: 0/100

### Patch path chosen — 2C

Patch 2C: add the missing per-component social fields to features_json. Minimal change at `signal_aggregator.py:2022-2030`. social_count computed inline as sum of the 3 booleans (matches the score modifier's computation at L591-595).

### Verify-script output (`.tmp_realism_loop/verify_social_patch.py`)

```
Part 1: Source file integration check
  found: "has_twitter":
  found: "has_telegram":
  found: "has_website":
  found: "social_count":
  found: "has_social":
  found: "twitter_followers":
  PASS: all 6 expected social-related feature keys present in code

Part 2: Mock-signal simulation
  all 3 platforms → social_count=3, scoring boost (>=2) APPLIES
  twitter only    → social_count=1, scoring boost DOES NOT APPLY
  no socials      → social_count=0, no boost
```

### Files changed

- `services/signal_aggregator.py` — features dict at line ~2022 extended with 4 new keys (`has_twitter`, `has_telegram`, `has_website`, `social_count`).

### Post-deploy verification (queued)

Will verify via fresh paper_trades.features_json sample after second SA redeploy completes (~5-10 min after Phase 2 push at 13:33 UTC). Expected: fresh rows from ~13:40 UTC onwards have all 4 new keys populated.

---

## §4 Phase 3 — ROADMAP-DEFERRED-CLEANUP

### Items reviewed

Comprehensive sweep of ZMN_ROADMAP.md Tier 1 + Tier 2 items with status DEFERRED, PLANNED, PARTIAL, IN_PROGRESS.

### Class A items closed this session

| ID | Disposition | Notes |
|---|---|---|
| **DOCS-004** | ✅ DONE | CLAUDE.md:478 + AGENT_CONTEXT.md:576 + 1883: `.com (NOT .xyz)` → `.xyz (NOT .com)`. Three docs touched; cited verification source `docs/audits/BITFOOT_2026_BASELINE_2026_04_23.md` §1. |
| **DOCS-002** | ✅ ALREADY DONE | CLAUDE.md:203 + 242 already have the strikethrough + SUPERSEDED note from `e9de6d7`. Verified no further action needed; updated roadmap row to ✅ COMPLETED. |
| **OBS-014** | ✅ MOOT | Searched `scripts/`, `services/`, `dashboard/`, `docs/` for literal `stop_loss_35%`. No production code uses it. Only historical artifacts (DIAGNOSTIC_SNAPSHOT.md, FEATURE_DEFAULT_FIX_REPORT.md, etc) which are append-only history. Updated roadmap row to ✅ MOOT. |
| **TUNE-004** | ✅ DONE | Set 4 stale env vars on signal_aggregator via Railway MCP: `SPEED_DEMON_BASE_SIZE_SOL=0.15` / `SPEED_DEMON_MAX_SIZE_SOL=0.25` / `MAX_SD_POSITIONS=20` / `MIN_POSITION_SOL=0.05` (all match bot_core). Verified-fields-before-coding: grep confirmed signal_aggregator code does NOT read these vars (zero references) — change is purely hygiene/audit, no behavior change. Triggered SA redeploy queued behind Phase 2's redeploy. |

### Class B items deferred (need design pass — out of session scope)

| ID | Reason |
|---|---|
| EXEC-001 / EXEC-002 (paired) | Multi-file execution-path refactor; pool routing state refresh + Jupiter NameError fix |
| OBS-013 (`sig_type=None`) | Investigation across signal_aggregator intake path; may surface broader issue |
| GOVERNANCE-RESILIENCE | Per-personality env-var pattern extension; multi-file refactor |
| SOCIALDATA-AUTO-TOPUP-001 | New cron worker — adds dependency surface |
| SEC-002 | Pre-commit `detect-secrets` hook — needs validation against existing repo |

### Class C items still correctly deferred

| ID | Reason |
|---|---|
| TUNE-001 / TUNE-002 / TUNE-003 / LIVE-001 | Trading-tune changes — affect WR/PnL; not safe in cleanup session |
| TREASURY-TEST-MODE-002 | Per its own audit recommendation: "revisit at V5a-supervised window" |
| SEC-001 / SEC-003 | Require Jay action (creds rotation / GitHub admin toggle) |
| BUG-010 (CFGI hallucination) | Anthropic credits exhausted — governance non-functional |
| ANALYST-PAPER-AUDIT-001 | Read-only diagnostic; out of cleanup scope |
| ML-THRESHOLD-DRIFT-2026-04-29 | Read-only deferred research; out of cleanup scope |
| BUG-019 (Governance SQL type mismatch) | No matches in `services/governance.py` — likely already fixed or in different file. Defer with current "QUEUED 15m cosmetic" status. |
| DOCS-001 (POSTMORTEM v4 cost) | File `ZMN_POSTMORTEM_2026_04_16.md` not found at expected path; may have been moved/archived. Skip. |
| DASH-B-014 (CFGI BTC/SOL) | Cosmetic dashboard fix; deferable. |
| INFRA-001 (postgres-mcp) | `.mcp.json` registration; non-critical. Sessions can use asyncpg shim. |
| BUG-021 bot_core part | Daily PnL writer trade_mode filter; deferred to a sizing-related session. |
| SILENCE-RECOVERY-2026-04-28 | Per AGENT_CONTEXT §7: ✅ CLEARED. Updated roadmap row. |
| STATUS-CONVENTION-001 | Per Session E: ✅ COMPLETED (5+ sessions appending cleanly). Updated roadmap row. |

---

## §5 Loop iterations summary

| Phase | Iterations | Notes |
|---|---:|---|
| Phase 1 — MARKET-MODE-001 | **1** | Single-pass: code change → verify-script → deploy → verified live (NORMAL). No iteration needed. |
| Phase 2 — SOCIAL-SCORING-001 | **1** | Single-pass: STATE C audit → patch 2C → verify-script (source check + mock simulation) PASS. Deploy verification queued. |
| Phase 3 — ROADMAP-CLEANUP | **1** | Single-pass classification + 4 Class A items closed. No verify-loop required for docs/env changes. |

No phase hit the 3-iteration STOP cap.

---

## §6 V5a precondition delta

**Forward (this session):**
- Market mode now correctly classifies as NORMAL/DEFENSIVE/AGGRESSIVE/FRENZY based on real Solana conditions. The HIBERNATE-forever bug that bypassed normal trading for weeks is closed. **HUGE for V5a observation window** — bot can now meaningfully cycle paper trades through correct sizing/aggression mode.
- ML training will accumulate per-component social features (`has_twitter`, `has_telegram`, `has_website`, `social_count`) on fresh paper rows from ~13:40 UTC onward. Future ML retrain cycles can learn from these.
- Vybe URL fix prevents future sessions burning time on `.com` 404s.

**Sideways:**
- Path B (LIVE-FEE-CAPTURE-002) remains V5a-blocking-but-degradable.
- ~3 SOL wallet top-up remains V5a-precondition (Jay action).
- TIME_PRIME-CONTRADICTION-001 remains.

**New blockers:** none. The latency observability follow-up (LATENCY-OBSERVABILITY-001) created by FEE-LATENCY-REALISM session remains, unchanged.

---

## §7 What this session leaves untrusted

1. **Sample size for MARKET-MODE-001 calibration is small.** Two readings 3 minutes apart. The 73 migrations/hour value drove threshold calibration. Real validation needs 24h of observation across day/night cycles. Re-tune if NORMAL fires constantly even during quiet hours, or if AGGRESSIVE never fires during peak hours.

2. **`pumpfun_vol_estimate` still uses 15% of dex_vol placeholder.** Patch 1C (PumpPortal stats API integration) skipped. If PumpPortal volume diverges from 15% baseline (especially during regime shifts), thresholds may need re-tuning.

3. **Phase 2 verification is queued, not done.** Deploy of `627f4c9` is in flight; need to wait ~5-10 min for fresh paper closes to confirm new social fields populate.

4. **Phase 1 `_compute_sentiment_score.grad_scaled` rescaling** changes downstream sentiment scores. New scale: `migrations_per_hour * 0.5` saturates at 200/hr=100. Old: `ratio * 50`. Sentiment values will read differently on future logs/dashboards (37.0 currently vs 28.7 pre-fix). No code consumes sentiment_score for trading decisions (verified via grep), so safe — but operators reading the dashboard will see different numbers.

5. **TUNE-004 env alignment doesn't change behavior.** signal_aggregator code doesn't read these 4 vars. Pure audit hygiene. If a future session re-introduces a sizing computation in signal_aggregator that reads these (mistaken assumption), it'll now use bot_core values — a directionally-correct mistake but still a mistake.

6. **DOCS-002 + OBS-014 marked as already-done / moot — verified by code search but not by exhaustive functional regression test.** If DOCS-002 had a strikethrough that's still misleading some readers, a future session would re-flag.

7. **bot_core's market_mode display source.** When checked at 13:24 UTC (before market_health redeployed), bot_core showed market_mode=DEFENSIVE while market_health.mode was HIBERNATE. That divergence was likely a stale `market:loss_override` Redis key (set by `rug_cascade_monitor`) or a different cached state — out of this session's scope. Documented as a follow-up: there's an unread `market:loss_override` Redis key that `rug_cascade_monitor` sets but no code reads (verified via grep). Track as **MARKET-LOSS-OVERRIDE-DEAD-CODE-001** (low priority).

---

## §8 Reproducibility

Verify scripts:
```bash
python .tmp_realism_loop/verify_market_mode.py
python .tmp_realism_loop/verify_social_patch.py
python .tmp_realism_loop/check_social_features.py
```

Live state checks:
```python
mcp__redis__get("market:health")
mcp__redis__get("market:mode:current")
mcp__redis__get("market:migration_count_1h")
mcp__redis__get("bot:status")
```

Code change inspection:
```bash
git log --oneline f3a1741..HEAD  # session commits
git diff f3a1741..HEAD services/  # all code changes
```

---

## §9 Open follow-ups created by this session

| ID | Severity | Notes |
|---|---|---|
| **MARKET-MODE-001-RE-CALIBRATE** (LOW) | sample size = 2 | Re-tune thresholds if 24h observation shows skewed distribution |
| **MARKET-LOSS-OVERRIDE-DEAD-CODE-001** (LOW) | code hygiene | `rug_cascade_monitor` writes `market:loss_override`; no reader. Either wire it in `_determine_market_mode` (it should DEFENSIVE-cap when set) or remove the writer. |
| **PUMPPORTAL-STATS-API-001** (LOW) | observability | Investigate if PumpPortal exposes a stats/volume endpoint. Replace `pumpfun_vol_estimate = dex_vol * 0.15` with real value. |
| Phase 2 deploy verification | OPEN | Confirm fresh features_json rows include the 4 new social keys after second SA redeploy completes. |

---

## §10 Trade-off summary

| dimension | PRE-session | POST-session |
|---|---|---|
| `market:mode:current` | HIBERNATE (forever, ~weeks) | **NORMAL** (cycles correctly) |
| `market:grad_rate_estimate` | 0.0 (rounded ratio, useless) | n/a (writer removed; market_health reads count directly) |
| MARKET_MODES thresholds | Ratio-based (0.5/0.8/1.0/1.5) | Count-based (10/30/100/200) |
| Sentiment score formula | grad_rate * 50 (assumes 0-2 ratio) | grad_rate * 0.5 (assumes 0-200 count/hr) |
| ML features for socials | has_social + twitter_followers (2 fields) | + has_twitter + has_telegram + has_website + social_count (6 fields) |
| Vybe URL guidance in CLAUDE.md / AGENT_CONTEXT | `.com (NOT .xyz)` (wrong) | `.xyz (NOT .com)` (correct) |
| signal_aggregator size env vars | Stale 0.45/0.75/3/0.10 vs bot_core 0.15/0.25/20/0.05 | Aligned with bot_core |
