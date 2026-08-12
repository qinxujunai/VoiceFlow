# ADR-003: Dismiss successful delivery without redundant confirmation

## Status

Accepted

## Date

2026-08-11

## Context

ADR-002 made delivery feedback explicit with a check and `已完成`. That state
was truthful, but it appeared after every successful dictation even though the
target input already displayed the final text. The extra state changed the
capsule after the task had visibly succeeded and kept it present for another
700 ms, making a fast paste feel slower and more interruptive.

Clipboard-only delivery is different: the target does not display the text, so
the user needs to know where the result went. Durable recovery and real errors
also require visible feedback.

## Decision

- After verified clipboard delivery and one dispatched paste, keep the
  authoritative text in place and fade the capsule out over 120 ms. Do not
  render a check or a success label.
- Keep the complete accessible announcement that the clipboard was verified
  and the paste command was dispatched.
- When paste is not dispatched but clipboard delivery is verified, show
  `已复制到剪贴板` long enough to be read.
- When only durable local recovery succeeds, show `已保存`. Real failures keep
  their concise recovery-oriented state.
- Mouse position remains irrelevant. Delivery continues to use the ordinary
  foreground target observed at stop time and falls back only on positive
  blocked-target evidence.

This supersedes only the explicit completion-feedback decision in ADR-002. Its
single recording color, fixed bundled model, and settings decisions remain in
force.

## Alternatives Considered

### Keep `已完成` but shorten its dwell

Rejected because the redundant state transition remains visible even at a
shorter duration and still makes the interaction appear unfinished.

### Show a check without text

Rejected because it is still an unnecessary success state and had already
proved too ambiguous in earlier builds.

### Hide all delivery feedback

Rejected because clipboard-only and recovery outcomes require the user to know
where the text remains available.

## Consequences

- The target input is the primary visible confirmation of successful delivery.
- Normal high-frequency dictation becomes quieter and appears to finish sooner
  without changing ASR or clipboard correctness.
- Fallback states are rarer but more explicit.
- Tests must preserve the silent-success branch, accessible announcement,
  bounded fade duration, and visible fallback states.
