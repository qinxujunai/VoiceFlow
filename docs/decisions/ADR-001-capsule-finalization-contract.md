# ADR-001: Separate live draft, authoritative text, and delivery feedback

## Status

Superseded by ADR-002

## Date

2026-08-09

## Context

VoiceFlow uses two recognizers with different jobs. The online Zipformer can
produce text while audio is still arriving, but its partial hypotheses are less
accurate than the full-context SenseVoice result. Treating both as the same
text made preview errors look like product errors, while replaying or repeatedly
replacing partial text caused rollback, latency, and unbounded long-session work.

The previous stop flow also waited for worker cleanup and showed a textual
finalizing state after 180 ms. Short dictations therefore passed through an
extra visible state even when final ASR finished quickly.

## Decision

Use one capsule with three explicit layers of truth:

1. The online recognizer appends a secondary-color live draft. Each PCM sample
   enters this recognizer once.
2. At a stable natural endpoint, SenseVoice may replace the covered prefix with
   primary-color authoritative text. Forced cache segments remain invisible so
   they cannot erase an active draft tail.
3. On stop, atomically freeze the final sample boundary, invalidate preview,
   and close the device afterward. Keep the last text unchanged for 350 ms;
   after that, show only a spinner in the mark region. When final ASR completes,
   replace the text in place without retyping it.

Delivery feedback is separate from recognition:

- verified clipboard plus paste dispatch: centered green check plus `已完成`;
- verified clipboard without paste: `已复制`;
- durable local recovery while clipboard is unavailable: amber `已保存`;
- errors: short reason with recovery actions elsewhere.

The final-cache worker and stop path claim work through the same handoff lock.
An in-flight segment finishes and commits coverage before stop-time ASR takes a
snapshot, preventing a duplicate full decode. There is no thread `join` in the
preview stop path.

## Alternatives Considered

### Show the SenseVoice result continuously by retranscribing all PCM

- Benefit: one model name and potentially more accurate visible text.
- Cost: repeated CPU work grows with recording length; hypotheses roll back;
  long dictation becomes progressively slower.
- Rejected because it violates bounded work and append-only preview.

### Treat Zipformer text as final

- Benefit: fastest stop response.
- Cost: preserves known English, punctuation, and mixed-language errors in the
  delivered text.
- Rejected because preview latency cannot replace final accuracy.

### Hide all text until stop

- Benefit: every visible word is authoritative.
- Cost: removes the confidence and error detection users need during long
  dictation.
- Rejected because honest draft styling communicates uncertainty without
  removing useful feedback.

### Replace Zipformer immediately with Paraformer or Chinese CTC

- Benefit: different latency and accuracy trade-offs.
- Cost: same-machine reference tests did not meet the combined Chinese,
  English, first-delta, update-gap, chunk, and licensing gates.
- Rejected as the default; candidates remain experimental.

## Consequences

- Preview mistakes remain possible and are deliberately shown as drafts.
- Final text is never replayed character by character.
- A result completing within 350 ms shows no spinner.
- The capsule DOM, queue, endpoint list, and final segment metadata remain
  bounded during hour-long sessions.
- Public claims about preview cadence or model accuracy remain blocked until
  the required natural-speech corpus and performance evidence exist.
- Future changes must preserve session guards, complete sample coverage,
  clipboard verification, and recovery semantics.
