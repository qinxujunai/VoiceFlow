# Flagship Reliability Architecture

Status: implemented in the local source candidate; installer and public release remain blocked.

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
7. Re-read the focused UI Automation element. Dispatch paste only when start
   and stop identify the same editable element and UIPI integrity is compatible.
8. Append history, clear the delivery record, and delete recovery PCM only
   after successful durable delivery.

Unknown controls, unavailable UI Automation providers, higher-integrity targets,
changed focus, clipboard contention, and model failures are normal product
states. They fall back to clipboard-only or recoverable-local delivery without
blind paste retries.

## Bounded long-session resources

- PCM: 16 kHz, 16-bit mono, about 115 MB per hour in memory and temporarily on disk.
- Preview: each sample enters the online model once.
- Final cache: explicit non-overlapping coverage ranges plus a retained tail.
- Capsule: at most 256 queued graphemes and 64 visible graphemes; stale visual
  animation is coalesced after a 600 ms hard lag.
- Metadata: atomic update at most every two seconds while the writer is active.

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
