# LIVE-FEE-CAPTURE-002 (Path B — Helius parseTransactions) — Audit (2026-05-01)

> Session 5 of 6 in chained-prompt sequence. **Path B deployed; id 6580 backfilled
> to live_actual_v1; on-chain truth match exact (delta 0.000000 SOL).**

## §1 Executive verdict

**✅ DEPLOYED.** New `services/helius_parser.py` helper + bot_core wiring at the
live-close UPDATE path. Falls back to Path A (`live_estimated_v1`) when Helius
parse fails. id 6580 backfilled successfully — `corrected_pnl_sol` updated from
−0.006429 (Path A) to −0.094245 (Path B), matching the on-chain truth exactly.

**V5a parity-of-truth precondition: closed.** Path B is now the authoritative
source for live-row PnL; Path A remains as fallback.

**Single push, single commit.** Files changed: `services/helius_parser.py` (NEW)
+ `services/bot_core.py` (Path B wiring at live-close UPDATE) + audit doc + ZMN_ROADMAP +
AGENT_CONTEXT + STATUS.md.

## §2 Helius response schema findings

### Critical discovery: use `accountData[*].nativeBalanceChange`, NOT `nativeTransfers`

Initial implementation used `nativeTransfers[*]` filtered for our wallet. That field
captures direct user-to-user transfers (e.g., the Jito tip). It does NOT capture
swap proceeds that flow via PDAs (program-derived addresses). For id 6580's exit
signature, `nativeTransfers` showed only −0.001841 SOL (the Jito tip outgoing) — but
the actual wallet net change was +0.280007 SOL (sell proceeds).

Correct approach: `accountData` is an array of per-account net balance changes for the
entire transaction, including PDA-mediated movements. Filter for entries where
`account == TRADING_WALLET_ADDRESS` and sum `nativeBalanceChange`:

```python
for ad in tx.get("accountData") or []:
    if ad.get("account") == TRADING_WALLET:
        native_delta += int(ad.get("nativeBalanceChange", 0) or 0)
```

### Verified field map

For pump.fun bonding-curve trades on id 6580 (signature parsed via `https://api-mainnet.helius-rpc.com/v0/transactions/`):

