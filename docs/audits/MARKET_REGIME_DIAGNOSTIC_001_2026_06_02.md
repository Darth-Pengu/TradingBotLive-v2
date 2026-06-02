# MARKET-REGIME-DIAGNOSTIC-001 — the HIBERNATE that halted the flip is a PIPELINE OUTAGE, not a market lull

**Date:** 2026-06-02 (~23:5x Sydney AEST / ~13:4x UTC). **Type:** READ-ONLY investigation. **State writes:** ZERO (no env, no Redis, no DB rows, no override, no redeploy beyond the unavoidable docs-push auto-deploy). Side effects: read queries + this documentation commit.
**Predecessor:** `docs/audits/V5A_FLIP_002_V3R_2026_06_02.md` (NO-FLIP, halted at STOP-M on HIBERNATE + 14 tok/hr; interpreted as "broad memecoin lull, re-attempt when market recovers").
**Method:** Railway env reads, Redis reads, Railway deploy logs + deployment list, asyncpg SELECTs (DATABASE_PUBLIC_URL), source reads with file:line, + a 9-agent workflow (3 independent external corroborators + 6 adversarial verifiers). All six verdicts survived adversarial refutation (confidence 0.88–0.95).

---

## §0 HEADLINE / TL;DR

The predecessor's interpretation is **REFUTED**. The market is **not** in a broad lull — pump.fun is launching **~1,500–2,000 tokens/hr** and graduations are at a **6–7 month high (~350/day)**. The `HIBERNATE` reading is a **misclassification produced by a crashed signal pipeline**: both `bot_core` and `signal_listener` are in a **CRASHED** Railway state, crash-looping on a Redis pubsub-timeout, which starves the migration counter (`market:migration_count_1h` absent → `grad_rate=0` → the sole leg forcing HIBERNATE). The bot has effectively been **down since ~2026-05-28T13:00Z** (5-day zero-trade, zero-heartbeat gap).

The session's central hypothesis — *"the +8.5 SOL/day paper edge may have been generated in HIBERNATE-with-bypass, making it unrepresentative of live"* — is **REFUTED on two independent grounds**: (a) the validation window ran in genuinely-NORMAL/DEFENSIVE regime (zero HIBERNATE snapshots), and (b) live would take HIBERNATE-bypassed trades too (the gate is TEST_MODE-independent), so there is no regime-eligibility gap. **But a more urgent finding replaced it: the bot is currently DOWN.**

**Verdict path: PATH C (HIBERNATE misclassified) + PATH D (flow degraded) — same root cause. Sharpened: the system is DOWN, not hibernating; service restoration is the #1 priority. DO NOT flip into a broken pipeline.** PC4 stays `[ ]`.

| Q | Verdict | Confidence |
|---|---|---|
| Q1 market mode | **HIBERNATE-MISCLASSIFIED** | 0.90 |
| Q2 paper-vs-live gate | **LIVE-TRADES-IN-HIBERNATE** (refutes "flip is inert") | 0.93 |
| Q3 paper trading now | bypass **configured-active but starved** (1 trade/24h) | 0.95 |
| Q4 validation regime | **VALIDATION-WAS-TRADEABLE-REGIME** (PC2 not re-opened) | 0.88 |
| Q5 signal flow | **FLOW-DEGRADED** (dual-service pubsub crash loop) | 0.90 |
| Path | **C + D**, root cause = pubsub crash loop; bot is DOWN | 0.90 |

---

## §1 (Q1) Is the current HIBERNATE volumetrically correct, or misclassified?

**Logic** — `services/market_health.py:266-284` `_determine_market_mode(dex_vol, grad_rate, pumpfun_vol)` requires **all three legs ≥ threshold** (L282 `if pumpfun_vol >= pf_thresh and grad_rate >= gr_thresh and dex_vol >= dex_thresh`), iterating highest→lowest, else falls through to HIBERNATE.

`MARKET_MODES` (`market_health.py:62-68`), columns `(pumpfun_vol_24h_USD, migrations_per_hour, solana_dex_vol_24h_USD)`:
FRENZY (400e6, 200, 4e9) · AGGRESSIVE (200e6, 100, 2e9) · NORMAL (100e6, 30, 1e9) · DEFENSIVE (50e6, 10, 500e6) · HIBERNATE (0, 0, 0).

