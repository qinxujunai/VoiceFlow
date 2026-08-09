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
venv\Scripts\python.exe scripts\verify.py
```

Individual checks:

```bat
venv\Scripts\python.exe scripts\doctor.py
venv\Scripts\python.exe -m py_compile src\main.py src\overlay_webview.py src\hotkey_manager.py src\output_handler.py src\text_cleaner.py src\transcriber.py src\streaming_transcriber.py src\audio_capture.py src\recording_session.py src\vocabulary.py
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
  streaming_transcriber.py # small online ASR for capsule preview
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
- Dispatch paste only when Windows UI Automation confirms the same editable
  focus element at start and stop and UIPI integrity is compatible.
- Recovery PCM is temporary local state. Delete it only after verified
  clipboard delivery plus history, or after an explicit user delete action.
- Final output must cover the complete stopped audio; streaming preview is only preview.
- Streaming preview feeds each new PCM sample once to its own online recognizer.
- Never restore rolling-window preview through the final SenseVoice recognizer:
  overlapping retranscription causes delayed chunks and hypothesis rollback.
- Long recordings may progressively cache stable final segments during recording, but stop-time output must still include the remaining tail and cover the complete audio.
- Default triggers are `f2`, `right_ctrl`, `xbutton1`, and `xbutton2`. Do not add combo keys as defaults — suppress=True blocks the individual keys from normal use.
- Tray right-click menu must keep a working `退出` action.
- Keep the overlay small, centered, and quiet.
- If docs disagree with runtime behavior, fix the docs or the code immediately.

## Hotkeys

```yaml
hotkeys:
  push_to_talk: ["f2", "xbutton1", "xbutton2", "right_ctrl"]
  cancel: "escape"
```

All push-to-talk keys are single keys — no combo keys. `f2` uses the `keyboard` package and is suppressed. `right_ctrl` uses `pynput` so left/right Ctrl stay distinct. Mouse side buttons use `pynput` and are not suppressed.

### Key Reference

| Key | Type | Notes |
|---|---|---|
| `f2` | keyboard | Windows default |
| `right_ctrl` | keyboard | detected via pynput virtual key code |
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

Legacy migration contract:

- v1 `ai-terms.txt`, `company-terms.txt`, and `user-custom.txt` are migration
  inputs only. They must not ship or appear in `hotwords.files`.
- Runtime schema v2 removes retired seed hashes, imports non-seed additions
  from modified legacy files, and then deletes the legacy filenames.

Use `wrong=correct` only in correction files.

## Packaging

- `scripts\generate_icon.py` creates the multi-size `assets\voiceflow.ico`.
- `scripts\create_shortcut.ps1` creates a desktop shortcut.
- `VoiceFlow.spec` is the windowed onedir application build. The Inno installer adds the
  reviewed default model and its license assets.
- Windows installers belong in GitHub Releases, not GitHub Packages. Never publish an
  installer link before the matching versioned Release asset exists.
- Never publish a macOS download, badge, or compatibility claim until a separately built,
  signed, notarized, and tested macOS artifact exists.
- macOS public releases use separately named Apple Silicon and Intel disk images built from
  the same version tag as Windows. Follow `docs/platform-release-contract.md`; update the
  website only after each matching Release asset exists and its URL has been verified.

## Product Quality Gates

- Do not expose a model to ordinary users merely because it loads. It must pass pinned-asset
  verification, pathological-output checks, fixed Chinese CER, fixed English WER, latency,
  memory, license, and clean-install gates.
- Model names are implementation details. Ordinary settings expose no model selection,
  download, repair, or switching controls.
- Keep one reliable bundled default. Alternative models remain internal benchmark inputs;
  pinned download, integrity verification, and rollback code is engineering infrastructure.
- Never call a model `更准确`, `高准确` or `最佳` without same-machine, same-corpus evidence.
- Synthetic speech is useful for reproducible regression but cannot replace authorized,
  natural user speech in release accuracy claims.
- Local or cloud polishing is a second stage. Preserve raw transcription, enforce a timeout,
  and fall back to raw text on every failure. No hidden network requests.
