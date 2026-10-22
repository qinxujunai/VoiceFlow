# VoiceFlow — Development

> Documentation sync: **2026-10-22** · Current contract / guide. Synchronization date is not a new test date. [Current index](README.md).

### Run from source

The Windows source environment uses Python 3.12 x64 and a pinned local ASR
build with unused speech synthesis disabled. See the
[build provenance and rebuild procedure](asr-runtime-build.md).

```bat
git clone https://github.com/qinxujunai/VoiceFlow.git
cd VoiceFlow
start.bat
```

### Verify

```bat
venv\Scripts\python.exe scripts\verify.py
venv\Scripts\python.exe scripts\verify.py --release
```

- [Quality gate](quality-gate.md)
- [ASR evaluation plan](asr-evaluation-plan.md)
- [Model strategy and admission decision](model-strategy.md)
- [Product quality standard](product-quality-standard.md)
- [0.3.9 release, installed upgrade and website verification](release-validation-0.3.9.md)
- [Supervised runtime and native UI boundary](decisions/ADR-004-supervised-runtime-boundary.md)
- [Runtime and user-data boundary](runtime-boundary.md)
- [Upgrade and local-data contract](upgrade-and-data-contract.md)
- [Release checklist](release-checklist.md)

VoiceFlow source code is available under the [MIT License](../LICENSE). Models and
third-party components remain subject to their respective licenses:

- [SenseVoice redistribution record](sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL compliance record](qt-lgpl-compliance.md)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)
- [0.3.9 dependency review](../licenses/release-review-0.3.9.md)
- [Corresponding LGPL sources and checksums](../licenses/LGPL-SOURCE.md)
