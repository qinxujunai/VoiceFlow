# AGENTS.md -- VoiceFlow

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](docs/README.md).

Start documentation work at `docs/README.md`. It separates current contracts,
dated release verification, superseded designs and archived measurements.
Document synchronization dates are not new test dates. Preserve original
evidence, versioned Release materials and pinned third-party license bytes.

## Decisions Not To Undo

Each has a reason; change one only after writing the new reason here.

| Decision | Why | Commit |
| --- | --- | --- |
| Settings pages live in `src/settings_ui/` (one mixin per page); `overlay_webview.py` only composes them | The window was one 3,507-line file. New page code goes into its page module; tests read the shell and the package together (`_settings_source()`, `_method_run()`) | `8fd32c3` |
| Settings look: light sidebar, grouped white cards, one fixed save bar, keycap shortcuts | Native macOS System Settings layout; single save transaction | `1e63302` |
| Capsule text: new glyphs fade in (140 ms), the final replaces the draft in place, a cropped start fades at the edge | Apple dictation feel without breaking the append-only contract below | `1e63302` |
| Center short capsule content (including its indicator) and center final text; long captions retain tail cropping and the edge fade | 2026-10-27 user feedback: short speech and status labels had excessive empty space on the right. Appended glyphs still appear once; centering can adjust the group position as it grows | 2026-10-27 |
| Win32 contract tests carry `@windows_only` | They test Win32 APIs or the Windows native wheel; macOS quality had been red since 2026-10-10 because of them. They still run in Windows quality | `bff8dbc` |
| macOS packaging files live in `installer/macos/` | One place per platform | `66c27cf` |
| Under 20 s the final text is the whole recording; after 0.3 s of quiet following speech it is recognized in the background (`_speculation_due`, 0.6 s silence pad) and used at stop if no speech came after it (`_speculative_result`: noise-floor speech tracker rescanned at stop, then the tail must be non-speech by the ASR worker's VAD and at most 1.5 s); workers write only within their reset epoch | Same accuracy as recognizing at stop (within noise). Stopping 0.8-1.2 s after the last word: wait 0.03-0.40 s instead of 0.45-0.81 s; stopping 0.2 s after: never slower than before. Extra CPU while recording: one background recognition per pause. Using pause-cut pieces from 12 s instead was rejected: about 2.5 points more character errors. Evidence: `docs/stop-latency-evaluation-2026-10-26.md` | 2026-10-26 |
| From 20 s, pieces are cut in the speaker's pause (`_quiet_cut`, verified quiet), at least 4 s, and a piece after a pause cut starts at the cut and is appended without the overlap merge (`_join_segments`); Chinese seams have no space | Cuts at the late endpoint split words, the 1 s overlap duplicated them, and the merge deleted words really repeated across a seam. 30-38 s dictation: 12.7 % -> 11.8 % character errors, stop wait 0.16 s -> 0.21 s (the tail no longer overlaps but starts at an earlier cut) | 2026-10-26 |
| Capsule preview stays append-only with the current bilingual model; no lighter-colour tentative tail | Measured: the unconfirmed guess would appear only ~80 ms earlier; every candidate model emits every 0.6-0.7 s. The 2023-02-20 bilingual model previews closer to the final text but doubles preview CPU and adds ~140 MB | 2026-10-26 |
| A public release needs the artifact-bound license review (`licenses/release-review-<version>.md`, LGPL sources) and installed verification | Compliance gate in `scripts/check_release_compliance.py` is fail-closed by design; do not bypass it in CI | 0.3.9 release |

The stack is already the mature choice for offline dictation on Windows (sherpa-onnx with
SenseVoice and a streaming Zipformer, PySide6, sounddevice, uiautomation); there is no reason
to swap engines without the quality gates below.

## Known Issues And Owner-Only Steps

- Windows 0.3.10/build 261022.1 is released with the exact installer sign-off,
  corresponding LGPL sources and installed-machine verification. See
  `docs/release-validation-0.3.10.md`. Future artifacts still require their own
  sign-off; this release does not approve different dependency or installer bytes.
- Unsigned installer; Windows 10/11 only; no public accuracy figures until enough authorized
  natural speech is collected.

## Handoff Log

- **2026-10-26, Claude**: CI was red since `01befe5` (my 2026-10-25 lock bump): anyio 4.15.1 needs
  typing_extensions >= 4.16.0 on Python < 3.15, and the Windows lock pinned 4.15.0 (I had checked with pip on 3.13 only).
  Bumped to 4.16.0, matching the macOS lock; both locks now resolve with `uv pip compile --python-version 3.12` for
  their platform (the old lock reproduces the failure). The macOS run also hit a timing assert (0.153 s vs 0.15 s) in
  `test_insertion_timeout_uses_the_same_mta_thread_and_never_retries_paste`; the bound is now 0.5 s, still far below the
  hung verifier's 2 s. Lock checks for future bumps: resolve for each target platform at Python 3.12.

- **2026-10-26, Claude**: stop latency (`src/main.py`). Under 20 s: speculative whole-recording recognition at
  pauses, used at stop when only silence follows. From 20 s: pause cuts inside the pause, no overlap or merge after
  them, 4 s minimum, no space at Chinese seams. Preview model and capsule unchanged after measuring five models and a
  tentative tail. An independent review found the merge deleting repeated words at seams, unverified pauses and an
  unenforced minimum; a second review found a cancelled recording's guess reaching the next recording and a
  soft last syllable being dropped; all fixed with tests. Not released. Verified: Linux offscreen suite 793 passed with the same 20
  environment failures as before; new tests in `tests/test_final_coverage.py` fail on the old code;
  `scripts/evaluate_speculative_final.py` and `scripts/evaluate_stop_latency.py` with a -50 dBFS noise floor.
  Details: `docs/stop-latency-evaluation-2026-10-26.md`. Real-microphone feel is still to be judged on Windows.

- **2026-10-25, Claude**: security bumps in both locks (`requirements.lock`, `installer/macos/requirements-macos.lock`):
  anyio 4.14.1→4.15.1 (GHSA-82r6-8w77-94w6 critical), certifi →2026.10.23 (GHSA-6q48-6c7w-9gw2 critical,
  compromised emSign roots), filelock 3.29.4→4.2.4 (GHSA-v4x8-3wr5-3wq8 high). Used only by model download tooling
  (huggingface_hub/httpx); the app itself stays offline. Not released: the next release needs its own artifact-bound
  license review for these versions. Verified: clean venv with huggingface_hub 1.21.0 + the new pins, `pip check` clean;
  packaging/platform/runtime-asset contract tests 56 passed (13 Windows-only skipped on Linux).

- **2026-10-24, Claude**: website header shows "‹ 返回 / ‹ Back" only for visitors who arrived from the
  owner's personal site (it leaves `qxj.back` in this tab's sessionStorage; contract in that repository's
  `docs/back-link.md`). Site-only change. Verified: site tests (22 passed); end-to-end click-through and direct open.

