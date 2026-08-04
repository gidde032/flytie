---
name: flytie-debugging-playbook
description: >
  Operational triage guide for flytie failures. Covers the symptom-to-root-cause
  path for every failure mode documented to have recurred or likely to recur:
  file-read deadlocks (FUSE/Cowork), Rich output wrapping on CI, WeasyPrint
  SIGSEGV on macOS, ruff import-order flip-flop, mypy/pytest disk-I/O errors,
  missing-table regressions, incompatible DB schema, missing editable install,
  silent test skips, Rich markup square-bracket escaping, exact-count assertion
  drift, and cold-start performance gate failures. Use when: a test that passes
  locally fails on CI with an assertion on CLI output; "OSError: [Errno 35]
  Resource deadlock avoided"; "no such table: patterns"; exit code 4 /
  incompatible environment; "ModuleNotFoundError: No module named 'flytie'";
  SIGSEGV during pytest collection; "I001" ruff import-order error on CI only;
  "sqlite3.OperationalError: disk I/O error"; tests silently skipping;
  "[NEW]" badge not appearing in Rich output; flytie --version takes >600ms.
---

# flytie Debugging Playbook

**Audience:** a mid-level engineer or a Sonnet-class model working from a plain git
clone and a terminal. This is a runbook, not a design document.

**Scope (as of 2026-07-02, v0.2.1):** recurring or structurally likely failure
modes with documented root causes. For settled investigations and historical
dead ends, see the sibling skill **flytie-failure-archaeology**. For the
quality gates that must pass before a tag, see **flytie-change-control**.

## When NOT to use this skill

| You want | Go here instead |
|---|---|
| To understand quality gates and what "must pass before tag" means | flytie-change-control |
| To read about a past investigation that is now closed | flytie-failure-archaeology |
| To understand architecture decisions or invariants | flytie-architecture-contract |
| To set up the dev environment from scratch | flytie-build-and-env |
| To understand how to run or operate flytie | flytie-run-and-operate |

---

## 1. First-response protocol

Before diving into a specific failure, run these three commands in order. They
take under 60 seconds combined and will answer 80% of "what is broken" questions.

### Step 1 — Collect environment facts

```bash
flytie info
```

`flytie info` is designed to work against an uninitialised DB, an incompatible
DB, and a missing DB (see `src/flytie/cli.py`, the `info` command). It reports
resolved paths and schema revision without calling `_open_db()`, so it succeeds
even when every other command fails with exit code 4. The output tells you:
- the DB path being used (wrong path = wrong env vars)
- whether the DB is initialised and schema-complete
- the Alembic revision stamped in the DB
- whether there is a compatibility mismatch

### Step 1b — Check whether the battle is already settled

Before deep diagnosis, match the symptom against `flytie-failure-archaeology`.
If it corresponds to a settled finding, the archaeology entry names the intended
contract, the root cause, and the pinning test — you are looking at a regression
of known behavior, not a new investigation.

### Step 2 — Sanity with smoke

```bash
pytest -m smoke
```

Five tests, ~1-3 seconds (verified against v0.2.1: 1.33 s). If any fail, you
have a regression in the core init/add/list/view/shop/portability surface.
The five smoke tests are:

| Test | File |
|---|---|
| `test_init_creates_db_file` | `tests/test_db.py` |
| `test_add_and_list_round_trip` | `tests/test_cli_commands.py` |
| `test_view_renders_pattern` | `tests/test_cli_commands.py` |
| `test_shop_dedupes_across_patterns` | `tests/test_cli_phase3.py` |
| `test_cli_import_db_round_trip` | `tests/test_portability.py` |

The regression test `tests/test_v0_1_2_fixes.py::test_smoke_marker_collects_exactly_five_happy_path_tests`
asserts this count is exactly 5. If you need to add a sixth smoke test, update
that regression test deliberately.

**Cowork sessions only:** append `-p no:cacheprovider -o cache_dir=/tmp/.pytest_cache`
to avoid `sqlite3.OperationalError: disk I/O error` from tool caches on a FUSE mount.

### Step 3 — Isolate

Once you know which tests fail and `flytie info` shows the DB state, scan the
symptom table below for the matching row. The "discriminating experiment" column
gives you the single command that confirms which failure you have.

---

## 2. Symptom-to-triage table

Grouped by surface. Each row: exact symptom → root cause → discriminating experiment → fix.

---

### Group A: Filesystem / environment

