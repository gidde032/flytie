"""User configuration: paths and settings.

Resolves the local DB path and reads/writes a TOML config in the user's
platform-appropriate config directory.

Environment variables take precedence:
- FLYTIE_DB_PATH overrides the database path.
- FLYTIE_CONFIG_DIR overrides the config directory (useful for tests).
- ANTHROPIC_API_KEY supplies the Claude API key (read at use-time, never stored).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - py310 path
    import tomli as tomllib

import tomli_w

APP_NAME = "flytie"


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings."""

    config_dir: Path
    data_dir: Path
    db_path: Path
    pdf_template: str = "default"
    pdf_output_dir: Path | None = None

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"


def _resolve_config_dir() -> Path:
    env = os.environ.get("FLYTIE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path(user_config_dir(APP_NAME))


def _resolve_data_dir() -> Path:
    env = os.environ.get("FLYTIE_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path(user_data_dir(APP_NAME))


def _resolve_db_path(data_dir: Path, config_db_path: str | None) -> Path:
    env = os.environ.get("FLYTIE_DB_PATH")
    if env:
        return Path(env).expanduser()
    if config_db_path:
        return Path(config_db_path).expanduser()
    return data_dir / "flytie.sqlite3"


class ConfigError(RuntimeError):
    """Raised when the on-disk config file cannot be parsed."""


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"flytie config at {path} is not valid TOML: {exc}. Edit or delete the file."
        ) from exc
    if not isinstance(data, dict):
        return {}
    return data


def load_settings() -> Settings:
    """Load settings, applying env > file > defaults precedence."""
    config_dir = _resolve_config_dir()
    data_dir = _resolve_data_dir()
    data: dict[str, Any] = {}
    config_file = config_dir / "config.toml"
    if config_file.exists():
        data = _read_config_file(config_file)
    db_section = data.get("database", {}) if isinstance(data, dict) else {}
    pdf_section = data.get("pdf", {}) if isinstance(data, dict) else {}
    db_path = _resolve_db_path(
        data_dir, db_section.get("path") if isinstance(db_section, dict) else None
    )
    pdf_template = "default"
    pdf_output_dir: Path | None = None
    if isinstance(pdf_section, dict):
        pdf_template = str(pdf_section.get("template", "default"))
        out = pdf_section.get("output_dir")
        if out:
            pdf_output_dir = Path(str(out)).expanduser()
    return Settings(
        config_dir=config_dir,
        data_dir=data_dir,
        db_path=db_path,
        pdf_template=pdf_template,
        pdf_output_dir=pdf_output_dir,
    )


@dataclass
class ConfigFile:
    """In-memory representation of the config file."""

    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, settings: Settings) -> ConfigFile:
        if not settings.config_file.exists():
            return cls(data={})
        return cls(data=_read_config_file(settings.config_file))

    def save(self, settings: Settings) -> None:
        """Write atomically (tmp + os.replace) so a crash never corrupts config."""
        settings.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = settings.config_file.with_suffix(settings.config_file.suffix + ".tmp")
        with tmp.open("wb") as fh:
            tomli_w.dump(self.data, fh)
        os.replace(tmp, settings.config_file)

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        cur: dict[str, Any] = self.data
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value

    def get(self, dotted_key: str, default: Any = None) -> Any:
        parts = dotted_key.split(".")
        cur: Any = self.data
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur
