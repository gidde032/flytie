"""Regression tests for bugs flagged in the Phase 1 review."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie.cli import app
from flytie.config import ConfigError, ConfigFile, load_settings
from flytie.core import patterns
from flytie.core.dto import MaterialLineDTO, PatternInput
from flytie.db import Database


def test_init_stamps_alembic_head(env_dirs: tuple[Path, Path]) -> None:
    """Review finding (HIGH, both A & B): `flytie init` must leave the DB
    stamped at the current Alembic revision so future migrations apply cleanly."""
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    db = Database.from_settings(load_settings())
    assert db.alembic_version() == "5af955bd607b"


def test_init_force_keeps_alembic_stamp(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["init", "--force"])
    assert result.exit_code == 0
    db = Database.from_settings(load_settings())
    assert db.alembic_version() == "5af955bd607b"


def test_edit_with_empty_tags_clears_them(session) -> None:  # type: ignore[no-untyped-def]
    """Review finding (MED, A): `edit_pattern` should treat empty list as 'clear'."""
    patterns.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            tags=["dryfly", "classic"],
            materials=[MaterialLineDTO(canonical_name="grizzly hackle", category="hackle")],
        ),
    )
    patterns.edit_pattern(
        session,
        "Adams",
        PatternInput(name="Adams", hook_size="14", tags=[]),
    )
    p = patterns.get_pattern(session, "Adams")
    assert p.tags == []


def test_edit_with_none_tags_leaves_them(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            tags=["dryfly"],
            materials=[MaterialLineDTO(canonical_name="grizzly hackle", category="hackle")],
        ),
    )
    patterns.edit_pattern(
        session,
        "Adams",
        PatternInput(name="Adams", hook_size="12", tags=None),
    )
    p = patterns.get_pattern(session, "Adams")
    assert {t.name for t in p.tags} == {"dryfly"}


def test_edit_with_none_materials_preserves_recipe(session) -> None:  # type: ignore[no-untyped-def]
    """No-op edit (e.g. just updating notes) must not blank the recipe."""
    patterns.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            materials=[
                MaterialLineDTO(canonical_name="grizzly hackle", category="hackle"),
                MaterialLineDTO(canonical_name="grey dubbing", category="dubbing"),
            ],
        ),
    )
    patterns.edit_pattern(
        session,
        "Adams",
        PatternInput(name="Adams", hook_size="14", notes="now with extra wing posts"),
    )
    p = patterns.get_pattern(session, "Adams")
    names = {pm.material.canonical_name for pm in p.current_version.materials}  # type: ignore[union-attr]
    assert names == {"grizzly hackle", "grey dubbing"}
    assert p.current_version.notes == "now with extra wing posts"  # type: ignore[union-attr]


def test_search_does_not_expand_user_wildcards(session) -> None:  # type: ignore[no-untyped-def]
    """Review finding (LOW, both): LIKE wildcards in user input must be escaped."""
    patterns.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            materials=[MaterialLineDTO(canonical_name="grizzly hackle", category="hackle")],
        ),
    )
    patterns.create_pattern(
        session,
        PatternInput(
            name="50% Off Pattern",
            hook_size="16",
            materials=[MaterialLineDTO(canonical_name="cdc", category="wing")],
        ),
    )
    # `%` should match literally now, not act as a wildcard.
    hits = patterns.search_patterns(session, "%")
    assert [p.name_display for p in hits] == ["50% Off Pattern"]
    assert "Adams" not in {p.name_display for p in hits}


def test_create_rejects_empty_hook_size(session) -> None:  # type: ignore[no-untyped-def]
    """Review finding (LOW, A): `hook_size` must be non-empty."""
    with pytest.raises(ValueError):
        patterns.create_pattern(session, PatternInput(name="X", hook_size=""))
    with pytest.raises(ValueError):
        patterns.create_pattern(session, PatternInput(name="Y", hook_size="   "))


def test_malformed_config_raises_clear_error(env_dirs: tuple[Path, Path]) -> None:
    """Review finding (MED, B): a broken config.toml should not crash the CLI
    with a raw TOMLDecodeError; it should raise our typed `ConfigError`."""
    config_dir, _ = env_dirs
    (config_dir / "config.toml").write_text("this is = not valid = toml\n[\n")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "not valid TOML" in str(exc.value)


def test_config_atomic_write(env_dirs: tuple[Path, Path]) -> None:
    """Review finding (LOW, B): writes should not leave a partial file behind."""
    settings = load_settings()
    cfg = ConfigFile()
    cfg.set("database.path", "/somewhere.sqlite3")
    cfg.save(settings)
    # No .tmp leftovers.
    assert not (settings.config_file.with_suffix(".toml.tmp")).exists()
    assert ConfigFile.load(settings).get("database.path") == "/somewhere.sqlite3"


def test_search_matches_instructions_and_notes(session) -> None:  # type: ignore[no-untyped-def]
    """Review finding (test gap, A): FR-3 requires search over notes/instructions."""
    patterns.create_pattern(
        session,
        PatternInput(
            name="RS2",
            hook_size="20",
            instructions="Tie in CDC wing post, wrap tight.",
            notes="Great for Henry's Fork tailwater hatches.",
            materials=[MaterialLineDTO(canonical_name="thread", category="thread")],
        ),
    )
    assert [p.name_display for p in patterns.search_patterns(session, "wing post")] == ["RS2"]
    assert [p.name_display for p in patterns.search_patterns(session, "henry")] == ["RS2"]
