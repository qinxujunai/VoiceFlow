# Streaming preview model distribution review

Status: **approved as a bilingual first-pass preview**

VoiceFlow bundles
`sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16` only for
low-latency capsule feedback. SenseVoice remains the authoritative recognizer
and rechecks the complete stopped audio before clipboard output.

## Pinned source and license

- Official sherpa-onnx release archive:
  `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16.tar.bz2`
- Upstream checkpoint: `csukuangfj/k2fsa-zipformer-bilingual-zh-en-t`
- Weight license: Apache-2.0
- Runtime: sherpa-onnx, Apache-2.0

The archive revision, selected runtime files, byte sizes, and SHA-256 values
are pinned in `model-manifest.json`. The installer includes only the int8
encoder, decoder, joiner, and token table required at runtime.

## Product decision

The previous Chinese-only CTC preview exposed `<unk>` control tokens during
English speech and could not be redistributed because its weight license was
not declared. It is no longer a bundled default.

The bilingual model was promoted because it:

- produces lexical Chinese and English instead of leaking model control tokens;
- is a true streaming first pass that consumes each PCM sample once;
- adds about 60.1 MB of runtime assets rather than another full final model;
- has an explicit Apache-2.0 weight license and pinned hashes.

It is not described as final-quality ASR. Preview mistakes are never pasted as
long as SenseVoice returns a valid complete result. The UI displays only
append-only confirmed deltas; the stopped-audio transcript remains recoverable
from the clipboard and local history.

The same-machine smoke evidence is recorded in
`streaming-preview-evaluation-2026-08-05.md`. A real, authorized bilingual
holdout is still required before making a population-level accuracy claim.
