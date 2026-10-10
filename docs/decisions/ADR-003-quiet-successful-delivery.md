# ADR-003: Dismiss successful delivery without redundant confirmation

## Status

Accepted; delivery confirmation tightened on 2026-10-06

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

- Only after reliable verification of the actual inserted final text, keep the
  authoritative text in place and fade the capsule out over 120 ms. Do not
  render a check or a success label.
- Announce confirmed insertion as `文字已输入`. A clipboard readback or accepted
  input events alone do not establish insertion.
- When one paste was dispatched but insertion is unverified, show
  `已复制到剪贴板` and announce manual Ctrl+V if the text has not appeared.
  Never retry automatically or mark onboarding complete from dispatch alone.
- When paste is not dispatched but clipboard delivery is verified, show
  `已复制到剪贴板` long enough to be read.
- When only durable local recovery succeeds, show `已保存`. Real failures keep
  their concise recovery-oriented state.
- Mouse position remains irrelevant. Bind delivery to the ordinary foreground
  target observed at stop time; revalidate before dispatch. A changed target,
  changed clipboard, held modifier, or positive blocked-target evidence requires
  recoverable delivery without automatic paste. Transient unknown UIA nodes
  alone remain insufficient to classify an ordinary target as blocked.

Historical dispatch-only statuses remain unverified; no migration may turn
them into confirmed insertion. The current development runtime has not yet
implemented a general insertion verifier, so dispatch remains unverified.

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