| Helius field | Use | Notes |
|---|---|---|
| `transactionError` | tx success check | None = success |
| `fee` (top-level) | network fee in lamports | divide by 1e9 for SOL |
| `accountData[*].nativeBalanceChange` | wallet SOL delta (signed) | sum per wallet account; INCLUDES swap proceeds via PDAs |
| `accountData[*].tokenBalanceChanges[*]` | wallet token delta (per mint) | filter `userAccount == TRADING_WALLET`; rawTokenAmount.tokenAmount = signed string |
| `accountData[*].tokenBalanceChanges[*].rawTokenAmount.decimals` | token decimals | typically 6 for pump.fun |
| `nativeTransfers[*]` | direct user-to-user SOL only (e.g. Jito tip) | DO NOT use for swap proceeds — incomplete |
| `tokenTransfers[*]` | token movements between accounts | redundant with accountData.tokenBalanceChanges; either works |
| `slot` / `timestamp` | tx block info | useful for ordering / debugging |
| `instructions[*].programId` | program-level filter | pump.fun = `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` (NOT seen on id 6580 because that signature uses raw nativeTransfers + token program — pump.fun program doesn't appear directly; the type field shows `SWAP` source `PUMP_FUN`) |

For id 6580 entry signature `cG4DC2rV...`:
- `accountData[wallet].nativeBalanceChange` = -374,251,786 lamports (-0.374252 SOL)
- type=SWAP, source=PUMP_FUN, fee=505,000 lamports

For id 6580 exit signature `4bHzZZxa...`:
- `accountData[wallet].nativeBalanceChange` = +280,006,808 lamports (+0.280007 SOL)
- `nativeTransfers[wallet→7FeFBY...]` = -1,840,821 lamports (-0.001841 SOL Jito tip; visible but not the swap proceeds)
- type=SWAP, source=PUMP_FUN, fee=505,000 lamports

Net: -0.374252 + 0.280007 = **-0.094245 SOL** (exact on-chain truth).

### Schema is stable on a 1-row sample

Schema captured for both signatures has identical key shapes (top-level `description`,
`type`, `source`, `fee`, `feePayer`, `signature`, `slot`, `timestamp`, `tokenTransfers`,
`nativeTransfers`, `accountData`, `transactionError`, `instructions`, `lighthouseData`,
`events`). Per `verify-fields-before-coding`, the parser is built against this stable
shape; if a future Helius schema change breaks this, the parser returns None and Path A
fallback kicks in (parse failure is non-fatal).

## §3 Implementation summary

### Files added

- **`services/helius_parser.py`** (NEW) — single async helper `helius_parse_signature(signature, *, timeout_seconds=5.0, retries=2) -> dict | None`. Uses `HELIUS_PARSE_TX_URL` and `TRADING_WALLET_ADDRESS` env vars. Returns dict with `fee_lamports`, `native_delta_lamports`, `token_deltas` (dict mint→raw int), `success`, `parse_method='helius_v1'`, `raw_response_size`. Returns None on rate-limit (after backoff retries), HTTP non-200, malformed response, timeout, or any exception. Honors standing rate-limit rule (1s → 2s → 4s → ... → 60s cap).

### Files modified

- **`services/bot_core.py`** (live-close UPDATE path, around line 1346) — added Path B branch:
  - Import `helius_parse_signature` lazily inside the close handler
  - Call on entry + exit signatures
  - If both return success, override `corrected_pnl_sol` with `(entry.native_delta + exit.native_delta) / 1e9` and set `correction_method='live_actual_v1'`
  - Else fall back to Path A (`live_estimated_v1` with `corrected_pnl_sol = realised_pnl_sol = pnl_sol`)
  - UPDATE statement updated to use `correction_method=$16` parameter (was hardcoded literal)
  - All asyncpg `$N` slots distinct per BUG-022 hotfix lesson

### Files NOT modified

Per session §9 (out of scope): no entry-decision logic changes, no paper-mode rows touched, no live trade execution changes.

### Compile check

```
python -m py_compile services/bot_core.py services/helius_parser.py
COMPILE OK
```

## §4 Verification (verify_path_b.py + id 6580 backfill)

### `.tmp_path_b/verify_path_b.py` output

```
Entry parse: success=True fee=505000 native_delta=-374251786 (-0.374252 SOL)
Exit parse:  success=True fee=505000 native_delta=280006808 (0.280007 SOL)

Computed Path B corrected_pnl_sol: -0.094245 SOL
On-chain truth (per session prompt): -0.094245 SOL
Delta: 0.000000 SOL  (must be < 0.0050 to PASS)

ASSERT |computed - (-0.094245)| < 0.005 — PASS
```

### `.tmp_path_b/backfill_6580.py` outcome (id 6580 in production DB)

BEFORE:
```
corrected_pnl_sol         -0.006429726381478863
correction_method         live_estimated_v1   (Path A)
```

AFTER:
```
corrected_pnl_sol         -0.094244978
corrected_pnl_pct         -25.80072837215694
corrected_outcome         loss
correction_method         live_actual_v1
correction_applied_at     2026-05-01 12:52:37.875775+00:00
```

Delta from on-chain truth: **0.000000 SOL** (exact match within float precision).

The 0.088 SOL gap that Path A missed (Path A said -0.006; truth -0.094) is fully closed by Path B.

## §5 Open issues / what Path B does NOT close

1. **Jito tip accounting on entry.** id 6580's entry shows `nativeTransfers` empty (Jito tip would appear here if applied). The fee field (505k lamports) is the standard network fee, not the Jito tip. Path B's `accountData.nativeBalanceChange` ALREADY incorporates any Jito tip (since the wallet's balance change reflects everything that left the wallet), so this is moot for PnL accuracy. But the `fee_lamports` field returned by the helper does NOT include Jito tip — only network fee. Callers needing Jito-only must compute `native_delta - swap_proceeds`.

2. **parseTransactions edge cases on graduated tokens (Raydium AMM).** Path B was tested only against pump.fun bonding-curve trades. Raydium AMM swaps may use different program IDs in `instructions`. The accountData approach SHOULD work universally (it's program-agnostic — just sums native balance changes for the wallet) but has not been verified against a Raydium trade. Risk mitigated: Path B falls back to Path A on any parse failure (return None semantic).

3. **Parse-failure rate is unknown empirically.** Only one live trade exists (id 6580). When V5a flips, monitor `correction_method` distribution to surface fail rate. If `live_estimated_v1` rate > 5% on live rows, investigate Helius reliability or schema changes.

4. **Sync API call adds latency to live close path.** `await helius_parse_signature(...)` blocks close handler for up to 5s × 3 attempts × 2 sigs = 30s worst case. Typical: <1s per call. If this becomes a problem (close-path latency causing missed exits), an async background-update pattern can be implemented later. Tracked as `LIVE-CLOSE-PATH-B-LATENCY-001` (Tier 2 🟢, low priority absent observed harm).

5. **Path B does NOT compute slippage tier.** It directly produces the PnL without classifying which tier. The `slippage_pct` field still uses Path A's `_simulate_slippage` estimates. If precise slippage attribution is needed, can be derived from Path B fills vs quoted prices. Tracked as `LIVE-PATH-B-SLIPPAGE-DERIVATION-001` (Tier 2 🟢, observability).

## §6 V5a precondition delta

**Closes V5a precondition: LIVE-FEE-CAPTURE-002.** Live mode flip is no longer blocked
on parity-of-truth — `live_actual_v1` is now the authoritative source for live-row PnL,
and Path A serves as fallback (zero-data-loss on parse failure).

V5a precondition list now: ~3 SOL wallet top-up (Jay action), 24-48h paper observation,
Renew Redis daily TTLs, V5a flip itself. Strikes: TIME_PRIME-CONTRADICTION-001 ✅
(Session 1), SD_MC_CEILING_002 ✅ (2026-04-30), MARKET-MODE-001 ✅ (2026-04-30),
**LIVE-FEE-CAPTURE-002 ✅ (this session)**.

## §7 Rollback procedure

If Helius API changes break the parser or unexpected wrong values surface:

```bash
# Code revert (preserves Path A live_estimated_v1 fallback automatically)
git revert HEAD --no-edit
git push
```

The revert restores `correction_method='live_estimated_v1'` hardcode in the UPDATE,
removing Path B from the close path. id 6580 row is unaffected by revert (it's already
backfilled; correction_applied_at preserved).

If only the helper has issues but bot_core wiring is fine, can soft-disable by setting
`HELIUS_PARSE_TX_URL=` (empty) on bot_core — helper returns None immediately, Path A
fallback kicks in.

## §8 Decision Log entry (mirrored to ZMN_ROADMAP.md)

```
2026-05-01 LIVE-FEE-CAPTURE-002 (Path B) ✅ DEPLOYED — Helius parseTransactions
wired into bot_core live-close UPDATE path. New services/helius_parser.py
helper. Verify-fix PASS: id 6580 reconstruction matches on-chain truth
(-0.094245) within 0.000000 SOL via accountData[*].nativeBalanceChange
(NOT nativeTransfers — that field misses PDA-mediated swap proceeds; closing
the original parser-bug gap of 0.281 SOL). id 6580 row backfilled to
correction_method='live_actual_v1'. Closes V5a parity-of-truth precondition.
New tracking: LIVE-CLOSE-PATH-B-LATENCY-001 (Tier 2), LIVE-PATH-B-SLIPPAGE-
DERIVATION-001 (Tier 2). Audit: docs/audits/LIVE_FEE_CAPTURE_002_PATH_B_2026_05_01.md.
```
