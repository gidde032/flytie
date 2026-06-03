"""Unit tests for the versioning helpers in `flytie.core.versions`."""

from __future__ import annotations

import pytest

from flytie.core import patterns as patterns_repo
from flytie.core import versions as versions_repo
from flytie.core.dto import MaterialLineDTO, PatternInput


def _seed(session) -> None:  # type: ignore[no-untyped-def]
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Adams",
            hook_size="14",
            instructions="Classic Catskill: tail, body, hackle.",
            notes="Tied 1922.",
            materials=[
                MaterialLineDTO(
                    canonical_name="grizzly hackle", category="hackle", quantity=1, unit="feather"
                ),
                MaterialLineDTO(
                    canonical_name="grey dubbing", category="dubbing", quantity=1, unit="pinch"
                ),
            ],
        ),
    )


def test_list_versions_returns_just_v1(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    vs = versions_repo.list_versions(session, "Adams")
    assert [v.version_number for v in vs] == [1]


def test_edit_then_list_returns_both(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    patterns_repo.edit_pattern(
        session, "Adams", PatternInput(name="Adams", hook_size="12", notes="tweaked")
    )
    vs = versions_repo.list_versions(session, "Adams")
    assert [v.version_number for v in vs] == [1, 2]
    # The historical version retains original materials (covers edit-preserves-materials).
    assert {m.canonical_name for m in vs[0].materials} == {"grizzly hackle", "grey dubbing"}


def test_get_version_returns_specific(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="12"))
    v1 = versions_repo.get_version(session, "Adams", 1)
    v2 = versions_repo.get_version(session, "Adams", 2)
    assert v1.hook_size == "14"
    assert v2.hook_size == "12"


def test_get_version_unknown_raises(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    with pytest.raises(versions_repo.VersionNotFoundError):
        versions_repo.get_version(session, "Adams", 99)


def test_diff_shows_hook_change(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    patterns_repo.edit_pattern(session, "Adams", PatternInput(name="Adams", hook_size="12"))
    _, _, diff = versions_repo.diff_versions(session, "Adams", 1, 2)
    text = "\n".join(diff)
    assert "hook_size: 14" in text
    assert "hook_size: 12" in text
    assert "-hook_size: 14" in text or "- hook_size: 14" in text
    assert "+hook_size: 12" in text or "+ hook_size: 12" in text


def test_diff_identical_versions_is_empty(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    patterns_repo.edit_pattern(
        session,
        "Adams",
        PatternInput(
            name="Adams",
            hook_size="14",
            instructions="Classic Catskill: tail, body, hackle.",
            notes="Tied 1922.",
            materials=[
                MaterialLineDTO(
                    canonical_name="grizzly hackle", category="hackle", quantity=1, unit="feather"
                ),
                MaterialLineDTO(
                    canonical_name="grey dubbing", category="dubbing", quantity=1, unit="pinch"
                ),
            ],
        ),
    )
    _, _, diff = versions_repo.diff_versions(session, "Adams", 1, 2)
    assert diff == []


def test_restore_appends_new_version(session) -> None:  # type: ignore[no-untyped-def]
    _seed(session)
    patterns_repo.edit_pattern(
        session, "Adams", PatternInput(name="Adams", hook_size="12", notes="tweaked")
    )
    new_v = versions_repo.restore_version(session, "Adams", 1)
    assert new_v.version_number == 3
    assert new_v.hook_size == "14"
    assert new_v.notes == "Tied 1922."
    # All three versions still exist.
    vs = versions_repo.list_versions(session, "Adams")
    assert [v.version_number for v in vs] == [1, 2, 3]
