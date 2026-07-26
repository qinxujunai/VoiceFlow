# VoiceFlow

<p align="right">
  <a href="README.md">简体中文</a> · <strong>English</strong>
</p>

> Offline. Immediate. Never lose a word.

[![Windows quality](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml/badge.svg)](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml)
[![Product site](https://img.shields.io/badge/product_site-open-111111)](https://qinxujunai.github.io/VoiceFlow/?lang=en)
[![Windows Beta](https://img.shields.io/badge/Windows_Beta-download-087FE7)](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.2.0-beta.1)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4)](#requirements)
[![Local first](https://img.shields.io/badge/local--first-offline-2EA44F)](#privacy-and-networking)
[![License](https://img.shields.io/github/license/qinxujunai/VoiceFlow)](LICENSE)

![VoiceFlow animated demo](docs/voiceflow-demo.svg)

VoiceFlow is local-first dictation for Windows. Press `F2`, speak, and press it again—the text returns to your current cursor. Recognition, vocabulary, and history stay on your device by default. If the target app does not accept the paste, the result remains recoverable from the clipboard and local history.

## Core Capabilities

- **Dictate wherever you type**: use `F2`, Right Ctrl, or a mouse side button in the app already in front of you.
- **Offline recognition**: no cloud ASR calls or online LLM processing in the default path.
- **Recoverable output**: text reaches the clipboard before paste is attempted and is also saved to local history.
- **Smooth long dictation**: preview, audio retention, and UI work stay bounded instead of growing with recording duration.
- **Truthful feedback**: the waveform follows actual microphone input; preview communicates progress, while final transcription produces the output.
- **Quiet presence**: tray operation, single-instance startup, and a compact overlay keep VoiceFlow out of the way.

## Quick Start

For normal use, choose a platform on the
[product site](https://qinxujunai.github.io/VoiceFlow/?lang=en) or open the
[GitHub Release](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.2.0-beta.1)
and download `VoiceFlow-Setup-0.2.0-beta.1-x64.exe`. The installer includes the
default offline model and needs no Python.

> This public Beta is not yet Authenticode-signed, so Windows may display a
> reputation warning. Download only from this repository and verify the file
> against `SHA256SUMS.txt` in the Release.

Developers can run from source:

```bat
git clone https://github.com/qinxujunai/VoiceFlow.git
cd VoiceFlow
start.bat
```

Source mode validates the Python environment and prepares a local model on first
run. Model files are not stored in Git; downloads are always explicit and
assets are verified before activation.

Once setup is complete, the desktop shortcut starts VoiceFlow without a console window. Starting it again brings the existing instance forward instead of creating another process.

### Requirements

- Windows 10 or Windows 11
- A working microphone
- The installed build needs no network; source setup needs network once

## Controls

| Key | Action |
| --- | --- |
| `F2` | Start / stop dictation |
| `Right Ctrl` | Start / stop dictation |
| `xbutton1` / `xbutton2` | Start / stop with a mouse side button |
| `Esc` | Cancel the current recording without output |

The normal output path is:

```text
Speech → Local ASR → Deterministic cleanup → Clipboard → Current cursor → Local history
```

Text shown while recording is a live preview. After you stop, VoiceFlow finishes the remaining audio before it outputs the complete result. Short recordings use one full final pass; long recordings progressively settle stable segments and finish the tail on stop.

## Reliability by Design

- **Silence protection**: local VAD rejects background noise, key sounds, and punctuation-only hallucinations without discarding genuine one-word dictation.
- **Complete tail coverage**: final output must include all stopped audio; preview is never treated as the final transcript.
- **Bounded live work**: preview reads a fixed recent audio window, and old PCM is released after stable segments settle.
- **Latest state wins**: the overlay renders the newest state instead of queueing stale recognition results or animation frames.
- **Failure recovery**: recognized text remains in the clipboard and `%LOCALAPPDATA%\VoiceFlow\logs\history.jsonl` even when automatic paste fails.

## Models and Languages

The current default engine is offline SenseVoice. VoiceFlow also provides a common model adapter and local evaluation tooling for SenseVoice, Qwen3-ASR, and Fun-ASR Nano. Candidates are compared on accuracy, latency, tail completeness, and resource use; only an engine that passes every product gate can become the default.

On first run, VoiceFlow seeds user configuration from the project or installed `config.yaml`. Runtime settings then live at `%LOCALAPPDATA%\VoiceFlow\config.yaml`. Options such as `zh`, `en`, and `auto` depend on the selected model's actual capabilities.

## Development and Verification

```bat
venv\Scripts\python.exe scripts\verify.py
venv\Scripts\python.exe scripts\verify.py --release
```

The standard gate covers environment diagnostics, compile checks, automated tests, 500 deterministic lifecycle cycles, a quick ASR benchmark, and integration. Release validation also requires recorded performance evidence, DPI screenshots, keyboard and Narrator tasks, long recordings, device switching, and residency testing.

- [Quality gate](docs/quality-gate.md)
- [ASR evaluation plan](docs/asr-evaluation-plan.md)
- [Runtime and user-data boundary](docs/runtime-boundary.md)
- [Release checklist](docs/release-checklist.md)

## Privacy and Networking

Recordings, transcripts, vocabulary, and history stay on the local machine by default. Runtime does not automatically download models, check for updates, or call cloud recognition services. Network access occurs only when the user explicitly starts model setup. Private evaluation audio lives in a Git-ignored directory and is never uploaded by the evaluation tools.

## Project Status

VoiceFlow 0.2.0-beta.1 is a public Windows x64 test build. The installed-runtime
boundary, user-data retention, SenseVoice redistribution record, and full
offline installer have passed local validation. Two limitations remain explicit:

- The installer is not yet Authenticode-signed and is not a stable release.
- macOS is not released. Global input, Accessibility permissions, signing, and
  notarization must be validated on real macOS hardware and cannot be replaced
  by a Windows build.

## License

VoiceFlow source code is available under the [MIT License](LICENSE). Models and third-party components remain subject to their respective licenses and are reviewed separately before public redistribution.

- [SenseVoice redistribution record](docs/sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL compliance record](docs/qt-lgpl-compliance.md)
