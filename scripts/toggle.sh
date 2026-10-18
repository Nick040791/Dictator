#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${HOME}/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    exec "${SCRIPT_DIR}/stop.sh"
else
    exec "${SCRIPT_DIR}/start.sh"
fi
