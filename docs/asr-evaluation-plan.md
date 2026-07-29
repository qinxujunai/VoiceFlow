# VoiceFlow ASR Evaluation Plan

The latest local smoke report is
[`model-lab-2026-07-18-preliminary.md`](model-lab-2026-07-18-preliminary.md).
It is intentionally preliminary and did not promote a model.

VoiceFlow should choose speech models by product evidence, not by popularity.
The default remains local-first and offline.

## Product Goal

The user presses a trigger, speaks naturally, and the complete final text lands at
the current cursor quickly. Streaming text is only feedback. The final output is
the contract.

## Candidate Engines

- SenseVoice ONNX: current default, strong fit for low-latency Chinese local dictation.
- Qwen3-ASR 0.6B int8: implemented accuracy challenger.
- Fun-ASR Nano int8: implemented Chinese/hotword challenger.
- Whisper large-v3-turbo int8: implemented multilingual control.

No candidate should become the default until it beats the current engine on the
same local manifest.

## Required Metrics

- Stop-to-paste latency: milliseconds from stop trigger to `OutputHandler.output`.
- Tail completeness: whether the final 10 spoken characters appear in output.
- Clean CER: character error rate after deterministic cleanup.
- Raw CER: character error rate before cleanup.
- Term hit rate: configured product and AI vocabulary terms recognized correctly.
- RTF: transcription time divided by audio duration.
- Segment count: number of cached final segments used for long recordings.
- Speech-onset-to-first-delta and speech-onset-to-first-browser-paint.
- Preview update-gap P95, chunk-size P95, queue-delay P95, and divergence count.

## Manifest Shape

Store private samples outside Git if they contain personal speech. A checked-in
example manifest can use public or synthetic audio only.

```jsonl
{"id":"zh-short-command-001","audio":"audio/zh-short-command-001.wav","reference":"把这个方案整理成三个重点。","terms":["方案"]}
```

## Fixed release corpus

- 160 authorized, de-identified natural utterances from at least eight speakers.
- 64 Chinese, 24 English, 32 mixed Chinese/English, 20 terminology/ITN, 12
  natural pauses and self-corrections, and 8 silence or non-speech samples.
- 12 additional 30-second, 2-minute, 5-minute, and 10-minute recordings.
- Synthetic speech and noise derivatives are regression aids only; they never
  support public accuracy claims.
- A release holdout is never used to tune rules or choose models.

## Acceptance Bar

- Short dictation under 20 seconds: paste should feel immediate.
- Two-minute dictation: final output must include the last 10 spoken characters.
- Long dictation over 5 minutes: cached body plus final tail must match the same
  final-output contract.
- A stronger model that adds noticeable stop latency should not replace the
  default unless accuracy gains are large enough to justify a separate mode.

## Implemented Model Lab

```bat
venv\Scripts\python.exe scripts\evaluate_asr.py --manifest eval\private\local.jsonl
```

The command evaluates every installed, hash-verified candidate, writes
per-sample JSONL plus a summary, applies the fixed weighted score and hard
gates, and leaves the default unchanged when coverage is incomplete. Add
`--promote` only for a controlled run; promotion still happens only when every
gate passes.

The weekly model smoke also runs `benchmark_models.py --strict-output`.
Pathological repetition or an impossible output rate is a hard failure, even
when the process itself exits normally.

The streaming model is measured separately:

```bat
venv\Scripts\python.exe scripts\evaluate_streaming_preview.py --enforce
```

It must meet first delta P95 <= 900 ms from detected speech onset, update gap
P95 <= 450 ms, chunk-size P95 <= 2 graphemes with a hard maximum of 4, and
queue delay P95 <= 250 ms. A candidate must also have an explicit model-weight
license before it can enter a public installer.
