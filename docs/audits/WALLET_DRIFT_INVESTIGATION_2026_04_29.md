# WALLET-DRIFT-INVESTIGATION 2026-04-29 — trading wallet drain reconciliation

**Session:** WALLET-DRIFT-INVESTIGATION-2026-04-29
**Author:** Claude Code (read-only)
**Audit-doc written:** 2026-04-30 (one day after ENV-AUDIT-2026-04-29 surfaced the WALLET-DRIFT blocker)
**Companions:** `ENV_AUDIT_2026_04_29.md` (§1 finding 1, §7), `LIVE_FEE_MODEL_AUDIT_2026_04_29.md` (§4), `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` (commit `1b40df3` — prior wallet baseline), `session_outputs/ZMN_LIVE_ROLLBACK.md` (Session 5 v4 documented live window)
**Scope:** READ-ONLY. No env changes. No Redis writes. No DB writes. No service restarts. No code changes. Single docs commit.

---

## §1 Executive verdict

**Outcome C — Drain explained by trades + an UNDOCUMENTED outgoing transfer.**

1. The 1.5 SOL drain between the 2026-04-19 forensics baseline (1.610389092 SOL) and today (0.064095633 SOL) is **fully reconciled to the lamport** by 8 on-chain transactions in the window. Reconciliation gap is **0 lamports** (sub-1e-9 SOL).
2. The drain is concentrated in a **single outgoing System Program TRANSFER** on **2026-04-21 10:04:48 UTC**, sig `42dnuS1xvWZcobAvnUENz1rJorguU1to9HwagCqZwRmEJVCGtBTNRwaXvd5xD7TMuHBB18p7jNiDpGh2SDeYoNL8`, sending **1.50 SOL** from `4h4pstXd…ii8xJ` to **`7DSQ3ktYiirRfs4YQojyDTqUM9Cwj9YgzwwegyiCAgUy`**. Fee payer = trading wallet itself (transaction signed with its private key). This is **not a swap, not a bot transaction**, not driven by `services/`. The destination address has zero references in the repo.
3. **V5a disposition: BLOCKER STAYS OPEN, status changed from 🔥 to 🟡 PENDING_USER_CONFIRMATION.** If Jay confirms the 2026-04-21 transfer was an intentional consolidation to his own wallet, the blocker collapses to "needs top-up only" (Outcome B path) and V5a sequencing can proceed. If unintended, the blocker escalates to Outcome D and security investigation precedes any further live work.

**Critical correction to the working hypothesis:** the session prompt assumed the 6 `paper_trades` "live" rows summing to −3.21 SOL realised PnL would explain the drain. **5 of those 6 rows are reconcile-residual paper-position force-closures with NULL on-chain signatures** (the well-documented Session 5 v4 reconcile-leak from `session_outputs/ZMN_LIVE_ROLLBACK.md`). They had **no on-chain SOL effect**. Only id 6580 (`yh3n441J`) was a real live trade, costing exactly −0.094245 SOL on-chain. The drain math required a separate non-trade explanation — the 1.5 SOL transfer is it.

---

## §2 Reference points (UTC throughout)

| Marker | Source | Date / time | On-chain wallet balance |
|---|---|---|---:|
| **A0. v4 forensics deep recon** | `1b40df3` `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` §1.1 | 2026-04-19 ~04:00 UTC | 1.610 SOL |
| **A1. v4 forensics commit time** | `git show 1b40df3` | 2026-04-19 05:50:59 UTC (15:50:59 +1000) | 1.658 SOL (post-ELONX +0.0485) |
| **B. AGENT_CONTEXT.md figure** | `AGENT_CONTEXT.md` §0.4 | 2026-04-17 (during v4 trial) | 3.6774 SOL **(stale — was a `portfolio_snapshots` paper-balance row inherited as a wallet figure; see `1b40df3` §2.5)** |
| **F0. Session 5 v4 T0 (live flip)** | `session_outputs/ZMN_LIVE_ROLLBACK.md` "T+0" | 2026-04-20 20:44:30 UTC | 1.658400592 SOL |
| **F1. Session 5 v4 final** | `session_outputs/ZMN_LIVE_ROLLBACK.md` "Final wallet" | 2026-04-20 20:59:22 UTC | 1.564155614 SOL |
| **D. EMERGENCY_STOP** | `STATUS.md` 2026-04-28 entries | 2026-04-25 21:52:50 UTC | (not snapshot) |
| **E. First post-recovery paper close** | `ENV_AUDIT_2026_04_29.md` §4.6 | 2026-04-28 13:02:06 UTC | (paper, irrelevant) |
| **C. ENV-AUDIT-2026-04-29 reading** | `ENV_AUDIT_2026_04_29.md` §7 (Helius getBalance) | 2026-04-29 12:39 UTC | 0.064095633 SOL |
| **C+1. This-session reading** | Helius `getBalance` (2026-04-30) | 2026-04-30 (writing time) | **0.064095633 SOL (unchanged from C)** |

