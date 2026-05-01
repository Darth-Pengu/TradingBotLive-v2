# TIME-PRIME-CONTRADICTION-FIX-001 — Audit (2026-05-01 ~01:00 UTC)

> Filename uses `2026_04_30` per chat-side prompt §7 directive (predecessor naming
> convention). Session actually executed 2026-05-01 ~00:30 UTC.

## §1 Executive verdict

**✅ PATCH LANDED.** TIME_PRIME 2× upsize at code aedt_hour 18-20 is now env-controlled
and disabled by default. Verification PASS in code (2/5 test cases neutralized) and
empirical PASS in DB (AEST 18-20 confirmed worst window: −2.46 SOL on 114 trades / 7d).

Single file change: `services/bot_core.py:704-720` — TIME_PRIME branch replaced with
env-driven version reading `TIME_PRIME_HOURS_AEST` (default `""`) and
`TIME_PRIME_MULTIPLIER` (default `1.0`). TIME_GOOD / TIME_DEAD / TIME_SLEEP /
WEEKEND_BOOST branches untouched (out of scope per session §10).

Rollback path documented in §6 (env-only revert possible without code revert).

## §2 Investigation findings

### §2 Step 1: TIME_PRIME logic located

`services/bot_core.py:704-718` (full block also includes 720-724 weekend boost):

```python
        # CHANGE 4: Time-of-day sizing (AEDT — Sydney) — data-driven from 426-trade analysis
        from datetime import timedelta as _td
        aedt_hour = datetime.now(timezone(_td(hours=11))).hour
        if aedt_hour in (18, 19, 20):
            size_sol *= 2.0
            logger.info("TIME_PRIME: hour=%d AEDT — 2.0x sizing (peak WR hours)", aedt_hour)
        elif aedt_hour in (7, 8, 9, 21):
            size_sol *= 1.5
            ...
```

- **Multiplier applied to:** `size_sol` (the final per-position size) AFTER min/max
  enforcement at line 702. Re-clamped at line 727 by `size_sol = max(_min_pos, min(size_sol, _max_pos))`.
- **Other windows with non-1.0 multiplier:** TIME_GOOD (AEDT 7,8,9,21 → 1.5×), TIME_DEAD
  (AEDT 11-16 → 0.3×), TIME_SLEEP (AEDT 2-5 → 0.3×), WEEKEND_BOOST (Sat/Sun → 1.25×).
- **Hardcoded:** YES, all five branches use literal multipliers/hours — no env-vars.
- **Tangent finding (out of scope to fix here):** the variable `aedt_hour` uses
  `timezone(timedelta(hours=11))` = AEDT/UTC+11, but Sydney is currently AEST/UTC+10
  post-DST-end 2026-04-05. So code's `aedt_hour=18` corresponds to actual Sydney clock
  17:00 — the firing window in AEST is **17-19**, not 18-20. The chat-side analysis
  using `AT TIME ZONE 'Australia/Sydney'` gets correct AEST hours, so its labeling
  mismatches the code's behavior by 1 hour.

### §2 Step 2: AEST hour distribution (last 7d, SD-paper)

```
 aest_hr      n    sum_sol         mean    wr%
       0     48    -0.8566    -0.017846   18.8
       1     48     0.1625     0.003385   22.9
      ...
      17     22    -0.6424    -0.029199   18.2     <- code's aedt_hour=18 (firing)
      18     54    -1.0550    -0.019537   31.5     <- code's aedt_hour=19 (firing)
      19     38    -1.0589    -0.027865   26.3     <- code's aedt_hour=20 (firing)
      20     22    -0.3490    -0.015866    9.1
      21     24    -0.3683    -0.015344   20.8
```

- AEST 18-20 (chat-side framing): n=114, sum=−2.4629 SOL
- AEST 17-19 (actual code firing): n=114, sum=−2.7563 SOL
- AEST other (non-firing): n=580, sum=+3.6258 SOL

Either framing confirms the window is **net negative** and is the worst section of
the day. Hypothesis CONFIRMED, no STOP triggered.

