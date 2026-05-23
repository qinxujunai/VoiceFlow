# AGENTS.md -- VoiceFlow

## Project Identity

VoiceFlow is a Windows local-first voice input layer. Press **F2** (or mouse upper side button / any configured key) to start recording, press again to stop, and cleaned text is pasted at the current cursor. Press **Esc** to cancel.

Treat older docs as historical context only. Current product target: reliable system-level dictation utility with low latency, centered overlay, personal vocabulary, and no lost text.

## Run

```bash
start.bat
# or
venv\Scripts\python.exe src\main.py
```

## Verify

```bash
venv\Scripts\python.exe -m py_compile src\*.py
venv\Scripts\python.exe -m pytest tests -q
venv\Scripts\python.exe test_integration.py
```

## Architecture

```text
src/
+-- main.py              # orchestration + streaming loop with energy gate
+-- recording_session.py # recording lifecycle
+-- audio_capture.py     # microphone adapter
+-- transcriber.py       # sherpa-onnx ASR (SenseVoice int8, num_threads=6)
+-- vocabulary.py        # layered dictionary/corrections
+-- text_cleaner.py      # clean() for final, clean_streaming() for live display
+-- output_handler.py    # paste + fallback
+-- history_store.py     # logs/history.jsonl (append-only JSONL)
+-- ui_state.py          # overlay state enum + display metadata
+-- overlay_webview.py   # PyQt overlay + tray, signal bridge (thread-safe)
+-- overlay.html         # centered pill UI (lerp ticker + spinner + sound bars)
+-- tray_icon.py         # runtime tray icon generation (multi-size QIcon)
```

## Key Design Decisions

### Recording toggle (race-condition free)
A synchronous `_actively_recording` flag guards start/stop/cancel.
Set True at the TOP of `_on_record_start` before any slow operations.
Checked by `_on_record_stop` and `_on_record_cancel`.
Prevents the F2 double-press race where stop fires before start completes.

### Streaming loop
- Delta-gated: tracks `last_len`, transcribes only when >= 0.6s of NEW audio.
- Energy-gated: computes RMS of most recent 0.5s. Skips if RMS < 0.008 (silence).
- Display: `updateStreaming()` in JS strips ALL punctuation. Final `clean()` preserves it.
- Reference: WeChat voice input (clean flow during recording, punctuation on stop).

### Final transcription
Always full-buffer `transcriber.transcribe()` on stop. No cache shortcut.
Guarantees no truncated text. Cost: one call (0.2--0.8s on Ryzen 7 5800H).

### Processing spinner
If final text differs from streaming cache, `showCompleting()` locks pill width,
switches sound bars to sequential pulse (`spinPulse` keyframes), then resolves.
If cache is complete: paste immediately, no spinner shown.

### Ticker lerp
`updateTickerOffset()` uses `requestAnimationFrame` lerp loop
(`_tickerCurrent` -> `_tickerTarget` at 0.32 factor per frame). No CSS transition.
Left-side CSS gradient mask fades text on overflow.

### Overlay visual stack
- 34px pill, max 260px, centered at screen bottom
- 3-layer box-shadow (0.5px edge + 1px tight + 3px ambient)
- Organic 3-bar sound animation (bar1/bar2/bar3 independent keyframes)
- `font-weight: 470` for crisp CJK rendering on Windows
- Success spring bounce (`confirm` keyframe) on paste

### ASR tuning
- Model: SenseVoice-Small INT8 (239 MB). RTF ~0.03 on Ryzen 7 5800H.
- `num_threads=6` (8-core CPU, leaves headroom for UI thread).
- Hotwords: post-processing via `text_cleaner.py` (SenseVoice lacks native contextual biasing).
- Punctuation filter: `clean()` returns empty if <=1 meaningful char remains (catches silence hallucinations like "I" or ".").

## Product Rules

- Default path must be offline. No network, no cloud ASR, no LLM in default flow.
- Config supports multiple PTT keys: `["f2", "xbutton1"]` format in `config.yaml`.
- Mouse keys (xbutton1/xbutton2) are NOT suppressed; keyboard keys ARE suppressed.
- Never lose text: paste failure -> clipboard fallback + history.
- Overlay always centered. Pill expands from center outward, never drifts left.
- Streaming display: no punctuation (stripped in JS). Final output: punctuation via `clean()`.
- Prefer small, testable modules. Do not bloat `main.py`.
- If docs disagree with runtime code, fix the docs or the code.

## Hotkey Config

```yaml
hotkeys:
  push_to_talk: ["f2", "xbutton1"]   # any key toggles recording
  cancel: "escape"
```

Supported: `f1`--`f12`, `xbutton1`, `xbutton2`, `right ctrl`, etc.
Full list in `keyboard` library documentation.

## Vocabulary

Primary files:
- `knowledge-base/builtin-ai.txt`
- `knowledge-base/corrections.txt`
- `knowledge-base/user-dictionary.txt`
- `knowledge-base/phrases.txt`

Legacy files loaded for compatibility:
- `knowledge-base/ai-terms.txt`
- `knowledge-base/company-terms.txt`
- `knowledge-base/user-custom.txt`

Use `wrong=correct` format only in correction files.

## Coding Rules

- Think before coding. State assumptions for risky changes.
- Keep changes surgical and tied to the requested outcome.
- Match existing style unless blocking the product goal.
- Add tests for pure logic and bug fixes.
- Prefer direct runtime verification over visual guessing.
- When editing `overlay.html`: JS lerp handles ticker offset; CSS transitions on `.ticker-text` are intentionally removed.
- `clean_streaming()` strips punctuation for display; `clean()` preserves punctuation for output. Do not swap them.
