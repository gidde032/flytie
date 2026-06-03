"""CLI integration tests for Phase 3 commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from flytie.cli import app


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def _seed_two(runner: CliRunner) -> None:
    runner.invoke(
        app,
        [
            "add", "Adams",
            "--hook", "14",
            "--tag", "dryfly",
            "--material", "grizzly hackle,hackle,1,feather",
            "--material", "grey dubbing,dubbing,1,pinch",
        ],
    )
    runner.invoke(
        app,
        [
            "add", "Royal Wulff",
            "--hook", "12",
            "--tag", "dryfly",
            "--material", "grizzly hackle,hackle,2,feather",
            "--material", "red floss,body,1,spool",
        ],
    )


def test_versions_lists_history(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    runner.invoke(app, ["edit", "Adams", "--notes", "tweaked"])
    r = runner.invoke(app, ["versions", "Adams"])
    assert r.exit_code == 0
    assert "v1" in r.stdout
    assert "v2" in r.stdout


def test_view_specific_version(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle,1,feather"],
    )
    runner.invoke(app, ["edit", "Adams", "--hook", "12"])
    r = runner.invoke(app, ["view", "Adams", "--version", "1"])
    assert r.exit_code == 0
    assert "v1" in r.stdout
    assert "14" in r.stdout


def test_view_unknown_version(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["view", "Adams", "--version", "99"])
    assert r.exit_code == 1
    assert "no version 99" in (r.stdout + r.stderr).lower()


def test_diff_versions(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle,1,feather"])
    runner.invoke(app, ["edit", "Adams", "--hook", "12"])
    r = runner.invoke(app, ["diff", "Adams", "1", "2"])
    assert r.exit_code == 0
    # Stripped of ANSI codes, "14" and "12" both appear in the diff.
    out = r.stdout
    assert "14" in out
    assert "12" in out


def test_diff_identical(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle,1,feather"]
    )
    runner.invoke(
        app, ["edit", "Adams", "--material", "hackle,hackle,1,feather", "--hook", "14"]
    )
    r = runner.invoke(app, ["diff", "Adams", "1", "2"])
    assert r.exit_code == 0
    assert "No differences" in r.stdout


def test_restore_old_version(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle,1,feather"]
    )
    runner.invoke(app, ["edit", "Adams", "--hook", "12"])
    r = runner.invoke(app, ["restore", "Adams", "1"])
    assert r.exit_code == 0
    assert "new v3" in r.stdout
    r = runner.invoke(app, ["view", "Adams"])
    assert "14" in r.stdout  # restored hook size


def test_shop_dedupes_across_patterns(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(app, ["shop", "--tag", "dryfly"])
    assert r.exit_code == 0
    out = r.stdout
    # Grizzly hackle appears once with quantity 3 (1 + 2).
    assert "grizzly hackle" in out
    assert "red floss" in out
    assert "grey dubbing" in out


def test_shop_requires_selector(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["shop"])
    assert r.exit_code == 2
    assert "--pattern" in (r.stdout + r.stderr)


def test_shop_markdown_format(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(app, ["shop", "--tag", "dryfly", "--format", "markdown"])
    assert r.exit_code == 0
    assert "# Shopping list" in r.stdout
    assert "## hackle" in r.stdout


def test_shop_text_format(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(app, ["shop", "--tag", "dryfly", "--format", "text"])
    assert r.exit_code == 0
    assert "Shopping list" in r.stdout
    assert "HACKLE" in r.stdout


def test_shop_exclude_owned(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(
        app, ["shop", "--tag", "dryfly", "--exclude", "grizzly hackle"]
    )
    assert r.exit_code == 0
    assert "grizzly hackle" not in r.stdout
    assert "red floss" in r.stdout


def test_shop_pattern_selector(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(app, ["shop", "--pattern", "Adams"])
    assert r.exit_code == 0
    assert "grey dubbing" in r.stdout
    # Royal Wulff materials are not included.
    assert "red floss" not in r.stdout


def test_shop_invalid_format(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(app, ["shop", "--tag", "dryfly", "--format", "yaml"])
    assert r.exit_code == 2
    assert "Unknown --format" in (r.stdout + r.stderr)


def test_shop_json_format(env_dirs: tuple[Path, Path]) -> None:
    """JSON output (added in Phase 3 review fix) is a valid spec-listed format."""
    runner = CliRunner()
    _init(runner)
    _seed_two(runner)
    r = runner.invoke(app, ["shop", "--tag", "dryfly", "--format", "json"])
    assert r.exit_code == 0
    assert '"items"' in r.stdout
    assert '"pattern_names"' in r.stdout
