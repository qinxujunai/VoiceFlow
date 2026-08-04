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
responsiveness bucket and rejects trigger-to-feedback P95 >= 100 ms, short
stop-to-paste P95 > 700 ms, or two-minute P95 > 2.5 seconds. Generate the
evidence on the release machine first:

```bat
venv\Scripts\python.exe scripts\measure_overlay_feedback.py --samples 20
venv\Scripts\python.exe scripts\measure_pipeline_performance.py --samples 20
```

The first command measures the real Qt paint completion. The second runs the
default ASR, text cleaner, progressive long-dictation tail, and output timing
path with deterministic audio and suppressed keyboard side effects. Stable
release approval still requires the separate real-device Windows matrix. UI
capture covers 100%, 125%, 150%, and 200% scale.

## Product Invariants

- Final output is copied before paste is attempted.
- Streaming preview is never treated as the final source of truth unless final
  transcription is empty and preview is the only safe fallback.
- Preview text is append-only, unpunctuated, fixed at a 48 ms display cadence,
  and resumes after a divergent segment reaches an endpoint.
- Long recording output must include the final tail.
- The previous clipboard is not restored after dictation.
- Default triggers stay single-key: `F2`, `Right Ctrl`, `xbutton1`, `xbutton2`.
- The tray `退出` action must remain functional.
- Model downloads must be visible and user-confirmed.

## Review Checklist

- README and the animated product demo match the current runtime states and product promise.
- The recording meter is driven by microphone RMS through a latest-only UI channel; fixed decorative waveform loops are rejected.
- `scripts\doctor.py` reports missing dependencies, model files, shortcuts, and
  knowledge-base files clearly.
- UI changes keep the overlay small and bounded.
- GitHub default branch is updated only after the full gate passes.
