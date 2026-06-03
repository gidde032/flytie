"""Unit tests for the shopping list aggregation in `flytie.core.shop`."""

from __future__ import annotations

from flytie.core import patterns as patterns_repo
from flytie.core import shop as shop_repo
from flytie.core.dto import MaterialLineDTO, PatternInput


def _make(session, name: str, **kw) -> None:  # type: ignore[no-untyped-def]
    patterns_repo.create_pattern(
        session,
        PatternInput(name=name, hook_size=kw.pop("hook", "14"), **kw),
    )


def test_dedupes_matching_material_and_unit(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        materials=[
            MaterialLineDTO(
                canonical_name="grizzly hackle", category="hackle", quantity=1, unit="feather"
            )
        ],
        tags=["dryfly"],
    )
    _make(
        session,
        "Royal Wulff",
        materials=[
            MaterialLineDTO(
                canonical_name="grizzly hackle", category="hackle", quantity=2, unit="feather"
            )
        ],
        tags=["dryfly"],
    )
    sl = shop_repo.build_shopping_list(session, tags=["dryfly"])
    items = {(i.canonical_name, i.unit): i for i in sl.items}
    assert items[("grizzly hackle", "feather")].quantity == 3
    assert sorted(items[("grizzly hackle", "feather")].used_in) == ["Adams", "Royal Wulff"]


def test_keeps_distinct_units_separate(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "A",
        materials=[
            MaterialLineDTO(canonical_name="thread", category="thread", quantity=1, unit="spool")
        ],
        tags=["x"],
    )
    _make(
        session,
        "B",
        materials=[
            MaterialLineDTO(canonical_name="thread", category="thread", quantity=10, unit="foot")
        ],
        tags=["x"],
    )
    sl = shop_repo.build_shopping_list(session, tags=["x"])
    keys = {(i.canonical_name, i.unit) for i in sl.items}
    assert keys == {("thread", "spool"), ("thread", "foot")}


def test_missing_quantity_marks_unitless(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "A",
        materials=[MaterialLineDTO(canonical_name="cdc", category="wing")],
        tags=["x"],
    )
    sl = shop_repo.build_shopping_list(session, tags=["x"])
    assert sl.items[0].has_unitless is True
    assert sl.items[0].quantity is None


def test_exclude_removes_owned_materials(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        materials=[
            MaterialLineDTO(canonical_name="grizzly hackle", category="hackle", quantity=1),
            MaterialLineDTO(canonical_name="grey dubbing", category="dubbing", quantity=1),
        ],
        tags=["dryfly"],
    )
    sl = shop_repo.build_shopping_list(session, tags=["dryfly"], exclude=["grey dubbing"])
    names = {i.canonical_name for i in sl.items}
    assert names == {"grizzly hackle"}
    assert "grey dubbing" in sl.excluded


def test_grouping_by_category(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        materials=[
            MaterialLineDTO(canonical_name="grizzly hackle", category="hackle", quantity=1),
            MaterialLineDTO(canonical_name="grey dubbing", category="dubbing", quantity=1),
        ],
        tags=["dryfly"],
    )
    sl = shop_repo.build_shopping_list(session, tags=["dryfly"])
    groups = sl.by_category()
    assert "hackle" in groups
    assert "dubbing" in groups


def test_name_selector_picks_only_named_patterns(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
    )
    _make(
        session,
        "RS2",
        materials=[MaterialLineDTO(canonical_name="cdc", category="wing", quantity=1)],
    )
    sl = shop_repo.build_shopping_list(session, names=["Adams"])
    names = {i.canonical_name for i in sl.items}
    assert names == {"hackle"}


def test_unknown_pattern_name_silently_skipped(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
    )
    sl = shop_repo.build_shopping_list(session, names=["Adams", "Nope"])
    # Adams is included, Nope is skipped.
    assert sl.pattern_names == ["Adams"]


def test_union_across_selectors(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        tags=["dryfly"],
        materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
    )
    _make(
        session,
        "Pheasant Tail",
        species=["brown trout"],
        materials=[MaterialLineDTO(canonical_name="pheasant tail", category="tail", quantity=1)],
    )
    sl = shop_repo.build_shopping_list(session, tags=["dryfly"], species=["brown trout"])
    assert set(sl.pattern_names) == {"Adams", "Pheasant Tail"}


def test_soft_deleted_patterns_excluded(session) -> None:  # type: ignore[no-untyped-def]
    _make(
        session,
        "Adams",
        tags=["dryfly"],
        materials=[MaterialLineDTO(canonical_name="hackle", category="hackle", quantity=1)],
    )
    patterns_repo.soft_delete_pattern(session, "Adams")
    sl = shop_repo.build_shopping_list(session, tags=["dryfly"])
    assert sl.pattern_names == []
    assert sl.items == []