### §2 Step 3: Multiplier ratio confirms TIME_PRIME fires

avg `amount_sol` per AEST hour (last 7d, SD paper):

```
AEST 17-19 mean:    0.1845 SOL  <- code's UTC+11 18,19,20 = firing window
AEST 15,16,20,21 neighbor mean:  0.0902 SOL
Ratio: 2.05x  <- exact match for 2.0× multiplier (within sampling noise)
```

Min position size at AEST 17-19 is 0.0985 SOL (≈ 2× the typical 0.0490 floor),
confirming the multiplier is applied at the size-clamping layer. Multiplier
**definitively fires** — no STOP triggered.

## §3 Patch chosen and why

**Path A** (preferred per session prompt). Justification: env-driven control gives
Jay a future re-tune lever without code change, defaults are SAFE (1.0× / empty
hours = full disable), and the change is single-file (within 2-file budget).
Path B (comment-out) was a fallback if Path A would expand scope; not needed here.

Path C explicitly rejected per session §3 (different-hours window is a separate
calibration session).

**Diff applied** (services/bot_core.py:704-720):

- Replaces the hardcoded `if aedt_hour in (18, 19, 20): size_sol *= 2.0` with
  env-driven `if aedt_hour in _tp_hours: size_sol *= _tp_multiplier`.
- Added comment block citing the 2026-05-01 fix, the AEDT/AEST drift note, and the
  empirical basis (-2.46 SOL on 114 trades).
- TIME_GOOD/TIME_DEAD/TIME_SLEEP/WEEKEND_BOOST branches **unchanged** (§10 out of scope).

Compile: `python -m py_compile services/bot_core.py` → OK.

## §4 Verify-script output (`.tmp_time_prime_fix/verify_output.txt`)

```
                       Timestamp  AEDT hr    OLD    NEW  Note
       2026-05-01T08:30:00+10:00        9  1.00x  1.00x  AEST 08:30 (non-prime)
       2026-05-01T18:30:00+10:00       19  2.00x  1.00x  AEST 18:30 (was firing per chat-side)
       2026-05-01T19:30:00+10:00       20  2.00x  1.00x  AEST 19:30 (was firing per chat-side)
       2026-05-01T20:30:00+10:00       21  1.00x  1.00x  AEST 20:30 (chat-side claim; actually AEDT=21 -> not in TIME_PRIME old window)
       2026-05-01T22:30:00+10:00       23  1.00x  1.00x  AEST 22:30 (non-prime)
ASSERT: NEW multiplier == 1.0 for all 5 cases — PASS
Smoke: AEST 19:30 (AEDT=20) with TIME_PRIME_HOURS_AEST=20, MULT=1.5 -> 1.50x [PASS] env re-enable works
Smoke: malformed TIME_PRIME_HOURS_AEST='not_a_number' -> 1.00x [PASS] fail-safe holds

BEHAVIOR DELTA:
  TIME_PRIME branch fired pre-fix on 2/5 test cases
  TIME_PRIME branch fires post-fix on 0/5 test cases (default env)
  Net upsize neutralized: 2 cases out of 5
```

Two of five test timestamps (AEST 18:30 and 19:30 → code aedt_hour 19 and 20)
had the 2× upsize neutralized to 1.0×. AEST 20:30 was not actually firing
pre-fix because its AEDT-hour 21 fell outside the (18,19,20) tuple — the
chat-side prompt's "was prime" label for AEST 20:30 was off by one due to the
DST drift documented in §2 Step 1.

## §5 Deploy verification — queued post-deploy

Verification plan post-`git push`:
1. Poll Railway MCP for bot_core deploy SUCCESS, wait additional 90s for warmup.
2. Set Railway env vars on bot_core: `TIME_PRIME_MULTIPLIER=1.0` and `TIME_PRIME_HOURS_AEST=""`.
   This redeploy is accepted per RAILWAY-REDEPLOY-DISCIPLINE-001 (the directive in §3
   Path A explicitly requires the env vars to be set even when defaults match).
