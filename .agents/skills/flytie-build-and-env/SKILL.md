---
name: flytie-build-and-env
description: >
  Use when setting up flytie from a fresh clone, troubleshooting install
  failures, configuring pre-commit hooks, resolving WeasyPrint / Pango native
  library errors on macOS or Linux, diagnosing a stale editable install,
  reproducing CI locally, or working inside a Cowork agent session where the
  repo is a FUSE mount. Covers the full environment from zero: Python version
  floor, venv, extras variants, hook registration, the verification ladder
  with expected outputs, and every known setup trap.
---

# flytie — Build and Environment Runbook

**Sibling skills** — this skill covers environment setup only.
- `flytie-change-control` — change classes, quality gates, what blocks a merge
- `flytie-debugging-playbook` — symptom-to-triage for runtime failures
- `flytie-run-and-operate` — CLI anatomy, `flytie init`, release runbook
- `flytie-diagnostics-and-tooling` — cold-start timing, importtime, coverage

---

## 1. Prerequisites

- Python **3.10 or newer** (as of 2026-07-02, v0.2.1). CI matrix: 3.10 / 3.11 / 3.12.
  The `>=3.10` floor was deliberately lowered from the spec's original 3.11+
  to broaden compatibility; `pyproject.toml` `requires-python = ">=3.10"`.
- git
- For PDF export only: native Pango/Cairo libraries (see §3).

---

## 2. Fresh-clone happy path

```bash
git clone https://github.com/finngidden/flytie.git
cd flytie
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### Install variants

```bash
# Full development install (recommended for contributors)
pip install -e ".[dev,pdf,ai]"

# Dev tooling only, no PDF or AI (skip if Pango unavailable)
pip install -e ".[dev,ai]"

# Core CLI only (no dev tooling, no PDF, no AI)
pip install -e "."
```

The `[dev]` extra installs: `pytest`, `pytest-cov`, `ruff`, `mypy`,
`pre-commit`, `syrupy` (snapshot testing), and `pdfminer.six` (used in tests
to assert PDF content — without it, PDF test modules skip).

The `[pdf]` extra installs `weasyprint`. It also needs native OS libraries;
see §3 before running this.

The `[ai]` extra installs the `anthropic` SDK.

### Register pre-commit hooks (do this once, after install)

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Both hook types must be named explicitly. Installing only `pre-commit` skips
the pre-push stage that runs pytest; installing only `pre-push` skips the
formatter.

Hook stages:

| Stage    | Fires on        | Does                                                     |
|----------|-----------------|----------------------------------------------------------|
| commit   | `git commit`    | `ruff format` + `ruff check --fix` + hygiene checks     |
| pre-push | `git push`      | `COLUMNS=80 pytest -q -p no:cacheprovider --tb=line`    |

Commit-stage hooks are auto-fixing. If `ruff format` rewrites a file, the
commit aborts — re-stage the changed file and re-commit. This is expected
behavior.

**Never use `--no-verify` as a habit.** The hooks are a contract, not a
suggestion. Use it only in a genuine emergency and fix the underlying issue
before merging.

---

## 3. Native dependency matrix (WeasyPrint / PDF)

WeasyPrint loads Pango, Cairo, and GdkPixbuf via ctypes. These are OS-level
libraries, not Python packages.

```bash
# macOS — install BEFORE pip install "flytie[pdf]"
brew install pango

# Debian / Ubuntu (matches ci.yml)
sudo apt-get update
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0

