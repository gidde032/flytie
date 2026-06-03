"""CLI integration tests for `flytie suggest`.

The Anthropic call is replaced by monkeypatching `flytie.ai.anthropic_streamer`
with a fake that replays a canned JSON response — no network, no real key.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie.cli import app

_SAMPLE_JSON = (
    '[{"name": "Parachute Adams", "hook_size": "14", '
    '"key_materials": ["grizzly hackle"], '
    '"rationale": "Reliable fall mayfly imitation."}, '
    '{"name": "October Caddis", "hook_size": "10", '
    '"key_materials": ["orange dubbing", "elk hair"], '
    '"rationale": "Matches the big fall caddis hatch."}]'
)


def _fake_streamer_factory(chunks: list[str]):
    """Mimic `anthropic_streamer`: takes (api_key, model=...) -> Streamer."""

    def _factory(api_key: str, model: str = "x") -> object:
        def _stream(system: str, user: str) -> Iterator[str]:
            yield from chunks

        return _stream

    return _factory


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def _add_adams(runner: CliRunner) -> None:
    r = runner.invoke(
        app,
        [
            "add",
            "Parachute Adams",
            "--hook",
            "14",
            "-s",
            "rainbow trout",
            "-m",
            "grizzly hackle,hackle,1,feather",
        ],
    )
    assert r.exit_code == 0, r.stdout


def test_suggest_happy_path(env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("flytie.ai.anthropic_streamer", _fake_streamer_factory([_SAMPLE_JSON]))
    runner = CliRunner()
    _init(runner)
    _add_adams(runner)
    r = runner.invoke(app, ["suggest", "--species", "rainbow trout", "--season", "late October"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "Parachute Adams" in r.stdout
    assert "October Caddis" in r.stdout
    # The library pattern is tagged; the novel one gets [NEW].
    assert "in library" in r.stdout
    assert "NEW" in r.stdout


def test_suggest_missing_api_key_friendly_error(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["suggest", "--species", "trout", "--season", "fall"])
    assert r.exit_code == 2
    out = r.stdout + r.stderr
    assert "ANTHROPIC_API_KEY" in out
    assert "Traceback" not in out


def test_suggest_requires_species_and_season(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["suggest", "--species", "trout"])
    assert r.exit_code == 2  # missing --season


def test_suggest_passes_water_and_conditions(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    def _factory(api_key: str, model: str = "x") -> object:
        def _stream(system: str, user: str) -> Iterator[str]:
            seen["user"] = user
            yield _SAMPLE_JSON

        return _stream

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("flytie.ai.anthropic_streamer", _factory)
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(
        app,
        [
            "suggest",
            "--species",
            "brown trout",
            "--season",
            "fall",
            "--water",
            "Henry's Fork",
            "--conditions",
            "low and clear",
        ],
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "Henry's Fork" in seen["user"]
    assert "low and clear" in seen["user"]


def test_suggest_handles_unparseable_response(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(
        "flytie.ai.anthropic_streamer",
        _fake_streamer_factory(["the model produced only prose, no JSON"]),
    )
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["suggest", "--species", "trout", "--season", "fall"])
    assert r.exit_code == 0
    # Falls back to showing the raw text.
    assert "only prose" in r.stdout


def test_suggest_surfaces_streamer_error(
    env_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from flytie.ai.suggest import AIError

    def _factory(api_key: str, model: str = "x") -> object:
        def _stream(system: str, user: str) -> Iterator[str]:
            raise AIError("Could not reach the Anthropic API — check your network.")
            yield  # pragma: no cover

        return _stream

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("flytie.ai.anthropic_streamer", _factory)
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["suggest", "--species", "trout", "--season", "fall"])
    assert r.exit_code == 2
    out = r.stdout + r.stderr
    assert "Could not reach" in out
    assert "Traceback" not in out
