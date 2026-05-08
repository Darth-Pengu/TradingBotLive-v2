# Vybe URL Fix Investigation — STOP per Step 7 condition #2

**Session:** VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08
**Author:** Claude Code (read-only investigation; NO code change committed)
**Goal (intended):** Fix 3 hardcoded `.com` URLs at `services/signal_aggregator.py:753, 850, 2568`
**Outcome:** STOP per Step 7 condition #2 — Vybe API has versioned-path migration; fix is more than a TLD swap. Findings audit committed; code change deferred to follow-up.
**HEAD at investigation:** `15a334a`

---

## §1 Executive summary

The session prompt anticipated a `.com → .xyz` TLD swap, based on the API-CREDITS-HEALTH-DIAGNOSTIC-001 audit (2026-05-05) which probed `.xyz` and got HTTP 401, inferring "auth required, but route exists." That inference was incorrect.

This investigation re-probed all candidate URLs with a valid `VYBE_API_KEY`. Results:

| Site | Bot's URL (current) | Status | Candidate `.xyz` (TLD-only) | Status | Canonical v4 path | Status |
|---|---|---:|---|---:|---|---:|
| L753 | `.com/token/{m}/top-holders?limit=20` | 404 | `.xyz/token/{m}/top-holders?limit=20` | 404 | `.xyz/v4/tokens/{m}/top-holders?limit=20` | **200** |
| L850 | `.com/token/{m}` | 404 | `.xyz/token/{m}` | 404 | `.xyz/v4/tokens/{m}` | **200** |
| L2568 | `.com/token/{m}/holders?limit=20` | 404 | `.xyz/token/{m}/holders?limit=20` | 404 | `.xyz/v4/tokens/{m}/top-holders?limit=20` | **200** |

The Vybe OpenAPI spec (via `mcp__vybe__get-endpoint`) explicitly states:
- `/v4/tokens/{mintAddress}/top-holders` — "**Replaces**: `GET /token/{mintAddress}/top-holders`"
- `/v4/tokens/{mintAddress}` — "**Replaces**: `GET /token/{mintAddress}`"

The TLD-only swap suggested by the prior audit does not work. The actual canonical fix involves host change AND path version migration AND, for L2568, endpoint-name change AND, for two sites, downstream field-name changes. This exceeds the prompt's "only the host/TLD changes" Step 2 contract → **STOP per Step 7 condition #2**.

---

## §2 Step 1 — Verification (read-only)

### §2.1 Step 1a — Locate all `vybenetwork` references in `services/`

```
$ Grep -r vybenetwork services/ --type=py
services/signal_aggregator.py:753:        url = f"https://api.vybenetwork.com/token/{mint}/top-holders?limit=20"
services/signal_aggregator.py:850:            url = f"https://api.vybenetwork.com/token/{mint}"
services/signal_aggregator.py:2568:                        vybe_url = f"https://api.vybenetwork.com/token/{mint}/holders?limit=20"
services/nansen_wallet_fetcher.py:209:    url = "https://api.vybenetwork.xyz/v4/wallets/top-traders"
```

The 3 broken sites are all in `signal_aggregator.py`. The sibling `.xyz/v4/...` reference in `nansen_wallet_fetcher.py:209` was always correct (commit `c9a30061`, 2026-03-29) and uses the **already-versioned** path. That file's developer left a comment at line 208: `# Vybe domain is .xyz with X-API-Key auth (not .com, not Bearer)`.

Full reference dump in `.tmp_vybe_fix/vybe_references.txt`.

### §2.2 Step 1b — Capture exact strings + surrounding context

#### L753 (`_fetch_holder_data_vybe`)
```python
async def _fetch_holder_data_vybe(session: aiohttp.ClientSession, mint: str) -> dict:
    """Vybe Network holder data fallback (free, labeled, 5-min updates)."""
    if not VYBE_API_KEY:
        return {}
    try:
        url = f"https://api.vybenetwork.com/token/{mint}/top-holders?limit=20"  # ← line 753
        headers = {"X-API-Key": VYBE_API_KEY}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            holders = data.get("data", data.get("holders", []))
            ...
            amounts = [float(h.get("balance", h.get("amount", 0)) or 0) for h in holders[:20]]
```

