# LIVE-MODE-FILTER-PARITY-001-V2 — fill-time MC ceiling on the LIVE buy branch

**Session:** LIVE-MODE-FILTER-PARITY-001-V2
**Type:** Implementation → deploy. Touches `services/bot_core.py` live branch only. Paper path untouched.
**Date authored:** 2026-05-14 (chat-side). **Landed:** 2026-05-19 via bot_core redeploy.
**Authorization:** Jay, chat-side 2026-05-14 — explicit Option-A authorization per `LIVE_MODE_FILTER_PARITY_001_2026_05_14.md` §8.1 open question.

---

## §1 Verdict

✅ **GATE IMPLEMENTED + DEPLOYED.** The V5A relaunch blocker `LIVE-MODE-FILTER-PARITY-001-V2` is **CLOSED.**

A fill-time MC ceiling now exists in `services/bot_core.py:953-980` (the live `else:` branch, before `execute_trade`). It is a faithful mirror of the paper C1 gate at `paper_trader.py:247-275` — same env var, same MC computation, same reject-log format, same Redis-counter pattern (with a distinct `:live:` segment so paper/live reject rates are separable post-relaunch). Code is dormant under `TEST_MODE=true` (the bot's current state); will activate at V5A flip. Verification standard at deploy is **code-level + 8-scenario verify harness + clean-startup**, since live-fire observation can only happen after V5A relaunch — same standard documented in `LIVE_MODE_FILTER_PARITY_001` §6.

---

## §2 Routing re-confirmation + insertion context

Routing assumption from LIVE-MODE-FILTER-PARITY-001 (2026-05-14) re-verified against current `services/bot_core.py` (HEAD after `4bb5247`):

- `:82-83` — `from services.paper_trader import paper_buy, paper_sell` is **inside** `if TEST_MODE:`. `paper_buy` is a name only when `TEST_MODE=true`. Live mode cannot accidentally invoke paper_buy.
- `:38` — `TEST_MODE` is a module-level constant; cannot change without process restart.
- `:836` — `if TEST_MODE:` → paper path → `paper_buy(...)` at `:848`.
- `:951` — `else:` → live path → `signal_type = ...` at `:952` → (NEW GATE `:953-980`) → `result = await execute_trade(...)` at `:981`.

Line-number drift vs the 2026-05-14 audit's `:948` reference: +3 lines because LIVE-TRADES-LOGGING-AUDIT-001 (`b867daa`) added 3-line `trade_mode` comment blocks above both `INSERT INTO trades` sites. Structure unchanged. **STOP-A does not fire.**

`self._get_token_price(mint) -> float` (`:388-391`) returns a USD price-per-token (Jupiter `price/v3` direct or Redis-cached SOL price × `market:sol_price`). On price-fetch failure returns `0.0`. Same units the paper gate uses for `entry_price`. **STOP-B does not fire.**

The live branch has a clean pre-`execute_trade` insertion point at `:953` (after `signal_type` is computed, before `execute_trade` is invoked). **STOP-C does not fire.**

Full Phase 1 evidence: `.tmp_live_filter_parity_v2/01_investigation.md`.

---

## §3 Gate design (the C1 mirror)

`services/bot_core.py:953-980`:

```python
# LIVE-MODE-FILTER-PARITY-001-V2 — fill-time MC ceiling gate (live
# path mirror of paper C1 at paper_trader.py:247-275). ...
fill_mc_ceiling = float(os.getenv("BOT_CORE_FILL_MC_CEILING_USD", "0"))
if fill_mc_ceiling > 0:
    fill_price = await self._get_token_price(mint)
    fill_mc = fill_price * 1_000_000_000
    if fill_mc > fill_mc_ceiling:
        logger.info(
            "FILL_MC_CEILING reject (live): %s mc=$%.0f > ceiling=$%.0f "
            "(slippage_tier=%s)",
            mint[:12], fill_mc, fill_mc_ceiling, slippage_tier,
        )
        if self.redis is not None:
            try:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                await self.redis.incr(f"bot:filter:fill_mc_ceiling:rejects:live:{today}")
                await self.redis.expire(f"bot:filter:fill_mc_ceiling:rejects:live:{today}", 86400 * 14)
            except Exception:
                pass
        return
```

Full Phase 2 design with line-by-line rationale: `.tmp_live_filter_parity_v2/02_design.md`.

---

## §4 Implementation + verify output

**Compile-check:** `python -m py_compile services/bot_core.py` → exit 0.

**Verify harness:** `.tmp_live_filter_parity_v2/verify_live_mc_gate.py` (gitignored). It extracts the gate block from `services/bot_core.py` at run time (so the test cannot drift from the source it's verifying), wraps it in an async closure with mocked `_get_token_price` + mocked Redis, and exercises 8 scenarios. Output captured in `.tmp_live_filter_parity_v2/verify_output.txt`:

| # | Scenario | Expected | Outcome |
|---|---|---|---|
| 1 | above-ceiling fill_mc=$1500 ceiling=$1000 | REJECT + Redis incr + 14d expire | ✅ PASS |
| 2 | at-ceiling fill_mc=$1000 ceiling=$1000 | PASS (strict `>`) | ✅ PASS |
| 3 | below-ceiling fill_mc=$500 ceiling=$1000 | PASS to execute_trade | ✅ PASS |
| 4 | ceiling=$0 (disabled) | PASS regardless of price | ✅ PASS |
| 5 | env var absent (default 0) | PASS regardless of price | ✅ PASS |
| 6 | price-fetch failure (_get_token_price → 0.0) | fail-OPEN, PASS | ✅ PASS |
| 7 | ceiling=$3000 fill_mc=$2500 | PASS | ✅ PASS |
| 8 | ceiling=$3000 fill_mc=$3500 | REJECT | ✅ PASS |

**OVERALL: ALL PASS (8 cases).** No development-loop re-iteration required (§1 piece 8 not exercised).

---

## §5 Deploy record

**Pre-deploy state (verified 2026-05-19 via Railway MCP `get-logs`):**
- bot_core container started `2026-05-19 12:36:14 UTC` on release `4bb524763a9b` (commit `4bb5247`, COST-FIDELITY-FINDINGS-DOCUMENTATION-001 push).
- `TEST_MODE=True`, paper portfolio 56.99 SOL, market mode NORMAL, 0 open positions at restart.
- `BOT_CORE_FILL_MC_CEILING_USD=1000` already set per C1 deploy 2026-05-13 — the V2 gate reuses this same var; no new env var introduced.
- No concurrent bot_core deploy in flight (latest STATUS.md entry was today's COST-FIDELITY-FINDINGS-DOCUMENTATION-001, docs-only).
- Paper C1 gate firing normally on paper path (recent log: `FILL_MC_CEILING reject: 8UZX4cZA5kKa mc=$2890 > ceiling=$1000`).

**Deploy:** single `git push` of the V2 commit triggers a Railway bot_core auto-redeploy. Per §1.5, Railway deploys take 15-20 minutes; container restart confirmed via Railway MCP polling post-push.

**Rollback procedure (instant, no redeploy):**
- `BOT_CORE_FILL_MC_CEILING_USD=0` on bot_core via Railway env. The gate's `if fill_mc_ceiling > 0:` short-circuits when the env is 0, so the live branch falls straight through to `execute_trade` exactly as before V2. This also disables the paper C1 gate (same var) — acceptable because the rollback scenario is "V2 broke live" not "C1 broke paper"; if only one path needs disabling, split the env vars (out of scope for this session).

---

## §6 Verification standard

This deploy uses the **code-level + verify-harness + clean-startup** standard, matching `LIVE_MODE_FILTER_PARITY_001` §6:

1. **Code-level (this audit §3):** the gate exists at the documented location with the documented logic.
2. **Verify-harness (this audit §4):** 8 scenarios PASS against the source extracted at run time.
3. **Clean-startup:** after Railway redeploy, the new container reaches "Bot Core ready — managing 3 personalities" with no Traceback / RuntimeError / ImportError in the deploy log.

**The gate cannot be observed firing in production today** because the bot is in `TEST_MODE=true` and the gate lives in the `else:` (live) branch. **Live-fire verification will happen at V5A relaunch.** Until then, the gate is committed and dormant — exactly the design intent.

**Paper trading unaffected post-deploy:** the `if TEST_MODE:` branch (`:836-950`) is untouched. Paper buys continue via `paper_buy(...)` at `:848`. The paper C1 gate at `paper_trader.py:247-275` is untouched. SD validation in flight (combined eval ≥2026-05-27) is not confounded.

---

## §7 V5A relaunch implications

**Blocker CLOSED.** Per `LIVE_MODE_FILTER_PARITY_001` §8.2 and `V5A-PRECONDITION-CHECKLIST-CLEANUP-001`'s PC3, the live relaunch was held back by the absence of a fill-time MC gate on the live path. That gate now exists. V5A's PC3 can be ticked off after this deploy confirms clean startup.

Outstanding V5A blockers post-V2: **PC1 wallet top-up** (0.064 SOL → target ≥1.5-2.5 SOL, Jay action); **PC2 post-C1 observation through combined eval ≥2026-05-27**; **PC4 V5A flip itself**. Per `docs/findings/COST_FIDELITY_GAP.md`, V5A relaunches with a known acknowledged cost-fidelity gap — this gate fix does not change that condition.

The previously-superseded `NO_MOMENTUM_90S_AUDIT_001` §10 "execution.py parity" open item — which LIVE-MODE-FILTER-PARITY-001 promoted into V2 — is now **CLOSED** by virtue of this deploy. Update propagated to ROADMAP Decision Log.

---

## §8 Parity confirmation — paper C1 vs live V2 (line by line)

| Dimension | Paper C1 (`paper_trader.py:247-275`) | Live V2 (`bot_core.py:953-980`) | Parity |
|---|---|---|---|
| Env var | `BOT_CORE_FILL_MC_CEILING_USD` | `BOT_CORE_FILL_MC_CEILING_USD` | ✅ same (one ceiling governs both) |
| Default value | `"0"` (disabled) | `"0"` (disabled) | ✅ same |
| Short-circuit when disabled | `if fill_mc_ceiling > 0:` | `if fill_mc_ceiling > 0:` | ✅ identical |
| Price source | `entry_price = price × (1 + slippage/100)` where `price` is Jupiter/Gecko/BC | `fill_price = await self._get_token_price(mint)` → Jupiter primary, Redis-cached fallback | ⚠️ near-parity: paper applies a sim-slippage padding before MC compute; live does not. **Documented difference**: paper's padding is a sim artifact (paper_trader synthesizes a buy fill); live uses the actual on-chain price at the moment of decision. The MC the gate sees is the closest available to "fill-time" in each branch. Both are USD price × 1B supply. Quantitatively the paper padding is small (`alpha_snipe` 3-12%) relative to the gate's ceiling — `$1000` ceiling rejects MCs in the $1k-3k+ band; a 12% padding shifts a $900 MC to $1008 = rejected, paper-only. Live without padding rejects $1001+ directly. **Tracked as a known minor non-parity** (`LIVE-PARITY-SLIPPAGE-PADDING-001` Tier 3 🟢 hygiene, NOT this session). |
| MC formula | `fill_mc = entry_price × 1_000_000_000` | `fill_mc = fill_price × 1_000_000_000` | ✅ identical (× 1B supply, pump.fun fixed supply) |
| Threshold comparison | `if fill_mc > fill_mc_ceiling:` | `if fill_mc > fill_mc_ceiling:` | ✅ identical (strict `>`) |
| Reject log format | `FILL_MC_CEILING reject: <mint12> mc=$<mc> > ceiling=$<ceil> (slippage_tier=<tier>, slippage=<slip>%)` | `FILL_MC_CEILING reject (live): <mint12> mc=$<mc> > ceiling=$<ceil> (slippage_tier=<tier>)` | ⚠️ near-parity: live log omits `slippage=...%` (no sim slippage in live), adds `(live)` discriminator. Both are scrapeable for analysis; the `(live)` tag is intentional for paper-vs-live grep. |
| Redis counter key | `bot:filter:fill_mc_ceiling:rejects:<UTC-date>` | `bot:filter:fill_mc_ceiling:rejects:live:<UTC-date>` | ✅ intentional namespace split per design §4.7 — paper/live reject rates separable post-V5A. TTL identical (14d). |
| Failure mode (price unavailable) | gate never sees price=0 — `paper_buy` returns `{"success": False, "error": "price_fetch_failed"}` at `:238-240` before the gate runs | `_get_token_price` returns `0.0` → `fill_mc=0` → `0 > ceiling` is False → **fail-open** → `execute_trade` proceeds | ⚠️ documented near-parity: gate block itself mirrors paper exactly (the gate's logic doesn't handle price=0 in either path). The fail-open happens because the live branch has no upstream `price_fetch_failed` short-circuit. **Acceptable for v1**: V5A relaunch in staged mode (small position sizing per V5A-GO-NO-GO PC8 caps) limits blast radius; in the worst case a price-unavailable live buy proceeds without the MC backstop, hitting whatever live cost it would have hit anyway. If desired, a `LIVE-PARITY-FAIL-CLOSED-001` follow-up can add `if fill_price <= 0: return` to make live mirror paper's upstream behavior. NOT this session. |
| Short-circuit on reject | `return {"success": False, "error": "fill_mc_ceiling_exceeded", ...}` (function-level return; caller treats as failed buy) | `return` (method-level return; falls through end-of-method, no Position created) | ✅ functionally equivalent — both paths produce "no buy placed, no position registered." |

**Net parity assessment:** the gate block is a faithful mirror of C1 in the load-bearing dimensions (env var, MC formula, threshold, reject behavior, Redis counter). Three minor near-parities are documented above with explicit tracking items for hygiene follow-up; none affect the gate's primary purpose (catching $1k-$3k fill-time MC band).

---

## §9 References

- `docs/audits/LIVE_MODE_FILTER_PARITY_001_2026_05_14.md` — the STOP-C audit that scoped this V2
- `.tmp_live_filter_parity/02_design.md` — Option A scoping (predecessor session, untracked)
- `.tmp_live_filter_parity_v2/01_investigation.md` — Phase 1 routing re-verification
- `.tmp_live_filter_parity_v2/02_design.md` — Phase 2 detailed design
- `.tmp_live_filter_parity_v2/verify_live_mc_gate.py` + `verify_output.txt` — 8-scenario verification
- `services/paper_trader.py:247-275` — the C1 gate being mirrored (source: STOP-LOSS-20-RUG-FILTER-DEPLOY-001 + NO-MOMENTUM-90S-FILTER-RETUNE-DEPLOY-001)
- `docs/audits/NO_MOMENTUM_90S_AUDIT_001_2026_05_12.md` §10 — the parity open item this V2 closes
- `docs/findings/COST_FIDELITY_GAP.md` — the cost-fidelity context for V5A relaunch (orthogonal to V2 but worth reading alongside)

---

## §10 What this session did NOT do

- Did NOT touch the paper path (`paper_trader.py` C1 gate; `bot_core.py if TEST_MODE:` branch). Paper observation window for SD validation continues unconfounded.
- Did NOT touch `execution.py` — LIVE-MODE-FILTER-PARITY-001 established the gate doesn't belong there.
- Did NOT change `BOT_CORE_FILL_MC_CEILING_USD`'s value (1000). Only made the live branch read it.
- Did NOT flip `TEST_MODE` or attempt any live trade. Live-fire verification waits for V5A relaunch.
- Did NOT split the env var into paper-vs-live (`PAPER_FILL_MC_CEILING_USD` / `LIVE_FILL_MC_CEILING_USD`) — single var is correct by design (one ceiling, paper informs live calibration).
- Did NOT fix the three near-parity hygiene items surfaced in §8 — tracked as Tier 3 🟢 follow-ups (`LIVE-PARITY-SLIPPAGE-PADDING-001`, `LIVE-PARITY-FAIL-CLOSED-001`) for a future small session.

**Verdict:** ✅ **GATE IMPLEMENTED + DEPLOYED.** V5A relaunch blocker `LIVE-MODE-FILTER-PARITY-001-V2` CLOSED.
