#!/usr/bin/env python3
"""
Dictator: Push-to-Talk STT & Punctuation Pipeline
Hotkeys: Hold Ctrl + E to record, release to transcribe, punctuate, and copy.

Pipeline: sounddevice capture -> NVIDIA Parakeet TDT (STT) -> Ollama
(punctuation) -> system clipboard.

All runtime settings can be overridden through environment variables or CLI
flags (see ``--help``), so the same image works across machines without code
edits.
"""

import argparse
import json
import os
import queue
import select
import threading
import time
import urllib.request

import evdev
import numpy as np
import pyperclip
import soundfile as sf
from evdev import ecodes

# ================= Configuration =================
# Each value can be overridden via environment variable, then CLI flag.
SAMPLE_RATE = int(os.environ.get("SAMPLE_RATE", "16000"))  # Parakeet native rate
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "bonsai-2:2b")
ASR_MODEL_ID = os.environ.get("DICTATOR_ASR_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
HOTKEY_SPEC = os.environ.get("DICTATOR_HOTKEY", "ctrl+e")
RAM_DISK_TEMP_PATH = os.environ.get(
    "DICTATOR_TEMP_WAV", "/dev/shm/dictator_temp.wav"
)
# =================================================


def parse_hotkey(spec: str) -> set:
    """Parses a ``ctrl+e`` style spec into a normalized key-token set."""
    tokens = {t.strip().lower() for t in spec.split("+") if t.strip()}
    if not tokens:
        raise ValueError(f"Empty hotkey specification: {spec!r}")
    return tokens


HOTKEY_KEYS = parse_hotkey(HOTKEY_SPEC)

audio_queue = queue.Queue()
audio_stream = None
is_recording = False
currently_pressed = set()
lock = threading.Lock()

# Heavy ASR model is loaded lazily so importing this module stays cheap and
# side-effect free (important for unit tests and fast CLI startup --help).
_asr_model = None
_asr_model_lock = threading.Lock()


def _load_asr_model():
    """Imports and loads the Parakeet ASR model, moving it to GPU if present."""
    print("[1/3] Loading NVIDIA Parakeet TDT ASR model...", flush=True)
    import nemo.collections.asr as nemo_asr
    import torch

    model = nemo_asr.models.ASRModel.from_pretrained(model_name=ASR_MODEL_ID)
    model.eval()

    if torch.cuda.is_available():
        model = model.cuda()
        print("      Model loaded onto CUDA device.", flush=True)
    else:
        print("      Warning: CUDA not detected, running on CPU.", flush=True)
    return model


def get_asr_model():
    """Returns the singleton ASR model, loading it on first use."""
    global _asr_model
    if _asr_model is None:
        with _asr_model_lock:
            if _asr_model is None:
                _asr_model = _load_asr_model()
    return _asr_model


def check_ollama() -> bool:
    """Pings the Ollama server and warns (without failing) if it is unreachable.

    Returns True when the configured model is available.
    """
    print(f"[2/3] Checking Ollama endpoint at {OLLAMA_URL}...", flush=True)
    try:
        base = OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/tags"
        with urllib.request.urlopen(base, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        names = [m.get("name", "") for m in data.get("models", [])]
        if OLLAMA_MODEL in names:
            return True
        print(
            f"      Warning: model '{OLLAMA_MODEL}' not found on Ollama "
            f"(available: {', '.join(names) or 'none'}). "
            f"Run: ollama pull {OLLAMA_MODEL}",
            flush=True,
        )
        return False
    except Exception as err:  # noqa: BLE001 - startup check must never crash
        print(
            f"      Warning: could not reach Ollama ({err}). "
            f"Punctuation will fall back to the raw transcript.",
            flush=True,
        )
        return False


def audio_callback(indata, frames, time_info, status):
    """Feeds incoming audio frames directly into the queue."""
    if status:
        print(f"[Audio Stream Status]: {status}", flush=True)
    audio_queue.put(indata.copy())


def _drain_queue() -> list:
    """Pops every currently queued audio chunk without blocking."""
    chunks = []
    while True:
        try:
            chunks.append(audio_queue.get_nowait())
        except queue.Empty:
            break
    return chunks


def start_audio_capture():
    """Initializes the audio stream when the hotkey is triggered."""
    global audio_stream, is_recording
    import sounddevice as sd  # deferred: needs PortAudio only at capture time

    _drain_queue()
    is_recording = True
    audio_stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        callback=audio_callback,
    )
    audio_stream.start()
    print("\n[Listening... Speak now]", flush=True)


def stop_audio_capture():
    """Stops the audio stream and returns the accumulated audio frames.

    Must be called while holding ``lock`` so start/stop never interleave.
    """
    global audio_stream, is_recording
    is_recording = False
    if audio_stream:
        audio_stream.stop()
        audio_stream.close()
        audio_stream = None

    chunks = _drain_queue()
    if not chunks:
        return None
    return np.concatenate(chunks, axis=0).flatten()


def transcribe_parakeet(audio_data) -> str:
    """Writes to shared RAM disk (/dev/shm) to transcribe with near-zero latency."""
    # Discard audio inputs shorter than 300 ms to avoid accidental key presses
    if audio_data is None or len(audio_data) < SAMPLE_RATE * 0.3:
        return ""

    model = get_asr_model()
    sf.write(RAM_DISK_TEMP_PATH, audio_data, SAMPLE_RATE)
    try:
        results = model.transcribe([RAM_DISK_TEMP_PATH])
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
        "think": False,
        "options": {"temperature": 0.0, "num_ctx": 1024},
    }

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("response", "").strip()
    except Exception as err:  # noqa: BLE001 - graceful degradation is intended
        print(f"[Ollama Error] Falling back to raw transcript: {err}")
        return raw_text


