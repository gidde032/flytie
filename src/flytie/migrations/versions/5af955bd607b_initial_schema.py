"""initial schema

Revision ID: 5af955bd607b
Revises:
Create Date: 2026-05-13 23:17:39.998686

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5af955bd607b"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="other"),
        sa.Column("default_unit", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_materials_canonical_name"), ["canonical_name"], unique=True
        )

    op.create_table(
        "patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("name_display", sa.String(length=200), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["current_version_id"],
            ["pattern_versions.id"],
            name="fk_pattern_current_version",
            ondelete="SET NULL",
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("patterns", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_patterns_name_key"), ["name_key"], unique=True)

    op.create_table(
        "species",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("species", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_species_name"), ["name"], unique=True)

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tags_name"), ["name"], unique=True)

    op.create_table(
        "pattern_species",
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("species_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["species_id"], ["species.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pattern_id", "species_id"),
    )
    op.create_table(
        "pattern_tags",
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pattern_id", "tag_id"),
    )
    op.create_table(
        "pattern_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("hook_size", sa.String(length=50), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pattern_id", "version_number", name="uq_pattern_version"),
    )
    with op.batch_alter_table("pattern_versions", schema=None) as batch_op:
        batch_op.create_index("ix_pattern_versions_pattern_id", ["pattern_id"], unique=False)

    op.create_table(
        "pattern_materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern_version_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["pattern_version_id"], ["pattern_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pattern_materials", schema=None) as batch_op:
        batch_op.create_index(
            "ix_pattern_materials_version_id", ["pattern_version_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("pattern_materials", schema=None) as batch_op:
        batch_op.drop_index("ix_pattern_materials_version_id")
    op.drop_table("pattern_materials")
    with op.batch_alter_table("pattern_versions", schema=None) as batch_op:
        batch_op.drop_index("ix_pattern_versions_pattern_id")
    op.drop_table("pattern_versions")
    op.drop_table("pattern_tags")
    op.drop_table("pattern_species")
    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tags_name"))
    op.drop_table("tags")
    with op.batch_alter_table("species", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_species_name"))
    op.drop_table("species")
    with op.batch_alter_table("patterns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patterns_name_key"))
    op.drop_table("patterns")
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_materials_canonical_name"))
    op.drop_table("materials")
