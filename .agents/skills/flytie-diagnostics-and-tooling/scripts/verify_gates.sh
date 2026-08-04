#!/usr/bin/env bash
# verify_gates.sh — Run the full flytie quality gate ladder in order.
#
# Usage:
#   ./verify_gates.sh [--narrow] [--sandbox]
#
# --narrow   Force COLUMNS=80 for pytest (mirrors CI / pre-push hook behaviour).
# --sandbox  Apply sandbox cache-redirect flags (-p no:cacheprovider
#            -o cache_dir=/tmp/.pytest_cache for pytest;
#            --cache-dir /tmp/.mypy_cache for mypy).
#            Auto-detected when the repo path contains /sessions/.
#
# Exits non-zero with a FAIL summary after the first failing gate.
# (Fail-fast: it makes no sense to run pytest if ruff format fails.)
#
# Gate order (mirrors spec NFR §4 and CI workflow):
#   1. ruff format --check
#   2. ruff check
#   3. mypy
#   4. pytest --cov (85% floor enforced by pyproject.toml fail_under)
#   5. pytest -m smoke

set -euo pipefail

NARROW=false
SANDBOX=false
COLUMNS_VAL=""

for arg in "$@"; do
    case "$arg" in
        --narrow)  NARROW=true ;;
        --sandbox) SANDBOX=true ;;
        *)
            echo "Unknown flag: $arg"
            echo "Usage: $0 [--narrow] [--sandbox]"
            exit 1
            ;;
    esac
done

# ── Locate repo root ──────────────────────────────────────────────────────────
# Script lives at .claude/skills/flytie-diagnostics-and-tooling/scripts/
# Four directory levels above repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

cd "$REPO_ROOT"

# Auto-detect sandbox if the resolved repo root is under /sessions/
if [[ "$REPO_ROOT" == /sessions/* ]]; then
    SANDBOX=true
fi

# ── Build argument lists ──────────────────────────────────────────────────────
PYTEST_CACHE_FLAGS=()
MYPY_CACHE_FLAGS=()
COVERAGE_FILE_VAR=""

if $SANDBOX; then
    PYTEST_CACHE_FLAGS=(-p no:cacheprovider -o cache_dir=/tmp/.pytest_cache)
    MYPY_CACHE_FLAGS=(--cache-dir /tmp/.mypy_cache)
    # The sandbox mounts the repo read-only for some files; .coverage in the
    # repo root may be permission-denied.  Redirect to /tmp to avoid the error.
    COVERAGE_FILE_VAR="/tmp/.coverage_flytie"
fi

if $NARROW; then
    COLUMNS_VAL="80"
else
    COLUMNS_VAL="200"
fi

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

pass() { echo -e "${GREEN}✔ PASS${RESET}  $1"; }
fail() { echo -e "${RED}✘ FAIL${RESET}  $1"; }

echo -e "${BOLD}=== flytie gate ladder — repo: $REPO_ROOT ===${RESET}"
echo "  sandbox=$SANDBOX  narrow=$NARROW  COLUMNS=$COLUMNS_VAL"
echo

# ── Gate 1: ruff format --check ───────────────────────────────────────────────
echo -e "${BOLD}[1/5] ruff format --check${RESET}"
if ruff format --check src tests 2>&1; then
    pass "ruff format --check"
else
    fail "ruff format --check"
    echo
    echo "Fix: run  ruff format src tests"
    exit 1
fi
echo

# ── Gate 2: ruff check ────────────────────────────────────────────────────────
echo -e "${BOLD}[2/5] ruff check${RESET}"
if ruff check src tests 2>&1; then
    pass "ruff check"
else
    fail "ruff check"
    echo
    echo "Fix: run  ruff check --fix src tests  (then fix residuals manually)"
    exit 1
fi
echo

# ── Gate 3: mypy ──────────────────────────────────────────────────────────────
echo -e "${BOLD}[3/5] mypy src${RESET}"
if mypy "${MYPY_CACHE_FLAGS[@]}" src 2>&1; then
    pass "mypy"
else
    fail "mypy"
    echo
    echo "Fix: address type errors reported above."
    exit 1
fi
echo

# ── Gate 4: pytest --cov (85% floor) ─────────────────────────────────────────
echo -e "${BOLD}[4/5] pytest --cov (85% floor)${RESET}"
if COLUMNS="$COLUMNS_VAL" COVERAGE_FILE="${COVERAGE_FILE_VAR:-}" pytest "${PYTEST_CACHE_FLAGS[@]}" \
    --cov=src/flytie --cov-report=term-missing 2>&1; then
    pass "pytest --cov"
else
    fail "pytest --cov"
    echo
    echo "If coverage dropped: add tests or check the omit-list in pyproject.toml."
    echo "If tests failed: see output above."
    exit 1
fi
echo

# ── Gate 5: pytest -m smoke ───────────────────────────────────────────────────
echo -e "${BOLD}[5/5] pytest -m smoke${RESET}"
if COLUMNS="$COLUMNS_VAL" pytest "${PYTEST_CACHE_FLAGS[@]}" -m smoke -v 2>&1; then
    pass "pytest -m smoke"
else
    fail "pytest -m smoke"
    echo
    echo "Smoke suite failure: one of the five happy-path tests broke."
    exit 1
fi
echo

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}=== SUMMARY ===${RESET}"
echo -e "${GREEN}All 5 gates PASSED.${RESET}"
echo "  ruff format --check  ✔"
echo "  ruff check           ✔"
echo "  mypy                 ✔"
echo "  pytest --cov         ✔"
echo "  pytest -m smoke      ✔"
