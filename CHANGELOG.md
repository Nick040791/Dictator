# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — 2026-10-18

### Changed (major polish for public release)
- **Production-quality rewrite of `dictator.py`**: lazy ASR model loading (import
  no longer loads NeMo/CUDA), CLI flags + env var overrides, atomic capture
  under lock (race-free hotkey state machine), robust evdev hot-plug handling,
  proper cleanup on device removal, friendlier Ollama health check with
  warnings.
- **Dockerfile**: removed unused `pynput` dependency.
- **`dictator.desktop`**: template with `@PROJECT_DIR@` placeholder (resolved by
  `install.sh`) — no more hardcoded personal paths.
- **`install.sh`**: now resolves and installs the templated desktop file.
- **README**: full rewrite for public audience (badges, architecture diagram,
  resource budget, quick start, configuration reference, development, FAQ-ish
  troubleshooting) — resume-ready.
- **Packaging**: added `requirements.txt` and `requirements-dev.txt` (torch/NeMo
  intentionally left to index URLs per README).
- **Testing**: added `tests/test_dictator.py` (22 unit tests, offline, mocks all
  heavy deps). All pass; `pytest -q` < 0.1 s.
- **Linting**: `ruff` passes cleanly.
- **CI**: added `.github/workflows/ci.yml` (lint, matrix tests on 3.10–3.12,
  shellcheck + syntax, Hadolint on Dockerfile).

### Added
- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`.

### Fixed
- Race condition between hotkey handler and worker thread: audio is captured and
  handed off under lock; only transcription/LLM runs off-thread.
- Docker compose env vars (`OLLAMA_URL`, `OLLAMA_MODEL`, etc.) are now actually
  consumed (module reads `os.environ`).
- More resilient device handling when keyboards are unplugged.

### Verified
- End-to-end STT pipeline confirmed working: Parakeet + Ollama produces correct
  punctuated output in ~0.6 s on target hardware.
- Import time < 0.2 s; no model loaded on import; hotkey combo detection
  correct; clipboard works via pyperclip (Wayland).
