# VoiceFlow 0.3.9 dependency review

Review date: 2026-10-21. Scope: the pinned Windows runtime and model inputs of
build 261021.6. This is an engineering redistribution review, not a claim of
legal advice, accuracy superiority, or approval of arbitrary future versions.
The final installer must still pass exact-file, clean-install, upgrade and
uninstall checks before publication.

## Microsoft runtime

The maintainer explicitly authorized acquiring the free Community entitlement
for this MIT/OSI open-source project. The Microsoft-signed Visual Studio 2022
Community bootstrapper completed successfully; vswhere confirms the complete,
launchable product 17.14.37806.7. The product, bootstrapper digest, license
origins and original documents are retained in `microsoft-vc-runtime/SOURCE.json`.
Community sections 1 and 4 and the VS2022 Distributable List provide the basis
for distributing the release CRT/STL code as part of VoiceFlow. The earlier
BuildTools compilation of necessary open-source dependencies is separately
covered by its open-source dependency exception; no retrospective compiler
license claim is needed.

The package contains release runtime DLLs 14.44.35211.0, and NumPy's renamed,
unchanged MSVCP140 14.40.33810.0. No debug CRT, Visual Studio IDE, compiler, SDK
or standalone redistributable installer is included. Runtime code is used only
as part of the substantially functional dictation product. It remains under
Microsoft's terms, outside the application MIT license. The installer presents
`VoiceFlow-install-terms.txt`, retaining the original Runtime terms. No
restriction is added to LGPL/MPL or other third-party source/replacement rights.

## Qt / PySide6 / Shiboken6 and pynput

These libraries are used under LGPL-3.0-only. Original library notices, GPLv3
terms incorporated by LGPLv3, source revisions and Qt third-party attributions
are retained. The package excludes the retired WebEngine/QML/Quick/PDF and
VirtualKeyboard runtime. The retained SDK DLL code/data payloads were compared
with the pinned official Qt archives; signing/checksum metadata differences
are explicitly excluded from that comparison.

The shared DLLs and original Python library sources remain outside the EXE.
Fresh tests of the 261012.5 runtime verify modified PySide6/Shiboken6/pynput
source loading and a changed Qt DLL's resource bytes without changing the EXE;
equivalent checks must be repeated on the final 261021.6 package. These are
replacement-mechanism tests, not a separately rebuilt Qt ABI certification.

`LGPL-SOURCE.md` identifies the matching Release source asset.
`lgpl-sources.json` pins full QtBase, QtSvg, QtImageFormats and PySide6 source
archives by immutable commit and SHA256, plus pynput's original PyPI sdist.
The source asset accompanies the installer; the unmodified original licenses
and build files are retained in each archive. The public-suffix MPL source,
generator and exact generated table are additionally provided in the install.

## Native ASR and model inputs

The unchanged ASR-only 1.13.3+voiceflow.5 wheel has no eSpeak/Piper TTS, C API,
diarization, PortAudio or websocket subsystem. Its source archive, two-line
disabled-TTS binding patch, ten dependency archives and compiler-read inputs
are pinned in `vendor/windows/asr-runtime.json`. The recorded read audit covers
1,096 files: 1,095 original archive matches and the declared two-line patch.
No GPL/LGPL source-pattern flags were found in those recorded compiler reads.

The wheel's 19 original notice/patch records cover sherpa-onnx, pybind11,
kaldi-native-fbank, kaldi-decoder, kaldifst, OpenFst, kissfft, Eigen,
simple-sentencepiece, nlohmann/json and ONNX Runtime. Apache-2.0, BSD and MIT
copyright/license notices are retained for static/header use. Eigen's complete,
unchanged 5.0.1 source archive and MPL terms are included locally. The additional
JSON conversion, Darts and ONNX float16 headers retain their per-file notices.
No optional Eigen MKL runtime is shipped. The unchanged ONNX Runtime DLL's own
MIT license and full third-party notices also cover the core wheel, whose
distribution metadata lacks a separate notice file.

The pinned SenseVoiceSmall, streaming preview, Silero and CT-Transformer
punctuation assets retain their existing source, hash, license and distribution
decisions. This release changes neither recognizer nor model weights and makes
no comparative accuracy claim. The natural-speech holdout remains incomplete;
the current fixed public/constructed regression, latency and pathological-output
checks are compatibility evidence, not a replacement for that holdout.

## Other retained native and Python components

| Component | License/obligation and retained evidence |
|---|---|
| CPython 3.12.13 and standard-library native dependencies | PSF and original libffi, zlib, bzip2, liblzma, OpenSSL, Expat and mpdecimal notices in `CPython-LICENSE.txt` and `cpython-3.12.13/`; 23 exact original binary matches are recorded. |
| OpenSSL 3.5.6 | Apache-2.0 original terms and upstream attribution; shared binaries remain unmodified. |
| NumPy / OpenBLAS / LAPACK / GCC runtime | Original wheel's full BSD notices, GCC runtime exception and component notices, with `numpy-2.5.0-supplements/` retaining the exact OpenBLAS wheel notice and delvewheel loader attribution. |
| CFFI / vendored libffi | CFFI MIT-0 and libffi MIT notices are distinct and both retained in `cffi-2.0.0/`. |
| PortAudio / sounddevice | MIT original notices; the optional ASIO DLL is excluded. |
| Mesa llvmpipe / LLVM | Retained software OpenGL binary matches the official Qt archive outside PE signing/checksum fields. Mesa MIT/Boost and LLVM NCSA, regex, ARM and MD5 original notices are all retained; no separate GPL runtime is introduced. |
| Qt MIME / public suffix / image codecs and bundled Qt third-party code | The 110 original Qt attribution/license files, upstream SBOM evidence and exact MPL public-suffix source supplements remain in `qt-6.11.1/`; source archives include the corresponding unmodified third-party code. |
| PyInstaller | Original GPL terms with the bootloader exception permit this combined application distribution; retain its original notice. |
| keyboard, pyperclip, PyYAML, six, typing_extensions, uiautomation, comtypes | Original wheel MIT/BSD/Apache notices retained under `licenses/python/` and the component supplements. |

Python ownership is derived from actual PyInstaller Analysis and distribution
RECORD, not a top-level requirements list alone. Each collected notice is hashed
in `dependency-notices.json`; all frozen files are listed in the final SBOM.
Earlier development manifests deliberately keep their historical incomplete
review flags. They do not replace or silently inherit this release review.

Final sign-off must identify the exact installer/application/source inputs,
verify the notice/source asset delivery, and record the clean-runner result.
Changed dependency bytes, new native inputs, missing sources or missing rights
require another review. Generated inventories alone do not constitute approval.
