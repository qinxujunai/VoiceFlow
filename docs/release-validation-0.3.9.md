# VoiceFlow 0.3.9 Windows release verification

> Documentation sync: **2026-10-22** · Current release evidence; dated results retained. Synchronization date is not a new test date. [Current index](README.md).

Verified on 2026-10-21. Build **261021.6**, Windows file version **0.3.9.6**.

- Build source: `4f9ab9c7c980f64c27283a2edb38fb716b537f40`.
- Verification workflow: `092afce9a9a72facfab173bee84bf73606580ea2`; the subsequent change is limited to unpublished-release access for the manually dispatched CI job. Runtime/build inputs are unchanged.
- Installer: `VoiceFlow-0.3.9-Windows-x64.exe`, **306692767 bytes**.
- Installer SHA256: `73772f0ad71609c44c26357768ab5d42fbe4b926ed897ddcf583b937f13f19b5`.
- Installed EXE SHA256: `402b00a77b1244f6b6a521df8b531a2aa1bbe218d713c93d1898aa25f5ccab47`.

## Evidence

The full local verification passed with **822 tests**, integration, deterministic text protection, lifecycle/fault stress, native motion, UI and recorded performance gates. Recorded historical latency evidence is distinguished from current native UI measurement; neither establishes a new natural-speech accuracy result.

[Windows source and packaged checks](https://github.com/qinxujunai/VoiceFlow/actions/runs/39555725700) passed. [Exact uploaded installer acceptance](https://github.com/qinxujunai/VoiceFlow/actions/runs/39557909782) verified a single fresh installation/start, upgrade from public 0.3.8, uninstallation, user dictionary/history retention, asset size and SHA256, and actual loading of bundled VC runtime DLLs. The Windows hosted image contains development tools; this is not a claim of a pristine consumer OS test.

All 87 packaged PE files and their 758 direct/delay imports resolved. Qt Python-source, native Qt DLL and pynput replacement checks passed against the exact final EXE. The native Qt test changes only version-resource bytes, so it demonstrates loader replacement, not compatibility with an arbitrary rebuilt Qt ABI.

The actual installation at `D:\Apps\VoiceFlow` was upgraded in place. All 492 packaged files matched the release inventory, all seven protected settings/vocabulary/history files retained their hashes, and hotkeys, audio, preview and final workers reached ready. The actual settings window displayed build 261021.6. Closing it hid the window while the same process stayed ready; normal launch restored settings.

See [artifact-bound sign-off](../release/v0.3.9/RELEASE_SIGNOFF.json), [dependency review](../licenses/release-review-0.3.9.md) and the versioned Release attachments for exact inventories and corresponding LGPL sources. Historical development manifests retain their incomplete flags; the current sign-off identifies the precise reviewed artifact.

## Public delivery recheck — 2026-10-22

The latest stable Release and live website metadata were rechecked as 0.3.9,
with the installer size and SHA256 above. The installed EXE still reports
0.3.9.6 and matches the recorded application SHA256. This is a state recheck,
not a repeat of the 822-test run or the physical installation performed on
2026-10-21.

[Post-merge Windows checks](https://github.com/qinxujunai/VoiceFlow/actions/runs/39559627823)
and [the subsequent README-only revision](https://github.com/qinxujunai/VoiceFlow/actions/runs/39566885381)
completed successfully. [Pages deployment](https://github.com/qinxujunai/VoiceFlow/actions/runs/39559227990)
serves the verified 0.3.9 download. The public installer was anonymously
downloaded and hashed on 2026-10-21; all ten uploaded assets matched their
recorded digest identities. That day's browser acceptance passed two automatic
loops with no Replay control, text filter, text transform, overflow or page error.

[PR 25](https://github.com/qinxujunai/VoiceFlow/pull/25) and
[PR 28](https://github.com/qinxujunai/VoiceFlow/pull/28) are merged. The Pages
fix routes stable release events to a deployment requested from `master`,
preserving the environment's branch protection. Its regression test passed;
the next stable tag must still verify that complete event path. No GitHub
build-provenance attestation is claimed for the locally built installer.

## Remaining limits and recovery

The installer is unsigned. Authorized natural-speech holdout coverage is incomplete; model weights are unchanged and no accuracy superiority is claimed. macOS checks still have Windows API test-adaptation failures; this release and sign-off cover Windows only and expose no macOS download.

A verified private pre-upgrade backup of 4,255 program files and the seven protected data files is retained locally at `output/voiceflow-upgrade-2026-10-21/backup`. It is not included in public assets. On a readiness or data-integrity failure, stop publication and restore that program backup without deleting user data or changing shortcut targets.
