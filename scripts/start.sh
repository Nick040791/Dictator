#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/mrnicholas/Dev/Dictator"
VENV_PYTHON="/home/mrnicholas/dictator-env/bin/python"
RUNTIME_DIR="/home/mrnicholas/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"
LOG_FILE="$RUNTIME_DIR/dictator.log"

mkdir -p "$RUNTIME_DIR"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Dictator is already running (PID $(cat "$PID_FILE"))."
    exit 0
fi

cd "$PROJECT_DIR"
nohup "$VENV_PYTHON" -u dictator.py > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Started Dictator (PID $!)."
echo "Log: $LOG_FILE"