**Live inputs** (Redis `market:health`, fresh ts 2026-06-02T13:25:57Z):
- `dex_volume_24h` = **1,753,526,743** ($1.753B) → clears NORMAL ($1B) and DEFENSIVE ($500M); a real DefiLlama measurement.
- `pumpfun_vol_estimate` = **263,029,011.45** ($263M). `1,753,526,743 × 0.15 = 263,029,011.45` **exactly** → this is the placeholder `pumpfun_vol_estimate = dex_vol * 0.15` (`market_health.py:390`), **NOT** a real PumpPortal stats call (code comment L60, L386-389). Clears AGGRESSIVE ($200M).
- `grad_rate` = Redis `market:migration_count_1h` → **KEY ABSENT** → default `0.0` (`market_health.py:396-403`).
- `market:mode:override` = **ABSENT** → the computed mode governs.

**Threshold eval with grad_rate=0:** every non-HIBERNATE tier fails *only* on the grad_rate leg (AGGRESSIVE needs ≥100, NORMAL ≥30, DEFENSIVE ≥10; all fail at 0). dex_vol qualifies NORMAL; pumpfun_vol qualifies AGGRESSIVE. **`grad_rate=0` is the SOLE binding constraint.** If `migration_count_1h` were ≥30 → NORMAL; ≥10 → DEFENSIVE.

**Why grad_rate=0 is an artifact, not a market reading:** the counter uses `INCR`+`EXPIRE(3600)`, so total absence ⇒ **literally zero migration events processed in the last 3600s**. That is categorically incompatible with the live on-chain reality (Q5 external: ~350 graduations/day ≈ 14.6/hr; PumpSwap $3.43B/24h + 13.6M txns) and with the bot's own concurrent `dex_vol=$1.75B` + `new_token_count=64–78/hr`. A genuinely dead market does not produce $1.75B DEX volume and 64+ captured new tokens/hr. The cause is the crashed pipeline (Q5), not the market.

**VERDICT Q1: `HIBERNATE-MISCLASSIFIED`.** This is **MARKET-MODE-001 territory promoted to a go-live blocker** — not the old ratio/unit bug, but a pipeline-fragility regression of the same leg.

**Mandatory caveats:**
1. **MISCLASSIFIED ≠ TRADEABLE.** Wrong-label-for-wrong-reason (outage) does not license a flip. Secondary market is genuinely soft (−82% Solana DEX weekly volume, SOL −7.3%/7d, cfgi ~35).
2. **Post-fix mode is uncertain between DEFENSIVE and NORMAL.** With a healthy pipeline, dex_vol ($1.75B≥$1B) + placeholder pumpfun_vol ($263M≥$200M) would clear NORMAL, but the *true* graduations/hr (~14.6) is **below** NORMAL's 30, so the mode could legitimately land at DEFENSIVE. Do not assume "would be NORMAL." Both DEFENSIVE and NORMAL are tradeable bands.
3. **Two of three legs are weak proxies** — `pumpfun_vol` is a placeholder (×0.15 of dex_vol), `grad_rate` is the fragile crash-prone counter; only `dex_vol` is a real measurement. The single-leg veto (a healthy dex_vol fully vetoed to HIBERNATE by one fragile counter) is the deeper design defect; the code comment even admits "Default 0 → falls to HIBERNATE on missing data" — conflating missing-data with dead-market.

Evidence: `.tmp_market_regime/02_mode_classification.md`.

---

## §2 (Q2) Does AGGRESSIVE_PAPER bypass HIBERNATE for paper, and does LIVE respect it?

**The HIBERNATE gate is the only one in the pipeline** — `signal_aggregator.py:1741-1746`:
```python
if market_mode == "HIBERNATE" and not AGGRESSIVE_PAPER:
    continue                      # skip-all
elif market_mode == "HIBERNATE" and AGGRESSIVE_PAPER:
    market_mode = "DEFENSIVE"     # bypass + downgrade LABEL, keep processing
```
`AGGRESSIVE_PAPER` (`signal_aggregator.py:152`) = `os.getenv("AGGRESSIVE_PAPER_TRADING","false")=="true"` — **NOT gated on TEST_MODE** at this site. (The ML-threshold override at L158 *is* `AGGRESSIVE_PAPER and TEST_MODE`; the HIBERNATE bypass is not.)

**bot_core has NO independent HIBERNATE skip** — `bot_core.py:615-724` `process_signal` gates on hourly cap, dup/cooldown, **governance** mode (L674: skip only if `governance:latest_decision.mode ∈ {HIBERNATE,PAUSE}`), personality enablement, max positions, ML gate, CFGI<10 fear. No `market_mode=='HIBERNATE'` skip. The only paper/live split is `if TEST_MODE:` at `bot_core.py:855`.

