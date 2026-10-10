# Windows ASR runtime build

The development candidate keeps SenseVoice, the online preview model and Silero
VAD unchanged. Its Python runtime is Windows Python 3.12 x64. macOS uses its
separate requirements files and is outside this native build procedure.

## Why a local build

The original sherpa-onnx 1.13.3 Windows extension includes unused eSpeak/Piper
speech synthesis. The development build disables TTS and the C API, diarization,
PortAudio, websocket and command-line binaries. This addresses an unnecessary
native dependency and license-review surface; it is not a model accuracy claim.

`vendor/windows/asr-runtime.json` pins the source archive, actual upstream commit,
ten dependency archives, CMake features, patch, wheel and native binary hashes.
`requirements.txt` and `requirements.lock` select the distinct local version
`1.13.3+voiceflow.5`. The official `sherpa-onnx-core==1.13.3` supplies the unchanged
ONNX Runtime DLL; its unused C/C++ API DLLs must not enter the frozen package.

The only upstream source patch adds two missing disabled-TTS placeholder
bindings so the unchanged Python wrappers import. The exact patch and its
modification date are included in the wheel's native build notice.

The upstream `version.cc` contains a baked Git string that differs from the
checked-out tag commit. It is explicitly not used as source provenance.

## Verify before installing or packaging

Run from the repository root:

```bat
python scripts\asr_runtime_assets.py --hash-only
python -m pip install -r requirements.lock
python scripts\asr_runtime_assets.py
python scripts\verify.py
python -m PyInstaller VoiceFlow.spec
python scripts\asr_runtime_assets.py --package-dir dist\VoiceFlow
```

The first check uses only the standard library. Subsequent checks validate wheel
RECORD, PE architecture and exports, the exact installed native extension and
ONNX Runtime. Packaging rejects the original native extension and unused C API
DLLs. These checks do not import an audio or ASR engine into the build guard.

Startup preserves an incompatible existing virtual environment and reports the
required Python ABI; it does not delete it to change Python versions.

## Rebuild from pinned inputs

Use existing CMake and Visual Studio 2022 C++ Build Tools, an installed Windows
SDK, and Python 3.12 x64. The script does not install those tools or replace the
project environment. Select paths for your own machine:

```bat
venv\Scripts\python.exe scripts\build_asr_runtime.py ^
  --work-dir tests_runtime\asr-rebuild-new ^
  --cache-dir C:\path\to\pinned-archive-cache ^
  --cmake C:\path\to\cmake.exe ^
  --vs-instance "C:\path\to\Visual Studio\2022\BuildTools" ^
  --version 1.13.3+voiceflow.5 --offline
```

The work directory must be new. Offline mode refuses missing or changed input
archives. Omitting `--offline` explicitly allows the script to download from
the pinned upstream URLs. All ten dependencies are extracted before CMake;
explicit source-directory overrides and fully disconnected FetchContent prevent
CMake from fetching a different dependency. The build uses four compiler workers and writes owned-process
exit, tool hashes and source provenance into the isolated work directory.

Output appears in `output/vendor/windows`. It is not installed or promoted.
MSVC paths and timestamps can change binary bytes; this is a repeatable build
procedure with exact input/output provenance, not a bit-reproducibility claim.
Run fresh import, audio, regression, package and clean-machine checks on each
new binary before selecting its wheel and manifest in the repository.

## Current evidence and limits

The earlier scripted rebuild succeeded on the local Windows 11 development
machine, but its original offline claim was contradicted by an actual OpenFst
download. The parent CMake module selected 2026-04-11 rather than the declared
2026-04-10 archive. The manifest records the actual archive. A new-directory,
fully disconnected `.5` build completed in 333.88 seconds and is selected by
requirements and the project venv. Its native binary is newly compiled;
no bit-reproducibility claim is made. Fresh isolated pip RECORD and wrapper
checks pass. Three paired rounds across ten identical public/constructed audio
cases produced 90 exact matches for final text, all preview events and VAD.
These are compatibility checks, not a natural-speech holdout, accuracy claim,
complete application benchmark or installed-product acceptance.
The comparisons used an isolated installation of the original official binary,
not inherited results for `.2`. Compiler reads were compared byte for byte with
all eleven pinned archives: 1,095 exact matches and the reviewed two-line patch.
The prior `.2`, `.3` and `.4` inputs remain historical evidence.

Original dependency notices are retained in the wheel and copied into packaged
notices. Ten native build inputs are also recorded in the release SBOM. Source
availability is provided for unmodified Eigen in
`licenses/native-asr/eigen-5.0.1.tar.gz` with its original terms and source
instructions. The unchanged JSON conversion header retains its extra copyright
attribution in the same directory. These are hashed bundled build inputs.
Header,
static-link and toolchain obligations remain under review; no complete license
approval or public-release approval is implied. Historical development packages
retain their original native payload and do not inherit this change.
