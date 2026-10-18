"""Unit tests for Dictator's pure / mockable logic.

These tests deliberately avoid loading the Parakeet model (a heavyweight,
network + CUDA operation) so they run fast in CI. The import-time model load
was removed precisely to make this possible; see ``get_asr_model``.
"""

import json
import urllib.error
from unittest import mock

import numpy as np
import pytest

import dictator


# ---------------------------------------------------------------- hotkey spec
class TestParseHotkey:
    def test_default_spec(self):
        assert dictator.parse_hotkey("ctrl+e") == {"ctrl", "e"}

    def test_is_case_and_space_insensitive(self):
        assert dictator.parse_hotkey("  Ctrl + E ") == {"ctrl", "e"}

    def test_single_key(self):
        assert dictator.parse_hotkey("f9") == {"f9"}

    def test_multi_key(self):
        assert dictator.parse_hotkey("ctrl+shift+space") == {"ctrl", "shift", "space"}

    def test_empty_spec_raises(self):
        with pytest.raises(ValueError):
            dictator.parse_hotkey("   ")

    def test_module_default_matches_spec(self):
        # The module-level constant must be the parsed form of the default spec.
        assert dictator.HOTKEY_KEYS == {"ctrl", "e"}


# ------------------------------------------------------------ evdev key mapping
class TestNormalizeEvdevKey:
    def test_left_ctrl(self):
        assert dictator._normalize_evdev_key(dictator.ecodes.KEY_LEFTCTRL) == "ctrl"

    def test_right_ctrl(self):
        assert dictator._normalize_evdev_key(dictator.ecodes.KEY_RIGHTCTRL) == "ctrl"

    def test_letter_e(self):
        assert dictator._normalize_evdev_key(dictator.ecodes.KEY_E) == "e"

    def test_unrelated_key_is_none(self):
        assert dictator._normalize_evdev_key(dictator.ecodes.KEY_A) is None


# ------------------------------------------------------------- queue draining
class TestDrainQueue:
    def test_drains_all_without_blocking(self):
        sentinel = object()
        q = dictator.audio_queue
        # Clear anything left over, then push two frames.
        dictator._drain_queue()
        q.put(sentinel)
        q.put(sentinel)
        out = dictator._drain_queue()
        assert out == [sentinel, sentinel]
        assert q.empty()

    def test_empty_queue_returns_empty_list(self):
        dictator._drain_queue()
        assert dictator._drain_queue() == []


# ---------------------------------------------------- transcription length gate
class TestTranscribeGuard:
    def test_none_audio_short_circuits(self, monkeypatch):
        # Must NOT touch the model for empty input.
        monkeypatch.setattr(dictator, "get_asr_model", mock.Mock())
        assert dictator.transcribe_parakeet(None) == ""
        dictator.get_asr_model.assert_not_called()

    def test_too_short_audio_short_circuits(self, monkeypatch):
        monkeypatch.setattr(dictator, "get_asr_model", mock.Mock())
        # 100 ms at 16 kHz is below the 300 ms threshold.
        short = np.zeros(int(0.1 * dictator.SAMPLE_RATE), dtype=np.float32)
        assert dictator.transcribe_parakeet(short) == ""
        dictator.get_asr_model.assert_not_called()


# ------------------------------------------------------------- punctuation path
class TestFormatPunctuation:
    @staticmethod
    def _fake_response(payload_dict):
        class _Resp:
            def read(self):
                return json.dumps(payload_dict).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    def test_returns_model_response(self):
        with mock.patch.object(
            dictator.urllib.request, "urlopen",
            return_value=self._fake_response({"response": "Hello world."}),
        ):
            assert dictator.format_punctuation_ollama("hello world") == "Hello world."

    def test_falls_back_to_raw_on_error(self):
        with mock.patch.object(
            dictator.urllib.request, "urlopen",
            side_effect=urllib.error.URLError("down"),
        ):
            raw = "no punctuation here"
            assert dictator.format_punctuation_ollama(raw) == raw

    def test_payload_uses_configured_model_and_deterministic_settings(self):
        captured = {}

        def _capture(req, timeout=None):
            captured["url"] = req.full_url
            captured["payload"] = json.loads(req.data.decode())
            return self._fake_response({"response": "x"})

        with mock.patch.object(dictator.urllib.request, "urlopen", side_effect=_capture):
            dictator.format_punctuation_ollama("hi")

        assert captured["url"] == dictator.OLLAMA_URL
        assert captured["payload"]["model"] == dictator.OLLAMA_MODEL
        assert captured["payload"]["options"]["temperature"] == 0.0
        assert captured["payload"]["think"] is False


