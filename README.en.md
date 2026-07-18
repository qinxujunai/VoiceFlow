# VoiceFlow

> Offline, immediate, never lost.

[![中文](https://img.shields.io/badge/中文-切换-6B7280)](README.md)
[![English](https://img.shields.io/badge/English-Current-111827)](README.en.md)

[![Platform](https://img.shields.io/badge/platform-Windows-0078D4)](#)
[![Local First](https://img.shields.io/badge/local--first-no%20cloud-2EA44F)](#)
[![ASR](https://img.shields.io/badge/ASR-sherpa--onnx%20offline-6F42C1)](#)
[![Tests](https://img.shields.io/badge/tests-pytest-0A7)](#)

![VoiceFlow dictation settings captured from the running app](docs/screenshots/settings-dictation.png)

<table>
  <tr>
    <td align="center"><img src="docs/screenshots/overlay-recording.png" alt="Recording state driven by real microphone energy"><br><sub>Listening: the meter follows real microphone energy</sub></td>
    <td align="center"><img src="docs/screenshots/overlay-streaming.png" alt="Bounded live preview state"><br><sub>Live preview: latest tail only, with no render backlog</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screenshots/overlay-finalizing.png" alt="Finalizing state after stop"><br><sub>After stop: complete the final audio tail</sub></td>
    <td align="center"><img src="docs/screenshots/overlay-completed.png" alt="Recoverable completion state"><br><sub>Complete: text is in the clipboard and local history</sub></td>
  </tr>
</table>

VoiceFlow is local-first dictation for Windows. It treats speech as live input,
not as a file to process: press `F2`, `Right Ctrl`, or a mouse side button,
speak, press again, and the final text is copied to the clipboard before
VoiceFlow attempts to paste it at the current cursor.

The product contract is simple: **recognized text must not be lost.** If the
target app does not accept paste, the text is still recoverable from the
clipboard and local history.

VoiceFlow has no hidden cloud ASR calls and no default LLM correction layer.
Codex is used for engineering workflow support, not as a runtime dependency.

## Why It Matters

- **System input layer**: designed for real cursor-level dictation across apps.
- **Final output is truth**: streaming preview is only feedback.
- **Truthful input feedback**: the 18 px meter follows real microphone RMS instead of playing a decorative loop, and its UI channel keeps only the latest frame.
- **Clipboard-first recovery**: paste can fail; text should not disappear.
- **Long dictation support**: stable segments are cached while recording, with a
  final tail pass on stop.
- **Local delivery path**: bootstrap can repair Python dependencies, logs, and
  shortcuts; model download is visible and user-confirmed.
- **Quality gate**: doctor, compile checks, pytest, benchmark, and integration
  are wired into `scripts\verify.py`.

## Tech Stack

- Python 3.12 on Windows
- PySide6 + Qt WebEngine on the LGPL release path
- `sherpa-onnx` adapters for SenseVoice, Qwen3-ASR, and Fun-ASR Nano
- Offline Silero VAD before ASR suppresses silence hallucinations without deleting genuine one-word dictation
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

Live preview work is duration-independent: it reads a bounded recent audio
window, releases PCM after stable segments are cached, drops stale recognition
results, and coalesces UI updates into a one-slot latest-only queue. The final
path still covers the complete recording.

## Verification

```bat
venv\Scripts\python.exe scripts\verify.py
```

The gate runs doctor, py_compile, pytest, 500 deterministic lifecycle cycles, a
quick ASR benchmark, and integration. `scripts\verify.py --release` also
enforces recorded responsiveness evidence.

Model promotion is handled by `scripts\evaluate_asr.py`. It writes per-sample
JSONL results and refuses promotion when coverage or any hard product gate is
missing. Runtime audio and private evaluation data stay local.

## Maintenance

- [Quality gate](docs/quality-gate.md)
- [ASR evaluation plan](docs/asr-evaluation-plan.md)
- [Release checklist](docs/release-checklist.md)
