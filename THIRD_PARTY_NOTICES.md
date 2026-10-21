# Third-party notices

VoiceFlow source code is licensed under the MIT License. The packaged product
also contains third-party components under their own licenses.

| Component | License | Use |
|---|---|---|
| PySide6 / Qt for Python | LGPL-3.0-only or commercial | Native desktop UI binding |
| Qt 6 libraries | LGPL-3.0-only, GPL, or commercial depending on module | Desktop UI runtime |
| Apache Tika MIME definitions / PRONOM | Apache-2.0 / Open Government Licence 3.0 attribution | MIME data included in QtCore |
| Mesa llvmpipe 11.2.2 | MIT and Boost-1.0 component notices | Qt's optional Windows software OpenGL runtime |
| LLVM 3.6.2 | University of Illinois/NCSA and component notices | Compiler support statically included in Mesa llvmpipe |
| CPython | PSF and included component notices | Bundled Python interpreter and standard library |
| Microsoft Visual C++ Runtime | Microsoft Distributable Code and Runtime terms | Windows runtime support; original terms and licensed Community provenance in `licenses/microsoft-vc-runtime/` |
| OpenSSL 3.5.6 | Apache-2.0 | TLS libraries accompanying CPython and Qt |
| PortAudio 19.7.0 | MIT | Ordinary Windows microphone backends; optional ASIO library excluded from the current package |
| sherpa-onnx | Apache-2.0 | Offline ASR runtime |
| pybind11, kaldi-native-fbank, kaldi-decoder, kaldifst, OpenFst, kissfft, Eigen, simple-sentencepiece, nlohmann/json | Original component notices included with the local ASR wheel | Native build inputs; static-link and header obligations remain under review |
| Silero VAD | MIT | Offline speech-presence detection before ASR |
| ONNX Runtime | MIT | Neural-network inference through sherpa-onnx |
| NumPy | BSD-3-Clause | Audio buffers and numeric processing |
| python-sounddevice | MIT | Microphone capture |
| PyYAML | MIT | Local configuration |
| pynput | LGPL-3.0-only | Right Ctrl and mouse trigger handling |
| keyboard | MIT | Suppressed F2 trigger handling |
| PyAutoGUI | BSD-3-Clause | Cross-platform development fallback; excluded from the current Windows build |
| pyperclip | BSD-3-Clause | Clipboard output |
| Python-UIAutomation-for-Windows 2.0.29 | Apache-2.0 | Focused editable-element inspection on Windows |
| comtypes 1.4.13 | MIT | COM binding used by Windows UI Automation |

PySide6 and Qt remain dynamically linked libraries in the onedir distribution.
Users may replace compatible LGPL builds. Nothing in the VoiceFlow license
restricts debugging or reverse engineering for the purpose of modifying those
LGPL components. The exact source revisions and replacement procedure are in
`docs/qt-lgpl-compliance.md`.

The current spec collects PySide6/Shiboken6 Python library modules as external
original sources, alongside their dynamic DLLs; dev15 and earlier archive the
Python portions in the EXE. This path requires actual frozen replacement checks.

The Windows onedir also collects pynput 1.8.2 as external original `.py` files
under `pynput/`, without duplicate modules sealed in the EXE's PYZ archive.
Exit VoiceFlow and back up that directory before replacing it with a compatible
modified library; restore the backup on incompatibility. The original per-file
copyrights remain in those sources, alongside the collected LGPL license.
This packaging choice does not certify the complete product license review.

The packaged application includes these verbatim upstream license texts:

- `licenses/Qt-LGPL-3.0-only.txt`
- `licenses/GPL-3.0-only.txt`
- `licenses/Chromium-BSD.txt`
- `licenses/Apache-2.0.txt`
- `licenses/Apache-Tika-MIME-NOTICE.txt`
- `licenses/comtypes-MIT.txt`
- `licenses/Mesa-llvmpipe-NOTICES.txt`
- `licenses/LLVM-3.6.2-LICENSE.txt`
- `licenses/LLVM-3.6.2-COPYRIGHT.regex`
- `licenses/LLVM-3.6.2-ARM-LICENSE.txt`
- `licenses/LLVM-3.6.2-MD5-NOTICES.txt`
- `licenses/ONNXRuntime-1.24.4-LICENSE.txt`
- `licenses/ONNXRuntime-1.24.4-ThirdPartyNotices.txt`
- `licenses/OpenSSL-3.5.6-LICENSE.txt`
- `licenses/PortAudio-LICENSE.txt`
- `licenses/Silero-MIT.txt`