- **2026-10-23, Claude**: website footer links to the owner's personal site
  (「秦徐俊的作品」 / "More by Qin Xujun", per language). Site-only change; no app code,
  installer or Release asset changed. Verified: site language, demo motion and brand
  presentation tests (22 passed); zh/en footer rendered without script errors.

- **2026-10-22, Codex**: released Windows 0.3.10 from `c9df2cc`, after
  829 local tests, release gates, Windows/macOS source checks, exact uploaded
  installer fresh/0.3.9-upgrade/uninstall-data checks and a verified local upgrade.
  All 500 payload files matched; seven protected data files survived unchanged.
  The user completed a 62.186 s F2 acceptance and reported good results. Source
  and installed screenshots, metadata-only speech acceptance and rollback are
  private under `logs/release-0.3.10/` and
  `tests_runtime/release261022-upgrade/backup`.
  Signed review: `release/v0.3.10/RELEASE_SIGNOFF.json`; full public evidence:
  `docs/release-validation-0.3.10.md`. The website follow-up versions `app.js`
  to prevent a cached prior script from overwriting the visible release number;
  its renderer regression failed before the fix and passed after. The redundant
  tag-triggered rebuild was canceled; the reviewed local installer was preserved,
  and no GitHub build attestation is claimed.

- **2026-10-22, Codex**: prepared 0.3.10 build 261022.1 from `72dc69c`,
  preserving `backup/local-20261022` and all unrelated private artifacts.
  Fixed narrow history metadata wrapping with a failing-then-passing native
  geometry regression; full local suite: 829 passed. Updated installed-candidate
  acceptance to upgrade from 0.3.9. Evidence: `logs/release-0.3.10/` (private).
  Release verification, exact installer acceptance, installed upgrade and final
  artifact sign-off must complete before publication; this entry is preparation.

