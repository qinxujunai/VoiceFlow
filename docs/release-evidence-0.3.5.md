# VoiceFlow 0.3.5 release verification evidence

Status: candidate verification in progress, 2026-10-01. Public verification
must complete before this release is called shipped.

## Identity and review

- Version `0.3.5`, build `261001.3`.
- Expected installer `VoiceFlow-0.3.5-Windows-x64.exe`.
- Adversarial review found destructive data-clear/recovery races, premature
  idle state during cancellation, and insufficient update digest validation.
- Regression tests cover recording phases, competing clear/recovery/start,
  failed cancellation, shutdown preservation, inconsistent digests, duplicate
  assets, incomplete uploads, empty assets, and bounded network responses.
- Data and update behavior is specified in `upgrade-and-data-contract.md`.

## Verification scope

Full local release verification passed for the final versioned candidate:
416 tests, 500 recording-state cycles, fixed-model benchmark, 10,000-cycle
fault stress, one-hour PCM recovery, Unicode fuzz, DPI UI captures, capsule
motion, recorded performance evidence, and integration transcription.

Performance gates reuse the existing recorded corpus; this patch does not
claim a new natural-speech accuracy or latency benchmark. UI captures use
sanitized fixtures. Public Windows artifacts still require packaged startup,
previous-version upgrade and installer smoke, license review, checksum/provenance, and live site verification.

Windows signing credentials are unavailable: installers remain unsigned.
Automated isolated install/reinstall/uninstall smoke does not cover every
Windows version, hardware device, foreground application, or real user voice.
No macOS installer is advertised. Untracked `creative/`, `output/`, `.serena/`
are excluded from all edits and commits. Previous release `v0.3.4` is retained
as the rollback reference; existing tags and assets are not rewritten.