Failure mode: `try/except` with `logger.debug` — silent at INFO log level.

#### L850 (`_fetch_creator_history` step 1 — Vybe creator lookup)
```python
async def _fetch_creator_history(session, mint, redis_conn=None) -> dict:
    details = {}
    creator = ""
    if VYBE_API_KEY:
        try:
            url = f"https://api.vybenetwork.com/token/{mint}"  # ← line 850
            headers = {"X-API-Key": VYBE_API_KEY}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    creator = data.get("creator", "")
                    details["creator_address"] = creator
        except Exception as e:
            logger.debug("Vybe error for %s: %s", mint[:12], e)
    if not creator or not HELIUS_PARSE_HISTORY_URL:
        return details   # ← always taken: creator stays empty
```

Failure mode: silent debug log; early-return at L860 if `creator` is empty.

#### L2568 (KOL/MM holder check, inline in graduation evaluation)
```python
if VYBE_API_KEY:
    try:
        vybe_url = f"https://api.vybenetwork.com/token/{mint}/holders?limit=20"  # ← line 2568
        async with session.get(vybe_url, headers={"X-API-Key": VYBE_API_KEY},
                             timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                vybe_data = await resp.json()
                holder_list = vybe_data.get("data", vybe_data.get("holders", []))
                for h in holder_list:
                    label = (h.get("ownerLabel") or h.get("label") or "").lower()
                    if any(k in label for k in ("kol", "mm", "market maker", "smart")):
                        kol_count += 1
                if kol_count >= 2: whale_boost = 1.25
                if kol_count >= 5: whale_boost = 1.5
    except Exception:
        pass   # ← fully silent (no logger)
```

Failure mode: bare `except: pass` — fully silent.

### §2.3 Step 1c — Git history of the introducing commits

```
$ git blame -L 750,756 services/signal_aggregator.py
751680e3 (Darth-Pengu 2026-04-08 00:07:51 +1000) Phase3.3+3.4: Fix Vybe auth + add Vybe holder fallback

$ git blame -L 847,853 services/signal_aggregator.py
672eb8ac (Darth-Pengu 2026-04-04 01:12:49 +1100) feat(signal_aggregator): Speed Demon momentum hard-gates, fix Vybe URL
   (NB: The "fix Vybe URL" in the commit message refers to a different aspect — line 850 still uses .com after this commit.)

$ git blame -L 2565,2575 services/signal_aggregator.py
94b3c564 (Darth-Pengu 2026-04-04 12:18:16 +1100) feat: ML label fix, governance JSON classification, graduation sniper, Bonk.fun detection, SocialData fallback
```

The history is consistent with the CLIFF supplement (2026-05-07) finding: all 3 `.com` sites were introduced 2026-04-04 to 2026-04-08, **pre-cliff** by 13-17 days. Bot's +598 SOL pre-cliff era ran with broken Vybe URLs throughout.

Even more telling — in the file's earlier history, the URL was once `.xyz/token/...` (without `/v4/`):
```
$ git log --all -p -- services/signal_aggregator.py | grep -B1 -A1 vybenetwork
   try:
-      url = f"https://api.vybenetwork.xyz/token/{mint}"   ← past state
+      url = f"https://api.vybenetwork.com/token/{mint}"   ← regression
```

This implies the `.xyz/token/...` (un-versioned) URL **was** working at some point. Vybe's API has since migrated to `/v4/tokens/...`. Both old patterns are now dead.

### §2.4 Step 1d — Probe candidate URLs

Probe script at `.tmp_vybe_fix/probe_urls.py` (TLD-only candidates) and `.tmp_vybe_fix/probe_v4_urls.py` (canonical v4 candidates). API key passed via env (never written to disk).

#### TLD-only probe results

