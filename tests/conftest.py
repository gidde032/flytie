"""Shared pytest fixtures for flytie tests.

Every test gets an isolated SQLite database in a temp directory, plus a
preconfigured `Database` instance whose settings point at that path. Environment
variables are scoped so tests cannot accidentally read or write the user's
real flytie data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from flytie.config import Settings, load_settings
from flytie.db import Database


@pytest.fixture
def env_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point flytie's config/data dirs at temp paths for the test's duration."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setenv("FLYTIE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FLYTIE_DATA_DIR", str(data_dir))
    monkeypatch.delenv("FLYTIE_DB_PATH", raising=False)
    return config_dir, data_dir


@pytest.fixture
def settings(env_dirs: tuple[Path, Path]) -> Settings:
    return load_settings()


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    db = Database.from_settings(settings)
    db.create_schema()
    try:
        yield db
    finally:
        db.engine.dispose()


@pytest.fixture
def session(database: Database):
    """Yields an open session; commits on success, rolls back on exception."""
    with database.session() as s:
        yield s
