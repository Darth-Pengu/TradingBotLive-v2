# FINDING: Market-mode is volumetric, paper≠live regime-eligibility, and HIBERNATE can be a pipeline artifact

**Created:** 2026-06-02 by `MARKET-REGIME-DIAGNOSTIC-001`
(`docs/audits/MARKET_REGIME_DIAGNOSTIC_001_2026_06_02.md`). Canonical for the topics below.

**Read before:** any V5A flip go/no-go that turns on `market:mode:current`; any reading of `market_health` market mode; any "paper edge → live" projection that involves market regime; any `MARKET-MODE-001` recalibration; any investigation of a "market lull" / "no signals" / low new-token-count condition; any decision relying on governance as a HIBERNATE backstop.

---

## 1. Market mode is VOLUMETRIC, not CFGI-driven
`services/market_health.py:_determine_market_mode` (L266-284) classifies mode from **three volumetric legs, ANDed** (L282): `pumpfun_vol >= pf_thresh AND grad_rate(migrations/hr) >= gr_thresh AND dex_vol >= dex_thresh`, iterating FRENZY→HIBERNATE (`MARKET_MODES` L62-68), falling through to HIBERNATE if no tier clears. **CFGI/sentiment do NOT determine mode** — they feed `sentiment_score` only. Do not reason "cfgi=35 fear → HIBERNATE." HIBERNATE is set by the three volume legs.

Two of the three legs are **weak proxies**, only one is a real measurement:
- `dex_vol` — real (DefiLlama Solana 24h). The trustworthy leg.
- `pumpfun_vol` — **placeholder `dex_vol * 0.15`** (`market_health.py:390`; comment L60 "TODO: PumpPortal stats API"). Never an independent pump.fun measurement. Verify in `market:health`: `pumpfun_vol_estimate == dex_volume_24h * 0.15` confirms the placeholder is still in the path.
- `grad_rate` — Redis `market:migration_count_1h` (written by `signal_aggregator.py:1655` on `migration` signals from signal_listener), default `0.0` when absent (`market_health.py:396`). **This counter is fragile** and is the usual single-leg cause of HIBERNATE.

## 2. The HIBERNATE single-leg veto: a healthy market reads HIBERNATE if the migration counter is starved
Because all three legs must clear, **`grad_rate=0` alone forces HIBERNATE even when `dex_vol` and `pumpfun_vol` are healthy.** On 2026-06-02, dex_vol=$1.753B (clears NORMAL) and pumpfun_vol=$263M (clears AGGRESSIVE), yet mode=HIBERNATE purely because `market:migration_count_1h` was absent (grad_rate=0). The counter uses `INCR`+`EXPIRE(3600)`, so **absence ⇒ literally zero migration events in the last hour** — when that contradicts on-chain reality (graduations were ~350/day on-chain), HIBERNATE is a **misclassification / data artifact, not a market reading**. Diagnostic rule: if `market:mode:current=HIBERNATE` but `dex_volume_24h >= $1B`, suspect a starved migration counter (degraded pipeline), not a dead market. `MISCLASSIFIED ≠ TRADEABLE` though — confirm secondary-market conditions separately.

## 3. AGGRESSIVE_PAPER_TRADING bypasses HIBERNATE for paper; LIVE does NOT respect HIBERNATE either
The only HIBERNATE "skip all signals" gate is `signal_aggregator.py:1741-1746`, gated on **`AGGRESSIVE_PAPER` only (NOT TEST_MODE)**. When `AGGRESSIVE_PAPER_TRADING=true` it bypasses the skip and **downgrades the recorded label to `DEFENSIVE`** (so true-HIBERNATE-bypassed trades masquerade as `DEFENSIVE` in `market_mode_at_entry`; the `NORMAL` label is never a downgrade artifact). `bot_core.process_signal` (L615-724) has **no independent HIBERNATE skip** (only governance-mode L674, ML gate, CFGI<10). The documented flip sets `TEST_MODE=false` on **bot_core only**, leaving signal_aggregator's `AGGRESSIVE_PAPER_TRADING=true` → the aggregator keeps feeding HIBERNATE-bypassed signals → **bot_core executes them LIVE**. So a flip in HIBERNATE is **NOT inert; it trades live** (in 2026-06-02 conditions, a starved trickle). To make live HIBERNATE-gated, an operator must set `AGGRESSIVE_PAPER_TRADING=false` on **signal_aggregator** — the runbook does not currently address this.

