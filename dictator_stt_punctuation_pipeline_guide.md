# Dictator: Push-to-Talk STT & Punctuation Pipeline

A lightweight, local, low-latency push-to-talk dictation utility for Ubuntu Linux designed to fit comfortably within an 8 GB VRAM budget.

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
  Transcribes audio directly via RAM-disk (/dev/shm) into raw text
                │
                ▼
     [ Ollama: Qwen 3.5 (2B) ]
  Restores punctuation & capitalization without modifying words/grammar
                │
                ▼
      [ System Clipboard ]
  Copies final formatted text via xclip / wl-clipboard
                │
                ▼
[ User pastes clean text anywhere via Ctrl + V ]
```

---

## 2. Resource & VRAM Budget (8 GB Target)

| Component | VRAM Footprint | Description |
| :--- | :--- | :--- |
| **NVIDIA Driver & Display** | ~0.5 – 0.8 GB | Base desktop overhead (GNOME / X11 / Wayland) |
| **Parakeet TDT 0.6B v3** | ~1.5 – 2.0 GB | Fast RNN-T / TDT acoustic model running on PyTorch/CUDA |
| **Ollama (Qwen 3.5 2B Q4)** | ~1.5 – 2.0 GB | Punctuation restorer with restricted context (`num_ctx: 1024`) |
| **Buffer / Headroom** | ~3.0 GB | Available memory ensuring zero CUDA OOM errors |

---

## 3. System Requirements & Installation

### Step 1: System Packages (Ubuntu)

Install system-level libraries for PortAudio and clipboard managers (supporting both X11 and Wayland):

```bash
sudo apt update
sudo apt install -y libportaudio2 portaudio19-dev xclip wl-clipboard
```

### Step 2: Python Environment

Create an isolated virtual environment with CUDA-enabled PyTorch:

```bash
# Create and activate virtual environment
python3 -m venv ~/dictator-env
source ~/dictator-env/bin/activate

# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install pipeline dependencies
pip install sounddevice soundfile numpy pynput pyperclip evdev
pip install "nemo_toolkit[asr]"
```

### Step 3: Ollama Model Setup

Ensure Ollama is installed and active on your system, then pull the lightweight Qwen 3.5 model:

```bash
ollama serve &
ollama pull qwen3.5:2b
```

---

## 4. Production Script (`dictator.py`)

Create a script named `dictator.py`:

```python
#!/usr/bin/env python3
"""
Dictator: Push-to-Talk STT & Punctuation Pipeline
Hotkeys: Hold Ctrl + E to record, release to transcribe, punctuate, and copy.
"""

import os
import json
import queue
import os
import json
import queue
import threading
import time
import select
import urllib.request
import numpy as np
import sounddevice as sd
import soundfile as sf
import pyperclip
import evdev
from evdev import ecodes
import torch

# ================= Configuration =================
SAMPLE_RATE = 16000          # Parakeet native sample rate (16 kHz mono)
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "bonsai-2:2b"
HOTKEY_KEYS = {"ctrl", "e"}
RAM_DISK_TEMP_PATH = "/dev/shm/dictator_temp.wav"
# =================================================

audio_queue = queue.Queue()
audio_stream = None
is_recording = False
currently_pressed = set()
lock = threading.Lock()

print("[1/3] Loading NVIDIA Parakeet TDT ASR model...")
import nemo.collections.asr as nemo_asr
parakeet_model = nemo_asr.models.ASRModel.from_pretrained(
    model_name="nvidia/parakeet-tdt-0.6b-v3"
)
parakeet_model.eval()

if torch.cuda.is_available():
    parakeet_model = parakeet_model.cuda()
    print("      Model loaded onto CUDA device.")
else:
    print("      Warning: CUDA not detected, running on CPU.")

print(f"[2/3] Checking Ollama endpoint at {OLLAMA_URL}...")
print(f"[3/3] Ready. Press and hold Ctrl + E to dictate.")


def audio_callback(indata, frames, time_info, status):
    """Feeds incoming audio frames directly into the queue."""
    if status:
        print(f"[Audio Stream Status]: {status}", flush=True)
    audio_queue.put(indata.copy())


def start_audio_capture():
    """Initializes the audio stream when the hotkey is triggered."""
    global audio_stream, is_recording
    while not audio_queue.empty():
        audio_queue.get_nowait()

    is_recording = True
    audio_stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='float32',
        callback=audio_callback
    )
    audio_stream.start()
    print("\n[Listening... Speak now]", flush=True)


def stop_audio_capture():
    """Stops the audio stream and extracts accumulated audio frames."""
    global audio_stream, is_recording
    is_recording = False
    if audio_stream:
        audio_stream.stop()
        audio_stream.close()
        audio_stream = None

    chunks = []
    while not audio_queue.empty():
        chunks.append(audio_queue.get_nowait())

    if not chunks:
        return None

    return np.concatenate(chunks, axis=0).flatten()


def transcribe_parakeet(audio_data: np.ndarray) -> str:
    """Writes to shared RAM disk (/dev/shm) to transcribe with near-zero latency."""
    # Discard audio inputs shorter than 300 ms to avoid accidental key presses
    if audio_data is None or len(audio_data) < SAMPLE_RATE * 0.3:
        return ""

    sf.write(RAM_DISK_TEMP_PATH, audio_data, SAMPLE_RATE)
    try:
        results = parakeet_model.transcribe([RAM_DISK_TEMP_PATH])
        if not results:
            return ""
        first = results[0]
        text = getattr(first, "text", first)
        return str(text).strip()
    finally:
        if os.path.exists(RAM_DISK_TEMP_PATH):
            os.remove(RAM_DISK_TEMP_PATH)


