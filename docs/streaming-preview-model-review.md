# Streaming preview model distribution review

Status: **internal candidate; public redistribution blocked**

VoiceFlow evaluates
`sherpa-onnx-streaming-zipformer-small-ctc-zh-int8-2025-04-01`
only as the low-latency capsule preview. SenseVoice remains the authoritative
final recognizer.

The same restriction applies to the evaluated
`sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30` checkpoint: the
official runtime documentation and archive identify its source, but the model
weights do not carry an explicit license declaration.

## Pinned source

- Official sherpa-onnx model archive:
  `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-small-ctc-zh-int8-2025-04-01.tar.bz2`
- Upstream checkpoint:
  `https://huggingface.co/csukuangfj/icefall-streaming-zipformer-small-ctc-zh-2025-04-01`
- Training project:
  `https://github.com/k2-fsa/icefall`

The archive, model, and token hashes are pinned in `model-manifest.json`.

## Decision

The icefall source repository is Apache-2.0, but neither the upstream model
card nor the downloaded model archive explicitly declares a license for the
model weights. A source-code license alone is not sufficient evidence that the
weights may be redistributed.

Therefore:

- local evaluation and private installation testing may use the pinned files;
- the public Release workflow must fail while
  `distribution_review_required` is `true`;
- no public installer may contain this model until the model owner or an
  authoritative upstream notice explicitly confirms redistributable terms;
- when confirmed, the exact evidence, attribution, license file, review date,
  and reviewer decision must be recorded here before changing the manifest
  gate.

This review is about distribution only. It does not affect VoiceFlow's
offline runtime behavior or the technical evaluation of the model.