The build also retains the original build interpreter's `LICENSE.txt` at
`licenses/CPython-LICENSE.txt`. Original wheel copyright/license files for
distributions referenced by PyInstaller Analysis are copied unchanged under
`licenses/python/`; their relative paths and SHA256 values are recorded in
`dependency-notices.json`. NumPy's complete wheel notice includes OpenBLAS,
LAPACK and the GCC runtime exception. A wheel with no notice file is explicitly
listed with an empty notice array and still requires a reviewed upstream notice.
These generated lists do not approve every native or statically linked component.

The 0.3.9 release review is recorded separately in `licenses/release-review-0.3.9.md`.
Earlier manifests retain their original evidence scope and pending-review fields;
they are historical provenance, not the final release sign-off. The exact corresponding
Qt/PySide6/pynput source archives are a separate versioned Release asset documented in
`licenses/LGPL-SOURCE.md` and pinned by `licenses/lgpl-sources.json`.

`licenses/cpython-3.12.13/` additionally retains nine unchanged native component
notice/header files from the interpreter's official 20260602 full archive and
CPython 3.12.13 source archive. Its manifest records the pinned archive hashes
and 23 exact binary matches to the corresponding install-only-stripped archive.
This includes libffi, liblzma, bzip2, zlib, OpenSSL, Expat and mpdecimal. The
Expat COPYING from CPython source supplements the older generic build notice;
the original mpdecimal header preserves its per-file copyright and terms.
The archives and their metadata have distinct scopes; these additions do not
complete the native redistribution review or establish MSVC entitlement.

`licenses/cffi-2.0.0/` retains unchanged original Windows libffi source/header
notices and the setup file from CFFI's pinned source distribution. Its manifest
records the exact official wheel match for the packaged native extension. CFFI's
root MIT No Attribution terms and the vendored libffi MIT copyright notices are
distinct. This source evidence does not claim a reproduced upstream wheel build.

`licenses/numpy-2.5.0-supplements/` retains the unchanged original MIT notice
for delvewheel 1.11.2's loader template embedded in NumPy's Windows initializer,
and the complete scipy-openblas64 0.3.33.112.0 wheel notice. The initializer
matches the original template after line-ending normalization; the packaged
OpenBLAS DLL matches that independent official wheel byte for byte. The manifest
records exact archive/member hashes and comparison scope. The original NumPy
wheel notice remains included; static dependency/source obligations are still
under review. Delvewheel is not added as a runtime dependency.

The current development ASR dependency is the distinct local version selected in
`vendor/windows/asr-runtime.json`. Its exact source archive, two-line modified
binding patch, native build inputs and hashes are included in its wheel notices;
see `docs/asr-runtime-build.md`. Unused eSpeak/Piper TTS and C API payloads are
excluded by this build. Historical packages containing the original upstream
extension do not inherit that exclusion or a completed license review.

Unmodified Eigen 5.0.1 source is included locally as
`licenses/native-asr/eigen-5.0.1.tar.gz`; `licenses/native-asr/SOURCE.md` gives
its exact archive hash, original source terms and how to obtain it. The unchanged
nlohmann/json `to_chars.hpp` and original MIT text retain the additional Florian
Loitsch attribution observed in the actual compiler-read inventory. These files
and the unchanged Darts and ONNX Runtime float16 headers preserve additional
BSD attributions. They are build-recorded bundled inputs, not evidence of
overall license approval.