**Implication for paper→live edge projection:** there is no paper-vs-live *regime-eligibility* gap (live takes the same regimes paper does). When judging whether a paper edge is reachable live, verify the **market-mode-at-entry distribution** of the paper trades — but rely on the `NORMAL` label and on `portfolio_snapshots.market_mode` (which reads `market:mode:current` directly, `bot_core.py:2353`), not on the ambiguous `DEFENSIVE` label. The 2026-05-20..05-28 validation (+8.9 SOL/day, 91.9% WR) ran in genuine NORMAL(1747)/DEFENSIVE(691)/HIBERNATE(0) and is regime-representative. (The cost-fidelity gap, `COST_FIDELITY_GAP.md`, is a *separate* sim-to-real gap that still applies.)

## 4. `market:mode:override` 24h-TTL renewal mechanic
`market_health.py:405-416` reads `market:mode:override`; if present and a valid mode name, it **overrides** the computed mode. It is set with a 24h TTL (per Emergency-Stop / live-flip runbooks: `SET market:mode:override NORMAL EX 86400`) and **must be renewed daily** or it expires and the computed (volumetric) mode governs again. When absent, the computed mode governs. **Do not "fix" a misclassified HIBERNATE by setting an override** — that masks the real defect (a starved counter / crashed pipeline) and re-introduces exactly the regime ambiguity. Fix the pipeline; let the computed mode be correct on its own.

## 5. A "market lull" / "no signals" condition is often a PIPELINE OUTAGE — check service health first
The pubsub `.listen()` loops in `signal_listener` (`_token_subscribe_listener` L335) and `bot_core` (`_emergency_listener`/`_exit_check_listener` ~L2096) run under an **unguarded top-level `asyncio.gather`** (L1395 / ~L2410). A transient `redis.exceptions.TimeoutError` on a pubsub read **crashes the whole process** instead of restarting just that task → crash loop (~6.7s/restart) → Railway deploy goes CRASHED → new-token/migration counters starve → HIBERNATE. On 2026-06-02 BOTH services were CRASHED; the bot had been effectively down since ~2026-05-28T13:00Z (5-day zero-trade gap). **Decisive test for "outage vs lull":** `_portfolio_snapshot_task` (`bot_core.py:2234`) writes a snapshot every ~5 min **unconditionally** — if `portfolio_snapshots` has a multi-hour gap, bot_core is non-functional, not idle. A genuine lull declines smoothly; an outage is an abrupt cliff. Tracked fix: `BOT-CORE-EMERGENCY-LISTENER-PUBSUB-ISOLATION-001` (promoted to flip-blocker, extended to signal_listener) — see `PIPELINE-PUBSUB-ISOLATION-001` in the roadmap.

## 6. How to verify market-mode-at-entry when judging if a paper edge is reachable live
1. `paper_trades.market_mode_at_entry` split — trust `NORMAL` (unambiguous), treat `DEFENSIVE` as possibly-downgraded-HIBERNATE.
2. `portfolio_snapshots.market_mode` over the window — reads `market:mode:current` directly; zero HIBERNATE snapshots ⇒ genuinely-tradeable regime.
3. Cross-check live-state counters (`market:new_token_count_1h`, `market:migration_count_1h`) against an **external** pump.fun launch/graduation rate (dexpaprika `getNetworkPools` solana sort_by=created_at; ~1,500/hr is normal) to detect feed degradation.

---
*Amendments require explicit Jay acknowledgement, recorded inline, originals preserved.*
