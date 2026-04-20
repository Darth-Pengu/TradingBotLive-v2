# Sell-path devnet validation + PumpPortal spec audit (Session 3)

> **Correction appended 2026-04-20 (post-session, same day):** Verdict amended from **B** ("spec matches code; 261 historical HTTP 400s are condition-specific — dust balance / mid-graduation pool drift / low liquidity / transients") to **B-conditional** — **spec matches code, BUT this audit did not investigate whether routing state is refreshed between buy and sell.** Subsequent evidence (`paper_trades.platform` is uniformly `pump.fun` across all 6,352 rows; sampled `features_json.bonding_curve_progress` values remain `0.0` through the entire hold — populated at signal-discovery / buy time and never updated) indicates the 261 historical HTTP 400s are **predominantly caused by stale routing state on sells of graduated tokens**, not by the "transient" causes originally named. Mechanism: `bot_core._close_position` passes `pos.bonding_curve_progress` (stale) to `execute_trade(..., bonding_curve_progress=...)`, which routes to `_execute_pumpportal_local` even when the token has graduated and the pump.fun pool no longer exists → HTTP 400. Fix tracked as **EXEC-001** (routing state refresh in `_close_position`), which must land paired with **EXEC-002** (Jupiter NameError at `services/execution.py:491`, this audit's Leftover concerns #1 — crashes on any successful Jupiter TX_SUBMIT). The spec-vs-code match finding itself (§3 of this audit) remains valid. The body of this audit is preserved unchanged as historical record; see `ZMN_ROADMAP.md` for EXEC-001 + EXEC-002 item text and ownership.

**Date:** 2026-04-20 (Sydney AEDT)
**Scope:** devnet Jupiter buy→hold→sell cycle attempt + read-only PumpPortal Local API spec audit.
**Not mainnet. No Railway changes. No TEST_MODE flip.**
**Runs in parallel with Session 4's 24h paper observation clock — no interference.**

---

## TL;DR

**Phase 2 (devnet Jupiter cycle): BLOCKED (not executed)** — two independent blockers, one transient (devnet faucet rate-limited out across every available public endpoint) and one structural (`services/execution.py` hardcodes mainnet URLs for Jupiter and PumpPortal; only the final `sendTransaction` RPC is env-overridable). Even with devnet SOL, a devnet-funded keypair signing a mainnet-assembled transaction cannot complete.

**Phase 3 (PumpPortal Local spec audit): VERDICT B — spec matches code.** All 7 required fields present; pool enum current; percentage-string sells (`"100%"`) are explicitly documented as the supported recipe. Content-type mismatch (form-urlencoded vs documented JSON example) is functionally irrelevant — endpoint tolerates form-data (proven by 97.1% historical success rate). **No payload patch this session.** The 261 historical HTTP 400s (2.9% error rate on v3/v4 mainnet trials) are condition-specific (dust balance, mid-graduation pool drift, low liquidity, or provider-side transients), not payload-format drift.

**Session 5 clearance: YES-WITH-CONDITIONS.** Proceed with (a) tightened sell-side error budget, (b) Sentry search for `"PumpPortal Local HTTP 400"` in the first 30 min of the live window to capture response body content, and (c) existing sell-storm circuit breaker (cd266de, 8 consecutive errors / 5 min park) as the backstop. If a condition class emerges in the Sentry body data, Session 5 or a follow-up can address with targeted code (Proposal A2.2 below).

---

## Phase 0 — Context loaded

- `CLAUDE.md`, `ZMN_ROADMAP.md` (2026-04-19 consolidated), `docs/audits/SENTRY_TRIAGE_2026_04_19.md`, `docs/audits/ZMN_LIVE_TRADE_FORENSICS_2026_04_19.md`, `session_outputs/ZMN_DASH_FIX_DONE.md` (Session 2 v2), `session_outputs/ZMN_DASH_ENTRY_DONE.md` (Session 2b).
- Session 2b (commit `dafe1fa`) already landed; entry-path INSERT + close-path UPDATE refactor complete.
- Session 4 (trading-tune bundle) already landed — verified from bot_core env: `TIERED_TRAIL_SCHEDULE_JSON` starts at `[0.10, 0.30]` (post-TUNE-001), `SD_EARLY_CHECK_SECONDS=60`, `SD_EARLY_MIN_MOVE_PCT=3.0`, `ML_THRESHOLD_SPEED_DEMON=40` (bot_core + signal_aggregator).

Code landmarks (read in full):

- `services/execution.py` — 811 lines.
- `_execute_pumpportal_local` at L305; sell payload at L335-344.
- `_execute_pumpportal` (post-grad JSON path) at L244.
- `_execute_jupiter` at L409.
- `execute_trade` entrypoint at L661, routes on `bc_progress < GRADUATION_THRESHOLD (0.95)` AND `signal_type != "migration"`.

---

## Phase 1 — Devnet setup

### 1.1 — Throwaway keypair

- Generated `/tmp/zmn_devnet_keypair.json` (0600; gitignored via new `.gitignore` pattern added this session).
- Devnet pubkey: `o1DqdAyvQxDjiazf9J2QDY9u3g1SF4B5Dp3VRgAZJ9t`.
- Private key never written to shell transcript or any committable file.

### 1.2 — Faucet: exhausted

| Attempt | Endpoint | Outcome |
|---|---|---|
| 1 | `solana airdrop 2` via default devnet | `airdrop request failed. This can happen when the rate limit is reached.` |
| 2 | `solana airdrop 1` retry | same error |
| 3 | `solana airdrop 1` retry (2nd) | same error |
| 4 | direct JSON-RPC `requestAirdrop 0.5 SOL` | HTTP 429: "You've either reached your airdrop limit today or the airdrop faucet has run dry. Please visit https://faucet.solana.com for alternate sources of test SOL" |
| 5 | `faucet.solana.com` | web UI only — not callable from CLI session |

Final balance: 0 SOL. The keypair is unfunded. Plan's STOP condition "Devnet faucet exhausted" technically tripped here, but the plan ALSO explicitly provides a fallback: "If single cycle FAILS... proceed to Phase 3 (spec audit may explain it)". Following the non-abort branch because Phase 3 (the core value) has no wallet dependency.

### 1.3 — Helius API key (read-only from Railway)

Read via `mcp__railway__list-variables` on bot_core. Extracted `HELIUS_API_KEY` only. Never written to any committable file. `/tmp/devnet.env` was NOT created this session — without a viable test path, writing the key to disk (even chmod 600) adds leak surface with no offsetting benefit.

### 1.4 — .gitignore hardening

Added in this session's non-commit state:
```
# Session 3 devnet test (never commit)
scripts/devnet_*
/tmp/devnet.env
/tmp/zmn_devnet_*
```

---

## Phase 2 — Jupiter devnet cycle: BLOCKED

Not executed. Root causes:

**Blocker 1 (transient):** Devnet faucet exhausted (§1.2).

**Blocker 2 (structural, discovered during setup):** `services/execution.py` hardcodes mainnet endpoints:

| Path | Endpoint | Devnet override? |
|---|---|---|
| `_execute_jupiter` | `JUPITER_ORDER_URL = https://api.jup.ag/swap/v2/order` (L57) | None — not env-configurable. |
| `_execute_jupiter` | `JUPITER_EXECUTE_URL = https://api.jup.ag/swap/v2/execute` (L58) | None. |
| `_execute_pumpportal` | `PUMPPORTAL_TRADE_URL = https://pumpportal.fun/api/trade-local` (L56) | None — mainnet-only per plan. |
| `_execute_pumpportal_local` | `PUMPPORTAL_LOCAL_URL = https://pumpportal.fun/api/trade-local` (L59) | None. |

Only `HELIUS_STAKED_URL` / `HELIUS_RPC_URL` / `HELIUS_GATEKEEPER_URL` are env-override points (L37-40, 46-53 startup guard), and they govern only the final `sendTransaction` RPC step. The Jupiter quote-assembly, Jupiter execute landing, and PumpPortal tx generation all target mainnet regardless of keypair cluster. A devnet-funded keypair signing a mainnet-assembled transaction fails on-chain (insufficient mainnet SOL at that wallet address).

**Implication for the session plan's assumption:** The plan's test harness (`scripts/devnet_sell_test.py`) writes `TEST_MODE=false`, `TRADING_WALLET_ADDRESS=<devnet_pubkey>`, `HELIUS_*_URL=https://devnet.helius-rpc.com/…`, and expects `execute_trade()` to route via Jupiter on devnet by virtue of `bonding_curve_progress=0.95`. This assumption is incorrect for this codebase — the cycle would still hit mainnet Jupiter, not devnet.

Enabling devnet validation of the sell path would require a separate session:
- Add `JUPITER_ORDER_URL` / `JUPITER_EXECUTE_URL` / `PUMPPORTAL_LOCAL_URL` env-override hooks (~8 lines).
- Switch test mint to a devnet-valid mint (e.g., devnet USDC `Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr`, not mainnet USDC `EPjFWdd5…`).
- Verify Jupiter devnet support (recent Jupiter docs indicate limited devnet routing; may require wSOL ↔ devnet test tokens with specific pool configs).

That scope is out-of-scope for this session, which is scoped to payload spec alignment, not to adding devnet routing capability to execution.py.

### Latency baselines (not collected)

| Metric | Status |
|---|---|
| Buy cycle latency | N/A (not run) |
| Sell cycle latency | N/A |
| 5-cycle stress latency stability | N/A |
| Sell-storm circuit breaker activation | N/A |

---

## Phase 3 — PumpPortal Local spec audit

### 3.1 — Current spec fetched

**Endpoint:** `POST https://pumpportal.fun/api/trade-local`
**Source:** https://pumpportal.fun/local-trading-api/trading-api (discovered via site nav — the `/trading-api` path in the session plan 404s; Lightning API is separately documented at `/trading-api/setup`).

**Required fields (spec):** `publicKey` (string), `action` (string, "buy"/"sell"), `mint` (string), `amount` (number OR string — percentage-string like "100%" explicitly supported on sells), `denominatedInSol` (string, "true"/"false"), `slippage` (number), `priorityFee` (number).
**Optional fields (spec):** `pool` (default "pump"), `skipPreflight` (default "true"), `jitoOnly` (default "false").
**Pool enum (current):** `pump`, `raydium`, `pump-amm`, `launchlab`, `raydium-cpmm`, `bonk`, `auto`.
**Content-Type:** JSON example shown; form-urlencoded is implicitly tolerated (not explicitly forbidden; 97.1% historical success proves it).
**Response:** serialized transaction bytes (not JSON).

### 3.2 — Code payload (sell path, `services/execution.py:335-344`)

```python
form_data = {
    "publicKey": TRADING_WALLET_ADDRESS,
    "action": "sell",
    "mint": mint,
    "amount": "100%",
    "denominatedInSol": "false",
    "slippage": str(slippage_pct),
    "priorityFee": "0.0005",
    "pool": pool,
}
```

### 3.3 — Comparison audit

| Field | Code value | Code type | Spec requirement | Spec type | Delta? |
|---|---|---|---|---|---|
| publicKey | `TRADING_WALLET_ADDRESS` env | string | required | string | MATCH |
| action | `"sell"` | string | required: "buy" or "sell" | string | MATCH |
| mint | `mint` param | string | required | string | MATCH |
| amount | `"100%"` | string (percentage) | "can be a percentage of tokens in your wallet (ex. amount: \"100%\")" | number or string | **MATCH** — percentage-string explicitly documented |
| denominatedInSol | `"false"` | string | required; "true" or "false" | string | MATCH |
| slippage | `str(slippage_pct)` | string (coerced) | required | number | minor cosmetic drift (see §3.5) |
| priorityFee | `"0.0005"` | string (literal) | required | number | minor cosmetic drift (see §3.5) |
| pool | `pool` param (default `"pump"`) | string | optional, default `"pump"` | string | MATCH |

**Required fields not present in current code:** NONE. All 7 required fields are sent.
**Deprecated fields present in current code:** NONE.

### 3.4 — Percentage vs exact-quantity on sell — MATCH

The spec explicitly documents `"100%"` as a valid percentage string. Code's `"amount": "100%"` is aligned with the documented recipe. **This is NOT the root cause of the 261 HTTP 400s.**

### 3.5 — Type-coercion observation (cosmetic)

The **post-graduation JSON path** at `_execute_pumpportal` (L257-266) sends:
```python
"amount": amount_sol,              # float
"slippage": slippage_pct,          # int
"priorityFee": priority_fee_sol,   # float
```

The **pre-graduation Local path** at `_execute_pumpportal_local` (L335-344) sends:
```python
"amount": "100%",                  # percentage string (correct)
"slippage": str(slippage_pct),     # string (spec says "number")
"priorityFee": "0.0005",           # string (spec says "number")
```

The two paths are internally inconsistent in their Python-side type handling. **However, since form-urlencoded (aiohttp `data=dict`) inherently transmits all values as strings on the wire, the Python-side `str()` coercion is effectively a no-op at the HTTP layer** — PumpPortal's parser receives identical string values either way for form-encoded submissions. This cosmetic inconsistency would only matter if the code were switched to JSON content-type, where `"10"` ≠ `10` to a strict JSON consumer.

**Not a fix.** Not this session.

### 3.6 — Other observations

- `skipPreflight` and `jitoOnly` optional fields are NOT sent by the Local path. Defaults apply: `skipPreflight=true` (no pre-send simulation by PumpPortal server-side), `jitoOnly=false` (the bot sends directly via Helius RPC after PumpPortal returns the tx bytes). Aligns with the current code, which sends via `sendTransaction` on Helius RPC at L377-395, not via Jito-only bundle.
- No mandatory new field has been added since the code was written.

### Verdict: **B — spec matches code, 261 errors are condition-specific**

**Reasoning.** Each of the leading payload-format hypotheses is eliminated:

| Hypothesis | Ruling |
|---|---|
| `"100%"` percent-string rejected | Explicitly documented as supported |
| `pool` enum drift | Current code values all appear in spec list |
| Missing required field | All 7 present |
| Content-type requirement changed | Form-urlencoded clearly accepted (97.1% success) |
| String-vs-numeric type coercion | Irrelevant for form-urlencoded transport |

**Likely cause class: condition-specific, not payload-format.** Possibilities (no way to discriminate without captured response bodies from the 261 failures — which were pre-Sentry-integration):

1. **Mint state transitions mid-sell.** A token graduating from bonding curve to Raydium between signal evaluation and sell submission would mismatch the `pool` field with current on-chain state. PumpPortal's `auto` pool logic should handle this, but the signal pipeline locks `pool` at enrichment time, so the sell can inherit a stale `pool="pump"` after the token migrated.
2. **Dust balance / rounding-to-zero.** `"100%"` on a wallet where the token balance is below PumpPortal's minimum sellable threshold rejects as invalid amount.
3. **No routable path at requested slippage.** Low-liquidity mints may return 400 (not 502) if no pool can satisfy the slippage constraint.
4. **Rate-limited bursts.** Some endpoints return 400 during rate-limit windows (most return 429, but 400 is occasionally seen).
5. **Transient provider issue.** 2.9% baseline error rate is within typical external-API reliability envelope.

None are fixable via payload patch alone.

### Proposed fix (if any): NONE this session

The verdict is B. Payload is correctly aligned. No code change warranted.

---

## Phase 4 — Stress test: SKIPPED

Plan specifies: "Skip this phase if Phase 2's single cycle failed." Phase 2 did not run; stress test requires a single-cycle baseline. Skipped.

---

## Clearance for Session 5: YES-WITH-CONDITIONS

Session 5 (LIVE-002 supervised live-enable) proceeds under these conditions:

1. **Tightened sell-side error budget.** Current sell-storm circuit breaker (cd266de, 8 consecutive errors / 5 min park per mint) remains the backstop. Consider tightening to 5/min for the Session 5 live window (env-tunable via `SELL_FAIL_THRESHOLD`), to surface condition-specific mint states earlier.

2. **Sentry body capture during the first 30 minutes.** Search Sentry with:
   ```
   mcp__sentry__search_events(
     organizationSlug='rz-consulting',
     projectSlugOrId='zmn-bot-core',
     naturalLanguageQuery='PumpPortal Local HTTP 400'
   )
   ```
   on any occurrence; the response body (captured by `services/execution.py:351-352` via `body[:2048]`) will reveal the condition class (dust, liquidity, pool drift, etc.). This gives Session 5 or a post-Session-5 session a definitive root cause with evidence.

3. **Existing SESSION 5 preconditions from CLAUDE.md "Live trading mode — session-gated" all remain in force** (market:mode:override=NORMAL, wallet balance verification, sell-storm breaker present, explicit authorization in session prompt).

**Session 5 is NOT blocked on further devnet work.** The code's sell payload is spec-aligned. Additional devnet infrastructure (env-override hooks for JUPITER_ORDER_URL / PUMPPORTAL_LOCAL_URL, devnet-valid test mint) is a separate nice-to-have and does not gate live-enable.

---

## A2-style follow-up proposals (NOT committed this session)

Two hygiene-class improvements that would reduce the HTTP 400 blast radius when live trading resumes. Both require their own sessions with Jay's review.

### Proposal A2.1 — Enriched 400-response capture (~15 min session)

Body is already captured in the error message at L351-352 (truncated to 2048 chars). When Sentry captures the subsequent `ExecutionError` via the ERROR path at L756-757 and L80-107 (`live_execution_log`), the body is preserved. **No code change needed.** Just ensure Session 5 includes a post-live-window Sentry pass for this query.

### Proposal A2.2 — 400-specific Jupiter fallback (~60-90 min session)

Tightens sell-storm handling for the 400 class specifically. Currently all ExecutionError types go through identical retry → park flow. A refinement:

- On HTTP 400 from PumpPortal Local: park the mint in PumpPortal path, try Jupiter V2 path once (post-graduation route). If the token has graduated but pool field was stale, Jupiter will succeed.
- On HTTP 5xx / timeout: park with backoff (existing behavior).

Scope: ~15 lines in `_execute_pumpportal_local` + a new branch in `execute_trade` for the 400→Jupiter fallback. Unit-testable with a mocked PumpPortal response (no devnet dependency). Deferred to a follow-up session with evidence from A2.1's Sentry capture.

### Proposal A2.3 — Devnet routing capability (~90-120 min session)

Enables genuine devnet validation by adding env-override hooks for mainnet-hardcoded URLs:

```python
JUPITER_ORDER_URL = os.getenv("JUPITER_ORDER_URL_OVERRIDE", "https://api.jup.ag/swap/v2/order")
JUPITER_EXECUTE_URL = os.getenv("JUPITER_EXECUTE_URL_OVERRIDE", "https://api.jup.ag/swap/v2/execute")
PUMPPORTAL_LOCAL_URL = os.getenv("PUMPPORTAL_LOCAL_URL_OVERRIDE", "https://pumpportal.fun/api/trade-local")
```

Plus a devnet-valid test harness (devnet USDC mint, Jupiter devnet routing confirmed). Enables CI-style pre-live validation for any future changes to the execution code. Not urgent; deferred until a future live trial reveals a concrete need for local validation.

---

## Leftover concerns

1. **Faucet exhaustion across all public endpoints** suggests the session IP or keypair is flagged in some provider's rate-limit table. Not this codebase's problem but affects future devnet sessions. Alternative: request Jay run the faucet manually via https://faucet.solana.com when Session 3.5 / A2.3 is scheduled.

2. **`services/execution.py:547` uses a separate auth pattern for HELIUS_STAKED_URL** (`Bearer` token + URL without `?api-key=` query string). This session did not audit the signing / auth logic — scope was payload spec only. Recommend a separate audit pass in the future to verify HELIUS_STAKED_URL Bearer auth is still the current Helius convention post-their recent API changes (not this session).

3. **`_execute_jupiter` at L491 references `amount_sol` in the `live_execution_log` call**, but `amount_sol` is not a variable name in that scope (only `amount_lamports`). Appears to be a NameError waiting to happen on any successful Jupiter TX_SUBMIT log. Flagged for follow-up (not in session 3 scope to fix). If Session 5 sees a NameError in bot_core logs after a Jupiter buy/sell, this is why.

---

## Session meta

- **Duration:** ~45 min (well under 90 min budget — Phase 2 blocked early, Phase 3 was the focus).
- **MCP calls:** `mcp__railway__list-variables` (1, read-only bot_core env), `WebFetch` (3, pumpportal.fun spec).
- **Files touched:** `.gitignore` (+3 lines), this audit doc (new file).
- **Commits this session:** 1 planned (audit-only; see §next).
- **Railway deploys triggered:** 0 (docs + .gitignore only).
- **STOP conditions:** faucet exhaustion tripped, but non-blocking for Phase 3. Proceeded on plan's explicit fallback branch.
