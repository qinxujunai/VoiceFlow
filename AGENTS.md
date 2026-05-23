# AGENTS.md -- VoiceFlow

## Project Identity

VoiceFlow is a Windows local-first dictation layer. Press **F2**, **Right Ctrl**, or a mouse side button to start recording, press again to stop, and cleaned text is copied to the clipboard and pasted at the current cursor. Press **Esc** to cancel.

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
- Default triggers are `f2`, `right_ctrl`, `xbutton1`, and `xbutton2`. Do not add combo keys as defaults — suppress=True blocks the individual keys from normal use.
- Tray right-click menu must keep a working `退出` action.
- Keep the overlay small, centered, and quiet.
- If docs disagree with runtime behavior, fix the docs or the code immediately.

## Hotkeys

```yaml
hotkeys:
  push_to_talk: ["f2", "xbutton1", "xbutton2"]
  cancel: "escape"
```

All push-to-talk keys are single keys — no combo keys. Keyboard keys use the `keyboard` package and are suppressed. Mouse side buttons use `pynput` and are not suppressed.

### Key Reference

| Key | Type | Notes |
|---|---|---|
| `f2` | keyboard | Windows default |
| `xbutton1` | mouse | side button (back) |
| `xbutton2` | mouse | side button (forward) |
| `escape` | keyboard | cancel recording |

### Right Ctrl Implementation

`right_ctrl` is detected via `pynput.keyboard.Listener`, not the `keyboard` library. pynput uses virtual key codes (`VK_RCONTROL` = 0xA3) which are distinct from `VK_LCONTROL` even on keyboards where left/right Ctrl share the same scan code. The `keyboard` library cannot do this because it relies on scan codes only. Since right ctrl is rarely used in typing combos, no suppression is needed — the key press itself produces no character output, and the 0.5s debounce prevents accidental double-fires when used in combinations.

### Anti-pattern: Combo Keys

Never add combo keys like `ctrl+shift+space` via `keyboard.add_hotkey` with `suppress=True`. The `keyboard` library will suppress *every individual key in the combo* (Ctrl, Shift, Space), breaking copy/paste, input methods, and normal typing.

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

## Troubleshooting

- **Desktop shortcut runs stale code:** The shortcut points to `start.bat` which uses source code directly. But if an old process is still running, it holds the old config in memory. After changing `config.yaml` or `hotkey_manager.py`, kill all Python processes before restarting:
  ```powershell
  Stop-Process -Name python -Force
  ```
- **`dist/VoiceFlow.exe` is a frozen snapshot.** If the desktop shortcut ever points to the exe instead of `start.bat`, the exe must be rebuilt with `venv\Scripts\pyinstaller.exe VoiceFlow.spec` to pick up config changes.


## Craft Standard

Think, then code. Every visual change must answer: would this belong in a native iOS or macOS app? Animations convey state, not decoration. Whitespace is intentional. Default to subtraction — remove before you add. The reference is not competing dictation tools; it is the restraint of Voice Memos, Notes, and Messages.

Match the existing code as if the same person wrote every line. Indentation, naming, control flow, comment style — follow the neighbors exactly. Before committing, re-read your diff and delete any line not traceable to the stated goal. Surgical, not sweeping.


## Known Issues

- **Pill flash on new recording.** After a recording ends and the pill hides, starting a new recording may briefly show the pill at the previous width before it snaps to the minimum listening width. Root cause involves the timing between Qt window visibility and WebEngine JavaScript execution. Future investigation should focus on ensuring the pill CSS `--target-width` is reset synchronously before `window.show()`.

- **Final text overwritten by streaming preview.** The streaming thread could send one last `updateStreaming` after `_stop_streaming()` returned, overwriting the final transcription shown by `show_result`. Fixed: `_start_streaming` saves the thread as `self._stream_thread`; `_stop_streaming` now calls `self._stream_thread.join(timeout=2.0)` to wait for the streaming loop to fully exit before proceeding to final transcription and result display.

## Coding Rules

- Keep changes narrow and tied to the product contract.
- Prefer readable state transitions over clever async behavior.
- Do not reintroduce clipboard restore.
- Do not add default shortcut keys that interfere with normal typing.
- Do not reintroduce overcomplicated processing animations unless they are tied to a measurable state.
