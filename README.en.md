# VoiceFlow

<p align="right">
  <a href="README.md">简体中文</a> · <strong>English</strong>
</p>

> Speak. Words land.

[![Windows quality](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml/badge.svg)](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml)
[![Download for Windows](https://img.shields.io/badge/Windows-download-087FE7)](https://github.com/qinxujunai/VoiceFlow/releases/latest)

![VoiceFlow animated demo](docs/voiceflow-demo.svg)

VoiceFlow is offline dictation for Windows. Press `F2` once to start and again
to finish. Stay in the current app while speech becomes text on your PC and
returns to the cursor.

## Why VoiceFlow

- **Entirely offline**: no account and no audio upload; dictation keeps working without a network.
- **Any text field**: stay in notes, browsers, documents, or chat while words return to the cursor.
- **Always recoverable**: if paste misses, the complete text remains in the clipboard and local history.
- **Complete audio first**: the capsule provides live feedback while the final result is produced from the complete recording.

## Download

Download the latest Windows installer from [GitHub Latest Release](https://github.com/qinxujunai/VoiceFlow/releases/latest).
The installer includes the default offline model and does not require Python.

Requirements: Windows 10 / 11 x64 and a working microphone.

## Controls

| Key | Action |
| --- | --- |
| `F2` | Start / stop dictation |
| `Right Ctrl` | Start / stop dictation |
| `xbutton1` / `xbutton2` | Start / stop with a mouse side button |
| `Esc` | Cancel the current recording without output |

Normal output path:

```text
Speech → Local recognition → Text cleanup → Clipboard → Current cursor → Local history
```

## Privacy and Networking

Audio, transcripts, vocabulary, and history stay on the local machine by
default. Normal operation does not automatically download models, check for
updates, or call cloud recognition services. Source mode uses the network only
when the user explicitly prepares a model.

<details>
<summary><strong>Development, verification, and licenses</strong></summary>

### Run from source

```bat
git clone https://github.com/qinxujunai/VoiceFlow.git
cd VoiceFlow
start.bat
```

### Verify

```bat
venv\Scripts\python.exe scripts\verify.py
venv\Scripts\python.exe scripts\verify.py --release
```

- [Quality gate](docs/quality-gate.md)
- [ASR evaluation plan](docs/asr-evaluation-plan.md)
- [Model strategy and admission decision](docs/model-strategy.md)
- [Product quality standard](docs/product-quality-standard.md)
- [Runtime and user-data boundary](docs/runtime-boundary.md)
- [Release checklist](docs/release-checklist.md)

VoiceFlow source code is available under the [MIT License](LICENSE). Models and
third-party components remain subject to their respective licenses:

- [SenseVoice redistribution record](docs/sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL compliance record](docs/qt-lgpl-compliance.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

</details>
