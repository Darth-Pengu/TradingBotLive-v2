# V5A go-live decisions — the seven rules governing relaunch

**Status:** standing decisions record. Survivable summary of the chat-side V5A go-live conversation (2026-05-19/20) — kept here in `docs/findings/` (not in dated `docs/audits/`) so it stays discoverable across sessions.

**Author:** Jay (chat-side), captured by Claude in CLAUDE-MD-FINDINGS-INDEX-001 + V5A-GO-LIVE-DECISIONS-RECORD-001.

**One-line:** seven decisions govern the V5A relaunch — daily/cumulative loss tolerance, market-mode check method, flip timing window, first-24h sizing + scale-up rule, observer commitment, plus a sizing graduation ladder and a strategic follow-up filed for autonomous governance.

**Override path:** chat-side with explicit Jay acknowledgement; amendments appended below with date + what changed + rationale (originals preserved for audit trail).

---

## §1 The seven decisions

| ID | Decision area | What was decided | Rationale / notes |
|---|---|---|---|
| **D-S3** | Daily / cumulative loss tolerance | **Daily halt: 1.5 SOL realized loss in 24h** triggers immediate bot halt (`TEST_MODE=true` revert). **Cumulative halt: 3.0 SOL realized loss across the V5A trial** triggers hard revert to paper. | "Realized" loss is the trigger, not unrealized drawdown — open positions can be temporarily underwater within trailing-stop tolerance and still resolve profitably. Daily ceiling ≈ 30% of 5 SOL budget; cumulative ≈ 60% of budget. Both are aggressive-but-not-insane against the cost-fidelity gap (live expected to underperform paper by ~8-12×). |
| **D-S4** | Market regime check at flip-time | **Manual at V5A relaunch.** The flip-time check confirms `market:mode:current` is `NORMAL` (not `DEFENSIVE`) and SOL price isn't mid-flash-crash. NOT delegated to an autonomous governance agent yet. | The autonomous version is the right long-term answer — filed as `GOVERNANCE-AGENT-MARKET-MODE-001` (see §3). For V5A specifically: (a) trust-building exercise — adding an unproven gating agent confounds attribution if anything goes wrong; (b) the agent needs V5A live data to calibrate, so building it pre-relaunch is a chicken-and-egg problem; (c) one manual check over a 48h window is the right cost/benefit at this stage. |
| **D-S5** | Flip timing window | **Wednesday or Thursday AEST evening, 18:00-21:00 Sydney time** (≈ AEST 19:00 ideal = UTC 09:00 AEST / UTC 08:00 AEDT depending on season). | Maps to ramping US trading hours. Memecoin volume peaks during US ET morning-to-afternoon (≈ UTC 13:00-21:00 = AEST 23:00-07:00 next day), so flipping at AEST evening gives 4-6 hours of active observation before peak volume, with Jay awake and watching. **Avoid weekends** (thinner liquidity widens cost-fidelity gap); **avoid Sunday night / Monday morning** (US futures-open flash moves); **avoid Friday after AEST 14:00** (US Friday afternoon chop pattern). |
| **D-S6** | First-24h sizing + scale-up rule | **Conservative trial sizing: `MAX_POSITION_SOL=0.10`, `MAX_SD_POSITIONS=5`.** **NO auto-scale on win-rate.** Sizing graduation is by staged ladder, evidence-based, manual decision at each step. See §2 below for the ladder. | Original suggestion was "scale up if 24h WR >80%." Overruled: 80% WR over a 24-80 trade sample is not statistically robust evidence — random variance at true WR of 65-70% can easily produce 80%+ in small samples. Auto-scaling on WR doubles risk surface (drawdown potential, market impact, kill-switch math) based on noise. Replaced with the §2 staged ladder. |
| **D-S7** | Observer commitment | **Jay watches actively for the first 4-6 hours post-flip**, glances every ~hour for the first 12 hours. Not constant monitoring — "did the bot die / did rollback fire" checking. | Sufficient for the trial's small size and staged structure. |

Two extras complement the matrix:

- **Sizing graduation ladder (§2)** — replaces the WR-trigger auto-scale rule overruled in D-S6.
- **Strategic follow-up filed (§3)** — autonomous governance agent for market-mode classification + broader operational gating.

