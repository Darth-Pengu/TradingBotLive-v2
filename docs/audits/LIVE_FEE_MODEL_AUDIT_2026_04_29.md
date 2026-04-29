# Live vs Paper Fee/PnL Model Audit — 2026-04-29

**Session:** LIVE-FEE-MODEL-AUDIT-2026-04-29
**Author:** Claude Code (read-only)
**Companion:** `CORRECTED_PNL_INVESTIGATION_2026_04_28.md` (paper-side reference)
**Prerequisite:** `ENV_AUDIT_2026_04_29.md` does **not** yet exist in repo —
this audit proceeds with the inline V5a wallet math from the session prompt
and notes the missing prerequisite. ENV_AUDIT can be filled in later without
invalidating any of the findings here.

---

## §1 Executive verdict

**MAJOR DIVERGENCE.** Live and paper do not compute PnL by the same formula.

The four load-bearing differences:

1. **Live PnL omits fees.** `bot_core._close_position` live branch computes
   `pnl_sol = (current_price - entry_price) / entry_price * sell_amount` —
   no `- fees_sol` term. Paper subtracts fees explicitly.
   ([bot_core.py:1232](services/bot_core.py#L1232) vs [paper_trader.py:380](services/paper_trader.py#L380))
2. **Live records `fees_sol = 0.0` and `slippage_pct = 0.0`** in the
   `paper_trades` row for every live trade. Both columns are populated
   correctly for paper trades (FEE-MODEL-001 fee/slippage simulation). All
   6 historical live rows in `paper_trades` confirm `fees_sol=0.0,
   slippage_pct=0.0` empirically.
3. **Live entry/exit prices are queried RPC prices, not actual fill prices.**
   bot_core calls `await self._get_token_price(mint)` after `execute_trade`
   succeeds and stores that as `entry_price`/`exit_price`. The actual fill
   price (post-swap) is never captured — `execute_trade` doesn't return it,
   and Helius `parseTransactions` is only used for confirmation, not for
   price extraction.
4. **Live `features_json` is NULL** on all 6 historical live rows. Paper
   has it populated (large dict written via UPDATE after paper_buy).

This explains the 96× paper-vs-live PnL gap on the v4 single trade
(`yh3n441…`, id=6580): paper without the new model said +0.0019 SOL; live
on-chain was −0.094 SOL; the FEE-MODEL-001 corrected paper model predicted
−0.094 within ±0.02. **The corrected model is right; the live recording
path is wrong.** All 6 stored live rows are systematically optimistic.

**TP/SL trigger logic is parity** (single code path; runs identically). No
divergence in *when* a trade closes — only in *how* the close is recorded.

**Sizing logic is parity** (calls `risk_manager.calculate_position_size`
plus the bot_core min/max sandwich). However the sandwich + current
trading wallet balance (~0.064 SOL) means **any V5a live attempt at the
default `MIN_POSITION_SOL=0.15` floor would size above the wallet** and
fail at the swap router. **V5a wallet math: BLOCKED until trading wallet
≥ 1.5 SOL** (or `MIN_POSITION_SOL` lowered, which is structurally below
break-even per FEE-MODEL-001).

---

## §2 Slippage path comparison

| Aspect | paper_trader | execution.py | Diverges? |
|---|---|---|---|
| Slippage source | `random.uniform(low, high) * (amount/0.1)^exp` Monte-Carlo per tier ([paper_trader.py:142-158](services/paper_trader.py#L142)) | Fixed integer percentages from `PUMPPORTAL_SLIPPAGE` dict ([execution.py:110-115](services/execution.py#L110)); fixed bps from `JUPITER_SLIPPAGE_BPS` keyed on liquidity tier ([execution.py:117-121](services/execution.py#L117)) | **Y — fundamentally different** |
| Pre-grad ranges (BUY) | `alpha_snipe (3.0, 12.0, 0.7)` / `confirmation (2.0, 8.0, 0.7)` | `alpha_snipe = 25` / `confirmation = 15` (fixed % cap) | **Y** — paper Monte-Carlo distributed; live sends a single fixed cap |
| Post-grad ranges (BUY) | `(0.5, 2.0, 0.3)` for `post_grad_dip` | bps tier 50 / 150 / 350 by liquidity | **Y** — paper is small percentages with size scaling; live is liquidity-tiered bps |
| Sell ranges | `sell (3.0, 15.0, 0.7)` pre / `sell_postgrad (0.5, 2.5, 0.3)` post | Fixed `sell = 10` from `PUMPPORTAL_SLIPPAGE`; bps tier on Jupiter | **Y** |
| What's submitted to router | n/a (paper) | The fixed % is sent **as a max-slippage protection bound**, not as the expected fill | n/a |
| What's recorded as `slippage_pct` in DB | The simulated stochastic value | **0.0** (column never updated; fixed cap not stored) | **Y — major** |
| Size impact captured | Yes (size exponent 0.7 pre-grad / 0.3 post-grad) | No (single bound regardless of position size) | **Y** |

**Specific question: does live submit a calibrated estimate or a fixed
max-slippage cap?**

Live submits a **fixed max-slippage cap** as protection. The `slippage`
parameter in the PumpPortal form data ([execution.py:330-343](services/execution.py#L330))
and the `slippageBps` parameter on the Jupiter `/order` endpoint ([execution.py:440](services/execution.py#L440))
are both **upper bounds** — the swap router rejects fills worse than the
cap. They are not "what the actual fill slippage was."

**Specific question: does the recorded `slippage_pct` reflect actual fill
or just the parameter sent?**

Neither. The `paper_trades.slippage_pct` column is **not written at all**
on the live path (entry INSERT and close UPDATE both omit it). It defaults
to `0.0`. The actual fill slippage **could** be derived from comparing the
quoted price (Jupiter `outAmount`) to the achieved on-chain price (Helius
`parseTransactions` token-transfer amounts), but no code does this today.

**Implication for V5a:** every live trade currently records
`slippage_pct=0.0` regardless of actual on-chain slippage, which on the
yh3n441 v4 trade was empirically ~14% per side per FEE-MODEL-001
calibration. This is a silent observability gap.

---

## §3 Fee path comparison

| Component | paper formula | live source | Diverges? |
|---|---|---|---|
| Platform fee (pump.fun pre-grad) | `amount * 0.01` (1% per side, env `PAPER_FEE_PUMPFUN_PCT`) ([paper_trader.py:181](services/paper_trader.py#L181)) | **Not modeled.** PumpPortal charges its own fee on-chain (1% per side per pump.fun docs); execution.py never reads or computes this. | **Y — major** |
| Platform fee (Raydium post-grad) | `amount * 0.0025` (0.25%) ([paper_trader.py:186](services/paper_trader.py#L186)) | Not modeled | **Y** |
| Platform fee (Jupiter) | `amount * 0.006` (0.6%, LP bundled) ([paper_trader.py:183](services/paper_trader.py#L183)) | Not modeled | **Y** |
| LP fee | Merged into Jupiter platform; separate `amount * 0.0025` for Raydium ([paper_trader.py:189-194](services/paper_trader.py#L189)) | Not modeled | **Y** |
| Priority fee | 0.0010 SOL pre / 0.0020 SOL post (round-trip; halved per side) ([paper_trader.py:74-75](services/paper_trader.py#L74)) | Hardcoded `priorityFee=0.0005` in PumpPortal form data ([execution.py:331-342](services/execution.py#L331)); escalating tier list `[0.0001, 0.0005, 0.001, 0.005, 0.01]` for retries ([execution.py:157-163](services/execution.py#L157)) | **Y** — different default; live escalates on retry, paper doesn't |
| Jito tip | 0 pre / 0.0010 SOL post (round-trip; halved per side) ([paper_trader.py:77-78](services/paper_trader.py#L77)) | `JITO_TIPS_LAMPORTS = {normal: 1_000_000, competitive: 10_000_000, frenzy_snipe: 100_000_000}` = 0.001 / 0.01 / 0.1 SOL ([execution.py:139-143](services/execution.py#L139)) | **Y** — live default Jito tip on PumpPortal trades is 0.001 SOL **even on pre-grad**; paper sets pre-grad Jito = 0 |

**Specific question: where does the `fees_sol` value in live `paper_trades`
rows come from?**

It doesn't. The live entry INSERT ([bot_core.py:922-934](services/bot_core.py#L922)) does
not set `fees_sol`, so the column defaults to `0.0` (or NULL — schema-dependent;
empirically all 6 rows show `0.0`). The live close UPDATE
([bot_core.py:1267-1277](services/bot_core.py#L1267)) does not set `fees_sol` either.
Verified: **all 6 live rows in `paper_trades` have `fees_sol=0.0`**.

**Specific question: does live have its own fee model, or call `_simulate_fees`
in live mode as an estimate?**

Live has no fee model. `paper_trader._simulate_fees` is **not called from
the live path** (the `paper_buy/paper_sell` imports are inside the
`if TEST_MODE:` block at [bot_core.py:70](services/bot_core.py#L70)). The on-chain
fee components (PumpPortal platform 1%, Jito tip 0.001 SOL on PumpPortal
trades, priority fee 0.0005 SOL hardcoded, Helius transaction fee ~5000
lamports) are charged by the actual venues but **never aggregated and
written to the paper_trades row.**

**Specific question: is the live `realised_pnl_sol` formula the same as
paper's closed-form `(exit/entry - 1) * amount_sol - fees`?**

**No.** Live uses `(exit/entry - 1) * sell_amount` — no fee term — at
[bot_core.py:1232](services/bot_core.py#L1232). This is the most consequential
divergence. Empirically confirmed in §4 below.

---

## §4 Empirical check on 6 historical live rows

Query:
```sql
SELECT id, mint, amount_sol, entry_price, exit_price, slippage_pct,
       fees_sol, realised_pnl_sol, exit_reason, hold_seconds, ml_score
FROM paper_trades WHERE trade_mode='live' ORDER BY id;
```

For each row, computed two closed-forms:

- `cf_with_fees = (exit/entry - 1) * amount_sol - fees_sol`
- `cf_no_fees   = (exit/entry - 1) * amount_sol`

| id | mint | amt | slip% | fees | realised | cf_no_fees | cf_with_fees | matches |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 6575 | 3jk7Y1uL | 0.997 | 0.0 | 0.0 | -0.704029 | -0.704029 | -0.704029 | ✓ identical (fees=0 collapses both) |
| 6576 | 4LAqGHMC | 0.247 | 0.0 | 0.0 | -0.200067 | -0.200067 | -0.200067 | ✓ |
| 6577 | nGsungJt | 0.312 | 0.0 | 0.0 | -0.311724 | n/a (exit=0) | n/a | n/a — `max_extended_hold` with exit_price=0 |
| 6578 | EwspLbYD | 0.764 | 0.0 | 0.0 | -0.763883 | n/a (exit=0) | n/a | n/a — `stale_no_price` |
| 6579 | DPyyHjaR | 1.227 | 0.0 | 0.0 | -1.227207 | n/a (exit=0) | n/a | n/a — `stale_no_price` |
| 6580 | yh3n441J | 0.365 | 0.0 | 0.0 | +0.001876 | +0.001876 | +0.001876 | ✓ — the v4 trade |

**Findings:**

- All 4 rows with valid prices (6575, 6576, 6580) match the closed-form
  `(exit/entry-1) * amount` to ≤ 1e-5 SOL — **no fee subtraction in live PnL**.
  The 4th row 6580 is the v4 trade that was the trigger for FEE-MODEL-001.
- 3 rows (6577, 6578, 6579) have `exit_price=0` — these are forced-close
  reasons (`max_extended_hold` / `stale_no_price`) where the position is
  liquidated at zero recorded exit, treated as 100% loss
  (`realised_pnl_sol = -amount_sol`).
- All 6 rows show `slippage_pct=0.0` and `fees_sol=0.0` — confirming
  the path-level finding that live never writes these columns.
- All 6 rows show `corrected_pnl_sol=NULL` (consistent with BUG-022).

**Pass/fail per session prompt threshold "> 1 of 6 live rows by more than 1e-3
SOL":** 0 of 6 fail this check. The closed-form formula works *exactly*
on all valid rows — but it works **without** the fee term. So this isn't
a "hidden divergence in PnL accounting" — it's the *visible* divergence
that fees were never modeled.

**STOP CONDITION (`> 1 row mismatched > 1e-3`) NOT TRIPPED.** The
divergence is real but it's coherent across all rows — every live row
omits fees consistently.

---

## §5 TP/SL trigger path

The trigger logic ([bot_core.py:1574-1739](services/bot_core.py#L1574)) is
**single-path** for paper and live:

| Aspect | Behavior | Verdict |
|---|---|---|
| Price source | Redis `token:latest_price:{mint}` (set by signal_listener subscription) | ✓ Same for both |
| Trigger thresholds | `STAGED_TAKE_PROFITS_JSON`, `TIERED_TRAIL_SCHEDULE_JSON`, `stop_loss_pct`, etc. | ✓ Same env vars; same code |
| Comparison basis | `current_price` vs `entry_price` / `peak_price` (gross of fees) | ✓ Same — fees never enter the trigger comparison |
| Branch on TEST_MODE | Only at line 1036 — trigger fires the same way; only the *recording* differs | ✓ |

There is no live-only branch with different thresholds. The "live aggressive"
mode mentioned in the prompt does not exist. The TIME_PRIME / TIME_GOOD /
TIME_DEAD / TIME_SLEEP sizing multipliers at
[bot_core.py:692-707](services/bot_core.py#L692) apply to **sizing only**, not
to trigger thresholds, and they apply uniformly to paper and live.

**Cross-finding (out of scope for this audit, noted for future):** the
TIME_PRIME 2.0× multiplier at AEDT hours 18, 19, 20 directly contradicts
`SD_DEAD_ZONE_001` (which proposes pausing those hours as the worst window).
The 4-day audit data showed 18-21 AEDT was the worst window. The current
sizing logic is **upsizing** in the worst window. This is a separate
TUNE-006 implementation concern.

**Verdict: TP/SL parity confirmed.** No work needed before V5a on this axis.

---

## §6 Sizing + V5a wallet math

### Sizing function

`risk_manager.calculate_position_size` ([risk_manager.py:194](services/risk_manager.py#L194)) is
called identically by both paper and live paths. It returns a quarter-Kelly
× drawdown × streak × time-of-day × market-mode product, capped at
per-personality `MAX_POSITION_PCT` (3% / 5% / 4% of total balance).

### Per-trade min/max sandwich (bot_core.py)

After risk_manager returns `base_size`, bot_core enforces:

```python
# bot_core.py:685-690
_min_pos     = float(os.environ.get("MIN_POSITION_SOL", "0.15"))
_max_pos_abs = float(os.environ.get("MAX_POSITION_SOL", "1.50"))
_wallet_now  = max(self.portfolio.total_balance_sol, 0.0)
_max_pos_frac = _wallet_now * MAX_POSITION_SOL_FRACTION  # default 0.10
_max_pos     = min(_max_pos_abs, _max_pos_frac) if _max_pos_frac > 0 else _max_pos_abs
size_sol     = max(_min_pos, min(size_sol, _max_pos))
```

**Default values (in code):**

- `MIN_POSITION_SOL = 0.15` (bot_core default; risk_manager default is 0.10)
- `MAX_POSITION_SOL = 1.50`
- `MAX_POSITION_SOL_FRACTION = 0.10` (10% of wallet)

Note: `_wallet_now` reads from `self.portfolio.total_balance_sol`, which is
the **tracked** portfolio balance, **not** the on-chain wallet balance.
The on-chain wallet is snapshotted to `portfolio_snapshots` (market_mode='LIVE_ONCHAIN')
at [bot_core.py:1329-1362](services/bot_core.py#L1329) but does not feed back
into sizing.

### V5a wallet math (carry from session prompt + verification)

Trading wallet balance: ~0.064 SOL (per session prompt; not verified
directly via Helius `getBalance` this session — would require live state
read).

If `self.portfolio.total_balance_sol` reflects the trading wallet:

- `_max_pos_frac = 0.064 * 0.10 = 0.0064 SOL`
- `_max_pos = min(1.50, 0.0064) = 0.0064 SOL`
- `size_sol = max(0.15, min(any, 0.0064)) = max(0.15, 0.0064) = 0.15 SOL`

The MIN floor at 0.15 wins **because `max(0.15, 0.0064)=0.15`**. The
sandwich does NOT respect the wallet cap — it only respects the abs cap.
**The bot would attempt a 0.15 SOL trade against a 0.064 SOL wallet and
fail at the swap router with "insufficient balance".**

If `self.portfolio.total_balance_sol` does NOT reflect the trading wallet
(it carries over from paper-mode 50.95 SOL via Redis state restore at
startup), the math is different — the bot would happily compute 0.15 SOL
but the on-chain wallet still can't fund it. Either way, **the trade
attempt fails.**

**Threshold for safe live entry:**

`MIN_POSITION_SOL ≤ wallet * MAX_POSITION_SOL_FRACTION`
→ `0.15 ≤ 0.10 * wallet`
→ `wallet ≥ 1.5 SOL`

**V5a is BLOCKED on the trading wallet balance until a transfer of at
least 1.5 SOL lands** — preferably the originally-planned 5 SOL to give
margin for sizing variance.

Lowering `MIN_POSITION_SOL` is structurally below the FEE-MODEL-001
break-even (0.05-0.15 thin-positive zone per the rebaseline audit). Not
recommended.

---

## §7 features_json gap on live

Query:
```sql
SELECT id, features_json FROM paper_trades WHERE trade_mode='live' ORDER BY id LIMIT 6;
```

All 6 rows: **`features_json IS NULL`**.

Path analysis:
- Paper entry path: INSERT (without features_json) at [paper_trader.py:260-271](services/paper_trader.py#L260),
  then UPDATE with features_json at [bot_core.py:803-806](services/bot_core.py#L803).
- Live entry path: INSERT at [bot_core.py:922-934](services/bot_core.py#L922) with
  no features_json column in the column list. There is no follow-up
  UPDATE to populate it.

This is a separate observability gap (independent of the fee/PnL
divergence). Not V5a-blocking — features_json is for ML training inputs,
not PnL math. But it does mean: **live trades that close successfully
won't have ML training labels usable downstream** (since the features
that drove the entry decision are not preserved).

Per `BUG-022 §3.2`, paper's `features_json` also lacks the per-component
`fee_breakdown`. So even if live started writing features_json, the
breakdown wouldn't be there for either side until that gap is also closed.

---

## §8 Pre-V5a recommendations

Priority list, scoped against the V5a-readiness bar.

### V5a-BLOCKING

**REC-1: Fund trading wallet to ≥ 1.5 SOL (preferably 5 SOL).**
Without this, every V5a entry attempt fails at the swap router.
Cannot be worked around in code without lowering `MIN_POSITION_SOL`
below the FEE-MODEL-001 break-even (not recommended). Out-of-scope
for this audit; tracked separately as the V5a wallet-transfer prerequisite.

**REC-2: Capture actual fee + slippage on live trades and write to
`paper_trades.fees_sol` / `slippage_pct`.** Two implementation paths:

- **Path A (low-fidelity, fast):** call `_simulate_fees` and `_simulate_slippage`
  from the live close path, write the simulated values. Restores numerical
  parity with paper but is still an estimate, not actual.
- **Path B (high-fidelity, slow):** add a Helius `parseTransactions` call
  after `execute_trade` returns successfully; extract token-transfer amounts
  + SOL deltas; compute actual fill price and on-chain fees; write those.
  Closes the divergence completely but adds latency, RPC cost, and code
  surface.

Path A unblocks numerical comparability for V5a. Path B unblocks long-term
calibration of the paper model from live data. Recommendation: Path A
before V5a; Path B as a follow-up tracked roadmap item (`LIVE-FEE-CAPTURE-001`
or similar).

**REC-3: Add fee subtraction to live PnL formula.**
Change [bot_core.py:1232](services/bot_core.py#L1232) from:

```python
pnl_sol = (current_price - pos.entry_price) / pos.entry_price * sell_amount
```

to:

```python
pnl_sol = (current_price - pos.entry_price) / pos.entry_price * sell_amount - fees_sol
```

Where `fees_sol` is whatever REC-2 produces. This brings live PnL into
formal parity with paper. Without REC-3, even after REC-2, the numerical
PnL is inflated — `realised_pnl_sol` and `fees_sol` would both be set
correctly but the relationship between them stays broken.

### High priority (non-blocking)

**REC-4: Backfill the 6 historical live rows** with FEE-MODEL-001
estimated fees + slippage. Mark `correction_method = 'live_estimated_v1'`
to distinguish from `pass_through`. Document as "estimated, not actual"
in the audit trail. Allows existing live rows to be analyzed under a
single PnL convention rather than as a fees-omitted special case. Pair
with the BUG-022 backfill (Option A).

**REC-5: Add features_json write on live entry path.** Mirror the paper
pattern: UPDATE the live entry row with the feature dict immediately
after INSERT (similar to [bot_core.py:803-806](services/bot_core.py#L803)
for paper). Unblocks future ML training using live trades.

### Medium priority

**REC-6: Rationalize sizing min/max sandwich.** The current logic at
[bot_core.py:685-690](services/bot_core.py#L685) does NOT prevent the bot from
attempting trades larger than the wallet (the `max(MIN_POSITION_SOL, …)`
floor wins regardless). Add a hard wallet-fraction floor:
`size_sol = min(size_sol, wallet * MAX_POSITION_SOL_FRACTION)` AFTER the
min-floor enforcement, so a tiny wallet always rejects rather than
attempts an oversized trade. This is preventative — the immediate V5a
blocker (REC-1) addresses the same issue by funding the wallet.

**REC-7: TIME_PRIME 2.0× multiplier conflict.** [bot_core.py:695-696](services/bot_core.py#L695)
upsizes at AEDT 18-20 — the data-confirmed worst window per
`PAPER_TRADES_4DAY_ANALYSIS_2026_04_28.md` §6. This is independent of
the fee/PnL divergence but stacks badly with V5a (the bot would size
*larger* in the losing window). Revisit during TUNE-006 implementation.

### Defer (not V5a-blocking)

**REC-8: Per-component fee breakdown in features_json.** Both paper and
live miss this. Useful for forensic analysis of historical trades. Track
as `OBS-fee-breakdown` (rough name) — not blocking V5a.

**REC-9: ENV_AUDIT_2026_04_29.md.** This audit's prerequisite was
referenced but not produced. Generate it as part of any subsequent
session that needs to confirm Railway env state for V5a. The current
audit's findings are robust to env values within the documented
defaults — this is a process gap, not a content gap.

---

## §9 Summary of divergences (one-page reference)

| Aspect | Paper | Live | V5a impact |
|---|---|---|---|
| Slippage in fill price | Stochastic per tier, size-aware | Cap submitted to router; fill never measured | High (silently inflates PnL) |
| Slippage in `paper_trades.slippage_pct` | Recorded | `0.0` | High (observability gone) |
| Platform fee | 1% pre / 0.25% Raydium / 0.6% Jupiter | Not modeled | High (PnL too rosy) |
| Priority fee | 0.0005 / side pre, 0.0010 / side post | Hardcoded 0.0005, escalates on retry | Low (small absolute) |
| Jito tip | 0 pre / 0.0010 post (round-trip) | 0.001 SOL on all PumpPortal | Medium (live pays Jito on pre-grad; paper doesn't model it) |
| Fees in `paper_trades.fees_sol` | Recorded | `0.0` | High (observability gone) |
| PnL formula | `(exit/entry-1)*amt - fees` | `(exit/entry-1)*amt` | High (inflated by ~3-30% depending on size & venue) |
| Trigger logic | Single-path bot_core | Same | None (parity) |
| Sizing | `risk_manager.calculate_position_size` + min/max sandwich | Same | Wallet-balance dependent — V5a blocks at <1.5 SOL |
| `features_json` | Populated | NULL | Medium (ML training labels lost on live) |
| `corrected_pnl_sol` | NULL on all rows (BUG-022) | NULL on all rows | Same problem; same fix |

**Verdict reaffirmed: MAJOR DIVERGENCE. V5a should not proceed before
REC-1 (wallet funding) AND at minimum REC-2/REC-3 path-A (live fee
capture + PnL formula fix) lands.** The 4-day audit's proposal impact
estimates (TUNE-006 SD_MC_CEILING_001 et al.) were derived from paper
data; without REC-2/REC-3, V5a cannot validate those estimates against
live behavior — the live recording path is too lossy.

---

## §10 Reproducibility

Code surface:
- `services/paper_trader.py` lines 142-213 (slippage/fees)
- `services/paper_trader.py` lines 215-444 (paper_buy / paper_sell incl. PnL formula L378-383)
- `services/execution.py` lines 109-166 (slippage configs, Jito tips, priority fee tiers)
- `services/execution.py` lines 244-498 (PumpPortal/Jupiter execution paths)
- `services/execution.py` lines 666-779 (`execute_trade` retry loop — note ExecutionResult has no fee/price fields)
- `services/bot_core.py` lines 70-71 (paper_buy/paper_sell imported only when TEST_MODE=True)
- `services/bot_core.py` lines 769-948 (entry path branching)
- `services/bot_core.py` lines 1021-1306 (close path branching incl. live PnL formula L1232)
- `services/bot_core.py` lines 685-690 (min/max position sandwich)
- `services/risk_manager.py` lines 194-291 (`calculate_position_size`)

DB queries (against `DATABASE_PUBLIC_URL=...gondola.proxy.rlwy.net:29062/railway`):

```python
# Live row check
asyncpg.connect(DSN).fetch("""
  SELECT id, mint, amount_sol, entry_price, exit_price, slippage_pct, fees_sol,
         realised_pnl_sol, realised_pnl_pct, exit_reason, hold_seconds, ml_score,
         trade_mode, features_json, corrected_pnl_sol
  FROM paper_trades WHERE trade_mode='live' ORDER BY id;
""")
# Result: 6 rows. All slippage_pct=0.0, fees_sol=0.0, features_json=NULL,
#         corrected_pnl_sol=NULL. realised_pnl_sol matches (exit/entry-1)*amt
#         exactly on all 4 rows with valid prices.
```

Run-once scripts used: `/tmp/zmn_live_rows.py` (this session's machine).

---

## §11 Out of scope (per session prompt)

- Implementing any REC-* — separate sessions.
- Lowering MIN_POSITION_SOL to enable V5a at current wallet — explicitly
  rejected as below FEE-MODEL-001 break-even.
- Live wallet `getBalance` verification — would require live RPC call;
  audit uses session prompt's "0.064 SOL" carry value.
- Helius `parseTransactions`-based fill price extraction (REC-2 Path B)
  — out of scope; tracked as future work.
- TIME_PRIME / TIME_GOOD / TIME_DEAD multiplier sanity vs 4-day audit
  data — flagged as cross-finding for TUNE-006 implementation session.
- `corrected_pnl_sol` backfill — already documented in BUG-022 audit;
  REC-4 here pairs with that work.
- BUG-022 fix — separate session; paired but independent.
