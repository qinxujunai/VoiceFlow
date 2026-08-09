# ADR-002: Use one recording color, explicit completion, and one bundled model

## Status

Accepted

## Date

2026-08-09

## Context

ADR-001 correctly separated preview text from authoritative text in the data
model, but exposed that distinction through two text colors and changed the
recording meter from red to gray when a natural-pause segment became
authoritative. Users experienced this as flicker and uncertainty rather than
useful information. Its paste-dispatch state also removed the label and left a
centered check for only 560 ms, which was too ambiguous to read as completion.

Natural-pause correction was additionally delayed by two independent waits:
the online recognizer used a 1.2-second token-bearing endpoint and the final
cache retained another two seconds of audio. A visible correction could
therefore arrive several seconds after speech stopped.

The settings page exposed model selection, download, repair, progress, and
switching. No optional model has passed the product admission gate, so these
controls transferred internal model research and failure handling to users
without adding a proven benefit.

## Decision

- Keep draft and authoritative text separate internally, but render both in the
  same primary text color. Recognition confidence must not create color flicker.
- Keep the three recording bars red for the entire recording state, including
  after an authoritative natural-pause update. Color changes only when the
  product leaves recording for finalization, recovery, or error.
- Verified clipboard plus paste dispatch shows a green check and `已完成` for
  700 ms. Clipboard-only remains `已复制`; durable recovery remains `已保存`.
- Configure token-bearing natural endpoints at 0.55 seconds of trailing
  silence and retain only 0.25 seconds before committing a final-cache segment.
  Empty-token silence remains more conservative at 1.6 seconds.
- Ordinary settings expose language, microphone, performance status, privacy,
  startup, shortcuts, dictionary, history, and diagnostics. They do not expose
  model selection, model downloads, model switching, or model repair.
- VoiceFlow ships and uses the reviewed bundled default. Alternative models
  remain internal benchmark candidates until a future product decision
  explicitly supersedes this ADR.

The data contract from ADR-001 remains: each PCM sample enters preview once,
the stopped final transcript covers complete PCM, preview cannot overwrite a
final state, and delivery claims only what clipboard verification and paste
dispatch can prove.

## Alternatives Considered

### Preserve two colors and add a legend

Rejected because it adds explanation to compensate for avoidable visual
complexity. Users need stable feedback and correct final text, not an ASR state
debugger.

### Keep check-only completion for maximum minimalism

Rejected because the icon alone does not distinguish completed delivery from a
decorative status. `已完成` supplies meaning with four characters and no false
claim of paste success.

### Expose optional models but label them experimental

Rejected because installation size, latency, accuracy, integrity, and rollback
remain product responsibilities. An experimental label does not make users the
right people to resolve those trade-offs.

## Consequences

- Internal transcript provenance remains testable without causing visible
  color changes.
- Natural-pause corrections arrive substantially sooner, with the existing
  full-PCM stop fallback preserving correctness if a segment is incomplete.
- The settings page is smaller and has fewer failure modes.
- Model download and switching services may remain as internal engineering
  infrastructure, but no ordinary UI may call or advertise them.
