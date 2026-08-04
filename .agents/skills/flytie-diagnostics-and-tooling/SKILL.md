---
name: flytie-diagnostics-and-tooling
description: >
  Use when verifying the flytie build is healthy before a commit, push, or
  tag. Covers every diagnostic the project uses: running the full gate
  ladder (ruff format, ruff check, mypy, pytest --cov, smoke), measuring
  cold-start against the 600 ms spec budget, checking why tests skipped,
  reading coverage output, asserting the smoke contract (exactly 5 tests
  collected), hunting cold-start regressions with importtime, and checking
  test-suite shape. Also the right skill when someone asks "is the build
  healthy?", "how do I benchmark this?", "why is coverage low?", or "why
  did some tests skip?".
---

# flytie — Diagnostics and Tooling

*As of 2026-07-02, v0.2.1.*

## When NOT to use this skill

| If you need…                               | Use instead                         |
|--------------------------------------------|-------------------------------------|
| Project environment setup / pip install    | `flytie-build-and-env`              |
| Triage a specific failure or crash         | `flytie-debugging-playbook`         |
| Pre-commit / release gate checklist        | `flytie-change-control`             |
| Quality evidence standards for a PR/audit  | `flytie-validation-and-qa`          |
| Understanding the architecture invariants  | `flytie-architecture-contract`      |

---

## Scripts in this skill

All scripts live at `.Codex/skills/flytie-diagnostics-and-tooling/scripts/`.
They locate the repo root relative to themselves via
`cd "$(dirname "${BASH_SOURCE[0]}")"/../../../..` — four levels up from
`scripts/` to the repo root. Do not move the scripts without updating that path.

Make them executable once after cloning:

```bash
chmod +x .Codex/skills/flytie-diagnostics-and-tooling/scripts/*.sh
```

---

## 1. Full gate ladder — `verify_gates.sh`

Runs all five quality gates in order. Exits non-zero on the first failure.

```bash
# Standard (developer machine):
.Codex/skills/flytie-diagnostics-and-tooling/scripts/verify_gates.sh

# CI parity — forces COLUMNS=80 so Rich-wrap fragility surfaces locally:
.Codex/skills/flytie-diagnostics-and-tooling/scripts/verify_gates.sh --narrow

# Cowork sandbox — adds cache-redirect flags (auto-detected, but explicit is fine):
.Codex/skills/flytie-diagnostics-and-tooling/scripts/verify_gates.sh --sandbox
```

**Sandbox cache flags** (applied automatically when the repo root is under `/sessions/`):
- pytest: `-p no:cacheprovider -o cache_dir=/tmp/.pytest_cache`
- mypy: `--cache-dir /tmp/.mypy_cache`
- coverage: `COVERAGE_FILE=/tmp/.coverage_flytie` (sandbox `.coverage` in repo root
  may be permission-denied due to FUSE mount constraints)

### Real output (v0.2.1, sandbox, 2026-07-02)

```
=== flytie gate ladder — repo: /sessions/.../mnt/flytie ===
  sandbox=true  narrow=false  COLUMNS=200

[1/5] ruff format --check
53 files already formatted
✔ PASS  ruff format --check

[2/5] ruff check
All checks passed!
✔ PASS  ruff check

[3/5] mypy src
Success: no issues found in 30 source files
✔ PASS  mypy

[4/5] pytest --cov (85% floor)
...  380 passed, 5 skipped, 1 warning in 35.76s
TOTAL  89%  Required test coverage of 85.0% reached. Total coverage: 89.17%
✔ PASS  pytest --cov

[5/5] pytest -m smoke
...  5 passed, 2 skipped, 378 deselected in 1.10s
✔ PASS  pytest -m smoke

=== SUMMARY ===
All 5 gates PASSED.
  ruff format --check  ✔
  ruff check           ✔
  mypy                 ✔
  pytest --cov         ✔
  pytest -m smoke      ✔
```

### Interpreting failures

| Gate | Typical cause | Fix |
|------|--------------|-----|
| ruff format | Unformatted code | `ruff format src tests` then re-stage |
| ruff check | Lint violations (unused import, isort order) | `ruff check --fix src tests` then address residuals |
| mypy | Type error in new or changed code | Read the error; `strict = true` means no implicit `Any` |
| pytest --cov | Test failures **or** coverage dropped below 85% | See §4 (Coverage reading) below |
| pytest -m smoke | One of the five happy-path tests broke | The test name identifies the surface; consult `flytie-debugging-playbook` |

---

## 2. Cold-start benchmark — `coldstart_bench.sh`

Best-of-5 timing of `flytie --version`. Uses Python for timing (portable —
macOS `date` lacks `%N` nanoseconds).

