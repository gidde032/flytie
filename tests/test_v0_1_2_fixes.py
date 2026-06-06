"""Regression tests for the v0.1.2 batch of CI / quality hardening fixes.

Each test pins a specific v0.1.2 change so a future contributor can't
silently regress the contract:

- Batch 3.1 — `@pytest.mark.smoke` happy-path subset exists and contains
  exactly the spec's five tests (init, add+list, view, shop, export-db
  round-trip).
- Batch 3.2 — `flytie --version` cold-start stays under the 600 ms
  budget the spec promises in NFR §4. Guards against someone
  re-introducing an eager top-level import of weasyprint, anthropic, or
  another heavy dependency.
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


# ---------------------------------------------------------------------------
# Batch 3.2 — Cold-start benchmark (spec NFR §4's 600 ms budget)
# ---------------------------------------------------------------------------


def test_cli_cold_start_under_budget() -> None:
    """`flytie --version` best-of-5 must finish in under 600 ms.

    Spec NFR §4 promises: "CLI startup under 600 ms (best-of-5
    `flytie --version` invocations)." The original 0.1.0 spec said 300 ms,
    but on real CI hardware that target was tight enough to flake. v0.1.2
    raised the budget to 600 ms with the understanding that the gate's
    purpose is to catch *regressions* in the import surface, not to chase
    the last 100 ms.

    The test runs `python -m flytie --version` five times, takes the best
    (fastest) wall-clock, and asserts that best is under 0.6 s. Best-of-5
    is the right statistic: it measures the tool's own startup once the
    OS filesystem cache is warm (a one-time cost the CLI does not
    control), so the number reflects what users experience on their
    second-and-onward invocation in a given shell session.

    If this test fails, the most likely cause is a new top-level import
    of a heavy dependency. Common culprits the codebase explicitly keeps
    lazy:

      - `weasyprint` (only imported inside the export command)
      - `anthropic` (only imported inside the suggest command)
      - `alembic` (lazy-imported inside `db.upgrade_to_head` /
        `db.stamp_alembic_head`)

    Adding any of those at module top level would push the best-of-5
    well past the budget. Run `python -X importtime -m flytie --version
    2>importtimes.log` and look at the longest lines for the offender.
    """
    import time

    project_root = _project_root()
    timings: list[float] = []
    for _ in range(5):
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "flytie", "--version"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        elapsed = time.perf_counter() - start
        assert result.returncode == 0, (
            f"`python -m flytie --version` exited {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        timings.append(elapsed)

    best = min(timings)
    # 0.6 s budget. The first run typically pays the OS filesystem-cache
    # cost (~1-2 s on a cold sandbox), which is why we take best-of-5
    # rather than median or worst.
    assert best < 0.6, (
        f"Cold-start (best of 5) was {best:.3f}s — over the 0.6s budget "
        f"in spec NFR §4. Full timings: {[f'{t:.3f}s' for t in timings]}. "
        "Most likely a heavy dependency (weasyprint, anthropic, alembic) "
        "is being imported at module top level. Diagnose with: "
        "`python -X importtime -m flytie --version 2>importtimes.log` "
        "and look for the slowest imports."
    )
