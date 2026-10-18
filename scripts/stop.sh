#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/home/mrnicholas/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"

stopped=0
if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        stopped=1
        echo "Stopped Dictator (PID $PID)."
    fi
    rm -f "$PID_FILE"
fi

# Fallback for processes started outside this wrapper.
if pgrep -f "/home/mrnicholas/dictator-env/bin/python.*dictator.py" >/dev/null 2>&1; then
    pkill -f "/home/mrnicholas/dictator-env/bin/python.*dictator.py" 2>/dev/null || true
    stopped=1
    echo "Stopped remaining Dictator process(es)."
fi

if [[ "$stopped" -eq 0 ]]; then
    echo "Dictator is not running."
fi
