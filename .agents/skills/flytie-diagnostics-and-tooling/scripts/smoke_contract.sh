#!/usr/bin/env bash
# smoke_contract.sh — Assert the smoke suite collects exactly 5 tests and runs in <5 s.
#
# Usage:
#   ./smoke_contract.sh [--sandbox]
#
# --sandbox  Apply sandbox cache-redirect flags.
#            Auto-detected when the repo path contains /sessions/.
#
# Exits 0 if:
#   (a) exactly 5 tests are marked @pytest.mark.smoke, AND
#   (b) those 5 tests complete in under 5 seconds.
#
# If you need to legitimately change the smoke set, you must ALSO update
# the exact-count regression in tests/test_v0_1_2_fixes.py —
# test_smoke_marker_collects_exactly_five_happy_path_tests().
# Never silently loosen that test; the count is a spec contract.

set -euo pipefail

SANDBOX=false

for arg in "$@"; do
    case "$arg" in
        --sandbox) SANDBOX=true ;;
        *)
            echo "Unknown flag: $arg"
            echo "Usage: $0 [--sandbox]"
            exit 1
            ;;
    esac
done

# ── Locate repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

cd "$REPO_ROOT"

if [[ "$REPO_ROOT" == /sessions/* ]]; then
    SANDBOX=true
fi

PYTEST_CACHE_FLAGS=()
if $SANDBOX; then
    PYTEST_CACHE_FLAGS=(-p no:cacheprovider -o cache_dir=/tmp/.pytest_cache)
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${BOLD}=== flytie smoke-contract check ===${RESET}"
echo "  repo: $REPO_ROOT  sandbox=$SANDBOX"
echo

# ── Step 1: Collect smoke tests ───────────────────────────────────────────────
echo -e "${BOLD}[1/2] Collecting @pytest.mark.smoke tests${RESET}"
COLLECT_OUT=$(COLUMNS=200 pytest "${PYTEST_CACHE_FLAGS[@]}" \
    --collect-only -m smoke -q 2>&1) || {
    echo -e "${RED}Collection failed:${RESET}"
    echo "$COLLECT_OUT"
    exit 1
}

echo "$COLLECT_OUT"
echo

# Count and print the collected test IDs (lines ending in ::test_something)
TEST_IDS=$(echo "$COLLECT_OUT" | grep -E '::test_' | sed 's/^[[:space:]]*//' || true)
COUNT=$(echo "$TEST_IDS" | grep -c '::test_' || echo 0)

echo "  Collected $COUNT smoke test(s)."
echo

if [ "$COUNT" -ne 5 ]; then
    echo -e "${RED}FAIL${RESET} — expected exactly 5 smoke tests; collected $COUNT."
    echo
    echo "If you intentionally changed the smoke set, update:"
    echo "  tests/test_v0_1_2_fixes.py :: test_smoke_marker_collects_exactly_five_happy_path_tests"
    echo "(Never loosen the assertion silently — that test is a spec contract.)"
    exit 1
fi

echo -e "${GREEN}✔ PASS${RESET}  exactly 5 smoke tests collected. Golden inventory:"
echo "$TEST_IDS" | while IFS= read -r line; do
    echo "    $line"
done
echo

# ── Step 2: Run smoke suite and measure wall-clock ────────────────────────────
echo -e "${BOLD}[2/2] Running smoke suite (budget: 5 s)${RESET}"

RUN_OUTPUT=$(python3 -c "
import subprocess, sys, time, os

cache_flags = []
if '$SANDBOX' == 'true':
    cache_flags = ['-p', 'no:cacheprovider', '-o', 'cache_dir=/tmp/.pytest_cache']

env = os.environ.copy()
env['COLUMNS'] = '200'

start = time.perf_counter()
r = subprocess.run(
    [sys.executable, '-m', 'pytest', '-m', 'smoke', '-v'] + cache_flags,
    capture_output=True, text=True, timeout=60, env=env,
    cwd='$REPO_ROOT'
)
elapsed = time.perf_counter() - start
print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
print(f'ELAPSED_SECONDS={elapsed:.2f}')
sys.exit(r.returncode)
" 2>&1) || {
    EXIT_CODE=$?
    echo "$RUN_OUTPUT"
    echo
    echo -e "${RED}FAIL${RESET} — smoke suite exited non-zero (exit $EXIT_CODE)."
    exit 1
}

echo "$RUN_OUTPUT"
ELAPSED=$(echo "$RUN_OUTPUT" | grep ELAPSED_SECONDS | sed 's/ELAPSED_SECONDS=//')

PASS=$(python3 -c "print(1 if float('${ELAPSED:-99}') < 5.0 else 0)" 2>/dev/null || echo 0)

echo
if [ "$PASS" = "1" ]; then
    echo -e "${GREEN}✔ PASS${RESET}  smoke suite completed in ${ELAPSED}s (budget: 5s)."
else
    echo -e "${RED}FAIL${RESET}  smoke suite took ${ELAPSED}s — over the 5s budget."
    echo "Check whether a slow test (PDF, AI, full round-trip) was accidentally"
    echo "tagged @pytest.mark.smoke."
    exit 1
fi
echo

echo -e "${BOLD}=== SUMMARY ===${RESET}"
echo -e "${GREEN}Smoke contract: PASS${RESET}"
echo "  Exactly 5 tests collected  ✔"
echo "  Suite completed in ${ELAPSED}s  ✔"
