# Dictator: Push-to-Talk STT & Punctuation Pipeline

A lightweight, local, low-latency push-to-talk dictation utility for Linux (Wayland) designed to fit comfortably within an 8 GB VRAM budget.

Hold **Ctrl + E** to record, release to transcribe, punctuate, and copy the result to the clipboard. Paste anywhere with **Ctrl + V**.

---

## 1. System Architecture

```text
[ User presses & holds Ctrl + E ]
                │
                ▼
      [ sounddevice Capture ]
  Records 16 kHz mono float32 audio stream directly into memory queue
                │
[ User releases Ctrl + E ]
                │
                ▼
   [ Parakeet TDT 0.6B v3 STT ]
  Transcribes audio via RAM-disk (/dev/shm) into raw text
                │
                ▼
     [ Ollama: bonsai-2:2b ]
  Restores punctuation & capitalization without modifying words/grammar
                │
                ▼
      [ System Clipboard (Wayland) ]
  Copies final formatted text via wl-clipboard
                │
                ▼
[ User pastes clean text anywhere via Ctrl + V ]
```

---

## 2. Resource & VRAM Budget (8 GB Target)

| Component | VRAM Footprint | Description |
| :--- | :--- | :--- |
| **NVIDIA Driver & Display** | ~0.5 – 0.8 GB | Base desktop overhead (Wayland) |
| **Parakeet TDT 0.6B v3** | ~1.5 – 2.0 GB | Fast RNN-T / TDT acoustic model running on PyTorch/CUDA |
| **Ollama (bonsai-2:2b)** | ~1.5 – 2.0 GB | Punctuation restorer with restricted context (`num_ctx: 1024`) |
| **Buffer / Headroom** | ~3.0 GB | Available memory ensuring zero CUDA OOM errors |

---

## 3. System Requirements & Installation

### Step 1: System Packages (Ubuntu, Wayland)

Install PortAudio and the Wayland clipboard tooling:

```bash
sudo apt update
sudo apt install -y libportaudio2 portaudio19-dev wl-clipboard
```

### Step 2: Python Environment

Create an isolated virtual environment with CUDA-enabled PyTorch:

```bash
python3 -m venv ~/dictator-env
source ~/dictator-env/bin/activate

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

pip install sounddevice soundfile numpy pyperclip evdev
pip install "nemo_toolkit[asr]"
```

### Step 3: Ollama Model Setup

Ensure Ollama is installed and running, then pull the punctuation model:

```bash
ollama serve &
ollama pull bonsai-2:2b
```

### Step 4: Keyboard Device Access (Wayland)

Dictator reads keyboard events directly from `/dev/input` via `evdev` to work around Wayland's global-shortcut restrictions. Grant your user read access to the input devices:

```bash
sudo usermod -aG input $USER
```

Log out and back in for the group change to take effect. (No `sudo` is required to run Dictator afterwards.)

---

## 4. Running Dictator

### Foreground (manual)

```bash
source ~/dictator-env/bin/activate
python /home/mrnicholas/Dev/Dictator/dictator.py
```

### Background service (provided scripts)

```bash
/home/mrnicholas/Dev/Dictator/scripts/start.sh    # start (no-op if already running)
/home/mrnicholas/Dev/Dictator/scripts/stop.sh     # stop
/home/mrnicholas/Dev/Dictator/scripts/restart.sh  # restart
/home/mrnicholas/Dev/Dictator/scripts/toggle.sh   # start or stop depending on state
```

`start.sh` runs the app with `nohup` and writes logs to `~/.local/share/dictator/dictator.log` (PID in `~/.local/share/dictator/dictator.pid`).

### Desktop shortcut

A ready-to-use launcher is provided as `dictator.desktop`. To use it from the desktop:

```bash
cp /home/mrnicholas/Dev/Dictator/dictator.desktop ~/Desktop/dictator.desktop
chmod +x ~/Desktop/dictator.desktop
gio set ~/Desktop/dictator.desktop metadata::trusted true
```

Double-clicking the icon toggles the service (start if stopped, stop if running). Right-click exposes **Start / Stop / Restart** actions.

---

## 5. Notes

* **Wayland only:** This setup targets Wayland sessions. Global hotkeys are captured through `/dev/input` (evdev), not X11.
* **RAM buffer (`/dev/shm`):** NeMo's file transcription path operates in RAM, avoiding physical disk writes.
* **Low KV cache (`num_ctx: 1024`):** Keeps Ollama's attention memory minimal so VRAM stays below the 8 GB ceiling.
* **Deterministic output (`temperature: 0.0`):** Prevents hallucinations or word modifications during punctuation correction.
* **Think mode disabled:** Ollama is called with `think: false` for direct punctuation output.

---

## 6. Troubleshooting

* **"No readable keyboard devices found"** — your user is not in the `input` group, or you have not logged out/back in after adding it.
* **Ollama errors / fallback to raw transcript** — ensure `ollama serve` is running and `bonsai-2:2b` is pulled.
* **No audio captured** — check microphone permissions / PulseAudio/PipeWire and that `libportaudio2` is installed.
* **Logs:** `tail -f ~/.local/share/dictator/dictator.log`
path: /home/mrnicholas/Dev/Dictator/README.md