#### A1. `OSError: [Errno 35] Resource deadlock avoided` on file reads or edits

**Surface:** file reads, edits, or bash `cat`/`grep` on repo files
**When it hit:** FUSE-mount cache coherency failure during Phase 3 in a Cowork
session. Affected certain inodes; recovery attempted in-place cost ~20k tokens.
**Cowork sessions only.**

| Field | Detail |
|---|---|
| Symptom | `OSError: [Errno 35] Resource deadlock avoided` on read or edit |
| Root cause | FUSE mount cache-coherency: inode the sandbox cached is stale or poisoned after a re-open |
| Discriminating experiment | `cp suspect_file /tmp/copy && cat /tmp/copy` — if that works, the original inode is poisoned, not the file |

**Fix ladder (attempt in order — stop when it clears):**

1. **Re-open the project folder in Codex** (cheapest, clears project-wide) then
   run `pip install -e .` to re-point the editable install. One user action fixes
   all affected inodes.
2. If only a single file is blocked: `cp src/flytie/foo.py /tmp/foo.py`, work on
   the copy, write back via the shell.
3. Last resort: mv the affected file aside and write a fresh copy from scratch.
   This is the in-place recovery playbook — historically expensive (~20k tokens
   when engaged first instead of last).

**Note:** eight `*_old.py` stragglers from the Phase 3 FUSE recovery are tracked
in git (a fresh clone gets all eight), inert, and excluded by `pyproject.toml`
(pytest addopts, ruff exclude, coverage omit). In the original Cowork workspace
their inodes are FUSE-poisoned, so deletion fails there. Never delete or "fix"
them without maintainer sign-off — chronicle in `flytie-failure-archaeology`.

---

#### A2. `ModuleNotFoundError: No module named 'flytie'` — or flytie resolves to wrong version

**Surface:** any `python -c "import flytie"`, `flytie` CLI, pytest
**When it hit:** common after environment churn (new venv, pip upgrade, failed install)

| Field | Detail |
|---|---|
| Symptom | `ModuleNotFoundError` or wrong `__version__` printed |
| Root cause | Stale or missing editable install |
| Discriminating experiment | `python -c "import flytie; print(flytie.__file__)"` — path outside the repo, or error, means stale install |

**Fix:**

```bash
pip uninstall -y flytie
pip install -e ".[dev,pdf,ai]"
```

---

#### A3. `sqlite3.OperationalError: disk I/O error` from mypy or pytest

**Surface:** mypy cache, pytest cache on a network or FUSE mount
**When it hit:** Cowork sandbox sessions where tool caches are on the mounted filesystem.
**Cowork sessions only.**

| Field | Detail |
|---|---|
| Symptom | `disk I/O error` during mypy or pytest startup |
| Root cause | mypy or pytest writing its cache to a path on the FUSE/network mount |
| Discriminating experiment | Check whether the error references a `.mypy_cache` or `.pytest_cache` path inside the repo |

**Fix:**

```bash
# mypy
mypy --cache-dir /tmp/.mypy_cache src

# pytest
pytest -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache
```

---

### Group B: Tests / CI

#### B1. Test passes locally, fails on CI — substring not found in CLI output

**Surface:** CI assertion on CLI output (`assert "X" in result.stdout`)
**When it hit:** two pre-existing tests failed on the first CI run after v0.1.1 shipped.
Rich/Typer wraps output at ~80 columns; the asserted phrase landed across the wrap point.

| Field | Detail |
|---|---|
| Symptom | `AssertionError: assert "JSON parse error" in r.stdout` — passes locally, fails in Actions |
| Root cause | Rich/Typer terminal-width wrapping; CI defaults to ~80 cols; phrase splits across the line break |
| Discriminating experiment | `COLUMNS=80 pytest -q tests/test_my_file.py` — if the assertion fails now, you have reproduced the CI environment |

**Fix (in order of preference):**

1. **Already mitigated for new tests.** `tests/conftest.py` has an `autouse=True`
   fixture `_wide_cli_runner_env` (name verified) that patches `CliRunner.invoke` to
   default `env={"COLUMNS": "200"}` for every test. Tests using `CliRunner()` directly
   or the `cli_runner` fixture get this for free.

2. **Normalize whitespace before asserting** (belt-and-suspenders for long phrases):
   ```python
   out = " ".join(result.stdout.split())
   assert "JSON parse error" in out
   ```