```bash
.Codex/skills/flytie-diagnostics-and-tooling/scripts/coldstart_bench.sh

# Override budget (e.g. tighten for known-fast hardware):
.Codex/skills/flytie-diagnostics-and-tooling/scripts/coldstart_bench.sh --budget-ms 400
```

### Real output (v0.2.1, sandbox, 2026-07-02)

```
=== flytie cold-start benchmark (best-of-5, budget 600 ms) ===
  repo: /sessions/.../mnt/flytie

  run 1: 271.5 ms
  run 2: 295.1 ms
  run 3: 250.8 ms
  run 4: 233.1 ms
  run 5: 227.4 ms

  Best of 5: 227.4 ms
  PASS — under 600 ms budget
```

Sandbox best-of-5: **~227 ms** (2026-07-02). The 600 ms budget is sized for
contributor machines post-warm-up (second-and-onward invocation in a shell session).

### What causes failures

The three dependencies the codebase explicitly keeps **lazy** (never at module
top level):

- `weasyprint` — loaded only inside `pdf/export.py::render_pattern_pdf()`
- `anthropic` — loaded only inside `ai/suggest.py::anthropic_streamer()`
- `alembic` — lazy inside `db.py::upgrade_to_head()` / `stamp_alembic_head()`

Adding any of these at module top level pushes best-of-5 well past 600 ms.
Diagnose with importtime (see §5 below).

---

## 3. Smoke contract — `smoke_contract.sh`

Asserts exactly 5 smoke tests are collected and the suite finishes in <5 s.
Prints the golden test inventory.

```bash
.Codex/skills/flytie-diagnostics-and-tooling/scripts/smoke_contract.sh

# Sandbox:
.Codex/skills/flytie-diagnostics-and-tooling/scripts/smoke_contract.sh --sandbox
```

### Real output (v0.2.1, sandbox, 2026-07-02)

```
=== flytie smoke-contract check ===
  repo: /sessions/.../mnt/flytie  sandbox=true

[1/2] Collecting @pytest.mark.smoke tests
5/383 tests collected (378 deselected) in 0.29s

  Collected 5 smoke test(s).

✔ PASS  exactly 5 smoke tests collected. Golden inventory:
    tests/test_cli_commands.py::test_add_and_list_round_trip
    tests/test_cli_commands.py::test_view_renders_pattern
    tests/test_cli_phase3.py::test_shop_dedupes_across_patterns
    tests/test_db.py::test_init_creates_db_file
    tests/test_portability.py::test_cli_import_db_round_trip

[2/2] Running smoke suite (budget: 5 s)
5 passed, 2 skipped, 378 deselected in 1.18s

✔ PASS  smoke suite completed in 1.50s (budget: 5s).

=== SUMMARY ===
Smoke contract: PASS
  Exactly 5 tests collected  ✔
  Suite completed in 1.50s   ✔
```

**The golden smoke inventory** (as of 2026-07-02, v0.2.1):

| # | Test | What it covers |
|---|------|----------------|
| 1 | `test_db.py::test_init_creates_db_file` | DB init success |
| 2 | `test_cli_commands.py::test_add_and_list_round_trip` | add + list |
| 3 | `test_cli_commands.py::test_view_renders_pattern` | pattern view |
| 4 | `test_cli_phase3.py::test_shop_dedupes_across_patterns` | shop + dedupe |
| 5 | `test_portability.py::test_cli_import_db_round_trip` | export-db → import-db |

**Critical warning — changing the smoke set requires deliberate action:**

If you add or remove a `@pytest.mark.smoke` marker, you MUST update
`tests/test_v0_1_2_fixes.py::test_smoke_marker_collects_exactly_five_happy_path_tests`.
That test asserts `collected == 5` and will fail CI if the count changes without
a matching assertion update. Never loosen that test silently — the exact-five
count is a spec contract (spec §7).

---

## 4. Coverage reading

```bash
pytest --cov=src/flytie --cov-report=term-missing

# Sandbox (COVERAGE_FILE keeps the data file off the FUSE mount):
COVERAGE_FILE=/tmp/.coverage_flytie \
    pytest -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache \
    --cov=src/flytie --cov-report=term-missing
```

### How to read `term-missing` output

`show_missing = true` (pyproject.toml) prints a `Missing` column with line numbers
not covered by any test. `skip_covered = true` hides modules at 100% — only modules
with gaps appear.

**Real output excerpt (v0.2.1, 2026-07-02):**