**Drain candidates (each evaluated below):**

| Window | SOL delta | Where evaluated |
|---|---:|---|
| B → C (2026-04-17 → 2026-04-29) | −3.6133 SOL | The B figure is **stale and not a true on-chain reading** (per `1b40df3` §2.5). Reframed as A0 → C. |
| **A0 → C (2026-04-19 → 2026-04-29)** | **−1.5460 SOL** | This audit. **Fully reconciled in §3, §6.** |
| F0 → F1 (Session 5 v4 window) | −0.0942 SOL | Already reconciled in `ZMN_LIVE_ROLLBACK.md` (1 real live trade, id 6580 yh3n441). Independently verified here in §3 row 2-4. |
| F1 → C (post-rollback → 2026-04-29) | −1.5001 SOL | **The actual unexplained delta.** Bot has been TEST_MODE=true since the rollback flip-back on 2026-04-20 20:59:22 UTC, so any on-chain activity in this window is non-bot. Resolved in §3 row 6 + §5. |

**Note on B (3.6774 SOL on 2026-04-17):** the `1b40df3` forensics doc explicitly identifies this number as a stale paper-balance row from a `portfolio_snapshots` snapshot taken *during* v4 (when TEST_MODE was briefly false), not from a fresh `getBalance` call. The first fresh on-chain reading after v4 ended is the deep-recon 1.61 SOL value (A0). The B figure is therefore not a load-bearing reference point for this reconciliation; it is preserved here only because the session prompt named it explicitly.

---

## §3 On-chain transaction inventory — wallet `4h4pstXd…ii8xJ` since 2026-04-19

Source: `mcp__helius__getTransactionHistory(mode=signatures)` enumerated all signatures (newest-first) — full wallet history is 410 sigs, of which **8 fall in the 2026-04-19 → 2026-04-30 window**. All 8 parsed via `mcp__helius__parseTransactions(showRaw=false)`.

