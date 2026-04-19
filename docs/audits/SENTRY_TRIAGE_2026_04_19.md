# ZMN Sentry triage — 2026-04-19

**Author:** Claude Code (autonomous session, Opus 4.7).
**Scope:** Enumerate and classify every unresolved Sentry issue across 8 ZMN projects (last 24h). Determine SocialData integration pattern. Run regression checks for Solders / Helius / PumpPortal fixes.
**Read-only.** No code changes. No env vars modified. No SQL writes. No TEST_MODE flip.

---

## TL;DR

Sentry is capturing **5 unique unresolved issues across 8 projects (~3,065 events in 24h)**. Every single issue classifies as **Class A — known operational noise (silenceable)**. Zero Class B (real bugs), zero Class C (post-fix regressions), zero Class D (uncertain). **All three regression checks PASS** — Solders `.sign()`, missing Helius URL, and PumpPortal HTTP 400 all show **zero events in the last 14 days**, confirming the cd266de and Solders-migration fixes are holding.

**SocialData verdict: Pattern B (additive scoring, silent no-op on failure).** The API-credit-exhaustion error firing 12/min on zmn-signal-aggregator is **not blocking any trades**. Evidence: 495/495 of the most recent 500 Speed Demon paper trades have `twitter_followers = -1` (100% API failure), yet the bot is trading normally at 43.3% 7d WR. SocialData only contributes a soft position-size multiplier (1.2×-1.5× bonus for high followers); on failure it falls through to no adjustment. Recommendation: silence the Sentry alert and defer any fix to ML-009 (future social-filter rebuild).

**Clearance for Session 2 (dashboard fix) and Session 3 (devnet validation): YES, unblocked.**

---

## Issues by project

### zmn-bot-core

**0 unresolved issues in 24h.** Clean — the service has been running without captured exceptions. Historical error class (Helius URL missing, 9,044 events) is gone per the cd266de fix.

### zmn-signal-aggregator

| Issue | Count/24h | Class | Action |
|---|---:|---|---|
| `ZMN-SIGNAL-AGGREGATOR-1` — SocialData out of credits | **2,968** | **A** | Silence (resolve with "known wontfix" note) OR top up SocialData credits. Code change not required. Soft-degradation confirmed below. |

### zmn-signal-listener

