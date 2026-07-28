# VoiceFlow Model Strategy

Status: accepted for the VoiceFlow 0.2.1 release candidate

## Product decision

VoiceFlow uses two deliberately separate paths: a lightweight online model for
append-only capsule feedback and SenseVoice Small int8 for the authoritative
complete final transcript. Public builds ship only models whose weight license,
fixed revision, and SHA-256 have passed the release gate.
Alternative models remain engineering experiments and are not presented to
normal users as “more accurate” or “enhanced”.

This is a product decision, not a limitation hidden by the interface. A model
may enter a future download center only after it improves a named user scenario
on the same corpus without breaking latency, memory, reliability, licensing, or
the offline contract.

## Same-machine evidence

The following results were produced on the release development machine with
`eval/public-smoke.jsonl` and strict pathological-output checks. The corpus has
only one Chinese and one English reference sample; it is strong enough to reject
obvious regressions, but too small to claim population-level accuracy.

| Candidate | Load | Chinese RTF / CER | English RTF / CER | 0.2 decision |
| --- | ---: | ---: | ---: | --- |
| SenseVoice Small int8 | 1.77 s | 0.033 / 0.000 | 0.036 / 0.000 | Default |
| Qwen3-ASR 0.6B int8 | 5.05 s | 0.219 / 0.429 | 0.235 / 0.075 | Experiment |
| Fun-ASR Nano 0.8B int8 | not promoted | pathological output / 1.000 | 0.209 CER | Rejected |
| Whisper large-v3-turbo int8 | not promoted | 0.527 / 0.071 | 0.477 / 0.164 | Experiment |

SenseVoice was the only candidate that improved neither accuracy nor speed by
being replaced. Qwen3 produced Traditional Chinese on the current reference,
Fun-ASR Nano produced a pathological one-character result, and Whisper added
roughly 1 GB of model assets without beating the default.

## User scenarios and gates

A candidate is evaluated by scenario, not by a single aggregate score:

| Scenario | Required evidence |
| --- | --- |
| Daily Chinese dictation | Chinese CER, punctuation, omitted-tail rate, terminology |
| English dictation | English WER, casing, number normalization |
| Mixed Chinese and English | code-switch accuracy and spacing |
| Long dictation | 2/5/10-minute tail coverage, merge errors, stop latency |
| Noisy or accented speech | authorized real-speech corpus by environment |
| Low-end CPU | RTF, UI long tasks, audio underruns, RSS |

Promotion requires at least 160 authorized, de-identified utterances, no
pathological-output failure, 100% stopped-audio tail coverage, documented model
license, fixed revision and SHA-256, and a clean-machine package test.

## Streaming preview

The capsule shows no punctuation and never edits text already shown. A token is
committed only after consecutive hypotheses confirm a common prefix. Permanent
hypothesis divergence freezes that segment, records the event, and resets at the
next endpoint so the rest of the session can continue.

The UI reveals confirmed graphemes at a fixed 80 ms cadence. The first
grapheme is immediate; there is no catch-up acceleration, full-text replay, or
horizontal translation. Run the measured model gate with:

```bat
venv\Scripts\python.exe scripts\evaluate_streaming_preview.py --enforce
```

The pinned 2025-04-01 CTC candidate currently remains internal because its
weights have no explicit redistribution license. Technical success cannot
override that distribution gate.

The latest same-machine three-candidate result is recorded in
[`streaming-preview-evaluation-2026-07-28.md`](streaming-preview-evaluation-2026-07-28.md).
None passes the complete latency, chunk, accuracy-smoke, and license gate.

## CPU and GPU

VoiceFlow 0.2 promises the CPU path only. On the current eight-core Ryzen 7
5800H, SenseVoice Chinese P95 was 278.5 ms with two threads, 207.3 ms with four,
174.0 ms with six, and 154.3 ms with eight. Runtime defaults are no longer tied
to that one machine: 2–4 physical cores use at most two final-ASR threads, 6–8
cores use four, and 10 or more use six. Preview uses one or two threads, and the
policy reserves capacity for Qt, audio, and the operating system.

DirectML or CUDA must be delivered as a separate, pinned runtime experiment.
A configuration switch alone is not GPU support. Promotion requires a clean
installer, driver-error fallback to CPU, separate benchmark evidence, and no
reduction in installation success.

## Punctuation and local polishing

The 0.2.1 path uses deterministic cleanup and user vocabulary. A final-only
punctuation adapter is fail-safe: after removing punctuation and spacing, every
lexical character must be identical or VoiceFlow returns the unpunctuated
source. No punctuation is predicted in the streaming capsule.

Any future local polishing stage must:

1. be explicitly enabled;
2. preserve both raw and polished text;
3. have a strict timeout and immediate raw-text fallback;
4. remain offline unless the user deliberately selects a separately disclosed
   online provider;
5. pass meaning-preservation, latency, memory, and rollback tests.

Ollama or another local service may be supported later as an optional adapter,
but it is not a lightweight built-in feature and must never become a hidden
runtime dependency.

## Download-center contract

The download center is deferred until at least one alternative model passes the
admission gate. When implemented, every model must expose:

- user-facing scenario, size, language, expected speed, and hardware class;
- explicit download action with progress, cancel, retry, and removal;
- fixed revision, per-file size, SHA-256, and license;
- `missing`, `downloading`, `verifying`, `ready`, `corrupt`, and `repairing`
  states;
- safe fallback to the bundled default.

Shipping an unqualified menu would transfer model research to the user. VoiceFlow
instead keeps the reliable default visible and the experiments honest.
