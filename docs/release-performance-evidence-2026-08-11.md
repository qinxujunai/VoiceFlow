# VoiceFlow 0.3.1 release performance evidence

Status: automated release performance gate passed on the release workstation.

This evidence measures latency and rendering mechanics. It does not claim
population-level speech accuracy. The preview benchmark uses the pinned public
Chinese and English WAV files and never writes recognized text into the
performance evidence file.

## Environment

- Windows 11, AMD Ryzen 7 5800H, 8 physical / 16 logical cores
- 15.9 GB RAM
- SenseVoice int8 authoritative final model
- bilingual streaming Zipformer int8 preview model
- 20 samples in every published latency bucket

## Reproduction

```bat
venv\Scripts\python.exe scripts\measure_pipeline_performance.py --samples 20 --preview-samples 20
venv\Scripts\python.exe scripts\performance_gate.py
venv\Scripts\python.exe scripts\verify.py --release
```

## Result

| Metric | P95 | Gate |
| --- | ---: | ---: |
| Trigger to first feedback | 6.237 ms | <= 50 ms |
| 0-10 s stop to paste dispatch | 426.809 ms | <= 500 ms |
| 10-60 s stop to paste dispatch | 454.219 ms | <= 700 ms |
| Two-minute stop to paste dispatch | 541.246 ms | <= 2.5 s |
| Preview first confirmed model delta | 745.5 ms | <= 1.3 s |
| Preview first visible paint | 793.5 ms | <= 1.3 s |
| Preview model update gap | 1280 ms | <= 1.3 s |
| Preview queue delay | 288 ms | <= 350 ms |
| Visible characters per paint step | 1 | exactly 1 |
| Preview model delta size | 8 characters | P95 <= 12 |

The candidate comparison kept the existing bilingual Zipformer. The local
Paraformer challenger was larger, slower, and produced worse Chinese and
English preview text on the same pinned samples. SenseVoice remains the final
authority in every case.
