"""Data transfer objects passed across the core/CLI boundary.

These are plain Pydantic models that don't carry an ORM session, so they're
safe to return from session-scoped functions and render or serialize.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MaterialLineDTO(BaseModel):
    canonical_name: str
    category: str = "other"
    quantity: float | None = None
    unit: str | None = None
    notes: str = ""


class PatternVersionDTO(BaseModel):
    version_number: int
    hook_size: str
    difficulty: int | None = None
    instructions: str = ""
    notes: str = ""
    created_at: datetime
    materials: list[MaterialLineDTO] = Field(default_factory=list)


class PatternDTO(BaseModel):
    id: int
    name: str
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    species: list[str] = Field(default_factory=list)
    current_version: PatternVersionDTO | None = None


class PatternInput(BaseModel):
    """Input payload for creating or editing a pattern.

    Edit semantics:
    - ``tags``/``species`` / ``materials`` set to ``None`` mean "leave unchanged".
    - An empty list means "clear all".
    - For ``create_pattern`` callers, ``None`` is treated as an empty list.
    """

    name: str
    hook_size: str
    difficulty: int | None = None
    instructions: str = ""
    notes: str = ""
    tags: list[str] | None = None
    species: list[str] | None = None
    materials: list[MaterialLineDTO] | None = None