- **2026-10-22, Claude**: settings redesign and capsule text fade (`1e63302`, `e8f345e`), site demo
  and `installer/macos/` (`66c27cf`), design QA record moved into `docs/` (`843c039`), Win32
  tests Windows-only (`bff8dbc`), settings split into `src/settings_ui/` (`8fd32c3`).
  Verified: Linux offscreen full suite identical before and after each change; Windows and
  macOS quality green. On `8fd32c3` Windows quality first failed once because the node process in
  `test_site_demo_motion.py` hung past 15 s (the test takes 0.1 s locally and `site/` was
  unchanged); the re-run passed. If it recurs, look at node startup on the runner first.

## Project Identity

VoiceFlow is a Windows local-first dictation layer. Press **F2**, **Right Ctrl**, or a mouse side button to start recording, press again to stop, and cleaned text is copied to the clipboard and pasted at the current cursor. Press **Esc** to cancel.

The current target is stability: no orphan processes, working tray exit, complete final transcription, clipboard fallback, and truthful docs.

## Run

```bat
start.bat
venv\Scripts\python.exe src\main.py
```

## Verify

Do not use `src\*.py` with `py_compile` on Windows; Python does not expand that glob.

```bat
venv\Scripts\python.exe scripts\verify.py
```

Individual checks:

```bat
venv\Scripts\python.exe scripts\doctor.py
venv\Scripts\python.exe -m py_compile src\main.py src\overlay_webview.py src\hotkey_manager.py src\output_handler.py src\text_cleaner.py src\transcriber.py src\streaming_transcriber.py src\audio_capture.py src\recording_session.py src\vocabulary.py
venv\Scripts\python.exe -m pytest tests -q
venv\Scripts\python.exe test_integration.py
```

## Architecture

```text
src/
  app_controller.py    # stable UI/action facade and runtime state
  main.py              # orchestration, lifecycle, streaming preview
  hotkey_manager.py    # keyboard + pynput mouse side buttons
  recording_session.py # recording lifecycle
  audio_capture.py     # sounddevice microphone adapter
  audio_worker.py      # supervised microphone, reused only after verified teardown
  asr_worker.py        # supervised authoritative-ASR process
  preview_worker.py    # supervised online-preview ASR process
  punctuation_worker.py # optional bounded Chinese punctuation worker
  transcriber.py       # sherpa-onnx ASR
  streaming_transcriber.py # small online ASR for capsule preview
  vocabulary.py        # layered dictionary/corrections
  text_cleaner.py      # deterministic cleanup
  output_handler.py    # clipboard first, then Ctrl+V
  history_store.py     # logs/history.jsonl
  overlay_webview.py   # settings window shell (construction, navigation, events), overlay facade + tray menu
  settings_ui/         # settings pages as mixins composed by _SettingsWindow:
                       #   preferences.py, dictionary.py, history.py, diagnostics.py, style.py
  capsule_native.py    # native black/red capsule, bounded append-only animation
  overlay.html         # retired renderer retained for development comparison
  runtime_bootstrap.py # process-local native thread budget before NumPy imports
  tray_icon.py         # runtime status tray icon
```

