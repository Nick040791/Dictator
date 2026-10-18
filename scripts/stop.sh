#!/usr/bin/env bash
# stop.sh — stop the Dictator service
set -euo pipefail

RUNTIME_DIR="${HOME}/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"

stopped=0

# Stop the systemd user service if it exists / is active or failed.
if systemctl --user is-active --quiet dictator 2>/dev/null || systemctl --user is-failed --quiet dictator 2>/dev/null; then
    systemctl --user stop dictator 2>/dev/null || true
    systemctl --user reset-failed dictator 2>/dev/null || true
    stopped=1
    echo "Stopped Dictator service."
fi

# Legacy PID file.
if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        # give it a moment
        for _ in $(seq 1 20); do
            kill -0 "$PID" 2>/dev/null || break
            sleep 0.1
        done
        kill -9 "$PID" 2>/dev/null || true
        stopped=1
        echo "Stopped Dictator (PID $PID)."
    fi
    rm -f "$PID_FILE"
fi

# Fallback for processes started outside the wrappers.
if pgrep -f "${HOME}/dictator-env/bin/python.*dictator.py" >/dev/null 2>&1; then
    pkill -f "${HOME}/dictator-env/bin/python.*dictator.py" 2>/dev/null || true
    stopped=1
    echo "Stopped remaining Dictator process(es)."
fi

if [[ "$stopped" -eq 0 ]]; then
    echo "Dictator is not running."
fi
