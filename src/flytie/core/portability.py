"""JSON import/export for pattern portability (FR-7).

The export format is a documented, versioned JSON schema so a pattern library
moves cleanly between machines and can be shared as a community pattern set.

Schema (``flytie_export_version`` 1)
------------------------------------
The top-level document is an :class:`ExportDocument`::

    {
      "flytie_export_version": 1,
      "exported_at": "2026-05-22T12:00:00",
      "patterns": [ <ExportPattern>, ... ]
    }

Each :class:`ExportPattern` carries its *full* version history — exporting
only the current version would lose data on round-trip, and versioning is a
first-class feature. Exactly one version per pattern has ``is_current: true``.

Export captures the whole database or a tag/species-filtered subset. Import
(see :func:`import_document`) is transactional — a failed import leaves the
database untouched — and offers skip / overwrite / rename conflict resolution.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from flytie.core.patterns import (
    get_or_create_material,
    get_or_create_species,
    get_or_create_tag,
    hard_delete_pattern,
)
from flytie.models import (
    Pattern,
    PatternMaterial,
    PatternVersion,
    Species,
    Tag,
    normalize_name,
)

# The `get_or_create_*` helpers are package-internal infrastructure of
# `flytie.core`. They are reused here (rather than reimplemented) so that
# material/tag/species creation — and material-category validation — stays
# identical to the path the `add`/`edit` commands take.

# Bump when the schema changes incompatibly. Import refuses a higher number.
EXPORT_FORMAT_VERSION = 1

# Hard cap on import file size. The JSON is held three times during parse
# (raw text, json.loads dict, Pydantic model), so a 50 MiB file peaks around
# 200 MiB of process memory — generous for a personal library, low enough that
# a runaway file can't OOM a laptop.
MAX_IMPORT_FILE_BYTES = 50 * 1024 * 1024


def _utcnow() -> datetime:
    """Naive UTC timestamp, matching how the rest of the project stores time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- schema (the documented JSON shape, as Pydantic models) ------------------


class ExportMaterial(BaseModel):
    canonical_name: str
    category: str = "other"
    quantity: float | None = None
    unit: str | None = None
    notes: str = ""


class ExportVersion(BaseModel):
    version_number: int
    hook_size: str
    difficulty: int | None = None
    instructions: str = ""
    notes: str = ""
    created_at: datetime
    # At most one version per pattern may be the current one. Zero is
    # permitted (import falls back to the highest version_number, as
    # documented in docs/json-schema.md); two or more is rejected by
    # `parse_document` since it is genuinely ambiguous.
    is_current: bool = False
    materials: list[ExportMaterial] = Field(default_factory=list)


class ExportPattern(BaseModel):
    name: str
    is_deleted: bool = False
    tags: list[str] = Field(default_factory=list)
    species: list[str] = Field(default_factory=list)
    versions: list[ExportVersion] = Field(default_factory=list)


class ExportDocument(BaseModel):
    flytie_export_version: int = EXPORT_FORMAT_VERSION
    exported_at: datetime = Field(default_factory=_utcnow)
    patterns: list[ExportPattern] = Field(default_factory=list)


class PortabilityError(RuntimeError):
    """Raised for malformed or incompatible import files."""


# --- export ------------------------------------------------------------------


def _load_patterns_for_export(
    session: Session,
    *,
    tag: str | None,
    species: str | None,
    include_deleted: bool,
) -> list[Pattern]:
    stmt = select(Pattern).options(
        selectinload(Pattern.tags),
        selectinload(Pattern.species),
        selectinload(Pattern.versions)
        .selectinload(PatternVersion.materials)
        .selectinload(PatternMaterial.material),
    )
    if not include_deleted:
        stmt = stmt.where(Pattern.is_deleted.is_(False))
    if tag:
        stmt = stmt.where(Pattern.tags.any(Tag.name == normalize_name(tag)))
    if species:
        stmt = stmt.where(Pattern.species.any(Species.name == normalize_name(species)))
    stmt = stmt.order_by(Pattern.name_key)
    return list(session.scalars(stmt))


