# HOLDER-DATA-PIPELINE-001 — Bot silence root cause + fix

**Date:** 2026-04-22
**Fix commit:** `fc87b03` (signal_aggregator.py) + follow-up BUG-021 commit (dashboard_api.py)
**Severity:** Tier 0 — bot completely silent for paper mode since GATES-V5 landed 2026-04-21.

---

## TL;DR

GeckoTerminal's `/api/v2/networks/solana/tokens/{mint}/info` endpoint changed the
shape of its `holders` field from a bare integer to a dict:

```
BEFORE: "holders": 6380239
NOW:    "holders": {"count": 6380239, "distribution_percentage": {...}, "last_updated": "..."}
```

Two call sites in `services/signal_aggregator.py` did `int(attrs.get("holders", 0))`.
`int(dict)` raises `TypeError`, caught by an outer `except Exception: pass`, so
`holders` silently stayed `0`. The GATES-V5 HOLDER gate (added 2026-04-21 in
commit `c012475` or earlier) then rejected every signal.

**Bot paper-trade cadence collapsed from ~2,256 trades / 7 days (2026-04-19)
to 0 paper trades / 10 days ending 2026-04-22.** Only live-mode trades in that
window were the Session 5 v3/v4 sessions (id 6576-6580).

---

## Evidence chain

### 1. Cadence check — bot is silent

```sql
SELECT COUNT(*), MAX(entry_time) FROM paper_trades
 WHERE entry_time > EXTRACT(EPOCH FROM NOW() - INTERVAL '48 hours');
-- Result: n=1, last_entry=2026-04-20 20:55 (Session 5 v4 live)
```

Last 10 days grouped by mode + personality: **only 6 rows, all live-mode** —
nothing paper.

### 2. Log evidence — GRAD_REJECT + HOLDER reject

Recent signal_aggregator logs consistently show:

```
GRAD_REJECT: mint=9z1aP85aw7Xg holders=0 reason=need_25+ → REJECT
HOLDER reject 24dy6zy1hUKo: 0 < 1
HOLDER reject AaLbi5hsmpPW: 0 < 1
HOLDER reject 5XF3cgdSnHe4: 0 < 1
```

Every signal shows `holders=0` even when the actual token has thousands of
holders on GeckoTerminal's page.

### 3. GeckoTerminal schema dump (live API)

```bash
curl https://api.geckoterminal.com/api/v2/networks/solana/tokens/So11111111111111111111111111111111111111112/info
```

Returns:

```json
"attributes": {
    ...
    "holders": {
        "count": 6380239,
        "distribution_percentage": {"top_10": "18.7368", "11_20": "4.1482", ...},
        "last_updated": "2026-04-22T13:11:42Z"
    },
    ...
}
```

`attributes.holders` is a dict, not an int. The bare-int schema is gone.

### 4. Failing code paths (pre-fix)

**Site A — main feature build path, `_fetch_gecko_pool_data`:**

```python
# services/signal_aggregator.py:L782 (pre-fix)
if resp.status == 200:
    info_data = await resp.json()
    attrs = info_data.get("data", {}).get("attributes", {})
    holders = int(attrs.get("holders", 0) or 0)   # ← int({...}) raises TypeError
    if holders > 0:
        result["holder_count"] = holders
except Exception as e:                             # ← swallows the TypeError
    logger.debug("GeckoTerminal token info error for %s: %s", mint[:12], e)
```

Downstream, `features["holder_count"]` stays 0 at L1881, so the GATES-V5 HOLDER
gate at L2226 rejects: `holder_count < holder_min` → `0 < 1` → reject.

**Site B — graduation processor, `_process_graduations`:**

```python
# services/signal_aggregator.py:L2441 (pre-fix)
holders = 0
try:
    gt_url = f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}/info"
    async with session.get(gt_url, ...) as resp:
        if resp.status == 200:
            gt_data = await resp.json()
            attrs = gt_data.get("data", {}).get("attributes", {})
            holders = int(attrs.get("holders", 0) or 0)   # ← same TypeError
except Exception:
    pass

if holders < 25:
    logger.info("GRAD_REJECT: mint=%s holders=%d reason=need_25+ → REJECT", ...)
    continue
```

Every graduated token was rejected with `holders=0`.

---

## Fix