**Flip topology:** the documented flip sets `TEST_MODE=false` on **bot_core only**; signal_aggregator (separate service) keeps `AGGRESSIVE_PAPER_TRADING=true` and its own `TEST_MODE=true`, and keeps scoring+publishing. Current env (Railway, verified): both services `AGGRESSIVE_PAPER_TRADING=true`, `TEST_MODE=true`.

**Consequence:** after a bot_core-only flip, the aggregator keeps forwarding HIBERNATE-bypassed (DEFENSIVE-labeled) signals; bot_core executes them **LIVE**. Inertness paths all fail: (a) flipping the aggregator's TEST_MODE would NOT restore the skip (it's AGGRESSIVE_PAPER-gated); only `AGGRESSIVE_PAPER_TRADING=false` would, which the runbook does not do; (b) governance is `CONSERVATIVE` (Anthropic 400/credits failure → permissive default), not in {HIBERNATE,PAUSE}; (c) downstream gates throttle but don't reject all — Q3's trade landed today via this exact path.

**VERDICT Q2: `LIVE-TRADES-IN-HIBERNATE`.** The hypothesis premise ("live respects HIBERNATE / flip is inert") is **REFUTED**.

**Mandatory caveats:**
1. **Magnitude:** structurally live-trades-in-HIBERNATE, but currently a **TRICKLE** (~1 signal/24h reaches bot_core) because the degraded pipeline starves volume — not because any gate blocks it. Phrase as "a flip WOULD execute live trades (not inert), at currently very low frequency."
2. **Compounding hazard:** flipping `TEST_MODE` is itself the redeploy trigger that would **revive the CRASHED bot_core** AND switch it live — un-inerting the consumer *and* arming it. Strengthens DO-NOT-FLIP.
3. **Governance veto is dead:** the permissive `CONSERVATIVE` default (LLM credits exhausted, BUG-010) means bot_core has **effectively zero market-regime veto** in live mode right now.

Evidence: `.tmp_market_regime/03_gate_paper_vs_live.md`.

---

## §3 (Q3) Is paper trading right now, despite HIBERNATE + absent override?

`paper_trades` (DB, NOW 13:36Z): entries last 6h = **1**, last 24h = **1**; most recent **id 10926** entry 2026-06-02T12:47:06Z (in HIBERNATE), `realised_pnl_sol=+0.0923`, `market_mode_at_entry='DEFENSIVE'` (the L1746 downgrade fingerprint). Prior row id 10925 = **2026-05-28T09:28Z** (contiguous id → ~5-day gap).

**VERDICT Q3: the AGGRESSIVE_PAPER bypass is configured-active and selected right now** (env `AGGRESSIVE_PAPER_TRADING=true` + live `market:mode:current=HIBERNATE` + the L1744 branch) — a structural fact, not a throughput claim. id 10926's `market_mode_at_entry='DEFENSIVE'` recorded while live mode was HIBERNATE is the bypass's exact fingerprint (a non-bypassed run hits `continue` at L1742 and writes nothing). **But the mechanism is ACTIVE-BUT-STARVED** — the single trade is a 1.5s-hold outlier (the only sub-120s hold among 526 recent closed trades; its exit anomaly is an exit-pipeline matter, not the entry bypass). Cite it as corroborating fingerprint, never as proof-by-throughput. `rejects:2026-06-02=7` (vs 1,982 on 05-28) confirms the bottleneck is upstream signal flow.

Evidence: `.tmp_market_regime/04_paper_now.md`.

---

## §4 (Q4) What regime did the +8.5 SOL/day VALIDATION window (2026-05-20 → 2026-05-28) run in?

**Mode-at-entry IS recorded** (`paper_trades.market_mode_at_entry`; `portfolio_snapshots.market_mode`, which reads `market:mode:current` directly via `bot_core.py:2353`). Caveat: bypassed-HIBERNATE trades are labeled `DEFENSIVE` (Q3) — but `NORMAL` is unambiguous (the bypass only ever synthesizes `DEFENSIVE`, never `NORMAL`; `signal_aggregator.py:1746`).

**Validation data (paper, closed, entry 2026-05-20..05-29)** — reproduced exactly on independent DB query:
| label | n | WR | total_pnl |
|---|---|---|---|
| NORMAL | 830 | 92.2% | +62.555 SOL |
| DEFENSIVE | 236 | 91.1% | +11.645 SOL |
| **OVERALL** | **1066** | **91.9%** | **+74.199 SOL** (8.33d → **8.91 SOL/day**) |

`portfolio_snapshots` in-window: **NORMAL 1747, DEFENSIVE 691, HIBERNATE 0** (last-ever HIBERNATE snapshot was 2026-05-01, 3 weeks before the window; NORMAL snapshots continuous 151–276/day).