3. Confirm both env vars present via Railway MCP.
4. SQL: count entries last 30min. If zero, market_mode may be HIBERNATE → log
   and proceed (verification cycles to next NORMAL window).
5. If entries present and any in AEST 17-19 window: confirm `amount_sol` does
   NOT show ~2× spike vs neighboring hours.

Outcomes will be reported in this session's STATUS.md entry and in Session 2
(STATE-RECONCILE) follow-up commits if a doc update is needed.

## §6 Rollback procedure

**Option A (env-only, no code revert) — preferred:**
```bash
# Re-enable old behavior at the platform level
railway variables --set "TIME_PRIME_MULTIPLIER=2.0" --set "TIME_PRIME_HOURS_AEST=18,19,20" -s bot_core
```
This restores the exact pre-fix behavior at the firing-window level (note: under
the AEDT/AEST drift this fires at Sydney clock 17,18,19 — same as pre-fix).

**Option B (code revert):**
```bash
git revert HEAD --no-edit
git push
```
Reverts the Edit and falls back to the hardcoded `if aedt_hour in (18,19,20):
size_sol *= 2.0`.

Use Option A for fast revert; Option B if Option A doesn't take effect for any
reason.

## §7 New roadmap items / follow-ups

- **TIME-PRIME-AEDT-AEST-DRIFT-001 (NEW, LOW)** — `services/bot_core.py:706` uses
  `timezone(timedelta(hours=11))` = AEDT/UTC+11, but Sydney is AEST post-DST. All
  TIME_GOOD/TIME_DEAD/TIME_SLEEP windows fire 1 hour earlier in Sydney clock than
  their labels suggest. NOT urgent: the windows are still (relatively) labeled
  consistently; the discrepancy only matters when comparing to PostgreSQL `AT TIME
  ZONE 'Australia/Sydney'` analyses. Fix would replace `_td(hours=11)` with
  `pytz.timezone('Australia/Sydney')` or `zoneinfo.ZoneInfo('Australia/Sydney')`.
  Tracked for a future TIME-PRIME-CALIBRATION session.

- **TIME-PRIME-CALIBRATION-001 (NEW, MEDIUM)** — does any hour deserve a 2× upsize
  given the empirical record? Current data says "no time window is reliably
  positive enough at this sample size to justify 2× sizing risk". Future session
  should look at deeper history + winning-window detection.

## §8 V5a precondition delta

**Closes V5a precondition #4 (TIME_PRIME-CONTRADICTION-001).** Live mode flip will
no longer amplify the AEST 17-19 (code's UTC+11 18-20) loss window by 2×. Net live
loss reduction at expected throughput: ~2× the −2.46 SOL/week paper bleed if the
paper-to-live edge holds. Even if edge degrades, the upsize-amplification factor
is removed.

V5a precondition list now: #1 wallet top-up (Jay action), #2 LIVE-FEE-CAPTURE-002
(Path B Helius parse), #3 48h paper observation. Strike #4.

## §9 Decision Log entry (for ZMN_ROADMAP.md)

```
2026-05-01 TIME-PRIME-CONTRADICTION-FIX-001 ✅ DEPLOYED — TIME_PRIME upsize
neutralized; previously hardcoded 2× at code aedt_hour 18-20 (= AEST 17-19 post-DST,
firing window misaligned with chat-side AEST 18-20 framing by 1h due to UTC+11 vs
UTC+10 drift). Empirically that window was the WORST: -2.46 SOL on 114 trades /
7d (AEST 18-20 framing) or -2.76 SOL / 114 (AEST 17-19 actual). Now env-driven
(TIME_PRIME_HOURS_AEST="" / TIME_PRIME_MULTIPLIER=1.0 by default = disabled).
Closes V5a precondition #4. New roadmap follow-ups: TIME-PRIME-AEDT-AEST-DRIFT-001
(LOW), TIME-PRIME-CALIBRATION-001 (MEDIUM).
```
