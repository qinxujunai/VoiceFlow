# VoiceFlow 0.3.10 Windows release verification

Verified on 2026-10-22. Build **261022.1**, Windows file version **0.3.10.1**.

- Build source: `c9df2cc027b1929f51504ec02f747a980b8246bc`, synchronized from upstream `72dc69cb38e0bd300441fea971811c1a67c0ed13`.
- Installer: `VoiceFlow-0.3.10-Windows-x64.exe`, **306742685 bytes**.
- Installer SHA256: `0ba560a26b58794f16510379dea9e720365ac2dc7ec37c719c3e27fb25c1de36`.
- Installed EXE SHA256: `e716d89e73b325c89f88baeeca18806c1c14afcf4135f70db0b3b2f2f01046d0`.

## Local and CI evidence

The upstream baseline passed `scripts/verify.py` with 828 tests. After the narrow-window fix, standalone pytest passed **829 tests**, and `scripts/verify.py --release` passed all 829 tests, 500 lifecycle cycles, strict model-output regression, UI capture, native capsule motion, flagship stress, performance evidence and integration gates. The performance gate consumed retained pipeline measurements; its success is not a fresh physical-microphone latency benchmark or natural-speech accuracy result. The new frozen worker probe exercised 20 synthetic audio-worker cycles and a public WAV through the authoritative and preview workers without recording a microphone or touching the clipboard.

[Windows source/package checks](https://github.com/qinxujunai/VoiceFlow/actions/runs/39804340777) and [macOS source checks](https://github.com/qinxujunai/VoiceFlow/actions/runs/39804340744) passed. macOS checks do not establish a public macOS artifact.

[Exact uploaded installer acceptance](https://github.com/qinxujunai/VoiceFlow/actions/runs/39805855353) passed its installed-candidate job: one fresh install/start, upgrade from public **0.3.9**, uninstall with retained user dictionary/history, matching upload size/digest and actual bundled VC DLL load paths. This is a hosted Windows runner containing development tools, not a pristine consumer OS.

All **87** packaged PE files and **758** direct/delay imports resolved. Frozen Qt Python-source, native Qt resource-byte and pynput source replacement probes passed with the original EXE hash unchanged. The native probe tests loading a changed version resource, not ABI compatibility with an independently rebuilt Qt.

## UI and installed machine

The three settings pages were captured and visually reviewed at application-controlled 100% and 150% effective rendering scale, without changing Windows monitor configuration; native monitor-DPI switching and Narrator remain untested. A 600-logical-pixel narrow-window capture exposed history metadata forcing the delete action outside the viewport. One line enabling metadata wrapping fixed it, with a failing-then-passing real Qt geometry regression. Screenshots are private under `logs/release-0.3.10/ui-dpi100/`, `ui-dpi150/` and `ui/narrow/`.

The actual installation at `D:\Apps\VoiceFlow` was upgraded from 0.3.9.6 using this exact installer. All **500** inventoried payload files matched; all **seven** protected configuration, vocabulary and history files kept their pre-upgrade hashes. The running EXE matched the hash above and reached ready for hotkeys, microphone and authoritative ASR. The actual installed settings screenshot displayed 0.3.10/build 261022.1 and ready status. Unowned older installation files were retained rather than deleted.

Human speech acceptance: the requested F2 test included a **62.186 s** recording on the installed build. The user reported good results after the three-part animation/final-replacement/insertion check. Duration and `clipboard_verified_paste_dispatched` were verified from metadata only; no personal transcript is retained in release evidence. Insertion confirmation is the user's observation, not an automated runtime verification claim.
Closing settings hid the window while the same process remained ready; another normal launch restored that same instance.

## License and public delivery

Locked Python distributions, native DLL/PYD bytes, model assets and original license records are unchanged from 0.3.9. The base-library ZIP container changed, but all 155 member payloads are identical. The five corresponding LGPL source archives match their pinned hashes; the reused source bundle SHA256 is `5137f59bab8df5002446cf2a8910b2105eb3eed6876574c09769857f7160e816`.

[Artifact-bound sign-off](../release/v0.3.10/RELEASE_SIGNOFF.json) and `check_release_compliance.py` passed after exact-installer, installed-data, replacement and human acceptance. See [dependency review](../licenses/release-review-0.3.10.md). The original generated incomplete manifests remain private evidence; only this exact reviewed artifact received approval.
The stable [v0.3.10 Release](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.10) has ten nonempty, unique assets whose GitHub size/digest identities matched local files. An anonymous installer download matched the SHA256 above. [Release-triggered Pages routing](https://github.com/qinxujunai/VoiceFlow/actions/runs/39807538433) and its [protected-master deployment](https://github.com/qinxujunai/VoiceFlow/actions/runs/39807557761) passed. Live download metadata identified the same version, size and digest. A browser retaining the previous `app.js` cache showed an old compatibility version; the follow-up site change versions the script URL and has a failing-then-passing renderer regression. Follow-up deployed browser verification is recorded in the final handoff. The redundant tag-triggered build was canceled before producing another installer, retaining the already-reviewed asset identity and the unchanged fail-closed compliance gate. No GitHub build attestation is claimed for this locally built installer.

## Limits and rollback

Unsigned installer. Authorized natural-speech holdout incomplete; no accuracy superiority claim. No public macOS download. Application-scale captures do not certify Windows monitor-DPI transitions or assistive technology. Retained pipeline performance evidence is identified above.

The local branch `backup/local-20261022` preserves the original checkout head; no tracked edits or local-only commits needed an additional snapshot commit. Existing untracked private artifacts were left intact and excluded from release commits.
A private pre-upgrade backup retains **4,264** program files and the seven protected data files at `tests_runtime/release261022-upgrade/backup`. On readiness or data-integrity failure, stop publication, exit only the identified idle VoiceFlow instance, and restore the program backup without deleting user data or changing shortcut targets.
