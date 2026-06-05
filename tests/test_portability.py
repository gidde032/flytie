"""Tests for JSON import/export portability (FR-7).

Covers the pure schema/parse functions, the export builder, the import
engine (including all three conflict modes and the transactional guarantee),
and the `export-db` / `import-db` CLI commands.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from flytie.cli import app
from flytie.core import patterns as patterns_repo
from flytie.core.dto import MaterialLineDTO, PatternInput
from flytie.core.portability import (
    EXPORT_FORMAT_VERSION,
    ExportDocument,
    ExportMaterial,
    ExportPattern,
    ExportVersion,
    PortabilityError,
    build_export_document,
    document_to_json,
    import_document,
    parse_document,
)
from flytie.db import Database

# --- helpers -----------------------------------------------------------------


def _add(
    session: Session,
    name: str,
    *,
    hook: str = "14",
    tags: list[str] | None = None,
    species: list[str] | None = None,
    materials: list[dict] | None = None,
) -> None:
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name=name,
            hook_size=hook,
            tags=tags or [],
            species=species or [],
            materials=[MaterialLineDTO(**m) for m in (materials or [])],
        ),
    )


def _export_version(version_number: int = 1, hook: str = "12") -> ExportVersion:
    return ExportVersion(
        version_number=version_number,
        hook_size=hook,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        is_current=True,
    )


# --- export ------------------------------------------------------------------


def test_export_empty_db_yields_no_patterns(session: Session) -> None:
    doc = build_export_document(session)
    assert doc.patterns == []
    assert doc.flytie_export_version == EXPORT_FORMAT_VERSION


def test_export_captures_tags_species_and_materials(session: Session) -> None:
    _add(
        session,
        "Parachute Adams",
        hook="14",
        tags=["dry", "mayfly"],
        species=["rainbow trout"],
        materials=[{"canonical_name": "grizzly hackle", "category": "hackle"}],
    )
    doc = build_export_document(session)
    assert len(doc.patterns) == 1
    p = doc.patterns[0]
    assert p.name == "Parachute Adams"
    assert sorted(p.tags) == ["dry", "mayfly"]
    assert p.species == ["rainbow trout"]
    assert p.versions[0].materials[0].canonical_name == "grizzly hackle"
    assert p.versions[0].materials[0].category == "hackle"


def test_export_includes_full_version_history(session: Session) -> None:
    _add(session, "Zebra Midge", hook="20")
    patterns_repo.edit_pattern(
        session, "Zebra Midge", PatternInput(name="Zebra Midge", hook_size="18")
    )
    doc = build_export_document(session)
    versions = doc.patterns[0].versions
    assert [v.version_number for v in versions] == [1, 2]
    # Exactly the latest version is flagged current.
    assert [v.is_current for v in versions] == [False, True]
    assert versions[0].hook_size == "20"
    assert versions[1].hook_size == "18"


def test_export_tag_filter_narrows_selection(session: Session) -> None:
    _add(session, "Adams", tags=["dry"])
    _add(session, "Hares Ear", tags=["nymph"])
    doc = build_export_document(session, tag="dry")
    assert [p.name for p in doc.patterns] == ["Adams"]


def test_export_species_filter_narrows_selection(session: Session) -> None:
    _add(session, "Adams", species=["brown trout"])
    _add(session, "Clouser", species=["smallmouth bass"])
    doc = build_export_document(session, species="smallmouth bass")
    assert [p.name for p in doc.patterns] == ["Clouser"]


def test_export_excludes_soft_deleted_by_default(session: Session) -> None:
    _add(session, "Keeper")
    _add(session, "Goner")
    patterns_repo.soft_delete_pattern(session, "Goner")
    names = [p.name for p in build_export_document(session).patterns]
    assert names == ["Keeper"]


def test_export_include_deleted_flag(session: Session) -> None:
    _add(session, "Keeper")
    _add(session, "Goner")
    patterns_repo.soft_delete_pattern(session, "Goner")
    doc = build_export_document(session, include_deleted=True)
    names = sorted(p.name for p in doc.patterns)
    assert names == ["Goner", "Keeper"]
    goner = next(p for p in doc.patterns if p.name == "Goner")
    assert goner.is_deleted is True


# --- parse / serialize -------------------------------------------------------


def test_document_to_json_round_trips_through_parse(session: Session) -> None:
    _add(session, "Adams", tags=["dry"])
    doc = build_export_document(session)
    text = document_to_json(doc)
    json.loads(text)  # is valid JSON
    reparsed = parse_document(text)
    assert reparsed.patterns[0].name == "Adams"


def test_parse_document_rejects_malformed_json() -> None:
    with pytest.raises(PortabilityError, match="not valid JSON"):
        parse_document("{ this is not json")


def test_parse_document_rejects_wrong_structure() -> None:
    with pytest.raises(PortabilityError, match="schema"):
        parse_document('{"flytie_export_version": 1, "patterns": "not-a-list"}')


def test_parse_document_rejects_newer_format_version() -> None:
    blob = json.dumps(
        {
            "flytie_export_version": EXPORT_FORMAT_VERSION + 1,
            "exported_at": "2026-01-01T00:00:00",
            "patterns": [],
        }
    )
    with pytest.raises(PortabilityError, match="newer flytie"):
        parse_document(blob)


# --- import ------------------------------------------------------------------


def test_import_creates_patterns_in_empty_db(database: Database) -> None:
    doc = ExportDocument(patterns=[ExportPattern(name="Adams", versions=[_export_version()])])
    with database.session() as s:
        result = import_document(s, doc)
    assert result.created == ["Adams"]
    with database.session() as s:
        assert patterns_repo.get_pattern(s, "Adams") is not None


def test_import_round_trips_versions_and_timestamps(database: Database) -> None:
    original = datetime(2024, 6, 1, 9, 30, 0)
    doc = ExportDocument(
        patterns=[
            ExportPattern(
                name="Zebra Midge",
                versions=[
                    ExportVersion(version_number=1, hook_size="20", created_at=original),
                    ExportVersion(
                        version_number=2,
                        hook_size="18",
                        created_at=datetime(2024, 7, 1, 9, 30, 0),
                        is_current=True,
                    ),
                ],
            )
        ]
    )
    with database.session() as s:
        import_document(s, doc)
    with database.session() as s:
        pattern = patterns_repo.get_pattern(s, "Zebra Midge")
        versions = sorted(pattern.versions, key=lambda v: v.version_number)
        assert [v.hook_size for v in versions] == ["20", "18"]
        assert versions[0].created_at == original  # timestamp preserved verbatim
        assert pattern.current_version.version_number == 2


def test_import_skip_leaves_existing_pattern_untouched(database: Database) -> None:
    with database.session() as s:
        _add(s, "Adams", hook="14")
    doc = ExportDocument(
        patterns=[ExportPattern(name="Adams", versions=[_export_version(hook="99")])]
    )
    with database.session() as s:
        result = import_document(s, doc, on_conflict="skip")
    assert result.skipped == ["Adams"]
    with database.session() as s:
        # Still the original hook, not the incoming "99".
        assert patterns_repo.get_pattern(s, "Adams").current_version.hook_size == "14"


def test_import_overwrite_replaces_existing_pattern(database: Database) -> None:
    with database.session() as s:
        _add(s, "Adams", hook="14")
    doc = ExportDocument(
        patterns=[ExportPattern(name="Adams", versions=[_export_version(hook="99")])]
    )
    with database.session() as s:
        result = import_document(s, doc, on_conflict="overwrite")
    assert result.overwritten == ["Adams"]
    with database.session() as s:
        assert patterns_repo.get_pattern(s, "Adams").current_version.hook_size == "99"


def test_import_rename_imports_under_a_fresh_name(database: Database) -> None:
    with database.session() as s:
        _add(s, "Adams", hook="14")
    doc = ExportDocument(
        patterns=[ExportPattern(name="Adams", versions=[_export_version(hook="99")])]
    )
    with database.session() as s:
        result = import_document(s, doc, on_conflict="rename")
    assert result.renamed == {"Adams": "Adams (imported)"}
    with database.session() as s:
        # Original survives, plus the renamed import.
        assert patterns_repo.get_pattern(s, "Adams").current_version.hook_size == "14"
        assert patterns_repo.get_pattern(s, "Adams (imported)").current_version.hook_size == "99"


def test_import_rename_handles_repeated_collisions(database: Database) -> None:
    with database.session() as s:
        _add(s, "Adams")
    doc = ExportDocument(patterns=[ExportPattern(name="Adams", versions=[_export_version()])])
    with database.session() as s:
        import_document(s, doc, on_conflict="rename")
    with database.session() as s:
        result = import_document(s, doc, on_conflict="rename")
    assert result.renamed == {"Adams": "Adams (imported 2)"}


def test_import_unknown_category_raises_portability_error(database: Database) -> None:
    doc = ExportDocument(
        patterns=[
            ExportPattern(
                name="Adams",
                versions=[
                    ExportVersion(
                        version_number=1,
                        hook_size="14",
                        created_at=datetime(2026, 1, 1),
                        materials=[
                            ExportMaterial(canonical_name="thingy", category="NOT_A_CATEGORY")
                        ],
                    )
                ],
            )
        ]
    )
    with pytest.raises(PortabilityError, match="category"):
        with database.session() as s:
            import_document(s, doc)


def test_import_pattern_with_no_versions_raises(database: Database) -> None:
    doc = ExportDocument(patterns=[ExportPattern(name="Empty", versions=[])])
    with pytest.raises(PortabilityError, match="no versions"):
        with database.session() as s:
            import_document(s, doc)


def test_import_unknown_conflict_mode_raises(database: Database) -> None:
    doc = ExportDocument(patterns=[])
    with pytest.raises(PortabilityError, match="conflict mode"):
        with database.session() as s:
            import_document(s, doc, on_conflict="bogus")


def test_import_is_transactional_on_failure(database: Database) -> None:
    """A failed import must leave the DB completely unchanged.

    The document has a valid pattern *before* a broken one; if the import were
    not atomic, the valid pattern would survive the rollback.
    """
    good = ExportPattern(name="Good", versions=[_export_version()])
    bad = ExportPattern(
        name="Bad",
        versions=[
            ExportVersion(
                version_number=1,
                hook_size="10",
                created_at=datetime(2026, 1, 1),
                materials=[ExportMaterial(canonical_name="x", category="BOGUS")],
            )
        ],
    )
    doc = ExportDocument(patterns=[good, bad])
    with pytest.raises(PortabilityError):
        with database.session() as s:
            import_document(s, doc)
    # Rollback must have removed "Good" too.
    with database.session() as s:
        assert patterns_repo.list_patterns(s, include_deleted=True) == []


# --- CLI ---------------------------------------------------------------------


def test_cli_export_db_writes_a_file(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-t", "dry"])
    out = tmp_path / "export.json"
    r = runner.invoke(app, ["export-db", "--out", str(out)])
    assert r.exit_code == 0, r.stdout
    assert out.is_file()
    assert json.loads(out.read_text())["patterns"][0]["name"] == "Adams"


def test_cli_export_db_subset_by_tag(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-t", "dry"])
    runner.invoke(app, ["add", "Hares Ear", "--hook", "12", "-t", "nymph"])
    out = tmp_path / "dries.json"
    r = runner.invoke(app, ["export-db", "-o", str(out), "--tag", "dry"])
    assert r.exit_code == 0
    names = [p["name"] for p in json.loads(out.read_text())["patterns"]]
    assert names == ["Adams"]


@pytest.mark.smoke
def test_cli_import_db_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    # First database: populate and export.
    cfg1, data1 = tmp_path / "c1", tmp_path / "d1"
    cfg1.mkdir()
    data1.mkdir()
    monkeypatch.setenv("FLYTIE_CONFIG_DIR", str(cfg1))
    monkeypatch.setenv("FLYTIE_DATA_DIR", str(data1))
    monkeypatch.delenv("FLYTIE_DB_PATH", raising=False)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-t", "dry", "-m", "hackle,hackle"])
    out = tmp_path / "exp.json"
    assert runner.invoke(app, ["export-db", "--out", str(out)]).exit_code == 0
    # Second, empty database: import into it.
    cfg2, data2 = tmp_path / "c2", tmp_path / "d2"
    cfg2.mkdir()
    data2.mkdir()
    monkeypatch.setenv("FLYTIE_CONFIG_DIR", str(cfg2))
    monkeypatch.setenv("FLYTIE_DATA_DIR", str(data2))
    runner.invoke(app, ["init"])
    r = runner.invoke(app, ["import-db", str(out)])
    assert r.exit_code == 0, r.stdout
    assert "created: 1" in r.stdout
    assert "Adams" in runner.invoke(app, ["list"]).stdout


def test_cli_import_db_skip_conflict(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    runner.invoke(app, ["add", "Adams", "--hook", "14"])
    out = tmp_path / "exp.json"
    runner.invoke(app, ["export-db", "--out", str(out)])
    r = runner.invoke(app, ["import-db", str(out), "--on-conflict", "skip"])
    assert r.exit_code == 0
    assert "skipped" in r.stdout


def test_cli_import_db_missing_file(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    r = runner.invoke(app, ["import-db", "/no/such/file.json"])
    assert r.exit_code == 2
    assert "not found" in (r.stdout + r.stderr)


def test_cli_import_db_malformed_file(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json at all")
    r = runner.invoke(app, ["import-db", str(bad)])
    assert r.exit_code == 2
    out = r.stdout + r.stderr
    assert "Traceback" not in out


def test_cli_import_db_rejects_bad_conflict_mode(
    env_dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    some = tmp_path / "x.json"
    some.write_text('{"flytie_export_version": 1, "patterns": []}')
    r = runner.invoke(app, ["import-db", str(some), "--on-conflict", "bogus"])
    assert r.exit_code == 2
    assert "Invalid --on-conflict" in (r.stdout + r.stderr)
