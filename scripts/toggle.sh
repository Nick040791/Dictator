#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${HOME}/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

running=0
if systemctl --user is-active --quiet dictator 2>/dev/null; then
    running=1
elif [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
        running=1
    fi
elif pgrep -f "${HOME}/dictator-env/bin/python.*dictator.py" >/dev/null 2>&1; then
    running=1
fi

if [[ "$running" -eq 1 ]]; then
    exec "${SCRIPT_DIR}/stop.sh"
else
    exec "${SCRIPT_DIR}/start.sh"
fi
