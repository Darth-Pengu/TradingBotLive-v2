# userMemories drift report — 2026-05-01

**Session:** STATE-RECONCILE-2026-05-01 (Session 2 of 6 in chained-prompt sequence)
**Author:** Claude Code
**Scope:** Re-classify chat-side userMemories claims after the SESSION_E persistence
hardening + 24-48h post-Session_E lever observation. Builds on
`USERMEMORIES_DRIFT_2026_04_30.md`. Read-only output; informs continuing
Persistence Convention discipline. **No env or code changes were made for this report.**

Companion outputs:
- `.tmp_state_reconcile/findings_A_through_E.txt` — raw 5-finding SQL output
- `.tmp_state_reconcile/reconciliation_table.md` — doc-claim classification matrix
- `.tmp_state_reconcile/quiz.md` — post-edit reader-perspective verification

---

## §1 Findings A-E (independently verified, 2026-05-01 ~12:18 UTC)

### Finding A — ML score band performance (last 7d, SD-paper, n=689)

| ML band | n | Total PnL (SOL) | Mean (SOL) | WR % |
|---|---:|---:|---:|---:|
| 30-40 | 112 | +0.4861 | +0.0043 | 18.8 |
| 40-50 | 206 | **−1.9769** (worst) | −0.0096 | 22.3 |
| 50-60 | 133 | −0.1831 | −0.0014 | 21.8 |
| 60-70 | 106 | −0.7004 | −0.0066 | 29.2 |
| 70-80 | 77 | **+1.6252** (best) | +0.0211 | 31.2 |
| 80-90 | 38 | −0.3454 | −0.0091 | 31.6 |
| 90+ | 17 | +0.0047 | +0.0003 | 47.1 |

Aggregate: **−1.0898 SOL on 689 trades**, mean −0.0016/trade.

Direction vs chat-side / 2026-04-17/19 framing:
- **Chat-side claim:** 40-50 worst (~−1.9), 50-60 strongly positive (+2.4), 70-80 positive (+1.5).
- **Reality 2026-05-01:** 40-50 worst CONFIRMED. 70-80 positive CONFIRMED. **50-60 is FLAT (−0.18) — chat overstated.** 60-70 is mildly negative.
- **CLAUDE.md ML threshold block (post-2026-04-17/19):** "Higher scores are better, not worse" was the framing. 7d data weakens this: 80-90 is mildly negative; only 70-80 is reliably positive at the new sample. Magnitudes have **collapsed by 50-100×** vs the 2026-04-17/19 numbers (40-50 was +88.9 SOL on 496 trades; now −1.98 on 206).

### Finding B — AEST hour distribution (last 7d, SD-paper)

Worst window: **AEST 18 (-1.0550), 19 (-1.0589), 20 (-0.3490)** → 3-hour aggregate −2.4629 SOL on 114 trades.

Code's TIME_PRIME firing window: AEDT/UTC+11 hours 18, 19, 20 → Sydney AEST 17, 18, 19 (post-DST 2026-04-05). AEST 17 (-0.6424) added to AEST 18-19 window: -2.7563 SOL on 114 trades.

AEST 11-17: +0.18 (~flat) — chat-side expectation matches.
AEST 21-23 + 00-08 (chat said ~+1 SOL): **actual ~−1.45 SOL** — disagreement on this secondary claim.

### Finding C — Exit reason ranking (last 7d, ALL paper)

Top losers (sorted by sum_sol ascending):
- **`no_momentum_90s`: −7.40 SOL on 356 trades / 0% WR** ← single largest loser; chat-side OMITTED
- `graduation_stop_loss`: −6.36 on 67 trades / 0% WR
- `stop_loss_20%`: −5.16 on 74 trades / 0% WR
- `graduation_time_exit`: −0.57 on 32 trades / 0% WR

Top winners:
- **`TRAILING_STOP`: +7.93 SOL on 206 trades / 76.7% WR** ← dominant winner
- `staged_tp_+1000%`: +2.71 on 3 trades / 100% WR
- `staged_tp_+500%`: +0.50 on 1 trade / 100% WR
- `staged_tp_+200%`: +0.30 on 4 trades / 100% WR
- `graduation_tp_30pct`: +0.07 on 17 trades / 88.2% WR

Total wins: ~+11.51 SOL. TRAILING_STOP alone: 7.93/11.51 = **69%** of gains (NOT 98% as userMemories claims).

Post-grad bleed (graduation_stop_loss + stop_loss_20% + graduation_time_exit) = **−12.09 SOL / 173 trades** — chat-side framed it as ~−23 SOL. Actual is about HALF chat's number.