3. **Reproduce CI locally:** the pre-push hook runs pytest at `COLUMNS=80`. You can
   also run `COLUMNS=80 pytest` manually before pushing.

Do not remove `_wide_cli_runner_env` to "fix" a test — it is the systemwide remedy.

---

#### B2. Hard SIGSEGV during pytest collection on macOS (WeasyPrint)

**Surface:** pytest collection crashes the process before any tests run
**When it hit:** macOS environments mixing Anaconda Python and Homebrew Pango/Cairo.
A bare `try/except` around `import weasyprint` cannot catch SIGSEGV — the crash
happens at the OS level during `dlopen`, before any Python exception propagates.

| Field | Detail |
|---|---|
| Symptom | pytest collection dies mid-stream with no Python traceback; process receives SIGSEGV |
| Root cause | Incompatible native library versions: Homebrew Pango vs Anaconda Python's bundled glib/cairo |
| Discriminating experiment | `python -c "import weasyprint"` in a subprocess (`subprocess.run([sys.executable, "-c", "import weasyprint"], capture_output=True)`) — a SIGSEGV signal in the returncode means native-lib clash |

**User-facing fix:** `brew install pango`

**Test-authoring rule:** any test file that imports WeasyPrint must use the subprocess
probe pattern. Never use a bare `import weasyprint` at module level. The canonical
pattern is in `tests/test_pdf_export.py` and `tests/test_cli_export.py`:

```python
import subprocess, sys
_pdf_probe = subprocess.run(
    [sys.executable, "-c", "import jinja2; import weasyprint"],
    capture_output=True,
    timeout=20,
)
if _pdf_probe.returncode != 0:
    pytest.skip(
        f"PDF tests skipped — WeasyPrint not safely loadable (probe exit "
        f"{_pdf_probe.returncode}). Last stderr: "
        f"{_pdf_probe.stderr.decode(errors='replace')[-300:]!r}",
        allow_module_level=True,
    )
```

Do not use `pytest.importorskip` for WeasyPrint — `importorskip` cannot catch SIGSEGV.

---

#### B3. `ruff check` fails I001 (import order) on CI but not locally

**Surface:** CI lint step; typically appears after adding a new dependency
**When it hit:** ruff's isort heuristic diverged between local and CI when explicit
first/third-party lists were missing from `pyproject.toml`.

| Field | Detail |
|---|---|
| Symptom | I001 import-order error on CI only; `ruff check --fix` flip-flops on re-run |
| Root cause | ruff/isort first-party/third-party classification diverges when not pinned to an explicit list |
| Discriminating experiment | `ruff check --diff src/flytie/` locally — if no I001, classification differs; inspect `[tool.ruff.lint.isort]` in `pyproject.toml` |

**Fix:** the lists are already set in `pyproject.toml` (verified):

```toml
[tool.ruff.lint.isort]
known-first-party = ["flytie"]
known-third-party = ["alembic", "sqlalchemy", "typer", "rich", "pydantic",
    "anthropic", "weasyprint", "jinja2", "platformdirs", "tomli", "tomli_w"]
```

If the error recurs after adding a new third-party dependency, add it to
`known-third-party` in the same commit as the dependency itself.

---

#### B4. Tests silently skipping — coverage drops without explanation

**Surface:** `pytest --cov` shows unexpectedly low coverage; tests disappear
**When it hit:** `pdfminer.six` was missing from the `[dev]` extra for the entire
project lifetime. 22 PDF-content assertion tests silently skipped because
`pytest.importorskip("pdfminer.high_level")` masked the missing dep.

| Field | Detail |
|---|---|
| Symptom | Fewer tests run than expected; coverage drops after adding features |
| Root cause | `pytest.importorskip` masking a missing dev dependency that should be mandatory |
| Discriminating experiment | `pytest -rs` — read skip reasons carefully. "no module named X" on a dep that should be in `[dev]` is a packaging gap |

**Rule:** `pytest.importorskip` is correct for optional environments (user opted out
of `[pdf]`, so WeasyPrint is not installed). It is wrong for dependencies that belong
in `[dev]` and should be available to every contributor. If a dev dep is missing
from `pyproject.toml [project.optional-dependencies] dev`, add it, then remove the
`importorskip` guard.

---

### Group C: CLI / runtime

#### C1. `no such table: patterns` after `flytie init`

**Surface:** any command that queries the DB after an interrupted `init`
**When it hit:** Phase 6 CRITICAL finding. Alembic can write `alembic_version` and
exit cleanly while the real DDL tables are never created. Subsequent `init` calls
see the stamp and no-op, leaving a permanently unusable DB.

