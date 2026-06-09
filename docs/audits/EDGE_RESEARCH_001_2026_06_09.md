# EDGE-RESEARCH-001 — comprehensive edge survey across all data sources/MCPs (what to build, why, paper→live)

**Session:** EDGE-RESEARCH-001 · **Executed:** 2026-06-09 · Author: Claude Code (Opus 4.8) + multi-agent research (survey of 8 sources → adversarial kill/rank → implementation design → credit economics; ~1.7M subagent tokens, 124 live MCP probes).
**Type:** READ-ONLY research + design. No code/env change in this doc (the enabling fix `PAPER-ENTRY-ORACLE-FIX-001` was deployed separately, commit `419d1bc`). Output = this finding + a prioritized, paste-ready roadmap.
**Scope:** every available data source/MCP (Nansen, Helius, Vybe, DexPaprika, CoinGecko, SocialData, Birdeye, DeFiLlama) + the bot's own pipeline + the Bitfoot dataset, surveyed for *real, testable* trading edges for the Solana pre-grad pump.fun sniper.

---

## TL;DR — the honest headline

> **There is no silver-bullet paid-API edge.** The overwhelming majority of recoverable edge is **FREE** and lives in the bot's own pipeline and execution path. Recommended **paid spend: ~$0–5/month.** The popular "smart money buys in the first seconds → follow it" thesis is **structurally dead** at sniper latency. The realistic path to profitability is: **(1)** the measurement fix just deployed (paper is now honest) → **(2)** stop the bot's own self-inflicted losses (free) → **(3)** add cheap on-chain microstructure edges → **(4)** a *selective* post-grad lane, offline-backtested before spending a credit. Each step is validated paper-on-the-honest-oracle → supervised-live (Path-B). **I cannot promise "extremely profitable"** — memecoin markets are adversarial and most strategies lose; but this is the highest-expected-value, lowest-cost, falsifiable path, and the same skepticism that just exposed the fake 91% edge is applied to every candidate below.

**Why "free" dominates:** the binding constraint is the **~25.8% live round-trip cost** (`COST_FIDELITY_GAP`). An edge only matters if it clears that. The biggest cost-clearing levers are *not losing money you already lose*: the bot's own ledger shows `no_momentum_90s` = **−22.19 SOL** (1,095 trades, 0.1% WR) and graduation-path exits = **−15 SOL** (0% WR), plus an execution path that overpays priority fees ~10–2700× and sells against graduated-away pools (the likely 261 historical HTTP-400 sell failures). Fixing those costs $0 and attacks the 25.8% directly.

---

## §1 The enabling fix (already deployed this session)

`PAPER-ENTRY-ORACLE-FIX-001` (commit `419d1bc`, `T_fix=1781009204`, `BOT_CORE_FILL_MC_CEILING_USD→0`) corrected the paper entry oracle (was ~10× deflated → fabricated the fake 91% WR; see `EDGE_PROXY_ARTIFACT_EVAL_001`). **Every paper-test below depends on this** — before the fix, paper PnL was fiction and no edge was falsifiable. Early Phase-2: fresh-row MC ratio **0.117 → 0.56** (artifact defused), bot still trading. **Until ≥7d of honest data accumulates, all paper-derived numbers below are either historical (pre-fix, contaminated) or pending.**

---

## §2 The prioritized roadmap (do in this order)

Each item is a one-lever, paper-first, gated session. **Tier 1 = free + high-confidence; Tier 2 = cheap on-chain; Tier 3 = selective paid / post-grad; Tier 4 = speculative.**

