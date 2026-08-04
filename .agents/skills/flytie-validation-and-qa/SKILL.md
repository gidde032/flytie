---
name: flytie-validation-and-qa
description: >
  Use when writing any new test for flytie, deciding where a test file lives,
  fixing a review or audit finding, asserting on CLI output, adding a PDF test,
  touching the smoke set, wondering what counts as evidence, or checking whether
  a fix is "done" without a paired regression test. Covers the evidence bar,
  test-tree map, the 5-test smoke golden inventory, CLI-output assertion
  discipline, PDF probe pattern, AI fake-streamer seam, doc-content smoke tests,
  coverage floor and omit-list rules, known assertion traps, and the end-to-end
  checklist for adding a test.
---

# flytie validation and QA

## When NOT to use this skill

- Setting up the dev environment or running the suite for the first time → **flytie-build-and-env**
- Diagnosing a specific test failure you can reproduce → **flytie-debugging-playbook**
- Understanding why a past fix was chosen a certain way → **flytie-failure-archaeology**
- Scheduling a reviewer subagent pass → **flytie-subagent-orchestration**
- Quality gates required before tagging a release → **flytie-change-control**

---

## 1. The evidence bar

The project's core contract: **no shipped bug ever re-surfaces silently.**

Every finding accepted from a code review or hardening audit requires a paired regression test that:

1. Fails before the fix is applied.
2. Passes after the fix is applied.
3. Has a docstring that names the reviewer persona (or audit lens) and severity.

"Fixed" means a named test demonstrates it, not an eyeball check. A fix without a paired test is not done.

**Real docstring examples** (from `tests/test_review_fixes_phase2.py` and `tests/test_review_fixes_phase3.py`):

```python
def test_h_short_flag_is_help_not_hook(env_dirs):
    """Reviewer B (MED): `-h` should not be hijacked for --hook."""

def test_add_requires_hook_when_no_file(env_dirs):
    """Reviewer A (HIGH): --hook must be required when --from-file is absent,
    but optional (and overridable) when a file supplies it."""

def test_parse_material_rejects_nan():
    """Reviewer B (MED): NaN poisons aggregation in shop."""
```

The pattern: `Reviewer <ID> (<SEVERITY>): <one-line description of the defect>`.

---

## 2. Test-tree map (as of 2026-07-02, v0.2.1)

### Core coverage files

| File | What it covers |
|---|---|
| `test_config.py` | Settings loading, env-var overrides, TOML config |
| `test_models.py` | ORM model field validation |
| `test_db.py` | Database init, schema creation, Alembic stamp |
| `test_patterns_repo.py` | `patterns` repository layer (CRUD, search, soft-delete) |
| `test_parsing.py` | `parse_material_spec` CSV grammar |
| `test_cli_commands.py` | Core CLI commands: init, add, list, view, edit, delete, search |
| `test_cli_phase3.py` | `flytie shop` command |
| `test_versions.py` | Version history, diff, restore |
| `test_shop.py` | `shop` repository layer |
| `test_pdf_export.py` | PDF/HTML export (skipped if WeasyPrint not safely loadable) |
| `test_cli_export.py` | `flytie export-pdf` / `export-html` CLI |
| `test_ai_suggest.py` | `flytie.ai.suggest` unit tests (no network) |
| `test_cli_suggest.py` | `flytie suggest` CLI (fake streamer, no network) |
| `test_portability.py` | `export-db` / `import-db` round-trip |
| `test_suggestions.py` | Suggestion rendering helpers |
| `test_dedupe.py` | Material deduplication logic |

### Regression files by origin

| File | Origin |
|---|---|
| `test_review_fixes.py` | Phase 1 three-reviewer pass |
| `test_review_fixes_phase2.py` | Phase 2 three-reviewer pass |
| `test_review_fixes_phase3.py` | Phase 3 three-reviewer pass |
| `test_review_fixes_phase4.py` | Phase 4 reviewer pass (PDF/OSError finding) |
| `test_review_fixes_phase5.py` | Phase 5 three-reviewer pass (AI suggestions) |
| `test_review_fixes_phase6.py` | Phase 6 three-reviewer pass (packaging, PyPI, tech-writing) |
| `test_audit_fixes.py` | Spec-drift audit (pre-v0.1.1) |
| `test_v0_1_1_fixes.py` | v0.1.1 hardening pass |
| `test_v0_1_2_fixes.py` | v0.1.2 hardening pass |
| `test_v0_2_phase1.py` | v0.2.0 Phase 1 (undelete, stats, material merge) |

### Excluded files (FUSE-poisoned inodes — inert, no shipping code)

