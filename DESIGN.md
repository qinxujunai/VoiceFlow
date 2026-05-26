# VoiceFlow Design

## Product Contract

VoiceFlow is a local-first Windows dictation layer. Press F2 or a mouse side button, speak, press again, and text appears where the cursor is. If paste cannot land in an input field, the text must remain in the clipboard and local history.

The product is intentionally small. Reliability, low latency, and "never lose text" matter more than decorative UI or automatic rewriting.

## Non-Negotiables

- Default path is offline: no cloud ASR, no cloud LLM, no hidden network work.
- Text output is first copied to the clipboard, then pasted.
- The app must not restore the old clipboard after dictation.
- Final output must cover the complete stopped audio, not only the streaming preview.
- Streaming preview may be throttled for long recordings, but final transcription must remain complete.
- Tray menu must expose a working Exit action.
- Default triggers are F2 plus xbutton1/xbutton2. Do not add more default keys unless there is a strong reason.

## Current Flow

```text
HotkeyManager
  -> VoiceInputSystem
  -> RecordingSession
  -> AudioCapture
  -> Transcriber
  -> TextCleaner + Vocabulary
  -> OutputHandler
  -> HistoryStore
  -> OverlayWindow / tray icon
```

Recording starts on toggle. A background thread updates the overlay with preview text. For long dictation, preview transcription uses only the most recent audio window and refreshes at a bounded interval so it cannot dominate CPU time. Preview remains UI feedback, not the source of truth.

Short recordings run final recognition over the complete stopped audio buffer. Long recordings progressively transcribe stable audio segments during recording and only transcribe the remaining tail on stop. The assembled final output still covers the complete audio. If final recognition returns empty while preview had text, the preview text is used as a safety fallback.

## Recognition

Default model is SenseVoice-Small int8 through sherpa-onnx. It is the current conservative default for local Chinese and mixed Chinese-English dictation on Windows CPU.

Qwen3-ASR stays experimental until `scripts/benchmark_models.py` proves a better local tradeoff for load time, RTF, stability, and domain vocabulary.

Vocabulary and corrections are deterministic post-processing. SenseVoice hotwords are not wired through sherpa transducer hotwords in this project.

## Output And History

`OutputHandler` copies text to clipboard before attempting `Ctrl+V`. This guarantees that a user can manually paste even when focus is not in a text field.

`HistoryStore` writes JSONL entries to `logs/history.jsonl`. Each successful text output should have raw text, cleaned text, output status, and timestamp.

## UI

The overlay is a compact bottom-centered pill. It is a state indicator, not a full editor. The left mark region and right text region stay stable so waveform, spinner, checkmark, and text never stack on top of each other:

- listening / streaming: three-bar waveform and live text
- processing: spinner in the left mark while preserving the last visible text and width
- done: checkmark plus short completion text, then hide/reset
- error / canceled: brief state, then hide

The pill should remain visually centered. Width grows with text up to a small maximum, and long text scrolls with a left fade.

The tray icon is generated at runtime for status. The application/shortcut icon is `assets/voiceflow.ico`.

## Packaging

`start.bat` remains the development launcher. `scripts/create_shortcut.ps1` creates a desktop shortcut for daily use.

`VoiceFlow.spec` is the release build configuration. It uses a windowed exe, includes overlay/config/knowledge-base/icon, and intentionally does not bundle large model files.

## Verification

```bat
venv\Scripts\python.exe -m py_compile src\main.py src\overlay_webview.py src\hotkey_manager.py src\output_handler.py src\text_cleaner.py
venv\Scripts\python.exe -m pytest tests -q
venv\Scripts\python.exe test_integration.py
```

Manual checks:

- Start app, verify tray icon appears.
- Right-click tray icon and click Exit; no VoiceFlow Python process should remain.
- Dictate into a text field; text should paste quickly and remain in clipboard.
- Dictate with no text field focused; text should still remain in clipboard.
- Dictate a long passage; final output should include the end of the speech.
