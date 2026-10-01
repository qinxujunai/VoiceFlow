# VoiceFlow 0.3.4 release verification evidence

Status: published and verified on 2026-10-01. The public Release, download
assets, README, Pages deployment, and live site all identify `0.3.4`.

## Candidate identity

- Version: `0.3.4`
- Build: `261001.2`
- Windows asset: `VoiceFlow-0.3.4-Windows-x64.exe`
- Required integrity asset: `SHA256SUMS.txt`
- Release workflow: [36814358353](https://github.com/qinxujunai/VoiceFlow/actions/runs/36814358353)
- Public Release: [v0.3.4](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.4)

## Local verification

The candidate passed the following checks before the tag was pushed:

- `venv\\Scripts\\python.exe -m pytest tests -q`: `401 passed`;
- `venv\\Scripts\\python.exe scripts\\verify.py --release`: passed, including
  stability 500/500, flagship stress, UI quality, performance, and integration;
- clean PyInstaller build using `VoiceFlow.spec`;
- packaged runtime readiness smoke and frozen-package audit with no ICU DLLs;
- Windows quality workflow [36813282770](https://github.com/qinxujunai/VoiceFlow/actions/runs/36813282770): passed, including the complete offline installer smoke;
- macOS quality workflow [36813282811](https://github.com/qinxujunai/VoiceFlow/actions/runs/36813282811): Apple Silicon and Intel passed;
- protected-worktree audit confirmed that untracked `creative/`, `output/`,
  and `.serena/` files were not changed or staged.

The local machine does not provide Inno Setup or a Windows signing certificate.
The matching installer and installer lifecycle smoke were produced and
verified by the tag-driven workflow. No signing certificate was configured;
the Release notes disclose that the Windows installer is unsigned and may
show a security prompt.

## Public verification

The published assets were checked individually:

| Asset | Size | GitHub SHA-256 digest |
| --- | ---: | --- |
| `VoiceFlow-0.3.4-Windows-x64.exe` | `362551874` bytes | `ca1535a095fe156790b15813aa38956f884e1839dfe2e955326a355eeb1b8d30` |
| `SHA256SUMS.txt` | `270` bytes | `2b5663dbd8e2c9aebe2e972659d6c471276df51a626398b5f2b6fe226fff3419` |
| `SBOM.cdx.json` | `16825` bytes | `0ef9adfe34267cb7ec2f8de028f27bca1131dc62b2beab5dfd4cb597cb3d8d80` |
| `THIRD_PARTY_NOTICES.md` | `3363` bytes | `94a2f5c8118e6c286b463057f70eb8255b30183f3e61d7d36ad8622489a59033` |

The installer was downloaded from the public Release and its computed SHA-256
matched the unique installer line in `SHA256SUMS.txt`.

Pages deployment [36815141441](https://github.com/qinxujunai/VoiceFlow/actions/runs/36815141441)
passed. The live site at
[qinxujunai.github.io/VoiceFlow](https://qinxujunai.github.io/VoiceFlow/)
returns the matching installer URL, `v0.3.4`, Windows x64 compatibility, and
the offline/no-sign-in copy. Live `release-metadata.json` reports version
`0.3.4`, installer size `362551874`, and the same installer SHA-256. The live
master README contains the `0.3.4` evidence link, upgrade/data contract link,
and local-data wording.

The release is considered complete because every public surface identifies
`0.3.4` and the installer digest matches the published `SHA256SUMS.txt` entry.
