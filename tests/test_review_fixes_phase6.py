"""Regression tests for the Phase 6 three-reviewer findings.

Each test pins a finding from the Phase 6 review pass (skeptical senior
engineer, packaging/PyPI specialist, technical-writing specialist) so the
same bug can't re-surface. Grouped by severity, then by reviewer.

Reviewer findings recorded in `handoff.md` under "Phase 6 review (Step 9)".
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from typer.testing import CliRunner

from flytie.cli import app
from flytie.core import patterns as patterns_repo
from flytie.core import portability as portability_repo
from flytie.core.portability import (
    EXPORT_FORMAT_VERSION,
    MAX_IMPORT_FILE_BYTES,
    ExportDocument,
    PortabilityError,
    parse_document,
)
from flytie.db import Database

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


# ---------------------------------------------------------------------------
# CRITICAL — `flytie init` half-built database (skeptical-senior reviewer)
# ---------------------------------------------------------------------------


def test_create_schema_is_complete_returns_false_on_empty_db(settings) -> None:
    """A freshly resolved DB file with nothing in it has no `patterns` table."""
    db = Database.from_settings(settings)
    try:
        # Force the SQLite file to exist (engine connect creates it) but do
        # not run any DDL. This mirrors a freshly-touched, empty database.
        with db.engine.connect():
            pass
        assert db.schema_is_complete() is False
    finally:
        db.engine.dispose()


def test_create_schema_repairs_stamped_but_empty_database(settings) -> None:
    """Reproduces and pins the CRITICAL finding from Reviewer 1.

    A previous `init` was interrupted after Alembic stamped `head` but
    before the migration's DDL ran. On the next `init`, Alembic sees the
    stamp, runs nothing, returns cleanly — and every later command dies on
    the missing `patterns` table. `create_schema()` must detect this and
    repair it; this test pins that behavior.
    """
    db = Database.from_settings(settings)
    try:
        # Build the corrupt state: stamp Alembic at head without running
        # the migration. Verify the real tables are missing.
        db.stamp_alembic_head()
        assert db.alembic_version() is not None
        assert not db.schema_is_complete()

        # Run create_schema and verify it has now repaired the schema.
        db.create_schema()
        assert db.schema_is_complete()
        assert inspect(db.engine).has_table("pattern_versions")
        assert inspect(db.engine).has_table("materials")

        # The repaired schema is actually usable end-to-end.
        with db.session() as s:
            from flytie.core.dto import PatternInput
            patterns_repo.create_pattern(
                s, PatternInput(name="Smoke Test", hook_size="14")
            )
        with db.session() as s:
            assert patterns_repo.get_pattern(s, "Smoke Test") is not None
    finally:
        db.engine.dispose()


def test_init_repairs_corrupt_db_without_force(env_dirs) -> None:
    """`flytie init` on a stamped-but-empty DB must repair, not refuse."""
    # Set up the corrupt state out-of-band (no `init` yet).
    from flytie.config import load_settings
    settings = load_settings()
    db = Database.from_settings(settings)
    db.stamp_alembic_head()
    db.engine.dispose()

    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "Repaired" in output or "repairing" in output.lower()

    # The repaired DB is usable: `add` works without dying on a missing table.
    result = runner.invoke(app, ["add", "Repair Test", "--hook", "14"])
    assert result.exit_code == 0, result.stdout + result.stderr


def test_init_says_already_exists_on_healthy_db(env_dirs) -> None:
    """The benign-existing-DB path remains unchanged — must not falsely 'repair'."""
    runner = CliRunner()
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0
    # Healthy DB: original "already exists" message, never the repair message.
    output = r.stdout + r.stderr
    assert "already exists" in output.lower()
    assert "repair" not in output.lower()


# ---------------------------------------------------------------------------
# HIGH — duplicate pattern names within one import file (Reviewer 1)
# ---------------------------------------------------------------------------


def _minimal_pattern(name: str, *, is_current: bool = True) -> dict:
    return {
        "name": name,
        "versions": [
            {
                "version_number": 1,
                "hook_size": "14",
                "created_at": "2026-01-01T00:00:00",
                "is_current": is_current,
                "materials": [],
            }
        ],
    }


def _minimal_document(*patterns: dict) -> str:
    return json.dumps(
        {
            "flytie_export_version": EXPORT_FORMAT_VERSION,
            "exported_at": "2026-01-01T00:00:00",
            "patterns": list(patterns),
        }
    )


def test_parse_document_rejects_duplicate_pattern_names() -> None:
    """parse_document rejects two patterns with the same (case-insensitive) name."""
    raw = _minimal_document(
        _minimal_pattern("Zebra Midge"), _minimal_pattern("ZEBRA MIDGE")
    )
    with pytest.raises(PortabilityError) as exc_info:
        parse_document(raw)
    assert "same name" in str(exc_info.value).lower()


def test_parse_document_accepts_distinct_names() -> None:
    """Sanity: an otherwise-valid file with unique names still parses."""
    raw = _minimal_document(
        _minimal_pattern("Zebra Midge"), _minimal_pattern("Hare's Ear")
    )
    doc = parse_document(raw)
    assert isinstance(doc, ExportDocument)
    assert {p.name for p in doc.patterns} == {"Zebra Midge", "Hare's Ear"}


def test_import_db_does_not_double_apply_duplicates(env_dirs, tmp_path) -> None:
    """End-to-end: dup-name file is rejected, the database stays empty.

    Without the fix, `import-db --on-conflict overwrite` would delete the
    pattern the *first* dup just created, leaving the library short.
    """
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    payload = _minimal_document(
        _minimal_pattern("Zebra Midge"), _minimal_pattern("Zebra Midge")
    )
    import_file = tmp_path / "dup.json"
    import_file.write_text(payload)

    result = runner.invoke(
        app, ["import-db", str(import_file), "--on-conflict", "overwrite"]
    )
    assert result.exit_code == 2
    # Library was not partially mutated.
    listing = runner.invoke(app, ["list"])
    assert "Zebra Midge" not in listing.stdout


# ---------------------------------------------------------------------------
# HIGH — import_document traceback leak in the CLI (Reviewer 1)
# ---------------------------------------------------------------------------


def test_import_db_catches_unexpected_exceptions(env_dirs, tmp_path, monkeypatch) -> None:
    """An unexpected exception inside import_document must surface as a
    formatted error, not a raw traceback."""
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0

    src = tmp_path / "x.json"
    src.write_text(_minimal_document(_minimal_pattern("Foo")))

    def explode(*args, **kwargs):
        raise RuntimeError("unexpected gremlin")

    monkeypatch.setattr(portability_repo, "import_document", explode)
    result = runner.invoke(app, ["import-db", str(src)])
    assert result.exit_code == 1
    assert "no changes were made" in (result.stdout + result.stderr).lower()
    # The raw exception class is not printed as a traceback.
    assert "Traceback" not in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# MEDIUM — is_current ambiguity rejected by parse_document (Reviewer 1)
# ---------------------------------------------------------------------------


def test_parse_document_rejects_multiple_is_current() -> None:
    """A pattern flagging two versions as `is_current` is genuinely ambiguous."""
    bad_pattern = {
        "name": "Two-Current",
        "versions": [
            {
                "version_number": 1, "hook_size": "14",
                "created_at": "2026-01-01T00:00:00", "is_current": True,
                "materials": [],
            },
            {
                "version_number": 2, "hook_size": "16",
                "created_at": "2026-02-01T00:00:00", "is_current": True,
                "materials": [],
            },
        ],
    }
    with pytest.raises(PortabilityError) as exc_info:
        parse_document(_minimal_document(bad_pattern))
    assert "is_current" in str(exc_info.value)


def test_parse_document_allows_zero_is_current() -> None:
    """Zero is_current=True is documented as the fallback case — must still parse."""
    pattern = _minimal_pattern("No-Current", is_current=False)
    doc = parse_document(_minimal_document(pattern))
    assert doc.patterns[0].name == "No-Current"


# ---------------------------------------------------------------------------
# MEDIUM — import file-size bound (Reviewer 1)
# ---------------------------------------------------------------------------


def test_import_db_rejects_oversize_file(env_dirs, tmp_path) -> None:
    """A file larger than MAX_IMPORT_FILE_BYTES is rejected up front."""
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    big = tmp_path / "big.json"
    # We don't need actually-valid JSON; the size check fires first.
    big.write_bytes(b"x" * (MAX_IMPORT_FILE_BYTES + 1))
    result = runner.invoke(app, ["import-db", str(big)])
    assert result.exit_code == 2
    assert "refuses" in (result.stdout + result.stderr).lower()


def test_max_import_file_bytes_is_50_mib() -> None:
    """Pin the documented limit so the docs and the code can't drift apart."""
    assert MAX_IMPORT_FILE_BYTES == 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# MEDIUM — public get_or_create_* helpers (Reviewer 1)
