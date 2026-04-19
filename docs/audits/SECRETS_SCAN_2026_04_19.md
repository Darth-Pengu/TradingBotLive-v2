# ZMN tracked-files secrets scan

**Date:** 2026-04-19
**Scope:** all files in `git ls-files` output. Untracked files (.env,
.env.local, local caches, Scripts/full_report.py + Scripts/check_state.py
which Jay deleted this morning) are out of scope — they're not in git
history.
**Method:** regex patterns tuned to catch the common high-signal shapes
(URL-embedded credentials, hardcoded API key assignments, PEM keys,
long base-encoded strings outside `os.getenv()` calls).

## Result

**Clean.** No tracked file contains a hardcoded secret.

## Patterns checked

### 1. URL-embedded credentials

```
git ls-files | xargs grep -lE 'postgresql://[^"]+:[^"]+@|redis://[^"]+:[^"]+@|sk-[A-Za-z0-9]{40,}|bearer\s+[A-Za-z0-9]{20,}'
```

One match — `.env.example:39`:

```
DATABASE_URL=                      # PostgreSQL — Railway auto-injects. Format: postgresql://user:pass@host:port/db
```

**Verdict: false positive.** This is documentation of the expected URL
format (literal `user:pass` placeholder, not a real credential). The
env var itself is empty. Safe.

No other hits across 119 tracked files.

### 2. Hardcoded API key / token / password assignments

```
git ls-files '*.py' | xargs grep -nE "(API_KEY|SECRET|PASSWORD|TOKEN|PRIVATE_KEY)\s*=\s*['\"][^'\"$][^'\"]{15,}['\"]"
  | grep -vE "os\.(getenv|environ)|getenv\(|environ\[|env\[|os\.environ\.get"
```

**Zero hits.** Every reference to API keys, secrets, passwords, tokens,
and private keys in tracked Python files goes through `os.getenv(...)` or
an equivalent environment read. This is the correct pattern.

### 3. PEM keys / long base-encoded strings (non-md files)

```
git ls-files | xargs grep -lE "(-----BEGIN [A-Z ]*PRIVATE KEY-----|base58|[A-Za-z0-9]{60,})"
  | grep -vE "\.md$|js/"
```

Candidate files surfaced: `requirements.txt`, `services/execution.py`,
`services/telegram_listener.py`, `services/treasury.py`.

Follow-up grep on each with `os.getenv|os.environ` filter applied:
**zero hits survive.** The long strings in these files are legitimate:

- **`services/execution.py`** — Solana program IDs and token mint
  addresses (base58-encoded, 32-44 chars typical; some longer hashes). No
  private keys.
- **`services/telegram_listener.py`** — session-name and auth-flow
  constants sourced from env.
- **`services/treasury.py`** — token mint constants.
- **`requirements.txt`** — package hashes (`sha256:...`). Not secrets.

No PEM keys, no raw private keys, no committed base58-encoded keypair
files (`.claude/keys/` is gitignored and remains empty).

## What was deleted this morning (context, not findings)

Jay deleted `Scripts/full_report.py` and `Scripts/check_state.py` earlier
today because both contained hardcoded Redis + Postgres credentials. Those
files were **never committed** — `git log --all -- Scripts/full_report.py`
confirms no history. Nothing to rotate, nothing to scrub from history.

## Preventive recommendations (NOT acted on this session)

These are suggestions Jay can queue for a future session:

1. **Pre-commit hook** using `detect-secrets` or `gitleaks` to block
   commits that contain URL-embedded credentials or high-entropy strings.
   Install:
   ```
   pipx install detect-secrets
   detect-secrets scan > .secrets.baseline
   ```
   Then add a pre-commit config. ~30-min session.

2. **GitHub secret scanning** — if `Darth-Pengu/TradingBotLive-v2` is
   public, enable GitHub's native secret scanning in the repo settings.
   Free for public repos, paid for private. No session needed — just a
   settings toggle.

3. **`.claude/keys/` re-verification** — already gitignored, already empty,
   already covered by `.gitignore` lines 18 + 19. Spot-check annually.

None of these are blockers. The repo is currently clean.

## Conclusion

Safe to commit. No secrets found in tracked files. Proceeding with Phase 4
cleanup commit and Phase 5 push as planned.