`tests/test_patterns_repo_old.py` and `tests/test_review_fixes_old.py` are excluded from pytest collection via `pyproject.toml` `addopts` (`--ignore=`) and from ruff via `[tool.ruff].exclude`. Do not import or reference them.

### Where a new test goes

| Situation | File |
|---|---|
| New feature or command | The matching core file (e.g., `test_cli_commands.py` for a new CLI command) |
| Accepted review finding from a per-phase pass | `test_review_fixes_phase{N}.py` where N is the current phase |
| Accepted finding from a hardening audit (cross-cutting contract fix) | `test_v0_X_Y_fixes.py` for the release being hardened (v0.1.1/v0.1.2 precedent) |
| Hardening finding that pins **feature-specific** behavior | The feature's own test file (v0.2.1 precedent: fixes landed in `tests/test_suggestions.py`, `tests/test_dedupe.py`; no `test_v0_2_1_fixes.py` was created) |
| v0.2+ phase work | `test_v0_2_phase{N}.py` |

Naming conventions are enforced by project convention, not by a linter. Keep them consistent so `git log tests/` stays navigable. **When a hardening finding pins feature-specific behavior, the paired test may live in that feature's test file (v0.2.1 precedent); `test_v0_X_Y_fixes.py` is reserved for cross-cutting contract fixes. Follow the convention of the release you're in; when unclear, ask the maintainer.**

---

## 3. Golden smoke inventory

The smoke suite is exactly 5 tests. Run with:

```bash
pytest -m smoke -q -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache
```

**The 5 tests (verified by grep on `@pytest.mark.smoke`):**

| Test ID | File | What it covers |
|---|---|---|
| `test_db.py::test_init_creates_db_file` | `test_db.py` | `flytie init` writes the SQLite file |
| `test_cli_commands.py::test_add_and_list_round_trip` | `test_cli_commands.py` | `add` then `list` returns the pattern |
| `test_cli_commands.py::test_view_renders_pattern` | `test_cli_commands.py` | `view` renders a stored pattern |
| `test_cli_phase3.py::test_shop_dedupes_across_patterns` | `test_cli_phase3.py` | `shop` deduplicates materials |
| `test_portability.py::test_cli_import_db_round_trip` | `test_portability.py` | `export-db` → `import-db` preserves data |

### The exact-count contract

`tests/test_v0_1_2_fixes.py` contains two meta-regression tests:

- `test_smoke_marker_collects_exactly_five_happy_path_tests` — runs `pytest --collect-only -m smoke -q` in a subprocess and asserts the collected count equals exactly 5.
- `test_smoke_suite_runs_under_five_seconds` — runs the full smoke suite and asserts wall-clock time is under 5 seconds.

**Rule:** if you need to add a sixth smoke test, update both the marker on the new test AND the exact-count assertion in `test_v0_1_2_fixes.py` deliberately. Never loosen the assert to `>= 5`. The exact count catches two failure modes:

1. A slow test (PDF render, AI streaming, full-suite subprocess) accidentally tagged `@pytest.mark.smoke`, bloating the "quick feedback" budget.
2. A smoke marker silently removed from one of the five tests, reducing coverage of a happy-path operation.

---

## 4. CLI-output assertion discipline

### The `_wide_cli_runner_env` autouse fixture

`tests/conftest.py` patches `CliRunner.invoke` with an autouse fixture that defaults `env={"COLUMNS": "200"}` for every invocation. This prevents Rich/Typer from wrapping output at ~80 columns (CI default), which breaks substring assertions when a phrase like `"JSON parse error"` wraps across lines.

How it works: the patch merges `{"COLUMNS": "200"}` with any user-supplied `env` dict; user values win. A test that deliberately wants narrow terminal behavior passes `env={"COLUMNS": "80"}` explicitly.

### Whitespace normalization

Even at 200 columns, Rich may insert a line break inside a long table cell or help text. Always normalize before substring assertions:

```python
out = " ".join((r.stdout + r.stderr).split())
assert "JSON parse error" in out
```

The `cli_help()` helper in `tests/_helpers.py` does this automatically for `--help` text:

```python
from tests._helpers import cli_help

out = cli_help(["add"])
assert "name,category,quantity,unit" in out
```

### Rich markup escaping

Rich interprets `[brackets]` as markup. If you assert on output that contains `[NEW]`, `[tag]`, or similar tokens, the CLI layer must escape them (`\[NEW]`) before printing or Rich consumes them silently. When writing assertions check that the literal text reaches stdout — `assert "NEW" in r.stdout` works; `assert "[NEW]" in r.stdout` may not if the CLI forgot to escape.

---

## 5. PDF-test discipline

### The subprocess probe pattern

