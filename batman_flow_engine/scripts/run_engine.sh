#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMEOUT=600

cd "$REPO_ROOT"

if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

$PYTHON_BIN runner.py "$@" &
ENGINE_PID=$!

# Watchdog: kill engine if exceeds timeout
(
    sleep $TIMEOUT
    if kill -0 $ENGINE_PID 2>/dev/null; then
        echo "⚠️  Engine timeout after ${TIMEOUT}s. Killing PID $ENGINE_PID"
        kill -TERM $ENGINE_PID 2>/dev/null
        sleep 5
        kill -KILL $ENGINE_PID 2>/dev/null
    fi
) &
WATCHDOG_PID=$!

# Wait for engine to finish (or be killed)
set +e
wait $ENGINE_PID
EXIT_CODE=$?
set -e

# Clean up watchdog
kill $WATCHDOG_PID 2>/dev/null || true
wait $WATCHDOG_PID 2>/dev/null || true

exit $EXIT_CODE