| Field | Detail |
|---|---|
| Symptom | `OperationalError: no such table: patterns` after a successful-looking `flytie init` |
| Root cause | Stamped-but-empty DB: `alembic_version` row exists but `patterns` table does not |
| Discriminating experiment | `sqlite3 ~/.local/share/flytie/flytie.sqlite3 ".tables"` — if only `alembic_version` appears, you have the bug |

**Fix:** the current `src/flytie/db.py` `create_schema` method handles this automatically.
After `upgrade_to_head`, it calls `schema_is_complete()` — which checks
`inspect(engine).has_table("patterns")` — and falls through to `_build_schema_directly()`
if the table is absent. So `flytie init` on a stamped-but-empty DB will self-repair
without `--force` and without data loss.

If you see this error on current code, it is a regression. Check `src/flytie/db.py`
`create_schema` to confirm the repair path is intact. The regression test is
`tests/test_review_fixes_phase6.py::test_create_schema_repairs_stamped_but_empty_database`.

---

#### C2. Exit code 4 / "incompatible environment" message

**Surface:** any command that calls `_open_db()` (everything except `flytie info` and `flytie init`)
**When it hit:** user upgraded flytie, ran `flytie init` (which stamped a new Alembic
revision), then downgraded. The downgraded build's bundled migrations do not know the
newer revision.

| Field | Detail |
|---|---|
| Symptom | Command fails immediately; exit code 4; stderr: "Database is at Alembic revision X, which this build of flytie does not recognize" |
| Root cause | `validate_compatibility()` in `src/flytie/db.py` found the DB's revision absent from `known_revisions()` |
| Discriminating experiment | `flytie info` — reports the revision without failing; compare it to what `flytie --version` prints |

**Fix (from the error message, verified in `src/flytie/db.py` `validate_compatibility`):**

```bash
# Option 1: install the newer flytie that stamped the DB
pip install "flytie>=X.Y.Z"

# Option 2: export/wipe/reimport (run export on the NEWER install first)
flytie export-db --out backup.json
pip install "flytie==X.Y.Z"    # downgrade
flytie init --force
flytie import-db backup.json
```

Exit codes (verified in `src/flytie/cli.py`):
- 1 — data error (pattern not found, constraint violation)
- 2 — input error (bad flags, parse failures, Pydantic validation)
- 3 — missing dependency (WeasyPrint not installed for PDF export)
- 4 — incompatible environment (DB schema newer than this build knows)

---

#### C3. Rich renders `[NEW]` badge wrong, or markup is swallowed

**Surface:** `flytie suggest` output; any code passing square-bracket text to Rich
**When it hit:** documented in `src/flytie/render.py`. Rich parses `[word]` as a
markup tag; `[NEW]` without escaping disappears or renders as an unknown style.

| Field | Detail |
|---|---|
| Symptom | Badge text missing from `flytie suggest` output; square-bracket text silently dropped |
| Root cause | Rich markup parser consumes `[NEW]` as a style tag |
| Discriminating experiment | Print raw `result.stdout` in a test and check whether the bracket sequence appears |

**Fix:** escape the opening bracket with a backslash (verified in `src/flytie/render.py`):

```python
# Wrong — Rich will try to apply "NEW" as a style:
badge = "[bold green][NEW][/bold green]"

# Correct — \[ renders as a literal [:
badge = r"[bold green]\[NEW][/bold green]"
```

Apply this pattern to any square-bracket text you pass into Rich markup strings.

---

#### C4. Exact-count assertion failures after adding a warning or output line

**Surface:** tests asserting `len(result.warnings) == N` or `.count("X") == N`

| Field | Detail |
|---|---|
| Symptom | `AssertionError: assert 1 == 2` on a count that was correct before your change |
| Root cause | A new warning, info line, or message was added to the surface you touched; old test expected the old count |
| Discriminating experiment | `grep -n "== 1\|== 2\|== 0" tests/test_*` for the command surface you changed |

**Fix:** find all exact-count assertions on that surface and update them in the same
commit. Add a comment explaining what each counted item represents. The full lesson
(the "grep before you commit a new warning" rule and its v0.2.1 origin) is owned by
`flytie-validation-and-qa`.

---

#### C5. Cold-start gate failure (`flytie --version` >600 ms)

