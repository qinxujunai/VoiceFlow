# Streaming Preview Evaluation — 2026-07-28

Status: **no candidate promoted**

This same-machine experiment uses the pinned public `zh.wav` sample only. It
is sufficient to reject latency and emission-granularity regressions, but it is
not an accuracy corpus and cannot support a public quality claim.

Command:

```bat
venv\Scripts\python.exe scripts\evaluate_streaming_preview.py --candidate MODEL_ID
```

All candidates used 80 ms PCM chunks, the same one-character stability guard,
the same endpoint state machine, CPU execution, and the then-current 80 ms capsule
display cadence.

| Candidate | Speech onset to first delta | Update gap P95 | Chunk P95 / max | Decode time | Sample transcript | Decision |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Small Zipformer CTC 2025-04-01 | 825.5 ms | 640 ms | 3 / 3 | 164.8 ms | 开放时间早上九点至下午五 | Rejected for public build: update/chunk gate and `NOASSERTION` license |
| Bilingual Paraformer int8 | 1225.5 ms | 640 ms | 2 / 2 | 470.8 ms | 菜放时间早上九点至下午五 | Rejected: first-delta gate and sample regression |
| Zipformer CTC 2025-06-30 | 1145.5 ms | 640 ms | 2 / 2 | 537.6 ms | 开放时间早上九点至下午 | Rejected: first-delta gate and `NOASSERTION` license |

Release thresholds are first delta <= 900 ms, update-gap P95 <= 450 ms,
chunk-size P95 <= 2 with a hard maximum of 4, and queue-delay P95 <= 250 ms.
None of the three candidates passes the complete gate.

The product fallback remains valid: when no redistributable preview candidate
passes, VoiceFlow must use a quiet recording capsule and keep SenseVoice as the
complete final recognizer. The release gate must not lower latency, integrity,
or license requirements to preserve streaming text.
