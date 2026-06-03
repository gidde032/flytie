"""Regression tests for bugs flagged in the Phase 3 review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie.cli import app
from flytie.core import patterns as patterns_repo
from flytie.core import shop as shop_repo
from flytie.core.dto import MaterialLineDTO, PatternInput
from flytie.core.parsing import MaterialParseError, parse_material_spec
from flytie.render import _escape_md, shopping_list_as_json, shopping_list_as_markdown


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def test_parse_material_rejects_nan() -> None:
    """Reviewer B (MED): NaN poisons aggregation in shop."""
    with pytest.raises(MaterialParseError):
        parse_material_spec("name,cat,nan,unit")


def test_parse_material_rejects_inf() -> None:
    with pytest.raises(MaterialParseError):
        parse_material_spec("name,cat,inf,unit")


def test_parse_material_rejects_negative() -> None:
    with pytest.raises(MaterialParseError):
        parse_material_spec("name,cat,-1,unit")


def test_shop_dedup_normalizes_units(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer B (LOW): 'Feather' / 'feather ' / 'FEATHER' must merge."""
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="A",
            hook_size="14",
            tags=["x"],
            materials=[
                MaterialLineDTO(
                    canonical_name="hackle", category="hackle", quantity=1, unit="Feather"
                )
            ],
        ),
    )
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="B",
            hook_size="14",
            tags=["x"],
            materials=[
                MaterialLineDTO(
                    canonical_name="hackle", category="hackle", quantity=2, unit="feather "
                )
            ],
        ),
    )
    sl = shop_repo.build_shopping_list(session, tags=["x"])
    assert len(sl.items) == 1
    assert sl.items[0].quantity == 3
    assert sl.items[0].unit == "feather"


def test_markdown_escapes_special_characters() -> None:
    """Reviewer B (MED): material names with # * [ ] should not break Markdown."""
    assert _escape_md("# bead head") == "\\# bead head"
    assert _escape_md("**flash**") == "\\*\\*flash\\*\\*"
    assert _escape_md("[brackets]") == "\\[brackets\\]"


def test_shop_markdown_render_escapes_special_chars(session) -> None:  # type: ignore[no-untyped-def]
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="A",
            hook_size="14",
            tags=["x"],
            materials=[
                MaterialLineDTO(canonical_name="*bead* head [#14]", category="bead", quantity=1)
            ],
        ),
    )
    sl = shop_repo.build_shopping_list(session, tags=["x"])
    md = shopping_list_as_markdown(sl)
    # No raw special chars survive in the material name; user sees literal text.
    assert "*bead*" not in md
    assert "\\*bead\\*" in md
    assert "[#14]" not in md


def test_shop_json_export_is_valid_json(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer A & B (MED): spec requires --format json; output must parse."""
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            tags=["dryfly"],
            materials=[
                MaterialLineDTO(
                    canonical_name="hackle", category="hackle", quantity=1, unit="feather"
                )
            ],
        ),
    )
    sl = shop_repo.build_shopping_list(session, tags=["dryfly"])
    parsed = json.loads(shopping_list_as_json(sl))
    assert parsed["pattern_names"] == ["Adams"]
    assert parsed["items"][0]["canonical_name"] == "hackle"


def test_restore_preserves_tags_and_species(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer A (test gap): restore must not touch tags or species."""
    from flytie.core import versions as versions_repo

    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            tags=["dryfly", "classic"],
            species=["rainbow trout"],
            materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
        ),
    )
    # Strip tags via edit.
    patterns_repo.edit_pattern(
        session, "Adams", PatternInput(name="Adams", hook_size="14", tags=[])
    )
    # Now restore v1.
    versions_repo.restore_version(session, "Adams", 1)
    p = patterns_repo.get_pattern(session, "Adams")
    # Tags from v1's *pattern* (not version) should still be cleared — restore
    # explicitly does not re-apply tags from history. This documents that
    # behavior so a future change can't silently re-introduce them.
    assert p.tags == []


def test_restore_returns_correct_new_version_number(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer A: verify restore's version_number bookkeeping."""
    from flytie.core import versions as versions_repo

    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
        ),
    )
    patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="12"))
    patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="10"))
    # 3 versions now exist. Restore v1 → new v4.
    new_v = versions_repo.restore_version(session, "Adams", 1)
    assert new_v.version_number == 4
    assert new_v.hook_size == "14"


def test_diff_with_reordered_materials_shows_changes(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer A (test gap): material list insert produces a visible diff."""
    from flytie.core import versions as versions_repo

    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            materials=[
                MaterialLineDTO(canonical_name="thread", category="thread"),
                MaterialLineDTO(canonical_name="hackle", category="hackle"),
            ],
        ),
    )
    patterns_repo.edit_pattern(
        session,
        "Adams",
        PatternInput(
            name="Adams",
            hook_size="14",
            materials=[
                MaterialLineDTO(canonical_name="thread", category="thread"),
                MaterialLineDTO(canonical_name="dubbing", category="dubbing"),
                MaterialLineDTO(canonical_name="hackle", category="hackle"),
            ],
        ),
    )
    _, _, lines = versions_repo.diff_versions(session, "Adams", 1, 2)
    text = "\n".join(lines)
    assert "dubbing" in text


def test_difficulty_none_renders_as_na_in_diff(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer A & B (LOW): no trailing-space noise in the diff."""
    from flytie.core import versions as versions_repo

    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            difficulty=None,
            materials=[MaterialLineDTO(canonical_name="hackle", category="hackle")],
        ),
    )
    patterns_repo.edit_pattern(
        session,
        "Adams",
        PatternInput(name="Adams", hook_size="14", difficulty=3),
    )
    _, _, lines = versions_repo.diff_versions(session, "Adams", 1, 2)
    text = "\n".join(lines)
    assert "difficulty: n/a" in text
    assert "difficulty: 3" in text


def test_shop_overlapping_selectors_dedups_patterns(session) -> None:  # type: ignore[no-untyped-def]
    """Reviewer A (test gap): pattern matching both --pattern AND --tag isn't counted twice."""
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            tags=["dryfly"],
            materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
        ),
    )
    sl = shop_repo.build_shopping_list(session, names=["Adams"], tags=["dryfly"])
    assert sl.pattern_names == ["Adams"]
    assert len(sl.items) == 1
    assert sl.items[0].quantity == 1  # not doubled


def test_view_unknown_version_via_cli(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["view", "Adams", "--version", "99"])
    assert r.exit_code == 1
    assert "no version 99" in (r.stdout + r.stderr).lower()