**Surface:** NFR §4 gate; CI cold-start check
**When it hit:** adding a top-level import of a heavy dependency
(`weasyprint`, `anthropic`, `alembic`) pulls the full import graph at startup.

| Field | Detail |
|---|---|
| Symptom | `flytie --version` consistently takes >600 ms best-of-5 |
| Root cause | A new top-level import added to a module that loads at startup |
| Discriminating experiment | `python -X importtime -m flytie --version 2>importtimes.log` then read the log for the heaviest cumulative entries |

**Baseline (verified v0.2.1, Linux):** ~250 ms best-of-5. macOS will be higher;
the gate is 600 ms.

**Fix:** heavy dependencies must stay lazy-imported inside the function body that
needs them, not at module level. Pattern from `src/flytie/db.py`:

```python
def upgrade_to_head(self) -> None:
    from alembic import command      # lazy — stays cheap at startup
    from alembic.config import Config
    ...
```

---

## 3. Escalation rules

### Bug is fixed — is the work done?

No. A fix is not complete until a paired regression test exists. The contract: no
shipped bug ever re-surfaces silently. See **flytie-validation-and-qa** for test
conventions. Regression tests go in:

- `tests/test_review_fixes_phase{N}.py` — for bugs found during per-phase review
- `tests/test_v0_X_Y_fixes.py` — for bugs found during hardening passes

The test docstring must name the reviewer (if applicable) and severity.

### You found a NEW failure mode not in this playbook

1. Add it here (to the playbook) so the next person finds it.
2. Add a record to **flytie-failure-archaeology** with the full investigation
   history, dead ends, and resolution.

### Full quality gate before any tag

```bash
ruff format --check src tests
ruff check src tests
mypy src
pytest --cov=src/flytie --cov-report=term-missing   # 85% floor
pytest -m smoke                                      # exactly 5 tests, <5s
```

Cold-start: `flytie --version` best-of-5 under 600ms.
Diagnose slow starts with `python -X importtime -m flytie --version 2>importtimes.log`.

**Hard nevers (ratified 2026-07-02):**
- No `git push --no-verify`, `git commit --no-verify`, force-push, or re-tag
- No weakening a quality gate to make it pass: never lower the coverage floor,
  widen the coverage omit-lists, loosen the smoke exact-count, or relax the
  cold-start budget. Any gate change requires maintainer sign-off (full ratified
  list in `flytie-change-control`).
- No live Anthropic API calls in tests (use fake streamers only)
- Subagents/automation must never run mutating git commands

---

## Provenance and maintenance

**Written:** 2026-07-02 | **Version:** v0.2.1

**Sources consulted and verified:**
- `src/flytie/cli.py` — `_open_db` exit code 4 (line 104), `info` command design, exit code table
- `src/flytie/db.py` — `create_schema` self-repair path, `schema_is_complete`, `validate_compatibility`
- `tests/conftest.py` — `_wide_cli_runner_env` autouse fixture verified by name and mechanism
- `tests/test_pdf_export.py` — subprocess probe pattern verified (lines 19-37)
- `tests/test_review_fixes_phase6.py` — stamped-but-empty DB regression tests confirmed
- `tests/test_v0_1_2_fixes.py` — smoke-count regression test confirmed
- `src/flytie/render.py` — `\[NEW]` escape confirmed at line 239
- `pyproject.toml` — isort known-first/third party lists confirmed
- `CONTRIBUTING.md` — pre-push hook at `COLUMNS=80`; `pdfminer.six` in `[dev]` extra
- Live smoke run (v0.2.1): `pytest -m smoke` → 5 passed, 1.33 s, 2 PDF tests skipped as expected
- Live cold-start timing: ~250 ms best-of-5 (Linux sandbox)

**Re-verification commands (run when flytie version changes):**

```bash
# Smoke count still exactly 5?
pytest -m smoke -v 2>&1 | grep -E "passed|failed|error"

# Autouse fixture still named _wide_cli_runner_env?
grep -n "autouse=True" tests/conftest.py

# Exit code 4 still in cli.py _open_db?
grep -n "code=4" src/flytie/cli.py

# \[NEW] escape still in render.py?
grep -n 'NEW' src/flytie/render.py

# isort lists in pyproject.toml?
grep -A2 "known-third-party" pyproject.toml
```

*Deeper reading, if present in your working copy:* `ai-development-practices/assessment.md §4`
covers each of these failure modes in narrative form. `handoff.md` "Known issues"
section has current-state triage for any not-yet-resolved items.
