"""Structural gates that catch drift in project conventions.

These are not feature tests — they assert invariants about the project
itself (file sizes, marker counts, config consistency) so a future
contributor can't silently break a contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.mark.smoke
def test_handoff_stays_within_its_budget() -> None:
    """handoff.md must not exceed 200 lines.

    The handoff file is the first thing every agent reads. If it balloons,
    sessions burn tokens re-reading stale history instead of doing useful
    work. The routing header at the top of the file explains what belongs
    here and where everything else goes.

    If this test fails, read the routing header, route the overflow to
    its correct destination, and delete the routed content from
    handoff.md.
    """
    handoff = _project_root() / "handoff.md"
    if not handoff.is_file():
        pytest.skip("handoff.md is gitignored and not present in CI")
    lines = handoff.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200, (
        f"handoff.md is {len(lines)} lines — over the 200-line budget. "
        f"Read the routing header at the top of the file and route "
        f"the overflow to its correct destination."
    )


def test_release_workflow_creates_github_release() -> None:
    """A pushed `v*` tag must produce a GitHub Release, not only a PyPI upload.

    Before this gate, release.yml published to PyPI only, and tags v0.1.1 to
    v0.2.3 had no GitHub Release until they were backfilled by hand. The
    workflow must check the CHANGELOG section in `build` (before the
    irreversible PyPI upload) and create the Release after `publish`.
    """
    text = (_project_root() / ".github" / "workflows" / "release.yml").read_text()
    build = text.index("\n  build:")
    publish = text.index("\n  publish:")
    release = text.index("\n  github-release:")
    preflight = text.index("Verify CHANGELOG has a section for this version")
    assert build < preflight < publish, "CHANGELOG check must run in build, before publish"
    assert publish < release
    job = text[release:]
    assert "needs: publish" in job
    assert "contents: write" in job
    assert "gh release create" in job and "--notes-file" in job


def test_changelog_has_a_section_for_the_package_version() -> None:
    """CHANGELOG.md must have a dated section for the current `__version__`.

    The release workflow builds the GitHub Release notes from this section.
    """
    import re

    from flytie import __version__

    text = (_project_root() / "CHANGELOG.md").read_text()
    pattern = rf"^## \[{re.escape(__version__)}\] — \d{{4}}-\d{{2}}-\d{{2}}$"
    assert re.search(pattern, text, re.MULTILINE), f"no dated CHANGELOG section for {__version__}"