# ------------------------------------------------------------- hotkey state machine
class TestHotkeyStateMachine:
    @pytest.fixture(autouse=True)
    def _reset_state(self):
        with dictator.lock:
            dictator.currently_pressed.clear()
            dictator.is_recording = False
            dictator.audio_stream = None
        yield
        with dictator.lock:
            dictator.currently_pressed.clear()
            dictator.is_recording = False

    def test_press_ctrl_then_e_starts_capture(self):
        starts = []

        def fake_start():
            dictator.is_recording = True
            starts.append(1)

        with mock.patch.object(dictator, "start_audio_capture", side_effect=fake_start):
            # _handle_evdev_event acquires dictator.lock itself; do not pre-hold it.
            dictator._handle_evdev_event(dictator.ecodes.KEY_LEFTCTRL, 1)
            assert not dictator.is_recording  # only one key down
            dictator._handle_evdev_event(dictator.ecodes.KEY_E, 1)
        assert len(starts) == 1
        assert dictator.is_recording

    def test_partial_key_release_does_not_stop(self):
        # Holding Ctrl alone (never reached full combo) then releasing it.
        with mock.patch.object(dictator, "start_audio_capture") as fake_start, \
             mock.patch.object(dictator, "run_pipeline") as fake_pipe:
            dictator._handle_evdev_event(dictator.ecodes.KEY_LEFTCTRL, 1)
            dictator._handle_evdev_event(dictator.ecodes.KEY_LEFTCTRL, 0)
        fake_start.assert_not_called()
        fake_pipe.assert_not_called()

    def test_release_triggers_pipeline_with_audio(self):
        # Simulate: combo pressed (capturing), then Ctrl released -> pipeline runs.
        fake_audio = np.zeros(100, dtype=np.float32)
        started = []

        def fake_start():
            started.append(1)
            dictator.is_recording = True

        def fake_stop():
            dictator.is_recording = False
            return fake_audio

        threads = []

        class _FakeThread:
            def __init__(self, target=None, args=(), daemon=None):
                self._t, self._a = target, args
                threads.append(self)

            def start(self):
                self._t(*self._a)

        with mock.patch.object(dictator, "start_audio_capture", side_effect=fake_start), \
             mock.patch.object(dictator, "stop_audio_capture", side_effect=fake_stop), \
             mock.patch.object(dictator, "run_pipeline") as fake_pipe, \
             mock.patch.object(dictator.threading, "Thread", _FakeThread):
            # Press both keys -> starts capture.
            dictator._handle_evdev_event(dictator.ecodes.KEY_LEFTCTRL, 1)
            dictator._handle_evdev_event(dictator.ecodes.KEY_E, 1)
            assert len(started) == 1
            # Release Ctrl -> combo no longer fully held -> stop + handoff.
            dictator._handle_evdev_event(dictator.ecodes.KEY_LEFTCTRL, 0)

        # stop was called and pipeline got the captured audio off-thread.
        assert threads, "expected a worker thread for run_pipeline"
        assert fake_pipe.call_count == 1
        np.testing.assert_array_equal(fake_pipe.call_args[0][0], fake_audio)


# ------------------------------------------------------------- Ollama health check
class TestCheckOllama:
    @staticmethod
    def _resp(payload):
        class _R:
            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return _R()

    def test_model_present_returns_true(self):
        with mock.patch.object(
            dictator.urllib.request, "urlopen",
            return_value=self._resp({"models": [{"name": dictator.OLLAMA_MODEL}]}),
        ):
            assert dictator.check_ollama() is True

    def test_unreachable_returns_false(self):
        with mock.patch.object(
            dictator.urllib.request, "urlopen",
            side_effect=urllib.error.URLError("refused"),
        ):
            assert dictator.check_ollama() is False
