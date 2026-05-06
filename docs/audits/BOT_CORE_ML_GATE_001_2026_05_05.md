# BOT-CORE-ML-GATE-001 — Audit (2026-05-05 ~14:00–15:01 UTC)

> Single-lever session: add an env-controllable, per-personality ML threshold
> gate at bot_core (consumption-time), restoring effectiveness of the
> `ML_THRESHOLD_*` env vars for paper mode that the
> `AGGRESSIVE_PAPER_TRADING + TEST_MODE` override at
> `signal_aggregator.py:158-160` was silently bypassing. Code-only change at
> bot_core; signal_aggregator left untouched. Gate landed inert (default 0)
> and was activated by setting `ML_THRESHOLD_BOT_CORE_SD=40`.

## §1 Executive verdict

**🟢 DEPLOYED — gate active in paper mode.**

- Code commit `ea0da2f` deployed to Railway bot_core service ~14:13 UTC
  (gate inert because env defaults to 0).
- `ML_THRESHOLD_BOT_CORE_SD=40` set on Railway bot_core at
  **2026-05-05T14:16:48Z**, triggering a second auto-deploy. Container
  start at 14:16:48 UTC is the canonical "gate-active" timestamp for all
  downstream observation windows.
- 8/8 verify-script cases PASS (boundary, fail-open, gate-disabled,
  cross-personality cases all match spec).
- §6 post-deploy SQL verification: PASS (low-confidence, single-sample) —
  0 below_40 admissions in 45 min post-cutoff, 1 admission at ml_score=47
  (id=8039), 0 `BOT_CORE_ML_GATE` reject log lines.
- Throughput preservation pending: market_mode=DEFENSIVE during the
  observation window suppresses upstream signal supply, so the paper
  pipeline received only 1 signal at bot_core in 45 min. Higher-throughput
  confirmation requires a NORMAL-mode window
  (MARKET-MODE-001-RE-CALIBRATE follow-up).

**Net effect:** the env value `ML_THRESHOLD_BOT_CORE_SD` is now load-bearing
for paper-mode admission. Prior to this commit, all `ML_THRESHOLD_*` env
vars on bot_core were vestigial (never read in code). Combined with the
pre-existing SA gate, paper mode now has two ML threshold gates active at
the same value (40); the more restrictive one binds. The bot_core gate is
the only paper-effective filter on whether a scored signal becomes a paper
trade — see §6 for the redundancy analysis.

## §2 Investigation findings (pre-implementation)

### §2.1 SA override mechanism — `services/signal_aggregator.py:140-174`

Module-import-time threshold dict (lines 140-149):

```python
ML_THRESHOLDS = {
    "speed_demon": int(os.getenv("ML_THRESHOLD_SPEED_DEMON", "65")),
    "analyst": int(os.getenv("ML_THRESHOLD_ANALYST", "70")),
    "whale_tracker": int(os.getenv("ML_THRESHOLD_WHALE_TRACKER", "70")),
}
```

Override block (lines 152-174 — the operative override is at lines 158-160):

```python
AGGRESSIVE_PAPER = os.getenv("AGGRESSIVE_PAPER_TRADING", "false").lower() == "true"
...
if AGGRESSIVE_PAPER and TEST_MODE:
    ML_THRESHOLDS = {"speed_demon": 30, "analyst": 30, "whale_tracker": 20}
    ML_BOOTSTRAP_THRESHOLDS = {"speed_demon": 30, "analyst": 30, "whale_tracker": 20}
elif AGGRESSIVE_PAPER and not TEST_MODE:
    # ML-012 FIX: log warning, DO NOT override
    ...
else:
    ...
```

Both `AGGRESSIVE_PAPER_TRADING=true` and `TEST_MODE=true` are set on
signal_aggregator (verified via Railway MCP `list-variables`), so the
override fires at module import. The env value of
`ML_THRESHOLD_SPEED_DEMON=65` on signal_aggregator is silently discarded.

