# SenseVoiceSmall Redistribution Decision

Status: **approved for VoiceFlow prerelease redistribution with attribution**

Decision date: 2026-07-27

Decision owner: VoiceFlow release maintainers
License reviewed: FunASR Model Open Source License Agreement, version 1.1

This is an engineering release-compliance decision, not legal advice. It
records why the pinned model may be included in a VoiceFlow prerelease and the
conditions every build must satisfy.

## Pinned artifact

- Product name retained: `SenseVoiceSmall`
- Author/source attribution: Alibaba Group / FunASR / SenseVoice
- Runtime conversion repository:
  `csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`
- Pinned repository revision:
  `2365baeacb507f821a0c8120fcee3d484dba7a07`
- Upstream model recorded in the manifest: `FunAudioLLM/SenseVoiceSmall`
- Primary int8 model SHA-256:
  `c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51`
- Tokens SHA-256:
  `f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc`

## License basis

Version 1.1 expressly permits use, copying, modification, and sharing when the
agreement is followed. Redistribution requires source and author attribution
and retention of the relevant model name.

VoiceFlow satisfies those conditions by:

1. retaining the exact license text as
   `licenses/FunASR-MODEL-LICENSE.txt`;
2. naming SenseVoiceSmall, FunASR, Alibaba Group, the conversion repository,
   upstream project, pinned revision, and hashes in this record and
   `model-manifest.json`;
3. shipping this record, the license text, `THIRD_PARTY_NOTICES.md`, and the
   model manifest with every installer that includes the model; and
4. leaving the model under its upstream terms rather than the VoiceFlow MIT
   source-code license.

## Release conditions

The approval is valid only for the pinned files and revision above. A release
must fail closed if the license file, notice, decision record, model manifest,
or required attribution is missing.

Review this decision again before redistribution if any of these change:

- model repository, upstream model, revision, file set, or SHA-256;
- FunASR model-license version or terms;
- author/source attribution requirements; or
- the way VoiceFlow modifies or separately distributes the model.

This decision removes the model-license inventory blocker only. Code signing,
clean-machine installation, performance, accuracy, and release approval remain
independent gates.
