"""Phase 4 — CLI integration tests for `flytie export`."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import jinja2  # noqa: F401
    import weasyprint  # noqa: F401
except (ImportError, OSError) as _pdf_err:
    pytest.skip(
        f"PDF CLI tests skipped — WeasyPrint not loadable: {_pdf_err}",
        allow_module_level=True,
    )
pdfminer_extract = pytest.importorskip("pdfminer.high_level").extract_text

from typer.testing import CliRunner  # noqa: E402

from flytie.cli import app  # noqa: E402


def _init_and_add(runner: CliRunner) -> None:
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0
    r = runner.invoke(
        app,
        ["add", "Parachute Adams", "--hook", "14", "-t", "dryfly",
         "-m", "grizzly hackle,hackle,1,feather",
         "-m", "grey dubbing,dubbing,1,pinch",
         "--notes", "Catskill classic."],
    )
    assert r.exit_code == 0


def test_export_writes_pdf_to_default_location(env_dirs: tuple[Path, Path], tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _init_and_add(runner)
    r = runner.invoke(app, ["export", "Parachute Adams"])
    assert r.exit_code == 0, r.stdout + r.stderr
    out_files = list(tmp_path.glob("*.pdf"))
    assert len(out_files) == 1
    assert "Parachute_Adams" in out_files[0].name
    text = pdfminer_extract(str(out_files[0]))
    assert "Parachute Adams" in text
    assert "grizzly hackle" in text


def test_export_writes_to_explicit_path(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init_and_add(runner)
    out = tmp_path / "adams.pdf"
    r = runner.invoke(app, ["export", "Parachute Adams", "--out", str(out)])
    assert r.exit_code == 0
    assert out.exists()


def test_export_writes_into_directory(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init_and_add(runner)
    target_dir = tmp_path / "cards"
    target_dir.mkdir()
    r = runner.invoke(app, ["export", "Parachute Adams", "--out", str(target_dir) + "/"])
    assert r.exit_code == 0
    pdfs = list(target_dir.glob("*.pdf"))
    assert len(pdfs) == 1


def test_export_html_only_to_stdout(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    _init_and_add(runner)
    r = runner.invoke(app, ["export", "Parachute Adams", "--html"])
    assert r.exit_code == 0
    assert "<html" in r.stdout
    assert "Parachute Adams" in r.stdout


def test_export_unknown_pattern(env_dirs: tuple[Path, Path]) -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["init"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["export", "Nope"])
    assert r.exit_code == 1
    assert "No pattern" in (r.stdout + r.stderr)


def test_export_missing_template_friendly_error(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init_and_add(runner)
    r = runner.invoke(
        app,
        ["export", "Parachute Adams", "--template", str(tmp_path / "nope.html")],
    )
    assert r.exit_code == 2
    assert "not found" in (r.stdout + r.stderr).lower()


def test_export_with_custom_template(env_dirs: tuple[Path, Path], tmp_path: Path) -> None:
    runner = CliRunner()
    _init_and_add(runner)
    tmpl = tmp_path / "t.html"
    tmpl.write_text("<html><body>MY-CUSTOM-MARKER {{ pattern.name }}</body></html>")
    out = tmp_path / "x.pdf"
    r = runner.invoke(
        app,
        ["export", "Parachute Adams", "--template", str(tmpl), "--out", str(out)],
    )
    assert r.exit_code == 0
    text = pdfminer_extract(str(out))
    assert "MY-CUSTOM-MARKER" in text
