"""Read-only library statistics for ``flytie stats``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flytie.models import (
    Material,
    Pattern,
    PatternMaterial,
    PatternSpecies,
    PatternVersion,
    Species,
    Tag,
)


@dataclass(frozen=True)
class RankedItem:
    """A name with a count, used for top-N lists."""

    name: str
    count: int


@dataclass(frozen=True)
class TimelineEntry:
    """A pattern name paired with a date."""

    name: str
    date: datetime


@dataclass(frozen=True)
class LibraryStats:
    """All computed statistics for the library."""

    # Overview
    active_patterns: int = 0
    deleted_patterns: int = 0
    total_versions: int = 0
    total_materials: int = 0
    total_species: int = 0
    total_tags: int = 0

    # Top 5s
    top_materials: list[RankedItem] = field(default_factory=list)
    top_species: list[RankedItem] = field(default_factory=list)
    top_versioned: list[RankedItem] = field(default_factory=list)

    # Timeline
    oldest: TimelineEntry | None = None
    newest: TimelineEntry | None = None
    most_recently_edited: TimelineEntry | None = None
    avg_versions_per_pattern: float = 0.0


def library_stats(session: Session) -> LibraryStats:
    """Compute a full library summary from the current database state."""

    # --- counts ---------------------------------------------------------------

    active_patterns = (
        session.scalar(
            select(func.count()).select_from(Pattern).where(Pattern.is_deleted.is_(False))
        )
        or 0
    )

    deleted_patterns = (
        session.scalar(
            select(func.count()).select_from(Pattern).where(Pattern.is_deleted.is_(True))
        )
        or 0
    )

    # Reference-table totals — computed regardless of active count so the
    # early-return path stays consistent with the normal path.
    total_materials = session.scalar(select(func.count()).select_from(Material)) or 0
    total_species = session.scalar(select(func.count()).select_from(Species)) or 0
    total_tags = session.scalar(select(func.count()).select_from(Tag)) or 0

    if active_patterns == 0:
        return LibraryStats(
            deleted_patterns=deleted_patterns,
            total_materials=total_materials,
            total_species=total_species,
            total_tags=total_tags,
        )

    # Total versions across active patterns only
    total_versions = (
        session.scalar(
            select(func.count())
            .select_from(PatternVersion)
            .join(Pattern, PatternVersion.pattern_id == Pattern.id)
            .where(Pattern.is_deleted.is_(False))
        )
        or 0
    )

    # --- top 5s ---------------------------------------------------------------

    # Most-used materials: count distinct active patterns whose current version
    # references each material.
    top_materials_rows = session.execute(
        select(Material.canonical_name, func.count(func.distinct(Pattern.id)).label("cnt"))
        .select_from(PatternMaterial)
        .join(PatternVersion, PatternMaterial.pattern_version_id == PatternVersion.id)
        .join(Pattern, PatternVersion.pattern_id == Pattern.id)
        .join(Material, PatternMaterial.material_id == Material.id)
        .where(Pattern.is_deleted.is_(False))
        .where(Pattern.current_version_id == PatternVersion.id)
        .group_by(Material.canonical_name)
        .order_by(func.count(func.distinct(Pattern.id)).desc())
        .limit(5)
    ).all()
    top_materials = [RankedItem(name=r[0], count=r[1]) for r in top_materials_rows]

    # Most-tagged species: count distinct active patterns
    top_species_rows = session.execute(
        select(Species.name, func.count(func.distinct(PatternSpecies.pattern_id)).label("cnt"))
        .select_from(PatternSpecies)
        .join(Species, PatternSpecies.species_id == Species.id)
        .join(Pattern, PatternSpecies.pattern_id == Pattern.id)
        .where(Pattern.is_deleted.is_(False))
        .group_by(Species.name)
        .order_by(func.count(func.distinct(PatternSpecies.pattern_id)).desc())
        .limit(5)
    ).all()
    top_species = [RankedItem(name=r[0], count=r[1]) for r in top_species_rows]

    # Most-versioned patterns
    top_versioned_rows = session.execute(
        select(Pattern.name_display, func.count(PatternVersion.id).label("cnt"))
        .select_from(PatternVersion)
        .join(Pattern, PatternVersion.pattern_id == Pattern.id)
        .where(Pattern.is_deleted.is_(False))
        .group_by(Pattern.id, Pattern.name_display)
        .order_by(func.count(PatternVersion.id).desc())
        .limit(5)
    ).all()
    top_versioned = [RankedItem(name=r[0], count=r[1]) for r in top_versioned_rows]

    # --- timeline -------------------------------------------------------------

    oldest_row = session.execute(
        select(Pattern.name_display, Pattern.created_at)
        .where(Pattern.is_deleted.is_(False))
        .order_by(Pattern.created_at.asc())
        .limit(1)
    ).first()
    oldest = TimelineEntry(name=oldest_row[0], date=oldest_row[1]) if oldest_row else None

    newest_row = session.execute(
        select(Pattern.name_display, Pattern.created_at)
        .where(Pattern.is_deleted.is_(False))
        .order_by(Pattern.created_at.desc())
        .limit(1)
    ).first()
    newest = TimelineEntry(name=newest_row[0], date=newest_row[1]) if newest_row else None

    most_recent_row = session.execute(
        select(Pattern.name_display, Pattern.updated_at)
        .where(Pattern.is_deleted.is_(False))
        .order_by(Pattern.updated_at.desc())
        .limit(1)
    ).first()
    most_recently_edited = (
        TimelineEntry(name=most_recent_row[0], date=most_recent_row[1]) if most_recent_row else None
    )

    avg_versions = round(total_versions / active_patterns, 1) if active_patterns else 0.0

    return LibraryStats(
        active_patterns=active_patterns,
        deleted_patterns=deleted_patterns,
        total_versions=total_versions,
        total_materials=total_materials,
        total_species=total_species,
        total_tags=total_tags,
        top_materials=top_materials,
        top_species=top_species,
        top_versioned=top_versioned,
        oldest=oldest,
        newest=newest,
        most_recently_edited=most_recently_edited,
        avg_versions_per_pattern=avg_versions,
    )