Both sites now handle the dict form and keep the bare-int fallback for
forward-compat (in case GeckoTerminal reverts or adds a new form):

```python
_h_raw = attrs.get("holders")
if isinstance(_h_raw, dict):
    holders = int(_h_raw.get("count", 0) or 0)
else:
    holders = int(_h_raw or 0)
```

Commit: `fc87b03` on `main`.

No behavior change outside the holders-read — same downstream flow, same
threshold gates, same decision logic. Threshold `HOLDER_COUNT_MIN=1` unchanged;
the roadmap notes TUNE-005 as the follow-up to raise it to 15 once fresh
paper-cadence data validates the fix.

---

## Verification plan

Once Railway signal_aggregator deploy lands (~60-90s after push):

1. `HOLDER reject <mint>: 0 < 1` lines should disappear (or be replaced with
   `N < 1` where N > 0 for tokens old enough for GeckoTerminal to have indexed).
2. `GRAD_REJECT holders=0` on graduated tokens should stop. New behavior:
   `GRAD_EVAL ... → ACCEPT` or `GRAD_REJECT holders=<real N> reason=need_25+`
   depending on actual holder count.
3. `SCORED:` log lines should start appearing (signal_aggregator pushing to
   `signals:scored` Redis list) and bot_core should start consuming → paper
   trades landing in `paper_trades` table.
4. Cadence check at T+1h: `SELECT COUNT(*) FROM paper_trades WHERE entry_time
   > EXTRACT(EPOCH FROM NOW() - INTERVAL '1 hour') AND trade_mode='paper'`
   should be non-zero.

If logs still show `HOLDER reject 0 < 1` after deploy, the fix didn't take
effect — rollback (`git revert fc87b03`) and investigate why GeckoTerminal is
not being reached (network, rate-limit, etc.).

---

## Second-order considerations

- **Fresh new_token signals (age_seconds=0) still have holder_count=0 at first
  evaluation.** GeckoTerminal indexes new tokens lazily; a 5-second-old
  pump.fun token will not yet have a GeckoTerminal entry. The fix restores
  trading for tokens with SOME GeckoTerminal presence (typically age>60s) and
  for graduated tokens. Pure brand-new mints still need the `live_unique`
  fallback (`token:stats:{mint}.unique_buyers` Redis hash populated by
  signal_listener early-subscription) to pass the gate. The fallback chain at
  L1881 is correct — the issue was just that the primary source returned 0.

- **TUNE-005 recommendation.** Once paper cadence data accumulates post-fix
  (24-48h), re-evaluate whether `HOLDER_COUNT_MIN=15` or `=1` is the better
  threshold. Setting it too high kills fresh-token signals; too low defeats
  the purpose of the gate. Current `=1` is permissive; the roadmap's
  intended `=15` would be restrictive for pre-grad Speed Demon.

- **Dead code path at L1881 fallback.** The third fallback
  `int(raw.get("holder_count", raw.get("holders", 0)))` reads the PumpPortal
  `raw_data`, which doesn't include a `holders` key for pump.fun createEvent
  signals. That fallback is effectively dead. Not a bug, just a note for
  future cleanup.

- **GeckoTerminal schema watch.** This is the second GeckoTerminal schema
  change that has broken us (the first was handling the transactions shape
  in `_fetch_gecko_pool_data` pool data, also silent-catch). Consider an
  Operating Principle in CLAUDE.md: "GeckoTerminal API schemas are unstable;
  every new parser must handle unexpected shape types gracefully." Also
  consider moving the broad `except Exception: pass` to a logged warning so
  future schema changes surface as alerts.

---

## Timeline

- **2026-04-21 ~11:00 UTC** — GATES-V5 HOLDER gate added to signal_aggregator
  (commit earlier in day), `HOLDER_COUNT_MIN=1` set on Railway.
- **2026-04-21 ~11:00 UTC onwards** — Bot silent for paper mode.
- **2026-04-22 13:15 UTC** — Session opens; user reports bot silence; root-cause
  diagnosis begins.
- **2026-04-22 13:28 UTC** — Fix committed as `fc87b03`, pushed to main.
- **2026-04-22 ~13:35 UTC** — Railway auto-deploy signal_aggregator (expected).
- **2026-04-22 T+1h post-deploy** — Expected first paper trades post-fix.

Downtime: ~24-26 hours with zero paper cadence.
