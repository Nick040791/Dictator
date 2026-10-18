#!/usr/bin/env bash
# install.sh — one-shot setup for Dictator (Wayland, push-to-talk STT).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${HOME}/dictator-env"
RUNTIME_DIR="${HOME}/.local/share/dictator"

echo "=== Dictator installer ==="
echo "Project: ${PROJECT_DIR}"

# --- System packages ---
echo "[1/6] Installing system packages..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y \
        libportaudio2 portaudio19-dev \
        wl-clipboard \
        python3 python3-venv
else
    echo "  apt-get not found; install PortAudio + wl-clipboard manually."
fi

# --- Python virtual environment ---
echo "[2/6] Creating Python virtual environment at ${VENV_DIR}..."
if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[3/6] Installing Python dependencies..."
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install sounddevice soundfile numpy pyperclip evdev
pip install "nemo_toolkit[asr]"

# --- Ollama model ---
echo "[4/6] Pulling Ollama punctuation model (bonsai-2:2b)..."
if command -v ollama >/dev/null 2>&1; then
    (ollama serve >/dev/null 2>&1 &) || true
    sleep 2
    ollama pull bonsai-2:2b || echo "  Could not pull model; ensure Ollama is running."
else
    echo "  Ollama not installed. Install from https://ollama.com then run: ollama pull bonsai-2:2b"
fi

# --- Input group access (Wayland hotkeys via evdev) ---
echo "[5/6] Granting /dev/input read access..."
if id -nG "$USER" | grep -qw input; then
    echo "  ${USER} already in 'input' group."
else
    sudo usermod -aG input "$USER"
    echo "  Added ${USER} to 'input' group. Log out and back in for it to take effect."
fi

# --- Runtime dirs + desktop integration ---
echo "[6/6] Setting up runtime dir and desktop launcher..."
mkdir -p "${RUNTIME_DIR}"
chmod +x "${PROJECT_DIR}/scripts/"*.sh 2>/dev/null || true

DESKTOP_FILE="${PROJECT_DIR}/dictator.desktop"
if [[ -f "${DESKTOP_FILE}" ]]; then
    chmod +x "${DESKTOP_FILE}"
    mkdir -p "${HOME}/.local/share/applications"
    cp "${DESKTOP_FILE}" "${HOME}/.local/share/applications/dictator.desktop"
    if [[ -d "${HOME}/Desktop" ]]; then
        cp "${DESKTOP_FILE}" "${HOME}/Desktop/dictator.desktop"
        chmod +x "${HOME}/Desktop/dictator.desktop"
        command -v gio >/dev/null 2>&1 && gio set "${HOME}/Desktop/dictator.desktop" metadata::trusted true || true
    fi
fi

echo
echo "=== Installation complete ==="
echo "Start Dictator:   ${PROJECT_DIR}/scripts/start.sh"
echo "Stop:             ${PROJECT_DIR}/scripts/stop.sh"
echo "Logs:             ${RUNTIME_DIR}/dictator.log"
echo
echo "If you were added to the 'input' group, log out and back in before running."
