# ADR-004: Stable UI controller and supervised native workers

- Status: Accepted for the 0.3.2 local candidate
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

1. a disposable microphone process;
2. a persistent online-preview recognizer process;
3. a persistent authoritative-final recognizer process.

Every process has bounded IPC, a heartbeat, and a hard termination path. Preview
messages and UI updates retain the existing session generation guard. Complete
PCM remains mirrored in the parent during this candidate so recovery and final
coverage do not depend on a worker remaining alive. That deliberate copy costs
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
