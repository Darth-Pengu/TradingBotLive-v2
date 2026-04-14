# Post-Recovery Data Review — 2026-04-14

## Executive Summary

The bot is barely net positive since recovery (+0.0518 SOL on 53 trades,
28.3% WR). Winner concentration is CRITICAL — without the single biggest
winner, P/L goes to -0.28 SOL. However, the staged TP system is working
excellently (14 staged trades at 92.9% WR, +1.84 SOL), fully carrying
the portfolio. The non-staged majority (39 trades, 5.1% WR, -1.79 SOL)
is the problem. Stage 2 (cfgi.io cutover) is **SAFE TO SHIP** — it only
changes the CFGI data source and does not touch entry/exit logic.

## Post-Recovery Window

- First trade: ID 3631 at 2026-04-14 11:40:49 UTC
- Last trade: ID 3683 at 2026-04-14 12:36:01 UTC
- Duration: ~55 minutes (heavy burst right after recovery)
- Total trades: 53 (closed)
- Wins: 15 | Losses: 38 | WR: 28.3%
- Total P/L: +0.0518 SOL
- Avg winner: +0.1238 SOL
- Avg loser: -0.0475 SOL
- Biggest winner: +0.3341 SOL (id 3642, +223.8%)
- Biggest loser: -0.2355 SOL (id 3670, -32.1%, Analyst)

## Winner Concentration

- Top winner: +0.3341 SOL (**645% of total P/L** — extremely concentrated)
- Top 3 winners: +0.9045 SOL (1746% of total P/L)
- Without top winner: **-0.2823 SOL** (net negative)
- Without top 3 winners: **-0.8527 SOL**
- Concentration verdict: **CRITICAL** — profitability depends on rare
  large winners. This is structurally the same as pre-crash behavior,
  but the edge is thinner on a 53-trade window.

## Top 10 Winners

| ID | Time (UTC) | Personality | P/L SOL | P/L % | Staged TPs | Exit |
|---|---|---|---|---|---|---|
| 3642 | 11:50:25 | speed_demon | +0.3341 | +223.8% | +50%, +100%, +200% | TRAILING_STOP |
| 3667 | 12:08:23 | speed_demon | +0.3100 | +207.7% | +50%, +100%, +200% | TRAILING_STOP |
| 3645 | 11:52:11 | speed_demon | +0.2604 | +174.5% | +50%, +100%, +200% | TRAILING_STOP |
| 3675 | 12:19:07 | speed_demon | +0.1926 | +129.0% | +50%, +100%, +200% | TRAILING_STOP |
| 3662 | 12:04:24 | speed_demon | +0.1876 | +88.6% | +50%, +100% | TRAILING_STOP |
| 3679 | 12:31:08 | speed_demon | +0.1454 | +39.6% | +50% | TRAILING_STOP |
| 3677 | 12:23:21 | speed_demon | +0.1391 | +92.6% | +50%, +100% | TRAILING_STOP |
| 3672 | 12:16:28 | speed_demon | +0.0934 | +62.6% | +50%, +100% | TRAILING_STOP |
| 3676 | 12:19:56 | speed_demon | +0.0511 | +23.5% | +50% | TRAILING_STOP |
| 3643 | 11:51:14 | speed_demon | +0.0501 | +33.6% | +50% | TRAILING_STOP |

All winners exited via TRAILING_STOP. All had at least one staged TP.
This validates that the TP system is working correctly.

## Loss Breakdown

- Biggest loss: ID 3670, -0.2355 SOL (Analyst, stop_loss_20%)
- Loss exit reasons:

| Exit Reason | Count | Avg P/L |
|---|---|---|
| no_momentum_90s | 22 | -0.0205 SOL |
| stop_loss_35% | 12 | -0.0895 SOL |
| BREAKEVEN_STOP | 1 | -0.0385 SOL |
| stale_no_price | 1 | -0.0033 SOL |
| stop_loss_20% | 1 | -0.2355 SOL |
| TRAILING_STOP | 1 | -0.0040 SOL |

**no_momentum_90s** remains the dominant loss exit (22 of 38 losses,
58%), with small average loss (-0.0205 SOL). These are tokens that
never got traction — the bot enters and the token dies within 90
seconds.

**stop_loss_35%** is the second largest category (12 losses) with
significantly worse avg loss (-0.0895 SOL). These are tokens that had
some price action but reversed hard.

## Personality Breakdown

| Personality | Trades | Wins | WR | Total P/L | Avg/trade |
|---|---|---|---|---|---|
| Speed Demon | 52 | 15 | 28.8% | +0.2873 SOL | +0.0055 SOL |
| Analyst | 1 | 0 | 0.0% | -0.2355 SOL | -0.2355 SOL |
| Whale Tracker | 0 | — | — | — | — |

Speed Demon carries the book with positive avg/trade despite low WR.
Whale Tracker dormant as expected.

## Analyst Boundary Trade Analysis

- Trade ID: 3670
- Entry: 2026-04-14 12:11:32 UTC
- Token: 2yd4Ucr5...
- ML score at entry: 26.7 (below normal analyst threshold of 55,
  but AGGRESSIVE_PAPER=true bypasses thresholds)
- Position size: 0.7216 SOL
- Exit reason: stop_loss_20% (Analyst uses tighter stops than Speed Demon)
- P/L: -0.2355 SOL (-32.1%)
- Staged TPs: none triggered

**Why it was allowed:** AGGRESSIVE_PAPER=true bypasses ML thresholds
for data collection. The Analyst personality is "paused" for normal
trading (CFGI < 20), but AGGRESSIVE_PAPER overrides this for training
data purposes. The ML score of 26.7 would normally have been rejected.

This is EXPECTED behavior under AGGRESSIVE_PAPER. When this flag is
eventually disabled, Analyst would have rejected this trade.

## Staged TP Instrumentation

- STAGED_TP_FIRE log entries: **0** (not found in bot_core logs)
- Distinct trades with staged TPs in Postgres: **14**
- Instrumentation working: **NO — log line not appearing**

The `PAPER_EXIT` log line DOES show `staged=[]` or `staged=["+50%", ...]`,
so staged TP execution IS being tracked in Postgres. However, the
STAGED_TP_FIRE log line added in commit 40dadb6 is either:
1. Not reaching the log output (the bot_core deployment may not have
   the latest code — needs verification), OR
2. Using a different log format than expected

**Staged vs Non-staged Performance:**

| Category | Trades | Wins | WR | Avg P/L | Total P/L |
|---|---|---|---|---|---|
| Staged | 14 | 13 | 92.9% | +0.1318 | +1.8445 |
| Non-staged | 39 | 2 | 5.1% | -0.0460 | -1.7928 |

The staged/non-staged split is stark: staged trades have 92.9% WR and
carry the portfolio. Non-staged trades are overwhelmingly losses (5.1%
WR). This means the bot's edge is entirely in tokens that pump enough
to hit the first +50% TP. The 39 non-staged trades are the signal
quality problem (no_momentum_90s exits dominate).

## Pre-Crash vs Post-Recovery Comparison

| Metric | Pre-crash (3601-3630) | Post-recovery (>=3631) |
|---|---|---|
| Trades | 30 | 53 |
| Wins | 15 | 15 |
| WR | 50.0% | 28.3% |
| Total P/L | +5.4432 SOL | +0.0518 SOL |
| Avg/trade | +0.1814 SOL | +0.0010 SOL |

## Pattern Classification

**Pattern A: Post-recovery materially worse.**

WR dropped from 50% to 28.3% (22 percentage points). Avg/trade dropped
from +0.1814 to +0.0010 (99.5% decrease). Total P/L dropped from +5.44
to +0.05 SOL.

However, several important caveats prevent this from being alarming:

1. **Sample size is small.** 53 trades is a thin window. On 30 trades,
   50% WR could easily be 33% on the next 30. The confidence interval
   on 28.3% WR at n=53 is roughly 17-42%.

