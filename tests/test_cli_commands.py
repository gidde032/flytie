"""Integration tests for Phase 2 CLI commands.

These exercise full command paths against a temp SQLite DB via the `env_dirs`
fixture, so they double as a smoke suite for the wire-up between Typer,
`flytie.core.patterns`, and the rendering layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from flytie.cli import app


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


def test_add_and_list_round_trip(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(
        app,
        [
            "add", "Parachute Adams",
            "--hook", "14",
            "--tag", "dryfly",
            "--tag", "classic",
            "--species", "rainbow trout",
            "--material", "grizzly hackle,hackle,1,feather",
            "--material", "grey dubbing,dubbing,1,pinch",
            "--notes", "Catskill classic.",
        ],
    )
    assert r.exit_code == 0, r.stdout
    assert "Added Parachute Adams" in r.stdout

    r = runner.invoke(app, ["list"])
    assert r.exit_code == 0
    assert "Parachute Adams" in r.stdout
    assert "dryfly" in r.stdout
    assert "rainbow trout" in r.stdout


def test_view_renders_pattern(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        [
            "add", "RS2",
            "--hook", "20",
            "--material", "grey thread,thread,1,spool",
            "--instructions", "Tie in CDC wing post; wrap tight.",
            "--notes", "Great for Henry's Fork.",
        ],
    )
    r = runner.invoke(app, ["view", "RS2"])
    assert r.exit_code == 0
    assert "RS2" in r.stdout
    assert "grey thread" in r.stdout
    # The instructions/notes panels appear too.
    assert "CDC wing post" in r.stdout
    assert "Henry's Fork" in r.stdout


def test_view_missing_pattern(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["view", "Nope"])
    assert r.exit_code == 1
    assert "No pattern named 'Nope'" in (r.stdout + r.stderr)


def test_search_matches_name_and_material(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle"])
    runner.invoke(app, ["add", "Pheasant Tail", "--hook", "16", "--material", "pheasant tail,tail"])
    r = runner.invoke(app, ["search", "grizzly"])
    assert r.exit_code == 0
    assert "Adams" in r.stdout
    assert "Pheasant Tail" not in r.stdout

    r = runner.invoke(app, ["search", "pheasant"])
    assert r.exit_code == 0
    assert "Pheasant Tail" in r.stdout


def test_search_no_results(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle"])
    r = runner.invoke(app, ["search", "zzz-nope"])
    assert r.exit_code == 0
    assert "No patterns match" in r.stdout


def test_edit_bumps_version_and_can_change_notes(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle"])
    r = runner.invoke(app, ["edit", "Adams", "--notes", "tweaked"])
    assert r.exit_code == 0
    assert "→ v2" in r.stdout
    r = runner.invoke(app, ["view", "Adams"])
    assert "tweaked" in r.stdout


def test_edit_clear_tags(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        ["add", "Adams", "--hook", "14", "--tag", "dryfly", "--material", "hackle,hackle"],
    )
    r = runner.invoke(app, ["edit", "Adams", "--clear-tags"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    # Tags should now be empty (rendered as '—').
    lines = [line for line in r.stdout.splitlines() if "Adams" in line]
    assert lines
    assert "dryfly" not in lines[0]


def test_edit_preserves_materials_when_unspecified(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle,1,feather"],
    )
    runner.invoke(app, ["edit", "Adams", "--notes", "minor tweak"])
    r = runner.invoke(app, ["view", "Adams"])
    assert "grizzly hackle" in r.stdout
    assert "minor tweak" in r.stdout


def test_edit_clear_materials(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        ["add", "Adams", "--hook", "14", "--material", "grizzly hackle,hackle"],
    )
    runner.invoke(app, ["edit", "Adams", "--clear-materials"])
    r = runner.invoke(app, ["view", "Adams"])
    assert "grizzly hackle" not in r.stdout


def test_delete_soft_then_hides_from_list(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["delete", "Adams", "--yes"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    assert "Adams" not in r.stdout
    r = runner.invoke(app, ["list", "--include-deleted"])
    assert "Adams" in r.stdout


def test_delete_hard_removes(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["delete", "Adams", "--hard", "--yes"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["view", "Adams"])
    assert r.exit_code == 1


def test_delete_without_yes_refuses_in_non_tty(env_dirs: tuple[Path, Path]) -> None:
    """In non-TTY contexts (tests, CI, piped shells), `delete` without `--yes`
    must refuse rather than silently destroy data — the regression test for the
    Phase 2 review finding about ambiguous exit codes."""
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["delete", "Adams"])
    assert r.exit_code == 2
    r = runner.invoke(app, ["list"])
    assert "Adams" in r.stdout


def test_tag_add_and_remove(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["tag", "add", "Adams", "catskill", "classic"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    assert "catskill" in r.stdout
    r = runner.invoke(app, ["tag", "remove", "Adams", "classic"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["list"])
    assert "classic" not in r.stdout
    assert "catskill" in r.stdout


def test_add_from_json_file(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init(runner)
    payload = {
        "name": "Zebra Midge",
        "hook_size": "20",
        "notes": "Tailwater staple.",
        "tags": ["nymph", "midge"],
        "species": ["rainbow trout"],
        "materials": [
            {"canonical_name": "black thread", "category": "thread", "quantity": 1, "unit": "spool"},
            {"canonical_name": "silver wire", "category": "flash", "quantity": 0.5, "unit": "foot"},
        ],
    }
    f = tmp_path / "zebra.json"
    f.write_text(json.dumps(payload))
    # The CLI requires hook + name positional but we override from-file.
    r = runner.invoke(app, ["add", "Zebra Midge", "--hook", "20", "--from-file", str(f)])
    assert r.exit_code == 0, r.stdout
    r = runner.invoke(app, ["view", "Zebra Midge"])
    assert "silver wire" in r.stdout
    assert "Tailwater staple" in r.stdout


def test_add_duplicate_errors(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "--material", "hackle,hackle"])
    r = runner.invoke(app, ["add", "adams", "--hook", "12", "--material", "hackle,hackle"])
    assert r.exit_code == 1
    assert "already exists" in (r.stdout + r.stderr)


def test_add_invalid_material_spec(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(
        app,
        ["add", "X", "--hook", "14", "--material", "name,cat,not-a-number,spool"],
    )
    assert r.exit_code == 2
    assert "non-numeric" in (r.stdout + r.stderr)


def test_list_with_tag_and_species_filters(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(
        app,
        [
            "add", "Adams",
            "--hook", "14",
            "--tag", "dryfly",
            "--species", "rainbow trout",
            "--material", "hackle,hackle",
        ],
    )
    runner.invoke(
        app,
        [
            "add", "Pheasant Tail",
            "--hook", "16",
            "--tag", "nymph",
            "--species", "brown trout",
            "--material", "pheasant tail,tail",
        ],
    )
    r = runner.invoke(app, ["list", "--tag", "nymph"])
    assert "Pheasant Tail" in r.stdout
    assert "Adams" not in r.stdout
    r = runner.invoke(app, ["list", "--species", "rainbow trout"])
    assert "Adams" in r.stdout
    assert "Pheasant Tail" not in r.stdout
