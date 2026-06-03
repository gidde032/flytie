"""Alembic migrations bundled inside the package so they ship with the wheel."""

from pathlib import Path

MIGRATIONS_DIR: Path = Path(__file__).resolve().parent
