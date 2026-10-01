# VoiceFlow 0.3.6 release verification evidence

Status: published and public assets/site verified, 2026-10-01.

## Identity and traceability

- Version `0.3.6`, build `261001.4`.
- Immutable annotated tag `v0.3.6`, source commit `4cc18abf49eb7cf34bb9847cf0fd94cc7f8737f7`. The tag is not signed.
- [Stable Release](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.6) published at `2026-10-01T11:05:27Z`.
- Exact-source [Windows quality](https://github.com/qinxujunai/VoiceFlow/actions/runs/36851795997), [macOS quality (Apple Silicon and Intel)](https://github.com/qinxujunai/VoiceFlow/actions/runs/36851795954), [Windows release](https://github.com/qinxujunai/VoiceFlow/actions/runs/36851833099), and [Pages deployment](https://github.com/qinxujunai/VoiceFlow/actions/runs/36853190109) completed successfully. macOS code checks do not establish a supported macOS package.
- `gh attestation verify <downloaded installer> --repo qinxujunai/VoiceFlow --format json` exited zero. Verified provenance identifies the source commit above, tag `refs/tags/v0.3.6`, release workflow and installer SHA256 below.

## Adversarial fixes

- Clear-data, recovery and recovery-delete actions atomically reserve idle before touching data; recording cannot race destructive cleanup.
- Cancellation remains busy until cleanup finishes. Failure marks runtime degraded instead of allowing another session against active audio.
- Update checks reject duplicate, empty or incomplete assets, malformed or oversized responses, inconsistent API/checksum digests and incorrect URLs. Site preparation verifies exact versioned URLs and checksum-file bytes.
- A real subprocess regression reproduced a microphone worker surviving a killed UI. Audio, final-ASR and preview workers now watch their owning process sentinel. Installed smoke requires worker PIDs to disappear within five seconds before uninstall, so uninstall cannot mask orphan processes.
- Native UI and website contrast improved; public copy describes ordinary application paste, fallback and explicit failure instead of universal input compatibility or zero-loss guarantees.

See `upgrade-and-data-contract.md` for data and manual-update behavior.

## Published bytes

All four assets were downloaded from the public Release. Byte sizes and SHA256 match GitHub asset metadata; the three unique checksum-manifest entries also match the downloaded installer, SBOM and notices. SBOM application version is `0.3.6`. Installer version strings are `0.3.6+261001.4` and `0.3.6`.

| Asset | Bytes | SHA256 |
| --- | ---: | --- |
| VoiceFlow-0.3.6-Windows-x64.exe | 362533616 | `4014a40379e199eb41f23f754bdd02f55985f4d325817533a161b9ed2bea06b1` |
| SHA256SUMS.txt | 270 | `815fdf7e6c8e71e40c1829942a54588c6d939f7e554872861bc14f9ce78c4ea5` |
| SBOM.cdx.json | 16825 | `6376fe3464dabc1b8b9ddabcfbdbea3100b28b34f171eea83440c9f23ecbab74` |
| THIRD_PARTY_NOTICES.md | 3363 | `94a2f5c8118e6c286b463057f70eb8255b30183f3e61d7d36ad8622489a59033` |

Windows Authenticode status is `NotSigned`: provenance verification does not replace a Windows code-signing certificate. No macOS download is advertised.

## Acceptance results

- Local `scripts/verify.py --release` passed; final local suite: **420 passed**. Hosted Windows release suite: **419 passed, 1 skipped** (environment-dependent).
- Recording-state 500 cycles, 10,000-cycle fault stress, one-hour synthetic PCM recovery, 5,000 delivery faults, 50,000 Unicode fuzz cases, integration, capsule motion and DPI UI gates passed. Synthetic PCM storage is not an hour of actual live speech. Sanitized UI fixtures cover 100/125/150/200% scaling.
- Release workflow verified the downloaded previous `v0.3.4` installer checksum, installed it, upgraded to this candidate, preserved configuration/vocabulary/history, verified bundled model/license assets and packaged runtime startup, forced UI exit with no surviving native workers, then uninstalled while preserving user-owned data. Installer smoke passed without relaxing the 30-second runtime readiness limit.
- Fixed reference benchmark passed pathological-output checks. The small two-sample corpus measured default-model Chinese CER `0.000` and English CER `0.045`; this is not broad natural-speech accuracy evidence.
- Performance gates reuse existing recorded evidence. This patch does not claim new natural-speech accuracy or latency measurements.
- Live [website](https://qinxujunai.github.io/VoiceFlow/) metadata, Chinese and English download links, GitHub Latest Release and both published READMEs agree on `v0.3.6` and the installer digest above. Live update checker returns `up_to_date` for `0.3.6` and `available` for `0.3.4` with that digest.
- Live Chinese mobile (390px) and English desktop (1440px) browser review found no horizontal overflow; language switching retained the correct asset URL. Console audit found no errors/warnings/issues. Both live Lighthouse audits scored accessibility, best practices, SEO and agentic browsing **100**, with **52 passed, zero failed**. These audits exclude performance.

## Limits and rollback

Two earlier candidate Windows CI runs had installer readiness timeouts ([first](https://github.com/qinxujunai/VoiceFlow/actions/runs/36847493043), [later](https://github.com/qinxujunai/VoiceFlow/actions/runs/36851415052)). The underlying cause is not established. Final exact-source Windows quality and release upgrade smoke passed; that does not prove startup timing is reliable on every machine. Diagnostic output and the unchanged readiness gate remain. The macOS subprocess fixture also needed to retain its shared heartbeat until spawn completed; final macOS checks passed after that test-fixture correction.

Automated isolated install/upgrade/uninstall checks do not cover every Windows version, microphone, foreground application, real user voice or failure mode. There is no zero-defect or best-product claim. Natural user speech evaluation and Windows code signing remain gaps.

The withheld `v0.3.5` candidate has no public Release; its tag is preserved. Previous public `v0.3.4` tag and assets remain the rollback reference. Existing tags/assets were not rewritten. Untracked `creative/`, `output/`, `.serena/` were excluded from edits and commits.