The "Net delta on 4h4pstXd…" column is from each transaction's `meta.preBalances[i] / meta.postBalances[i]` for the trading wallet's account index (encoded by Helius's parser as `Account Balance Changes`). It includes the network fee where the trading wallet was the fee payer.

| # | Time UTC | Sig (truncated) | Status | Type / Source | Net delta (SOL) | Tx fee (SOL) | Description |
|---:|---|---|:---:|---|---:|---:|---|
| 1 | 2026-04-19 04:49:29 | `4x1bQy…` | ✅ | SWAP / OKX_DEX_ROUTER | **+0.0480115** | 0.000080001 | ELONX dust sale via OKX. **External — not bot-originated.** Already documented in `1b40df3` §2.4 (no `services/` references OKX). |
| 2 | 2026-04-20 20:55:50 | `cG4DC2…` | ✅ | SWAP / PUMP_FUN | **−0.374251786** | 0.000505 | yh3n441 BUY (`paper_trades.id=6580` `entry_signature`). 0.3653 SOL face-value position + ~0.009 SOL fees/tips/rent. |
| 3 | 2026-04-20 20:55:53 | `2J5uPEv…` | ❌ | TRANSFER / SYSTEM_PROGRAM | 0 | 0.000005825 | **Failed** (`InsufficientFundsForRent`). Fee payer = `odinWNf6…` (NOT the trading wallet). Trading wallet appears as a 1-lamport leg in a many-recipient broadcast — this is a 3rd-party "odin" promotional dust attempt that failed. **Zero impact on 4h4pstXd…** |
| 4 | 2026-04-20 20:56:44 | `4bHzZZ…` | ✅ | SWAP / PUMP_FUN | **+0.280006808** | 0.000505 | yh3n441 SELL (`paper_trades.id=6580` `exit_signature`). |
| 5 | 2026-04-20 20:59:20 | `2QWwQxr…` | ✅ | TRANSFER / SYSTEM_PROGRAM | **0** (no balance change) | 0.000005 | Pump.fun creator-fee distribution. Fee payer = `25ipFp7Z…` (NOT the trading wallet). The trading wallet is a referenced account but has no balance change. **Zero impact on 4h4pstXd…** |
| 6 | **2026-04-21 10:04:48** | **`42dnuS1…`** | ✅ | **TRANSFER / SYSTEM_PROGRAM** | **−1.50008** | **0.00008** | **OUTGOING 1.5 SOL TRANSFER from 4h4pstXd… to `7DSQ3ktYiirRfs4YQojyDTqUM9Cwj9YgzwwegyiCAgUy`. Fee payer = trading wallet (signed with its private key).** See §5. |
| 7 | 2026-04-21 10:05:38 | `5r5gZ7y…` | ✅ | TRANSFER / SYSTEM_PROGRAM | +0.00001 | 0.000005 | Inbound 0.00001 SOL from `7DSQVNcXRDXvC485izTK6kGA2Ya3751Ga3CJ8QQ8AgUy` — 50s after row 6, with a vanity address that **shares both prefix `7DSQ` and suffix `AgUy` with the row-6 destination** but is NOT the same key. Classic **dust-phishing pattern** (mimics destination from row 6 hoping the wallet owner will copy-paste to the wrong recipient on a later send). Zero security impact; informational. |
| 8 | 2026-04-21 10:05:55 | `4uSUHU6…` | ✅ | TRANSFER / SYSTEM_PROGRAM | +0.000010019 | (0.000015 paid by sender) | Inbound 10,019 lamports from `QVtWcAX3R7Cr51VhAxFSYntoCAmTQzK8Hf4R1TrKNQ4` via a relay (`7DS1Lkbz…`). Programmatic dust — broadcast to multiple wallets in the same transaction. Likely scraped from row-6 leg in row-6's broadcast. Zero security impact; informational. |

**Window after 2026-04-21 10:05:55 UTC:** ZERO transactions on `4h4pstXd…` through 2026-04-30 (writing time). Wallet has been completely on-chain-idle for **9 days**. Helius `getBalance` returns the same `0.064095633` SOL value as in the env audit at 2026-04-29 12:39 UTC.

---

## §4 Trade-pair reconciliation against `paper_trades` live rows

Query (read-only):

```sql
SELECT id, mint, amount_sol, entry_price, exit_price, slippage_pct, fees_sol,
       realised_pnl_sol, exit_reason, hold_seconds,
       entry_signature, exit_signature, entry_time, exit_time, personality
FROM paper_trades WHERE trade_mode = 'live' ORDER BY id;
```

Result on the 6 live rows:

| paper_trades id | mint (8) | entry_sig matched on-chain? | exit_sig matched on-chain? | DB realised_pnl | On-chain entry delta | On-chain exit delta | On-chain trade-pair total |
|---:|---|---|---|---:|---:|---:|---:|
| 6575 | 3jk7Y1uL | **NULL** in DB → cannot match | **NULL** in DB → cannot match | −0.704029 | n/a | n/a | n/a |
| 6576 | 4LAqGHMC | **NULL** | **NULL** | −0.200067 | n/a | n/a | n/a |
| 6577 | nGsungJt | **NULL** | **NULL** | −0.311724 | n/a | n/a | n/a |
| 6578 | EwspLbYD | **NULL** | **NULL** | −0.763883 | n/a | n/a | n/a |
| 6579 | DPyyHjaR | **NULL** | **NULL** | −1.227207 | n/a | n/a | n/a |
| **6580** | **yh3n441J** | **`cG4DC2…` ✅ (row 2 of §3)** | **`4bHzZZ…` ✅ (row 4 of §3)** | **+0.001876** | **−0.374251786** | **+0.280006808** | **−0.094244978** |

`S_trades_onchain = −0.094244978 SOL` (single trade, id 6580 only).

**Critical interpretation:** the 5 rows with NULL signatures are NOT on-chain live trades. They are the **reconcile-residual paper positions** force-closed during the Session 5 v4 live window. Per `session_outputs/ZMN_LIVE_ROLLBACK.md` lines 96-122, the bot inherited 5 stale paper positions in `self.positions` when bot_core restarted with TEST_MODE=false at 20:44:30 UTC, then attempted live sells against mints that had no on-chain position. Each mint produced 5 ERROR events (HTTP 400 or "no Helius URL") before the rollback. None of those 5 sell attempts ever landed on-chain — they failed at the swap router or failed before reaching it.

The 5 rows were nevertheless recorded in `paper_trades` with `trade_mode='live'` because the rollback's force-close path (`exit_reason='stop_loss_35%' / 'max_extended_hold' / 'stale_no_price'`) ran through `bot_core._close_position` while TEST_MODE was still false at close time. The recorded `realised_pnl_sol` values reflect paper-style accounting (entry_amount × price drop, with 100% loss assumed when exit_price=0 forced the position to be marked unsellable), **not actual on-chain SOL movement**.

The mints' 8-char prefixes verify against the rollback doc's "5 distinct mints" table (`3jk7Y1uLHU7J`, `4LAqGHMCDD48`, `nGsungJtyDG8`, `EwspLbYDQ5GT`, `DPyyHjaRakeP`) — exact correspondence in all 5 cases.

This means the session prompt's working hypothesis ("the drain is from the 6 historical live trades") was based on a misread of the `paper_trades` schema. The audit corrects the framing: only id 6580 represents an actual live round-trip; the other 5 represent in-memory paper positions that collided with a TEST_MODE flip without bot_core restart (the bug class flagged in CLAUDE.md "TEST_MODE flip alone does not reset in-memory state" and addressed by CLEAN-003).

---

## §5 Untracked transactions

Untracked = present in §3, exists with non-trivial SOL delta, but has no `entry_signature` / `exit_signature` reference in any `paper_trades` row (or in any other DB table writing on-chain references).

The session prompt's threshold "non-trivial SOL delta (> 0.001 SOL absolute)" filters out rows 7 and 8 (the dust txs with deltas 0.00001 and 0.000010019 SOL). Two §3 rows pass that filter and remain to investigate: **row 1 (ELONX sale, +0.0480 SOL)** and **row 6 (1.5 SOL outgoing transfer)**. Row 5 (creator-fee distribution, 0 delta) also lacks `paper_trades` references but has zero balance impact and is excluded.

### §5.1 Row 1 — 4x1bQy ELONX sale (already-documented, NOT a finding)

| Field | Value |
|---|---|
| Time | 2026-04-19 04:49:29 UTC |
| Type | OKX_DEX_ROUTER swap |
| Net delta on `4h4pstXd…` | **+0.0480115 SOL** |
| Counterparty | OKX_DEX_ROUTER (program `proVF4pMXVaYqmy4NjniPh4pqKNfMmsihgd4wdkCX3u`) |
| Description | Sold 8.7M ELONX tokens for ~0.0485 SOL minus router fees |
| Documentation status | **Documented** in `1b40df3` `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` §1.2 + §2.4 |
| `1b40df3` verdict | "External — not bot-originated. Most likely Jay's manual sale of leftover ELONX dust through the OKX wallet UI." |
| Code-grep status | `services/nansen_client.py:913` is the only "okx" reference, and it's a string-match for wallet labeling, not execution. **No execution code path references OKX_DEX_ROUTER.** |

**Disposition:** documented. Not a new finding for this audit.

### §5.2 Row 6 — 42dnuS1 outgoing 1.5 SOL transfer (NEW FINDING)

| Field | Value |
|---|---|
| Time | **2026-04-21 10:04:48 UTC** (= 20:04:48 AEDT) |
| Sig | `42dnuS1xvWZcobAvnUENz1rJorguU1to9HwagCqZwRmEJVCGtBTNRwaXvd5xD7TMuHBB18p7jNiDpGh2SDeYoNL8` |
| Type | TRANSFER (System Program — lamport move) |
| Net delta on `4h4pstXd…` | **−1.50008 SOL** (1.5 SOL principal + 0.00008 SOL transaction fee) |
| **Destination** | **`7DSQ3ktYiirRfs4YQojyDTqUM9Cwj9YgzwwegyiCAgUy`** |
| Fee payer | `4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ` (i.e., the trading wallet itself — transaction signed with its private key) |
| Programs invoked | `ComputeBudget111…` + `11111111111111111111…` (System Program) |
| Repo references to destination | **None.** `grep -r "7DSQ3ktY"` over the entire working tree returns zero matches. Address is not in CLAUDE.md, not in AGENT_CONTEXT.md, not in any STATUS.md entry, not in any audit doc, not in `.env*` files, not in any `services/` source. |
| STATUS.md mention of a manual transfer | **None.** Searched STATUS.md for `transfer`, `top.up`, `topup`, `withdraw`, `manual`, `Session 5` (and adjacent). Zero hits relating to a 2026-04-21 transfer. |
| Roadmap mention | **None.** ZMN_ROADMAP.md mentions a planned "5 SOL transfer" (in the 2026-04-21 GATES-V5 + MCP-RECON + DASH-RESET changelog) but only as a forward-looking statement; there is no entry recording the **opposite-direction** 1.5 SOL outflow from the trading wallet that actually happened on 2026-04-21. |
| Holding wallet involved? | **No.** Holding wallet is `2gfHQvyQdpDtiyUcFQJE6o15VkrHn7YXubp8DRwttWJ9`. The destination `7DSQ3ktY…` is a different address. The treasury sweep target is also the holding wallet (per `services/treasury.py`), so this was not a treasury sweep. |

**Address shape observations (informational, not interpretive):**

- The destination has a vanity pattern: prefix `7DSQ`, suffix `AgUy`. Vanity addresses cost CPU to generate; addresses with both deliberate prefix and suffix are uncommon and typically belong to entities that wanted to brand their address (exchanges, services, or individuals who specifically generated one).
- 50 seconds after this transfer, a separate address `7DSQVNcXRDXvC485izTK6kGA2Ya3751Ga3CJ8QQ8AgUy` (matching both `7DSQ`+`AgUy`, distinct middle) sent the trading wallet a 0.00001 SOL dust (row 7 of §3). This is consistent with **on-chain dust-phishing**, where adversaries see a large transfer's destination, generate or pre-cache a vanity collision, and dust the sender so the lookalike appears in their tx history (raising chances of a future copy-paste to the wrong recipient). The phishing's existence neither confirms nor refutes the legitimacy of the original 1.5 SOL transfer — it only confirms the destination address was visible on-chain.
- Timing: 2026-04-21 10:04:48 UTC = 2026-04-21 20:04:48 AEDT. **~13 hours** after the Session 5 v4 rollback flip-back at 2026-04-20 20:59:22 UTC. **5 hours** after the GATES-V5 / MCP-RECON / DASH-RESET commit consolidation (`057f938` 2026-04-21 ~13:17 UTC, per ZMN_ROADMAP.md changelog). 8:04 PM Sydney is reasonable evening hours for a manual operation; the timing is consistent with — but does not establish — Jay performing a manual consolidation.

**This audit does not label the destination "Jay's wallet" or "compromise" or any other interpretive class.** Per session prompt §5: "Do NOT label any address as 'compromise' or 'Jay's wallet' — just record what's there." The audit records what's on-chain (a 1.5 SOL outgoing transfer from a wallet that the trading wallet's private key had to sign for) and the absence of any documentation in the repo. The disposition is left to Jay.

