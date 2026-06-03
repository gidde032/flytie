"""Helpers that turn CLI-friendly strings into DTOs.

The `--material` flag accepts a compact mini-grammar:

    name,category,quantity,unit,notes

Empty fields are allowed (trailing commas may be omitted). Examples:

    --material "grizzly hackle,hackle,1,feather"
    --material "thread,thread,1,spool,8/0 black"
    --material "pheasant tail,tail"

For richer payloads (multi-line notes, many materials), use `--from-file` with
a JSON or TOML document conforming to ``PatternInput``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from flytie.core.dto import MaterialLineDTO, PatternInput

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


# Reject pattern files larger than 5 MiB to fence off accidental binary loads.
_MAX_PATTERN_FILE_BYTES = 5 * 1024 * 1024


class MaterialParseError(ValueError):
    """Raised when a `--material` mini-grammar string can't be parsed."""


class PatternFileError(ValueError):
    """Raised when a `--from-file` pattern document can't be loaded.

    Carries an actionable message; the CLI surfaces this to the user.
    """


def parse_material_spec(spec: str) -> MaterialLineDTO:
    parts = [p.strip() for p in spec.split(",", maxsplit=4)]
    if not parts or not parts[0]:
        raise MaterialParseError(
            f"Material specification {spec!r} is empty — expected at least a name. "
            f'Try --material "grizzly hackle,hackle,1,feather".'
        )
    name = parts[0]
    category = parts[1] if len(parts) > 1 and parts[1] else "other"
    quantity: float | None = None
    if len(parts) > 2 and parts[2]:
        try:
            quantity = float(parts[2])
        except ValueError as exc:
            raise MaterialParseError(
                f"Material {name!r} has non-numeric quantity {parts[2]!r}. "
                f"Try a positive number like 1 or 0.5."
            ) from exc
        # Reviewer B (med): reject non-finite or non-positive values so
        # downstream aggregation can't be poisoned by NaN/inf/negatives.
        import math

        if math.isnan(quantity) or math.isinf(quantity) or quantity < 0:
            raise MaterialParseError(
                f"Material {name!r} has invalid quantity {quantity!r}; "
                f"expected a finite, non-negative number."
            )
    unit = parts[3] if len(parts) > 3 and parts[3] else None
    notes = parts[4] if len(parts) > 4 else ""
    return MaterialLineDTO(
        canonical_name=name,
        category=category,
        quantity=quantity,
        unit=unit,
        notes=notes,
    )


def load_pattern_file(path: Path) -> PatternInput:
    """Load a JSON or TOML pattern document into a `PatternInput`.

    - Expands ``~`` and resolves the path.
    - Refuses unknown extensions with a clear message.
    - Refuses files over 5 MiB.
    - Wraps JSON/TOML decode errors in ``PatternFileError`` with the path.
    - Lets Pydantic ``ValidationError`` propagate so the caller can format it.
    """
    expanded = path.expanduser().resolve()
    if not expanded.exists():
        raise PatternFileError(f"Pattern file not found: {expanded}")
    if not expanded.is_file():
        raise PatternFileError(f"Pattern path is not a file: {expanded}")
    size = expanded.stat().st_size
    if size > _MAX_PATTERN_FILE_BYTES:
        raise PatternFileError(
            f"Pattern file {expanded} is {size} bytes; refusing to load files "
            f"larger than {_MAX_PATTERN_FILE_BYTES} bytes."
        )
    ext = expanded.suffix.lower()
    raw: dict[str, Any]
    if ext == ".toml":
        try:
            with expanded.open("rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise PatternFileError(f"{expanded}: TOML parse error — {exc}") from exc
    elif ext == ".json":
        try:
            raw = json.loads(expanded.read_text())
        except json.JSONDecodeError as exc:
            raise PatternFileError(f"{expanded}: JSON parse error — {exc}") from exc
    else:
        raise PatternFileError(
            f"Unsupported pattern file extension {ext!r}; use .json or .toml."
        )
    if not isinstance(raw, dict):
        raise PatternFileError(f"{expanded}: expected a top-level mapping, got {type(raw).__name__}.")
    return PatternInput.model_validate(raw)