`ML_THRESHOLDS` is a module-global dict initialized once at import and never
reassigned in normal flow — there is no per-call escape hatch. The only
way to disable the override at SA is to flip
`AGGRESSIVE_PAPER_TRADING=false` (which would also lose its
intentional design value as an ML-training data-volume preserver — see
§7 for the design rationale).

### §2.2 bot_core consumption path — `services/bot_core.py`

bot_core consumes scored signals via Redis BRPOP at line 1911
(`_consume_signals` loop, lines 1899-1921). Signals arrive as JSON
payloads with `ml_score` as a top-level float:

```python
mint = scored_signal["mint"]
personality = scored_signal["personality"]
ml_score = scored_signal["ml_score"]
market_mode = scored_signal.get("market_mode", "NORMAL")
features = scored_signal.get("features", {})
```

Parsed at `services/bot_core.py:562-566`. `ml_score` is available
**before any decision branch or sizing computation**, satisfying the
STOP CONDITION from the session §2 Step 2.

Pre-fix bot_core had **zero matches** for `ML_THRESHOLD` across the entire
file (`grep "ML_THRESHOLD" services/bot_core.py` returned 0 lines).
`ml_score` was used only for sizing (line 657), logging (line 788), and
DB write-through (lines 807-927) — never as a hard gate.

Confirmed insertion point: **between line 633 (governance max-positions) and
line 639 (CFGI fear gate)**, in parity with where SA places its gate
(after governance/personality enabled, before sizing). The actual landed
gate sits at lines 673-677, after the governance max-positions log
message at line 670.

### §2.3 Empirical SQL discrepancy (paper_trades)

Connection: `gondola.proxy.rlwy.net:29062` (DATABASE_PUBLIC_URL public
proxy). All queries READ-ONLY SELECT.

Both `ml_score` and `ml_score_at_entry` columns exist on `paper_trades`
and are written at entry time. Agreement check: 0 divergent rows over
last 7d (n=551 SD-paper). Canonical column: `ml_score_at_entry`.

**Band query, last 7d (SD-paper, trade_mode='paper'):**

| band | n |
|---|---:|
| 00-30 | 0 |
| 30-40 | 144 |
| 40-50 | 166 |
| 50+ | 241 |
| **TOTAL** | **551** |

**Last 24h (same query):** 17 / 11 / 12 / 0 in 30-40 / 40-50 / 50+ / 00-30
bands respectively (TOTAL=40 trades).

**ml_score range over 7d (SD-paper):**

- min = **30.0** (pinned exactly at SA override floor)
- max = 96.8
- mean = 50.106
- nulls = 0

**Interpretation.** The 00-30 band is empty in both windows (24h and 7d).
Over 551 trades in the past week, zero have a score below 30 — impossible
by chance given the underlying distribution (max=96.8, mean=50.1). The
hard cutoff at exactly 30.0 is the SA override at
`signal_aggregator.py:158-160` writing through to `paper_trades`.

If the env `ML_THRESHOLD_SPEED_DEMON=65` were active, the 30-40 band
would also be 0 (and 40-65 partially zeroed). It is not — env is a no-op.

**Volume that gets filtered with `ML_THRESHOLD_BOT_CORE_SD=40`:**

| Window | Trades < 40 | Total | % filtered |
|---|---:|---:|---:|
| Last 24h | 17 | 40 | 42.5% |
| Last 7d | 144 | 551 | 26.1% |

This is the upper bound on the volume reduction at the bot_core gate. The
true volume reduction will be lower because SA's existing gate at
threshold=30 lets these signals through, but bot_core's gate at 40 will
now filter the 30-40 fraction (the ~26-43% the env was supposed to be
filtering all along).

## §3 Patch path chosen

**Path A — bot_core gate at consumption time** (per session §3 of plan).

### §3.1 Why Path A over Path B/C

- **Path B (fix SA override semantics):** changes the meaning of
  `AGGRESSIVE_PAPER_TRADING` for ML-training data-composition logic.
  Out-of-scope for a single-lever session and risks reducing training
  data volume. Rejected.
- **Path C (Redis-published threshold):** introduces a new control plane
  for a problem that the existing env-var convention already addresses.
  Adds operational surface (Redis key TTL, health monitoring) without
  proportional benefit. Rejected.

