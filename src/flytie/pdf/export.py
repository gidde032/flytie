"""WeasyPrint-driven pattern card rendering.

Renders a `PatternDTO` to either HTML or PDF using a Jinja2 template plus a
CSS stylesheet. Templates and CSS are bundled with the package; users can
override either with --template / --css.

Heavy dependencies (WeasyPrint, Jinja2) are imported lazily so the core CLI
runs without the `pdf` extra installed.
"""

from __future__ import annotations

import base64
import mimetypes
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from flytie import __version__ as FLYTIE_VERSION
from flytie.core.dto import PatternDTO

if TYPE_CHECKING:  # pragma: no cover
    pass


class PDFDependencyError(RuntimeError):
    """Raised when the optional `pdf` extra is not installed."""


class PDFTemplateError(RuntimeError):
    """Raised when a user-supplied template or CSS path cannot be loaded."""


_NATIVE_DEP_HINT = (
    "WeasyPrint installed, but its native libraries (Pango, Cairo, ...) "
    "are missing on this system.\n"
    "  macOS:   brew install pango\n"
    "  Linux:   apt install libpango-1.0-0 libpangoft2-1.0-0 (Debian/Ubuntu) "
    "or dnf install pango (Fedora/RHEL)\n"
    "  Windows: see https://doc.courtbouillon.org/weasyprint/stable/first_steps.html\n"
    "Or render to HTML instead with `flytie export <name> --html` — this works without WeasyPrint.\n"
)


def _require_jinja2() -> object:
    """Import Jinja2; needed for both HTML and PDF rendering."""
    try:
        import jinja2
    except ImportError as exc:  # pragma: no cover
        raise PDFDependencyError(
            "Pattern export needs the optional 'pdf' extra. "
            "Install with: pip install 'flytie[pdf]'"
        ) from exc
    return jinja2


def _require_weasyprint() -> object:
    """Import WeasyPrint; only needed for PDF rendering."""
    try:
        import weasyprint
    except ImportError as exc:  # pragma: no cover
        raise PDFDependencyError(
            "PDF export needs the optional 'pdf' extra. "
            "Install with: pip install 'flytie[pdf]'"
        ) from exc
    except OSError as exc:  # pragma: no cover
        raise PDFDependencyError(_NATIVE_DEP_HINT + f"Original error: {exc}") from exc
    return weasyprint


def _require_deps() -> tuple[object, object]:
    """Back-compat wrapper: import both Jinja2 and WeasyPrint."""
    return _require_jinja2(), _require_weasyprint()


def _read_bundled(filename: str) -> str:
    """Read a bundled resource (template or stylesheet) as text."""
    return resources.files("flytie.templates").joinpath(filename).read_text(encoding="utf-8")


def _read_user_path(path: Path, kind: str) -> str:
    p = path.expanduser().resolve()
    if not p.exists():
        raise PDFTemplateError(f"{kind.capitalize()} not found: {p}")
    if not p.is_file():
        raise PDFTemplateError(f"{kind.capitalize()} is not a file: {p}")
    return p.read_text(encoding="utf-8")


def _photo_data_uri(photo_path: Path | None) -> str | None:
    if photo_path is None:
        return None
    p = photo_path.expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise PDFTemplateError(f"Photo not found: {p}")
    mime, _ = mimetypes.guess_type(p.name)
    if mime is None or not mime.startswith("image/"):
        raise PDFTemplateError(
            f"Photo {p} doesn't look like an image (mime={mime!r})."
        )
    encoded = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_pattern_html(
    pattern: PatternDTO,
    *,
    template_path: Path | None = None,
    css_path: Path | None = None,
    photo_path: Path | None = None,
) -> str:
    """Render a pattern DTO to a self-contained HTML string.

    Useful as a fallback when WeasyPrint isn't installed: the styled HTML can
    be opened in any browser and printed from there.
    """
    if pattern.current_version is None:
        raise PDFTemplateError(
            f"Pattern {pattern.name!r} has no current version to render."
        )
    jinja2 = _require_jinja2()
    Environment = jinja2.Environment  # type: ignore[attr-defined]
    select_autoescape = jinja2.select_autoescape  # type: ignore[attr-defined]

    if template_path is not None:
        template_source = _read_user_path(template_path, "template")
    else:
        template_source = _read_bundled("pattern_card.html")
    if css_path is not None:
        stylesheet = _read_user_path(css_path, "stylesheet")
    else:
        stylesheet = _read_bundled("pattern_card.css")

    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    template = env.from_string(template_source)
    rendered = template.render(
        pattern=pattern,
        version=pattern.current_version,
        stylesheet=stylesheet,
        photo_data_uri=_photo_data_uri(photo_path),
        flytie_version=FLYTIE_VERSION,
    )
    # `template` is lazy-imported, so Jinja2's `render()` is typed `Any`;
    # coerce explicitly to satisfy the declared `-> str` return.
    return str(rendered)


def render_pattern_pdf(
    pattern: PatternDTO,
    out_path: Path,
    *,
    template_path: Path | None = None,
    css_path: Path | None = None,
    photo_path: Path | None = None,
) -> Path:
    """Render a pattern DTO to a PDF at `out_path`. Returns the written path."""
    weasyprint = _require_weasyprint()
    html_string = render_pattern_html(
        pattern,
        template_path=template_path,
        css_path=css_path,
        photo_path=photo_path,
    )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML = weasyprint.HTML  # type: ignore[attr-defined]
    HTML(string=html_string).write_pdf(str(out))
    return out


def default_filename(pattern: PatternDTO) -> str:
    """Filesystem-safe filename for a pattern PDF."""
    safe = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in pattern.name)
    safe = "_".join(safe.split())
    v = pattern.current_version
    return f"{safe or 'pattern'}_v{v.version_number}.pdf" if v else f"{safe or 'pattern'}.pdf"