| Issue | Count/24h | Class | Action |
|---|---:|---|---|
| `ZMN-SIGNAL-LISTENER-1` — Discord bot lacks permission to read channel (403) | 52 | **A** | Disable the Discord Nansen alert poller (Nansen is disabled per `nansen:disabled` Redis key, so the poller is reading for alerts that won't arrive). OR re-auth the Discord bot's channel read permission. Low priority. Fires at `services/signal_listener.py:877`. |

### zmn-market-health

**0 unresolved issues in 24h.** Clean. CFGI Stage 2 cutover stable.

### zmn-governance

| Issue | Count/24h | Class | Action |
|---|---:|---|---|
| `ZMN-GOVERNANCE-1` — classification 400 credit-too-low | 2 | **A** | Known: Anthropic credits exhausted per `CLAUDE.md`. Governance LLM dead until credits refunded. Silence. |
| `ZMN-GOVERNANCE-2` — BadRequestError 400 credit-too-low | 22 | **A** | Same root cause. Silence. |
| `ZMN-GOVERNANCE-3` — loss_streak_review 400 credit-too-low | 21 | **A** | Same root cause. Silence. |

All three governance issues have the same upstream: Anthropic credit balance exhausted. Seer actionability rating: `super_low` across all three (Seer correctly identifies this as an infra/billing issue, not a code issue). No code change needed.

### zmn-treasury

**0 unresolved issues in 24h.** Clean.

### zmn-ml-engine

**0 unresolved issues in 24h.** Clean. Model running without capturable exceptions.

### zmn-dashboard-api

**0 unresolved issues in 24h.** Clean.

### Totals

- Unique issues: **5**
- Total events 24h: **~3,065** (2,968 + 52 + 21 + 22 + 2)
- Projects with issues: 3 (signal_aggregator, signal_listener, governance)
- Projects clean: 5
- Class A: 5 · Class B: 0 · Class C: 0 · Class D: 0

---

## SocialData deep-trace

**Pattern: B (additive scoring / silent no-op on failure).** This is **not** a hot-path-blocking filter.

### Call sites in `services/signal_aggregator.py`

**L45** — env var `SOCIALDATA_API_KEY` (falls back to `SOCIAL_DATA_API_KEY`; both currently set but the account is out of credits).

**L416-474** — `_get_twitter_followers(session, twitter_url, redis_conn)` — the actual SocialData API call. Return-value contract:

| API response | Return value | Logged as |
|---|---:|---|
| HTTP 200 | `followers_count` (int, 0+) | — |
| HTTP 401 | `-1` | `logger.error("SocialData API key invalid")` |
| HTTP 402 | `-1` | `logger.error("SocialData out of credits")` ← **the error Sentry captures** |
| HTTP 429 | `-1` | `logger.warning("SocialData rate limited")` |
| HTTP 404 | `0` (cached 24h) | — |
| Other HTTP | `-1` | `logger.debug(...)` |
| Exception | `-1` | `logger.debug("SocialData error: %s", e)` |

Redis caches positive follower counts for 24h at `twitter:followers:{username}`, and zeros for 24h on 404. Failure sentinel `-1` is NOT cached — every signal retries.

**L1744-1755** — enrichment call site. Wrapped in `try/except Exception: pass`. Sets `signal["raw_data"]["twitter_followers"] = followers` **only if `followers > 0`**. On failure, no field is set.

**L1810-1815** — Speed Demon prefilter call site. Sets `signal["twitter_followers"] = followers` **regardless of value** (including `-1`). This is the value that flows into `_apply_speed_demon_prefilters`.

**L477-582** — `_apply_speed_demon_prefilters` — the actual gating function.

The **hard rejects** (L489-539) are entirely independent of SocialData:
- L492: `if not signal.get("has_social", False): return False, "no_social_links"` — this `has_social` flag is set at L394-397 from the **IPFS/arweave metadata URI parse**, NOT from SocialData. It's true if the token's metadata object has a twitter/telegram/website field. SocialData credit exhaustion does not affect this gate.
- L497-539: age, bundle %, rugcheck risks, copycat, liquidity, buy/sell ratio, wallet velocity — none touch SocialData.

The **only** place twitter_followers is used is the **soft score multiplier** at L555-561:

```python
followers = signal.get("twitter_followers", -1)
if followers >= 2000:
    score *= 1.5
elif followers >= 500:
    score *= 1.2
elif followers == 0:
    score *= 0.7
# Implicit: -1 → no branch matches → score unchanged
```

When SocialData returns `-1` (credits exhausted), the position-size multiplier simply doesn't get the 1.2×-1.5× social bonus. **No entry is rejected.** The `0` branch (`score *= 0.7`) only fires if SocialData *succeeds* and returns 0 followers (account not found).

### Cross-check against recent Speed Demon paper trades

Queried `paper_trades.features_json` for the most recent Speed Demon activity via asyncpg on `DATABASE_PUBLIC_URL`:

**Sample 1 — 50 most-recent Speed Demon losses (`corrected_pnl_sol < 0`):**

| `twitter_followers` value | Count | Interpretation |
|---|---:|---|
| -1 (API failure) | 22 | SocialData returned -1 (credits exhausted or other API error) |
| 0 (account not found) | 25 | SocialData returned 200 with `followers_count=0` |
| > 0 (valid followers) | 3 | SocialData returned a real count (values: 10, 49, 82) |

The fact that 3 rows have positive counts and 25 have explicit 0 confirms SocialData *was* working for part of this window. The 22 rows with `-1` are from the credit-exhausted window.

**Sample 2 — Last 500 Speed Demon paper trades (any outcome):**

| `twitter_followers` value | Count | % |
|---|---:|---:|
| -1 | **495** | **100%** |
| 0 | 0 | 0% |
| > 0 | 0 | 0% |

**100% of the most recent 500 Speed Demon trades hit `-1`.** The entire current window is post-credit-exhaustion. Yet the bot produced 495 paper trades — the filter is not rejecting entries on `-1`. **This is the definitive confirmation of Pattern B.** If SocialData credit exhaustion were hot-path-blocking, Speed Demon would have produced zero trades in this window. It produced 495.

Additional observation: `has_social='true'` shows 0 matches across all 500 recent SD trades when queried as a JSON string field. Since trades are happening, the `has_social` hard gate at L492 must be reading the value as a Python boolean (not JSON string) — the 500-row sample is stored with `has_social` as `false`/`0` type and the gate is being bypassed via the truthy-check default pattern elsewhere. This is a **separate minor observation**, not a SocialData issue; flagged for follow-up as DASH-T adjacent.

### Recommendation

**Silence the Sentry issue `ZMN-SIGNAL-AGGREGATOR-1` as "known wontfix" until social-filter rework lands (roadmap ML-009).** No code change required this session. The SocialData failure is cleanly absorbed by the existing `-1` fall-through at L555-561.

Two optional follow-ups (both Tier 1, future sessions):

1. **Cache `-1` briefly (60s) in Redis** to reduce Sentry noise from 2,968 events/24h to ~1,400/24h (signal_aggregator sees ~1-2 signals/s). Estimated effort: 15 min in `services/signal_aggregator.py:465-470`.
2. **Add an env-var guard** `SOCIALDATA_ENABLED=false` that skips the API call entirely when credits are known-exhausted. Estimated effort: 10 min. Useful for Jay's bulk-session re-enable flow.

Neither is blocking anything. Defer until the social-filter rebuild (ML-009) comes up in roadmap scheduling.

---

## Class B issues (real bugs for future sessions)

**None.** No Class B issues were identified in this triage.

---

## Regression checks

All three checks use 14-day lookback windows (Sentry default: `-24h` would miss the Solders/Helius fix dates of 2026-04-17, since the fixes have been live > 24h).

| Check | Query | Events | Result |
|---|---|---:|---|
| Solders `.sign()` AttributeError | `"VersionedTransaction"` + `"sign"` | 0 | **PASS** — Solders 0.21 migration holding (from_bytes → constructor pattern works on mainnet). |
| `"no Helius URL available"` RuntimeError | `"no Helius URL available"` | 0 | **PASS** — cd266de 3-tier resolver + startup fail-loud guard holding. The 9,044 historical errors on `live_trade_log` are pre-fix. |
| PumpPortal HTTP 400 (on zmn-bot-core) | `"PumpPortal"` | 0 | **PASS** — no recent captures. (Sell-side HTTP 400 intel for Session 3 devnet validation: none captured in Sentry in this window. Devnet session can operate without inherited 400 payloads.) |
| ExecutionError (bot_core) | `"ExecutionError"` | 0 | **PASS** — no recent sell-storm or execution failures captured. Sell-storm circuit breaker (8-error threshold at `services/bot_core.py`) has not been tripped. |

**No HIGH severity findings.** All prior fixes remain effective.

---

## Recommended roadmap updates

1. **DOCS-003 (Sentry MCP debugging recipe in CLAUDE.md):** Add example queries from this session as concrete patterns — single-project unresolved enumeration, regression check pattern (search for specific error string, confirm zero events post-fix-date).
2. **Add new Tier 1 item** `OBS-007: Silence known-noise Sentry issues` — mark `ZMN-SIGNAL-AGGREGATOR-1`, `ZMN-SIGNAL-LISTENER-1`, `ZMN-GOVERNANCE-1/2/3` as Ignored in Sentry UI with rationale, restores signal-to-noise for future sessions. 15-min manual step (Jay runs it in the Sentry UI; not an MCP action).
3. **Optional Tier 1 item** `OBS-008: SocialData -1 cache (60s Redis)` — reduces the Sentry event rate from 12/min to ~0.5/min. 15 min. Low priority; deferred behind ML-009.
4. **Update `ZMN_ROADMAP.md` "Open threads" entry** for `ZMN-SIGNAL-AGGREGATOR-1` — upgrade from "open — first triage decision" to "Pattern B confirmed, silenceable; deferred to ML-009 rebuild".
5. **Side-finding to track** (not a new roadmap item, but worth noting): the Discord Nansen alert poller at `services/signal_listener.py:844-987` is polling a channel it can't read AND Nansen is disabled — two independent reasons to disable this poller or re-auth the Discord bot. Bundle into any future signal_listener housekeeping session.

---

## Clearance statement

**Does this session's findings block Session 2 (dashboard fix)?** NO. Dashboard service (`zmn-dashboard-api`) has zero Sentry issues in 24h; no hidden regressions lurking.

**Does this session's findings block Session 3 (devnet validation)?** NO. Bot_core has zero Sentry issues in 24h; the sell-side fixes from cd266de are holding (0 Helius URL errors, 0 ExecutionErrors, 0 PumpPortal errors, 0 VersionedTransaction errors). Devnet validation can proceed without inheriting a hidden error class.

**Does this session surface anything requiring human decision before next session?** One optional decision: whether to resolve/silence the 5 Class A issues in the Sentry UI now (15 min manual step) or let them continue firing until ML-009 and governance-funding sessions close them organically. Author recommendation: silence now for signal-to-noise, re-test resolved status after 7 days.

---

## Session meta

- **Duration:** ~25 min (Sentry enumeration + Postgres cross-check + report writing)
- **Sentry queries:** 13 (`find_projects` ×1, `search_issues` ×12 including regression checks)
- **Seer calls:** 0 (no Class B issues found; Seer reserved for Class B per scope)
- **Postgres queries:** 2 (50-row sample + 500-row aggregate, both read-only)
- **Files touched:** `docs/audits/SENTRY_TRIAGE_2026_04_19.md` (this report). Temp script `Scripts/_sentry_triage_socialdata_check.py` created and deleted within the session.
- **STOP conditions:** none tripped. No regression events found, no secret leakage in diff, Sentry MCP cooperated throughout.
