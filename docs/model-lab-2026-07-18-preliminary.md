# VoiceFlow Model Lab — 2026-07-18 preliminary run

Status: **no candidate promoted**. The active engine remains SenseVoice.

This is an engineering smoke comparison, not the final 120-sample model
decision. It uses two pinned, distributable sherpa-onnx reference clips and is
deliberately rejected by the hard gate because long-tail, two-minute, private
calibration, and 500 real microphone-cycle evidence are not present.

## Environment

- Windows 11 build 26200
- AMD Ryzen 7 5800H, 8 cores / 16 logical processors
- 16 GB system memory
- sherpa-onnx 1.13.3, CPU provider, six inference threads
- Each model ran in a fresh process; peak working set is therefore isolated
  per candidate.

## Results

| Candidate | Clean CER | Terms | Short P95 | Peak memory | Score | Decision |
|---|---:|---:|---:|---:|---:|---|
| SenseVoice-Small int8 | 2.27% | 75% | 163 ms | 355 MB | 84.21 | Keep current default pending full set |
| Qwen3-ASR-0.6B int8 | 23.02% | 25% | 1,298 ms | 1,459 MB | 55.03 | Reject preliminary latency and accuracy gates |
| Fun-ASR-Nano 0.8B int8 | 126.22% | 25% | 902 ms | 1,647 MB | 26.64 | Reject preliminary hallucination, latency, and accuracy gates |
| Whisper large-v3-turbo int8 | 3.79% | 75% | 3,217 ms | 1,399 MB | 66.94 | Reject interactive latency gate; retain as multilingual control |

The exact machine-readable report is
`logs/model-lab-final-preliminary/20260718-121746-summary.json`, with per-sample
rows in the adjacent `results.jsonl`. Those local evidence files are excluded
from source control because later runs may contain private calibration paths or
text.

## Hard-gate interpretation

- SenseVoice is the only tested candidate below the 700 ms short-recording P95
  target in this smoke run.
- Every candidate fails release coverage: no 1/2/5/10-minute tail corpus and no
  500-cycle real microphone run were supplied to this invocation.
- Qwen3-ASR, Fun-ASR-Nano, and Whisper do not meet the required relative CER and
  terminology improvement over SenseVoice on this small set.
- Qwen3-ASR 1.7B was not admitted because no pinned sherpa-onnx int8 export was
  available and the upstream artifact exceeds the product resource ceiling.

The Model Lab therefore returns `winner: null`; `config.yaml` is not modified.
