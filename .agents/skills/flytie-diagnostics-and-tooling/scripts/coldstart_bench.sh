#!/usr/bin/env bash
# coldstart_bench.sh — Best-of-5 cold-start benchmark for `flytie --version`.
#
# Mirrors the spec's NFR §4 method: best of 5 runs, budget 600 ms.
# Uses Python for timing so the script is portable across macOS (where
# `date +%s%N` is not available) and Linux (where it is).
#
# Usage:
#   ./coldstart_bench.sh [--budget-ms N]
#
# --budget-ms N   Override the pass/fail budget (default: 600).
#                 Useful for tightening the budget on known-fast machines.
#
# Note on sandbox results: the dev Cowork sandbox typically sees best-of-5
# around 250 ms.  Contributor machines with cold filesystem caches will
# be slower; the 600 ms budget is sized for real contributor hardware
# post-warm-up (second-and-onward invocation in a shell session).

set -euo pipefail

BUDGET_MS=600

for arg in "$@"; do
    case "$arg" in
        --budget-ms)
            shift
            BUDGET_MS="${1:-600}"
            ;;
        --budget-ms=*)
            BUDGET_MS="${arg#*=}"
            ;;
        *)
            echo "Unknown flag: $arg"
            echo "Usage: $0 [--budget-ms N]"
            exit 1
            ;;
    esac
done

# ── Locate repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

cd "$REPO_ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${BOLD}=== flytie cold-start benchmark (best-of-5, budget ${BUDGET_MS} ms) ===${RESET}"
echo "  repo: $REPO_ROOT"
echo

# Python one-liner: time one `python -m flytie --version` run and print ms.
TIME_PYTHON=$(cat <<'PYEOF'
import subprocess, sys, time
start = time.perf_counter()
r = subprocess.run([sys.executable, "-m", "flytie", "--version"],
                   capture_output=True, text=True, timeout=10)
elapsed_ms = (time.perf_counter() - start) * 1000
if r.returncode != 0:
    print(f"ERROR: exit {r.returncode}\nstdout: {r.stdout}\nstderr: {r.stderr}", file=sys.stderr)
    sys.exit(1)
print(f"{elapsed_ms:.1f}")
PYEOF
)

BEST_MS=99999
RUN=1

while [ $RUN -le 5 ]; do
    MS=$(python3 -c "$TIME_PYTHON" 2>&1) || {
        echo "  run $RUN: ERROR — $MS"
        exit 1
    }
    echo "  run $RUN: ${MS} ms"
    # Compare floats via python (bash can't do floating point natively)
    IS_LOWER=$(python3 -c "print(1 if float('$MS') < float('$BEST_MS') else 0)")
    if [ "$IS_LOWER" = "1" ]; then
        BEST_MS="$MS"
    fi
    RUN=$((RUN + 1))
done

echo
echo "  Best of 5: ${BEST_MS} ms"

PASS=$(python3 -c "print(1 if float('${BEST_MS}') < float('${BUDGET_MS}') else 0)")
if [ "$PASS" = "1" ]; then
    echo -e "  ${GREEN}PASS${RESET} — under ${BUDGET_MS} ms budget"
    exit 0
else
    echo -e "  ${RED}FAIL${RESET} — ${BEST_MS} ms exceeds ${BUDGET_MS} ms budget"
    echo
    echo "Diagnose with:"
    echo "  python -X importtime -m flytie --version 2>importtimes.log"
    echo "  python3 -c \""
    echo "    import re, pathlib"
    echo "    lines = pathlib.Path('importtimes.log').read_text().splitlines()"
    echo "    pairs = [(int(m.group(1)), l) for l in lines if (m := re.search(r'cumulative (\d+)', l))]"
    echo "    for ms, l in sorted(pairs, reverse=True)[:10]: print(ms, l[-80:])"
    echo "  \""
    exit 1
fi