```
=== L753 .com /top-holders === STATUS: 404 — body: 404
=== L753 .xyz /top-holders === STATUS: 404 — body: {"code":20,"message":"The requested endpoint does not exist","id":"..."}
=== L850 .com /token === STATUS: 404 — body: 404
=== L850 .xyz /token === STATUS: 404 — body: {"code":20,"message":"The requested endpoint does not exist","id":"..."}
=== L2568 .com /holders === STATUS: 404 — body: 404
=== L2568 .xyz /holders === STATUS: 404 — body: {"code":20,"message":"The requested endpoint does not exist","id":"..."}
```

Both `.com` and `.xyz` versions of `/token/...` paths return 404. The `.xyz` host responds with a Vybe-formatted JSON error, indicating the host exists but the path does not.

The earlier audit (2026-05-05) probe likely tested `.xyz/token/...` *without* the API key and got HTTP 401 (Vybe's auth-required middleware fires before the not-found check). With a valid key, the actual path-level 404 is exposed.

#### Canonical v4 probe results

```
=== L753-fixed /v4/tokens/{mint}/top-holders === STATUS: 200
DATA[0] keys: balance, mintAddress, ownerAddress, ownerLogoUrl, ownerName, percentageOfSupplyHeld, rank, tokenLogoUrl, tokenSymbol, valueUsd
DATA[0] sample: {"rank":1, "ownerAddress":"9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
                 "ownerName":"Binance Exchange 1", "balance":"6996666051223.322200", ...}

=== L850-fixed /v4/tokens/{mint} === STATUS: 200
BODY keys: category, currentSupply, decimal, logoUrl, marketCap, mintAddress, name,
           price, price1d, price7d, subcategory, symbol, tokenAmountVolume24h,
           updateTime, usdValueVolume24h, verified
BODY excerpt: {"symbol":"Bonk", "name":"Bonk", "mintAddress":"DezX...", "price":6.94e-06, ...}

=== L2568-candidate /v4/tokens/{mint}/top-holders === STATUS: 200
(same data as L753-fixed — only one /top-holders endpoint exists)
```

All three v4 paths return HTTP 200 with valid data. Test mint: BONK (`DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`).

### §2.5 Step 1e — Cross-check Vybe documentation

Via `mcp__vybe__search-endpoints` and `mcp__vybe__get-endpoint`:

> `/v4/tokens/{mintAddress}/top-holders`
> **Description:** "Replaces: `GET /token/{mintAddress}/top-holders`. Returns the top 1,000 token holders (updated every 3 hours)."
> **Auth:** X-API-KEY header
> **Server:** `https://api.vybenetwork.xyz/`
> **Response schema:** `TopHoldersReturn { data: TopHolders[] }` where `TopHolders { rank, ownerAddress, ownerName?, ownerLogoUrl?, mintAddress, balance, valueUsd, percentageOfSupplyHeld, tokenSymbol?, tokenLogoUrl? }`

> `/v4/tokens/{mintAddress}`
> **Description:** "Replaces: `GET /token/{mintAddress}`. Returns token price, market cap, volume, and 24h metrics for any Solana token."
> **Auth:** X-API-KEY header
> **Server:** `https://api.vybenetwork.xyz/`
> **Response schema:** `TokenInformationCH { symbol, mintAddress, price, price1d, price7d, decimal, verified, updateTime, currentSupply, marketCap, name?, logoUrl?, category?, subcategory?, tokenAmountVolume24h?, usdValueVolume24h? }`
> **No `creator` field in the v4 response schema.** A "creator" is not part of v4 Token Details.

A `/token/{mint}/holders` endpoint (the path used at L2568) does not exist in v4. The `mcp__vybe__search-endpoints "holders"` returned only:
- `/v4/tokens/{mintAddress}/top-holders` (Top Holders)
- `/v4/tokens/{mintAddress}/holders-count-ts` (Holder Count History)

For L2568 (KOL/MM detection, scanning labeled top owners), `/v4/tokens/{mint}/top-holders` is the correct semantic equivalent.

---

## §3 Why the fix is more than a TLD swap

For each of the 3 sites, the changes required to actually restore data flow:

### L753 (HOLDER fallback) — URL+path fix is sufficient ✅

| Change | Required? |
|---|---|
| Host `.com → .xyz` | yes |
| Path version `/token/ → /v4/tokens/` | yes |
| Endpoint name | unchanged (`top-holders`) |
| Downstream field-name extraction | compatible — bot reads `data.[].balance`, v4 returns same |

URL+path fix alone restores HOLDER fallback fully. Bot's `top10_pct` calculation continues to work as before (sample-based, not absolute, but unchanged from current behavior).

### L850 (creator-history Vybe step) — URL+path fix is necessary but not sufficient ⚠️

| Change | Required? |
|---|---|
| Host `.com → .xyz` | yes |
| Path version `/token/ → /v4/tokens/` | yes |
| Downstream field extraction `data.creator` | **broken — `creator` is no longer a v4 field** |

URL+path fix changes 404 → 200 but the function continues to return `details = {"creator_address": ""}` because the v4 Token Details endpoint does not return a `creator` field. The function falls through to the early-return at L860 (`if not creator: return details`).

Net effect of URL+path fix at L850: same as current state (silent empty). Restoring creator-history needs an alternative data source — Helius `parseTransactions` on the token's first slot, pump.fun metadata, or another provider. Track separately.

### L2568 (KOL/MM holder check) — URL+path fix needs paired field-name update ⚠️

| Change | Required? |
|---|---|
| Host `.com → .xyz` | yes |
| Path version `/token/ → /v4/tokens/` | yes |
| Endpoint name `/holders → /top-holders` | yes |
| Downstream field extraction `ownerLabel`/`label` | **broken — v4 returns `ownerName`** |

URL+path fix changes 404 → 200 but `kol_count` stays 0 because `h.get("ownerLabel") or h.get("label")` returns empty. The actual labels in v4 live in `ownerName` (e.g., `"Binance Exchange 1"` for the BONK top holder). Without the field-name update, the URL fix produces no functional improvement.

Net effect of URL+path fix at L2568: same as current state. Pairing it with `h.get("ownerName") or ""` would restore KOL/MM detection.

---

## §4 Step 4 — Downstream caller analysis

### §4.1 `_fetch_holder_data_vybe` (L753)

Called from `_fetch_holder_data` at L693:
```python
async def _fetch_holder_data(session, mint) -> dict:
    result = await _fetch_holder_data_helius(session, mint)
    if result and result.get("holder_count_sample", 0) >= 5:
        return result
    return await _fetch_holder_data_vybe(session, mint)   # ← Vybe fallback
```

`_fetch_holder_data` itself is part of the `_collect_premarket_data` parallel fetch (L622). Its return dict is merged into `details` via `result.update(result)` at L632. **Caller doesn't break on empty return.** When Vybe returns valid data post-fix, downstream consumers (ML feature `holder_count_sample`, `top10_holder_pct`, `holder_gini`) become populated.

Risk: very low. Changes a feature from "always missing" to "sometimes present" — the ML model already handles missing values.

### §4.2 `_fetch_creator_history` (L850)

Called directly from `_collect_premarket_data` at L618. Result merged into `details` via the same `result.update` pattern. **Caller doesn't break on empty return.** The function chains to Helius `parseTransactions` if a creator is found — but with the v4 deprecation of `creator`, this chain never fires.

Risk: zero (no behavioral change vs current state).

### §4.3 L2568 (inline KOL check)

Inline in graduation handling. Sets `whale_boost` (default 1.0). After URL+path fix without field-name update, `kol_count` stays 0 → `whale_boost` stays 1.0. **Behaviorally indistinguishable from current state.**

If field-name update lands too: `whale_boost` becomes 1.25 or 1.5 for tokens with labeled top holders, scaling the graduation `score` (L2601: `score = 70 * whale_boost`). For graduated tokens the analyst signal generation will assign higher scores to those with labeled smart-money/KOL holders. That's the intended behavior — but note **ANALYST_DISABLED=true** (per Railway env). The graduation path that consumes L2568 only fires for the analyst personality, which is currently env-gated off. **Functional impact today: zero. Functional impact when analyst is re-enabled: KOL boost active.**

### §4.4 No caller will break

All three call sites already gracefully handle empty returns / silent failures. The code paths have run with Vybe data absent for the bot's entire +598 SOL pre-cliff era and the post-cliff period. There is **no caller that assumes Vybe data is populated**. Adding real Vybe data is an additive feature restoration, not a contract change.

---

## §5 Expected impact (qualitative — no SOL/day estimate)

The prior CLIFF supplement (`docs/audits/CLIFF_VYBE_SOCIALDATA_SUPPLEMENT_2026_05_05.md`) established that Vybe was NOT a load-bearing edge contributor pre-cliff. Bot's +598 SOL ran with broken Vybe URLs throughout. The fix is current-edge-restoration only, not cliff-recovery.

Magnitude bound (from the supplement's analogous SocialData populated-vs-sentinel comparison): post-cliff sample populated edge ≈ +0.0125 SOL/trade mean. At ~30 paper trades/day, this projects to ~0.4 SOL/day if Vybe holder data has comparable signal value to Twitter. Reality probably lower (Vybe holder concentration is one feature among ~13 populated; ML model weights vary).

**Do not commit a SOL/day estimate without paper sample.** Restoration value is real but bounded. Decision-relevant only if the cost of the fix is also small — which it is (3 line changes + 1 paired field-name change).

---

## §6 Why STOP (Step 7 condition #2)

The session prompt's Step 2 explicitly contracts:
> Replace the broken URL string with the verified-working one
> Preserve any path, query, or formatting around it (only the host/TLD changes)
> Do NOT refactor surrounding code

And Step 7 condition #2 explicitly says:
> STOP and write `.tmp_vybe_fix/STOPPED.md` with reason if:
> 2. Vybe API documentation indicates breaking changes between the old endpoint and a current canonical one (i.e., the fix is more than a TLD swap)

The fix is unambiguously more than a TLD swap:
1. Host `.com → .xyz` (the TLD part the prompt anticipated)
2. Path version `/token/ → /v4/tokens/` (NOT a TLD change)
3. For L2568: endpoint-name `/holders → /top-holders` (NOT a TLD change)
4. For L850 and L2568: downstream field-name issues (`creator` deprecated, `ownerLabel`/`label` renamed `ownerName`)

The Vybe OpenAPI spec uses the exact wording **"Replaces"** for the path migration — explicit acknowledgment of breaking version change.

Per the prompt's own contract, this triggers STOP. Findings audit committed (this doc); no code change committed.

---

## §7 Recommended follow-up scope

### Path A — Single follow-up session (recommended)

`VYBE-URL-CODE-DRIFT-001-FIX-V2`:

1. Apply URL+path migration at all 3 sites:
   - L753: `https://api.vybenetwork.com/token/{mint}/top-holders?limit=20` → `https://api.vybenetwork.xyz/v4/tokens/{mint}/top-holders?limit=20`
   - L850: `https://api.vybenetwork.com/token/{mint}` → `https://api.vybenetwork.xyz/v4/tokens/{mint}`
   - L2568: `https://api.vybenetwork.com/token/{mint}/holders?limit=20` → `https://api.vybenetwork.xyz/v4/tokens/{mint}/top-holders?limit=20`
2. For L2568, paired field-name update: `h.get("ownerLabel") or h.get("label")` → `h.get("ownerName") or ""`. (Lower-case match for `kol`, `mm`, etc. continues to work — names like `"Binance Exchange 1"` won't match those keywords, which is fine; only labeled smart-money holders should boost.)
3. For L850, two sub-options:
   - **A1:** apply URL+path fix only; document that creator-history continues to return empty until a different data source is wired up. Track as `VYBE-CREATOR-LOOKUP-DEPRECATED-001`. Smaller fix.
   - **A2:** delete the Vybe-step-1 in `_fetch_creator_history` and replace with Helius `parseTransactions` first-slot creator detection. Bigger; defer to its own session.
4. Verify-script demonstrates 4xx → 200 at all 3 sites.
5. Cost: S (4 string substitutions + 1 field-name update + redeploy SA).

### Path B — Skip Vybe for L850 / L2568

If Vybe enrichment is not worth maintenance:

1. Apply URL+path fix only at L753 (full functional restoration).
2. Delete or env-gate `_fetch_creator_history` Vybe-step-1 path.
3. Delete or env-gate the L2568 KOL Vybe call.
4. Cliff supplement already established Vybe was not load-bearing pre-cliff; loss of these two features is bounded.

---

## §8 Files committed this session

1. `docs/audits/VYBE_URL_FIX_2026_05_08.md` — this doc (findings only)
2. `STATUS.md` — STOP entry (newest at top)
3. `ZMN_ROADMAP.md` — Decision Log entry
4. `AGENT_CONTEXT.md` — VYBE entry refined (status remains 🔴, scope expanded)
5. `MONITORING_LOG.md` — append entry

**Not committed:** any change to `services/signal_aggregator.py`. No Railway redeploy.

`.tmp_vybe_fix/` artifacts (probe scripts, raw outputs, STOPPED.md) are untracked and remain local.

---

## §9 Reproducibility

```bash
# 1. Get VYBE_API_KEY from Railway
mcp__railway__list-variables --service signal_aggregator --kv | grep VYBE_API_KEY

# 2. Probe broken paths (TLD-only candidates)
VYBE_API_KEY=<key> python .tmp_vybe_fix/probe_urls.py

# 3. Probe canonical v4 paths
VYBE_API_KEY=<key> python .tmp_vybe_fix/probe_v4_urls.py

# 4. Cross-check via Vybe MCP
mcp__vybe__search-endpoints --pattern "top holders"
mcp__vybe__search-endpoints --pattern "token info"
mcp__vybe__get-endpoint --path "/v4/tokens/{mintAddress}/top-holders" --method GET
mcp__vybe__get-endpoint --path "/v4/tokens/{mintAddress}" --method GET

# 5. Git history of vybenetwork in signal_aggregator.py
git log --all -p -- services/signal_aggregator.py | grep -B2 -A2 vybenetwork
```

---

## §10 Decision Log entry (for ZMN_ROADMAP.md)

```
2026-05-08 VYBE-URL-CODE-DRIFT-001-FIX-2026-05-08 ⏸ STOP — Investigation complete, code change deferred. Audit established that the prior 2026-05-05 hypothesis (`.com → .xyz` TLD swap) is invalid: with valid VYBE_API_KEY, both `.com` and `.xyz` versions of `/token/{mint}/...` return HTTP 404 ("endpoint does not exist"). Canonical Vybe v4 paths `https://api.vybenetwork.xyz/v4/tokens/{mint}/top-holders` and `https://api.vybenetwork.xyz/v4/tokens/{mint}` return HTTP 200 (verified against BONK mint). Vybe OpenAPI spec explicitly notes these "Replace" the older `/token/...` paths. Per Step 7 condition #2 ("more than a TLD swap"), STOP triggered; no code change committed. Two breaking issues for downstream callers: (1) v4 Token Details no longer returns `creator` — L850 `_fetch_creator_history` will continue to return empty even after URL fix; (2) v4 `/top-holders` returns `ownerName` not `ownerLabel`/`label` — L2568 KOL detection needs paired field-name update. Recommended follow-up `VYBE-URL-CODE-DRIFT-001-FIX-V2` (Path A1): URL+path migration at all 3 sites + L2568 ownerName field update; track creator-source replacement as `VYBE-CREATOR-LOOKUP-DEPRECATED-001`. Cost S. No edge-recovery claim — cliff supplement already established Vybe was non-load-bearing pre-cliff. Audit: docs/audits/VYBE_URL_FIX_2026_05_08.md. NO code change.
```