### TIER 1 — free, high-value, do first
| # | Session | What | Why it clears the 25.8% bar |
|---|---|---|---|
| 1 | **FEATURE-PERSIST-001** ⭐ keystone | Persist the full entry-feature vector to `paper_trades.features_json` at INSERT (gate telemetry: bc_progress, BSR, holder_count, velocity, koth_zone, pre_filter, age — computed at filter-time, **currently discarded at close**). One JSONB dump, zero risk. | Not an edge itself — **unlocks ~6 edges (#2,#4,#8,#9,#11,#15) that are un-falsifiable without it.** Nothing should jump ahead of it. |
| 2 | **ML-FLOOR-RETUNE-003** | Re-derive `ML_THRESHOLD_BOT_CORE_SD` on **post-fix honest** data + use monotonic ML rank as the primary entry selector. `ml_score` is cleanly monotonic vs outcome over 7,200 trades (12.6%→86.9% WR); the *ordering* survives de-artifacting (the bug scaled PnL magnitude, not rank). | The single best cost-surviving lever the bot already owns. One env var; the *new* part is re-deriving where the floor sits on honest data. |
| 3 | **GRAD-BYPASS-FIX-001** | Stop the graduation-path quality-gate bypass: `graduation_stop_loss` (n=145, 0% WR, −12.89 SOL) + `graduation_time_exit` (n=79, 0% WR, −2.16 SOL) = **−15 SOL at ~0% WR**. | Second-largest concentrated, fully-attributed loss in the bot's own ledger. Gating the cohort is a multi-SOL swing. |
| 4 | **NO-MOMENTUM-90S-TUNE-001** | Fix the **#1 loss bucket**: `no_momentum_90s` = 1,095 trades, 0.1% WR, **−22.19 SOL** (fires `bot_core.py:2109-2123` when <`SD_EARLY_MIN_MOVE_PCT` at 90s). Either loosen/delay the cut or pre-screen the doomed cohort upstream (needs #1). | Largest single attributed loss. Even halving it is a multi-SOL swing. Threshold-tune variant is testable now; upstream-predictor variant needs #1. |
| 5 | **EXEC-001/002 routing fix** (carryover, now a flip prerequisite) | Refresh BC pool state before every sell so graduated-mid-hold tokens don't sell against a dead BC pool (likely root of the 261 HTTP-400 sell errors). One cheap `getAccountInfo`. | Attacks a **known catastrophic** failure (failed/wrong-pool sells = 5–20% of position), not a marginal saving. **Hard live-flip prerequisite.** |
| 6 | **ML-DEADFEATURE-PRUNE-001** | Prune the ~42 permanently-zero `FEATURE_COLUMNS` (Nansen DRY_RUN-disabled + stubbed) to the ~13 genuinely-populated; denoise the small-n model. | Pure variance reduction, zero signal lost (features already 0). Low risk, sharpens the ML the whole funnel leans on. |
| 7 | **GATES-V5-RECALIBRATE-001** | Outcome-calibrate the hand-set `BSR≥3.0 / holder≥15 / pre_filter≥1.15` thresholds — especially the **<30s age bypass** that lets the freshest snipes (the bread-and-butter) skip ALL three quality gates. Needs #1. | Hand-set thresholds are rarely optimal; BSR/holder are face-valid 2×-weighted features. |

### TIER 2 — cheap on-chain microstructure (Helius, ~1cr/call)
| # | Session | What |
|---|---|---|
| 8 | **EXEC-DYNAMIC-PRIOFEE-001** | Wire the **already-existing-but-dead** `_get_dynamic_priority_fee` (`execution.py:218`, calls Helius `getPriorityFeeEstimate`) into the pre-grad path, which hardcodes `0.0005 SOL` ≈ 10× live "High" in calm markets. Bimodal: saves when calm, pays up when congested so fills don't silently drop. Needs `HELIUS_DAILY_BUDGET>0` (currently 0) for live. |
| 9 | **BC-FILL-VELOCITY-001** | `vSol delta/sec` (rate-of-change of `vSolInBondingCurve`) as a momentum entry gate — the purest on-chain net-inflow measure, **free** (bot already ingests vSol). Orthogonal to price/BSR. Needs #1 + a thin reserves time-series logger. |
| 10 | **DEV-REPUTATION-BLACKLIST-001** | Stateful creator→outcome reputation table (funding cluster + prior launch/rug history) the sniper reads **O(1) from Redis** at entry. Rug avoidance = asymmetric payoff (avoid one −90% = ~3.5× round-trip). **Offline-backtestable on Bitfoot first.** Must be pre-cached (cold creator-history ~110cr/hundreds-of-ms is too slow inline). |
| 11 | **HOLDER-CONCENTRATION-VETO-001** | Hard veto on top-10 concentration / dev-residual-%supply via Helius `getTokenHolders` + `getAccountInfo(supply)`. Removes a −90% rug tail. |
| 12 | **HOLDER-VELOCITY-SHADOW-001** | Distinct-holder-count delta/sec in first 30-60s (organic vs bundle-only). **Shadow-log first** (not historically reconstructable). Redundancy check: if PumpPortal trade events already carry buyer wallets, this is free. |
| 13 | **SOL-REGIME-GATE-001** | Graded intraday SOL-down gate (e.g. SOL_1h<−2% / SOL_24h<−6%) beneath the latched −10%/24h breaker — fresh pump.fun longs are beta-amplified SOL bets. Free (CoinGecko `simple.price` 30-60s into Redis). |

### TIER 3 — selective paid / post-grad (offline-backtest BEFORE spending)
| # | Session | What |
|---|---|---|
| 14 | **NANSEN-POSTGRAD-SM-ANALYST-001** | Nansen's **real** edge (the pre-grad thesis is dead): on *just-graduated* tokens, net SM/fund inflow over 1h/6h + high still-holding%. Post-grad, the label-emptiness vanishes. **Offline-backtest against Bitfoot's 22,288 peak-multiples FIRST (zero credits)**; only if it shows lift, lift `NANSEN_DRY_RUN` for a thin post-grad gate. |
| 15 | **ANALYST-POSTGRAD-DIPBUY-001** | A *slow* post-grad Analyst lane (NOT Speed Demon): Bitfoot 2-filter `top10≥30% + MC $50-300k` + Meteora venue tilt. Post-grad tokens have deeper liquidity (friendlier to 25.8% cost) and a 2x+ target swamps the cost. Offline on Bitfoot's 32,851 outcomes first. |
| 16 | **RUG-FEATURE-REPOPULATE-001** | Repopulate the stubbed-but-designed rug features (`creator_rug_count`, `dev_sold_pct`, `bundle_detected`, `holder_gini`) — code paths exist, 2×-weighted, currently hardcoded defaults. |

### TIER 4 — speculative (measure before building)
17 **EXEC-FILL-LATENCY-PROBE-001** (Helius Sender/staked fastest-landing — *first measure* current fill latency + entry-price-vs-slot sensitivity; could be 1-3% or ~0). · 18 **COPY-TRADE-WALLET-ALLOWLIST-001** (mine profitable sniper wallets *once* offline via Nansen PnL leaderboards ~500-2000cr, follow live via free Helius webhooks). · **JITO-REIMPLEMENT-001** (re-enable MEV-protected submission correctly — `use_jito` is force-disabled; pairs with **EXEC-SLIPPAGE-MEV-001**, the dominant cost lever: tighten the 25%/15% slippage tolerance per pool-depth).

---

## §3 Data-source credit economics (the "what to pay for, and why" answer)

| Source | Recommendation | Monthly cost | What to call |
|---|---|---|---|
| **Helius** | **implement-now-free** | ~$0–5 incremental | `getPriorityFeeEstimate` (1cr) before each `execute_trade`; `getTokenHolders`/`getAccountInfo` (1-10cr) for concentration vetoes; pre-cached creator history. The workhorse. |
| **CoinGecko** | **implement-now-free** | $0 (public MCP) | `simple.price` SOL+BTC every 30-60s → Redis for the regime gate. |
| **Nansen** | **offline-backtest-first** | $0 near-term | **Do NOT call per-signal.** Offline `token_pnl_leaderboard` burst (~500-2000cr one-time) for wallet mining + the Bitfoot SM-flow backtest. Live post-grad gate only if the backtest shows lift. |
| **DexPaprika** | **offline-backtest-first** | $0 (free MCP) | Validate a post-grad screener on Bitfoot's 32,851 corpus first; then live `getNetworkPoolsFilter`/`getPoolOHLCV` for the Analyst lane only. (No pre-grad coverage; 429s after ~5 rapid calls.) |
| **Bitfoot (offline)** | **offline-backtest-first** | $0 | In-repo dataset (`session_outputs/bitfoot_analysis/`): 32,851 post-grad outcomes + 22,288 peak-multiples. The free backtest harness for all post-grad/Nansen edges. |
| **Vybe** | **defer** | $0 | Nothing for the sniper. Tier-gated (code-19 on free plan) for PnL; labels NULL on fresh pump.fun; top-holders 3h-stale. Only if a post-grad lane needs it and Helius is insufficient. |
| **SocialData** | **drop** | $0 | `twitter_followers` already tested = **no edge** (`CLIFF_VYBE_SOCIALDATA_SUPPLEMENT_2026_05_05`); polling-only/3-rpm/~9s latency. Use only the **free** PumpPortal `has_twitter/has_telegram` flags. |
| **Birdeye / DeFiLlama** | **drop** | $0 | Birdeye MCP down; DeFiLlama is post-grad-TVL only (doesn't exist for pre-grad). Not worth auth. |

**Recommended total paid spend: ~$0–5/month** (Helius execution reads on the existing plan). **Free-vs-paid headline: the recoverable edge is overwhelmingly FREE** (internal + execution + cheap-Helius); paid is selective/post-grad only.

### Nansen credit strategy (you asked specifically)
- **Budget:** 10,000 cr/mo ≈ **2,000 calls** (5cr median; CLAUDE.md's "50/day" framing is even tighter, ~1,500/mo).
- **Why per-signal sniper enrichment is wrong — two independent reasons:** **(1) Budget:** ~14 entries/hr ≈ 10,000 signals/mo × 5cr = **~50,000 cr/mo = 5× over budget** (a 2026-05-05 dry-run logged 100,671 would-POST calls in *one day* — naive wiring burns the month in ~2 hours). **(2) Signal:** Nansen labels are assigned *retroactively* from wallet history, so on a 30-90s-old $3-8k token the labeled-smart-money set is **~empty** — a near-constant feature with ~no information at the Speed Demon entry. The production code already concedes this (gates `who_bought_sold` to Analyst/Whale only).
- **Right use:** **(a)** offline wallet-cohort mining (one-time bursts) for a copy-trade allowlist followed *live by free Helius*; **(b)** the offline Bitfoot backtest of SM-flow-at-graduation; **(c)** *if (b) shows lift*, a thin post-grad Analyst gate on a handful of graduations/day (tens of calls/day — fits budget). **Keep `NANSEN_DRY_RUN=TRUE` until a backtest justifies lifting it.**

---

## §4 What NOT to pursue (15 kills — saves money + time)

**Already-tried-dead:** Twitter follower-count (n~5200, no edge, latency-infeasible); pre-grad Nansen smart-money (retroactive labels = empty on fresh tokens). **Tier-gated/empty:** Vybe wallet-PnL (code-19 paywall) + labeled-holders (NULL on fresh pump.fun, 3h-stale). **Duplicative/inferior:** CoinGecko newPools (PumpPortal WS is strictly faster for the same tokens); Vybe Pyth/holder-ts/liquidity-ts (all already free in-process); standalone BTC gate (subsumed by SOL gate). **Latency-infeasible for a sniper:** Twitter mention-velocity (polling-only, 3rpm); Telegram scraper (botted, high build cost). **Not-applicable to pre-grad:** DexPaprika/DeFiLlama as a sniper feed (no DEX pool until graduation); Nansen quant-score (null on small/new). **Anti-edge:** network-congestion gating (pump.fun launches happen *during* congestion → would miss the best tokens); trending-narrative (slow, gameable). **Small-n/survivorship:** standalone Meteora-venue tilt (fold into the post-grad screener, don't isolate).

---

## §5 The paper→supervised-live validation pipeline (the methodology)

Every edge follows the same gated path — **this discipline is the actual product**, because it's what would have caught the fake 91% before it ever justified a flip:

1. **Persist + shadow-log** (free, no behavior change): log the candidate signal per trade (`FEATURE-PERSIST-001` makes this possible). For non-reconstructable signals (holder/BC velocity), shadow-log live without gating.
2. **Offline backtest** where data exists (Bitfoot for post-grad/rug/Nansen edges) — **zero live-credit risk**, kills bad ideas before any spend.
3. **Paper-test on the now-honest oracle:** segment honest closed `paper_trades` (`entry_time > T_fix`) by the signal; require a *monotone, cost-surviving* relationship over a stated sample (≥300-1000 trades) **net of the FEE-MODEL costs**. Held-out 30% confirmation. This is where most candidates will die — and that's the point.
4. **Supervised-live gate:** the survivors flip via `FLIP_NIGHT_PLAYBOOK` at smallest sizing (`MAX_POSITION_SOL=0.10`), validated on **Path-B on-chain truth** (real lamports, not the entry ratio) over ≥20 live closes, revert on net-negative. Live is the only validator that can't be faked.

**Hard prerequisites before ANY live flip** (independent of edges): `EXEC-001/002` routing fix (#5), `MC-CEILING-TRUE-SCALE-REDECIDE-001` (re-derive the fill ceiling on the true scale — it's at 0 now), `ML-CORPUS-QUARANTINE-CUTOFF-001` (the `trades` ML table is poisoned by the pre-fix artifact), and the standard `FLIP_READINESS` §6 config.

---

## §6 Honest expectations + the real "loop"

The research has **converged** — and intellectual honesty (the same that exposed the 91% artifact) means saying so rather than manufacturing more hopeful candidates. The answer is not a secret API; it's: **fix the measurement (done) → stop the self-inflicted losses (free) → add cheap on-chain microstructure → a disciplined post-grad lane → validate everything live in tiny size.** Whether the *sum* of these clears the 25.8% cost into reliable profit is **genuinely unknown** and only live Path-B data will tell — but this is the highest-EV, lowest-cost, fully-falsifiable path, and the failure modes are now instrumented.

The real iterative loop from here is **not more upfront research** — it's the **paper-test→live-validate cadence** above, one edge per session, each either earning its place on honest data or being killed. The next concrete action is **`FEATURE-PERSIST-001`** (the keystone that makes the rest falsifiable), in parallel with `ML-FLOOR-RETUNE-003` accumulating ≥7d of honest post-fix data.

---

## §7 Provenance
Survey workflow `wf_ec006510-a93` (8 source agents, live MCP probes); design/kill workflow `wf_7bcdbf72-0c6` (adversarial kill-and-rank, implementation design, credit economics). Full raw outputs retained in the session task transcripts. Cross-referenced: `EDGE_PROXY_ARTIFACT_EVAL_001_2026_06_09.md`, `COST_FIDELITY_GAP.md`, `BITFOOT_2026_BASELINE_2026_04_23.md`, `CLIFF_VYBE_SOCIALDATA_SUPPLEMENT_2026_05_05.md`, `MARKET_REGIME_GAP.md`.
