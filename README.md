# VoiceFlow

<p align="right">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

> 离线，即刻，不丢一个字。

[![Windows quality](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml/badge.svg)](https://github.com/qinxujunai/VoiceFlow/actions/workflows/windows-quality.yml)
[![产品网站](https://img.shields.io/badge/产品网站-打开-111111)](https://qinxujunai.github.io/VoiceFlow/)
[![Windows Beta](https://img.shields.io/badge/Windows_Beta-下载-087FE7)](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.2.0-beta.1)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D4)](#系统要求)
[![Local first](https://img.shields.io/badge/local--first-offline-2EA44F)](#隐私与联网)
[![License](https://img.shields.io/github/license/qinxujunai/VoiceFlow)](LICENSE)

![VoiceFlow 动态演示](docs/voiceflow-demo.svg)

VoiceFlow 是 Windows 上的本地语音输入工具。按 `F2` 开始说话，再按一次，文字就会回到当前光标处。识别、词库与历史默认留在本机；即使目标应用没有接住粘贴，结果仍可从剪贴板和本地历史中找回。

## 核心能力

- **在任何输入框里说话**：通过 `F2`、右 `Ctrl` 或鼠标侧键，在当前应用直接输入。
- **离线识别**：默认不调用云端 ASR，也不把录音交给在线大模型处理。
- **结果可恢复**：先写入剪贴板，再尝试粘贴，并同步保存到本地历史。
- **长语音持续流畅**：预览、音频缓存与 UI 更新都有固定上限，不随录音时长持续堆积。
- **反馈真实而克制**：录音波形来自麦克风实际音量；预览只表达进度，最终转写才会输出。
- **安静驻留**：托盘运行、单实例启动、小尺寸悬浮胶囊，不打断当前工作。

## 快速开始

普通用户请从[产品网站](https://qinxujunai.github.io/VoiceFlow/)选择平台，
或直接打开 [GitHub Releases](https://github.com/qinxujunai/VoiceFlow/releases/tag/v0.2.0-beta.1)
下载 `VoiceFlow-Setup-0.2.0-beta.1-x64.exe`。安装包已包含默认离线模型，
不需要 Python。

> 当前公开 Beta 尚未完成 Authenticode 签名，Windows 可能显示信誉提示。
> 请只从本仓库下载，并用 Release 中的 `SHA256SUMS.txt` 核对文件。

开发者可从源码启动：

```bat
git clone https://github.com/qinxujunai/VoiceFlow.git
cd VoiceFlow
start.bat
```

源码模式首次启动会检查 Python 环境并准备本地模型。模型文件不进入 Git
仓库；任何下载都需要用户明确触发，并在启用前校验版本与文件完整性。

环境准备完成后，可通过桌面快捷方式安静启动。重复启动只会唤起现有窗口，不会产生多个主进程。

### 系统要求

- Windows 10 或 Windows 11
- 可用麦克风
- 安装版无需网络；源码版首次准备环境与模型时需要网络

## 使用方式

| 按键 | 行为 |
| --- | --- |
| `F2` | 开始 / 停止语音输入 |
| `Right Ctrl` | 开始 / 停止语音输入 |
| `xbutton1` / `xbutton2` | 用鼠标侧键开始 / 停止 |
| `Esc` | 取消当前录音，不输出文字 |

正常链路始终是：

```text
说话 → 本地识别 → 确定性文本清理 → 剪贴板 → 当前光标 → 本地历史
```

录音时的胶囊文字是即时预览。停止后，VoiceFlow 会完成剩余音频的最终转写，再输出完整结果。短语音执行一次完整识别；长语音会持续收束稳定片段，并在停止时补齐尾部。

## 可靠性设计

- **静音保护**：本地 VAD 会拦截底噪、按键声和纯标点幻听，同时保留真实的单字输入。
- **完整尾部**：最终结果必须覆盖停止时的全部音频，流式预览不能替代最终转写。
- **有界实时链路**：预览只读取最近的固定音频窗口；稳定片段完成后释放旧 PCM。
- **最新帧优先**：悬浮层只渲染最新状态，过期识别结果和 UI 帧不会排队追赶。
- **故障兜底**：即使自动粘贴失败，已识别文字仍保留在剪贴板与 `%LOCALAPPDATA%\VoiceFlow\logs\history.jsonl`。

## 模型与语言

当前默认引擎是离线 SenseVoice。VoiceFlow 也提供统一的模型适配与本机评测工具，用同一套准确率、延迟、尾部完整性和资源门槛比较 SenseVoice、Qwen3-ASR 与 Fun-ASR Nano；只有通过全部质量门的候选才会成为默认模型。

首次运行会从项目或安装目录的 `config.yaml` 初始化用户配置，之后运行时设置保存在 `%LOCALAPPDATA%\VoiceFlow\config.yaml`。当前支持的 `zh`、`en`、`auto` 等语言选项取决于所选模型的实际能力。

## 开发与验证

```bat
venv\Scripts\python.exe scripts\verify.py
venv\Scripts\python.exe scripts\verify.py --release
```

质量门覆盖环境诊断、编译检查、自动化测试、500 次确定性生命周期循环、快速 ASR benchmark 与集成测试。发布检查还要求真实性能记录、DPI 截图、键盘与 Narrator 任务、长录音、设备切换和驻留测试。

- [质量门](docs/quality-gate.md)
- [ASR 评测计划](docs/asr-evaluation-plan.md)
- [运行时与用户数据边界](docs/runtime-boundary.md)
- [发布检查清单](docs/release-checklist.md)

## 隐私与联网

录音、转写、词库和历史默认只保存在本机。运行时不会自动下载模型、检查更新或调用云端识别服务；只有用户明确运行模型准备命令时才会联网。私有评测音频位于 Git 忽略目录，评测工具不会上传音频。

## 项目状态

VoiceFlow 0.2.0-beta.1 是 Windows x64 公开测试版。安装态运行时边界、
用户数据保留、SenseVoice 再分发记录和完整离线安装已完成本机验收。
当前仍有两项明确限制：

- 安装器尚未完成 Authenticode 代码签名，不是稳定版。
- macOS 版尚未发布；全局输入、辅助功能权限、签名与 notarization
  必须在真实 macOS 环境分别验收，不能由 Windows 构建代替。

## 许可证

项目代码基于 [MIT License](LICENSE) 开源。模型及第三方组件遵循各自许可证，公开分发前会单独完成授权审查。

- [SenseVoice 再分发记录](docs/sensevoice-redistribution-decision.md)
- [Qt / PySide6 LGPL 合规记录](docs/qt-lgpl-compliance.md)