`licenses/qt-6.11.1/manifest.json` identifies unchanged original QtBase, Qt SVG
and Qt Image Formats attribution/license files and the official SDK build/source
SBOMs associated with the 25 payload-matched Qt DLLs. This includes bundled
FreeType, HarfBuzz, JPEG, PNG, PCRE2, zlib, TIFF, WebP and component notices.
The upstream SBOMs also describe build interfaces and unshipped tools; they are
provenance inputs rather than a declaration that all their components ship.
The manifest preserves the specific source-verification limits, including
Windows line endings and WebP COPYING's tag-only provenance. Full applicability
and LGPL obligations remain under review. Dev4 and earlier packages predate
this additional notice bundle.

The bundled Qt font and rasterizer code uses the FreeType License option.
This software is based in part on the work of the FreeType Team.
This software is based in part on the work of the Independent JPEG Group.
Qt's smooth-scaling code used by VoiceFlow is based on Imlib2, with contributions
by Daniel M. Duley, Carsten Haitzler and other contributors, and Willem Monsuwe.
The original copyright, permission and disclaimer texts for these components
remain in `licenses/qt-6.11.1/`; these acknowledgments supplement those texts.

`licenses/qt-6.11.1/public-suffix-data/` retains the unchanged preferred MPL 2.0
source for the Public Suffix List embedded in Qt Network, its generated C++
table and the original standalone BSD generator and notice. The pinned list
reproduces the original table byte for byte; that table matches the current
Network DLL. The included `SOURCE.md` and parent manifest provide exact source
URLs, hashes and a local regeneration command. This is a specific covered-source
supplement; it does not complete the whole Qt or product license review.

The current Windows build uses checked native paste and excludes PyAutoGUI's
unused helper chain, including MouseInfo (declared GPLv3+ upstream) and Tk.
Earlier development packages did include that chain and do not inherit this
exclusion retrospectively. ONNX Runtime's full upstream third-party notice is
retained; inclusion of that notice is not a claim that every optional upstream
provider, such as MKL, is present in this package.

The ordinary PortAudio DLL matches python-sounddevice 0.5.5's official wheel and
`spatialaudio/portaudio-binaries` commit
`bf2681cd2c6c88c2ad83341049b2420d805d5353` byte for byte. That commit's build
workflow selects PortAudio v19.7.0. The optional `*-asio.dll` is excluded; packaged
processes ignore inherited `SD_ENABLE_ASIO` before sounddevice imports. This
does not change the host environment or development-source backend selection.
ASIO-only device support is outside this Windows package's supported scope.
Historical dev3 and earlier packages included the optional DLL and still require
its separate SDK/version/license review before redistribution.

These notices must remain in every redistributed application. The 2026-10-04
native candidate excludes Qt WebEngine and Chromium. Historical WebEngine builds
must additionally retain their bundled generated Chromium credits resources.

## Speech models

Final Chinese punctuation uses the pinned `CT-Transformer` int8 model,
`iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch`, by Alibaba Group /
FunASR / ModelScope, converted for sherpa-onnx by k2-fsa. See
`docs/punctuation-model-review.md` for source URLs, exact artifact hashes,
language limits and the dated distribution record. Retain the model name,
source and author attribution, `licenses/Apache-2.0.txt` and the additional
`licenses/FunASR-MODEL-LICENSE.txt`. The VoiceFlow MIT license does not replace
the model's upstream terms.

The bundled Silero VAD is byte-identical to k2-fsa's official 16 kHz release
asset (asset ID 271935959), SHA256
`9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`.
The original Silero Team MIT notice is retained unchanged from the upstream v4.0
commit `915dd3d639b8333a52e001af095f87c5b7f1e0ac`; source URLs and hashes are in
`model-manifest.json` under `auxiliary_assets`. The referenced k2-fsa exporter
documents its derivation; VoiceFlow has not reproduced that export.

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

QtCore MIME data attribution: upstream Apache Tika revision 408c26e1e03e018a623e732dff6fb047a2fb8e19. The complete upstream NOTICE is retained verbatim (SHA256 4cd09bac8d81bd34decf6b95fb23d42fc9b3d6b653ec4be8ef44674b692c97cd). Only MIME definitions are used here; other components mentioned in that upstream NOTICE are not claims of bundled VoiceFlow dependencies. The definitions include PRONOM material from The National Archives under Open Government Licence 3.0.
