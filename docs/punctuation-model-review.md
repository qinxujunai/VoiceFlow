# Final punctuation candidate review — 2026-10-11

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](README.md).

VoiceFlow uses `CT-Transformer` only to rebuild punctuation in Chinese prose.
It does not replace the dictation recognizer, correct guessed words, or rewrite
the speaker's wording. English-only input retains recognizer punctuation: a
constructed English example produced incorrect sentence boundaries. Chinese
and English accuracy are not conflated.

## Artifact and attribution

Alibaba Group / FunASR / ModelScope:
`iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch`, converted by k2-fsa
for sherpa-onnx. Only the ONNX weights are used; archive scripts are not run.

- [Upstream model](https://modelscope.cn/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch/summary)
- [Runtime documentation](https://k2-fsa.github.io/sherpa/onnx/punctuation/pretrained_models.html)
- Release archive `sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2`
- Archive SHA256 `c0d5aa5f8eeb686032345e180bedf39319dc2e0556781c6264bcadba8328a6e1`
- ONNX: 75,519,198 bytes; SHA256 `65a3fb9f5ad7bfb96bf69e0dc4481df97f6ee60513c1d94ce981ba6effd524b1`
- Upstream weights revision `524de490e17649ffa0900a02ab5b1a66656c7c96`

The dated archive name is not proof of immutable content. The downloaded
archive and extracted weights are identified by the exact hashes above.

## Distribution basis and retained materials

The upstream ModelScope model metadata retrieved on 2026-10-11 declares
`Apache License 2.0`. Retain `licenses/Apache-2.0.txt`, this source/author/model
record, the manifest and THIRD_PARTY_NOTICES. The existing FunASR model terms
1.1 are also retained in `licenses/FunASR-MODEL-LICENSE.txt`; those terms grant
use, copying, modification and sharing with source/author attribution and
retention of the model name. Neither set of model terms is replaced by the
VoiceFlow source MIT license. This engineering record covers only these pinned
weights and retained notices, not the application's independent native runtime
or public release review. Re-review changed weights, terms or attribution.

## Acceptance and limits

Initial direct-model regression: 14 constructed cases, 20 calls each. Load
302.8 ms; Chinese short-case P95 5.2–14.4 ms, 900-character repeated prose P95
159.8 ms on this development CPU. Direct inference retains erroneous existing
full stops, so the worker rebuilds sentence punctuation paragraph by paragraph.
The final guard must preserve every non-sentence-punctuation character,
including case, apostrophes, hyphens, quotations and numbers. Protected code,
paths, URLs, versions and preserve-format input bypass inference.

Final guarded-worker regression on 2026-10-12: 14 constructed cases, 20 calls
each; startup 476.2 ms; Chinese short-case P95 4.3–9.2 ms; 900-character repeated
prose P95 121.5 ms. Working set 148.2 MiB, peak 186.9 MiB. All lexical guards
passed and the child process exited after shutdown. English-only cases passed
through unchanged. These are development-machine measurements, not installed
package measurements or speech recognition accuracy results.

One CPU thread; separate supervised process; bounded queues; 2,000-character
limit; 600 ms response deadline. A missing, corrupt, crashed, busy or timed-out
worker returns original text. After timeout its channel is discarded so a late
response cannot affect later dictation. Startup runs outside the Qt thread.

Punctuation boundaries can still be wrong. This is text regression evidence,
not a natural-speech recognition accuracy result. Do not advertise improved
CER/WER, flawless punctuation or English punctuation restoration. Final package
measurements, worker cleanup, and application release checks remain required.
