# VoiceFlow — Development

### 从源码运行

Windows 源码环境使用 Python 3.12 x64。ASR 依赖来自仓库内固定的构建，
关闭未使用的语音合成功能；[构建来源与重建步骤](asr-runtime-build.md)。

```bat
git clone https://github.com/qinxujunai/VoiceFlow.git
cd VoiceFlow
start.bat
```

### 验证

```bat
venv\Scripts\python.exe scripts\verify.py
venv\Scripts\python.exe scripts\verify.py --release
```

- [质量门](quality-gate.md)
- [ASR 评测计划](asr-evaluation-plan.md)
- [模型策略与准入结论](model-strategy.md)
- [产品质量标准](product-quality-standard.md)
- [0.3.6 发布验证证据](release-evidence-0.3.6.md)
- [2026-10-04 本机响应与资源修复](local-upgrade-2026-10-04.md)
- [运行时与用户数据边界](runtime-boundary.md)
- [更新与本地数据契约](upgrade-and-data-contract.md)
- [发布检查清单](release-checklist.md)

项目代码基于 [MIT License](../LICENSE) 开源。模型及第三方组件遵循各自许可证：

- [SenseVoice 再分发记录](sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL 合规记录](qt-lgpl-compliance.md)
- [第三方声明](../THIRD_PARTY_NOTICES.md)
