"""Shared pytest fixtures for flytie tests.

Every test gets an isolated SQLite database in a temp directory, plus a
preconfigured `Database` instance whose settings point at that path.
Environment variables are scoped so tests cannot accidentally read or
write the user's real flytie data.

CLI test infrastructure (v0.1.2)
================================

`_wide_cli_runner_env` is an `autouse=True` fixture that patches
``CliRunner.invoke`` for the duration of every test so that every invocation
defaults to ``env={"COLUMNS": "200"}``. This eliminates the class of bug
documented in ``ai-development-practices.md`` §4: Rich/Typer output wraps at
~80 columns on CI's narrow default fake terminal, and substring assertions
like ``assert "JSON parse error" in r.stdout`` break when Rich inserts a
newline between "JSON" and "parse error". Forcing a wide terminal removes
the wrap, and a user-supplied ``env`` argument still wins (so a test that
deliberately wants narrow-terminal behavior can pass
``env={"COLUMNS": "80"}`` and the override propagates). The patch is scoped
to the test via ``monkeypatch.setattr``, so library code outside the test
session sees the unmodified ``CliRunner``.

`cli_runner` is a regular fixture that simply yields a fresh ``CliRunner()``
for tests that prefer the explicit-injection style. Functionally identical
to constructing ``CliRunner()`` inline (thanks to the autouse patch above);
offered as a clearer affordance and a documentation hook for new tests:

    def test_my_command(cli_runner):
        result = cli_runner.invoke(app, ["my-command"])
        assert result.exit_code == 0

Existing tests that do ``runner = CliRunner()`` inline are equally safe and
don't need to migrate.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flytie.config import Settings, load_settings
from flytie.db import Database

# --- Terminal hermeticity (v0.2.2) ------------------------------------------
# Typer's rich help module and Rich itself read several environment variables
# AT IMPORT TIME as module-level constants (TERMINAL_WIDTH, FORCE_COLOR,
# PY_COLORS, GITHUB_ACTIONS; Rich 14 adds TTY_COMPATIBLE/TTY_INTERACTIVE) and
# latch them before any pytest fixture can run. A shell exporting any of them
# gets ANSI codes inside CliRunner-captured output and help rendered at a
# forced width that ignores COLUMNS — four tests failed on a real contributor
# machine this way while CI stayed green. Neutralize them HERE, at module
# top-level, after conftest's own imports (flytie.config/db don't import
# typer or create Rich consoles) but before any test module imports
# flytie.cli — which is what latches these values. A fixture would be too
# late. (Popping
# GITHUB_ACTIONS only affects this pytest process — it makes CI rendering
# behave identically to local instead of secretly forced-terminal.)
for _var in (
    "TERMINAL_WIDTH",
    "FORCE_COLOR",
    "PY_COLORS",
    "GITHUB_ACTIONS",
    "CLICOLOR",
    "CLICOLOR_FORCE",
    "COLORTERM",
    "TTY_COMPATIBLE",
    "TTY_INTERACTIVE",
    "NO_COLOR",
):
    os.environ.pop(_var, None)


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


@pytest.fixture(autouse=True)
def _wide_cli_runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every `CliRunner.invoke` call to a wide fake terminal.

    Rich/Typer wraps output at ~80 columns by default in `CliRunner`. CI
    runners often default narrower than local terminals, so substring
    assertions on CLI output (`assert "X" in r.stdout`) can pass locally
    and fail in Actions when a phrase lands at the wrap point. Defaulting
    every invocation to `COLUMNS=200` removes the entire class. Tests that
    want to assert *against* narrow-terminal behavior can pass
    `env={"COLUMNS": "80"}` (or any other value) explicitly — the
    user-supplied env wins. See `ai-development-practices.md` §4.

    Narrow-terminal stress gate: if `FLYTIE_TEST_COLUMNS` is set in the
    outer environment, it replaces the 200 default. This is how the
    pre-push hook and the CI stress leg (`FLYTIE_TEST_COLUMNS=80 pytest`)
    actually exercise narrow-terminal wrapping — a plain outer `COLUMNS=80`
    cannot, because this fixture's default would override it for every
    invocation (v0.2.2 review finding: the old `COLUMNS=80` gates were
    silent no-ops). Per-test explicit `env` still wins over both.
    """
    original_invoke = CliRunner.invoke
    default_columns = os.environ.get("FLYTIE_TEST_COLUMNS", "200")

    def wide_invoke(
        self: CliRunner,
        *args: Any,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged = {"COLUMNS": default_columns}
        if env:
            merged.update(env)
        return original_invoke(self, *args, env=merged, **kwargs)

    monkeypatch.setattr(CliRunner, "invoke", wide_invoke)


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip `ANTHROPIC_API_KEY` from the environment for every test.

    Guarantees structurally that a real key exported in a contributor's
    shell can never leak into a test run or change test behavior. Tests
    that need a key set one explicitly with `monkeypatch.setenv` (the
    test-body call runs after this fixture, so it wins).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def cli_runner() -> CliRunner:
    """A fresh CliRunner.

    Functionally identical to constructing `CliRunner()` directly — the
    `_wide_cli_runner_env` autouse fixture defaults every invocation to a
    wide terminal regardless of how the runner was constructed. Offered as
    a clearer affordance for new tests; existing tests don't need to
    migrate.
    """
    return CliRunner()