---

## §2 Sizing graduation ladder

The ladder replaces the WR-trigger auto-scale that D-S6 overruled. Scale by sample-size confidence + cumulative PnL trajectory, not by short-window WR.

| Window | `MAX_POSITION_SOL` | `MAX_SD_POSITIONS` | Trigger to advance |
|---|---|---|---|
| **Hours 0-24** | 0.10 | 5 | Bot functional, no rollback triggers fired, cost gap roughly matches audit prediction (~8-12× live underperformance vs paper). |
| **Day 2-4** | 0.10 | 5 | **Hold here regardless of WR.** Purpose: gather Path B (real on-chain) cost data to start closing the cost-fidelity gap. |
| **Day 5-7** | 0.15 | 5 | Advance only if: first 4 days produced ≥100 closed trades AND cumulative PnL ≥ break-even AND no rollback triggers fired. **Manual decision.** |
| **Week 2** | 0.20 | 7 | Advance only if: week 1 was net profitable AND Path B sample size ≥ 10 rows (the gate `PAPER-FEE-MODEL-CALIBRATION-001` needs). **Manual decision.** Scale by **capital ratio** not by WR alone. |

The principle: scale on **cumulative evidence**, not on **short-window indicators**. WR is a noisy estimator; cumulative PnL trajectory + closed-trade count + Path B sample size is the joint signal that actually tells you the strategy is working as predicted.

Tracked in `ZMN_ROADMAP.md` Tier 1 as `V5A-SIZING-GRADUATION-LADDER-001`.

---

## §3 Strategic follow-up filed: `GOVERNANCE-AGENT-MARKET-MODE-001`

From the D-S4 conversation: the right long-term answer to "why is the market regime check manual" is an autonomous governance agent — not just for market mode but for the broader class of operational gates currently held manually (TTL renewal, regime monitoring, position-sizing graduation, kill-switch threshold tuning).

**Filed as Tier 2** in `ZMN_ROADMAP.md`, **gated on V5A producing live data across ≥2 distinct market regimes** (NORMAL + CAUTIOUS or DEFENSIVE) so the classifier has training signal in both regime states. **Absorbs the existing deferred `MARKET-MODE-001-RE-CALIBRATE-V2`** (linked, not deleted).

The first relaunch is too early to use an autonomous gate (catch-22: needs live data to be trustworthy, can't get that data without relaunching). Governance-agents are the right direction for *all* the manual checks in the V5A operational surface over time — but they earn that trust by being calibrated against live outcomes, not designed in the abstract.

Design happens in a future investigation session, not now. The roadmap entry captures the strategic direction.

---

## §4 Cross-references

- `docs/findings/COST_FIDELITY_GAP.md` — the acknowledged-not-blocking gap that motivates the conservative sizing in D-S6 and the Path-B-data-gathering purpose of Day 2-4.
- `AGENT_CONTEXT.md` §6 V5A preconditions outstanding — the operational checklist these decisions plug into. Section "Decisions (recorded)" points here.
- `docs/audits/LIVE_MODE_FILTER_PARITY_001_V2_2026_05_19.md` — V2 deploy that landed PC3 (technical precondition, separate from these strategic decisions).
- `ZMN_ROADMAP.md` Tier 1 `V5A-SIZING-GRADUATION-LADDER-001` — the §2 ladder filed as a roadmap reference.
- `ZMN_ROADMAP.md` Tier 2 `GOVERNANCE-AGENT-MARKET-MODE-001` — the §3 strategic follow-up.
- `ZMN_ROADMAP.md` Tier 2 `PAPER-FEE-MODEL-CALIBRATION-001` — the cost-gap-closer that gates Week-2 ladder advancement.
- CLAUDE.md "Standing findings — read before related work" — index entry pointing here.

---

## §5 Override path

Decisions in this doc can be amended chat-side with Jay's explicit acknowledgement. Amendments are appended below with date, what changed, and rationale — original decisions preserved.

If decisions conflict with chat-side guidance during a live session, **this doc wins** (per CLAUDE.md "Standing findings" convention) unless Jay explicitly amends it. Default behaviour when in doubt: halt the bot, ask Jay, capture the answer here.

### Amendments

*None yet. First amendment becomes a dated subsection appended below this line.*
