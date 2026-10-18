#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/home/mrnicholas/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    exec /home/mrnicholas/Dev/Dictator/scripts/stop.sh
else
    exec /home/mrnicholas/Dev/Dictator/scripts/start.sh
fi