- Streaming preview may reveal only confirmed text. Smooth visual presentation must have a
  bounded catch-up time and must be canceled before processing or final output.
- Product and website claims must map to a reproducible test, release artifact, or documented
  limitation. Remove aspirational claims that are not true in the shipped build.
- A public release requires the full verification suite, model quality evidence, packaged
  smoke, clean-machine install/upgrade/uninstall checks, license review, and exact SHA256.

## Troubleshooting

- **Desktop shortcut runs stale code:** The shortcut points to the windowed source launcher, `scripts\launch_voiceflow.pyw`, through `venv\Scripts\pythonw.exe`. It still uses source code directly. But if an old process is still running, it holds the old config in memory. After changing `config.yaml` or `hotkey_manager.py`, kill all Python processes before restarting:
  ```powershell
  Stop-Process -Name python -Force
  ```
- **`dist/VoiceFlow.exe` is a frozen snapshot.** If the desktop shortcut ever points to the exe instead of the windowed source launcher, the exe must be rebuilt with `venv\Scripts\pyinstaller.exe VoiceFlow.spec` to pick up config changes.


## Craft Standard

Think, then code. Every visual change must answer: would this belong in a native iOS or macOS app? Animations convey state, not decoration. Whitespace is intentional. Default to subtraction — remove before you add. The reference is not competing dictation tools; it is the restraint of Voice Memos, Notes, and Messages.

Match the existing code as if the same person wrote every line. Indentation, naming, control flow, comment style — follow the neighbors exactly. Before committing, re-read your diff and delete any line not traceable to the stated goal. Surgical, not sweeping.


## Regression Guards

- **Pill flash on new recording.** The old failure modes were showing the Qt window before WebEngine had reset the DOM, writing the previous final long text back into the pill before hiding, and resetting DOM while the window was still visible. Keep `prepareRecording()` as the JS-then-show entrypoint and keep hide as hide-first then offscreen `resetHidden()`. Normal stop atomically freezes the sample boundary, invalidates preview without joining workers, keeps the existing text unchanged for 350 ms, optionally changes only the mark to a spinner, replaces the draft with authoritative final text in place, and then shows minimal delivery feedback. Do not call `show_result(text)` for the normal recording stop path.

- **Streaming text replay and reverse motion.** The online recognizer owns one
  stream per recording and receives each new PCM sample exactly once. Its
  Python-to-JavaScript contract is `appendStreaming(delta, session_id)`:
  characters are appended once and are never retracted or replayed. Cadence is
  normally 48 ms, may smoothly accelerate under backlog, and must coalesce
  stale animation after the 600 ms hard lag. Do not restore rolling-window
  SenseVoice preview, full-text `updateStreaming`, common-prefix resets, or
  horizontal transforms.

- **Final text overwritten by streaming preview.** Stop freezes the microphone
  first, then invalidates the preview generation. `_stop_streaming()` may only
  signal cancellation and transfer ownership; it must not join worker threads.
  Session guards prevent stale preview work from updating settling, final, or
  delivery states. The capsule replaces the draft with final text in place,
  then shows a check with `已完成`, `已复制`, or `已保存` as appropriate. Never
  restore the character-count summary or claim paste success.

- **Recording color stability.** Draft and authoritative provenance remains internal.
  Both render in one text color, and the three recording bars remain red until recording
  actually ends. Do not couple recognition confidence to visible color changes.

- **Long dictation preview cost and coverage.** The lightweight online preview
  and SenseVoice progressive final cache use separate workers. Active recording
  PCM must not be discarded. Progressive final segments carry explicit sample
  ranges; final assembly must prove continuous coverage from sample zero to the
  frozen stop sample, otherwise retry the retained full PCM. Do not output
  preview text as final unless final transcription is empty and the explicit
  safety fallback is the only recoverable text.

## Coding Rules

- Keep changes narrow and tied to the product contract.
- Prefer readable state transitions over clever async behavior.
- Do not reintroduce clipboard restore.
- Do not add default shortcut keys that interfere with normal typing.
- Do not reintroduce overcomplicated processing animations unless they are tied to a measurable state.
