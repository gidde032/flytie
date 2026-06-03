"""Tests for the settings/config layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from flytie.config import ConfigFile, Settings, load_settings


def test_env_dirs_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setenv("FLYTIE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FLYTIE_DATA_DIR", str(data_dir))
    monkeypatch.delenv("FLYTIE_DB_PATH", raising=False)
    s = load_settings()
    assert s.config_dir == config_dir
    assert s.data_dir == data_dir
    assert s.db_path == data_dir / "flytie.sqlite3"


def test_db_path_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLYTIE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("FLYTIE_DATA_DIR", str(tmp_path))
    custom = tmp_path / "elsewhere.sqlite3"
    monkeypatch.setenv("FLYTIE_DB_PATH", str(custom))
    s = load_settings()
    assert s.db_path == custom


def test_config_file_round_trip(env_dirs: tuple[Path, Path]) -> None:
    s = load_settings()
    cfg = ConfigFile.load(s)
    assert cfg.data == {}
    cfg.set("database.path", "/tmp/explicit.sqlite3")
    cfg.set("pdf.template", "custom")
    cfg.save(s)

    reloaded = ConfigFile.load(s)
    assert reloaded.get("database.path") == "/tmp/explicit.sqlite3"
    assert reloaded.get("pdf.template") == "custom"
    assert reloaded.get("missing.key", default="fallback") == "fallback"


def test_settings_uses_file_db_path(env_dirs: tuple[Path, Path]) -> None:
    _, data_dir = env_dirs
    s = load_settings()
    cfg = ConfigFile.load(s)
    target = data_dir / "configured.sqlite3"
    cfg.set("database.path", str(target))
    cfg.save(s)
    s2 = load_settings()
    assert s2.db_path == target


def test_settings_is_frozen() -> None:
    import dataclasses

    s = Settings(config_dir=Path("/x"), data_dir=Path("/y"), db_path=Path("/z"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.db_path = Path("/")  # type: ignore[misc]
