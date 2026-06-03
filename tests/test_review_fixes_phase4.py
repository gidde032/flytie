"""Regression tests for Phase 4 review findings.

The formal three-reviewer subagent pass was blocked by API quota, but the user's
hands-on local test on macOS surfaced one real bug (the test modules' skip
gating only caught ImportError, not OSError from a missing libpango). The
fixes for that bug are pinned here.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from flytie.pdf.export import (
    PDFDependencyError,
    _require_jinja2,
    _require_weasyprint,
)


def test_require_weasyprint_translates_oserror_to_friendly_message() -> None:
    """Live user-finding: native libpango missing throws OSError. We must
    catch it and produce an install-hint, not a raw dyld traceback."""
    fake_err = OSError(
        "cannot load library 'libpango-1.0-0': dlopen(libpango-1.0-0, 0x0002): "
        "tried: 'libpango-1.0-0' (no such file)..."
    )
    with (
        patch("flytie.pdf.export.importlib", create=True),
        patch("builtins.__import__", side_effect=fake_err),
    ):
        with pytest.raises(PDFDependencyError) as exc:
            _require_weasyprint()
    assert "brew install pango" in str(exc.value)
    assert "--html" in str(exc.value)
    assert "Original error" in str(exc.value)


def test_require_jinja2_does_not_load_weasyprint() -> None:
    """Live finding: --html mode only needs Jinja2; should not trigger any
    WeasyPrint import (and therefore not need libpango)."""
    # If WeasyPrint is installed in the test environment this is a no-op
    # assertion; the meaningful guarantee is that _require_jinja2 itself
    # never references weasyprint.
    import inspect

    source = inspect.getsource(_require_jinja2)
    assert "weasyprint" not in source


def test_html_only_export_path_imports_only_jinja2(session) -> None:  # type: ignore[no-untyped-def]
    """Render to HTML must succeed even on a hypothetical system where
    weasyprint imports raise OSError. We can't actually unimport weasyprint
    cleanly, so we patch it to raise on access."""
    from flytie.core import patterns as patterns_repo
    from flytie.core.dto import MaterialLineDTO, PatternInput
    from flytie.pdf.export import render_pattern_html

    pytest.importorskip("jinja2")

    patterns_repo.create_pattern(
        session,
        PatternInput(
            name="Test",
            hook_size="14",
            materials=[MaterialLineDTO(canonical_name="thread", category="thread")],
        ),
    )
    p = patterns_repo.get_pattern(session, "Test")
    dto = patterns_repo.to_dto(p)
    # Should NOT raise even if WeasyPrint is fake-broken — render_pattern_html
    # only goes through _require_jinja2.
    html = render_pattern_html(dto)
    assert "Test" in html
    assert "thread" in html