### §5.3 Rows 7 + 8 — dust phishing (informational, not material)

Combined inbound dust: 0.00001 + 0.000010019 = 0.000020019 SOL. Both received free (sender paid the fees). Both are below the session prompt's > 0.001 SOL threshold for inclusion as "untracked transactions" requiring categorization. Captured here for completeness.

The row-7 sender's vanity prefix/suffix collision with the row-6 destination is the strongest available signal that someone outside the system is monitoring `4h4pstXd…` for large outflows. **No security action is implied** — dust phishing is a write-only operation by the attacker; it cannot move the trading wallet's funds. The risk only materializes if the wallet *initiates* a transfer and copy-pastes the wrong destination from history. Mitigation: when sending from this wallet in the future, never copy-paste a destination from chain history without verifying the full address. (This is general hygiene, not a session-specific finding.)

---

## §6 Reconciliation math

### §6.1 Starting balance back-computation

The session prompt's Step 6a method: pick the earliest tx in the window, back-compute pre-tx balance from its post-balance and delta. Earliest tx in window is **row 1 (4x1bQy, 2026-04-19 04:49:29)** with post-balance derivable from forward chaining.

Forward chain from a hypothesized starting balance `X`:

```
X
+ row 1 delta (+0.0480115)
+ row 2 delta (-0.374251786)
+ row 3 delta (0, failed tx)
+ row 4 delta (+0.280006808)
+ row 5 delta (0, no balance change)
+ row 6 delta (-1.50008)
+ row 7 delta (+0.00001)
+ row 8 delta (+0.000010019)
= 0.064095633     ← Helius getBalance reading at audit time (matches both 2026-04-29 12:39 and 2026-04-30)
```

