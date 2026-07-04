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
- quick ASR benchmark
- integration test

## Product Invariants

- Final output is copied before paste is attempted.
- Streaming preview is never treated as the final source of truth unless final
  transcription is empty and preview is the only safe fallback.
- Long recording output must include the final tail.
- The previous clipboard is not restored after dictation.
- Default triggers stay single-key: `F2`, `Right Ctrl`, `xbutton1`, `xbutton2`.
- The tray `退出` action must remain functional.
- Model downloads must be visible and user-confirmed.

## Review Checklist

- README and demo assets match the current runtime behavior.
- `scripts\doctor.py` reports missing dependencies, model files, shortcuts, and
  knowledge-base files clearly.
- UI changes keep the overlay small and bounded.
- GitHub default branch is updated only after the full gate passes.
