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
tag workflow must pass those checks again before this evidence is considered
final.

## Public-surface checks after publishing

The following checks remain release gates and must be recorded against the
published v0.3.3 assets:

- GitHub Release is stable, points at the v0.3.3 tag, and contains exactly the
  Windows installer plus `SHA256SUMS.txt`, `SBOM.cdx.json`, and
  `THIRD_PARTY_NOTICES.md`.
- The installer asset digest equals the v0.3.3 `SHA256SUMS.txt` entry.
- README Chinese and English links resolve to this evidence document.
- GitHub Pages `release-metadata.json`, rendered version, download URL, and
  asset digests all identify v0.3.3.
- The deployed bilingual copy contains `完全离线 · 内置模型 · 无需登录` and
  `Fully offline · Built-in models · No sign-in`, without unresolved release
  markers.
