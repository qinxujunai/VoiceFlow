# VoiceFlow — Development

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
- [0.3.6 release verification evidence](release-evidence-0.3.6.md)
- [Local responsiveness and resource repair](local-upgrade-2026-10-04.md)
- [Runtime and user-data boundary](runtime-boundary.md)
- [Upgrade and local-data contract](upgrade-and-data-contract.md)
- [Release checklist](release-checklist.md)

VoiceFlow source code is available under the [MIT License](../LICENSE). Models and
third-party components remain subject to their respective licenses:

- [SenseVoice redistribution record](sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL compliance record](qt-lgpl-compliance.md)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)