The Qt process must not load or call native audio/ASR engines directly in the
normal runtime. Construct `AppController` before the overlay or tray, register
hotkeys before worker initialization, and keep worker IPC bounded. See
`docs/decisions/ADR-004-supervised-runtime-boundary.md`.
The capsule uses native Qt painting; release builds exclude WebEngine/QML/Quick.
Workers dispatch through PyInstaller freeze support before Qt runtime hooks.
OpenBLAS uses one thread per process; the ASR runtime has its own explicit budget.
Do not reintroduce synchronous focus/UIA inspection or optional preview startup
on the recording action path. Preview PCM blocks are at most 100 ms.

## Product Rules

- Offline by default. Do not add cloud ASR, cloud LLM, or hidden network calls.
- Text cleanup preserves wording and repetitions. Only visible dictionary corrections
  may replace words. Punctuation inference preserves lexical content, bypasses technical
  or preserve-format input, and falls back unchanged on failure or timeout.
- Settings use one dirty draft and one save transaction. Missing evaluation audio
  does not block ordinary settings saves; pinned runtime weights remain verified.
- Never lose text. If text exists, it must remain in clipboard and `logs/history.jsonl`.
- Do not restore the previous clipboard after dictation.
- After verified clipboard delivery, revalidate and dispatch one paste to the ordinary
  foreground application observed at stop time unless the target or clipboard
  changed, a physical modifier remains held, or there is positive
  evidence of a blocked target (desktop, secure desktop, incompatible UIPI,
  VoiceFlow's own non-input window, or no valid foreground window). The start
  target is diagnostic context only; transient UIA unknown/group nodes are not
  a clipboard-only gate.
- Only reliable verification of inserted final text means confirmed success.
  Input event dispatch remains unverified and must retain recovery guidance.
- Recovery PCM is temporary local state. Delete it only after verified
  clipboard delivery plus history, or after an explicit user delete action.
- Final output must cover the complete stopped audio; streaming preview is only preview.
- Streaming preview feeds each new PCM sample once to its own online recognizer.
- Never restore rolling-window preview through the final SenseVoice recognizer:
  overlapping retranscription causes delayed chunks and hypothesis rollback.
- Long recordings may progressively cache stable final segments during recording, but stop-time output must still include the remaining tail and cover the complete audio.
- Default triggers are `f2`, `right_ctrl`, `xbutton1`, and `xbutton2`. Do not add combo keys as defaults — suppress=True blocks the individual keys from normal use.
- Tray right-click menu must keep a working `退出` action.
- Keep the overlay small, centered, and quiet.
- If docs disagree with runtime behavior, fix the docs or the code immediately.

## Hotkeys

```yaml
hotkeys:
  push_to_talk: ["f2", "xbutton1", "xbutton2", "right_ctrl"]
  cancel: "escape"
```

All push-to-talk keys are single keys — no combo keys. `f2` uses the `keyboard` package and is suppressed. `right_ctrl` uses `pynput` so left/right Ctrl stay distinct. Mouse side buttons use `pynput` and are not suppressed.

### Key Reference

| Key | Type | Notes |
|---|---|---|
| `f2` | keyboard | Windows default |
| `right_ctrl` | keyboard | detected via pynput virtual key code |
| `xbutton1` | mouse | side button (back) |
| `xbutton2` | mouse | side button (forward) |
| `escape` | keyboard | cancel recording |

### Right Ctrl Implementation

`right_ctrl` is detected via `pynput.keyboard.Listener`, not the `keyboard` library. pynput uses virtual key codes (`VK_RCONTROL` = 0xA3) which are distinct from `VK_LCONTROL` even on keyboards where left/right Ctrl share the same scan code. The `keyboard` library cannot do this because it relies on scan codes only. Since right ctrl is rarely used in typing combos, no suppression is needed — the key press itself produces no character output, and the 0.5s debounce prevents accidental double-fires when used in combinations.

### Anti-pattern: Combo Keys

Never add combo keys like `ctrl+shift+space` via `keyboard.add_hotkey` with `suppress=True`. The `keyboard` library will suppress *every individual key in the combo* (Ctrl, Shift, Space), breaking copy/paste, input methods, and normal typing.

## Output Contract

The output path is:

```text
clean text -> pyperclip.copy(text) -> Ctrl+V -> history.jsonl
```

This is intentional. Even if `Ctrl+V` lands nowhere, the user can manually paste.

## Vocabulary

Primary files:

- `knowledge-base/builtin-ai.txt`
- `knowledge-base/corrections.txt`
- `knowledge-base/user-dictionary.txt`
- `knowledge-base/phrases.txt`

Legacy migration contract:

- v1 `ai-terms.txt`, `company-terms.txt`, and `user-custom.txt` are migration
  inputs only. They must not ship or appear in `hotwords.files`.
- Runtime schema v2 removes retired seed hashes, imports non-seed additions
  from modified legacy files, and then deletes the legacy filenames.

Use `wrong=correct` only in correction files.

## Packaging

- `scripts\generate_icon.py` creates the multi-size `assets\voiceflow.ico`.
- `scripts\create_shortcut.ps1` creates a desktop shortcut.
- `VoiceFlow.spec` is the windowed onedir application build. The Inno installer adds the
  reviewed default model and its license assets.
- Windows installers belong in GitHub Releases, not GitHub Packages. Never publish an
  installer link before the matching versioned Release asset exists.
- Keep generated compliance inventories fail-closed. An artifact-bound review must
  identify the exact installer, EXE, build inputs, licenses and corresponding LGPL
  sources; historical incomplete review flags must not be rewritten as new approval.
- Verify the uploaded installer itself on a disposable Windows runner: single fresh
  install/start, previous-release upgrade, uninstall and retained user data. Do not
  run installer lifecycle smoke under the production Windows user: an isolated
  directory does not isolate the installer's HKCU uninstall registration.
- Synchronize source, installed build, Release assets, bilingual documentation and
  live website metadata before reporting delivery. Keep dated evidence in
  `docs/release-validation-<version>.md`, with exact SHA256 and private rollback paths.
- Pages release events request deployment from `master`; only the deployment job
  enters the protected `github-pages` environment. Do not broaden its branch policy
  to work around a rejected version-tag deployment.
- Never publish a macOS download, badge, or compatibility claim until a separately built,
  signed, notarized, and tested macOS artifact exists.
- macOS public releases use separately named Apple Silicon and Intel disk images built from
  the same version tag as Windows. Follow `docs/platform-release-contract.md`; update the
  website only after each matching Release asset exists and its URL has been verified.

## Product Quality Gates

- Do not expose a model to ordinary users merely because it loads. It must pass pinned-asset
  verification, pathological-output checks, fixed Chinese CER, fixed English WER, latency,
  memory, license, and clean-install gates.
- Model names are implementation details. Ordinary settings expose no model selection,
  download, repair, or switching controls.
- Keep one reliable bundled default. Alternative models remain internal benchmark inputs;
  pinned download, integrity verification, and rollback code is engineering infrastructure.
- Never call a model `更准确`, `高准确` or `最佳` without same-machine, same-corpus evidence.
- Synthetic speech is useful for reproducible regression but cannot replace authorized,
  natural user speech in release accuracy claims.
- Local or cloud polishing is a second stage. Preserve raw transcription, enforce a timeout,
  and fall back to raw text on every failure. No hidden network requests.
- Streaming preview may reveal only confirmed text. Smooth visual presentation must have a
  bounded catch-up time and must be canceled before processing or final output.
- Product and website claims must map to a reproducible test, release artifact, or documented
  limitation. Remove aspirational claims that are not true in the shipped build.
- A public release requires the full verification suite, model quality evidence, packaged
  smoke, clean-machine install/upgrade/uninstall checks, license review, and exact SHA256.

## Troubleshooting

- **A running program is a snapshot.** Verify the actual process executable,
  shortcut target, and runtime-state build before diagnosing source changes.
  Exit the identified VoiceFlow instance from its tray before restarting. Never
  terminate all Python processes, change shortcuts, or interrupt live recording.
- **Frozen builds require rebuilding.** Source edits do not update an installed
  `VoiceFlow.exe`. Record the exact candidate, backup, data hashes, and readiness
  checks for an authorized in-place upgrade; restore the old files on failure.


## Craft Standard

Think, then code. Every visual change must answer: would this belong in a native iOS or macOS app? Animations convey state, not decoration. Whitespace is intentional. Default to subtraction — remove before you add. The reference is not competing dictation tools; it is the restraint of Voice Memos, Notes, and Messages.

Match the existing code as if the same person wrote every line. Indentation, naming, control flow, comment style — follow the neighbors exactly. Before committing, re-read your diff and delete any line not traceable to the stated goal. Surgical, not sweeping.


## Regression Guards

- **Pill flash on new recording.** Prepare the native state and cancel previous
  width/level/fade animation before showing the Qt window. Hide first, then reset
  offscreen. All timers belong to the Qt thread. Normal stop freezes the sample
  boundary, invalidates preview without joining workers, and replaces draft with
  the authoritative final text in place. Confirmed insertion fades silently; fallback
  and failure retain their truthful labels. Never call `show_result(text)` for a
  normal recording stop.

- **Streaming text replay and reverse motion.** The online recognizer owns one
  stream per recording and receives each new PCM sample exactly once. Its
  renderer contract is an append delta plus session generation:
  characters are appended once and are never retracted or replayed. Cadence is
  normally 48 ms, may smoothly accelerate under backlog, and must coalesce
  stale animation after the 600 ms hard lag. Do not restore rolling-window
  SenseVoice preview, full-text `updateStreaming`, common-prefix resets, or
  horizontal transforms.

- **Final text overwritten by streaming preview.** Stop freezes the microphone
  first, then invalidates the preview generation. `_stop_streaming()` may only
  signal cancellation and transfer ownership; it must not join worker threads.
  Session guards prevent stale preview work from updating settling, final, or
  delivery states. The capsule replaces the draft with final text in place.
  Reliably confirmed insertion fades out silently; unverified dispatch and clipboard-only show
  `已复制到剪贴板`, and durable recovery shows `已保存`. Never restore the
  character-count summary or claim paste success.

- **Recording color stability.** Draft and authoritative provenance remains internal.
  Both render in one text color, and the three recording bars remain red until recording
  actually ends. Do not couple recognition confidence to visible color changes.

- **One recording entry point.** Do not put a transcript input/result box on the
  settings home page. Settings may show plain shortcut guidance. F2, Right Ctrl, and
  mouse side buttons use the same controller path; no independent Trial/试说 session
  or result-writeback path is allowed.

- **Long dictation preview cost and coverage.** The lightweight online preview
  and SenseVoice progressive final cache use separate workers. Active recording
  PCM must not be discarded. Progressive final segments carry explicit sample
  ranges; final assembly must prove continuous coverage from sample zero to the
  frozen stop sample, otherwise retry the retained full PCM. Do not output
  preview text as final unless final transcription is empty and the explicit
  safety fallback is the only recoverable text.

## Coding Rules

- Keep changes narrow and tied to the product contract.
- Prefer readable state transitions over clever async behavior.
- Do not reintroduce clipboard restore.
- Do not add default shortcut keys that interfere with normal typing.
- Do not reintroduce overcomplicated processing animations unless they are tied to a measurable state.