def _pattern_to_export(pattern: Pattern) -> ExportPattern:
    versions: list[ExportVersion] = []
    for v in sorted(pattern.versions, key=lambda x: x.version_number):
        materials = [
            ExportMaterial(
                canonical_name=pm.material.canonical_name,
                category=pm.material.category,
                quantity=pm.quantity,
                unit=pm.unit,
                notes=pm.notes,
            )
            for pm in sorted(v.materials, key=lambda pm: pm.position)
        ]
        versions.append(
            ExportVersion(
                version_number=v.version_number,
                hook_size=v.hook_size,
                difficulty=v.difficulty,
                instructions=v.instructions,
                notes=v.notes,
                created_at=v.created_at,
                is_current=v.id == pattern.current_version_id,
                materials=materials,
            )
        )
    return ExportPattern(
        name=pattern.name_display,
        is_deleted=pattern.is_deleted,
        tags=sorted(t.name for t in pattern.tags),
        species=sorted(s.name for s in pattern.species),
        versions=versions,
    )


def build_export_document(
    session: Session,
    *,
    tag: str | None = None,
    species: str | None = None,
    include_deleted: bool = False,
) -> ExportDocument:
    """Build an :class:`ExportDocument` for the whole DB or a filtered subset.

    `tag` and `species` narrow the selection; `include_deleted` adds
    soft-deleted patterns (excluded by default, as elsewhere in the CLI).
    """
    patterns = _load_patterns_for_export(
        session, tag=tag, species=species, include_deleted=include_deleted
    )
    return ExportDocument(
        exported_at=_utcnow(),
        patterns=[_pattern_to_export(p) for p in patterns],
    )


def document_to_json(document: ExportDocument) -> str:
    """Serialize an export document to a pretty-printed JSON string."""
    return document.model_dump_json(indent=2) + "\n"


# --- import-side parsing (used by the import command in this module) ---------


