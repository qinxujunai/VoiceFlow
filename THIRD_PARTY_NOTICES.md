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
| Python-UIAutomation-for-Windows 2.0.29 | Apache-2.0 | Focused editable-element inspection on Windows |
| comtypes 1.4.13 | MIT | COM binding used by Windows UI Automation |

PySide6 and Qt remain dynamically linked libraries in the onedir distribution.
Users may replace compatible LGPL builds. Nothing in the VoiceFlow license
restricts debugging or reverse engineering for the purpose of modifying those
LGPL components. The exact source revisions and replacement procedure are in
`docs/qt-lgpl-compliance.md`.

The packaged application includes these verbatim upstream license texts:

- `licenses/Qt-LGPL-3.0-only.txt`
- `licenses/GPL-3.0-only.txt`
- `licenses/Chromium-BSD.txt`
- `licenses/Apache-2.0.txt`
- `licenses/comtypes-MIT.txt`

These notices and Qt WebEngine's bundled credits resources must remain in every
redistributed application.

## Speech models

Models are not part of the VoiceFlow source-code license. Each model keeps its
upstream terms and pinned source information in `model-manifest.json`.

- Qwen3-ASR-0.6B and Fun-ASR-Nano use Apache-2.0 upstream models.
- SenseVoiceSmall is marked `LicenseRef-Model-License` and remains under the
  FunASR Model Open Source License Agreement 1.1. The pinned VoiceFlow 0.2
  redistribution decision is recorded in
  `docs/sensevoice-redistribution-decision.md`; the exact reviewed terms are
  retained in `licenses/FunASR-MODEL-LICENSE.txt`.
- SenseVoiceSmall attribution: Alibaba Group / FunASR / SenseVoice;
  conversion repository
  `csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`,
  revision `2365baeacb507f821a0c8120fcee3d484dba7a07`, upstream model
  `FunAudioLLM/SenseVoiceSmall`.
- The bundled Chinese-English streaming preview originates from the official
  sherpa-onnx release asset
  `sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16` and the
  upstream `csukuangfj/k2fsa-zipformer-bilingual-zh-en-t` checkpoint under
  Apache-2.0. Exact source and hashes are recorded in `model-manifest.json` and
  `docs/streaming-preview-model-review.md`.

This notice is an engineering inventory, not legal advice. Release owners must
retain upstream copyright and license files in every public build. The
UIAutomation package is covered by the bundled Apache-2.0 text; the exact
comtypes copyright and MIT terms are retained separately.
