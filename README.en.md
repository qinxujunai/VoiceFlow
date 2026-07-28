# VoiceFlow

<p align="right">
  <a href="README.md">简体中文</a> · <strong>English</strong>
</p>

> Speak. Words land.

[![Windows quality](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml/badge.svg)](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml)
[![Download for Windows](https://img.shields.io/badge/Windows-download-087FE7)](https://github.com/qinxujunai/VoiceFlow/releases/download/v0.2.0/VoiceFlow-0.2.0-Windows-x64.exe)

![VoiceFlow animated demo](docs/voiceflow-demo.svg)

VoiceFlow is offline dictation for Windows. Press `F2`, speak, and press it
again—the text returns to your current cursor. Recognition runs on your PC
without an account or audio upload.

## Why VoiceFlow

- **Entirely offline**: core dictation makes no cloud recognition calls and works without a network.
- **Any text field**: dictate directly into notes, browsers, documents, and chat windows.
- **Recoverable results**: text reaches the clipboard before paste is attempted and is also saved to local history.
- **Complete long dictation**: live preview provides feedback while the stop path finishes all recorded audio.

## Download

Most people only need
[VoiceFlow-0.2.0-Windows-x64.exe](https://github.com/qinxujunai/VoiceFlow/releases/download/v0.2.0/VoiceFlow-0.2.0-Windows-x64.exe).
The installer includes the default offline model and does not require Python.

> The installer is not yet Authenticode-signed, so Windows may display a
> reputation warning. Download only from this repository or the
> [product site](https://qinxujunai.github.io/VoiceFlow/?lang=en).

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