def parse_document(raw_text: str) -> ExportDocument:
    """Parse and validate raw JSON text into an :class:`ExportDocument`.

    Raises :class:`PortabilityError` for malformed JSON, a structure that
    doesn't match the schema, an export-format version newer than this build
    understands, a duplicate pattern name within the file, or a pattern that
    flags more than one version as current.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PortabilityError("The import file is not valid JSON.") from exc
    try:
        document = ExportDocument.model_validate(data)
    except ValidationError as exc:
        raise PortabilityError(
            "The import file does not match the flytie export schema:\n"
            f"{exc.error_count()} validation error(s)."
        ) from exc
    if document.flytie_export_version > EXPORT_FORMAT_VERSION:
        raise PortabilityError(
            f"This file was written by a newer flytie "
            f"(export format v{document.flytie_export_version}); "
            f"this build understands up to v{EXPORT_FORMAT_VERSION}. "
            "Upgrade flytie and try again."
        )

    # Reject duplicate pattern names within the file up front. Phase 6 review:
    # a duplicate inside one file silently corrupted the import under
    # `--on-conflict overwrite` — the second occurrence's overwrite would
    # delete the pattern the first occurrence had *just* created.
    seen_names: dict[str, str] = {}
    for exported in document.patterns:
        key = normalize_name(exported.name)
        if not key:
            # Empty names get a clearer message during import; skip the
            # dup-check here so we don't squash that diagnostic.
            continue
        if key in seen_names:
            raise PortabilityError(
                f"The import file lists two patterns with the same name "
                f"({seen_names[key]!r} and {exported.name!r}). "
                "Pattern names must be unique within an import file."
            )
        seen_names[key] = exported.name

        # A pattern may flag at most one version as current. Zero is allowed
        # (documented fallback to the highest version number); two or more
        # is genuinely ambiguous and is rejected so the user fixes the file
        # rather than getting an unpredictable import.
        current_count = sum(1 for v in exported.versions if v.is_current)
        if current_count > 1:
            raise PortabilityError(
                f"Pattern {exported.name!r} flags {current_count} versions as "
                "current; at most one version may be marked is_current."
            )
    return document


# --- import ------------------------------------------------------------------

# How to resolve a pattern whose name already exists in the database.
CONFLICT_MODES = ("skip", "overwrite", "rename")


class ImportResult(BaseModel):
    """Summary of an import run, for reporting back to the user."""

    created: list[str] = Field(default_factory=list)
    overwritten: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    # original name -> the new name it was imported under
    renamed: dict[str, str] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.created) + len(self.overwritten) + len(self.skipped) + len(self.renamed)


def _unique_import_name(session: Session, base_name: str) -> str:
    """Return a name not yet used in the DB, derived from `base_name`."""
    candidate = f"{base_name} (imported)"
    counter = 2
    while (
        session.scalar(select(Pattern.id).where(Pattern.name_key == normalize_name(candidate)))
        is not None
    ):
        candidate = f"{base_name} (imported {counter})"
        counter += 1
    return candidate


def _create_pattern_from_export(
    session: Session, exported: ExportPattern, *, name_override: str | None = None
) -> Pattern:
    """Build a full Pattern (with its entire version history) from export data.

    Version numbers and `created_at` timestamps are preserved verbatim so the
    import is a faithful round-trip, not an approximation.
    """
    name = name_override if name_override is not None else exported.name
    name_key = normalize_name(name)
    if not name_key:
        raise PortabilityError("The import file contains a pattern with an empty name.")
    if not exported.versions:
        raise PortabilityError(
            f"Imported pattern {name!r} has no versions; every pattern needs at least one."
        )

    pattern = Pattern(
        name_key=name_key,
        name_display=name.strip(),
        is_deleted=exported.is_deleted,
    )
    session.add(pattern)
    session.flush()

    for tag_name in exported.tags:
        if normalize_name(tag_name):
            pattern.tags.append(get_or_create_tag(session, tag_name))
    for species_name in exported.species:
        if normalize_name(species_name):
            pattern.species.append(get_or_create_species(session, species_name))

    sorted_versions = sorted(exported.versions, key=lambda v: v.version_number)
    created_versions: list[PatternVersion] = []
    for exported_version in sorted_versions:
        version = PatternVersion(
            pattern_id=pattern.id,
            version_number=exported_version.version_number,
            hook_size=exported_version.hook_size,
            difficulty=exported_version.difficulty,
            instructions=exported_version.instructions,
            notes=exported_version.notes,
            created_at=exported_version.created_at,
        )
        session.add(version)
        session.flush()
        created_versions.append(version)
        for position, material_line in enumerate(exported_version.materials):
            try:
                material = get_or_create_material(
                    session, material_line.canonical_name, material_line.category
                )
            except ValueError as exc:
                raise PortabilityError(
                    f"Pattern {name!r}, version {exported_version.version_number}: {exc}"
                ) from exc
            session.add(
                PatternMaterial(
                    pattern_version_id=version.id,
                    material_id=material.id,
                    quantity=material_line.quantity,
                    unit=material_line.unit,
                    position=position,
                    notes=material_line.notes,
                )
            )

    # Pick the current version: the one flagged `is_current`, or — if the file
    # flags none — fall back to the highest version number. parse_document
    # already rejected files that flag more than one.
    current = created_versions[-1]
    for version, exported_version in zip(created_versions, sorted_versions, strict=True):
        if exported_version.is_current:
            current = version
    pattern.current_version_id = current.id
    pattern.current_version = current
    session.flush()
    return pattern


def import_document(
    session: Session, document: ExportDocument, *, on_conflict: str = "skip"
) -> ImportResult:
    """Import every pattern in `document` into the database.

    `on_conflict` decides what happens when a pattern's name already exists:
    ``skip`` leaves the existing one untouched, ``overwrite`` replaces it, and
    ``rename`` imports the incoming pattern under a fresh, non-colliding name.

    This function does not commit. The caller runs it inside a single
    `Database.session()` block, which commits on success and rolls back on any
    exception — so a failed import leaves the database completely unchanged.
    """
    if on_conflict not in CONFLICT_MODES:
        raise PortabilityError(
            f"Unknown conflict mode {on_conflict!r}. Choose one of: {', '.join(CONFLICT_MODES)}."
        )
    result = ImportResult()
    try:
        for exported in document.patterns:
            name_key = normalize_name(exported.name)
            if not name_key:
                raise PortabilityError("The import file contains a pattern with an empty name.")
            existing = session.scalar(select(Pattern).where(Pattern.name_key == name_key))
            if existing is None:
                _create_pattern_from_export(session, exported)
                result.created.append(exported.name)
            elif on_conflict == "skip":
                result.skipped.append(exported.name)
            elif on_conflict == "overwrite":
                hard_delete_pattern(session, exported.name)
                session.flush()
                _create_pattern_from_export(session, exported)
                result.overwritten.append(exported.name)
            else:  # rename
                new_name = _unique_import_name(session, exported.name)
                _create_pattern_from_export(session, exported, name_override=new_name)
                result.renamed[exported.name] = new_name
    except PortabilityError:
        raise
    except SQLAlchemyError as exc:
        raise PortabilityError(
            "The import data violates a database constraint "
            "(for example, duplicate version numbers within one pattern)."
        ) from exc
    return result
