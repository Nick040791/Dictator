# Dictator

<!-- Replace the username below with your GitHub handle if forking. -->
[![CI](https://github.com/Nick040791/Dictator/actions/workflows/ci.yml/badge.svg)](https://github.com/Nick040791/Dictator/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/linter-ruff-261230.svg)](https://docs.astral.sh/ruff/)

**A local, low-latency push-to-talk dictation tool for Linux (Wayland).** Hold a
hotkey, speak, release — your words come back punctuated and on the clipboard,
ready to paste. Everything runs on-device: no cloud, no telemetry, no
subscription.

```text
hold Ctrl + E ──► record ──► Parakeet STT ──► Ollama punctuation ──► clipboard
                 release                                 │
                                              paste anywhere with Ctrl + V
```

---

## Highlights

- **Sub-second transcription** — NVIDIA Parakeet TDT 0.6B v3 via NeMo, warmed and
  resident on GPU; audio is buffered in RAM (`/dev/shm`) so no disk I/O touches
  the hot path.
- **Automatic punctuation & casing** — a small local LLM (via Ollama) restores
  punctuation without ever changing a word (temperature `0.0`, verbatim prompt).
- **Wayland-native hotkeys** — reads `/dev/input` with `evdev`, sidestepping
  Wayland's global-shortcut restrictions entirely (no X11, no XGrabKey hacks).
- **Hot-plug resilient** — monitors multiple keyboards, rescans every 5 s, and
  survives devices being unplugged mid-session.
- **Runs anywhere** — native (venv + scripts) or fully containerized (Docker +
  NVIDIA runtime), with a desktop launcher and a systemd user service.
- **Fits an 8 GB VRAM budget** — measured end-to-end within the target on a
  GTX 1070 (see [Resource budget](#resource--vram-budget)).

---

## Table of contents

- [How it works](#how-it-works)
- [Resource & VRAM budget](#resource--vram-budget)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)
- [Docker](#docker)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)
- [License](#license)

---

## How it works

```text
[ User presses & holds Ctrl + E ]
                │
                ▼
      [ sounddevice capture ]
  16 kHz mono float32 frames pushed to an in-memory queue
                │
[ User releases Ctrl + E ]        capture stop is atomic (single lock);
                │                 transcription runs on a worker thread
                ▼
   [ Parakeet TDT 0.6B v3 ]  ──► raw text (NeMo ASR, CUDA)
                │
                ▼
     [ Ollama · bonsai-2:2b ] ──► punctuated, capitalized text
                │                  (words never altered)
                ▼
      [ system clipboard ]       pyperclip / wl-clipboard on Wayland
                │
                ▼
[ Paste anywhere with Ctrl + V ]
```

Design notes:

- **`/dev/shm` for audio** — NeMo's file-based `transcribe()` API is handed a WAV
  on the RAM disk, so transcription latency stays near zero.
- **Atomic capture state** — `start`/`stop` of the microphone happen under one
  lock; only the slow STT/LLM work is pushed to a daemon thread, so a quick
  re-press can't interleave with teardown.
- **Graceful degradation** — if Ollama is down, Dictator falls back to the raw
  (unpunctuated) transcript instead of failing.

---

## Resource & VRAM budget

Target ceiling: **8 GB**.

| Component                          | VRAM footprint | Notes                                      |
| --------------------------------- | -------------- | ------------------------------------------ |
| NVIDIA driver & Wayland display    | ~0.5 – 0.8 GB  | Base desktop overhead                      |
| Parakeet TDT 0.6B v3               | ~1.5 – 2.0 GB  | RNN-T / TDT acoustic model (CUDA)          |
| Ollama · `bonsai-2:2b`             | ~1.5 – 2.0 GB  | `num_ctx: 1024` to keep KV cache small     |
| Headroom                           | ~3.0 GB        | Absorbs fragmentation, avoids CUDA OOM     |

Measured on a GTX 1070 (8 GB): Dictator's process peaks around **4.9 GB** during
transcription, leaving ample headroom alongside a desktop session.

---

## Requirements

- **OS:** Linux with a **Wayland** session (X11 is not supported — hotkeys use
  `/dev/input`).
- **GPU:** NVIDIA GPU + driver (CUDA). CPU-only works but is slower.
- **Python:** 3.10+.
- **Ollama:** running locally, with the punctuation model pulled.
- **Packages:** PortAudio, wl-clipboard, and access to the `input` group.

---

## Quick start

The one-shot installer handles system packages, the venv, Python dependencies,
the Ollama model, group membership, and the desktop launcher:

```bash
git clone https://github.com/Nick040791/Dictator.git
cd Dictator
./install.sh
```

> **After install:** if you were added to the `input` group, **log out and back
> in** before running Dictator.

### Manual install

<details>
<summary>Step-by-step (equivalent to <code>./install.sh</code>)</summary>

**1. System packages (Ubuntu / Debian):**

```bash
sudo apt update
sudo apt install -y libportaudio2 portaudio19-dev wl-clipboard python3-venv
```

**2. Python environment (CUDA-enabled PyTorch):**

```bash
python3 -m venv ~/dictator-env
source ~/dictator-env/bin/activate

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
pip install "nemo_toolkit[asr]"
```

**3. Ollama punctuation model:**

```bash
ollama serve &
ollama pull bonsai-2:2b
```

**4. Keyboard device access (Wayland):**

```bash
sudo usermod -aG input "$USER"
# log out and back in for the group change to take effect
```

</details>

---

## Usage

### Foreground

```bash
source ~/dictator-env/bin/activate
python dictator.py
```

Hold **Ctrl + E** to record; release to transcribe, punctuate, and copy. Paste
with **Ctrl + V**.

### Background service

```bash
./scripts/start.sh     # start (no-op if already running)
./scripts/stop.sh      # stop
./scripts/restart.sh   # restart
./scripts/toggle.sh    # start or stop, depending on state
```

`start.sh` launches Dictator as a **systemd user service** (so it survives the
launcher exiting) and writes logs to `~/.local/share/dictator/dictator.log`.

### Desktop launcher

`install.sh` installs a `.desktop` entry. You can also install it manually —
the repo ships `dictator.desktop` with an `@PROJECT_DIR@` placeholder that
`install.sh` resolves to your checkout:

```bash
./install.sh   # resolves @PROJECT_DIR@ and installs the launcher
```

The icon **toggles** the service (start if stopped, stop if running); right-click
exposes **Start / Stop / Restart**.

---

## Configuration

Every setting can be overridden by **environment variable** or **CLI flag**, so
the same image runs across machines with no code edits.

| Env var                | CLI flag          | Default                            | Purpose                          |
| ---------------------- | ----------------- | ---------------------------------- | -------------------------------- |
| `SAMPLE_RATE`          | `--sample-rate`   | `16000`                            | Capture sample rate (Hz)         |
| `OLLAMA_URL`           | `--ollama-url`    | `http://localhost:11434/api/generate` | Ollama generate endpoint      |
| `OLLAMA_MODEL`         | `--ollama-model`  | `bonsai-2:2b`                      | Ollama punctuation model         |
| `DICTATOR_ASR_MODEL`   | `--asr-model`     | `nvidia/parakeet-tdt-0.6b-v3`      | NeMo/HF ASR model id             |
| `DICTATOR_HOTKEY`      | `--hotkey`        | `ctrl+e`                           | Push-to-talk hotkey              |
| `DICTATOR_TEMP_WAV`    | —                 | `/dev/shm/dictator_temp.wav`       | RAM-disk temp file for STT       |

```bash
# Example: use a different hotkey and punctuation model
python dictator.py --hotkey "ctrl+shift+space" --ollama-model bonsai-2:27b
```

Run `python dictator.py --help` for the full reference.

---

## Docker

An NVIDIA Container Toolkit setup is included. The compose file passes through
`/dev/snd` (mic), `/dev/input` (hotkeys), the Wayland socket (clipboard), and
`/dev/shm` (audio buffer), and sets the same env vars shown above.

```bash
docker compose up --build -d
docker compose logs -f
```

> The compose file's `OLLAMA_*` env vars are now actually consumed by
> `dictator.py` (they used to be ignored).

---

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

pytest              # 22 unit tests, no GPU/model required (< 0.1 s)
ruff check .        # lint
ruff format .       # format
```

The ASR model loads **lazily on first use**, so importing `dictator` is fast and
side-effect free — unit tests run without touching CUDA or the network.

CI (GitHub Actions) runs lint, tests, shell syntax checks, and Dockerfile lint on
every push and PR.

---

## Troubleshooting

- **"No readable keyboard devices found"** — your user isn't in the `input`
  group, or you haven't logged out/back in after adding it.
- **Ollama errors / fallback to raw transcript** — ensure `ollama serve` is
  running and the model is pulled (`ollama pull bonsai-2:2b`).
- **No audio captured** — check mic permissions and that `libportaudio2` is
  installed (`pactl list sources short` to confirm a default source).
- **CUDA out of memory** — make sure no other model process is holding VRAM
  (`nvidia-smi`); Dictator targets < 5 GB for its own process.
- **Logs** — `tail -f ~/.local/share/dictator/dictator.log`

---

## Project structure

```text
Dictator/
├── dictator.py            # main app: capture → STT → punctuation → clipboard
├── requirements.txt       # lightweight runtime deps (torch/NeMo installed separately)
├── requirements-dev.txt   # + pytest, ruff
├── install.sh             # one-shot installer
├── scripts/               # start / stop / restart / toggle (systemd user service)
├── dictator.desktop       # desktop launcher template (@PROJECT_DIR@ placeholder)
├── Dockerfile             # CUDA runtime image
├── docker-compose.yaml    # device/socket passthrough + env config
├── tests/                 # unit tests (no GPU required)
└── .github/workflows/     # CI pipeline
```

---

## License

MIT — see [LICENSE](LICENSE).
