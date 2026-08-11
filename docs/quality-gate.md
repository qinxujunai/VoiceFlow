# VoiceFlow Quality Gate

VoiceFlow changes are accepted only when the runtime contract and delivery path
still match the product promise: local-first dictation, complete final output,
and recoverable text.

## Required Command

```bat
venv\Scripts\python.exe scripts\verify.py
```

This gate runs:

- runtime doctor
- Python compilation for project files
- pytest
- deterministic 500-cycle recording state test
- quick ASR benchmark with pathological-output detection enabled
- integration test

For a release candidate, run:

```bat
venv\Scripts\python.exe scripts\verify.py --release
venv\Scripts\python.exe scripts\ui_quality_gate.py
venv\Scripts\python.exe scripts\evaluate_streaming_preview.py --enforce
```

Release mode also requires at least 20 reproducible measurements in each
responsiveness bucket and rejects trigger-to-feedback P95 > 50 ms, 0-10 second
stop-to-paste P95 > 500 ms, 10-60 second P95 > 700 ms, or two-minute P95 >
2.5 seconds. Generate the
evidence on the release machine first:

```bat
venv\Scripts\python.exe scripts\measure_overlay_feedback.py --samples 20
venv\Scripts\python.exe scripts\measure_pipeline_performance.py --samples 20 --preview-samples 20
```

The first command measures the real Qt paint completion. The second runs the
default ASR, text cleaner, progressive long-dictation tail, output timing, and
the pinned bilingual preview model with deterministic audio and suppressed
keyboard side effects. Preview evidence separates model batches from the
capsule's one-character visible paint cadence and contains no recognized text.
The current release-machine evidence is recorded in
[`release-performance-evidence-2026-08-11.md`](release-performance-evidence-2026-08-11.md).
Stable release approval still requires the separate real-device Windows
matrix. UI capture covers 100%, 125%, 150%, and 200% scale.

## Product Invariants

- Final output is copied before paste is attempted.
- Streaming preview is never treated as the final source of truth unless final
  transcription is empty and preview is the only safe fallback.
- Preview text is append-only and unpunctuated. Its bounded cadence targets
  48 ms per grapheme, accelerates under backlog, and coalesces stale animation
  after a 600 ms hard lag.
- Live draft and authoritative text use one visual color; provenance remains an
  internal state distinction. Recording bars stay red until recording ends.
- Long recording output must include the final tail.
- The previous clipboard is not restored after dictation.
- Default triggers stay single-key: `F2`, `Right Ctrl`, `xbutton1`, `xbutton2`.
- The tray `退出` action must remain functional.
- Ordinary settings must not expose model selection, download, repair, or
  switching. Candidate models remain internal quality-gate inputs.

## Review Checklist

- README and the animated product demo match the current runtime states and product promise.
- The recording meter is driven by microphone RMS through a latest-only UI channel; fixed decorative waveform loops are rejected.
- `scripts\doctor.py` reports missing dependencies, model files, shortcuts, and
  knowledge-base files clearly.
- UI changes keep the overlay small and bounded.
- GitHub default branch is updated only after the full gate passes.