Plain `importorskip` or `try/except ImportError` is insufficient for WeasyPrint. If the native Pango/Cairo libraries are present but mismatched in version (common on macOS with mixed Homebrew/Conda Python), `import weasyprint` triggers a SIGSEGV that kills the test collector before any exception fires — all tests in the file are lost with no informative output.

The mandatory pattern (from `tests/test_pdf_export.py`, verified):

```python
import subprocess
import sys
import pytest

_pdf_probe = subprocess.run(
    [sys.executable, "-c", "import jinja2; import weasyprint"],
    capture_output=True,
    timeout=20,
)
if _pdf_probe.returncode != 0:
    pytest.skip(
        f"PDF tests skipped — WeasyPrint not safely loadable in this "
        f"environment (probe exit {_pdf_probe.returncode}). Last stderr: "
        f"{_pdf_probe.stderr.decode(errors='replace')[-300:]!r}",
        allow_module_level=True,
    )
```

Place this block at module level before any WeasyPrint import. If the probe exits non-zero the entire module is skipped cleanly; the subprocess death does not take down the collector.

After the probe, use `pdfminer.six` for content assertions — extract text and assert on strings rather than byte-diffing the PDF (PDF byte output is non-deterministic across WeasyPrint releases):

```python
pdfminer_extract = pytest.importorskip("pdfminer.high_level").extract_text
# ...
text = pdfminer_extract(str(pdf_path))
assert "Parachute Adams" in text
```

**Hard rule:** every new test file that imports WeasyPrint must use the subprocess probe pattern at module level. Never use a bare `importorskip("weasyprint")` or a `try/except`.

---

## 6. AI-test discipline

### The Streamer seam

The AI module (`flytie.ai.suggest`) accepts a `streamer` callable as a parameter. Tests inject a fake streamer that replays canned chunks — no network, no real API key.

Pattern from `tests/test_ai_suggest.py` (verified):

```python
def _fake_streamer(chunks: list[str]):
    """Return a Streamer that yields the given chunks verbatim."""
    def _stream(system: str, user: str) -> Iterator[str]:
        yield from chunks
    return _stream

result = generate_suggestions(req, grounding, _fake_streamer([_SAMPLE_JSON]))
```

For CLI tests, `tests/test_cli_suggest.py` monkeypatches `flytie.ai.anthropic_streamer`:

```python
monkeypatch.setattr("flytie.ai.anthropic_streamer", _fake_streamer_factory([_SAMPLE_JSON]))
```

**Hard rule: no live API calls in tests.** Any test that hits `api.anthropic.com` is a defect.

### Privacy assertions

Two tests pin the privacy constraints explicitly:

- `tests/test_ai_suggest.py::test_grounding_block_excludes_instructions_and_notes` — asserts that `build_prompt` never includes `instructions` or `notes` text in the user prompt sent to the API. Only pattern names, hook sizes, and material names appear.
- `tests/test_v0_1_1_fixes.py::test_info_never_mentions_api_key` — asserts that `flytie info` does not echo the API key value or `ANTHROPIC_API_KEY` even when the env var is set.

When adding new fields to `PatternDTO` or `PatternVersionDTO`, check `flytie.ai.suggest.build_prompt` and verify the field does not appear in the constructed prompt. If it might be sensitive, add a test mirroring `test_grounding_block_excludes_instructions_and_notes`.

---

## 7. Doc-content smoke tests

`tests/test_v0_1_1_fixes.py` contains a set of tests that read documentation files and assert that specific phrases are present. These pin doc promises in the same way code tests pin behavior.

Pattern:

```python
def _read_doc(name: str) -> str:
    return (_project_root() / "docs" / name).read_text()

def test_commands_md_documents_flytie_info() -> None:
    text = _read_doc("commands.md")
    assert "## `flytie info`" in text
    assert "Anthropic API key is **never** displayed" in text

def test_quickstart_explains_question_mark_in_shop_output() -> None:
    text = _read_doc("quickstart.md")
    normalized = " ".join(text.split())   # paragraph-internal line breaks collapse
    assert "`?`" in text
    assert "without a numeric quantity" in normalized or "without a quantity" in normalized
```

Always whitespace-normalize (`" ".join(text.split())`) before asserting on phrases that may span a paragraph-internal line break in the source Markdown.