# ---------------------------------------------------------------------------


def test_public_get_or_create_helpers_exist() -> None:
    """The three helpers used by `portability.py` are publicly named."""
    for name in ("get_or_create_material", "get_or_create_tag", "get_or_create_species"):
        assert callable(getattr(patterns_repo, name)), name


def test_underscore_aliases_still_resolve() -> None:
    """The old underscore names remain as aliases for one release."""
    assert patterns_repo._get_or_create_material is patterns_repo.get_or_create_material
    assert patterns_repo._get_or_create_tag is patterns_repo.get_or_create_tag
    assert patterns_repo._get_or_create_species is patterns_repo.get_or_create_species


# ---------------------------------------------------------------------------
# HIGH (new in this step) — `--out` directory-detection bug
# ---------------------------------------------------------------------------


def _add_simple_pattern(runner: CliRunner) -> None:
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(
        app,
        ["add", "Adams", "--hook", "14",
         "-m", "grizzly hackle,hackle,1,feather"],
    ).exit_code == 0


_HAS_WEASYPRINT: bool
try:  # pragma: no cover - environment-dependent
    import jinja2  # noqa: F401
    import weasyprint  # noqa: F401
    _HAS_WEASYPRINT = True
except (ImportError, OSError):
    _HAS_WEASYPRINT = False


@pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="WeasyPrint not loadable; covered by --html fallback in test_export_html_only",
)
def test_export_creates_directory_from_path_without_extension(
    env_dirs, tmp_path, monkeypatch
) -> None:
    """`--out somedir` (no extension, missing) should be treated as a dir."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _add_simple_pattern(runner)
    target = tmp_path / "cards"  # no `.pdf` suffix, doesn't yet exist
    assert not target.exists()

    result = runner.invoke(app, ["export", "Adams", "--out", str(target)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert target.is_dir(), "the --out path should have been created as a directory"
    pdfs = list(target.glob("*.pdf"))
    assert len(pdfs) == 1, f"expected one PDF inside {target}, got {pdfs}"


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="WeasyPrint not loadable")
def test_export_with_explicit_pdf_extension_writes_that_file(
    env_dirs, tmp_path, monkeypatch
) -> None:
    """`--out somedir/foo.pdf` writes exactly that file (and creates the parent)."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _add_simple_pattern(runner)
    target = tmp_path / "cards" / "adams.pdf"
    result = runner.invoke(app, ["export", "Adams", "--out", str(target)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert target.is_file()


def test_export_html_fallback_works_without_weasyprint(env_dirs) -> None:
    """The --html path keeps working — used in commands.md examples."""
    runner = CliRunner()
    _add_simple_pattern(runner)
    result = runner.invoke(app, ["export", "Adams", "--html"])
    assert result.exit_code == 0
    assert "<html" in result.stdout
    assert "Adams" in result.stdout


# ---------------------------------------------------------------------------
# HIGH — pyproject.toml dynamic version + PEP 639 license (Reviewer 2)
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_pyproject() -> dict:
    with (_project_root() / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_pyproject_uses_dynamic_version() -> None:
    """Version is sourced dynamically from `__init__.py`, not pinned in pyproject."""
    cfg = _read_pyproject()
    project = cfg.get("project", {})
    assert "version" in project.get("dynamic", []), (
        "expected `dynamic = [\"version\", ...]` so the package version has a "
        "single source of truth in src/flytie/__init__.py"
    )
    assert "version" not in project, (
        "pyproject.toml must not pin `version = ...` once dynamic is enabled "
        "— that double-declares it and risks divergence"
    )
    hatch_version = cfg.get("tool", {}).get("hatch", {}).get("version", {})
    assert hatch_version.get("path", "").endswith("src/flytie/__init__.py")


def test_pyproject_uses_pep639_license() -> None:
    """`license = "MIT"` SPDX string, not the deprecated `{ text = "MIT" }`."""
    cfg = _read_pyproject()
    project = cfg.get("project", {})
    license_value = project.get("license")
    assert isinstance(license_value, str) and license_value, (
        f"expected PEP 639 SPDX license string, got {license_value!r}"
    )
    assert project.get("license-files") == ["LICENSE"]
    # The "License :: OSI Approved :: MIT License" classifier is deprecated
    # alongside PEP 639 — both forms together trip newer twine warnings.
    classifiers = project.get("classifiers", [])
    assert not any(c.startswith("License ::") for c in classifiers), (
        "remove the deprecated `License ::` classifier when using PEP 639"
    )


def test_runtime_version_matches_pyproject_source() -> None:
    """`__version__` is parseable and present at the path declared in pyproject."""
    from flytie import __version__
    assert __version__, "runtime __version__ must be a non-empty string"
    # Walking the dynamic source path is what the release.yml check does too.
    init_text = (_project_root() / "src" / "flytie" / "__init__.py").read_text()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    assert match is not None, "could not find __version__ in src/flytie/__init__.py"
    assert match.group(1) == __version__


# ---------------------------------------------------------------------------
# HIGH — release.yml tag/version assertion step (Reviewer 2)
# ---------------------------------------------------------------------------


def test_release_workflow_has_tag_vs_version_check() -> None:
    """The release workflow must compare the pushed `v*` tag to `__version__`.

    A typo'd tag uploaded to PyPI can't be replaced — only yanked — so the
    check is a hard prerequisite for safe releases.
    """
    workflow = _project_root() / ".github" / "workflows" / "release.yml"
    assert workflow.is_file(), "release.yml must exist at .github/workflows/"
    text_ = workflow.read_text()
    assert "GITHUB_REF_NAME" in text_
    assert "__version__" in text_ or "flytie.__version__" in text_
    # The check must run inside `build` (which `publish` needs) so a mismatch
    # blocks the publish job from ever running.
    assert "Verify tag matches package version" in text_


# ---------------------------------------------------------------------------
# Docs (Reviewer 3) — small smoke-tests so the docs don't silently regress
# ---------------------------------------------------------------------------


def _read_doc(name: str) -> str:
    return (_project_root() / "docs" / name).read_text()


def test_quickstart_export_example_uses_correct_out_form() -> None:
    """Quickstart no longer recommends the weird `~/cards.pdf/` shape."""
    text_ = _read_doc("quickstart.md")
    assert "~/cards.pdf/" not in text_, (
        "the misleading `--out ~/cards.pdf/` example (writes file `cards.pdf`, "
        "not a directory) should be replaced with `--out ~/cards/` or "
        "`--out ~/cards/parachute-adams.pdf`"
    )


def test_quickstart_does_not_reference_undefined_pattern_file() -> None:
    """The §3 teaser referenced `zebra-midge.json` without defining it."""
    text_ = _read_doc("quickstart.md")
    # The quickstart should now defer pattern-file usage to the migrating doc.
    assert "--from-file zebra-midge.json" not in text_, (
        "drop the teaser that runs `flytie add ... --from-file zebra-midge.json` "
        "without showing the file; link to migrating-from-notebook.md instead"
    )


def test_index_documents_all_three_env_overrides() -> None:
    """`docs/index.md` documents FLYTIE_DB_PATH, FLYTIE_DATA_DIR, FLYTIE_CONFIG_DIR."""
    text_ = _read_doc("index.md")
    assert "FLYTIE_DB_PATH" in text_
    assert "FLYTIE_DATA_DIR" in text_
    assert "FLYTIE_CONFIG_DIR" in text_


def test_commands_md_no_oldest_filters_first() -> None:
    """The stray "oldest filters first" phrase is gone from `flytie list`."""
    text_ = _read_doc("commands.md")
    assert "oldest filters first" not in text_


def test_migrating_from_notebook_uses_tyer_spelling() -> None:
    """Reviewer 3: 'tiers' → 'tyers', 'flys' → 'flies'."""
    text_ = _read_doc("migrating-from-notebook.md")
    assert "Most tyers already have" in text_
    assert "Most tiers already have" not in text_
    assert "Improve flies as you go" in text_
    assert "Improve flys as you go" not in text_


def test_json_schema_documents_new_rejection_rules() -> None:
    """The expanded validation list mentions duplicate names and multiple is_current."""
    text_ = _read_doc("json-schema.md")
    text_lower = text_.lower()
    assert "same name" in text_lower
    assert "is_current" in text_
    assert "50 mib" in text_lower or "max_import_file_bytes" in text_lower


# ---------------------------------------------------------------------------
# Sanity — version sourced from the package, end-to-end through CLI
# ---------------------------------------------------------------------------


def test_cli_version_flag_matches_package_version() -> None:
    """`flytie --version` reads the same string the wheel will ship."""
    from flytie import __version__
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