Sum of deltas: `−1.546293459 SOL`.

Solving: `X = 0.064095633 + 1.546293459 = 1.610389092 SOL`.

**This is the predicted starting balance immediately before 2026-04-19 04:49:29 UTC.**

Compare to `1b40df3` `ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md` §1.1: deep-recon read at "~70 minutes before commit time" gave **1.610 SOL**. Commit time was 2026-04-19 05:50:59 UTC, so deep recon was at approximately **2026-04-19 04:40 UTC** — i.e., 9 minutes before row 1. In that 9-minute window the wallet had no transactions. **Predicted starting balance 1.610389092 vs documented 1.610 SOL: gap < 0.001 SOL (likely just rounding in the forensics doc).** ✓

### §6.2 Walk-forward sanity check

| After tx | Balance (computed) | Documented elsewhere? | Match? |
|---|---:|---|---|
| (pre-row-1) | 1.610389092 | `1b40df3` §1.1 deep recon = 1.610 SOL | ✓ |
| Row 1 (ELONX sale) | 1.658400592 | `ZMN_LIVE_ROLLBACK.md` "T+0 baseline" = **1.658400592 SOL** | ✓ exact |
| Row 2 (yh3n441 BUY) | 1.284148806 | `ZMN_LIVE_ROLLBACK.md` "Now wallet at trigger" = **1.284148806 SOL** | ✓ exact |
| Row 3 (failed) | 1.284148806 | (no change expected) | ✓ |
| Row 4 (yh3n441 SELL) | 1.564155614 | `ZMN_LIVE_ROLLBACK.md` "Final wallet" = **1.564155614 SOL** | ✓ exact |
| Row 5 (creator-fee) | 1.564155614 | (no change expected) | ✓ |
| Row 6 (1.5 SOL OUT) | 0.064075614 | (no documentation) | — |
| Row 7 (dust IN) | 0.064085614 | (informational) | — |
| Row 8 (dust IN) | **0.064095633** | `ENV_AUDIT_2026_04_29.md` §7 = **0.064095633 SOL** | ✓ exact |