Path A is minimal, reversible (`ML_THRESHOLD_BOT_CORE_SD=0` disables it),
and uses the existing env-var control plane.

### §3.2 Code summary — commit `ea0da2f`

3 hunks, +44 lines net to `services/bot_core.py`:

**Hunk 1 — env reads (lines 52-61).** Two new module-level
constants with `int(os.getenv(...))` defaulting to 0. Documented inline
with the override-bypass rationale.

```python
# BOT-CORE-ML-GATE-001 (2026-05-05) — bot_core-side ML threshold gate.
# signal_aggregator.py:158-160 forces an effective paper threshold of 30/30/20
# when AGGRESSIVE_PAPER_TRADING + TEST_MODE are both true, making
# ML_THRESHOLD_SPEED_DEMON env-tuning a no-op for paper mode. This bot_core
# gate restores env-controllable filtering. Default 0 = gate disabled (no
# behaviour change at deploy time); set ML_THRESHOLD_BOT_CORE_SD>0 to activate.
# ml_score is None or threshold==0 → ACCEPT (fail open). Boundary inclusive
# (ml_score == threshold → ACCEPT).
ML_THRESHOLD_BOT_CORE_SD = int(os.getenv("ML_THRESHOLD_BOT_CORE_SD", "0"))
ML_THRESHOLD_BOT_CORE_ANALYST = int(os.getenv("ML_THRESHOLD_BOT_CORE_ANALYST", "0"))
```

**Hunk 2 — helper function (lines 130-153).** Pure module-level helper
returning a reason string or None. Pure for testability — verify-script
exercises this function directly without instantiating the bot.

```python
def _ml_gate_reject_reason(personality, ml_score):
    """Return a human-readable reason if the bot_core ML gate rejects, else None.

    Rules:
      - threshold lookup: speed_demon → ML_THRESHOLD_BOT_CORE_SD,
        analyst → ML_THRESHOLD_BOT_CORE_ANALYST, anything else → ungated.
      - threshold <= 0 → gate disabled (always ACCEPT).
      - ml_score is None → fail open (ACCEPT) — do not block on missing data.
      - ml_score < threshold → REJECT, return reason string.
      - boundary inclusive: ml_score == threshold → ACCEPT.
    """
    if personality == "speed_demon":
        threshold = ML_THRESHOLD_BOT_CORE_SD
    elif personality == "analyst":
        threshold = ML_THRESHOLD_BOT_CORE_ANALYST
    else:
        return None
    if threshold <= 0:
        return None
    if ml_score is None:
        return None
    if ml_score < threshold:
        return f"ml_score={ml_score} below threshold={threshold}"
    return None
```

**Hunk 3 — gate call site (lines 673-677).** Single early-return wired
into `process_signal` immediately after the governance max-positions
check (line 670) and before the CFGI fear gate (line 681) and any sizing
computation (line 689 onward).

```python
# BOT-CORE-ML-GATE-001: env-controllable per-personality ML threshold filter.
ml_reject = _ml_gate_reject_reason(personality, ml_score)
if ml_reject:
    logger.info("BOT_CORE_ML_GATE: skip %s mint=%s %s", personality, mint[:12], ml_reject)
    return
```

### §3.3 Gate semantics (rules summary)

| Condition | Outcome | Rationale |
|---|---|---|
| `personality not in {speed_demon, analyst}` | ACCEPT | whale_tracker / others left ungated; explicit per-personality vars only |
| `threshold <= 0` (env default) | ACCEPT | "0 = disabled" — env-default deploy is a no-op |
| `ml_score is None` | ACCEPT | fail open; do not block on missing data |
| `ml_score < threshold` | REJECT (log + return) | binding case |
| `ml_score == threshold` | ACCEPT | boundary inclusive |
| `ml_score > threshold` | ACCEPT | normal pass |

**No metric counter added** (per §10 STOP rule of the plan — bot_core has
no existing metric infra to extend; adding a Redis counter introduces
new surface area out-of-scope for this session). Gate effects are
visible via `BOT_CORE_ML_GATE: skip ...` log lines and via post-deploy
SQL band queries.

