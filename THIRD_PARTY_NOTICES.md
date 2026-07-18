# Third-party notices

VoiceFlow source code is licensed under the MIT License. The packaged product
also contains third-party components under their own licenses.

| Component | License | Use |
|---|---|---|
| PySide6 / Qt for Python | LGPL-3.0-only or commercial | Desktop UI and WebEngine binding |
| Qt 6 libraries | LGPL-3.0-only, GPL, or commercial depending on module | Desktop UI runtime |
| sherpa-onnx | Apache-2.0 | Offline ASR runtime |
| Silero VAD | MIT | Offline speech-presence detection before ASR |
| ONNX Runtime | MIT | Neural-network inference through sherpa-onnx |
| NumPy | BSD-3-Clause | Audio buffers and numeric processing |
| python-sounddevice | MIT | Microphone capture |
| PyYAML | MIT | Local configuration |
| pynput | LGPL-3.0-only | Right Ctrl and mouse trigger handling |
| keyboard | MIT | Suppressed F2 trigger handling |
| PyAutoGUI | BSD-3-Clause | Paste and keyboard output |
| pyperclip | BSD-3-Clause | Clipboard output |

PySide6 and Qt remain dynamically linked libraries in the onedir distribution.
Users may replace compatible LGPL builds. Nothing in the VoiceFlow license
restricts debugging or reverse engineering for the purpose of modifying those
LGPL components. Qt and Chromium license files shipped by the PySide6
distribution must remain in the packaged application.

## Speech models

Models are not part of the VoiceFlow source-code license. Each model keeps its
upstream terms and pinned source information in `model-manifest.json`.

- Qwen3-ASR-0.6B and Fun-ASR-Nano use Apache-2.0 upstream models.
- SenseVoiceSmall is marked `LicenseRef-Model-License`; its model terms require
  distribution review. The public installer build must not redistribute it
  until that review is recorded, even though local users may download it
  explicitly from the pinned upstream source.

This notice is an engineering inventory, not legal advice. Release owners must
retain upstream copyright and license files in every public build.
