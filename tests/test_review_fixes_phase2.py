"""Regression tests for bugs flagged in the Phase 2 review."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from flytie.cli import app


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def test_h_short_flag_is_help_not_hook(env_dirs: tuple[Path, Path]) -> None:
    """Reviewer B (MED): `-h` should not be hijacked for --hook."""
    runner = CliRunner()
    _init(runner)
    # Now `-h` is unbound (we set help_option_names=["--help"]) so it should
    # be treated as an unknown short flag for `add`.
    r = runner.invoke(app, ["add", "X", "-h", "14"])
    assert r.exit_code != 0


def test_add_requires_hook_when_no_file(env_dirs: tuple[Path, Path]) -> None:
    """Reviewer A (HIGH): --hook must be required when --from-file is absent,
    but optional (and overridable) when a file supplies it."""
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["add", "X"])
    assert r.exit_code == 2
    assert "--hook" in (r.stdout + r.stderr)


def test_add_from_file_uses_file_hook(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    """Reviewer A (HIGH): --from-file should provide hook_size without requiring --hook."""
    runner = CliRunner()
    _init(runner)
    f = tmp_path / "p.json"
    f.write_text(
        json.dumps(
            {
                "name": "RS2",
                "hook_size": "20",
                "materials": [{"canonical_name": "thread", "category": "thread"}],
            }
        )
    )
    r = runner.invoke(app, ["add", "RS2", "--from-file", str(f)])
    assert r.exit_code == 0, r.stdout + r.stderr
    r = runner.invoke(app, ["view", "RS2"])
    assert "20" in r.stdout


def test_add_cli_hook_overrides_file_when_explicit(
    env_dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    runner = CliRunner()
    _init(runner)
    f = tmp_path / "p.json"
    f.write_text(
        json.dumps(
            {
                "name": "RS2",
                "hook_size": "20",
                "materials": [{"canonical_name": "thread", "category": "thread"}],
            }
        )
    )
    r = runner.invoke(app, ["add", "RS2", "--from-file", str(f), "--hook", "18"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["view", "RS2"])
    assert "18" in r.stdout


def test_edit_from_file_layers_cli_overrides(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    """Reviewer A & B (HIGH): edit --from-file must let other CLI flags layer on top."""
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle,1,feather"],
    )
    f = tmp_path / "p.json"
    f.write_text(
        json.dumps(
            {
                "name": "Adams",
                "hook_size": "12",
                "notes": "from file",
                "materials": [{"canonical_name": "ginger hackle", "category": "hackle"}],
            }
        )
    )
    r = runner.invoke(
        app,
        ["edit", "Adams", "--from-file", str(f), "--notes", "overridden by CLI"],
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    r = runner.invoke(app, ["view", "Adams"])
    assert "overridden by CLI" in r.stdout
    assert "ginger hackle" in r.stdout


def test_edit_does_not_silently_rename_on_case_change(
    env_dirs: tuple[Path, Path],
) -> None:
    """Reviewer A (MED): `flytie edit adams --notes x` must not mutate the
    display name from 'Adams' to 'adams' — rename is opt-in via --rename-to."""
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["edit", "adams", "--notes", "tweaked"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    assert "Adams" in r.stdout
    assert "adams" not in r.stdout.replace("Adams", "")


def test_edit_rename_to_changes_display_name(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["edit", "Adams", "--rename-to", "Parachute Adams"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    assert "Parachute Adams" in r.stdout


def test_conflicting_tag_and_clear_tags_errors(env_dirs: tuple[Path, Path]) -> None:
    """Reviewer A (MED): `--tag x --clear-tags` must error, not silently let one win."""
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["edit", "Adams", "--tag", "dryfly", "--clear-tags"])
    assert r.exit_code == 2
    assert "Cannot combine" in (r.stdout + r.stderr)


def test_conflicting_material_and_clear_materials_errors(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(
        app,
        ["edit", "Adams", "--material", "hackle,hackle", "--clear-materials"],
    )
    assert r.exit_code == 2


def test_malformed_json_pattern_file_friendly_error(
    env_dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    """Reviewer A & B (MED): malformed JSON must not show a Python traceback."""
    runner = CliRunner()
    _init(runner)
    f = tmp_path / "broken.json"
    f.write_text("{not json")
    r = runner.invoke(app, ["add", "X", "--hook", "14", "--from-file", str(f)])
    assert r.exit_code == 2
    out = r.stdout + r.stderr
    assert "JSON parse error" in out
    assert "Traceback" not in out


def test_missing_pattern_file_friendly_error(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(
        app,
        ["add", "X", "--hook", "14", "--from-file", str(tmp_path / "missing.json")],
    )
    assert r.exit_code == 2
    assert "not found" in (r.stdout + r.stderr).lower()


def test_pydantic_validation_friendly_error(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    """Reviewer A (MED): bad field types should surface as a structured error,
    not a Pydantic ValidationError stacktrace."""
    runner = CliRunner()
    _init(runner)
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"name": "X", "hook_size": 14, "materials": [{"canonical_name": 1}]}))
    r = runner.invoke(app, ["add", "X", "--from-file", str(f)])
    assert r.exit_code == 2
    out = r.stdout + r.stderr
    assert "invalid" in out.lower()
    assert "Traceback" not in out


def test_unsupported_pattern_file_extension(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init(runner)
    f = tmp_path / "p.yaml"
    f.write_text("name: x")
    r = runner.invoke(app, ["add", "X", "--hook", "14", "--from-file", str(f)])
    assert r.exit_code == 2
    assert "Unsupported" in (r.stdout + r.stderr)


def test_tag_normalization_at_cli_boundary(env_dirs: tuple[Path, Path]) -> None:
    """Reviewer B (suggestion → test gap): tags are case-insensitive end-to-end."""
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    runner.invoke(app, ["tag", "add", "Adams", "DryFly"])
    r = runner.invoke(app, ["tag", "remove", "Adams", "dryfly"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    line = next(line for line in r.stdout.splitlines() if "Adams" in line)
    assert "dryfly" not in line.lower()


def test_search_excludes_soft_deleted(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    runner.invoke(app, ["delete", "Adams", "--yes"])
    r = runner.invoke(app, ["search", "adams"])
    assert "Adams" not in r.stdout
