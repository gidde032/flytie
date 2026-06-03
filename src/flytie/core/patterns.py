"""Pattern repository: create/read/update/delete + helpers.

All functions take an open SQLAlchemy `Session` so callers control transaction
boundaries. Returns are either ORM rows (for further composition) or DTOs
(when crossing the CLI boundary).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from flytie.core.dto import (
    MaterialLineDTO,
    PatternDTO,
    PatternInput,
    PatternVersionDTO,
)
from flytie.models import (
    MATERIAL_CATEGORIES,
    Material,
    Pattern,
    PatternMaterial,
    PatternVersion,
    Species,
    Tag,
    normalize_name,
)

# --- helpers ------------------------------------------------------------------


def get_or_create_material(
    session: Session, canonical_name: str, category: str = "other"
) -> Material:
    """Return the existing material with this canonical name, or create one.

    Public since v0.1.1 (Phase 6): the JSON import code in
    ``flytie.core.portability`` needs these helpers, and a cross-module
    import of an underscore-private name was flagged in review.
    """
    canonical = normalize_name(canonical_name)
    if not canonical:
        raise ValueError("Material name cannot be empty.")
    category_key = (category or "other").strip().lower()
    if category_key not in MATERIAL_CATEGORIES:
        raise ValueError(
            f"Unknown material category {category!r}. "
            f"Valid categories: {', '.join(MATERIAL_CATEGORIES)}."
        )
    existing = session.scalar(select(Material).where(Material.canonical_name == canonical))
    if existing:
        return existing
    mat = Material(canonical_name=canonical, category=category_key)
    session.add(mat)
    session.flush()
    return mat


def get_or_create_tag(session: Session, name: str) -> Tag:
    """Return the existing tag with this name, or create one."""
    key = normalize_name(name)
    if not key:
        raise ValueError("Tag name cannot be empty.")
    existing = session.scalar(select(Tag).where(Tag.name == key))
    if existing:
        return existing
    tag = Tag(name=key)
    session.add(tag)
    session.flush()
    return tag


def get_or_create_species(session: Session, name: str) -> Species:
    """Return the existing species with this name, or create one."""
    key = normalize_name(name)
    if not key:
        raise ValueError("Species name cannot be empty.")
    existing = session.scalar(select(Species).where(Species.name == key))
    if existing:
        return existing
    sp = Species(name=key)
    session.add(sp)
    session.flush()
    return sp


# Backward-compatible aliases. The three helpers above were underscore-private
# prior to v0.1.1; the leading-underscore names are retained so any code that
# imported them keeps working through this release. Prefer the public names.
_get_or_create_material = get_or_create_material
_get_or_create_tag = get_or_create_tag
_get_or_create_species = get_or_create_species


def _to_version_dto(version: PatternVersion) -> PatternVersionDTO:
    materials = [
        MaterialLineDTO(
            canonical_name=pm.material.canonical_name,
            category=pm.material.category,
            quantity=pm.quantity,
            unit=pm.unit,
            notes=pm.notes,
        )
        for pm in version.materials
    ]
    return PatternVersionDTO(
        version_number=version.version_number,
        hook_size=version.hook_size,
        difficulty=version.difficulty,
        instructions=version.instructions,
        notes=version.notes,
        created_at=version.created_at,
        materials=materials,
    )


def _to_pattern_dto(pattern: Pattern) -> PatternDTO:
    return PatternDTO(
        id=pattern.id,
        name=pattern.name_display,
        is_deleted=pattern.is_deleted,
        created_at=pattern.created_at,
        updated_at=pattern.updated_at,
        tags=[t.name for t in pattern.tags],
        species=[s.name for s in pattern.species],
        current_version=_to_version_dto(pattern.current_version)
        if pattern.current_version
        else None,
    )


class PatternNotFoundError(LookupError):
    """Raised when a pattern lookup fails."""


class DuplicatePatternError(ValueError):
    """Raised when a pattern create would collide with an existing canonical name."""


# --- public API ---------------------------------------------------------------


def get_pattern(session: Session, name: str, include_deleted: bool = False) -> Pattern:
    key = normalize_name(name)
    stmt = (
        select(Pattern)
        .options(
            selectinload(Pattern.tags),
            selectinload(Pattern.species),
            selectinload(Pattern.versions)
            .selectinload(PatternVersion.materials)
            .selectinload(PatternMaterial.material),
            selectinload(Pattern.current_version)
            .selectinload(PatternVersion.materials)
            .selectinload(PatternMaterial.material),
        )
        .where(Pattern.name_key == key)
    )
    if not include_deleted:
        stmt = stmt.where(Pattern.is_deleted.is_(False))
    pattern = session.scalar(stmt)
    if pattern is None:
        raise PatternNotFoundError(f"No pattern named {name!r}.")
    return pattern


def hook_size_tokens(hook_size: str) -> set[int]:
    """Extract the set of integer hook sizes a hook-size string represents.

    "14" -> {14}; "12-16" -> {12,13,14,15,16}; "14, 16" -> {14,16}.
    Non-numeric strings (e.g. "streamer") yield an empty set, in which case
    callers fall back to substring matching.
    """
    import re

    tokens: set[int] = set()
    for chunk in re.split(r"[,/;]", hook_size):
        chunk = chunk.strip()
        range_match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", chunk)
        if range_match:
            lo, hi = int(range_match.group(1)), int(range_match.group(2))
            tokens.update(range(min(lo, hi), max(lo, hi) + 1))
        elif chunk.isdigit():
            tokens.add(int(chunk))
    return tokens


def _matches_hook_size(version: PatternVersion | None, query: str) -> bool:
    """True if a pattern version's hook size matches the query (size or range)."""
    if version is None:
        return False
    stored = version.hook_size or ""
    query_tokens = hook_size_tokens(query)
    stored_tokens = hook_size_tokens(stored)
    if query_tokens and stored_tokens:
        return bool(query_tokens & stored_tokens)
    # Either side is non-numeric — fall back to case-insensitive substring.
    return query.strip().lower() in stored.lower()


