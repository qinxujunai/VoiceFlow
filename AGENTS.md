# AGENTS.md -- VoiceFlow

## Project Identity

VoiceFlow is a Windows local-first dictation layer. Press **F2** or a configured mouse side button to start recording, press again to stop, and cleaned text is copied to the clipboard and pasted at the current cursor. Press **Esc** to cancel.

The current target is stability: no orphan processes, working tray exit, complete final transcription, clipboard fallback, and truthful docs.

## Run

```bat
start.bat
venv\Scripts\python.exe src\main.py
```

## Verify

Do not use `src\*.py` with `py_compile` on Windows; Python does not expand that glob.

```bat
venv\Scripts\python.exe -m py_compile src\main.py src\overlay_webview.py src\hotkey_manager.py src\output_handler.py src\text_cleaner.py
venv\Scripts\python.exe -m pytest tests -q
venv\Scripts\python.exe test_integration.py
```

## Architecture

```text
src/
  main.py              # orchestration, lifecycle, streaming preview
  hotkey_manager.py    # keyboard + pynput mouse side buttons
  recording_session.py # recording lifecycle
  audio_capture.py     # sounddevice microphone adapter
  transcriber.py       # sherpa-onnx ASR
  vocabulary.py        # layered dictionary/corrections
  text_cleaner.py      # deterministic cleanup
  output_handler.py    # clipboard first, then Ctrl+V
  history_store.py     # logs/history.jsonl
  overlay_webview.py   # PyQt overlay + tray menu
  overlay.html         # centered pill UI
  tray_icon.py         # runtime status tray icon
```

## Product Rules

- Offline by default. Do not add cloud ASR, cloud LLM, or hidden network calls.
- Never lose text. If text exists, it must remain in clipboard and `logs/history.jsonl`.
- Do not restore the previous clipboard after dictation.
- Final output must use the complete stopped audio buffer; streaming preview is only preview.
- Streaming preview may be throttled for long recordings, but final transcription must remain complete.
- Default triggers are `f2`, `xbutton1`, and `xbutton2`; avoid adding more default keys.
- Tray right-click menu must keep a working `退出` action.
- Keep the overlay small, centered, and quiet.
- If docs disagree with runtime behavior, fix the docs or the code immediately.

## Hotkeys

```yaml
hotkeys:
  push_to_talk: ["f2", "xbutton1", "xbutton2"]
  cancel: "escape"
```

Keyboard keys use the `keyboard` package and are suppressed. Mouse side buttons use `pynput` and are not suppressed.

## Output Contract

The output path is:

```text
clean text -> pyperclip.copy(text) -> Ctrl+V -> history.jsonl
```

This is intentional. Even if `Ctrl+V` lands nowhere, the user can manually paste.

## Vocabulary

Primary files:

- `knowledge-base/builtin-ai.txt`
- `knowledge-base/corrections.txt`
- `knowledge-base/user-dictionary.txt`
- `knowledge-base/phrases.txt`

Legacy files still load for compatibility:

- `knowledge-base/ai-terms.txt`
- `knowledge-base/company-terms.txt`
- `knowledge-base/user-custom.txt`

Use `wrong=correct` only in correction files.

## Packaging

- `scripts\generate_icon.py` creates `assets\voiceflow.ico`.
- `scripts\create_shortcut.ps1` creates a desktop shortcut.
- `VoiceFlow.spec` is the windowed release build. It includes overlay/config/knowledge-base/icon, but not large model files.

## Coding Rules

- Keep changes narrow and tied to the product contract.
- Prefer readable state transitions over clever async behavior.
- Do not reintroduce clipboard restore.
- Do not add default shortcut keys that interfere with normal typing.
- Do not reintroduce overcomplicated processing animations unless they are tied to a measurable state.
