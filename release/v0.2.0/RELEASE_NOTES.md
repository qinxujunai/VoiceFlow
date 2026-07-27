# VoiceFlow 0.2 for Windows

开口，文字就位。

VoiceFlow 0.2 是面向普通 Windows 用户的首个完整离线版本。下载
`VoiceFlow-0.2.0-Windows-x64.exe`，双击安装即可。安装包包含默认
SenseVoice 模型，不需要 Python；安装完成后，核心听写可在断网状态下使用。

## 这一版带来了什么

- 在记事本、浏览器、文档和聊天窗口里直接说话输入。
- 使用 `F2`、右 `Ctrl` 或鼠标侧键开始和停止；按 `Esc` 取消。
- 识别结果先写入剪贴板，再发送粘贴，并保存在本地历史。
- 长语音的预览与最终转写彼此隔离，停止后补齐完整尾部。
- 胶囊对已确认的新文字进行有界匀速呈现，减少分块跳变；最终结果不等待动画。
- 程序资源与用户数据分离；升级和卸载默认保留配置、历史、词典和模型。
- 完整离线安装包内置经过版本与 SHA-256 固定的 SenseVoice 模型。
- 设置首页围绕“是否就绪”重新设计，模型、麦克风、快捷键和恢复路径更清楚。
- 中英文产品网站清楚说明核心价值、离线边界、质量证据和可下载平台。
- SenseVoice、Qwen3-ASR、Fun-ASR Nano 与 Whisper 完成同机公开样本复测；
  只有 SenseVoice 进入普通用户安装包，其余模型保持实验或拒绝状态。

## 已验证

- Windows 11 x64 覆盖安装、启动、退出和用户数据保留。
- 冻结态启动、模型校验、卸载和数据保留。
- 自动化测试、500 次生命周期循环和完整 ASR 集成。
- 录音胶囊首帧 P95 23 ms，短听写停止到粘贴 P95 455 ms；均为当前发布
  机器 20 次可复现样本，不代表所有电脑。
- 100%、125%、150%、200% 显示缩放 UI 截图门。
- 安装包内模型、Qt/PySide6、Chromium 和第三方许可资产。

## 下载前请知悉

- 当前安装器尚未完成 Authenticode 代码签名，Windows 可能显示信誉提示。
  请只从本 Release 下载，并用 `SHA256SUMS.txt` 核对文件。
- 当前支持 Windows 10 22H2 / Windows 11 x64 的 CPU 路径。
- macOS 尚未提供。全局输入、辅助功能权限、签名和 notarization 必须在
  真实 macOS 环境完成，不能用未经验证的占位包代替。
- 自动粘贴只能确认已发送按键；文字始终先保留在剪贴板和本地历史。

---

## English

VoiceFlow 0.2 is the first complete offline Windows release for everyday
users. Download `VoiceFlow-0.2.0-Windows-x64.exe`; the installer includes the
default SenseVoice model and requires no Python. Core dictation works without
a network after installation.

This release also adds bounded smooth reveal for confirmed preview text,
redesigns the app around readiness and recovery, and documents why SenseVoice
is the only customer-facing model after same-machine comparison with Qwen3-ASR,
Fun-ASR Nano, and Whisper.

The installer is not Authenticode-signed yet, so Windows may show a reputation
warning. Download only from this Release and verify `SHA256SUMS.txt`.

macOS is not available yet. Accessibility, global input, signing, and
notarization must pass on real macOS hardware before a download is offered.
