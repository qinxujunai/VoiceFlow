# VoiceFlow Design

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](docs/README.md).

## Product Contract

VoiceFlow is a local-first Windows dictation layer. Press F2, Right Ctrl or a mouse side button, speak, and press again to finish. Final text is copied before one paste attempt; unverified insertion retains recovery guidance and local history.

The product is intentionally small. Reliability, low latency, and "never lose text" matter more than decorative UI or automatic rewriting.

## Non-Negotiables

- Default path is offline: no cloud ASR, no cloud LLM, no hidden network work.
- Text output is first copied to the clipboard, then pasted.
- The app must not restore the old clipboard after dictation.
- Final output must cover the complete stopped audio, not only the streaming preview.
- Streaming preview may be throttled for long recordings, but final transcription must remain complete.
- Tray menu must expose a working Exit action.
- Default triggers are F2, Right Ctrl, xbutton1, and xbutton2. Do not add more default keys unless there is a strong reason.

## Current Flow

```text
HotkeyManager
  -> AppController / VoiceInputSystem
  -> RecordingSession / supervised audio worker
  -> separate online preview and authoritative ASR workers
  -> safe cleanup / visible dictionary corrections / bounded punctuation worker
  -> OutputHandler
  -> HistoryStore
  -> OverlayWindow / tray icon
```

Recording starts on toggle. The preview worker owns one online stream per session
and receives each PCM sample once. It emits confirmed append deltas; do not
retranscribe overlapping recent-audio windows through the final recognizer.
The Qt process does not load native audio/ASR engines. Preview remains feedback,
not the source of truth; see [ADR-004](docs/decisions/ADR-004-supervised-runtime-boundary.md).

Short recordings run final recognition over the complete stopped audio buffer. Long recordings progressively transcribe stable audio segments during recording and only transcribe the remaining tail on stop. The assembled final output still covers the complete audio. If final recognition returns empty while preview had text, the preview text is used as a safety fallback.

## Recognition

Default model is currently SenseVoice-Small int8 through sherpa-onnx. It remains the conservative baseline until a complete Model Lab run promotes a challenger.

Before any engine receives audio, an energy floor and the bundled Silero VAD must confirm speech presence. Punctuation-only output is not user text; lexical one-character dictation remains valid.

SenseVoice, Qwen3-ASR 0.6B int8, and Fun-ASR Nano int8 share the `EngineAdapter` contract. Model assets are pinned by revision, size, license, and SHA-256. `scripts/evaluate_asr.py` owns scoring, hard rejection, reports, and promotion; no model is selected by popularity.

Vocabulary and corrections are deterministic post-processing. SenseVoice hotwords are not wired through sherpa transducer hotwords in this project.

## Output And History

`OutputHandler` copies text to clipboard before attempting `Ctrl+V`. This guarantees that a user can manually paste even when focus is not in a text field.

`HistoryStore` writes JSONL entries to
`%LOCALAPPDATA%\VoiceFlow\logs\history.jsonl`. Each successful text output
should have raw text, cleaned text, output status, and timestamp.

## UI

The overlay is a compact native Qt pill, not a full editor. Its mark and text
regions remain stable. WebEngine/QML/Quick are excluded from Windows releases.

- listening / streaming: three-bar waveform and live text
- processing: spinner in the left mark while preserving the last visible text and width
- final: replace the draft with the complete authoritative text in place
- confirmed insertion: fade silently; a dispatched paste is not confirmation
- unverified dispatch / clipboard fallback: show `已复制到剪贴板`; durable recovery: `已保存`
- error / canceled: brief state, then hide

Keep the pill centered as a window, with left-aligned text and bounded staged
width growth. Append characters once, normally at 48 ms cadence, accelerate
under backlog and coalesce after the 600 ms lag limit. Do not recenter each
character, replay text or apply horizontal transforms. Stop freezes the audio
boundary and rejects late preview updates before the final text replaces it.

Text on screen follows iOS dictation: each newly appended glyph fades in over
140 ms (a hard catch-up fades its whole run once); when the start is cropped,
the leading 18 px fade out instead of cutting a glyph; the final text either
completes the draft in place or, when it differs, the draft fades out and the
final fades in (160 ms, no overlap, no movement). Reduced motion and high
contrast render statically.

Settings have one draft and one save transaction, with feedback in the content
area. The window follows macOS System Settings: a light sidebar, grouped white
cards of label/control rows on a soft grey canvas, a fixed save bar, text
buttons for secondary actions and red for destructive ones. Closing settings hides the window; the tray remains available. Vocabulary
supports visible selection and undo. There is no independent Trial recorder.

The tray icon is generated at runtime for status. The application/shortcut icon is `assets/voiceflow.ico`.

## Packaging

`start.bat` remains the development launcher.
`scripts/create_shortcut.ps1` creates a source-mode desktop shortcut for
maintainers. Installed builds use the Start menu shortcut created by Inno.

`VoiceFlow.spec` produces a PySide6 onedir build so Qt libraries remain dynamically replaceable and startup avoids one-file extraction. `installer/VoiceFlow.iss` produces a per-user installer. Model inclusion is a separate release decision gated by Model Lab results and redistribution terms.

The 0.3.9 Windows installer includes the pinned SenseVoice final recognizer,
bilingual online preview, bounded Chinese punctuation model and Silero VAD with
their runtime files and notices. They serve separate roles, not a user-facing
model selector. User configuration, history, vocabulary, logs and downloaded
models live outside the install directory under `%LOCALAPPDATA%\VoiceFlow`.
See [release verification](docs/release-validation-0.3.9.md) and the
[documentation index](docs/README.md) for dated evidence and limits.

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