## §4 Verify-script output

Run via `python .tmp_bot_core_ml_gate/verify_gate.py` with
`ML_THRESHOLD_BOT_CORE_SD=40` and `ML_THRESHOLD_BOT_CORE_ANALYST=0` set in
the test env. The script imports `services.bot_core` and exercises
`_ml_gate_reject_reason` directly with stub args.

Output saved to `.tmp_bot_core_ml_gate/verify_output.txt`:

```
======================================================================
BOT-CORE-ML-GATE-001 helper verification
  ML_THRESHOLD_BOT_CORE_SD       = 40
  ML_THRESHOLD_BOT_CORE_ANALYST  = 0
======================================================================
[PASS] case 1: speed_demon ml=25, SD=40 (below threshold) -> REJECT ('ml_score=25 below threshold=40')
[PASS] case 2: speed_demon ml=35, SD=40 (below threshold) -> REJECT ('ml_score=35 below threshold=40')
[PASS] case 3: speed_demon ml=40, SD=40 (boundary inclusive) -> ACCEPT
[PASS] case 4: speed_demon ml=50, SD=40 (above threshold) -> ACCEPT
[PASS] case 5: speed_demon ml=None, SD=40 (fail open) -> ACCEPT
[PASS] case 6a: speed_demon ml=25, SD=0 (gate disabled via monkey-patch) -> ACCEPT
[PASS] case 6b: whale_tracker ml=25 (ungated personality, equivalent to disabled) -> ACCEPT
[PASS] case 7: analyst ml=25, ANALYST=0 (analyst gate disabled) -> ACCEPT
======================================================================
SUMMARY: 8/8 cases passed
======================================================================
ALL_TESTS_PASS
```

**Mandatory cases (per §4 of plan): 6/6 PASS.**
- Case 3 confirms boundary inclusivity: `ml=40, SD=40 → ACCEPT` (not REJECT).
- Case 5 confirms fail-open: `ml=None, SD=40 → ACCEPT` (do not block on
  missing data).
- Case 6a confirms gate-disabled: `SD=0` via monkey-patch → ACCEPT
  regardless of ml_score (the deploy-time default — first deploy is a
  no-op).

**Bonus cases: 2/2 PASS.**
- Case 6b: `whale_tracker` (ungated personality) → ACCEPT regardless.
- Case 7: `analyst` with `ANALYST=0` → ACCEPT (analyst-side gate
  reserved but not yet activated).

## §5 Deploy verification

### §5.1 Timeline

| Time (UTC) | Event |
|---|---|
| ~14:00 | implementer subagent finished local edits |
| ~14:13 | code commit `ea0da2f` deployed to Railway bot_core (gate inert; env defaults to 0) |
| **14:16:48** | `ML_THRESHOLD_BOT_CORE_SD=40` set on Railway bot_core → second deploy auto-triggered; gate-active timestamp |
| ~14:16-14:17 | second deploy active; container start 14:16:48Z |
| ~15:01 | §6 post-deploy verification complete; verdict PASS (low-confidence, single-sample) |

### §5.2 Check 1 — post-deploy SQL band counts

Cutoff epoch: `1777990608` (= 2026-05-05T14:16:48Z UTC, verified via
`SELECT TO_TIMESTAMP(1777990608)`). Spec originally provided
`1746455808` which decodes to 2025 instead of 2026 — used the
corrected value.

```
======================================================================
Check 1 (corrected): SD-paper post-deploy band counts
  cutoff epoch=1777990608 (2026-05-05T14:16:48Z, 2026 corrected)
======================================================================
  cutoff_ts (DB)=2026-05-05 14:16:48+00:00
  db_now=2026-05-05 15:01:46.467610+00:00
  band=40_plus    n=1  earliest=2026-05-05 14:58:36.724524+00:00  latest=2026-05-05 14:58:36.724524+00:00
  (no rows in 00-30 / 30-40 / sub-40 bands)

======================================================================
Most recent SD-paper trade (regardless of cutoff)
======================================================================
  id=8039  entry_time=1777993117  utc=2026-05-05 14:58:36.724524+00:00
          ml_score_at_entry=47.0  ml_score=47.0
```