def run_pipeline(audio_data):
    """Executes STT -> Punctuation -> Clipboard on a worker thread.

    Audio capture is already stopped by the hotkey handler; this function only
    does the (slow) compute so the input thread is never blocked.
    """
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

    try:
        pyperclip.copy(punctuated_text)
        print("✓ Copied to clipboard! Ready to paste.")
    except Exception as err:  # noqa: BLE001 - clipboard may be unavailable
        print(f"[Clipboard Error] Could not copy: {err}")


# ================= Hotkey Handlers =================
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
        except Exception:  # noqa: BLE001,S112 - skip unreadable devices
            continue
        if not (
            ecodes.KEY_LEFTCTRL in caps
            or ecodes.KEY_RIGHTCTRL in caps
            or ecodes.KEY_E in caps
        ):
            continue
        devices.append(dev)
    return devices


def _handle_evdev_event(code, value):
    """Updates hotkey state from a single evdev key event.

    Start/stop of audio capture happens atomically under ``lock``; only the
    slow transcription work is handed to a background thread. This avoids the
    race where a quick re-press could start a new stream while the previous one
    was still being torn down.
    """
    key = _normalize_evdev_key(code)
    if key is None:
        return

    captured_audio = None
    with lock:
        if value in (1, 2):  # press or repeat
            currently_pressed.add(key)
            if HOTKEY_KEYS.issubset(currently_pressed) and not is_recording:
                start_audio_capture()
        elif value == 0:  # release
            currently_pressed.discard(key)
            if is_recording and not HOTKEY_KEYS.issubset(currently_pressed):
                # Stop capture synchronously (under lock) and hand the audio
                # off to a worker for transcription.
                captured_audio = stop_audio_capture()

    if captured_audio is not None:
        threading.Thread(
            target=run_pipeline, args=(captured_audio,), daemon=True
        ).start()


def _hotkey_loop():
    """Blocks on evdev devices, dispatching key events until interrupted."""
    devices = _keyboard_devices()
    if not devices:
        print("[Error] No readable keyboard devices found under /dev/input.")
        print(
            "        Make sure you have read access (input group) to the "
            "keyboard device files."
        )
        raise SystemExit(1)

    hotkey_label = " + ".join(sorted(HOTKEY_KEYS))
    print(f"[Input] Monitoring {len(devices)} keyboard device(s) for {hotkey_label}.")

    known_paths = {dev.path for dev in devices}
    last_rescan = time.time()

    while True:
        # Periodically rescan for hot-plugged keyboards.
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
            except (OSError, BlockingIOError):
                print(
                    f"[Input] Keyboard device removed: "
                    f"{getattr(dev, 'name', dev.path)}"
                )
                if dev in devices:
                    devices.remove(dev)
                known_paths.discard(dev.path)
                try:
                    dev.close()
                except Exception:  # noqa: BLE001,S110 - best-effort cleanup
                    pass
                continue
            for event in events:
                if event.type == ecodes.EV_KEY:
                    _handle_evdev_event(event.code, event.value)


def parse_args(argv=None):
    """Builds the CLI parser. Every flag falls back to the env/default value."""
    parser = argparse.ArgumentParser(
        prog="dictator",
        description="Push-to-talk speech-to-text with automatic punctuation.",
    )
    parser.add_argument(
        "--sample-rate", type=int, default=SAMPLE_RATE,
        help="Capture sample rate in Hz (default: %(default)s).",
    )
    parser.add_argument(
        "--ollama-url", default=OLLAMA_URL,
        help="Ollama generate endpoint (default: %(default)s).",
    )
    parser.add_argument(
        "--ollama-model", default=OLLAMA_MODEL,
        help="Ollama model used for punctuation (default: %(default)s).",
    )
    parser.add_argument(
        "--asr-model", default=ASR_MODEL_ID,
        help="NeMo/Hugging Face ASR model id (default: %(default)s).",
    )
    parser.add_argument(
        "--hotkey", default=HOTKEY_SPEC,
        help="Push-to-talk hotkey, e.g. 'ctrl+e' (default: %(default)s).",
    )
    return parser.parse_args(argv)


def _apply_overrides(args):
    """Writes CLI overrides back onto the module-level configuration globals."""
    global SAMPLE_RATE, OLLAMA_URL, OLLAMA_MODEL, ASR_MODEL_ID, HOTKEY_KEYS
    SAMPLE_RATE = args.sample_rate
    OLLAMA_URL = args.ollama_url
    OLLAMA_MODEL = args.ollama_model
    ASR_MODEL_ID = args.asr_model
    HOTKEY_KEYS = parse_hotkey(args.hotkey)


def main(argv=None):
    """Entry point: configure, load models, then enter the hotkey loop."""
    args = parse_args(argv)
    _apply_overrides(args)

    get_asr_model()
    check_ollama()
    print("[3/3] Ready. Press and hold the hotkey to dictate.", flush=True)

    try:
        _hotkey_loop()
    except KeyboardInterrupt:
        print("\n[Exiting Dictator]")


if __name__ == "__main__":
    main()
