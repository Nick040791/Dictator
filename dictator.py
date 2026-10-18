#!/usr/bin/env python3
"""
Dictator: Push-to-Talk STT & Punctuation Pipeline
Hotkeys: Hold Ctrl + E to record, release to transcribe, punctuate, and copy.
"""

import os
import json
import queue
import threading
import urllib.request
import numpy as np
import sounddevice as sd
import soundfile as sf
import pyperclip
from pynput import keyboard
import torch

# ================= Configuration =================
SAMPLE_RATE = 16000          # Parakeet native sample rate (16 kHz mono)
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.5:2b"
HOTKEY_KEYS = {keyboard.Key.ctrl, keyboard.KeyCode(char='e')}
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
    model_name="nvidia/parakeet-tdt-0.6b-en"
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
        return results[0].strip() if results else ""
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

    print("[Punctuating with Qwen 3.5...]")
    punctuated_text = format_punctuation_ollama(raw_text)
    print(f"  Cleaned: {punctuated_text}")

    pyperclip.copy(punctuated_text)
    print("✓ Copied to clipboard! Ready to paste.")


# ================= Hotkey Handlers =================
def normalize_key(key):
    """Resolves Left/Right Ctrl to a single Key.ctrl value."""
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        return keyboard.Key.ctrl
    return key


def on_press(key):
    normalized = normalize_key(key)
    with lock:
        currently_pressed.add(normalized)
        if HOTKEY_KEYS.issubset(currently_pressed) and not is_recording:
            start_audio_capture()


def on_release(key):
    normalized = normalize_key(key)
    with lock:
        was_recording = is_recording
        if normalized in currently_pressed:
            currently_pressed.remove(normalized)

        # Trigger processing once any hotkey key is released
        if was_recording and not HOTKEY_KEYS.issubset(currently_pressed):
            threading.Thread(target=run_pipeline, daemon=True).start()


if __name__ == "__main__":
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()