```
Name                             Stmts   Miss Branch BrPart  Cover   Missing
----------------------------------------------------------------------------
src/flytie/ai/suggest.py           171      8     62      3    95%   233-234, 236, 241...
src/flytie/cli.py                  680    101    228     29    84%   132-133, 348, 350...
src/flytie/pdf/export.py            70     30     16      4    51%   66, 71, 80-85...
...
TOTAL                             2210    193    662     90    89%

8 files skipped due to complete coverage.
Required test coverage of 85.0% reached. Total coverage: 89.17%
```

- **Cover column**: line + branch coverage combined. Floor is 85% (`fail_under = 85`).
- **Missing column**: line numbers not executed. Gaps in defensive error-path branches
  are acceptable; gaps in business logic are not.
- **`pdf/export.py` at 51%**: expected — WeasyPrint not installed in the sandbox, so
  the PDF rendering paths can't run. The WeasyPrint probe skips those test modules.
- **`cli.py` at 84%**: slightly below 85% at the file level, but coverage is measured
  at the **total** (2210 stmts), which reads 89.17%. The per-file column being below 85
  does not trigger `fail_under`.
- **Real total as of 2026-07-02**: **89.17%** (4 pp headroom above the 85% floor).
- **Headroom rule** (candidate practice): if headroom drops below ~2 percentage points
  (i.e., total coverage falls to ~87%), surface it to the maintainer before adding
  more code. Do not raise `fail_under` without the maintainer's approval.

### What the omit-list hides and why

| Pattern | Reason excluded |
|---------|----------------|
| `src/flytie/*_old.py` | FUSE-poisoned stale inodes from Phase 3 recovery — zero shipping code |
| `src/flytie/core/*_old.py` | Same |
| `src/flytie/migrations/*_old.py` | Same |
| `src/flytie/__main__.py` | 5-line entry-point wrapper; its effect is tested via console_script tests |
| `src/flytie/migrations/env.py` | Alembic migrations run in subprocess; coverage.py cannot see them |
| `src/flytie/migrations/versions/*.py` | Same — migration effects exercised end-to-end via `database` fixture |

The `*_old.py` files are also excluded from pytest collection (`addopts --ignore=...`)
and ruff lint (`[tool.ruff].exclude`).

---

## 5. Cold-start regression hunting with importtime

When the cold-start benchmark fails or approaches 600 ms:

```bash
python -X importtime -m flytie --version 2>importtimes.log

# Extract top offenders by cumulative import time:
python3 -c "
import pathlib
lines = pathlib.Path('importtimes.log').read_text().splitlines()
pairs = []
for l in lines[1:]:
    parts = [p.strip() for p in l.split('|')]
    if len(parts) >= 3:
        try:
            cum_us = int(parts[1].strip())
            pkg = parts[2].strip()
            pairs.append((cum_us, pkg))
        except ValueError:
            pass
for cum_us, pkg in sorted(pairs, reverse=True)[:15]:
    print(f'{cum_us:8d} us   {pkg}')
"
```

**Real top offenders (v0.2.1, 2026-07-02):**

```
  211238 us   flytie.cli        ← normal; loads all CLI handlers
   55095 us   sqlalchemy        ← core dep, loads at startup (expected)
   43823 us   flytie.core.dedupe
   41716 us   sqlalchemy.engine
   28351 us   flytie.core.patterns
   22100 us   pydantic
   21204 us   typer
```

**Absent from the log — lazy loading confirmed (2026-07-02):**
`weasyprint`, `anthropic`, `alembic` do NOT appear. If any of these appear
in your importtimes.log, that module has been imported eagerly and will add
hundreds of milliseconds to cold-start.

| Signal | Meaning |
|--------|---------|
| `weasyprint` in log | Imported at module load — must remain lazy in `pdf/export.py` |
| `anthropic` in log | Anthropic SDK imported eagerly — must stay inside `ai/suggest.py::anthropic_streamer()` |
| `alembic` at top level | Not deferred in `db.py` — must stay inside upgrade methods |
| `sqlalchemy` with high cumulative | Normal; SQLAlchemy is a core dep |

---

## 6. Skip forensics

```bash
pytest -rs   # show reason for every skip/xfail
```

**Real skip output (v0.2.1, 2026-07-02):**

```
SKIPPED [1] tests/test_cli_export.py: PDF CLI tests skipped — WeasyPrint not safely
    loadable in this environment (probe exit 1)...ModuleNotFoundError: No module named 'weasyprint'
SKIPPED [1] tests/test_pdf_export.py: PDF tests skipped — WeasyPrint not safely
    loadable in this environment (probe exit 1)...ModuleNotFoundError: No module named 'weasyprint'
SKIPPED [1] tests/test_audit_fixes.py:209: WeasyPrint not loadable
SKIPPED [1] tests/test_review_fixes_phase6.py:319: WeasyPrint not loadable
SKIPPED [1] tests/test_review_fixes_phase6.py:340: WeasyPrint not loadable
380 passed, 5 skipped
```

