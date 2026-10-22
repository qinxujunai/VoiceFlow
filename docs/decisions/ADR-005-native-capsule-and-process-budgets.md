# ADR-005: Native capsule and bounded process costs

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](../README.md).

- Date: 2026-10-04
- Status: shipped in the 0.3.9 Windows release; [artifact-bound verification](../release-validation-0.3.9.md) records the scope. Earlier local measurements remain historical.

## Problem and decision

The compact dictation capsule required an entire Chromium runtime. Frozen native
workers also imported Qt through automatic runtime hooks, while NumPy created
16-thread OpenBLAS pools with large private allocations on this Windows machine.
Healthy recording stop/cancel restarted the audio process. These costs compound
on a 16 GB laptop even when recognizer execution itself is fast.

Use Qt Widgets native painting while preserving the established 34 px black
capsule, 17 px corners, three red bars and light text. Typed queued signals carry
commands; Qt owns timers, painting and transitions. Display confirmed graphemes
once, bound animation backlog, reject stale sessions, retain text during stop,
replace it with the complete final output and fade only after verified delivery.
Hide before resetting and reset every animation before a new recording.

Exclude WebEngine/QML/Quick from the release. Dispatch frozen worker processes
before GUI runtime hooks. Set OpenBLAS to one thread before importing NumPy;
sherpa/ONNX inference retains its independent budget. Reuse the audio process
only after confirmed stream teardown; preserve the termination/recovery fallback.

Recording feedback precedes optional focus diagnostics and preview startup.
Preview receives distinct PCM blocks of at most 100 ms on its own thread.
Settings report controller readiness instead of treating model-file presence as
proof that recording and recognition are usable.

## Verification and limits

Regression tests cover blocked driver teardown, worker reuse, preview startup
cancellation, focus latency, state generations, Unicode graphemes, native pixels,
idle timers and successive recording animation. The public-WAV packaged probe
exercises real recognition and fixture-based audio IPC without a microphone,
clipboard output or personal history. This does not replace real microphone,
application paste, clean-machine or natural-speech accuracy validation.

The source-only legacy renderer remains available through
`VOICEFLOW_CAPSULE_RENDERER=webengine` for comparison. A release candidate does
not contain the dependencies required by that developer override. Public model
and release claims remain subject to the existing quality gates.
