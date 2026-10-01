# VoiceFlow 0.3.6 release verification evidence

Status: candidate verification in progress, 2026-10-01.

## Identity and review

- Version `0.3.6`, build `261001.4`.
- Expected installer `VoiceFlow-0.3.6-Windows-x64.exe`.
- Adversarial review found destructive data-clear/recovery races, premature
  idle state during cancellation, and insufficient update/site digest and URL validation.
- Regression tests cover recording phases, competing clear/recovery/start,
  failed cancellation, shutdown preservation, inconsistent digests, duplicate
  assets, incomplete uploads, empty assets, and bounded network responses. Website tests also reject mismatched asset
  URLs and checksum-file size/digest tampering.
- Data and update behavior is specified in `upgrade-and-data-contract.md`.

## Verification scope

Local verification is being repeated for the corrected candidate. Required gates:
420 tests, 500 recording-state cycles, fixed-model benchmark, 10,000-cycle
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


## Additional crash and UI review

A real subprocess regression reproduced an audio worker surviving forced UI
termination. Native audio, final-ASR and preview workers now wait on their
parent process sentinel and exit when the owning process dies. Installed
smoke verifies all recorded worker PIDs disappear within five seconds before
uninstall, preventing taskkill from masking orphans. Upgrade and uninstall
compare isolated configuration, vocabulary and history files.

The prior candidate is retained as WITHHELD, never advertised as a release.
One early CI installer-readiness timeout was not reproduced in the exact-tag
validation; no timeout threshold was relaxed. Diagnostics are retained for
any subsequent failure.

Mobile browser audit identified three contrast failures (accessibility 96).
After a narrow CSS correction, local Lighthouse accessibility, best practices,
SEO and agentic browsing all scored 100 with zero failed audits. Public copy
now describes delivery fallback and explicit errors instead of universal input
compatibility or zero-loss guarantees. Live deployment remains to be verified.
