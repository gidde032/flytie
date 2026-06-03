"""Smoke tests for the pattern repository functions used in Phase 2+."""

from __future__ import annotations

import pytest

from flytie.core import patterns
from flytie.core.dto import MaterialLineDTO, PatternInput


def _payload(name: str = "Adams", hook: str = "14") -> PatternInput:
    return PatternInput(
        name=name,
        hook_size=hook,
        instructions="Wrap, dub, post.",
        notes="Classic Catskill style.",
        tags=["dryfly", "classic"],
        species=["rainbow trout"],
        materials=[
            MaterialLineDTO(canonical_name="grizzly hackle", category="hackle", quantity=1, unit="feather"),
            MaterialLineDTO(canonical_name="grey dubbing", category="dubbing", quantity=1, unit="pinch"),
        ],
    )


def test_create_pattern_starts_at_version_1(session) -> None:  # type: ignore[no-untyped-def]
    p = patterns.create_pattern(session, _payload())
    assert p.current_version is not None
    assert p.current_version.version_number == 1
    assert {m.material.canonical_name for m in p.current_version.materials} == {
        "grizzly hackle",
        "grey dubbing",
    }


def test_create_duplicate_raises(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload())
    with pytest.raises(patterns.DuplicatePatternError):
        patterns.create_pattern(session, _payload(name="ADAMS"))


def test_edit_pattern_creates_new_version_preserving_old(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload())
    updated = patterns.edit_pattern(
        session,
        "Adams",
        PatternInput(
            name="Adams",
            hook_size="12",
            instructions="Hook 12 variant.",
            tags=["dryfly"],
            species=["rainbow trout"],
            materials=[
                MaterialLineDTO(canonical_name="grizzly hackle", category="hackle", quantity=1, unit="feather"),
            ],
        ),
    )
    assert updated.current_version is not None
    assert updated.current_version.version_number == 2
    versions = {v.version_number: v for v in updated.versions}
    assert set(versions) == {1, 2}
    v1_materials = {m.material.canonical_name for m in versions[1].materials}
    assert "grey dubbing" in v1_materials


def test_get_missing_pattern_raises(session) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(patterns.PatternNotFoundError):
        patterns.get_pattern(session, "Does Not Exist")


def test_list_patterns_filters_by_tag_and_species(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload(name="Adams"))
    patterns.create_pattern(
        session,
        PatternInput(
            name="Pheasant Tail",
            hook_size="16",
            tags=["nymph"],
            species=["brown trout"],
            materials=[MaterialLineDTO(canonical_name="pheasant tail", category="tail")],
        ),
    )
    by_tag = patterns.list_patterns(session, tag="nymph")
    assert [p.name_display for p in by_tag] == ["Pheasant Tail"]
    by_species = patterns.list_patterns(session, species="rainbow trout")
    assert [p.name_display for p in by_species] == ["Adams"]


def test_search_matches_name_and_materials(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload(name="Adams"))
    hits = patterns.search_patterns(session, "grizzly")
    assert [p.name_display for p in hits] == ["Adams"]
    hits = patterns.search_patterns(session, "ada")
    assert [p.name_display for p in hits] == ["Adams"]


def test_soft_delete_hides_from_listing(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload(name="Adams"))
    patterns.soft_delete_pattern(session, "Adams")
    assert patterns.list_patterns(session) == []
    assert patterns.list_patterns(session, include_deleted=True) != []


def test_hard_delete_removes_rows(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload(name="Adams"))
    patterns.hard_delete_pattern(session, "Adams")
    with pytest.raises(patterns.PatternNotFoundError):
        patterns.get_pattern(session, "Adams", include_deleted=True)


def test_add_remove_tags(session) -> None:  # type: ignore[no-untyped-def]
    patterns.create_pattern(session, _payload(name="Adams"))
    patterns.add_tags(session, "Adams", ["catskill", "dryfly"])
    p = patterns.get_pattern(session, "Adams")
    assert {t.name for t in p.tags} >= {"catskill", "dryfly", "classic"}
    patterns.remove_tags(session, "Adams", ["classic"])
    p = patterns.get_pattern(session, "Adams")
    assert "classic" not in {t.name for t in p.tags}