**VERDICT Q4: `VALIDATION-WAS-TRADEABLE-REGIME`.** The edge was generated predominantly (78% of trades, 84% of PnL) in genuine NORMAL regime, the remainder in genuine DEFENSIVE; zero HIBERNATE. **PC2 (validation) is NOT re-opened by regime contamination.** The hypothesis is refuted twice: the window was genuinely tradeable AND (per Q2) live would take HIBERNATE trades anyway.

**Mandatory caveats:**
1. **Cost-fidelity gap is orthogonal and NOT refuted** (`docs/findings/COST_FIDELITY_GAP.md`): paper costs ~17.6× too cheap, zero fill latency; the one Path-B truth (id 6580) had paper overstate live by ~96×. **The +8.9 SOL/day is a paper-model hypothesis, NOT a bankable live edge.** Live data overrides.
2. **Stress-test (encouraging, not exonerating):** this window is unusually well-cushioned vs the corpus — median |pnl|≈0.0508 SOL (~2× the corpus-wide 0.0257), median win ~37.9% of position, only ~21.5% of trades inside the ±0.030 corruption band. Applying the full Path-B-derived 24.3% extra round-trip cost: ALL → ~+32.5 SOL / 76.7% WR; NORMAL-only → ~+26.1 SOL / 73.3% WR (only ~15–19% of winners flip). Even pessimistic cost-correction leaves a positive-expectancy, high-WR result — but this remains a hypothesis until live Path-B data confirms.
3. `portfolio_snapshots.market_mode` for the DEFENSIVE bucket is not a fully independent witness (set from the same downgraded `scored_signal['market_mode']` via `bot_core.py:661,2255`); NORMAL is independent. The `signal_aggregator.py:1736` "default NORMAL when key absent" contamination vector did NOT engage during validation (snapshot density proves the key was present throughout).

Evidence: `.tmp_market_regime/05_validation_regime.md`.

---

## §5 (Q5) Is 14/64 new-tokens/hr real, or pipeline degradation?

**Internal:** `signal_listener` crash-loops **~6.7s/restart** (11 starts in 74s) on `redis.exceptions.TimeoutError` in `_token_subscribe_listener` (`signal_listener.py:335`) via an unguarded `asyncio.gather` (`signal_listener.py:1395`). PumpPortal WS IS connected + emitting fresh `new_token` events each cycle, but the ~7s lifespan means migration events rarely reach the aggregator → `market:migration_count_1h` (written by **signal_aggregator.py:1655** on migration signals *from* the listener) stays absent → `grad_rate=0` → HIBERNATE. **Latest Railway deploy of BOTH bot_core AND signal_listener = CRASHED** (13:22:42Z). The identical pubsub-timeout-via-unguarded-gather also crashes bot_core (`bot_core.py:~2410`; `_emergency_listener`/`_exit_check_listener`), independently fatal to position management.

