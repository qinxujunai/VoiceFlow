# VoiceFlow ASR Evaluation Plan

VoiceFlow should choose speech models by product evidence, not by popularity.
The default remains local-first and offline.

## Product Goal

The user presses a trigger, speaks naturally, and the complete final text lands at
the current cursor quickly. Streaming text is only feedback. The final output is
the contract.

## Candidate Engines

- SenseVoice ONNX: current default, strong fit for low-latency Chinese local dictation.
- faster-whisper: candidate for broader multilingual accuracy and Whisper ecosystem compatibility.
- whisper.cpp: candidate for portable local packaging and quantized deployment.
- qwen3-asr or other local ONNX engines: candidate only after they pass the same local tests.

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

## Manifest Shape

Store private samples outside Git if they contain personal speech. A checked-in
example manifest can use public or synthetic audio only.

```json
[
  {
    "id": "zh-short-command-001",
    "audio": "benchmarks/audio/zh-short-command-001.wav",
    "language": "zh",
    "duration_seconds": 5.2,
    "expected": "把这个方案整理成三个重点。",
    "terms": ["方案"]
  }
]
```

## Acceptance Bar

- Short dictation under 20 seconds: paste should feel immediate.
- Two-minute dictation: final output must include the last 10 spoken characters.
- Long dictation over 5 minutes: cached body plus final tail must match the same
  final-output contract.
- A stronger model that adds noticeable stop latency should not replace the
  default unless accuracy gains are large enough to justify a separate mode.

## Next Implementation Step

Add `scripts/evaluate_asr.py --manifest <path> --engine <name>` and write JSONL
results into `logs/asr-eval.jsonl`. The script should reuse the production
transcriber, cleaner, vocabulary, and history metadata fields so benchmark
results match real dictation behavior.
