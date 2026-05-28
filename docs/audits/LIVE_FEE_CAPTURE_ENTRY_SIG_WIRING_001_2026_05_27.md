# LIVE-FEE-CAPTURE-ENTRY-SIG-WIRING-001 — wire `Position.entry_signature` so live closes capture full Path B

**Date:** 2026-05-28 (Sydney; UTC stamp at commit)
**Predecessor:** `V5A-FIXES-001` (2026-05-21) §11 filed `LIVE-FEE-CAPTURE-002-PATH-B-ENTRY-SIG-NOT-WIRED-001` Tier 3
**Successor:** `V5A-FLIP-002-V3` (next D-S5 window) — its Phase 10.5 first-live-close check behaviorally verifies THIS fix.
**Type:** Single-commit, single-file code fix (live-execution path), deployed while `TEST_MODE=true`. Fail-safe by design.
**Commit:** `7458f2d`
**Authorization:** Jay-acknowledged chat-side (Option 2 — fix before tonight's flip).

---

## §1 Why

Path B (`bot_core.py:1436-1478` — `LIVE-FEE-CAPTURE-002`) reconstructs on-chain net SOL delta from Helius `parseTransactions` on entry + exit signatures, producing `correction_method='live_actual_v1'` (the calibration-grade Path B row). Without an entry signature, the parser returns `None` for the entry side, the condition at L1457-1458 fails, and the close falls back to `correction_method='live_estimated_v1'` (Path A — estimated round-trip cost).

Tonight's V5A-FLIP-002-V3 trial exists in part to accumulate ≥10 Path B rows to unlock `PAPER-FEE-MODEL-CALIBRATION-001`. Without entry_signature wiring, every live close tonight would have closed as Path A. Calibration would not advance.

---

## §2 Investigation (Phase 1 — Q1–Q5)

Recorded in `.tmp_entrysig/01_investigation.md` (gitignored). Summary:

**Q1 — exit_signature template (works correctly):** `bot_core.py:1434` reads `_pt_exit_sig = getattr(result, "signature", None)` from the synchronously-returned `ExecutionResult`, then writes to `paper_trades.exit_signature` (UPDATE $7 / INSERT $12) and feeds the Path B parser at L1454.

**Q2 — Live buy signature availability:** `services/execution.py:666-779` `execute_trade(action, ...)` returns `ExecutionResult(success=True, signature=signature, ...)` at L750-756 synchronously, regardless of routing (`_execute_pumpportal_local_with_session` / `_execute_pumpportal_with_session` / `_execute_jupiter_with_session`). **STOP-Async NOT triggered.**

**Q3 — Position construction sites (3 total):**
- L330 — reconciler (paper_trades or trades on restart)
- L903 — paper entry (after `paper_buy`)
- **L1005 — LIVE entry (after `execute_trade("buy", ...)`)** ← the fix site

At L1005, `result.signature` is already in scope: L1061 writes it to `paper_trades.entry_signature` DB column (INSERT $8); L1090 logs it in the `ENTERED:` log line.

**Q4 — Close path DB write:** Path B at L1450 reads **in-memory** `pos.entry_signature` (not the DB column). Position dataclass at L190-218 had no `entry_signature` field → `getattr(pos, "entry_signature", None)` always returned None → Path B condition L1457-1458 always failed → `_correction_method` stayed `'live_estimated_v1'`. The fix is purely in-memory wiring; DB persistence at INSERT time (L1061) already worked.

**Q5 — Restart persistence:** Live reconciler at L309 reads `trades` table; `trades` has no `entry_signature` column. Restored Positions on restart will have `entry_signature=None` and the close will fall back to Path A. **Documented limitation** — SD holds are short (<5 min typical), mid-position restarts rare. Schema migration to add the column to `trades` would be STOP-Scope; deferred. Per session prompt §3 Q5 this is acceptable for tonight.

**id 6580 precedent:** the lone existing `live_actual_v1` row, with both signatures populated. DB sample confirms the column accepts text and the Path B parser succeeds end-to-end given a real sig.

---

## §3 Design (Phase 2)

Recorded in `.tmp_entrysig/02_design.md` (gitignored). Three minimal changes, all in `services/bot_core.py`:

1. **Position dataclass (L218):** add `entry_signature: str | None = None`. Default None covers paper entries, reconciler-restored Positions, and any buy result lacking a signature attr — all paths the close-path already handles as "skip entry parse, Path A fallback".
2. **Live entry construction (L1005):** add kwarg `entry_signature=getattr(result, "signature", None)`.
3. **Observability log (post-L1012):** `logger.info("[ENTRY_SIG] captured entry_signature=%s... ...")` when populated.

**Fail-safe properties:**
- Default `None` → paper mode unchanged (paper Position at L903 doesn't set the field).
- `getattr(result, "signature", None)` → fallback None on any anomaly.
- Path B condition at L1450 already guards on truthy `pos.entry_signature` — None path is the no-op.
- No execution path changed; no DB schema changed; no DB write changed (entry_signature already INSERTed at L1061).

**LOC:** 9 LOC delta (3 LOC code + 6 LOC comments). 1 file. Well under STOP-Scope (50 LOC / 2 files).

---

## §4 Patch (Phase 3)

`services/bot_core.py` — 9 insertions, 0 deletions:

- L218 region (Position dataclass): `entry_signature: str | None = None` + 5-line comment block explaining default-None semantics.
- L1005 region (live entry Position construction): `entry_signature=getattr(result, "signature", None),` with 3-line comment.
- Post-construction: 2-line conditional log emitting `[ENTRY_SIG] captured entry_signature=<first 8 chars>... for <personality> position (mint=<first 12 chars>)`.

Diff:
```
+    entry_signature: str | None = None
...
+    entry_signature=getattr(result, "signature", None),
...
+if pos.entry_signature:
+    logger.info("[ENTRY_SIG] captured entry_signature=%s... for %s position (mint=%s)",
+                pos.entry_signature[:8], personality, mint[:12])
```

`python -m py_compile services/bot_core.py` → COMPILE_OK.

---

## §5 Verify (Phase 3) — 17/17 PASS

`.tmp_entrysig/verify_entrysig.py`, full output in `.tmp_entrysig/verify_output.txt` (both gitignored). Five test groups:

**1. Source assertions (10/10):**
- `entry_signature: str | None = None` present in Position dataclass — PASS
- Live-entry Position block locatable + contains `entry_signature=getattr(result,` kwarg — PASS
- exit_signature template at L1434 unchanged — PASS
- Path B reference `helius_parse_signature(pos.entry_signature)` unchanged — PASS
- Paper-entry block locatable + does NOT pass entry_signature kwarg (regression-safe) — PASS
- Reconciler block locatable + does NOT pass entry_signature kwarg (Q5 limitation documented) — PASS
- `[ENTRY_SIG]` log line present — PASS

**2. Position dataclass unit tests (2/2):**
- `Position(entry_signature='testSig123')` → `p1.entry_signature == 'testSig123'` — PASS
- `Position()` default → `p2.entry_signature is None` — PASS (paper-mode parity)

**3. Mock ExecutionResult fail-safe (2/2):**
- `getattr(_MockResultWithSig(), 'signature', None)` → `'mock_sig_abcdef'` — PASS
- `getattr(_MockResultNoSig(), 'signature', None)` → `None` (no exception) — PASS

**4. Path B dry-run on id 6580 (3/3):**
- `SELECT entry_signature FROM paper_trades WHERE id=6580` → `cG4DC2rV3dj3...` — PASS
- `helius_parse_signature(sig)` → dict with `keys=['signature','fee_lamports','native_delta_lamports','token_deltas','success','parse_method','raw_response_size']` — PASS
- `parsed['success'] is True` with `native_delta_lamports=-374251786` — PASS

**Total: 17/17 PASS.** All Path B downstream consumer behavior reproduces; the wiring change is the only missing link.

---

## §6 Deploy + post-restart verify (Phase 4)

**Commit + push:** `git commit -m "fix(live-exec): LIVE-FEE-CAPTURE-ENTRY-SIG-WIRING-001 — populate Position.entry_signature from live buy result ..."` → `7458f2d` → `git push origin main` → landed (`0cb9923..7458f2d main -> main`).

**Concurrent-session check:** before push, `git fetch origin main` showed clean (no ahead, no behind). No rebase needed.

**Railway auto-deploy:** triggered by GitHub webhook on push.

**Post-restart verify (paper mode):**
- Container restarted (`bot:status` / `service:bot_core:heartbeat` transient gap observed during the restart window; pre-restart bot was actively running per `bot:filter:fill_mc_ceiling:rejects:2026-05-28=1982`).
- Paper trading expected to resume normally on the new code path. No `[ENTRY_SIG]` log lines expected in paper mode (paper buy result has no real signature; field stays None — correct).
- Deploy verification limited to: container reachable + paper trading continues. **Behavioral verification of the fix (Path B → `live_actual_v1`) is deferred to V5A-FLIP-002-V3 first-live-close** (the only path that exercises the live entry branch).

---

## §7 Known limitations

1. **Mid-position restart loses entry_signature (Q5).** Live reconciler reads `trades` table which has no `entry_signature` column. Restored Positions have `entry_signature=None`; close falls back to `live_estimated_v1`. Acceptable because SD positions are short-hold and mid-position restarts are rare. Future enhancement (out of scope): reconciler could lookup `paper_trades.entry_signature` by `mint + trade_mode='live' + exit_time IS NULL`.
2. **Behavioral verification deferred.** TEST_MODE=true throughout — the live entry branch (L993-1090) is not exercised in paper mode, so the new `[ENTRY_SIG]` log line cannot appear until tonight's flip. The 17/17 verify suite covers source-level + dataclass-level + downstream Path B parser (id 6580 dry-run); only the entry-side wiring inside a real live buy remains unverified-in-production until the flip.

---

## §8 Scope discipline

- **No** change to `TEST_MODE` (stayed paper throughout).
- **No** env var changed.
- **No** other service touched.
- **No** schema migration.
- **No** modification of exit_signature mechanism (mirrored, not touched).
- **No** modification of trade execution logic.
- **No** Tier 3 follow-up fixed beyond this one (PORTFOLIO-SNAPSHOT-MODE-FILTER-001, HEARTBEAT-EMERGENCY-STOP-REFLECTION-001, PAPER-CLOSE-TRADES-CLOSED_AT-HARDENING-001 unchanged).

---

## §9 STOPs evaluated

| STOP | Trigger | Status |
|---|---|---|
| A | Railway MCP not callable | did-not-fire (callable) |
| D | Concurrent session | did-not-fire (clean fetch pre-push) |
| H | Precedence file missing | did-not-fire (all readable) |
| Z | TEST_MODE ≠ true | did-not-fire (verified `true` via Railway MCP) |
| Async | Buy sig not synchronous | did-not-fire (`execute_trade` returns sig synchronously) |
| Investigate | exit_signature template broken | did-not-fire (template verified working) |
| Scope | >50 LOC / >2 files / schema migration | did-not-fire (9 LOC / 1 file / no migration) |
| Verify | Verify assertion fails | did-not-fire (17/17 PASS after 1 regex retune in verify script — code unchanged) |
| Loop | 3 retry attempts exhausted | did-not-fire |
| J | Deploy fails | not-yet-evaluated (deploy in progress at write time; will be reported in STATUS) |
| L | Git push conflict | did-not-fire (clean fetch) |
| Claude | Claude limit hit | did-not-fire |

---

## §10 Carry-forward for V5A-FLIP-002-V3

Add to its Phase 10.5 (first-live-close verification):

> Verify the first live close produces `correction_method='live_actual_v1'`. If it produces `live_estimated_v1`, the entry-sig wiring didn't take effect on the live path. Note it. Do NOT auto-rollback on this alone — profitability is unaffected; calibration data quality is the impact. Flag for immediate post-trial investigation and re-verify against the entry log (`[ENTRY_SIG] captured entry_signature=...`).

---

## §11 Outputs

- **NEW** `docs/audits/LIVE_FEE_CAPTURE_ENTRY_SIG_WIRING_001_2026_05_27.md` (this file)
- **CODE** `services/bot_core.py` (+9 LOC, 0 deletions)
- **UPDATED** `AGENT_CONTEXT.md` (header refresh; §6 follow-up marked RESOLVED)
- **PREPENDED** `MONITORING_LOG.md`, `STATUS.md`
- **APPENDED** `ZMN_ROADMAP.md` Decision Log
- **SCRATCH (gitignored)** `.tmp_entrysig/{PROGRESS.md, 01_investigation.md, 02_design.md, verify_entrysig.py, verify_output.txt}`

Single push at end of session: `7458f2d` (code) + amended commit including docs.
