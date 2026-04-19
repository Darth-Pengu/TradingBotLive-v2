# ZMN Railway deploy bloat audit

**Date:** 2026-04-19
**Scope:** what each of the 8 Railway services actually uploads per deploy,
and what the smallest possible deploy looks like.
**Disclaimer:** Jay runs 8 Railway services off the same repo, each dispatching
on `SERVICE_NAME`. I'm auditing the repo shape, not per-service filtering
(Railway doesn't do per-service filtering — every service sees the full repo).

---

## What Railway currently uploads per deploy

`railway.toml`:
```toml
[deploy]
startCommand = "python main.py"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

`nixpacks.toml`:
```toml
[variables]
PYTHONPATH = "/app"

[phases.setup]
nixPkgs = ["python311"]
aptPkgs = ["libgomp1"]
```

Railway uses Nixpacks. Nixpacks uploads the **git working tree minus
`.gitignore`** — it does NOT honor `.dockerignore` when building via
Nixpacks (Dockerfile builds do honor `.dockerignore`, but this repo uses
Nixpacks, not a Dockerfile).

Current gitignored:

```
.env, .env.local, *.session, *.db, *.log, logs/
__pycache__/, *.pyc
.venv/, venv/, ENV/, Lib/, Scripts/*.exe, scripts/*.exe
.railway/
.claude/*  (with .claude/skills/ and .claude/skills/** re-included)
.claude/keys/
.claude/settings.local.json
data/whale_wallets.json
data/memetrans/
data/whale_wallets_pending.json
node_modules/
package.json, package-lock.json
.DS_Store
session_outputs/
```

Good coverage. Secrets and venv artifacts excluded. `__pycache__` present
on disk (confirmed `.Scripts/__pycache__`, `./services/__pycache__`,
`./__pycache__`) but correctly gitignored.

---

## Tracked file inventory

```
git ls-files | wc -l
```

**123 tracked files**. Surprising-in-a-good-way — the repo is lean.

Top 20 by size (bytes):

```
3,578,158  js/main.js.map         ← orphan, being deleted this session
  729,968  js/main.js              ← orphan, being deleted this session
  311,857  data/models/accelerated_model.pkl
  118,563  services/signal_aggregator.py
  115,693  services/dashboard_api.py
   95,078  services/bot_core.py
   87,463  AGENT_CONTEXT.md
   69,873  services/signal_listener.py
   61,031  MONITORING_LOG.md
   59,557  services/governance.py
   48,135  services/ml_engine.py
   46,323  .claude/skills/skill-creator/eval-viewer/viewer.html
   45,840  dashboard/dashboard.html
   43,448  services/nansen_client.py
   41,858  dashboard/dashboard-wallet.html
   41,286  dashboard/dashboard-analytics.html
   34,008  services/execution.py
   33,781  services/ml_model_accelerator.py
   33,653  .claude/skills/skill-creator/SKILL.md
   29,519  .claude/skills/mcp-builder/reference/node_mcp_server.md
```

Nothing else tracked tops 30KB.

---

## Size deltas

**Today's cleanup (js/ deletion):**

- Before: 123 tracked files, ~4.2MB leading two entries (js/main*.map + js/main.js).
- After: 119 tracked files, same working-tree structure minus `js/`.
- Savings per Railway deploy × 8 services = **~33.6MB of repeated upload
  avoided per full redeploy wave**.
- Savings per local clone = **~4.2MB** one-time.

**If 30 root-level session report `.md` files were archived later:**

- Estimated ~500KB additional savings.
- Bigger gain: root directory visibly cleaner; reading tree-view becomes
  useful again.

**If `data/models/*.pkl` were moved out of git:**

- Would save ~300KB in git tree.
- NOT proposed. The ML engine loads these on startup; Railway deploys
  currently ship them via git. Moving to a bucket (S3/GCS) would require
  bootstrap code in the ML engine and credentials. Out of scope.

---

## Untracked mass sitting next to the repo (NOT in deploys)

These are on Jay's dev machine but gitignored or untracked, so Railway
never sees them:

```
18MB    img/       (Satoshi theme stock images)
12MB    share/     (Satoshi theme shared assets)
1.9MB   css/       (Satoshi theme CSS bundles)
612KB   pages/     (Satoshi theme pages)
458KB   svg/       (Satoshi theme icons)
264KB   components/ (Satoshi theme components)
162MB   data/       (ML training data — partially tracked)
64KB    catboost_info/  (training telemetry — gitignored)
75MB    .git/       (repo history — not deployed)
```

**Total untracked template weight: ~33MB** (see `DASHBOARD_REDESIGN_2026_04_19.md`
for reuse assessment).

None of this is in the deploy upload.

---

## `.dockerignore` recommendation

**Do not add a `.dockerignore` right now.** Nixpacks builds ignore it.
If Jay ever migrates to a custom `Dockerfile`, adding a `.dockerignore`
would then be worth doing:

```
.git
.claude
docs
*.md
!README.md
tests/
scripts/
data/models/*.pkl   # if models move to a bucket
```

That would shrink the Docker image build context by roughly 75MB (mostly
`.git/`). For a Nixpacks pipeline, the equivalent is additions to
`.gitignore` — but that's the wrong lever because it would remove those
files from version control entirely.

Practical answer: **current .gitignore is correct. Nixpacks is fine. No
.dockerignore needed unless the build pipeline changes.**

---

## `requirements.txt` audit (static only, not validated)

I did not run a tool like `pipreqs` or `pip-audit` this session. Candidates
worth investigating in a dedicated session:

- Packages that appear in `requirements.txt` but do NOT appear in any
  `import` statement across `services/`, `scripts/`, `main.py`.
- Duplicated transitive deps (e.g. if both `requests` and `httpx` are
  pinned and only one is used).

**Do not remove any dep based on static analysis alone.** Several services
import modules only under specific runtime conditions (e.g. `lightgbm` under
`LGB_ENABLED=true`). A proper audit needs runtime coverage.

---

## Action summary

- ✅ This session: delete `js/` orphans. ~4.2MB × 8 services every full
  redeploy wave.
- 📋 Next session candidate: archive 30 root-level report `.md` files to
  `docs/archive/`. Low effort, modest weight gain, high organization gain.
- ❌ Do not add `.dockerignore` (Nixpacks ignores it).
- 📋 Future: requirements.txt audit with a tool that does runtime
  introspection. Not this session.
- ❌ Do not move `data/models/*` out of git without ML engineer signoff.

---

## Deploy-discipline reminder

From CLAUDE.md: **"Deploy discipline — no duplicate deploys."** Railway
auto-deploys on `git push`. This session pushes ONCE at the very end.
No `railway up` calls. Verified.
