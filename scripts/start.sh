#!/usr/bin/env bash
# start.sh — start the Dictator service (no-op if already running)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${HOME}/dictator-env/bin/python"
RUNTIME_DIR="${HOME}/.local/share/dictator"
PID_FILE="$RUNTIME_DIR/dictator.pid"
LOG_FILE="$RUNTIME_DIR/dictator.log"

mkdir -p "$RUNTIME_DIR"

# Already running as a systemd user service?
if systemctl --user is-active --quiet dictator 2>/dev/null; then
    PID="$(systemctl --user show dictator -p MainPID --value 2>/dev/null || true)"
    [[ -n "${PID:-}" && "$PID" != "0" ]] && echo "$PID" > "$PID_FILE"
    echo "Dictator is already running (PID ${PID:-?})."
    exit 0
fi

# Legacy / externally started process?
if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Dictator is already running (PID $OLD_PID)."
        exit 0
    fi
    rm -f "$PID_FILE"
fi
# Fallback: any stray process?
if pgrep -f "${HOME}/dictator-env/bin/python.*dictator.py" >/dev/null 2>&1; then
    echo "Dictator is already running."
    exit 0
fi

# Clear a previously failed transient unit so we can reuse the name.
systemctl --user reset-failed dictator 2>/dev/null || true

# Launch as an independent systemd user service so it survives the launcher's
# (e.g. GNOME desktop) scope being torn down when the launching process exits.
if ! systemd-run --user --unit=dictator \
    --description="Dictator push-to-talk dictation service" \
    --working-directory="$PROJECT_DIR" \
    --property=StandardOutput=append:"$LOG_FILE" \
    --property=StandardError=append:"$LOG_FILE" \
    --collect \
    "$VENV_PYTHON" -u dictator.py >/dev/null 2>&1; then
    echo "Failed to start Dictator via systemd-run. Check log: $LOG_FILE" >&2
    journalctl --user -u dictator -n 20 --no-pager >&2 2>/dev/null || true
    exit 1
fi

# Wait briefly for the service to become active.
for _ in $(seq 1 50); do
    if systemctl --user is-active --quiet dictator 2>/dev/null; then
        break
    fi
    sleep 0.1
done

PID="$(systemctl --user show dictator -p MainPID --value 2>/dev/null || true)"
if [[ -n "${PID:-}" && "$PID" != "0" ]]; then
    echo "$PID" > "$PID_FILE"
fi

if systemctl --user is-active --quiet dictator 2>/dev/null; then
    echo "Started Dictator (PID ${PID:-?})."
    echo "Log: $LOG_FILE"
else
    echo "Failed to start Dictator. Check log: $LOG_FILE" >&2
    # Surface recent journal output for diagnosis.
    journalctl --user -u dictator -n 20 --no-pager >&2 2>/dev/null || true
    exit 1
fi