def list_patterns(
    session: Session,
    *,
    tag: str | None = None,
    species: str | None = None,
    hook_size: str | None = None,
    include_deleted: bool = False,
) -> list[Pattern]:
    stmt = select(Pattern).options(
        selectinload(Pattern.tags),
        selectinload(Pattern.species),
        selectinload(Pattern.current_version)
        .selectinload(PatternVersion.materials)
        .selectinload(PatternMaterial.material),
    )
    if not include_deleted:
        stmt = stmt.where(Pattern.is_deleted.is_(False))
    if tag:
        tag_key = normalize_name(tag)
        stmt = stmt.where(Pattern.tags.any(Tag.name == tag_key))
    if species:
        species_key = normalize_name(species)
        stmt = stmt.where(Pattern.species.any(Species.name == species_key))
    stmt = stmt.order_by(Pattern.name_key)
    rows = list(session.scalars(stmt))
    if hook_size:
        # Hook-size matching needs interval arithmetic that's awkward in SQL;
        # post-filter in Python on the (already eager-loaded) current version.
        rows = [p for p in rows if _matches_hook_size(p.current_version, hook_size)]
    return rows


def _escape_like(text: str) -> str:
    """Escape SQL LIKE wildcards so user input is treated literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_patterns(session: Session, query: str) -> list[Pattern]:
    escaped = _escape_like(query.strip().lower())
    q = f"%{escaped}%"
    stmt = (
        select(Pattern)
        .options(
            selectinload(Pattern.tags),
            selectinload(Pattern.species),
            selectinload(Pattern.current_version)
            .selectinload(PatternVersion.materials)
            .selectinload(PatternMaterial.material),
        )
        .where(Pattern.is_deleted.is_(False))
        .where(
            or_(
                Pattern.name_key.like(q, escape="\\"),
                Pattern.current_version.has(PatternVersion.instructions.ilike(q, escape="\\")),
                Pattern.current_version.has(PatternVersion.notes.ilike(q, escape="\\")),
                Pattern.current_version.has(
                    PatternVersion.materials.any(
                        PatternMaterial.material.has(Material.canonical_name.like(q, escape="\\"))
                    )
                ),
            )
        )
        .order_by(Pattern.name_key)
    )
    return list(session.scalars(stmt))


def create_pattern(session: Session, payload: PatternInput) -> Pattern:
    name_key = normalize_name(payload.name)
    if not name_key:
        raise ValueError("Pattern name cannot be empty.")
    if not payload.hook_size or not payload.hook_size.strip():
        raise ValueError("Pattern hook_size cannot be empty.")
    existing = session.scalar(select(Pattern).where(Pattern.name_key == name_key))
    if existing is not None:
        raise DuplicatePatternError(f"Pattern {payload.name!r} already exists.")
    pattern = Pattern(name_key=name_key, name_display=payload.name.strip())
    session.add(pattern)
    session.flush()

    version = PatternVersion(
        pattern_id=pattern.id,
        version_number=1,
        hook_size=payload.hook_size.strip(),
        difficulty=payload.difficulty,
        instructions=payload.instructions,
        notes=payload.notes,
    )
    session.add(version)
    session.flush()
    pattern.current_version_id = version.id
    pattern.current_version = version

    _attach_materials(session, version, payload.materials or [])
    _sync_tags(session, pattern, payload.tags or [])
    _sync_species(session, pattern, payload.species or [])
    session.flush()
    return pattern


def edit_pattern(session: Session, name: str, payload: PatternInput) -> Pattern:
    """Apply an edit by appending a new immutable version.

    Sentinel rules: ``None`` for tags/species/materials means "leave unchanged".
    An empty list means "clear all". This lets `flytie edit --no-tags` express
    intent unambiguously in Phase 2.
    """
    if not payload.hook_size or not payload.hook_size.strip():
        raise ValueError("Pattern hook_size cannot be empty.")
    pattern = get_pattern(session, name)
    last = max((v.version_number for v in pattern.versions), default=0)
    new_version = PatternVersion(
        pattern_id=pattern.id,
        version_number=last + 1,
        hook_size=payload.hook_size.strip(),
        difficulty=payload.difficulty,
        instructions=payload.instructions,
        notes=payload.notes,
    )
    pattern.versions.append(new_version)
    session.flush()
    pattern.current_version_id = new_version.id
    pattern.current_version = new_version
    # Materials carry over the previous version's lines if the caller didn't
    # supply any (a no-op edit should preserve the recipe, not blank it).
    if payload.materials is None:
        previous = pattern.versions[-2] if len(pattern.versions) >= 2 else None
        if previous is not None:
            _copy_materials(session, previous, new_version)
    else:
        _attach_materials(session, new_version, payload.materials)
    if payload.tags is not None:
        _sync_tags(session, pattern, payload.tags)
    if payload.species is not None:
        _sync_species(session, pattern, payload.species)
    # Allow renames via display name; canonical key is preserved.
    pattern.name_display = payload.name.strip() or pattern.name_display
    session.flush()
    return pattern


def _copy_materials(session: Session, src: PatternVersion, dst: PatternVersion) -> None:
    for pm in src.materials:
        session.add(
            PatternMaterial(
                pattern_version_id=dst.id,
                material_id=pm.material_id,
                quantity=pm.quantity,
                unit=pm.unit,
                position=pm.position,
                notes=pm.notes,
            )
        )


def soft_delete_pattern(session: Session, name: str) -> Pattern:
    pattern = get_pattern(session, name)
    pattern.is_deleted = True
    session.flush()
    return pattern


def hard_delete_pattern(session: Session, name: str) -> None:
    pattern = get_pattern(session, name, include_deleted=True)
    # Break the FK to allow ORM cascade on versions.
    pattern.current_version_id = None
    session.flush()
    session.delete(pattern)
    session.flush()


def add_tags(session: Session, name: str, tags: Iterable[str]) -> Pattern:
    pattern = get_pattern(session, name)
    existing = {t.name for t in pattern.tags}
    for raw in tags:
        key = normalize_name(raw)
        if not key or key in existing:
            continue
        pattern.tags.append(get_or_create_tag(session, key))
        existing.add(key)
    session.flush()
    return pattern


def remove_tags(session: Session, name: str, tags: Iterable[str]) -> Pattern:
    pattern = get_pattern(session, name)
    keys = {normalize_name(t) for t in tags}
    pattern.tags[:] = [t for t in pattern.tags if t.name not in keys]
    session.flush()
    return pattern


def to_dto(pattern: Pattern) -> PatternDTO:
    return _to_pattern_dto(pattern)


def to_version_dto(version: PatternVersion) -> PatternVersionDTO:
    return _to_version_dto(version)


# --- internal sync helpers ----------------------------------------------------


def _attach_materials(
    session: Session, version: PatternVersion, lines: Iterable[MaterialLineDTO]
) -> None:
    for pos, line in enumerate(lines):
        material = get_or_create_material(session, line.canonical_name, line.category)
        pm = PatternMaterial(
            pattern_version_id=version.id,
            material_id=material.id,
            quantity=line.quantity,
            unit=line.unit,
            position=pos,
            notes=line.notes,
        )
        session.add(pm)


def _sync_tags(session: Session, pattern: Pattern, tags: Iterable[str]) -> None:
    desired = [get_or_create_tag(session, t) for t in tags if normalize_name(t)]
    seen: set[str] = set()
    pattern.tags.clear()
    for tag in desired:
        if tag.name in seen:
            continue
        pattern.tags.append(tag)
        seen.add(tag.name)


def _sync_species(session: Session, pattern: Pattern, species: Iterable[str]) -> None:
    desired = [get_or_create_species(session, s) for s in species if normalize_name(s)]
    seen: set[str] = set()
    pattern.species.clear()
    for sp in desired:
        if sp.name in seen:
            continue
        pattern.species.append(sp)
        seen.add(sp.name)
