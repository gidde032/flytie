"""Version-aware queries over a pattern's history."""

from __future__ import annotations

import difflib

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flytie.core.dto import MaterialLineDTO, PatternInput, PatternVersionDTO
from flytie.core.patterns import (
    PatternNotFoundError,
    edit_pattern,
    get_pattern,
    to_version_dto,
)
from flytie.models import PatternMaterial, PatternVersion


class VersionNotFoundError(LookupError):
    """Raised when a requested version number doesn't exist for the pattern."""


def list_versions(session: Session, name: str) -> list[PatternVersionDTO]:
    pattern = get_pattern(session, name)
    stmt = (
        select(PatternVersion)
        .options(
            selectinload(PatternVersion.materials).selectinload(PatternMaterial.material),
        )
        .where(PatternVersion.pattern_id == pattern.id)
        .order_by(PatternVersion.version_number)
    )
    rows = list(session.scalars(stmt))
    return [to_version_dto(v) for v in rows]


def get_version(session: Session, name: str, version_number: int) -> PatternVersionDTO:
    pattern = get_pattern(session, name)
    stmt = (
        select(PatternVersion)
        .options(
            selectinload(PatternVersion.materials).selectinload(PatternMaterial.material),
        )
        .where(
            PatternVersion.pattern_id == pattern.id,
            PatternVersion.version_number == version_number,
        )
    )
    version = session.scalar(stmt)
    if version is None:
        raise VersionNotFoundError(
            f"Pattern {pattern.name_display!r} has no version {version_number}."
        )
    return to_version_dto(version)


def diff_versions(
    session: Session, name: str, v1: int, v2: int
) -> tuple[PatternVersionDTO, PatternVersionDTO, list[str]]:
    a = get_version(session, name, v1)
    b = get_version(session, name, v2)
    a_lines = _version_as_lines(a)
    b_lines = _version_as_lines(b)
    diff = list(
        difflib.unified_diff(
            a_lines,
            b_lines,
            fromfile=f"{name} v{v1}",
            tofile=f"{name} v{v2}",
            lineterm="",
        )
    )
    return a, b, diff


def restore_version(session: Session, name: str, version_number: int) -> PatternVersionDTO:
    pattern = get_pattern(session, name)
    source = get_version(session, name, version_number)
    payload = PatternInput(
        name=pattern.name_display,
        hook_size=source.hook_size,
        difficulty=source.difficulty,
        instructions=source.instructions,
        notes=source.notes,
        materials=[
            MaterialLineDTO(
                canonical_name=m.canonical_name,
                category=m.category,
                quantity=m.quantity,
                unit=m.unit,
                notes=m.notes,
            )
            for m in source.materials
        ],
        tags=None,
        species=None,
    )
    updated = edit_pattern(session, name, payload)
    if updated.current_version is None:
        raise RuntimeError(
            f"restore_version: edit_pattern returned a Pattern with no current_version for {name!r}."
        )
    return to_version_dto(updated.current_version)


def _version_as_lines(v: PatternVersionDTO) -> list[str]:
    difficulty = "n/a" if v.difficulty is None else str(v.difficulty)
    lines: list[str] = [
        f"hook_size: {v.hook_size}",
        f"difficulty: {difficulty}",
        "materials:",
    ]
    # Sort by canonical name so diffs reflect actual material changes,
    # not positional reordering noise (Phase-3-deferred redesign, v0.2.0).
    for m in sorted(v.materials, key=lambda m: m.canonical_name):
        qty = "" if m.quantity is None else f" {m.quantity:g}"
        unit = f" {m.unit}" if m.unit else ""
        note = f"  ({m.notes})" if m.notes else ""
        lines.append(f"  - {m.canonical_name}{qty}{unit} [{m.category}]{note}")
    lines.append("instructions:")
    lines.extend("  " + line for line in (v.instructions or "").splitlines())
    lines.append("notes:")
    lines.extend("  " + line for line in (v.notes or "").splitlines())
    return lines


__all__ = [
    "PatternNotFoundError",
    "VersionNotFoundError",
    "diff_versions",
    "get_version",
    "list_versions",
    "restore_version",
]
