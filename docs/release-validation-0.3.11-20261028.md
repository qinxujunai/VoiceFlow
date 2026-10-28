# VoiceFlow 0.3.11 release and handoff — 2026-10-28

## Current delivery

Windows **0.3.11 / build 261028.3** is published as [v0.3.11](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.11). Frozen source commit `dfde0e2bce61f6627acf3e0ef2da4f188245bf6f`; later documentation and website commits do not change the installed executable. Installer SHA-256 `0b200ecb27eead9adba33cc63f53a0360aef497044a5c690bda73e5ca72b241a`, 306756611 bytes. Installed program files (493), seven models and seven protected data files were hash-verified before application start.

[Website](https://qinxujunai.github.io/VoiceFlow/) deployment [40649233063](https://github.com/qinxujunai/VoiceFlow/actions/runs/40649233063) succeeded; the live page shows 0.3.11, the revised Chinese copy, and points to the exact public installer. Anonymous full download SHA-256 matches the installed candidate. Website metadata, source and installed build remain separate states; recheck them before future releases.

## Changes and verification

Silent dictation cancels without leaving an error; real capture failure retains its separate recovery path. The waveform stays anchored to the capsule's left edge, text is centered within the right-hand area, and width adjusts smoothly as text grows. The user confirmed the final installed layout and usability. Chinese text render captures at four widths are retained locally. The full `scripts/verify.py --release` passed with **862 tests**; site language/motion checks passed (3). The [exact-installer Windows run 40646034963](https://github.com/qinxujunai/VoiceFlow/actions/runs/40646034963) passed fresh installation, 0.3.10 upgrade, uninstall, and user-data retention. Hosted Windows has development tools; it is not a pristine consumer machine.

User testing on the final build included a 44.964-second run (`segments_plus_tail`) and a 14.292-second run (`speculative_full`). The user accepted the result and explicitly directed release without further repeated testing. Separate screenshots and individually recorded feedback for all three originally requested utterances were not captured; no such evidence is implied. Programmatic capsule images are not natural-speech screenshots.

The prior same-machine synthetic stop-to-paste P95 measurements were 323.766 / 288.492 / 386.296 ms versus historical 426.809 / 454.219 / 541.246 ms for 0–10 s / 10–60 s / 120 s. They predate the final UI build and are not a new exact-build measurement or an accuracy claim.

## Artifact review and limitations

[Dependency review](../licenses/release-review-0.3.11.md), [sign-off](../release/v0.3.11/RELEASE_SIGNOFF.json), SBOM, provenance, notices, checksums, five matching LGPL source archives, build inputs and a sanitized verification bundle accompany the public release. Exact-build Qt Python, Qt native-resource and pynput replacement tests passed; 87 PE files and 758 imports had zero missing. The installer is unsigned; no public macOS artifact or comparative accuracy improvement is claimed.

Tag creation also started a separate Release rebuild [40649222704](https://github.com/qinxujunai/VoiceFlow/actions/runs/40649222704); it was canceled to preserve the already reviewed exact installed installer. It is not a passing release-build workflow.

An earlier candidate lacking models was labeled invalid and its workflow canceled. The following candidate's isolated job failed because its checksum asset was absent; the final candidate had a valid checksum and passed. Preserve these historical failures, not as current delivery failures.

## Local recovery

Original local changes are preserved on branch `backup/local-20261027`; prior candidates and evidence are under `E:/01_Projects/AI_core/release-evidence-20261027/`. `voice-data-before-right-center-upgrade.zip` is the latest pre-install user-data backup and contains private data; do not publish it. Superseded local trial commits are preserved on `backup/local-master-20261028-pre-cloud`; local `master` tracks the fetched `origin/master`.
