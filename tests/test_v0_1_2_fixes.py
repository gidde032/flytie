"""Regression tests for the v0.1.2 batch of CI / quality hardening fixes.

Each test pins a specific v0.1.2 change so a future contributor can't
silently regress the contract:

- Batch 3.1 — `@pytest.mark.smoke` happy-path subset exists and contains
  exactly the spec's five tests (init, add+list, view, shop, export-db
  round-trip).

Future v0.1.2 batches (cold-start benchmark, etc.) will add tests here
following the same naming convention.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Batch 3.1 — Smoke-marker pass (spec §7's five-test happy-path suite)
# ---------------------------------------------------------------------------


def test_smoke_marker_collects_exactly_five_happy_path_tests() -> None:
    """`pytest -m smoke` must collect exactly the spec's five happy-path tests.

    Spec §7 promises: "A `pytest -m smoke` marker exists for a five-test
    happy-path suite intended for quick local feedback." Before v0.1.2 the
    marker was registered in `pyproject.toml` but carried by zero tests, so
    `pytest -m smoke` collected nothing. v0.1.2 Batch 3.1 attached the
    marker to five carefully-chosen tests:

      - init success                     (test_db.py)
      - add + list round-trip            (test_cli_commands.py)
      - view renders a pattern           (test_cli_commands.py)
      - shop dedupes across patterns     (test_cli_phase3.py)
      - export-db → import-db round-trip (test_portability.py)

    This regression test fails if a future change adds the marker to more
    than five tests (the suite no longer fits the "quick local feedback"
    promise) or drops it from any (the suite loses coverage of one of the
    five happy-path operations). The exact-five contract matters: it's
    what the spec promises, and it's what the pre-push hook in
    `.pre-commit-config.yaml` relies on if a contributor wants to gate
    only on smoke.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-m",
            "smoke",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "cache_dir=/tmp/.pytest_cache",
        ],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"smoke collection failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    # pytest's collect-only summary line varies by version but always
    # contains a digit followed by "tests collected" or "selected". Look
    # for `N/M tests collected` or `N tests collected` and pull N out.
    match = re.search(r"(\d+)\s*(?:/\d+)?\s*(?:tests?|selected)\s+collected", result.stdout)
    assert match is not None, (
        f"couldn't parse collection summary from pytest output:\n{result.stdout}"
    )
    collected = int(match.group(1))
    assert collected == 5, (
        f"Expected exactly 5 smoke tests; pytest -m smoke collected {collected}. "
        f"Full output:\n{result.stdout}"
    )


def test_smoke_suite_runs_under_five_seconds() -> None:
    """The smoke suite is supposed to be quick local feedback — pin a budget.

    The spec frames smoke as "intended for quick local feedback." Five
    seconds is a generous upper bound (the current suite finishes in ~3s
    on the dev sandbox); the budget mostly guards against someone
    accidentally tagging a slow test (PDF rendering, AI streaming, a
    full-suite round-trip) with `@pytest.mark.smoke`.
    """
    import time

    start = time.perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "smoke",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "cache_dir=/tmp/.pytest_cache",
        ],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, (
        f"smoke run failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # 5 seconds is the budget. Subprocess overhead + pytest startup eats
    # ~1s of that on a slow machine, so the actual test wall-clock has to
    # stay well under 4s for the budget to hold.
    assert elapsed < 5.0, (
        f"Smoke suite took {elapsed:.2f}s — over the 5s "
        f'"quick local feedback" budget. '
        f"Either a slow test was tagged @pytest.mark.smoke or the existing "
        f"smoke tests have grown. Output:\n{result.stdout}"
    )
