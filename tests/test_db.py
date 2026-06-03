"""Tests for the Database wrapper and CLI `init` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from flytie.cli import app
from flytie.config import load_settings
from flytie.db import Database


def test_init_creates_db_file(env_dirs: tuple[Path, Path]) -> None:
    _, data_dir = env_dirs
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.stdout
    assert (data_dir / "flytie.sqlite3").exists()
    assert "Initialized flytie database" in result.stdout


def test_init_is_idempotent_without_force(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0
    second = runner.invoke(app, ["init"])
    assert second.exit_code == 0
    assert "already exists" in second.stdout.lower()


def test_init_force_recreates(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"])
    # Write a sentinel row, then re-init with --force, expect the table empty.
    settings = load_settings()
    db = Database.from_settings(settings)
    from flytie.models import Pattern

    with db.session() as s:
        s.add(Pattern(name_key="sentinel", name_display="Sentinel"))
    db.engine.dispose()

    result = runner.invoke(app, ["init", "--force"])
    assert result.exit_code == 0

    db2 = Database.from_settings(load_settings())
    from sqlalchemy import select

    with db2.session() as s:
        assert s.scalars(select(Pattern)).first() is None


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "flytie" in result.stdout
