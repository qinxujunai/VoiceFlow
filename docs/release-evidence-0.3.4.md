# VoiceFlow 0.3.4 release verification evidence

Status: release candidate prepared from the `v0.3.4` tag. This record is
updated after the tag-driven Windows release and Pages deployment complete.

## Candidate identity

- Version: `0.3.4`
- Build: `261001.2`
- Windows asset: `VoiceFlow-0.3.4-Windows-x64.exe`
- Required integrity asset: `SHA256SUMS.txt`

## Local verification

The release candidate must pass the following checks before the tag is pushed:

- source tests and release verification;
- clean PyInstaller build using `VoiceFlow.spec`;
- packaged runtime readiness smoke;
- protected-worktree audit confirming that untracked `creative/`, `output/`,
  and `.serena/` files were not changed.

The local machine does not provide Inno Setup or a Windows signing certificate.
The matching installer, installer lifecycle smoke, signing state, checksums,
SBOM, and third-party notices are therefore produced and verified by the
tag-driven GitHub Actions release workflow.

## Public verification

After publishing, this document records the exact Release URL, workflow run,
asset names and sizes, installer SHA-256, Pages deployment run, live metadata,
and the README/site text comparison. A release is considered complete only
when every public surface identifies `0.3.4` and the installer digest matches
the published `SHA256SUMS.txt` entry.
