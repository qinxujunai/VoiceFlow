# VoiceFlow

> Local-first dictation for Windows. Press a key, speak, and final text lands at the cursor with clipboard-first recovery.

[![中文](https://img.shields.io/badge/中文-切换-6B7280)](README.md)
[![English](https://img.shields.io/badge/English-Current-111827)](README.en.md)

[![Platform](https://img.shields.io/badge/platform-Windows-0078D4)](#)
[![Local First](https://img.shields.io/badge/local--first-no%20cloud-2EA44F)](#)
[![ASR](https://img.shields.io/badge/ASR-sherpa--onnx%20%2B%20SenseVoice-6F42C1)](#)
[![Tests](https://img.shields.io/badge/tests-pytest-0A7)](#)

![VoiceFlow demo](docs/voiceflow-demo.svg)

VoiceFlow is a Windows local-first dictation layer. Press `F2`, `Right Ctrl`,
or a mouse side button to start recording, press again to stop, and the final
text is copied to the clipboard before VoiceFlow attempts to paste it at the
current cursor.

The product contract is simple: **recognized text must not be lost.** If the
target app does not accept paste, the text is still recoverable from the
clipboard and local history.

VoiceFlow has no hidden cloud ASR calls and no default LLM correction layer.
Codex is used for engineering workflow support, not as a runtime dependency.

## Why It Matters

- **System input layer**: designed for real cursor-level dictation across apps.
- **Final output is truth**: streaming preview is only feedback.
- **Clipboard-first recovery**: paste can fail; text should not disappear.
- **Long dictation support**: stable segments are cached while recording, with a
  final tail pass on stop.
- **Local delivery path**: bootstrap can repair Python dependencies, logs, and
  shortcuts; model download is visible and user-confirmed.
- **Quality gate**: doctor, compile checks, pytest, benchmark, and integration
  are wired into `scripts\verify.py`.

## Tech Stack

- Python 3.12 on Windows
- PyQt6 + PyQt6 WebEngine
- `sherpa-onnx` with local SenseVoice ONNX models
- `sounddevice`, `keyboard`, and `pynput`
- `pyperclip` plus simulated `Ctrl+V`
- PyInstaller for packaged builds

GitHub's language bar reports source-code composition. Speech language is
configured separately in `config.yaml`; the default is `zh`, with model-backed
settings such as `zh`, `en`, and `auto`.

## Quick Start

```bat
git clone https://github.com/qinxujunai/VoiceFlow.git
cd VoiceFlow
start.bat
```

`start.bat` validates the virtual environment, installs dependencies when
needed, creates logs, restores the desktop shortcut, and opens a visible setup
path if the local ASR model is missing.

Models are intentionally kept out of Git. To download the default model:

```bat
venv\Scripts\python.exe scripts\download_models.py
```

## Shortcuts

| Key | Action |
| --- | --- |
| `F2` | Start / stop dictation |
| `Right Ctrl` | Start / stop dictation |
| `xbutton1` / `xbutton2` | Start / stop with mouse side buttons |
| `Esc` | Cancel current recording |

## Architecture

```text
Hotkey
  -> RecordingSession
  -> AudioCapture
  -> Transcriber
  -> TextCleaner + Vocabulary
  -> Clipboard
  -> Ctrl+V
  -> logs/history.jsonl
```

For short recordings, VoiceFlow runs one complete final pass. For long
recordings, it caches stable final segments while recording, then transcribes
the remaining tail on stop and de-duplicates transcript joins.

## Verification

```bat
venv\Scripts\python.exe scripts\verify.py
```

The gate runs doctor, py_compile, pytest, a quick ASR benchmark, and integration.

## Maintenance

- [Quality gate](docs/quality-gate.md)
- [ASR evaluation plan](docs/asr-evaluation-plan.md)
- [Release checklist](docs/release-checklist.md)