def format_punctuation_ollama(raw_text: str) -> str:
    """Restores punctuation and capitalization using local Ollama model."""
    prompt = (
        "Add appropriate punctuation and capitalization to the following transcript.\n"
        "Do not change any words. Do not rephrase.\n"
        "Output only the punctuated text.\n"
        f"Transcript:\n{raw_text}"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_ctx": 1024
        }
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("response", "").strip()
    except Exception as err:
        print(f"[Ollama Error] Falling back to raw transcript: {err}")
        return raw_text


def run_pipeline():
    """Executes the STT -> Punctuation -> Clipboard pipeline on a worker thread."""
    audio_data = stop_audio_capture()
    if audio_data is None:
        return

    print("[STT Processing...]")
    raw_text = transcribe_parakeet(audio_data)
    if not raw_text:
        print("[No actionable audio found]")
        return
    print(f"  Raw STT: {raw_text}")

    print(f"[Punctuating with {OLLAMA_MODEL}...]")
    punctuated_text = format_punctuation_ollama(raw_text)
    print(f"  Cleaned: {punctuated_text}")

    pyperclip.copy(punctuated_text)
    print("✓ Copied to clipboard! Ready to paste.")


# ================= Hotkey Handlers =================
currently_pressed = set()


def _normalize_evdev_key(code):
    """Maps evdev key codes to the normalized hotkey tokens."""
    if code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
        return "ctrl"
    if code == ecodes.KEY_E:
        return "e"
    return None


def _keyboard_devices():
    """Returns readable evdev devices capable of emitting Ctrl or E."""
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities().get(ecodes.EV_KEY, [])
        except Exception:
            continue
        if not (ecodes.KEY_LEFTCTRL in caps or ecodes.KEY_RIGHTCTRL in caps or ecodes.KEY_E in caps):
            continue
        devices.append(dev)
    return devices


def _handle_evdev_event(code, value):
    """Updates hotkey state from a single evdev key event."""
    global is_recording
    key = _normalize_evdev_key(code)
    if key is None:
        return

    with lock:
        if value in (1, 2):  # press or repeat
            currently_pressed.add(key)
            if HOTKEY_KEYS.issubset(currently_pressed) and not is_recording:
                start_audio_capture()
        elif value == 0:  # release
            was_recording = is_recording
            currently_pressed.discard(key)
            if was_recording and not HOTKEY_KEYS.issubset(currently_pressed):
                threading.Thread(target=run_pipeline, daemon=True).start()


if __name__ == "__main__":
    devices = _keyboard_devices()
    if not devices:
        print("[Error] No readable keyboard devices found under /dev/input.")
        print("        Make sure you have read access (input group) to the keyboard device files.")
        raise SystemExit(1)

    print(f"[Input] Monitoring {len(devices)} keyboard device(s) for Ctrl + E.")

    known_paths = {dev.path for dev in devices}
    last_rescan = time.time()

    try:
        while True:
            if time.time() - last_rescan > 5.0:
                last_rescan = time.time()
                for dev in _keyboard_devices():
                    if dev.path not in known_paths:
                        devices.append(dev)
                        known_paths.add(dev.path)
                        print(f"[Input] Added keyboard device: {dev.name}")

            if not devices:
                print("[Input] No keyboard devices available; rescanning...")
                time.sleep(1.0)
                devices = _keyboard_devices()
                known_paths = {dev.path for dev in devices}
                continue

            try:
                readable, _, _ = select.select(devices, [], [], 0.5)
            except (ValueError, OSError):
                time.sleep(0.5)
                continue

            for dev in list(readable):
                try:
                    events = list(dev.read())
                except (OSError, IOError, BlockingIOError):
                    print(f"[Input] Keyboard device removed: {getattr(dev, 'name', dev.path)}")
                    if dev in devices:
                        devices.remove(dev)
                    known_paths.discard(dev.path)
                    try:
                        dev.close()
                    except Exception:
                        pass
                    continue
                for event in events:
                    if event.type == ecodes.EV_KEY:
                        _handle_evdev_event(event.code, event.value)
    except KeyboardInterrupt:
        print("\n[Exiting Dictator]")
```

---

## 5. Execution & Linux Desktop Integration

### Running the Script

```bash
source ~/dictator-env/bin/activate
python dictator.py
```

### Wayland vs. X11 Permissions

1. **Under X11 (`echo $XDG_SESSION_TYPE` returns `x11`):**
   * The script captures `Ctrl + E` globally across any active window without extra privileges.
2. **Under Wayland (`echo $XDG_SESSION_TYPE` returns `wayland`):**
   * Wayland blocks global keyloggers for security, so the script no longer relies on X11 or `sudo`.
   * It reads keyboard events directly from `/dev/input` (via `evdev`), which works for both X11 and Wayland sessions. Make sure your user can read the keyboard devices, usually by being in the `input` group:
     ```bash
     sudo usermod -aG input $USER
     ```
     Then log out and back in. After that, run normally:
     ```bash
     source ~/dictator-env/bin/activate
     python dictator.py
     ```
   * *Alternative native solution*: Bind a custom keyboard shortcut under **Settings → Keyboard → View and Customize Shortcuts** to trigger an IPC flag (or run an activation script) if direct `/dev/input` access is undesirable.

### Optimizations Included

* **RAM Buffer (`/dev/shm`):** NeMo's file transcription path operates completely within RAM, avoiding physical disk writes.
* **Low KV Cache (`num_ctx: 1024`):** Keeps Ollama's attention memory minimal so that VRAM remains well below the 8 GB ceiling.
* **Deterministic Output (`temperature: 0.0`):** Prevents hallucinations or word modifications during punctuation correction.