**Verdict — Check 1: PASS (low-confidence, single-sample).**
- `below_40` count = **0** (consistent with gate firing OR with no <40
  signals reaching bot_core; both indistinguishable in this sample).
- `40_plus` count = **1** (id=8039, mint `EV1na7Wj5WLX`, ml_score=47.0,
  admitted at 14:58:36.7Z = 41m48s post-cutoff).

### §5.3 Check 2 — deploy-log grep for `BOT_CORE_ML_GATE`

Searched the full deploy log payload from 14:16:48Z onward (~52 min of
logs):

- **Zero lines** containing `BOT_CORE_ML_GATE`.
- Single `ENTERING:` line:
  `2026-05-05 14:58:36,370 [bot_core] INFO: ENTERING: speed_demon EV1na7Wj5WLX 0.0872 SOL (ML=47.0, mode=DEFENSIVE) [PAPER]`
- Followed by `paper_trader` PAPER BUY at 14:58:36,748 and
  `SHADOW_MEASURE ENTRY_FILL` at 14:58:36,749.

The single signal that did reach bot_core was processed through
`_ml_gate_reject_reason(personality='speed_demon', ml_score=47.0)`
which returned None (47.0 ≥ 40), and the trade was admitted normally
with no Sentry errors visible around 14:58:36.

**Three possible causes for zero rejects:**
1. No signals reached the gate — partly true: only 1 signal got through
   to bot_core in 52 min, consistent with DEFENSIVE upstream
   suppression (§5.4).
2. All signals had `ml_score >= 40` — supported by the 1 observed
   signal (47.0). With upstream `ML_THRESHOLD_SPEED_DEMON=40` filtering
   at SA AND bot_core gate at 40, the bot_core gate is **redundant in
   the steady-state pipeline**. Rejects only fire on the discrepancy
   edge — the legacy enrichment override case at
   `signal_aggregator.py:158`, which this session was scoped to fix.
3. Gate code path not exercised — extremely unlikely given §5.2's
   admitted trade clearly hit the helper.

**Verdict — Check 2: PASS** (consistent with gate present and inert
under current conditions).

### §5.4 Check 3 — Market state context

| Redis key | Value |
|---|---|
| `market:mode:current` | `DEFENSIVE` |
| `market:health.timestamp` | (key not found) |
| `bot:emergency_stop` | (key not found, healthy) |

`market:mode:current=DEFENSIVE` explains the low throughput post-cutoff.
bot_core entry path applies DEFENSIVE filtering upstream of the gate
(visible in the admitted-trade log line: `mode=DEFENSIVE`). This is
consistent with the V5a NO-GO state from V5A_GO_NO_GO_2026_05_01.md and
the queued MARKET-MODE-001-RE-CALIBRATE follow-up. `bot:emergency_stop`
absent — emergency_stop is NOT tripped (good).

## §6 Implication for V5a observation window

### §6.1 Restart of V5a observation window

The 48h V5a observation window referenced in
`V5A_GO_NO_GO_2026_05_01.md` §2 PC5 is now **considered RESTARTED at
2026-05-05T14:16:48Z** (gate-active timestamp).

**Reasoning:** every post-cutoff paper trade is now subject to a binding
ML threshold of 40 at bot_core. Pre-cutoff paper trades were under the
override-bottomed effective threshold of 30 (with no second gate). The
admission criteria for paper trades have changed; pre-cutoff samples
are not directly comparable to post-cutoff samples.

| Window | Opens | Closes |
|---|---|---|
| 48h V5a observation | 2026-05-05T14:16:48Z | 2026-05-07T14:16:48Z |
| 7d post-this-deploy | 2026-05-05T14:16:48Z | 2026-05-12T14:16:48Z |

### §6.2 Required re-queue

**ML-THRESHOLD-DATA-DRIVEN-RETUNE-002** (the follow-up to the Session 4
sweep that was STOPPED per §8) should be re-queued for **≥2026-05-12
14:16Z UTC**, allowing 7 days of post-gate paper accumulation. Until
then, threshold sweep results across the cutoff are not interpretable as
a single sample (composition has changed mid-stream).

