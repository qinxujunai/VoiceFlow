# Model Center Contract

Status: superseded by
[`ADR-002`](decisions/ADR-002-single-visual-state-and-fixed-model.md). The
ordinary product no longer exposes model selection, download, repair, or
switching. The remaining sections are retained as historical engineering
context only.

## Ordinary user choices

| Mode | Model | Download | Preliminary short P95 | Preliminary Clean CER | Peak memory | Product decision |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 极速听写 | SenseVoice Small int8 | 240,500,355 bytes | 163 ms | 2.27% | 355 MB | Recommended default |
| 多语言识别 | Qwen3-ASR 0.6B int8 | 987,015,347 bytes | 1,298 ms | 23.02% | 1,459 MB | User-initiated lab candidate |

These numbers come from the existing same-machine preliminary corpus and are
shown with the limitation that this corpus is too small to represent all users,
accents, environments, or long-form speech. They are rejection evidence, not a
marketing accuracy claim. Qwen3 is not labelled more accurate because it did
not win the current evidence.

SenseVoice now defaults to `auto`. The original clean English reference alone
favoured `zh` by one word, but it hid the actual failure mode: two short natural
English samples were decoded as Chinese or mixed-script garbage with the `zh`
hint and returned to lexical English with `auto` / `en`. Nine Chinese and mixed
regression clips produced eight identical transcripts; the remaining difference
was punctuation at a code-switch boundary. This evidence supports automatic
bilingual detection as the safer default without claiming population-level
accuracy. The settings UI keeps explicit Chinese-first, English-first and
Cantonese choices for users who need a fixed language.

## Download states

`missing -> downloading -> verifying -> ready`

Failures become `failed`; cancellation becomes `cancelled`; an installed asset
whose pinned size or SHA-256 differs becomes `corrupt`. Downloads use the fixed
revision and hashes in `model-manifest.json`. The active model directory is not
overwritten until the candidate has verified.

## Switching and rollback

Changing models stages an atomic transaction containing the complete previous
configuration. The candidate becomes authoritative only after it loads on the
next VoiceFlow startup. A load failure restores the exact previous config and
loads the previous model. A successful startup removes the transaction.

The settings UI never exposes rejected or ineligible engineering inventory as
ordinary choices. Fun-ASR Nano, Whisper controls, and Qwen3 1.7B remain in the
engineering manifest for reproducibility rather than transferring research risk
to users.
