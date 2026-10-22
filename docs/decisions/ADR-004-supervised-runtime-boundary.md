# ADR-004: Stable UI controller and supervised native workers

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](../README.md).

- Status: Accepted; used by the 0.3.9 Windows release. See [release verification](../release-validation-0.3.9.md).
- Date: 2026-08-24

## Context

VoiceFlow previously created the settings window and tray before all callbacks
were available. Some controls therefore retained empty callbacks for the life of
the process. Global hotkeys were also registered only after both recognizers had
loaded, so one model failure could make F2 appear dead. Finally, PortAudio and
native ONNX calls shared the application process; a blocked driver or recognizer
could prevent the settings window from responding or exiting.

## Decision

Construct one `AppController` before creating any UI. UI, tray, hotkeys, and
history actions bind only to this stable controller. Actions are serialized by a
bounded dispatcher and return `ActionResult`; controls never call audio, ASR,
clipboard, or history implementations directly.

The Qt process owns presentation, hotkeys, delivery, and durable history. Three
supervised child processes own the native failure surfaces:

1. a supervised microphone process (see the 2026-10-04 amendment below);
2. a persistent online-preview recognizer process;
3. a persistent authoritative-final recognizer process.

Every process has bounded IPC, a heartbeat, and a hard termination path. Preview
messages and UI updates retain the existing session generation guard. Complete
PCM for preview remains mirrored in the parent. The audio worker owns the complete
authoritative PCM and the recovery journal (see the 2026-10-06 amendment below).
That deliberate copy costs
about 115 MB for one hour of 16 kHz mono PCM and must be included in memory gates.

Hotkeys start before model initialization. During `STARTING`, F2 produces an
immediate "正在准备" result. Initialization failure moves the controller to
`DEGRADED`; F2 remains responsive and reports that dictation is temporarily
unavailable instead of failing silently.

## Consequences

- A blocked driver or native recognizer can no longer freeze Qt navigation.
- Settings actions cannot capture an uninitialized callback.
- A child failure preserves the current recording and is visible through a
  stable error code in `runtime-state.json`.
- Frozen packaging must support `multiprocessing.freeze_support()` and include
  all worker modules.
- The candidate uses more memory than a single-owner PCM design. Moving preview
  and recovery PCM transfer into one shared ring buffer is a future optimization,
  not a release blocker unless measured memory exceeds the release budget.
- Worker restart never repeats a paste or silently retries an authoritative
  transcript; the durable recovery path remains the source of truth.

## Rejected alternatives

- **Late callback injection:** keeps the initialization race and makes button
  behavior depend on window creation timing.
- **More cleanup threads:** cannot recover a permanently blocked native call and
  permits unbounded thread growth.
- **Load models before hotkeys:** repeats the silent-F2 failure mode.
- **Automatic force-kill of an unresponsive existing instance:** risks losing a
  live recording; the UI must offer an explicit restart choice instead.

## 2026-10-04 amendment

Reuse a healthy microphone worker after stop/cancel only when its acknowledgement
confirms that every stream teardown thread has finished. Otherwise terminate the
worker and preserve mirrored PCM. This removes repeated Python/native-library
startup between healthy sessions without relaxing blocked-driver recovery.
Worker dispatch precedes frozen Qt hooks, and process-local OpenBLAS is limited
before NumPy import. Presentation is native Qt Widgets; see ADR-005.

## 2026-10-06 recovery amendment (development source)

The microphone worker journals accepted PCM directly through a bounded background
writer before publishing optional preview events. Preview IPC carries absolute
sample offsets; an IPC gap disables the incomplete mirror instead of corrupting
sample positions. Stop returns complete worker PCM through shared memory and closes
the journal. The host may delete closed PCM only after verified clipboard delivery
and history, or explicit cancellation/deletion. Parent death freezes acceptance
and allows at most two seconds for journal flush before forced worker exit.

Disk errors and queue/storage limits stop further acceptance, are reported to the
host, and request normal finalization of retained PCM. Metadata IO does not hold
the callback-side lock. Undelivered recordings never expire silently; a 512 MiB
total PCM budget and 64 MiB disk reserve refuse new storage rather than evicting
old sessions. The recovery PCM and schema-v1 format stay compatible.

Deterministic microphone-boundary crash and queue tests verify this source change.
Packaged fault acceptance and long-session resource gates remain required.

## 2026-10-06 native inference amendment (development source)

Silero speech-presence initialization and inference run in the authoritative ASR
worker before recognizer inference, using unchanged thresholds and full PCM.
The same result response carries text and speech presence; progressive silence
segments can commit continuous coverage without rescanning them in the host.
Microphone device enumeration also runs in the audio worker, with a cached list
exposed through AppController. The Qt host does not import sounddevice during
normal startup. Standalone diagnostic mode may explicitly load native audio.