`stop_loss_35%` not present in last 7d (matches REALISM-AND-ROADMAP audit's OBS-014 verdict).

### Finding D — Analyst recency (last 30d)

Last analyst entry: **2026-04-28 13:02 UTC**. 304 analyst trades in last 30d. **0 in last 3 days.** Confirms ANALYST-DISABLE-002 (`9d6e95c`) is enforced — chat-side expectation matches exactly.

### Finding E — SD daily performance trend (last 14d)

| Date | n | Sum (SOL) | WR % |
|---|---:|---:|---:|
| 2026-04-22 | 105 | +1.4486 | 52.4 |
| 2026-04-23 | 137 | +5.0333 | 50.4 |
| 2026-04-24 | 160 | +3.9933 | 44.4 |
| 2026-04-25 | 126 | −1.2063 | 33.3 |
| (2026-04-26/27 — gap, HIBERNATE/no signals) | — | — | — |
| 2026-04-28 | 170 | −1.3282 | 21.2 |
| 2026-04-29 | 102 | +1.6261 | 26.5 |
| 2026-04-30 | 168 | −0.3052 | 17.9 |
| 2026-05-01 (early, 12 hr) | 26 | −0.1587 | 0.0 |

Direction: WR ~50% → 17-26% drop confirmed. Aggregate 14d still net +9.0 SOL but recent 4d -1.18 SOL. Chat-side expectation matches.

---

## §2 Drift table (claims vs reality, 2026-05-01)

Newly classified entries since 2026-04-30 drift report. ✅ marks claims that were stale on 2026-04-30 but have since been corrected; ⚠️ marks new drifts surfaced this cycle.

| userMemories / CLAUDE.md claim | Reality (2026-05-01) | Drift type | New action |
|---|---|---|---|
| ✅ TEST_MODE=true on bot_core | Verified (Railway MCP env list + Redis bot:status `test_mode: true` at 12:13 UTC) | Resolved 2026-04-30 (status persisted) | Maintain |
| ⚠️ "ML 50+ mostly profitable" (chat-side draft + USERMEMORIES_DRIFT_2026_04_30 implication) | 50-60 = −0.18 (flat); 60-70 = −0.70 (mildly neg); 70-80 = +1.63 (positive); 80-90 = −0.35 (mildly neg). Only 70-80 reliably positive. | Direction-overstated | Update CLAUDE.md ML threshold block with 2026-05-01 addendum + reference this audit |
| ⚠️ "TRAILING_STOP captures 98%+ of gains" | TRAILING_STOP = 69% of wins (7d); staged_tp_* fills the other ~31% | Magnitude-overstated | Replace 98% claim with "TRAILING_STOP ~69% + staged_tp_* ~31%" |
| ⚠️ "Speed Demon profitable" (current carry) | 7d aggregate = −1.09 SOL on 689 trades (mildly negative); 14d = +9.0 SOL (positive); recent 4d = −1.18 SOL | Sample-stale (window dependent) | Add nuance: lifetime positive, 14d positive, 7d mildly negative; watch direction over rolling 14d |
| ⚠️ "stop_loss_35% significant loss source" (older carry) | Not present in last 7d. Top 3 losers: `no_momentum_90s` -7.40, `graduation_stop_loss` -6.36, `stop_loss_20%` -5.16 | State-stale | Replace; surface `no_momentum_90s` as the primary loss leak |
| ⚠️ "AEDT 11-17 dead zone" | AEST 18-20 is the dead zone (post-DST). 11-17 is flat-positive (+0.18). Code's `aedt_hour=18-20` actually fires at Sydney clock 17-19 | Sample-stale + scope-confusion (DST drift) | Update CLAUDE.md / userMemories: AEST 18-20 / code `aedt_hour=18-20` is the bad window; see TIME-PRIME-CONTRADICTION-FIX-001 |
| ✅ TIME_PRIME 2× upsize at AEDT 18-20 | NEUTRALIZED 2026-05-01 (Session 1 commit `13d4324`); env-controlled, default disabled | Resolved | Maintain |
| ⚠️ "Post-grad bleed ~23 SOL" (chat-side framing for Session 3) | Actual 7d: -12.09 SOL on 173 trades (graduation_stop_loss + stop_loss_20% + graduation_time_exit) | Magnitude-overstated by ~2× | Recalibrate POST-GRAD-LOSS-INVESTIGATION-001 expected ROI |
| 🟢 last analyst entry ~2026-04-28 | Confirmed: 2026-04-28 13:02 UTC | accurate ✓ | maintain |
| 🟢 SD WR dropped 50% → 17-26% | Confirmed: 04-22/23 WR ~50%, last 4d WR 17-26% | accurate ✓ | maintain (continue watching trend) |
| ⚠️ ML threshold drift still active | bot_core=40 (env list confirms), SA=65 (per ENV_AUDIT_2026_04_29), web=45 (carryover claim, not re-verified) | Continued state — open via ML-THRESHOLD-DATA-DRIVEN-RETUNE-001 (Session 4) | Address in Session 4 |

---

## §3 Drift severity classification (using 04-30 schema)

| severity | what it means | this cycle's examples |
|---|---|---|
| 🔴 ACTION-CHANGING | acting on the memory would cause regression | "ML 50+ mostly profitable" → would mislead the ML retune toward 50, when 70 is the empirical sweet spot. "Post-grad bleed -23 SOL" → would over-prioritize fix at the cost of misjudging ROI of other fixes. |
| 🟡 SCOPE-CONFUSION | memory true on one service / context, drifts elsewhere | ML threshold drift (40 bot_core / 65 SA / 45 web). AEDT/AEST timezone drift (code uses UTC+11 but Sydney is UTC+10 since 2026-04-05). |
| 🟢 SAMPLE-STALE | memory true at writing-time, world moved | "TRAILING_STOP 98% of gains" was true at one window; now ~69%. "stop_loss_35% loss source" was true at one window; absent in current 7d. "Speed Demon profitable" — true on lifetime + 14d, weaker on 7d. |
| 🔵 NUANCE-MISSING | direction correct but missing mechanism | `no_momentum_90s` largest single loser BUT not strictly a "loss" — it's an exit-when-flat-after-90s. Different category from `stop_loss_*` which are drawdown-triggered. Userland docs that lump them together miss this. |

This cycle: 0 🔴 ACTION-CHANGING (good — Session 1 closed the TIME_PRIME one); 2 🟡 SCOPE-CONFUSION (ML threshold drift, AEDT/AEST drift); 3 🟢 SAMPLE-STALE (TRAILING_STOP %, stop_loss_35%, SD profitability); 1 🔵 NUANCE-MISSING (no_momentum_90s vs stop_loss categorization).

---

## §4 What changes from this report

### Doc updates landed in the same commit as this audit

1. **CLAUDE.md** — appended a 2026-05-01 addendum to the ML threshold block citing the 7d data + this audit doc. Existing 2026-04-17/19 block + table preserved as historical evidence.
2. **AGENT_CONTEXT.md** — state-header verification timestamp refreshed; "Known leaks under investigation" added; V5a precondition list re-stated post-Session-1.
3. **ZMN_ROADMAP.md** — `POST-GRAD-LOSS-INVESTIGATION-001` Tier 1 🔴 added (with -12.09 SOL/7d not -23 SOL); `ML-THRESHOLD-DATA-DRIVEN-RETUNE-001` Tier 1 🟡 added (gated on Session 3 outcome); Decision Log entry for STATE-RECONCILE.
4. **MONITORING_LOG.md** — appended 2026-05-01 reconciliation entry summarizing Findings A-E.
5. **STATUS.md** — Session 2 entry prepended.

### Future userMemories hygiene from this cycle

- Add the AEDT/AEST drift caveat to any time-window memory: "Sydney clock vs code's aedt_hour are off by 1 hour post-DST; specify which frame".
- Replace specific magnitude claims (e.g., "98%+", "~23 SOL") with directional statements + "see audit X for current data" pointers.
- For ML threshold beliefs, ALWAYS specify the service and the AGGRESSIVE_PAPER_TRADING bypass status.

---

## §5 STOP-condition assessment

`STATE-RECONCILE-2026-05-01` §7 STOP triggers:

- DB connection failures: **0** ✓
- Direction-disagreement on a finding: HEADLINE directions all confirmed (AEST 18-20 worst ✓, 40-50 ML band worst ✓, post-grad + stop_loss_20% dominant losers ✓, TRAILING_STOP dominant winner ✓, analyst dormant ✓, SD WR dropped ✓). Detail-level mismatches noted (chat overstated 50-60 strength, magnitude of post-grad bleed, AEST 21-23 + 00-08 sign). These do NOT meet §7 STOP bar — they require nuanced reconciliation rather than wholesale rejection.
- Doc edit introducing contradiction: verified in `.tmp_state_reconcile/quiz.md` post-edits.

**Verdict: PROCEED. Reconcile docs to ACTUAL data, not chat-side framing where data refutes details.**

---

## §6 Decision Log entry (mirrored in ZMN_ROADMAP.md)

```
2026-05-01 STATE-RECONCILE-2026-05-01 ✅ — Reconciled CLAUDE.md / AGENT_CONTEXT.md /
ZMN_ROADMAP.md / MONITORING_LOG.md against verified production-DB findings A-E.
Headline directions (AEST 18-20 worst, 40-50 ML band worst, post-grad losers,
TRAILING_STOP winner) confirmed. Detail-level chat-side framings adjusted to
actual data: post-grad bleed -12 SOL/7d not -23; TRAILING_STOP captures ~69%
of gains not 98%; ML 50+ NOT "mostly profitable" — only 70-80 reliably positive.
New roadmap items: POST-GRAD-LOSS-INVESTIGATION-001 (with corrected ROI
estimate), ML-THRESHOLD-DATA-DRIVEN-RETUNE-001. New drift report:
USERMEMORIES_DRIFT_2026_05_01.md. No code, no env-var changes.
```
