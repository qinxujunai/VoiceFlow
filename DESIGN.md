# VoiceFlow Design

## Product Intent

VoiceFlow is a local-first Windows dictation layer for people who think faster than they type. The product contract is simple: press F2, speak naturally, press F2 again, and the cleaned text appears at the current cursor without losing the original speech.

The project is not constrained by earlier prototype docs. Existing code is useful only where it supports the current product direction.

## Non-Negotiables

- **F2 is the main recording key.** Esc cancels.
- **Offline first.** No network calls in the default path.
- **Low latency over heavy AI polish.** The main path uses ASR + deterministic cleanup.
- **Never lose text.** Store output attempts in local history and keep clipboard fallback.
- **Personal vocabulary is product core.** Corrections, names, product terms, and phrases must be easy to maintain.
- **The overlay is a state indicator, not a full app window.** It must stay centered, quiet, and precise.

## Current Architecture

```text
HotkeyManager
  -> RecordingSession
  -> AudioCapture
  -> Transcriber
  -> TextCleaner + Vocabulary
  -> OutputHandler
  -> HistoryStore
  -> OverlayWindow / tray icon
```

### Recording

`RecordingSession` owns the recording lifecycle. `AudioCapture` remains the hardware adapter around `sounddevice`. Background streaming is used only for preview; final output is generated from the complete stopped audio buffer.

### Recognition

SenseVoice-Small through sherpa-onnx is the default engine because it is fast, local, and light. Qwen3-ASR remains experimental until model download, runtime, and prompt/context behavior are verified in this repo.

SenseVoice does not use sherpa transducer hotwords in the current implementation. Vocabulary improvement happens through deterministic post-processing.

### Vocabulary

`Vocabulary` loads layered files from `knowledge-base`:

- `builtin-ai.txt`: curated AI/developer terms.
- `corrections.txt`: `wrong=correct` pairs.
- `user-dictionary.txt`: personal nouns and project names.
- `phrases.txt`: phrases that should survive cleanup.
- legacy `ai-terms.txt`, `company-terms.txt`, `user-custom.txt`: still loaded for compatibility.

`TextCleaner` applies corrections and formatting after ASR. It avoids broad lowercase rewrites that corrupt ordinary English words.

### Output And History

`OutputHandler` uses clipboard + Ctrl+V as the default cross-app insertion path. It returns an output status and stores the last text for repeat-paste. `HistoryStore` writes append-only JSONL entries to `logs/history.jsonl` with raw text, cleaned text, output status, timestamp, and error.

### UI

The overlay is a transparent bottom-centered band. The pill itself is centered inside the band, so short and long content expands visually from the center instead of drifting left. States:

- idle
- listening
- streaming
- processing
- success
- error
- canceled

The tray icon is generated at runtime and exposes useful background commands: show window, copy last result, repaste last result, open dictionary, quit.

## Implementation Priorities

1. **Reliability**: state transitions, final transcription, history, fallback.
2. **Visual precision**: centered pill, responsive width, clear microphone/state indicator.
3. **Vocabulary learning**: corrections and personal dictionary first; UI for editing later.
4. **Packaging**: one-click install, model checks, formal app icon.
5. **Optional intelligence**: local cleanup mode only after the base path is fast and stable.

## Verification

Required checks before claiming the app is healthy:

```bash
venv\Scripts\python.exe -m py_compile src\*.py
venv\Scripts\python.exe -m unittest discover tests -v
venv\Scripts\python.exe test_integration.py
```

Manual checks:

- Start app, confirm no JavaScript errors during initialization.
- Press F2: overlay appears bottom-centered.
- Speak, press F2: text is pasted and written to `logs/history.jsonl`.
- Press Esc while recording: overlay shows canceled and no text is output.
- Tray menu can copy and repaste the last result.

## Explicitly Out Of Default Path

- Cloud ASR or cloud LLM cleanup.
- Always-on microphone listening.
- Multiple competing recording hotkeys.
- Heavy AI rewriting that changes user intent.