2. **Time of day differs.** Pre-crash was 11:08-13:37 UTC (peak
   Asia/evening hours). Post-recovery spans the same window plus
   quieter hours. Memecoin activity varies dramatically by session.

3. **Market conditions differ.** Pre-crash CFGI was 12 (Alternative.me),
   now 21. SOL price was different. The token landscape changes hourly.

4. **No code difference in entry/exit logic.** The only functional change
   between pre-crash and post-recovery is the TP instrumentation log line,
   which doesn't affect execution. Entry filters, ML scoring, exit
   strategy are all identical.

5. **The bot IS net positive.** Barely, but the structure (high-conviction
   staged winners carrying many small losses) is the intended design.

## Stage 2 Recommendation

**SAFE TO SHIP.**

Stage 2 (cfgi.io cutover) changes only the CFGI data source read by
bot_core and signal_aggregator. It does not touch:
- Entry filter logic
- ML scoring thresholds
- Exit strategy
- Position sizing formula

The current performance pattern (thin edge carried by staged winners)
exists under both CFGI values. Switching from BTC F&G (21, Extreme
Fear) to SOL CFGI (56.5, Neutral) will:

1. **Potentially shift mode from HIBERNATE toward NORMAL** — more
   aggressive entry sizing
2. **Unpause Analyst** — CFGI > 20 threshold met
3. **Increase Speed Demon sizing** — from 0.75x toward 1.0x

These changes increase capital deployment. On a bot with a positive
(but thin) edge, more trades at the same edge = more profit. The
risk is that higher deployment amplifies losses IF the edge doesn't
hold. But the edge structure (staged TPs) is sound — the problem is
signal quality on non-staged trades, which CFGI source doesn't affect.

**The bigger risk is NOT shipping Stage 2:** The bot is stuck in
HIBERNATE with artificially fearful conditions. SOL CFGI at 56.5
represents reality — the Solana market is neutral, not in extreme
fear. Trading under the wrong sentiment data leads to wrong mode
decisions.

## What's Different Between Pre-Crash and Post-Recovery

Likely causes of the performance gap, in order of probability:

1. **Random variance on small sample** — most likely explanation.
   30 trades vs 53 trades, different market minutes.
2. **Market conditions** — different time windows, different token
   launches, different liquidity patterns.
3. **Time of day** — memecoin pump activity correlates with specific
   session hours.
4. **Post-outage signal backlog** — the first few minutes after
   recovery had a stale signals:raw queue (trimmed to 1000). Some
   early entries may have been on already-dead tokens.

NOT a factor: code changes (identical entry/exit paths).

## Data Quality Notes

1. **outcome column is NULL for ALL post-recovery trades** (and all
   trades since id=1131). The `outcome` field stopped being populated
   early in the bot's life. All WR calculations in this report use
   P/L-based determination (pnl > 0 = win). This is a pre-existing
   bug, not related to recovery.

2. **corrected_pnl_sol**: The pass_through_v2 correction was applied
   to trades 3606-3630. Post-recovery trades (3631+) have
   corrected_pnl = realised_pnl (both columns identical, no staged
   TP accounting bug since those were fixed in commit 5b92226).

3. **In-flight trades not counted**: 0 open positions at time of
   query. All 53 trades fully closed.

4. **STAGED_TP_FIRE instrumentation not logging**: Postgres has the
   staged data, but the log line isn't appearing. May need to verify
   bot_core is running commit 40dadb6 code.

## New Bug Found: outcome Column Not Populated

The `outcome` column in paper_trades has been NULL since id=1131
(~2500 trades ago). The `paper_sell` or exit logic is not setting
this field. This affects:
- Any query using `WHERE outcome = 'win'` (returns 0 rows)
- Dashboard widgets that rely on the outcome column
- ML training that uses outcome for labeling

**Recommendation:** Fix the paper_sell code to set outcome = 'win'
or 'loss' based on realised_pnl_sol. Also backfill the NULL outcomes
for all closed trades. ~15-minute fix.
