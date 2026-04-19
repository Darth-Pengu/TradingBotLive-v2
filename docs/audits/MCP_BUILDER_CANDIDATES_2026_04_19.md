# MCP-builder skill — candidate ZMN MCPs to build

> **STATUS (2026-04-19):** This audit's actionable items are consolidated in `ZMN_ROADMAP.md`. Refer there for current status, priority, and dependencies. This doc is retained as evidence / deep-dive detail.


**Author:** Claude Opus 4.7 · **Date:** 2026-04-19 · **Status:** scoping only, no build this session.
**Skill reference:** `.claude/skills/mcp-builder/SKILL.md` (read this session). Recommends TypeScript SDK + Streamable HTTP for remote, stdio for local. Workflow tools vs. comprehensive coverage tradeoff. Stateless JSON over stateful sessions. Pydantic/Zod schemas with examples in field descriptions.

---

## Inventory of "missing" crypto MCPs

These four were flagged in the original tooling-install research but don't exist as community/official MCPs. Each scoping below answers: should we build it, what would it wrap, how big a session, and which ZMN pain point it unblocks.

### 1. PumpPortal MCP — **HIGHEST ROI**

**What it would wrap:** PumpPortal WebSocket + REST (`https://pumpportal.fun/api`).

Endpoints PumpPortal exposes that ZMN currently consumes through ad-hoc Python in `services/signal_listener.py`:
- WS subscribe to new token creates (`createEvent`)
- WS subscribe to per-token trade events (`tokenTrade`)
- REST trade build (`/api/trade-local`) — returns serialized tx bytes
- REST account-state read

**Why an MCP makes sense:** every CC session that wants to "show me the last 10 pump.fun launches" or "what's the current bonding curve state of mint X" currently has to ask me to write a script. With an MCP it's one tool call.

**Pain point unblocked:**
- Re-diagnosis Pain point 1 — diagnosing why specific stop_loss_35% trades died (peak price + trade-by-trade history without paper_trades round-trip)
- Re-diagnosis Pain point 4 — Whale Tracker entry signal becomes a one-call tool: `pumpportal.recent_buyers(mint=X, limit=20)`
- Future micro-live validation — `pumpportal.simulate_trade(mint=X, sol=0.01)` returns expected outcome without on-chain submission

**Session size to build:** 90-120 min for read-only tools (`getTokenStats`, `getRecentTrades`, `getNewLaunches`, `getBondingCurveState`). **Do NOT include trade-build / trade-submit tools** — the trading wallet private key must never be reachable from an MCP per the existing rule.

**Scoping risk:** PumpPortal API is undocumented in places; some endpoints require reverse-engineering from network traffic.

### 2. Jito MCP — **MEDIUM ROI, deferred**

**What it would wrap:** Jito Block Engine REST (`https://mainnet.block-engine.jito.wtf/api/v1`) + bundle submission.

ZMN currently uses Jito for bundle submission in `services/execution.py`. An MCP would expose:
- `getBundleStatus(bundle_id)` — track inflight bundles
- `getRecentTipFloor()` — observe what tip levels are getting included
- `getValidatorList()` — debugging
- `simulateBundle(bundle)` — already exposed via Helius's `simulateBundle` MCP tool, so partial overlap

**Pain point unblocked:**
- Live trial v3+ debugging — currently bundle status is only visible via raw curl + manual ID lookup
- Tip-fee tuning — Helius's `getPriorityFeeEstimate` covers Solana priority fees but not Jito tip floor

**Session size:** 60-90 min. Jito API is publicly documented and well-shaped.

**Scoping risk:** low. But Helius MCP already covers a lot of the diagnostic needs (`simulateBundle`, `getSenderInfo`). May not be worth a dedicated build.

### 3. SocialData MCP — **LOW ROI right now, parked**

**What it would wrap:** SocialData.tools API (`SOCIALDATA_API_KEY` already in env vars) — Twitter/X data for token discovery.

**Why low ROI right now:** ZMN's social filter (`Social Filter, Speed Demon, Option C strict` in `ZMN_ROADMAP.md` item 3) is in the "READY" backlog but blocked behind ML training. Until that ships, an MCP wrapper isn't unblocking anything.

**Pain point unblocked:** Pain point 5 (entry-time risk) — checking Twitter follower count, account age, recent activity for a token's Twitter handle.

**Session size:** 60-75 min. SocialData has reasonably clean docs.

**Scoping risk:** low.

### 4. LetsBonk MCP — **LOW ROI, parked**

**What it would wrap:** LetsBonk launchpad data — competitive landscape with PumpFun.

**Why low ROI:** ZMN trades pump.fun and (post-graduation) Raydium/PumpSwap. LetsBonk volume is a tiny fraction of pump.fun's $50M/day. Not on the critical path.

**Pain point unblocked:** none currently. Diversification away from pump.fun would be a separate strategic decision.

**Session size:** 90 min if API is decent; could be 120+ if reverse-engineering needed.

**Scoping risk:** medium. LetsBonk API less documented than PumpPortal.

---

## Ranked recommendation

If Jay decides to spend a session building an MCP:

1. **PumpPortal MCP** — highest ROI, broadest impact across re-diagnosis pain points.
2. **Sentry SDK integration in services/** (NOT an MCP build) — see optimization plan Tier 2. 30 min, unlocks the Sentry MCP that already exists.
3. **Jito MCP** — only if Helius's coverage proves insufficient during live trial debugging.
4. **SocialData MCP** — pair with the social filter session when it lands.
5. **LetsBonk MCP** — defer indefinitely.

---

## What the mcp-builder skill provides

When the build session happens, the skill provides:
- Project scaffolding (TypeScript SDK or Python SDK depending on choice)
- Reference patterns for `streamable-http` vs `stdio` transport
- Zod / Pydantic schema templates with examples in field descriptions
- "API coverage vs. workflow tools" decision framework
- `mcp_best_practices.md` checklist
- Sample tool-annotation patterns (`readOnlyHint`, `idempotentHint`, etc.)

Per the SKILL.md, the recommended stack is **TypeScript + Streamable HTTP** for remote MCPs (which is what PumpPortal would be — a remote MCP that wraps an external WS API).
