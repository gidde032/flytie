"""Phase 4 — PDF export tests.

Uses pdfminer.six to extract text from rendered PDFs (snapshot via content
assertions, not byte-for-byte diff — PDF byte output isn't deterministic across
WeasyPrint releases).

If WeasyPrint isn't installed the tests are skipped so the core test suite
still passes without the `pdf` extra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Skip the entire module when WeasyPrint can't be loaded — either because the
# Python package isn't installed (`flytie` without the `pdf` extra) OR because
# its native deps (Pango/Cairo) are missing on this system (common on macOS
# without `brew install pango`). `pytest.importorskip` only catches ImportError;
# native-library failures throw OSError, so we wrap manually.
try:
    import jinja2  # noqa: F401
    import weasyprint  # noqa: F401
except (ImportError, OSError) as _pdf_err:
    pytest.skip(
        f"PDF tests skipped — WeasyPrint not loadable: {_pdf_err}",
        allow_module_level=True,
    )
pdfminer_extract = pytest.importorskip("pdfminer.high_level").extract_text

from flytie.core import patterns as patterns_repo  # noqa: E402
from flytie.core.dto import MaterialLineDTO, PatternInput  # noqa: E402
from flytie.pdf import (  # noqa: E402
    PDFTemplateError,
    default_filename,
    render_pattern_html,
    render_pattern_pdf,
)


def _seed_adams(session) -> None:  # type: ignore[no-untyped-def]
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Parachute Adams",
            hook_size="14",
            difficulty=3,
            instructions="Tie in tail. Wrap dubbing. Post + hackle.",
            notes="Catskill classic.",
            tags=["dryfly", "classic"],
            species=["rainbow trout", "brown trout"],
            materials=[
                MaterialLineDTO(canonical_name="grizzly hackle", category="hackle", quantity=1, unit="feather"),
                MaterialLineDTO(canonical_name="grey dubbing", category="dubbing", quantity=1, unit="pinch"),
                MaterialLineDTO(canonical_name="calf body hair", category="wing", quantity=1, unit="clump"),
            ],
        ),
    )


def test_render_html_contains_pattern_name(session) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    html = render_pattern_html(dto)
    assert "Parachute Adams" in html
    assert "grizzly hackle" in html
    assert "Catskill classic" in html
    # Header structure
    assert "<h1" in html
    assert "Materials" in html
    # Default CSS got inlined
    assert "@page" in html


def test_render_html_escapes_special_chars(session) -> None:  # type: ignore[no-untyped-def]
    """Material names with HTML special characters must be escaped."""
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="<script>alert(1)</script>",
            hook_size="14",
            materials=[
                MaterialLineDTO(canonical_name="bead <head>", category="bead", quantity=1)
            ],
        ),
    )
    p = patterns_repo.get_pattern(session, "<script>alert(1)</script>")
    dto = patterns_repo.to_dto(p)
    html = render_pattern_html(dto)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "bead &lt;head&gt;" in html


def test_render_pdf_to_disk(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    out = tmp_path / "adams.pdf"
    written = render_pattern_pdf(dto, out)
    assert written == out.resolve()
    assert written.exists()
    assert written.stat().st_size > 1000  # not an empty/dummy file
    # Snapshot via text extraction: every key field should appear in the PDF.
    text = pdfminer_extract(str(written))
    assert "Parachute Adams" in text
    assert "grizzly hackle" in text
    assert "grey dubbing" in text
    assert "calf body hair" in text
    assert "Catskill classic" in text
    # Difficulty + version surface
    assert "Difficulty" in text
    assert "v1" in text


def test_render_pdf_pattern_without_difficulty(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Difficulty-None must not produce a half-empty Difficulty: row."""
    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Zebra Midge",
            hook_size="20",
            materials=[MaterialLineDTO(canonical_name="black thread", category="thread", quantity=1)],
        ),
    )
    p = patterns_repo.get_pattern(session, "Zebra Midge")
    dto = patterns_repo.to_dto(p)
    out = tmp_path / "zebra.pdf"
    render_pattern_pdf(dto, out)
    text = pdfminer_extract(str(out))
    assert "Zebra Midge" in text
    assert "Difficulty" not in text  # block hidden when None


def test_render_pdf_empty_materials(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Pattern with no materials renders the empty-state hint, not a crash."""
    patterns_repo.create_pattern(
        session,
        PatternInput(name="Bare", hook_size="14"),
    )
    p = patterns_repo.get_pattern(session, "Bare")
    dto = patterns_repo.to_dto(p)
    out = tmp_path / "bare.pdf"
    render_pattern_pdf(dto, out)
    text = pdfminer_extract(str(out))
    assert "Bare" in text
    assert "no materials recorded" in text


def test_custom_template_overrides_default(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    template = tmp_path / "custom.html"
    template.write_text(
        "<!DOCTYPE html><html><body>"
        "<style>{{ stylesheet|safe }}</style>"
        "CUSTOM-MARKER {{ pattern.name }} v{{ version.version_number }}"
        "</body></html>"
    )
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    html = render_pattern_html(dto, template_path=template)
    assert "CUSTOM-MARKER Parachute Adams v1" in html


def test_custom_css_overrides_default(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    css = tmp_path / "custom.css"
    css.write_text("body { background: rebeccapurple; } /* SENTINEL-CSS */")
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    html = render_pattern_html(dto, css_path=css)
    assert "SENTINEL-CSS" in html
    assert "rebeccapurple" in html


def test_missing_template_raises_typed_error(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    with pytest.raises(PDFTemplateError) as exc:
        render_pattern_html(dto, template_path=tmp_path / "nope.html")
    assert "not found" in str(exc.value).lower()


def test_missing_photo_raises_typed_error(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    with pytest.raises(PDFTemplateError):
        render_pattern_html(dto, photo_path=tmp_path / "nope.jpg")


def test_non_image_photo_rejected(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    bad = tmp_path / "fake.txt"
    bad.write_text("not an image")
    with pytest.raises(PDFTemplateError) as exc:
        render_pattern_html(dto, photo_path=bad)
    assert "image" in str(exc.value).lower()


def test_default_filename_is_safe() -> None:
    from datetime import datetime

    from flytie.core.dto import PatternDTO, PatternVersionDTO

    v = PatternVersionDTO(version_number=3, hook_size="14", created_at=datetime.now())
    dto = PatternDTO(
        id=1, name="Adams / Catskill (#14)", created_at=datetime.now(), updated_at=datetime.now(), current_version=v
    )
    name = default_filename(dto)
    # No slashes, no parens, no hashes — safe for any filesystem.
    for ch in "/\\():#":
        assert ch not in name
    assert name.endswith(".pdf")
    assert "v3" in name


def test_html_embeds_photo_as_data_uri(session, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _seed_adams(session)
    # Smallest valid PNG (1x1 transparent).
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
    )
    img = tmp_path / "tiny.png"
    img.write_bytes(png)
    p = patterns_repo.get_pattern(session, "Parachute Adams")
    dto = patterns_repo.to_dto(p)
    html = render_pattern_html(dto, photo_path=img)
    assert "data:image/png;base64," in html
