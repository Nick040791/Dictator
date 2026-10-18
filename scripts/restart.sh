#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/stop.sh" >/dev/null 2>&1 || true
sleep 1
exec "$SCRIPT_DIR/start.sh"
