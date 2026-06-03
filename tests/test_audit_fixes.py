"""Tests for the spec-drift-audit fixes (config command, hook-size filter,
category validation, batch export).

Each test names the audit recommendation it pins.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flytie.cli import app
from flytie.core import patterns as patterns_repo
from flytie.core.dto import MaterialLineDTO, PatternInput


def _init(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0, r.stdout


# --- Audit fix 1: flytie config (FR-8) ---------------------------------------


def test_config_path_prints_config_file(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    # Wide terminal so Rich/Click doesn't wrap the printed path mid-string.
    # On a narrow CI terminal, `config.toml` would otherwise split as
    # `config.tom\nl`, breaking the substring assertion.
    r = runner.invoke(app, ["config", "path"], env={"COLUMNS": "200"})
    assert r.exit_code == 0
    # Also normalize whitespace in case any wrapping still slips through;
    # we only care that the filename is present, not where line breaks fall.
    assert "config.toml" in "".join(r.stdout.split())


def test_config_set_then_get_round_trip(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["config", "set", "pdf.template", "fancy"])
    assert r.exit_code == 0
    assert "Set" in r.stdout
    r = runner.invoke(app, ["config", "get", "pdf.template"])
    assert r.exit_code == 0
    assert "fancy" in r.stdout


def test_config_set_persists_to_disk(env_dirs: tuple[Path, Path]) -> None:
    config_dir, _ = env_dirs
    runner = CliRunner()
    runner.invoke(app, ["config", "set", "database.path", "/tmp/custom.sqlite3"])
    assert (config_dir / "config.toml").exists()
    text = (config_dir / "config.toml").read_text()
    assert "custom.sqlite3" in text


def test_config_show_lists_set_keys(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    runner.invoke(app, ["config", "set", "pdf.template", "fancy"])
    r = runner.invoke(app, ["config", "show"])
    assert r.exit_code == 0
    assert "pdf.template" in r.stdout
    assert "fancy" in r.stdout


def test_config_show_empty(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["config", "show"])
    assert r.exit_code == 0
    assert "No settings configured" in r.stdout


def test_config_get_unknown_key_errors(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["config", "get", "bogus.key"])
    assert r.exit_code == 2
    assert "Unknown config key" in (r.stdout + r.stderr)


def test_config_set_unknown_key_errors(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["config", "set", "bogus.key", "x"])
    assert r.exit_code == 2


def test_config_has_no_api_key_setting(env_dirs: tuple[Path, Path]) -> None:
    """The API key is env-only and must never be a config-managed key."""
    runner = CliRunner()
    r = runner.invoke(app, ["config", "set", "api.key", "secret"])
    assert r.exit_code == 2  # rejected as unknown key


# --- Audit fix 2: list --hook-size (FR-3) ------------------------------------


def test_list_hook_size_exact_match(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-m", "hackle,hackle"])
    runner.invoke(app, ["add", "RS2", "--hook", "20", "-m", "thread,thread"])
    r = runner.invoke(app, ["list", "--hook-size", "14"])
    assert r.exit_code == 0
    assert "Adams" in r.stdout
    assert "RS2" not in r.stdout


def test_list_hook_size_range_match(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-m", "hackle,hackle"])
    runner.invoke(app, ["add", "Midge", "--hook", "22", "-m", "thread,thread"])
    r = runner.invoke(app, ["list", "--hook-size", "12-16"])
    assert "Adams" in r.stdout
    assert "Midge" not in r.stdout


def test_list_hook_size_matches_stored_range(env_dirs: tuple[Path, Path]) -> None:
    """A pattern whose hook is stored as a range '12-16' matches a query of 14."""
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Variant", "--hook", "12-16", "-m", "hackle,hackle"])
    r = runner.invoke(app, ["list", "--hook-size", "14"])
    assert "Variant" in r.stdout


def test_hook_size_tokens_helper() -> None:
    from flytie.core.patterns import hook_size_tokens

    assert hook_size_tokens("14") == {14}
    assert hook_size_tokens("12-16") == {12, 13, 14, 15, 16}
    assert hook_size_tokens("14, 16") == {14, 16}
    assert hook_size_tokens("streamer") == set()


# --- Audit fix 3: category validation (Section 5) ----------------------------


def test_invalid_category_rejected(session) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="Unknown material category"):
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name="Bad",
                hook_size="14",
                materials=[MaterialLineDTO(canonical_name="x", category="banana")],
            ),
        )


def test_valid_categories_accepted(session) -> None:  # type: ignore[no-untyped-def]
    # Includes the three superset additions: bead, weight, adhesive.
    for cat in ("thread", "hackle", "bead", "weight", "adhesive", "other"):
        patterns_repo.create_pattern(
            session,
            PatternInput(
                name=f"P-{cat}",
                hook_size="14",
                materials=[MaterialLineDTO(canonical_name=f"m-{cat}", category=cat)],
            ),
        )


def test_invalid_category_rejected_via_cli(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["add", "X", "--hook", "14", "-m", "thing,banana"])
    assert r.exit_code == 2
    assert "Unknown material category" in (r.stdout + r.stderr)


# --- Audit fix 4: batch export --tag (FR-5) ----------------------------------

_weasy = None
try:
    import weasyprint  # noqa: F401

    _weasy = True
except (ImportError, OSError):
    _weasy = False

pdf_required = pytest.mark.skipif(not _weasy, reason="WeasyPrint not loadable")


def test_export_requires_a_selector(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["export"])
    assert r.exit_code == 2
    assert "Specify a pattern name" in (r.stdout + r.stderr)


def test_export_rejects_multiple_selectors(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-m", "hackle,hackle", "-t", "dryfly"])
    r = runner.invoke(app, ["export", "Adams", "--tag", "dryfly"])
    assert r.exit_code == 2
    assert "only one of" in (r.stdout + r.stderr).lower()


def test_export_batch_rejects_html(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["export", "--tag", "dryfly", "--html"])
    assert r.exit_code == 2


@pdf_required
def test_export_batch_by_tag(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init(runner)
    runner.invoke(app, ["add", "Adams", "--hook", "14", "-m", "hackle,hackle", "-t", "dryfly"])
    runner.invoke(app, ["add", "Wulff", "--hook", "12", "-m", "hackle,hackle", "-t", "dryfly"])
    runner.invoke(app, ["add", "RS2", "--hook", "20", "-m", "thread,thread", "-t", "nymph"])
    out = tmp_path / "cards"
    r = runner.invoke(app, ["export", "--tag", "dryfly", "--out", str(out)])
    assert r.exit_code == 0, r.stdout + r.stderr
    pdfs = sorted(p.name for p in out.glob("*.pdf"))
    assert len(pdfs) == 2  # Adams + Wulff, not RS2
    assert "Wrote 2 cards" in r.stdout


def test_export_batch_empty_selector(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init(runner)
    r = runner.invoke(app, ["export", "--tag", "no-such-tag", "--out", str(tmp_path)])
    assert r.exit_code == 0
    assert "No patterns match" in r.stdout