**The cliff (decisive disproof of "lull"):** daily paper entries healthy through 05-28 (69–201/day), then **0/0/0/0** on 05-29→06-01, 1 on 06-02. `portfolio_snapshots` STOP at 2026-05-28T12:57Z — yet `_portfolio_snapshot_task` (`bot_core.py:2234`) writes every ~5 min **unconditionally** of market/trades. **~1,150 missing heartbeats** = process non-functionality, not a quiet market. (Loop-vs-hard-down *within* the 05-28→06-02 gap is inferred — the gap-deployment's logs were REMOVED/purged — but heartbeat-absence proves non-functionality regardless.)

**External (3 independent sources, all `DEGRADED_FEED_LIKELY`, conf 0.8–0.9):** pump.fun launching **~1,500–2,000 pools/hr** (≈1 every ~2s); graduations at a **6–7 month high ~350/day**; PumpSwap $3.43B/24h. The bot feed (~64–78/hr) captures **~3% of reality**. Genuine softness exists but on the *secondary-volume* axis (Solana DEX volume −82% over 2 weeks; SOL −7.3%/7d), which modestly reduces trade volume but cannot explain a clean 4-day zero.

**VERDICT Q5: `FLOW-DEGRADED`.**

Evidence: `.tmp_market_regime/06_flow.md`.

---

## §6 VERDICT — recommended go-live path

**PATH C (misclassified) + PATH D (flow degraded), one root cause: the dual-service pubsub-timeout crash loop starves the migration counter, which single-leg-vetoes the mode to HIBERNATE.** Sharpened by adversarial review: **the system is DOWN, not hibernating — service restoration is the true #1 priority.** A `TEST_MODE=false` flip now would feed a broken/degraded pipeline into live execution (and the flip's own redeploy would revive the crashed consumer into live mode). **DO NOT FLIP.**

What this changes vs the predecessor: the V3R NO-FLIP verdict was **correct** (don't flip in HIBERNATE), but its *reason* ("wait for the market to recover") was wrong. The market is fine; the **bot** is broken. "Waiting for the market" would wait forever — the fix is code, not patience.

### Recommended next CC session (for chat-side authoring) — `PIPELINE-PUBSUB-ISOLATION-001` (code + deploy; the real flip-unblocker)
Single lever: **isolate the pubsub `.listen()` loops from the top-level `asyncio.gather` in both `signal_listener` and `bot_core`** so a transient Redis read-timeout restarts only that task (try/except + reconnect-with-backoff loop), not the whole process. This is the already-filed Tier-2 `BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001`, **promoted to a go-live blocker and extended to signal_listener** (`signal_listener.py:335`/`1395`) + bot_core (`bot_core.py:~2096`/`~2410`).
- Scope: ~1 lever, 2 files, no trade-logic change. Compile-check, single push, monitor restart-stability.
- **Acceptance gate before any future flip re-attempt:** after deploy, (1) both services run without the redis-TimeoutError restart loop (Railway deploy status RUNNING, not CRASHED); (2) `market:new_token_count_1h` recovers into the hundreds–thousands/hr (matching the ~1,500/hr external rate); (3) `market:migration_count_1h` is **present and non-trivial**; (4) `market:mode:current` becomes non-HIBERNATE **because all three legs genuinely clear** (verify migration_count, not via a manual `market:mode:override`); (5) `portfolio_snapshots` resume their 5-min cadence.

### Secondary follow-ups (file at Tier 2/3; not blocking the pubsub fix)
- **MARKET-MODE-001-RE-CALIBRATE-002** (Tier 2): the single-leg `grad_rate` veto conflates missing-data with dead-market. Options: (a) treat absent `migration_count_1h` as a sentinel (don't force HIBERNATE when dex_vol clears NORMAL and the counter is merely missing); (b) recalibrate grad thresholds to current baseline (~14.6 graduations/hr would otherwise top out at DEFENSIVE); (c) replace the `pumpfun_vol = dex_vol*0.15` placeholder (`market_health.py:390`) with a real PumpPortal/dexpaprika pump.fun stats call. Do NOT do this *instead of* the pubsub fix — a recalibration on top of a crashed listener still reads a starved counter.
- **GOVERNANCE-LLM-CREDITS (BUG-010)**: governance is failing on Anthropic 400/credits → permissive `CONSERVATIVE` default → bot_core has no market-regime veto in live mode. Relevant if relying on governance as a HIBERNATE backstop.
- **Operational note for the flip runbook:** because the HIBERNATE gate is in signal_aggregator and gated on `AGGRESSIVE_PAPER_TRADING` (not TEST_MODE), the runbook should decide explicitly whether the aggregator's `AGGRESSIVE_PAPER_TRADING` stays `true` during a live flip — leaving it `true` means live trades in any future HIBERNATE; setting it `false` means live is HIBERNATE-gated. This is a deliberate operator choice the current runbook does not address.

**Multiple paths live?** Primarily C+D (pipeline). A *minor* genuine-softness component exists (real −82% secondary-volume contraction) but it is not the cause of the halt and does not by itself argue against a flip once the pipeline is healthy.

---

## §7 STOP register
| STOP | Fired | Note |
|---|---|---|
| STOP-A | no | Railway authed (10 services) |
| STOP-H | no | newest STATUS = expected 2026-06-02 predecessor + addendum; no unexpected post-2026-06-02 session |
| STOP-Scope | no | ZERO state writes (reads only; no override set; only side effect = this docs commit + its auto-deploy) |
| STOP-L | no | local HEAD == origin/main `1a44349` (0/0); re-fetch before push |
| STOP-Claude | no | no limit hit |

## §8 Outputs
- **NEW** this audit. **NEW** `docs/findings/MARKET_REGIME_GAP.md` (standing finding). **UPDATE** `CLAUDE.md` (Standing-findings row), `AGENT_CONTEXT.md` (header + §6/§6.7), `ZMN_ROADMAP.md` (Decision Log + follow-ups). **PREPEND** `STATUS.md`, `MONITORING_LOG.md`. Scratch (gitignored) `.tmp_market_regime/` (PROGRESS + 02–06 + query scripts). Single push; `commit --amend` to backfill hash.
