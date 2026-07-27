# VoiceFlow Product Quality Standard

Status: required release policy

VoiceFlow uses one rule for engineering, design, packaging, and communication:
every visible claim must map to reproducible evidence. A successful build is
not a successful product release.

## 1. Requirement traceability

Every material user report is assigned an ID, translated into a product or
engineering risk, and closed as adopted, deferred with a gate, or rejected with
a reason. The current closure matrix is
[`feedback-review-2026-07-28.md`](feedback-review-2026-07-28.md).

## 2. Core invariants

- Core dictation works without network access.
- Complete stopped audio, including the tail, is the final source of truth.
- Recognized text reaches the clipboard before paste is attempted.
- Text remains recoverable from the clipboard and local history.
- Streaming preview cannot overwrite final output.
- User data is outside the install directory and survives a normal upgrade or
  uninstall.
- Default hotkeys do not break ordinary typing.

## 3. Release gates

### Automated

- full pytest suite;
- 500 start/stop/cancel lifecycle cycles;
- pathological ASR output detection;
- packaged-runtime contract;
- installer install, launch, upgrade, uninstall, and data-retention smoke;
- bilingual website resource, navigation, overflow, and console checks.

### Performance

- recording trigger to actual first paint: P50 at most 50 ms, P95 below 100 ms;
- up to 20-second stop-to-clipboard: P95 at most 700 ms;
- two-minute stop-to-clipboard: P95 at most 2.5 s;
- at least 20 samples per published bucket;
- no audio callback underrun in the release matrix;
- no Qt main-thread task longer than 50 ms during recording;
- bounded preview memory and work during long dictation.

### Model quality

- at least 120 authorized, de-identified Chinese, English, and mixed utterances
  before making public accuracy claims;
- explicit CER/WER and terminology results by scenario;
- 100% tail coverage for 2/5/10-minute cases;
- hard failure for repeated-character, repeated-phrase, impossible-rate, and
  silence-hallucination output;
- fixed revision, SHA-256, license, and distribution decision.

### Visual and accessibility

- app states captured at 100%, 125%, 150%, and 200% scale;
- primary task keyboard-operable;
- visible focus, readable contrast, reduced-motion behavior, and no clipped
  localized copy;
- overlay motion communicates state and never fabricates recognition progress;
- website tested in the selected real browser at desktop and mobile widths.

### Delivery

- clean Windows machine without Python, Git, CUDA, or developer tools;
- installer and installed app versions match the tag;
- public filename follows `VoiceFlow-{version}-Windows-x64.exe`;
- `SHA256SUMS.txt`, release notes, third-party notices, and model attribution;
- exact Release asset exists before README or website download links go live;
- human approval after CI and installed-product validation.

## 4. Claim policy

“Best”, “most accurate”, “instant”, and “never loses words” are not acceptable
without a defined population, corpus, hardware, sample count, and measurement.
VoiceFlow may describe mechanisms it can prove—offline operation, clipboard
fallback, local history, bounded preview work, and complete stopped-audio
coverage—while disclosing the machine and sample limits of performance data.

## 5. Stop conditions

The release stops if any invariant fails, the installer asset is missing, a
model or Qt license record is incomplete, the website points to a nonexistent
download, or a real-user claim exceeds the available evidence. Deferred features
must remain visibly unavailable rather than being represented by placeholder
downloads or nonfunctional controls.
