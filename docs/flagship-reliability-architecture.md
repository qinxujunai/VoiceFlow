# Flagship Reliability Architecture

Status: implemented in the local source candidate; public release remains subject to the release checklist.

## Product contract

VoiceFlow treats a stopped recording as a recoverable local session, not as a
transient UI gesture. A session is complete only after authoritative text has
been verified in the clipboard and appended to history. Sending `Ctrl+V` is a
dispatch attempt; it is never proof that the target accepted the paste.

```text
IDLE -> ARMING -> RECORDING -> FINALIZING -> DELIVERING
                                           |-> COMPLETE
                                           |-> RECOVERABLE
                                           `-> ERROR
```

## Durable session order

1. Create a unique `session_id` and atomic metadata journal.
2. Keep complete PCM in memory and enqueue a second copy to a low-priority
   recovery writer. The audio callback performs no disk IO.
3. Freeze audio, stop preview, and prove final sample coverage.
4. Pass raw model text through `SafeTextBoundary`; it may remove protocol and
   control material but may not rewrite semantics.
5. Write an atomic pending-delivery record.
6. Write and exactly read back Unicode clipboard text with bounded retries.
7. Observe the stop-time foreground target through UI Automation and
   `GetGUIThreadInfo`. Dispatch one paste to an ordinary foreground application
   unless the desktop, secure desktop, UIPI, VoiceFlow itself, or the absence
   of a foreground window provides positive evidence to block it. The start
   target is diagnostic context only.
8. Append history, clear the delivery record, and delete recovery PCM only
   after successful durable delivery.

Unknown or transient UI Automation nodes are normal inside rich-text chat
editors and do not by themselves block a stop-time paste. Higher-integrity
targets, the desktop, clipboard contention, and model failures remain normal
product states with clipboard-only or recoverable-local delivery and no blind
paste retries.

## Bounded long-session resources

- PCM: 16 kHz, 16-bit mono, about 115 MB per hour in memory and temporarily on disk.
- Preview: each sample enters the online model once.
- Final cache: explicit non-overlapping coverage ranges plus a retained tail.
- Capsule: at most 256 queued graphemes and 64 visible graphemes; stale visual
  animation is coalesced after a 600 ms hard lag.
- Preview endpoints: at most 256 retained sample indices and consumed as final
  cache coverage advances.
- Metadata: atomic update at most every two seconds while the writer is active.

## Capsule and finalization contract

The capsule keeps live draft and authoritative prefix separate in state, while
rendering both in one primary text color with a stable red recording meter. A
natural preview endpoint may trigger a SenseVoice cache
segment before stop; fixed 18-second cache segments stay invisible until final
assembly. This avoids presenting background cache work as a correction of the
user's active draft.

Stop atomically latches the final sample before device teardown. Preview is
invalidated immediately and no worker thread is joined on the interaction path.
The existing text remains unchanged for 350 ms. If work continues, only the
meter becomes a spinner. Final text replaces the draft in place and delivery
feedback follows the rules in
[`ADR-002`](decisions/ADR-002-single-visual-state-and-fixed-model.md).

The stop path and progressive cache use a shared handoff lock plus a bounded
idle event. An already-running cache segment commits its coverage before final
assembly snapshots the cache; no new cache segment may start after stop.

## Recovery UX

At startup, recoverable sessions produce a quiet amber notification. History
lists each local recording with duration and model. The user can re-recognize
and copy it, copy an existing confirmed preview, or explicitly delete it.
Successful recovery writes history before deleting PCM. Unhandled recovery
assets expire after 24 hours.

## Release blockers

This architecture is necessary but not sufficient for a public installer. The
release remains blocked until the one-hour natural-speech gate, forced-crash
matrix, UI Automation application matrix, clipboard contention suite, clean
machine packaging, license bundle, and 500 real recording lifecycles pass.
