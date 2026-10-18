# Contributing to Dictator

Thanks for your interest in Dictator. Contributions are welcome!

## Ground rules

- **Small, focused PRs:** one logical change per pull request.
- **No network calls in unit tests:** tests must run offline. The ASR model
  loads lazily, so importing the module has no side effects.
- **Follow the code style:** we use `ruff` for linting and formatting. Run
  `ruff check .` and `ruff format .` before committing.
- **Stay deterministic:** Ollama calls in production use `temperature: 0.0` and
  preserve words verbatim. Don't change that behavior without discussion.
- **Keep paths portable:** do not hardcode personal directories. For desktop
  files, use the `@PROJECT_DIR@` placeholder and resolve at install time.

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest        # all tests offline
ruff check .
ruff format .
```

## Testing

- **Unit tests** cover: hotkey parsing, evdev key mapping, queue draining,
  transcription short-circuit guard, Ollama punctuation behavior, and the
  hotkey state machine. They mock heavy dependencies (no GPU, no Ollama).
- **Manual end-to-end**: record a short phrase and confirm transcription +
  punctuation + clipboard round-trip.

## CI

GitHub Actions run lint (ruff), tests (3.10–3.12), shell syntax + ShellCheck,
and Hadolint on Dockerfile. All checks must pass.

## Reporting issues

Include:
- Linux distro / Wayland session details
- NVIDIA driver / GPU (`nvidia-smi`)
- Ollama version + models (`ollama list`)
- Relevant logs (`~/.local/share/dictator/dictator.log`)
- Minimal steps to reproduce (including hotkey used)

## Code of conduct

Be kind, respectful, and assume good intent. No harassment or discriminatory
language.