Three independent reference points (`1b40df3` deep recon, `ZMN_LIVE_ROLLBACK.md` T0 + final, `ENV_AUDIT_2026_04_29.md` §7) all match the walk-forward chain to **sub-lamport precision** at every checkpoint where they exist.

### §6.3 Reconciliation equation

```
Wallet at start of window (back-computed): 1.610389092 SOL
+ on-chain trade deltas (S_trades_onchain): -0.094244978 SOL  (id 6580 yh3n441 round-trip only)
+ untracked tx 1 (ELONX sale, documented):  +0.048011500 SOL
+ untracked tx 6 (1.5 SOL out, NEW):        -1.500080000 SOL
+ untracked tx 7 (dust in):                 +0.000010000 SOL
+ untracked tx 8 (dust in):                 +0.000010019 SOL
+ failed-tx + creator-fee (zero deltas):    +0.000000000 SOL
+ network fees absorbed (already included in Helius preBal/postBal deltas above): 0
= predicted ending balance:                  0.064095633 SOL
- actual ending balance (Helius getBalance): 0.064095633 SOL
= reconciliation gap:                        0.000000000 SOL
```

**Gap: 0 lamports.** Per session prompt §6 disposition rubric: gap < 0.01 SOL → **HYPOTHESIS CONFIRMED, drain explained**. But the explanation includes one untracked transfer that has no documented provenance, which forces the verdict to **C**, not A.

---

## §7 Verdict + V5a wallet-blocker disposition

### §7.1 Outcome selection per session prompt §7

- **Outcome A** (drain fully explained by 6 live trades + on-chain fees): **REJECTED.** Only 1 of the 6 "live" rows was a real on-chain trade (id 6580 yh3n441). Trade-pair sum is −0.0942 SOL, far short of the 1.546 SOL drain.
- **Outcome B** (drain explained by trades + a documented top-up/transfer): **REJECTED.** The 1.5 SOL transfer destination `7DSQ3ktY…` has no STATUS / ROADMAP / audit / CLAUDE.md / AGENT_CONTEXT.md reference. ROADMAP changelog entries from 2026-04-21 mention an *inbound* "5 SOL transfer planned" to the trading wallet (which never appears in on-chain history); the **outbound** 1.5 SOL on 2026-04-21 is undocumented.
- **Outcome C** (drain explained by trades + an UNDOCUMENTED transfer): **SELECTED.** Reconciliation closes to 0 lamports once the 1.5 SOL untracked outflow is included. Source/destination captured (§5.2). Disposition pending Jay's confirmation.
- **Outcome D** (drain unexplained by trades or transfers): **REJECTED.** The drain IS explained — the question is whether the explanation was authorized.

### §7.2 V5a wallet-blocker disposition

**Status change: 🔥 → 🟡 PENDING_USER_CONFIRMATION.**

The block on V5a now has two layers:

1. **Wallet size insufficient for current sizing config.** Per `ENV_AUDIT_2026_04_29.md` §7 + `LIVE_FEE_MODEL_AUDIT_2026_04_29.md` §6: at wallet 0.064 SOL, `effective_max = min(MAX_POSITION_SOL=0.25, wallet * 0.10) = min(0.25, 0.0064) = 0.0064`, and `MIN_POSITION_SOL=0.05/0.15` exceeds wallet × fraction, so V5a cannot open a position even if all other blockers cleared. **Top-up to ≥ 1.5-2.5 SOL is required mechanically.**
2. **Transfer-intent confirmation pending.** Before any top-up, Jay must confirm whether the 2026-04-21 10:04:48 UTC outflow to `7DSQ3ktYiirRfs4YQojyDTqUM9Cwj9YgzwwegyiCAgUy` was intentional. Three branches:
   - **Branch 1 (benign — Jay's own wallet / consolidation / exchange deposit):** blocker collapses to layer 1 only ("needs top-up"). V5a sequencing resumes per `ENV_AUDIT_2026_04_29.md` §8 priority order. STATUS gets a backfill entry recording what the transfer was for.
   - **Branch 2 (intentional but to a different ZMN-related address — e.g., a freshly-generated trial wallet):** same as Branch 1 functionally. STATUS backfill should record both the destination's role and a note about why it wasn't STATUS-logged at the time.
   - **Branch 3 (unintended / unauthorized):** blocker escalates to **Outcome D treatment**. Halt all V5a discussion immediately; next session is a **security investigation** (was the trading wallet's private key on a machine that could have been compromised between 2026-04-20 21:00 UTC and 2026-04-21 10:05 UTC? Has any other wallet derived from the same seed been touched? Rotate `TRADING_WALLET_PRIVATE_KEY` before any new SOL is loaded). The 9-day post-transfer idle period is mildly reassuring but not conclusive — an attacker with a small dust receiver may simply be waiting for a top-up to drain again.

**Recommendation:** Jay confirms intent on the 1.5 SOL transfer **before** any further sessions in the V5a chain (BUG-022 fix, LIVE-FEE-CAPTURE-001 Path A, LIVE-PNL-FEE-FORMULA-001, etc.). The other sessions don't depend on the wallet being topped up, but starting them while the wallet's security state is unconfirmed adds risk-surface without benefit. Confirmation is a one-line answer — defer the rest of the queue 30-60 minutes until that lands.

### §7.3 Holding wallet (out of scope but flagged)

`ENV_AUDIT_2026_04_29.md` §7 also flagged the holding wallet `2gfHQvyQ…` at 0.00978 SOL vs CLAUDE.md baseline 0.0984 SOL (~0.089 SOL drain). **Out of scope this session** per the prompt (which targets only the trading wallet). If the trading-wallet investigation lands on Outcome C Branch 3 (security), the holding wallet should be enumerated in the same Helius-forensics motion. Otherwise it's a low-priority follow-up since the absolute amount is small.

### §7.4 Updates to other audit / roadmap entries

This audit clarifies a misleading framing in two places:

1. **CLAUDE.md "Live trading mode — session-gated" block:** says "Wallet moved 5.0 → ~1.6 SOL via real trades (~3.4 SOL net cost)." That is correct for the v4 trial (2026-04-16/17 → 2026-04-19) but **does not cover** the 2026-04-21 1.5 SOL outflow. Recommend appending a short note: "Wallet then moved 1.564 → 0.064 SOL on 2026-04-21 10:04:48 UTC via a single 1.5 SOL outgoing transfer to `7DSQ3ktY…AgUy` (sig `42dnuS1…`); see `WALLET_DRIFT_INVESTIGATION_2026_04_29.md`. Awaiting transfer-intent confirmation." This audit does not edit CLAUDE.md (out of scope per session prompt's "no code changes anywhere"); the note is a recommendation for a separate Tier 1 docs session if Jay's branch-1 confirmation comes back.
2. **`LIVE_FEE_MODEL_AUDIT_2026_04_29.md` §4 "6 historical live rows":** should be re-read with the framing established in §4 above — **5 of the 6 are reconcile-residual paper closures with NULL signatures, NOT real on-chain trades**. The audit's findings about live PnL formula divergence + fees_sol/slippage_pct=0 still hold for id 6580; for the other 5 rows the divergence claim is irrelevant because there was no on-chain fill to compare against. This affects how `LIVE-ROW-BACKFILL-001` should scope: the backfill should only apply FEE-MODEL-001 estimates to id 6580 (since it had a real on-chain trade); the other 5 rows are **already accurate accounting fictions** — the bot recorded "100% loss of `amount_sol`" because the position couldn't be sold, which is what actually happened economically (the SOL was spent at entry on those mints back in v4 — the entries themselves are recorded under the v4 trial's `trades` table per `1b40df3` §2.2; the `paper_trades` rows just record the close).

---

## §8 Reproducibility

### Wallet & sigs

```
mcp__helius__getBalance(address="4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ")
  → 0.064095633 SOL (verified 2026-04-29 12:39 UTC + 2026-04-30, no movement)

mcp__helius__getTransactionHistory(
  address="4h4pstXd5JtQuiFFSiLyP5DWWdpaLJAMLNzKwfoii8xJ",
  mode="signatures",
  limit=1000,
  status="any",          # to capture failed txs (row 3 above)
  sortOrder="desc"
)
  → 410 sigs (full wallet history). 8 fall in 2026-04-19+ window.

mcp__helius__parseTransactions(signatures=[<8 sigs>], showRaw=false)
  → SOL deltas + fees + types for all 8.
```

### DB query (read-only)

```python
import asyncpg
DSN = "postgresql://postgres:<pass>@gondola.proxy.rlwy.net:29062/railway"
# Query:
# SELECT id, mint, amount_sol, entry_price, exit_price, slippage_pct, fees_sol,
#        realised_pnl_sol, exit_reason, hold_seconds,
#        entry_signature, exit_signature, entry_time, exit_time, personality
# FROM paper_trades WHERE trade_mode='live' ORDER BY id;
```

Result: 6 rows. Only id 6580 has populated `entry_signature` / `exit_signature`. The other 5 are NULL on both.

### Repo grep

```
grep -r "7DSQ3ktY" .              # 0 matches
grep -r "42dnuS1xvW" .             # 0 matches
grep -ri "manual.*transfer\|wallet.*top.up\|wallet.*topup\|wallet.*withdraw" STATUS.md    # only ENV-AUDIT references
```

### Math verification

```
predicted_start = 1.610389092 SOL    (back-computed from forward chain)
walked_forward  = 0.064095633 SOL    (matches Helius getBalance to 1e-9)
forensics doc deep recon = 1.610 SOL ← matches predicted_start within rounding
ZMN_LIVE_ROLLBACK T0      = 1.658400592 SOL ← matches walk after row 1 exactly
ZMN_LIVE_ROLLBACK FINAL   = 1.564155614 SOL ← matches walk after row 4 exactly
ENV_AUDIT §7              = 0.064095633 SOL ← matches walk after row 8 exactly
```

All arithmetic is reproducible from the §3 table alone.

### Out of scope (carried)

- **Holding wallet investigation.** Not part of session prompt.
- **Pre-2026-04-19 transactions.** v4-era reconciliation already done in `1b40df3`; this audit assumes 1b40df3 is correct and starts from its 1.610 SOL deep recon as A0.
- **Address-class lookup for `7DSQ3ktY…`.** Could be done via Helius `parseTransactions` over the destination's own history, or via Vybe `/v4/wallets/{addr}/...` for label info, but the session prompt specifically prohibits classifying the destination ("Do NOT label any address as 'compromise' or 'Jay's wallet'"). Reserved for Jay's confirmation.
- **CLAUDE.md edits** to add the 2026-04-21 transfer to the "Live trading mode — session-gated" block. Out of scope per "no code changes anywhere"; recommended as a follow-up Tier 1 docs session pending Jay's branch-1 confirmation.

---

## §9 Summary card

```
verdict:                Outcome C (drain = trades + UNDOCUMENTED transfer)
reconciliation gap:     0 lamports (sub-1e-9 SOL)
real on-chain trades:   1 (yh3n441, id 6580, net -0.094 SOL)
"live" rows in paper_trades that were NOT real on-chain trades: 5 of 6
                        (reconcile-residual paper closures from Session 5 v4)
unexplained outflow:    1.50008 SOL on 2026-04-21 10:04:48 UTC
                        sig: 42dnuS1xvWZcobAvnUENz1rJorguU1to9HwagCqZwRmEJVCGtBTNRwaXvd5xD7TMuHBB18p7jNiDpGh2SDeYoNL8
                        destination: 7DSQ3ktYiirRfs4YQojyDTqUM9Cwj9YgzwwegyiCAgUy
                        fee payer: trading wallet (signed with its private key)
V5a blocker:            🔥 → 🟡 PENDING_USER_CONFIRMATION
                        confirm intent → Branch 1/2 → "needs top-up only"
                        unintended    → Branch 3 → security investigation
holding wallet:         out of scope; flagged for follow-up if Branch 3
this audit:             read-only; no code/env/Redis/DB changes; one docs commit
```
