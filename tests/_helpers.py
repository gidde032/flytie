"""Shared test helpers for flytie.

Module-level helpers used by multiple test files. Fixtures live in
`conftest.py`; reusable pure functions and tiny utilities live here.
"""

from __future__ import annotations

from typer.testing import CliRunner

from flytie.cli import app


def cli_help(command: list[str], runner: CliRunner | None = None) -> str:
    """Run ``flytie <command> --help`` and return its stdout, whitespace-normalized.

    Useful for asserting on `--help` content without worrying about line wraps:

        out = cli_help(["add"])
        assert "name,category,quantity,unit" in out
        assert "12-16" in out

    The wide-terminal default that the `_wide_cli_runner_env` fixture in
    `tests/conftest.py` injects into every `CliRunner.invoke` call usually
    eliminates wrapping by itself. The whitespace normalization here is a
    belt-and-suspenders backstop for cells that Rich wraps even at 200
    columns (e.g., a very long help cell or a help line whose markup forces
    a line break). See `ai-development-practices.md` §4 for the lesson.
    """
    r = runner or CliRunner()
    result = r.invoke(app, [*command, "--help"])
    assert result.exit_code == 0, result.stdout + result.stderr
    return " ".join(result.stdout.split())