# Fedora / RHEL
sudo dnf install pango
```

**macOS SIGSEGV trap.** On some macOS setups — specifically Anaconda Python
combined with Homebrew Pango — `import weasyprint` triggers a SIGSEGV that
kills the interpreter. A `try/except ImportError` cannot catch SIGSEGV, so
flytie uses a subprocess probe pattern: `subprocess.run([sys.executable, "-c",
"import weasyprint"])` and checks the exit code. If the probe exits non-zero,
the entire PDF test module skips cleanly.

User fix: use a consistent toolchain. Either brew-installed Python with
brew-installed Pango, or skip `[pdf]` entirely and use `flytie export --html`
(no native dependencies — Jinja2 is in core).

Without Pango installed, `pip install "flytie[pdf]"` succeeds but `flytie
export <name>` raises `PDFDependencyError` with an install hint at runtime.

---

## 4. Verification ladder (expected outputs as of 2026-07-02, v0.2.1)

Run these after install to confirm everything is wired up.

```bash
flytie --version
```
Expected: `flytie 0.2.1`

```bash
ruff format --check src tests
```
Expected: `N files already formatted` (exit 0, no diff)

```bash
ruff check src tests
```
Expected: `All checks passed!` (exit 0)

```bash
mypy src
```
Expected: `Success: no issues found in 30 source files` (exit 0)

```bash
pytest -m smoke
```
Expected: **5 passed** in ~2 s. PDF test modules skip if `[pdf]` is absent
(2 skipped lines in output — this is correct). Exactly 5 tests carry the
`smoke` marker: init success, add+list round-trip, view, shop dedupe, and
export-db→import-db round-trip.

```bash
COLUMNS=80 pytest -q
```
Full suite: **380 passed, 5 skipped**, 383 items collected (all skips are
PDF-related, expected without `[pdf]`). The math: 383 collected = 380 passed +
3 inline skips; two additional PDF modules skip at module level, so the summary
line reports 5 skipped. Runtime ~40 s.

Cold-start budget: `flytie --version` best-of-5 must be under 600 ms (spec
NFR §4). Baseline in sandbox: ~240 ms best-of-3. Heavy deps (`weasyprint`,
`anthropic`, `alembic`) stay lazy; a new top-level import of any of them breaks
this gate. Diagnose: `python -X importtime -m flytie --version 2>importtimes.log`
(full importtime walkthrough: `flytie-diagnostics-and-tooling` §5).

---

## 5. CI parity

Reproduce what CI runs locally:

```bash
# What the pre-push hook runs (catches Rich-wrap fragility)
COLUMNS=80 pytest -q

# Exact CI lint gates (no --fix; gate only)
ruff format --check src tests
ruff check src tests
mypy src

# Full suite with coverage (85% floor enforced)
pytest --cov=src/flytie --cov-report=term-missing
```

CI matrix (`.github/workflows/ci.yml`): Ubuntu, Python 3.10 / 3.11 / 3.12.
CI installs `libpango-1.0-0 libpangoft2-1.0-0` before the pip step so the
PDF path is exercised in CI even when it skips locally.

Coverage floor: `fail_under = 85` in `[tool.coverage.report]`. Current real
coverage is 89.2% in a sandbox without `[pdf]` extras (weasyprint absent drags `pdf/export.py`); higher with all extras installed as in CI; the enforced floor is 85%. If a change drops below 85%, CI fails with:
`FAIL Required test coverage of 85% not reached`. Run
`pytest --cov=src/flytie --cov-report=term-missing` locally, read the
missing-lines column, add tests before pushing.

---

## 6. Known traps

| Symptom | Cause | Fix |
|---------|-------|-----|
| `flytie: command not found` after `pip install -e .` | Entry-point not on PATH | Activate the venv: `source .venv/bin/activate`. Or use `python -m flytie`. |
| Formatter or lint failures appear in CI but not locally | pre-commit hooks not installed | `pre-commit install --hook-type pre-commit --hook-type pre-push` |
| `pytest` picks up wrong version of `flytie` | Stale editable install (e.g., after moving the repo) | `pip uninstall -y flytie && pip install -e .` |
| PDF tests unexpectedly skip | `pdfminer.six` absent (needed for PDF content assertions) OR `weasyprint` not installed | Run `pytest -rs` to read skip reasons. Install `[dev]` for pdfminer; install `[pdf]` + native Pango for weasyprint. |
| Test fails only in CI at `COLUMNS=80`, passes locally | Rich output wraps at narrow terminal width, breaking substring assertions | Run `COLUMNS=80 pytest` locally to reproduce. See `flytie-debugging-playbook` for the COLUMNS trap. |
| `import weasyprint` kills the interpreter (SIGSEGV on macOS) | Anaconda Python + Homebrew Pango binary mismatch | Switch to a non-Anaconda Python, or skip `[pdf]` and use `--html`. |
| `mypy src` reports errors in migration files | Alembic migration stubs aren't type-checked | These are excluded via `ignore_missing_imports = true`; if new errors appear in `src/flytie/`, they're real. |
| New third-party package causes import-sort thrash between dev machine and CI | Package not in `known-third-party` list | Add to `[tool.ruff.lint.isort] known-third-party` in `pyproject.toml`. |

**Python 3.10 floor note.** The spec originally said 3.11+; it was deliberately
lowered to 3.10. `pyproject.toml` and the CI matrix both reflect 3.10 as the
floor. Do not raise this without a spec update and a migration plan.

**The `*_old.py` fossils.** Eight `*_old.py` paths are tracked in git
(`src/flytie/cli_old.py`, `src/flytie/render_old.py`,
`src/flytie/core/{parsing,shop,versions}_old.py`, `src/flytie/migrations/env_old.py`,
`tests/test_patterns_repo_old.py`, `tests/test_review_fixes_old.py`) — so fresh
clones get all eight, inert and excluded from pytest (`addopts --ignore=...`),
ruff (`[tool.ruff].exclude`), and coverage (`omit = ["src/flytie/*_old.py", ...]`).
As of 2026-07-02 all eight are physically present in the working copy
(verify: `find src tests -name "*_old.py"`). Their inodes are FUSE-poisoned in
Cowork sandbox sessions — unlink fails there. Do not delete or
'fix' any of them without maintainer sign-off. Full incident chronicle:
`flytie-failure-archaeology`.

---

## 7. Appendix: Cowork agent sessions (FUSE mount environment)

This section is for engineers or agents running inside a Cowork session, where
the repo is mounted into a Linux sandbox via FUSE. The setup differs from a
plain git clone in important ways. **If you are working from a plain terminal
on macOS or Linux, stop here — this appendix does not apply.**

**Shell-timeout batching.** Sandbox shells often cap a single command at ~45 s,
which the full suite plus coverage can exceed. Run pytest in file batches for
interim verification (each batch with the cache-redirect flags), but the single
full-suite `pytest --cov` run remains mandatory before any tag — if the sandbox
can't complete it, say so in the report rather than substituting batch results.

### How the environment differs

- The repo is a FUSE mount. Host file tools (`Read`, `Edit`, `Glob`, `Grep`)
  and sandbox bash commands see the same files but through different path
  prefixes. The sandbox mount path varies per session — check your session's
  mount mapping, do not hardcode absolute paths.
- Bash runs in an isolated Linux sandbox. The sandbox is **ephemeral** —
  reinstall on every session start.
- `pip` needs `--break-system-packages` because the sandbox Python is the
  system Python: `pip install --break-system-packages -e ".[dev,ai]"`
  (skip `[pdf]` — WeasyPrint is not installed and the PDF tests skip cleanly).
- Installed scripts land in `~/.local/bin`. Add to PATH before running:
  `export PATH="$HOME/.local/bin:$PATH"`

### Redirect tool caches off the FUSE mount

SQLite-backed caches stored on the FUSE mount hit `disk I/O error`. Redirect:

```bash
# pytest — disable cache plugin entirely
pytest -p no:cacheprovider

# mypy — redirect cache dir
mypy src --cache-dir /tmp/.mypy_cache

# coverage — redirect data file (or run from /tmp)
# Note: --cov with data file on the mount may raise PermissionError.
# Run the full suite without coverage for quick checks:
COLUMNS=80 pytest -p no:cacheprovider -q
```

### FUSE inode deadlock: `OSError: [Errno 35] Resource deadlock avoided`

**First move: ask the user to re-open the project folder.** The Cowork mount
refreshes with new inodes; the deadlock clears project-wide for one user
action. Then re-run `pip install --break-system-packages -e ".[dev,ai]"` to
re-point the editable install.

For the full recovery ladder (single-file `cp`-to-`/tmp` workaround, heavy-edit-burst
strategy, and the in-place reconstruction last resort), see the owner:
`flytie-debugging-playbook` (A1).

### Verification ladder in the sandbox

```bash
export PATH="$HOME/.local/bin:$PATH"

# Install (once per session)
pip install --break-system-packages -e ".[dev,ai]"

# Verify entry point
flytie --version
# Expected: flytie 0.2.1

# Smoke (fast, ~3 s)
pytest -m smoke -p no:cacheprovider
# Expected: 5 passed, 2 skipped (PDF skips expected)

# Lint + type check
ruff format --check src tests
ruff check src tests
mypy src --cache-dir /tmp/.mypy_cache

# Full suite (no coverage — avoids .coverage PermissionError on mount)
COLUMNS=80 pytest -p no:cacheprovider -q
# Expected: 380 passed, 5 skipped (383 collected)
```

---

## Provenance and maintenance

**Date:** 2026-07-02. **Version:** v0.2.1.

**Sources verified:** `README.md`, `CONTRIBUTING.md`, `pyproject.toml`,
`.pre-commit-config.yaml`, `.github/workflows/ci.yml`, live sandbox runs.

**Re-verify commands** (run after any release to update this skill):

```bash
flytie --version                                      # check version string
pytest --collect-only -q | tail -5                    # update test counts
ruff format --check src tests; ruff check src tests   # confirm clean
mypy src --cache-dir /tmp/.mypy_cache                 # confirm source file count
git ls-files | grep _old                              # check fossil list unchanged
```
