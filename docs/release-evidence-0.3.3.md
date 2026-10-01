# VoiceFlow 0.3.3 release verification evidence

This document records the evidence for the `0.3.3` public patch release. It
does not make a population-level speech-accuracy claim.

## Candidate

- Version: `0.3.3`
- Build: `261001.1`
- Platform target: Windows 10 / 11 x64
- Runtime change: none; the patch aligns public release metadata and the
  website deployment path with the stable Windows Release.
- Public download rule: the Pages renderer accepts only a published stable
  Release containing the matching installer, `SHA256SUMS.txt`, SBOM, and
  third-party notices, with the installer digest matching the checksum file.

## Local source and runtime gates

Run on 2026-10-01 from the release checkout:

- Explicit Windows `py_compile` list: passed.
- `venv\\Scripts\\python.exe -m pytest tests -q`: `396 passed`.
- `venv\\Scripts\\python.exe scripts\\verify.py --release`: passed.
  - doctor: passed; the existing desktop shortcut was reported as a warning.
  - stability: `500 / 500` cycles.
  - UI quality: four DPI scales passed.
  - flagship stress: `10,000` state sequences, `5,000` delivery-fault cases,
    and `50,000` safe-text fuzz cases passed.
  - performance: passed with `20` samples in each measured group.
  - integration: passed for Chinese, English, Japanese, and Korean fixtures.

## Packaging evidence

The local `venv\\Scripts\\pyinstaller.exe VoiceFlow.spec --noconfirm` build
completed and embedded Windows file version `0.3.3.1` and product version
`0.3.3+261001.1`.

The local `scripts\\smoke_packaged_runtime.ps1` check did not pass on this
workstation: the frozen process exited before writing `runtime-state.json`.
A temporary console build reproduced the cause as `PySide6.QtCore` failing to
load a Qt DLL, followed by the intentional fallback to the unavailable
PyQt6 binding. The temporary diagnostic files and console setting were
removed. This local result is a release limitation, not a passed packaging
claim.

The previous clean GitHub Windows Release runner passed the same packaged
runtime smoke and installer smoke for v0.3.2 in run
https://github.com/qinxujunai/VoiceFlow/actions/runs/32756233090. The v0.3.3
Windows quality run also passed the unit, integration, and package smoke gates
on a clean runner:
https://github.com/qinxujunai/VoiceFlow/actions/runs/36795670250.

The local packaged-runtime limitation remains recorded above. The v0.3.3
release runner passed the corresponding clean-runner checks, including
packaged runtime smoke and full installer lifecycle smoke:
https://github.com/qinxujunai/VoiceFlow/actions/runs/36796628282.

## Public-surface checks after publishing

The following checks were recorded against the published v0.3.3 assets:

- GitHub Release: https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.3
  is stable and points to tag `v0.3.3`, resolved at commit
  `a9b9d707bb61e6fc3a9510c0ad4ae0a2dfa32c28`.
- Release assets are exactly:
  `VoiceFlow-0.3.3-Windows-x64.exe` (`362504336` bytes,
  `73c17d5af0e257ba1781beed9f35b52ca77a780648c098d56a6fc4e986308a2f`),
  `SHA256SUMS.txt` (`270` bytes,
  `260ec7425df95aa5bfe608ca75e6636642a1e61488e84e3d46475eb11b05bb11`),
  `SBOM.cdx.json` (`16825` bytes,
  `d5283bfe672aaace22c6b2a1a768f16b7b19d6e80903b65cacd8a86a12c0af3d`),
  and `THIRD_PARTY_NOTICES.md` (`3363` bytes,
  `94a2f5c8118e6c286b463057f70eb8255b30183f3e61d7d36ad8622489a59033`).
- The installer digest equals the `SHA256SUMS.txt` entry. The three
  compliance asset digests also match the published asset metadata.
- README Chinese and English evidence links resolve with HTTP 200 to this
  document:
  https://github.com/qinxujunai/VoiceFlow/blob/master/docs/release-evidence-0.3.3.md
- GitHub Pages deployment run
  https://github.com/qinxujunai/VoiceFlow/actions/runs/36797496829 passed
  from the release commit. The live metadata at
  https://qinxujunai.github.io/VoiceFlow/release-metadata.json identifies
  version `0.3.3`, tag `v0.3.3`, the matching installer URL, size, installer
  digest, and compliance digests.
- The deployed bilingual copy contains `完全离线 · 内置模型 · 无需登录` and
  `Fully offline · Built-in models · No sign-in`, with no unresolved release
  markers. The rendered page and download URL identify `v0.3.3`.
- The release workflow had no Windows signing certificate configured;
  Authenticode verification passed for the expected `NotSigned` state, and
  the release notes disclose that Windows may show a security prompt.
