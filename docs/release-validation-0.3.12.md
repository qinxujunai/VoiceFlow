# VoiceFlow 0.3.12 Windows release verification

Verified on 2026-11-03. Build **261103.1**, Windows file version **0.3.12.1**.

- Build source: `fb1312c64c7d63940fd6393feee433d82710c1b9` (frozen; later documentation and website commits do not change the installed executable).
- Installer: `VoiceFlow-0.3.12-Windows-x64.exe`, **306907346 bytes**.
- Installer SHA256: `9495f143a7c4f5da0c43d962d34d70658e35cb9f3756112019af853efa343b27`.
- Application EXE SHA256: `b50024faed8660c2df4135f9ddd3f51e424861d32d0d0248ba62328bcdb92c81`.

## What changed

Hold to talk (a press held 0.3 s or longer stops on release; a tap still toggles; 设置 → 按键方式), a silent finish after a sent paste, seam punctuation in long and mixed dictation, and split or sound-alike dictionary terms. Release notes: [RELEASE_NOTES.md](../release/v0.3.12/RELEASE_NOTES.md).

An independent review of `706d409..d4f4f59` found that the first sound-alike rule rewrote ordinary English (「I could code that」 → 「I Claude Code that」), that problem notices after a sent paste were drawn into the fading capsule and hidden after 140 ms, that a hold release could be dropped and leave the microphone on, and that split terms crossed line breaks and turned 「Hugging Face」 into 「HuggingFace」. All were fixed with failing-then-passing tests; Codex then fixed a release-during-key-validation race, separated 「已粘贴」 from 「已发送粘贴」 in history and added the punctuation model to CI and installer checks (`fb1312c`). The review's simulations (150 random key interleavings, ten timing scenarios) end with no recording left running.

## Local evidence

`scripts/verify.py --release` passed: **926 tests**, 500 lifecycle cycles, strict model-output regression, UI capture, native capsule motion, flagship stress, performance evidence and integration. Same-machine synthetic stop-to-paste P95 was regenerated on 2026-11-03: 390.7 / 391.7 / 493.3 ms for 0–10 s / 10–60 s / 120 s (gates 500 / 700 / 2500 ms; 2026-10-27: 323.8 / 288.5 / 386.3 ms), measured from the frozen source before the environment fix below while the owner's source build and other agents were running. It is not a physical-microphone benchmark or an accuracy claim.

Before freezing, the repository virtual environment had drifted from `requirements.lock` in 15 packages (cffi 2.1.1, pyinstaller-hooks-contrib 2026.9 and others, installed when the clone was recreated on 2026-11-02). A first frozen build packaged cffi 2.1.1 and was discarded. The locked versions were reinstalled (`pip check` clean, 55 of 55 pins matching), the release gate was rerun and the application was rebuilt; the artifact generator confirmed every frozen distribution matches the lock.

Compared with the signed 0.3.11 package, only the executable among 87 PE files changed; all 86 DLL/PYD files match, all 155 `base_library.zip` members match and the notice manifest is identical. Static direct and delay imports: **87** PE files, **758** imports, zero missing. Frozen Qt Python-source, native Qt resource-byte and pynput replacement probes passed with the original EXE hash unchanged. Details: [dependency review](../licenses/release-review-0.3.12.md).

## Isolated Windows

The exact installer was uploaded to the draft candidate `v0.3.12-candidate.1.1` (GitHub digest equal to the local SHA256) and exercised by [run 41617554295](https://github.com/qinxujunai/VoiceFlow/actions/runs/41617554295). Its installed-candidate job checked the upload size, digest and checksum file, then passed one fresh install and start, an upgrade from the public **0.3.11** installer (its own published checksum verified), uninstall, and user dictionary and history retained unchanged. The installed EXE hash matched the application hash above; installed model sizes and SHA256, frozen runtime mode, preview readiness, a live punctuation worker, VC runtime DLLs loaded from the installed payload and worker exit with the UI were all checked. The same run's source tests and package smoke passed. This is a hosted Windows runner with development tools, not a pristine consumer machine.

## Human acceptance

The owner dictated with a real microphone on an earlier 0.3.12 development source build (short, paused 15 s and 30 s+ recordings) and reported faster text and better accuracy, then directed publication without hand-testing the installed build. No human acceptance of this exact installer is claimed. The owner's installed copy at `D:\Apps\VoiceFlow` was not upgraded.

## License and public delivery

[Artifact-bound sign-off](../release/v0.3.12/RELEASE_SIGNOFF.json) was written only after the exact-installer, replacement and package checks above, and `scripts/check_release_compliance.py` passed on the signed materials; the generated unsigned originals are kept privately. The owner directed publication in this session. The stable [v0.3.12 Release](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.12) was published on 2026-11-03 (10:42 UTC) from tag `v0.3.12` at `fb1312c` with eleven assets: installer, `SHA256SUMS.txt`, SBOM, notices, provenance, sign-off, release notes, dependency review, LGPL sources, build inputs and verification bundle. Every GitHub digest matched the local SHA256 and the checksum file. An anonymous download of the installer matched the SHA256 above.

The tag also started a Release rebuild ([run 41621550448](https://github.com/qinxujunai/VoiceFlow/actions/runs/41621550448)); it was canceled before producing another installer, so the reviewed asset identity stands and no GitHub build attestation is claimed for this locally built installer. The release event's [Pages request](https://github.com/qinxujunai/VoiceFlow/actions/runs/41621551851) and the [protected-master deployment](https://github.com/qinxujunai/VoiceFlow/actions/runs/41621567304) succeeded. The live page reports 0.3.12, links to the exact installer above, describes hold to talk in both languages without the former development-build note, and its capsule illustration shows 「已复制，按 Ctrl+V 粘贴」 as the app does.

## Limits and rollback

Unsigned installer. Authorized natural-speech holdout incomplete; no accuracy superiority claim. No public macOS download. Known follow-ups from the review: a press held while the previous dictation is still finishing starts nothing and shows nothing; holding Right Ctrl and pressing Esc opens the Start menu; the settings home text describes hold-to-talk even when 按键方式 is taps only; accidental holds of 0.3 s or longer leave recoverable recordings; the CI-built installer includes the staged models twice.

Private evidence (not in Git): `tests_runtime/release261103-evidence/` (logs, package comparison, native closure, performance evidence before regeneration), `tests_runtime/release261103-{qt-python,qt-native,pynput}/`, `tests_runtime/release261103-ci/` and the anonymous download in `tests_runtime/release261103-public-download/`. Rollback: the previous verified installer remains the public [v0.3.11 Release](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.3.11). 0.3.12 only adds the optional `hotkeys.trigger_mode` setting (missing means `auto`, and 0.3.11 ignores it), so reinstalling 0.3.11 keeps configuration, dictionaries and history.
