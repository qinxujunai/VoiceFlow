# AGENTS.md — VoiceFlow

## Project Identity

VoiceFlow is a Windows local-first voice input layer. Press **F2** to start recording, press **F2** again to stop, and cleaned text is pasted at the current cursor. Press **Esc** to cancel.

Treat older docs as historical context only. The current product target is a reliable system-level dictation utility: low latency, centered overlay, personal vocabulary, and no lost text.

## Run

```bash
start.bat
# or
venv\Scripts\python.exe src\main.py
```

## Verify

```bash
venv\Scripts\python.exe -m py_compile src\*.py
venv\Scripts\python.exe -m unittest discover tests -v
venv\Scripts\python.exe test_integration.py
```

## Architecture

```text
src/
├── main.py              # orchestration
├── recording_session.py # recording lifecycle
├── audio_capture.py     # microphone adapter
├── transcriber.py       # sherpa-onnx ASR
├── vocabulary.py        # layered dictionary/corrections
├── text_cleaner.py      # deterministic cleanup
├── output_handler.py    # paste + fallback
├── history_store.py     # logs/history.jsonl
├── ui_state.py          # overlay states
├── overlay_webview.py   # PyQt overlay + tray
├── overlay.html         # centered pill UI
└── tray_icon.py         # runtime tray icon generation
```

## Product Rules

- F2 is the only primary recording key. Do not add extra recording modes without a strong reason.
- Default path must be offline. Do not add network calls, cloud ASR, or LLM cleanup to the default flow.
- Do not use LLM rewriting in the main path. Deterministic cleanup and vocabulary corrections come first.
- Never lose recognized text. If paste fails, preserve text in clipboard/history and show a short error.
- Keep the overlay centered. The pill should expand visually from the center and never drift left as text grows.
- Prefer small, testable modules over adding more orchestration logic to `main.py`.
- If docs disagree with runtime code, fix the docs or the code; do not let fake features linger.

## Vocabulary

Primary files:

- `knowledge-base/builtin-ai.txt`
- `knowledge-base/corrections.txt`
- `knowledge-base/user-dictionary.txt`
- `knowledge-base/phrases.txt`

Legacy files are still loaded for compatibility:

- `knowledge-base/ai-terms.txt`
- `knowledge-base/company-terms.txt`
- `knowledge-base/user-custom.txt`

Use `wrong=correct` only in correction files.

## Coding Rules

- Think before coding. State assumptions for risky changes.
- Keep changes surgical and tied to the requested outcome.
- Match existing style unless the local code is blocking the product goal.
- Add tests for pure logic and bug fixes.
- Prefer direct runtime verification over visual guessing.
