# VoiceFlow

<p align="right">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

> 开口，文字就位。

[![Windows quality](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml/badge.svg)](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml)
[![Windows 下载](https://img.shields.io/badge/Windows-下载-087FE7)](https://github.com/qinxujunai/VoiceFlow/releases/download/v0.2.1/VoiceFlow-0.2.1-Windows-x64.exe)

![VoiceFlow 动态演示](docs/voiceflow-demo.svg)

VoiceFlow 是 Windows 上的离线语音输入工具。按 `F2` 开始说话，再按一次，
文字就会回到当前光标处。识别在本机完成，不需要账户，也不上传录音。

## 为什么是 VoiceFlow

- **完全离线**：核心听写不调用云端识别，断网仍可使用。
- **任意输入框**：在记事本、浏览器、文档或聊天窗口中直接说话输入。
- **结果可恢复**：文字先进入剪贴板，再尝试粘贴，并同步保存到本地历史。
- **长语音不丢尾**：实时预览只负责反馈，停止后仍会完成全部音频的最终转写。

## 下载

普通用户只需下载
[VoiceFlow-0.2.1-Windows-x64.exe](https://github.com/qinxujunai/VoiceFlow/releases/download/v0.2.1/VoiceFlow-0.2.1-Windows-x64.exe)。
安装包已经包含默认离线模型，不需要 Python。

> 当前安装包尚未完成 Authenticode 代码签名，Windows 可能显示信誉提示。
> 请仅从本仓库或[产品网站](https://qinxujunai.github.io/VoiceFlow/)下载。

系统要求：Windows 10 / 11 x64、可用麦克风。

## 使用

| 按键 | 行为 |
| --- | --- |
| `F2` | 开始 / 停止语音输入 |
| `Right Ctrl` | 开始 / 停止语音输入 |
| `xbutton1` / `xbutton2` | 用鼠标侧键开始 / 停止 |
| `Esc` | 取消当前录音，不输出文字 |

正常输出链路：

```text
说话 → 本地识别 → 文本清理 → 剪贴板 → 当前光标 → 本地历史
```

## 隐私与联网

录音、转写、词库和历史默认只保存在本机。日常运行不会自动下载模型、
检查更新或调用云端识别服务。源码模式只有在用户明确准备模型时才会联网。

<details>
<summary><strong>开发、验证与许可</strong></summary>

### 从源码运行

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

- [质量门](docs/quality-gate.md)
- [ASR 评测计划](docs/asr-evaluation-plan.md)
- [模型策略与准入结论](docs/model-strategy.md)
- [产品质量标准](docs/product-quality-standard.md)
- [运行时与用户数据边界](docs/runtime-boundary.md)
- [发布检查清单](docs/release-checklist.md)

项目代码基于 [MIT License](LICENSE) 开源。模型及第三方组件遵循各自许可证：

- [SenseVoice 再分发记录](docs/sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL 合规记录](docs/qt-lgpl-compliance.md)
- [第三方声明](THIRD_PARTY_NOTICES.md)

</details>