Expected skips (all WeasyPrint-related — healthy without the `pdf` extra):

| Module | Skip trigger |
|--------|-------------|
| `test_pdf_export.py` | Subprocess probe `import weasyprint` fails |
| `test_cli_export.py` | Same probe |
| `test_audit_fixes.py:209` | `_weasy` flag from probe |
| `test_review_fixes_phase6.py:319,340` | `_HAS_WEASYPRINT` flag |

Suspicious skips (investigate):

| Pattern | What it might mean |
|---------|--------------------|
| `importorskip("pdfminer.high_level")` in pdf tests | `pdfminer.six` not installed — run `pip install -e .[dev]` |
| Any smoke test appears in skip list | A core dep is missing; run `pip install -e .[dev,ai]` |
| Skip reason references a fixture error | `tests/conftest.py` has an import error |

---

## 7. Test-suite shape check

```bash
# Count all collected tests:
pytest --collect-only -q | tail -1

# Smoke tests only:
pytest --collect-only -m smoke -q | tail -1

# Sandbox:
pytest -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache --collect-only -q | tail -1
```

**Real counts (v0.2.1, 2026-07-02):**

```
383 tests collected in 0.28s     ← full suite (without PDF skip — those add 2 skipped)
5/383 tests collected (378 deselected)  ← smoke subset
```

Any change of >10 tests in the full count without a corresponding feature addition is
worth investigating. A drop in smoke from 5 means a marker was removed.

---

## 8. `flytie info` as runtime diagnostic

`flytie info` works even against an incompatible or uninitialised database and is the
first command to run when DB state is uncertain:

```bash
flytie info
```

**Real output (uninitialised sandbox, 2026-07-02):**

```
Database path      /home/user/.local/share/flytie/flytie.sqlite3
Config file        /home/user/.config/flytie/config.toml
Data directory     /home/user/.local/share/flytie
Schema revision    not initialized — run `flytie init`
Schema status      incomplete — run `flytie init` to repair
```

The API key is intentionally absent — it is excluded from `_CONFIG_KEYS` in `cli.py`
and never written to disk or printed by any command.

---

## 9. Wrap-fragility stress test

```bash
COLUMNS=80 pytest -q
```

The project's `conftest.py` patches every `CliRunner.invoke` to default `COLUMNS=200`
so Rich-wrapped CLI output doesn't break substring assertions on CI. Running at
`COLUMNS=80` stresses that protection locally.

This is exactly what the pre-push hook runs:

```
env COLUMNS=80 pytest -q -p no:cacheprovider --tb=line
```

If a test passes at `COLUMNS=200` and fails at `COLUMNS=80`, it either bypasses the
conftest autouse patch (rare) or contains a hardcoded assertion against wrapped text.

The `--narrow` flag to `verify_gates.sh` applies `COLUMNS=80` to the full gate run,
mirroring CI exactly.

---

## 10. When to run what

| Moment | Command(s) |
|--------|-----------|
| Before `git commit` | `pytest -m smoke` (fast local check) |
| Before `git push` | `verify_gates.sh --narrow` (mirrors pre-push hook) |
| Before a release tag | `verify_gates.sh` + `coldstart_bench.sh` |
| After adding a top-level import | `coldstart_bench.sh`, then importtime if close to budget |
| After touching `@pytest.mark.smoke` | `smoke_contract.sh` — must still collect exactly 5; update `tests/test_v0_1_2_fixes.py` if count changed |
| After adding many new tests | `pytest --collect-only -q | tail -1` to check suite shape |
| When coverage floor drops | Read `term-missing` output; surface to maintainer if headroom < 2 pp |

---

## Provenance and maintenance

Authored: 2026-07-02, v0.2.1. All script outputs verified live in the Cowork sandbox.
Sources: `pyproject.toml` (gate config, omit-list, `fail_under`, markers),
`tests/conftest.py` (COLUMNS patch, fixtures),
`tests/test_v0_1_2_fixes.py` (cold-start and smoke contract regression tests),
`.pre-commit-config.yaml` (hook layout, COLUMNS=80 rationale),
`src/flytie/pdf/export.py`, `src/flytie/ai/suggest.py`, `src/flytie/db.py`
(lazy-import patterns, verified absent from importtime log).

Re-verify with:

```bash
pytest --collect-only -m smoke -q | tail -1   # must print "5/N tests collected"
python -m flytie --version                    # must print "flytie 0.2.1"
COVERAGE_FILE=/tmp/.coverage_flytie \
  pytest -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache \
  --cov=src/flytie --cov-report=term-missing 2>&1 | tail -3  # total must be >= 85%
```