When to add a doc-content test: any documentation change that states a contract (a command's behavior, a format promise, a safety guarantee) should be pinned. The second occurrence of a question about doc accuracy is the signal to add one.

---

## 8. Coverage discipline

The coverage floor is **85%** via `[tool.coverage.report] fail_under = 85` in `pyproject.toml`. The current real coverage is 89.2% in a sandbox without `[pdf]` extras (weasyprint absent drags `pdf/export.py`); higher with all extras installed as in CI; the enforced floor is 85% — 85% is a floor, not a target.

### Omit-list rationale (three categories)

1. **`src/flytie/*_old.py` and variants** — FUSE-poisoned inert placeholders from the Phase 3 recovery. They contain no shipping code and are excluded from pytest collection and ruff as well. The omit list keeps them from dragging the floor down.

2. **`src/flytie/__main__.py`** — a 5-line entry-point wrapper. Exercised only via `python -m flytie`; the console_script tests in `test_cli_*.py` cover the same paths more directly.

3. **`src/flytie/migrations/env.py` and `src/flytie/migrations/versions/*.py`** — Alembic migrations run inside a subprocess that coverage.py cannot see. Their effects are exercised end-to-end by every test that calls `database.create_schema()`, and edge cases are pinned by specific tests.

### The sync rule

The pytest `addopts --ignore=`, ruff `[tool.ruff].exclude`, and `[tool.coverage.run] omit` lists must stay in sync. There is one project-wide answer to "what counts as live code." When you add a new file to any one of the three lists, add it to all three in the same commit.

**Hard rule:** never widen the omit list to make a failing coverage gate pass. That requires explicit maintainer sign-off and a written rationale in the commit message.

---

## 9. Known assertion traps

### Exact-count assertions break when warnings are added

`len(result.warnings) == 1` style assertions are brittle when a code path gains a new warning in a later change. Real example from `tests/test_v0_2_phase1.py`:

```python
# A merge of materials that also discards a quantity now emits two warnings:
assert len(result.warnings) == 2
assert any("discarded quantity" in w for w in result.warnings)
```

A previous version of that test asserted `== 1`. When Fix C in v0.2.1 added the explicit quantity-discard warning, the test broke.

**Rule:** before any commit that adds a new warning to a code path, grep for exact-count assertions on that path and update them in the same commit:

```bash
grep -n "len(result.warnings) ==" tests/
grep -n "== 1" tests/test_v0_2_phase1.py
```

The same trap applies to exact counts on list lengths, table rows, or any collection whose size you asserted precisely.

---

## 10. Checklist: adding a test

1. **Pick the right file.** Use the decision list in §2. Do not put review-fix tests in a core coverage file or vice versa.

2. **Write the docstring.** For regression tests: `Reviewer <ID> (<SEVERITY>): <defect description>`. For new-feature tests: describe what the test asserts, not how.

3. **CLI output?** Let `_wide_cli_runner_env` handle the COLUMNS default. Normalize with `" ".join(out.split())` before substring asserts. Avoid asserting on Rich markup tokens (`[NEW]`, `[tag]`) without first checking they are escaped in the CLI layer.

4. **PDF test?** Use the subprocess probe pattern at module level (§5). Use `pdfminer.six` for content assertions. Never `importorskip("weasyprint")` bare.

5. **AI test?** Inject a fake streamer (§6). Assert on `build_prompt` output to verify privacy. No live API key, no network.

6. **Smoke marker?** Only tag if the test covers one of the five happy-path operations and runs in well under 5 seconds. If you tag a sixth test, update `test_smoke_marker_collects_exactly_five_happy_path_tests` in `test_v0_1_2_fixes.py` to assert `== 6`, deliberately.

7. **Run the suite:**

```bash
pytest --collect-only -m smoke -q -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache
pytest -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache
pytest --cov=src/flytie --cov-report=term-missing -p no:cacheprovider -o cache_dir=/tmp/.pytest_cache
```

8. **Check coverage did not drop below 85%.** If it did, add tests rather than widening the omit list.

9. **Check for exact-count assertion traps** on any code path your change touches (§9).

---

## Provenance and maintenance

**Date:** 2026-07-02. **Version:** v0.2.1.

**Sources verified against:** `tests/` directory (full file list via glob), `tests/conftest.py` (fixture names and behavior), `tests/test_pdf_export.py` (probe block, pdfminer usage), `tests/test_ai_suggest.py` (fake streamer pattern, privacy tests), `tests/test_v0_1_1_fixes.py` (doc-content smoke tests), `tests/test_v0_1_2_fixes.py` (exact-count and runtime contracts), `tests/test_v0_2_phase1.py` (warnings exact-count trap), `tests/test_review_fixes_phase2.py`, `tests/test_review_fixes_phase3.py` (docstring examples), `tests/_helpers.py` (cli_help), `pyproject.toml` (`fail_under`, omit list, addopts, smoke marker registration).

**Re-verify with:**

```bash
# Confirm the 5 smoke tests
grep -rn "@pytest.mark.smoke" tests/ --include="*.py"

# Confirm coverage floor
grep "fail_under" pyproject.toml

# Confirm omit-list and addopts sync
grep -A 30 "\[tool.coverage.run\]" pyproject.toml
grep "addopts" pyproject.toml
```
