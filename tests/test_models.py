"""Tests for ORM model behavior and the database bootstrap."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from flytie.db import Database
from flytie.models import (
    Material,
    Pattern,
    PatternMaterial,
    PatternVersion,
    Species,
    Tag,
    normalize_name,
)


def test_create_schema_creates_tables(database: Database) -> None:
    insp_tables = set()
    with database.engine.connect() as conn:
        from sqlalchemy import inspect

        insp_tables = set(inspect(conn).get_table_names())
    expected = {
        "patterns",
        "pattern_versions",
        "materials",
        "pattern_materials",
        "species",
        "pattern_species",
        "tags",
        "pattern_tags",
    }
    assert expected.issubset(insp_tables)


def test_normalize_name_collapses_whitespace_and_case() -> None:
    assert normalize_name("  Parachute   Adams ") == "parachute adams"
    assert normalize_name("PMD") == "pmd"


def test_pattern_unique_name_key(database: Database) -> None:
    with database.session() as s:
        s.add(Pattern(name_key="hare's ear", name_display="Hare's Ear"))
    with pytest.raises(IntegrityError):
        with database.session() as s:
            s.add(Pattern(name_key="hare's ear", name_display="Hare's Ear (dup)"))


def test_pattern_version_uniqueness(database: Database) -> None:
    with database.session() as s:
        p = Pattern(name_key="adams", name_display="Adams")
        s.add(p)
        s.flush()
        v1 = PatternVersion(pattern_id=p.id, version_number=1, hook_size="14")
        v2 = PatternVersion(pattern_id=p.id, version_number=2, hook_size="12")
        s.add_all([v1, v2])
    with pytest.raises(IntegrityError):
        with database.session() as s:
            p = s.scalar(select(Pattern).where(Pattern.name_key == "adams"))
            assert p is not None
            s.add(PatternVersion(pattern_id=p.id, version_number=1, hook_size="14"))


def test_pattern_version_cascade(database: Database) -> None:
    with database.session() as s:
        p = Pattern(name_key="rs2", name_display="RS2")
        s.add(p)
        s.flush()
        v = PatternVersion(pattern_id=p.id, version_number=1, hook_size="20")
        s.add(v)
        s.flush()
        m = Material(canonical_name="grey thread")
        s.add(m)
        s.flush()
        pm = PatternMaterial(pattern_version_id=v.id, material_id=m.id, quantity=1, unit="spool", position=0)
        s.add(pm)

    # Delete the pattern; versions and pattern_materials should disappear.
    with database.session() as s:
        p = s.scalar(select(Pattern).where(Pattern.name_key == "rs2"))
        assert p is not None
        p.current_version_id = None
        s.flush()
        s.delete(p)

    with database.session() as s:
        assert s.scalars(select(PatternVersion)).first() is None
        assert s.scalars(select(PatternMaterial)).first() is None
        # Materials are NOT deleted (RESTRICT) — they live as canonical records.
        assert s.scalars(select(Material)).first() is not None


def test_updated_at_changes_on_update(database: Database) -> None:
    with database.session() as s:
        p = Pattern(name_key="psy", name_display="Pheasant Soft Hackle")
        s.add(p)
        s.flush()
        created = p.updated_at
    with database.session() as s:
        p = s.scalar(select(Pattern).where(Pattern.name_key == "psy"))
        assert p is not None
        p.name_display = "Pheasant Tail Soft Hackle"
    with database.session() as s:
        p = s.scalar(select(Pattern).where(Pattern.name_key == "psy"))
        assert p is not None
        assert p.updated_at >= created
        assert isinstance(p.updated_at, datetime)


def test_foreign_keys_are_enforced(database: Database) -> None:
    # SQLite needs PRAGMA foreign_keys=ON, which Database enables.
    with pytest.raises(IntegrityError):
        with database.session() as s:
            s.add(PatternVersion(pattern_id=999999, version_number=1, hook_size="14"))


def test_species_and_tags_many_to_many(database: Database) -> None:
    with database.session() as s:
        p = Pattern(name_key="zebra midge", name_display="Zebra Midge")
        s.add(p)
        s.flush()
        sp = Species(name="rainbow trout")
        tag = Tag(name="nymph")
        s.add_all([sp, tag])
        s.flush()
        p.species.append(sp)
        p.tags.append(tag)

    with database.session() as s:
        p = s.scalar(select(Pattern).where(Pattern.name_key == "zebra midge"))
        assert p is not None
        assert [t.name for t in p.tags] == ["nymph"]
        assert [sp.name for sp in p.species] == ["rainbow trout"]
