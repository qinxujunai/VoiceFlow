# User Feedback Closure — 2026-07-28

Source: the complete `需求反馈` folder supplied by the maintainer. The Word
document and all three screenshots were reviewed. External project names were
verified against public repositories or official product documentation before
being used as evidence.

## Closure matrix

| ID | Feedback | Decision | Product response |
| --- | --- | --- | --- |
| F01 | VoiceSnap feels faster | Adopted | Keep the model resident, bound preview work, measure actual first paint and stop-to-paste, and avoid claiming that model choice alone explains speed. |
| F02 | Chinese accuracy and omitted words | Adopted | Keep complete-audio finalization, tail tests, strict abnormal-output gates, user vocabulary, and require an authorized real-speech corpus before accuracy claims. |
| F03 | English is weaker | Adopted | Maintain a separate English WER gate. SenseVoice remains default because current same-machine English evidence does not justify a replacement. |
| F04 | Offer Qwen3-ASR, Whisper, SenseVoice, and other models | Deferred by gate | All named candidates were benchmarked. The alternatives are slower, less accurate on current public samples, pathological, or about 1 GB. They remain experiments until one wins a real scenario. |
| F05 | Add local AI polishing | Deferred by gate | The future stage must be optional, preserve raw text, time out safely, and pass meaning/latency/RSS tests. No hidden local LLM dependency is added to 0.2. |
| F06 | Add online API choices | Rejected for 0.2 | Cloud ASR conflicts with the core offline promise. A future separately disclosed adapter may be considered, but never in the default path. |
| F07 | Capsule text appears in chunks | Partially closed | Confirmed graphemes now reveal at a fixed 80 ms rhythm with no acceleration, replay, or reverse motion. The current preview model still fails the update-gap and chunk-size targets and remains an internal candidate. |
| F08 | Prefer smooth per-character output | Adopted with truth constraint | Only text already returned by ASR is animated. The UI does not fabricate unrecognized tokens or delay the final result. Reduced-motion users receive immediate text. |
| F09 | Long-running use may lag | Adopted with a new safety tradeoff | Preview consumes only new PCM. Full int16 mono PCM is retained through stop (about 19 MB for ten minutes), while progressive final segments provide bounded finalization without sacrificing recoverability. |
| F10 | Create a WeChat or QQ group | Deferred | GitHub Issues is the current auditable support channel. A private group requires an owner, moderation, privacy rules, and response capacity before publication. |
| F11 | Study CapsWriter-Offline, VocoType, AriaType, VoiceSnap, and Typeoff | Completed | Their relevant architecture and product lessons are summarized below; license boundaries are preserved. |
| F12 | Installer is missing from GitHub Packages | Corrected | Windows installers belong in GitHub Releases. The website and READMEs link directly to the versioned Release asset; Packages remains intentionally unused. |

## Competitor lessons

### VoiceSnap

VoiceSnap uses a compact Go/Wails application, a sherpa-onnx C runtime, and a
Windows DirectML-first path. Its short-session speed also benefits from doing a
single stop-time decode instead of repeatedly transcribing preview windows.
VoiceFlow adopted the evidence lesson—measure the whole user path—but will not
claim GPU support until a separately packaged runtime passes installation and
fallback tests.

### CapsWriter-Offline

CapsWriter uses overlapping chunks, bounded fuzzy merge, an ASR worker process,
engine capabilities, and optional Ollama/OpenAI-compatible polishing. These
patterns are valuable for long dictation and future adapters. VoiceFlow keeps
its simpler in-process default for 0.2 because the current performance gate
passes and a process split would require new shutdown, crash-recovery, and
packaging validation.

### VocoType

VocoType keeps models warm and moves final transcription to a background queue.
Its public local path is still stop-time transcription, and its bounded queue
can discard work when full. VoiceFlow adopts the resident-model and responsive
UI ideas but rejects job dropping because recoverable output is a core contract.

### AriaType

AriaType has strong model-status, raw/final history, and correction-memory
information architecture. Its public focus is macOS and its AGPL license does
not permit copying implementation into this MIT project. VoiceFlow adopts the
behavioral lessons while keeping code independent.

### Typeoff

Typeoff clearly separates cloud WebSocket live transcription from local Whisper.
Its smooth real-time cloud text is not evidence that an offline CPU model emits
tokens at the same granularity. VoiceFlow therefore smooths confirmed local
increments while keeping final output immediate and recoverable.

## Result for the VoiceFlow 0.2.1 candidate

The release keeps one bundled SenseVoice model, CPU-first execution, no cloud
path, no hidden AI rewriting, and no false macOS asset. The capsule, application
information architecture, website story, release naming, and model communication
were revised. Alternative models and local polishing now have explicit admission
contracts instead of unfinished customer-facing controls.

The privacy migration, stopped-audio coverage, and append-only preview contracts
have automated regression coverage. This is not yet a public-release claim:
authorized holdout data, real 2/5/10-minute microphone evidence, resource
budget, clean Win10/11 lifecycle evidence, model-weight redistribution rights,
and Authenticode signing remain hard blockers.
