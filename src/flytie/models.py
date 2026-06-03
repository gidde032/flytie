"""SQLAlchemy ORM models for flytie.

Schema overview:
- patterns: top-level pattern record (unique by canonical name).
- pattern_versions: append-only history of pattern revisions.
- materials: canonical material registry.
- pattern_materials: per-version line items linking materials to a version.
- species, pattern_species: target species many-to-many on the pattern.
- tags, pattern_tags: tag many-to-many on the pattern.

The "current" version of a pattern is `Pattern.current_version_id`, which
always references the latest row in `pattern_versions` for that pattern.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    false,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime.

    SQLite doesn't persist tzinfo on `DateTime(timezone=True)` columns; storing
    naive UTC keeps reads and writes symmetric, which matters because the ORM
    keeps the in-memory object around after flush.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# --- Association tables -------------------------------------------------------


class PatternTag(Base):
    __tablename__ = "pattern_tags"
    pattern_id: Mapped[int] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class PatternSpecies(Base):
    __tablename__ = "pattern_species"
    pattern_id: Mapped[int] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    species_id: Mapped[int] = mapped_column(
        ForeignKey("species.id", ondelete="CASCADE"), primary_key=True
    )


# --- Core entities ------------------------------------------------------------


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Lowercase canonical key; presentation form is stored on PatternVersion.name_display
    name_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    name_display: Mapped[str] = mapped_column(String(200), nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "pattern_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_pattern_current_version",
        ),
        nullable=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    versions: Mapped[list[PatternVersion]] = relationship(
        "PatternVersion",
        back_populates="pattern",
        cascade="all, delete-orphan",
        foreign_keys="PatternVersion.pattern_id",
        order_by="PatternVersion.version_number",
    )
    current_version: Mapped[PatternVersion | None] = relationship(
        "PatternVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary="pattern_tags",
        back_populates="patterns",
    )
    species: Mapped[list[Species]] = relationship(
        "Species",
        secondary="pattern_species",
        back_populates="patterns",
    )

    def __repr__(self) -> str:
        return f"<Pattern id={self.id} name={self.name_display!r}>"


class PatternVersion(Base):
    __tablename__ = "pattern_versions"
    __table_args__ = (
        UniqueConstraint("pattern_id", "version_number", name="uq_pattern_version"),
        Index("ix_pattern_versions_pattern_id", "pattern_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern_id: Mapped[int] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    hook_size: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    pattern: Mapped[Pattern] = relationship(
        "Pattern",
        back_populates="versions",
        foreign_keys=[pattern_id],
    )
    materials: Mapped[list[PatternMaterial]] = relationship(
        "PatternMaterial",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="PatternMaterial.position",
    )

    def __repr__(self) -> str:
        return f"<PatternVersion pattern_id={self.pattern_id} v{self.version_number}>"


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(50), default="other", nullable=False)
    default_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<Material id={self.id} name={self.canonical_name!r}>"


class PatternMaterial(Base):
    __tablename__ = "pattern_materials"
    __table_args__ = (Index("ix_pattern_materials_version_id", "pattern_version_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern_version_id: Mapped[int] = mapped_column(
        ForeignKey("pattern_versions.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    version: Mapped[PatternVersion] = relationship("PatternVersion", back_populates="materials")
    material: Mapped[Material] = relationship("Material")


class Species(Base):
    __tablename__ = "species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    patterns: Mapped[list[Pattern]] = relationship(
        "Pattern",
        secondary="pattern_species",
        back_populates="species",
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    patterns: Mapped[list[Pattern]] = relationship(
        "Pattern",
        secondary="pattern_tags",
        back_populates="tags",
    )


# Categories are advisory, validated at the application level.
MATERIAL_CATEGORIES = (
    "thread",
    "hook",
    "hackle",
    "dubbing",
    "flash",
    "body",
    "tail",
    "wing",
    "head",
    "bead",
    "weight",
    "adhesive",
    "other",
)


def normalize_name(name: str) -> str:
    """Lowercase, strip, and collapse whitespace for canonical keys."""
    return " ".join(name.strip().lower().split())


# `updated_at` is maintained by the column-level `onupdate=_utcnow`. We keep an
# explicit event hook so manual attribute reassignment by callers is also
# captured (column-level `onupdate` only fires when the row is otherwise dirty).
@event.listens_for(Pattern, "before_update")
def _pattern_before_update(_mapper: object, _connection: object, target: Pattern) -> None:
    # Only refresh updated_at if the caller did not set it explicitly during
    # this flush. This preserves caller-supplied timestamps (e.g., JSON import).
    from sqlalchemy import inspect

    state = inspect(target)
    if "updated_at" in state.attrs and state.attrs.updated_at.history.has_changes():
        return
    target.updated_at = _utcnow()