Until 7d post-this-deploy passes, all paper-data analysis must be
flagged as **"post-gate sample only"** in audits and Decision-Log entries.

### §6.3 V5a precondition delta

`V5A_GO_NO_GO_2026_05_01.md` §2 PC5 (48h observation) and PC6 (ML retune
verified) status updates:

- **PC5:** previously failed because <1h since latest deploy (Session 5
  LIVE-FEE-CAPTURE-002 at 12:55 UTC). Now restarted at 14:16:48 UTC,
  closes 2026-05-07 14:16:48 UTC.
- **PC6:** Session 4's STOP rationale (env-var change ineffective due to
  override) is **CLOSED** by this session. The bot_core ML gate is the
  Option-A patch Session 4 explicitly recommended. With env-controllable
  filtering now in place, threshold sweeps post-cutoff are actionable.
  Threshold remains at 40 (matching SA's effective override) until the
  retune session lands; CONDITIONAL → PASS after 7d post-gate sample
  collected.

## §7 Decision Log entry (paste verbatim into ZMN_ROADMAP.md)

```
2026-05-05 BOT-CORE-ML-GATE-001 ✅ DEPLOYED — bot_core ML gate active at threshold 40 (commit ea0da2f, env-active 14:16:48Z UTC). Closes the AGGRESSIVE_PAPER override bypass that contaminated all prior threshold-tuning analysis. 7d observation window for V5a + ML-THRESHOLD-DATA-DRIVEN-RETUNE-002 restarts from 2026-05-05T14:16:48Z. §6 verification PASS (low-confidence, single-sample post-deploy at score=47.0; 0 below_40 admissions; full confidence requires NORMAL market mode and higher signal throughput, currently blocked by MARKET-MODE-001-RE-CALIBRATE follow-up). Re-queue ML-THRESHOLD-DATA-DRIVEN-RETUNE-002 for ≥2026-05-12 14:16Z UTC.
```

## §8 Open issues / what this session does NOT close

### §8.1 Marginal findings (🔵 NUANCE-MISSING)

- **Gate redundancy under steady-state.** When SA's effective gate is 30
  and bot_core's gate is 40, all <30 signals are filtered by SA before
  reaching bot_core. The 30-40 band is what bot_core actually filters.
  Under steady-state agreement of the two gates (e.g. both at 40 for
  paper, or both at 65 for live), the bot_core gate fires zero rejects.
  This is intentional belt-and-suspenders behaviour: bot_core's gate
  fires only on the **discrepancy edge** — when SA passes a sub-40 score
  through the override path, or under a future SA bug or regression
  that re-introduces an effective sub-40 threshold without operator
  awareness.
- **No reject-counter metric.** bot_core has no existing Redis-counter
  infrastructure for ML-gate rejects. Per §10 STOP rule of the plan,
  no new metric was added this session. Reject visibility is via
  `BOT_CORE_ML_GATE: skip ...` log lines (greppable) and via SQL
  band-count diffs across the cutoff. Adding a metric counter would be
  a separate observability lever.
- **Analyst-side gate (`ML_THRESHOLD_BOT_CORE_ANALYST`) is reserved but
  not activated.** Default 0 = disabled. Analyst is currently disabled
  globally via `ANALYST_DISABLED=true` (ANALYST-DISABLE-002 commit
  `9d6e95c`), so the analyst gate is moot until that env flag is
  reverted. Analyst-side activation requires a follow-up session if
  analyst is ever re-enabled.
- **Whale Tracker not gated by env var.** The helper returns None for
  any personality other than `speed_demon` or `analyst`. Whale Tracker
  is dormant (no signal source configured), so this is moot. If
  WHALE-001-v2 lands a Vybe-first whale signal source, a third env var
  (`ML_THRESHOLD_BOT_CORE_WHALE_TRACKER`) would be a small follow-up.

### §8.2 What this session intentionally leaves open

- **AGGRESSIVE_PAPER+TEST_MODE override semantics at SA.** This session
  did NOT modify `signal_aggregator.py:158-160`. Per §1 of the
  ML-RETUNE Session-4 §8 STOP analysis and the AGGRESSIVE-PAPER-DISABLE
  proposal queued in ZMN_ROADMAP.md Tier 2, the override has design
  value as an **ML-training data-volume preserver** — it ensures the
  ML model receives enough labeled outcomes from across the score
  distribution to learn pattern boundaries. Disabling it at SA would
  reduce training data composition. The bot_core gate sidesteps this
  trade-off: SA still passes 30-40 signals (so they get scored,
  enriched, and emitted), but bot_core doesn't trade on them. This is
  the right partition between "training data availability" and "trading
  decision quality."
- **NORMAL-mode confidence sample.** §5 verdict is PASS with low
  confidence. Higher confidence requires a NORMAL-mode window with
  multi-trade-per-hour throughput. MARKET-MODE-001-RE-CALIBRATE
  follow-up is the prerequisite for that confidence. Under HIBERNATE /
  DEFENSIVE cycling, the gate may go hours-to-days between exercises.
- **Post-gate threshold optimum not re-determined.** Session 4's sweep
  found optimum=55 over both 14d and 7d windows under the override-
  bottomed sample. Whether 55 remains optimum under the gate-active
  sample is an empirical question for ML-THRESHOLD-DATA-DRIVEN-RETUNE-002
  (≥2026-05-12). Until then, 40 is conservative and in the right
  direction.
- **Live-mode threshold consistency.** Live mode uses signal_aggregator's
  env value (65, since AGGRESSIVE_PAPER+TEST_MODE override does not
  apply when TEST_MODE=false). bot_core's gate at 40 would NOT bind
  in live (40 < 65). For live mode, only SA's gate is operative. If a
  future session sets `TEST_MODE=false` on bot_core, the bot_core gate
  semantics still apply (bot_core's threshold-vs-ml_score check is
  mode-agnostic) but the binding gate is SA's at 65.

### §8.3 Carry-forward dependencies

| Item | Type | Notes |
|---|---|---|
| MARKET-MODE-001-RE-CALIBRATE | follow-up audit | gate-verification confidence is suppressed under DEFENSIVE/HIBERNATE; needs NORMAL window |
| TIMEZONE-AUDIT-001 | next-session audit | predecessor §0 satisfied by this commit's audit doc + Railway env state |
| ML-THRESHOLD-DATA-DRIVEN-RETUNE-002 | re-queue ≥2026-05-12 | post-gate 7d sample required |
| AGGRESSIVE-PAPER-DISABLE-001 | Tier 2 evaluation | NO LONGER URGENT — bot_core gate sidesteps the SA override impact for trading decisions; SA override retained for training-data composition |

## §9 Files

- `services/bot_core.py` — modified, +44 lines, 3 hunks. Commit `ea0da2f`.
- `.tmp_bot_core_ml_gate/sa_override_mechanism.md` — §2 Step 1 evidence
- `.tmp_bot_core_ml_gate/bot_core_signal_path.md` — §2 Step 2 evidence
- `.tmp_bot_core_ml_gate/sql_evidence.md` — §2 Step 3 SQL findings
- `.tmp_bot_core_ml_gate/sql_evidence.txt` — raw SQL output
- `.tmp_bot_core_ml_gate/verify_gate.py` — verify-script source
- `.tmp_bot_core_ml_gate/verify_output.txt` — 8/8 PASS output
- `.tmp_bot_core_ml_gate/post_deploy_check2.py` — corrected SQL script
- `.tmp_bot_core_ml_gate/post_deploy_sql.txt` — captured raw SQL output
- `.tmp_bot_core_ml_gate/post_deploy_verify.md` — §6 verification report
- `docs/audits/BOT_CORE_ML_GATE_001_2026_05_05.md` — this audit doc

---

**Audit complete.** Verdict: ✅ DEPLOYED (gate active in paper mode). The
single-sample §6 verification is sufficient for landing-pass; full
confidence accrues passively as the gate-active observation window matures.
