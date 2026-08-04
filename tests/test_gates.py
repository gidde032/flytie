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
