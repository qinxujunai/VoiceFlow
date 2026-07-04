# VoiceFlow v0.1.0

VoiceFlow v0.1.0 is the first source release of the local-first Windows dictation layer.

## What It Delivers

- Press `F2`, `Right Ctrl`, or a mouse side button to start and stop dictation.
- Final text is copied to the clipboard before VoiceFlow attempts to paste it at the current cursor.
- If paste does not land in the target app, the text remains recoverable from the clipboard and local history.
- The overlay stays small and quiet: red waveform while recording, green check when final text is ready.
- The launcher validates the Python environment, repairs a broken venv, restores logs, and recreates the desktop shortcut.

## Product Contract

VoiceFlow is offline by default. There are no hidden cloud ASR calls and no default LLM correction path. Streaming preview is only feedback; final output comes from the complete final transcription path.

## Verify

```bat
venv\Scripts\python.exe scripts\verify.py
```

This release is source-first. Large local model files and packaged binaries are intentionally kept outside GitHub until the packaging flow is published.
