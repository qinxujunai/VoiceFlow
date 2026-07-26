# VoiceFlow 0.2.0-beta.1

首个面向普通 Windows 用户的完整离线测试版。

## 下载与安装

下载 `VoiceFlow-Setup-0.2.0-beta.1-x64.exe`，双击安装即可。安装包包含
SenseVoice 默认模型，不需要 Python，安装完成后核心听写可断网使用。

当前安装器尚未完成 Authenticode 签名，因此 Windows 可能显示信誉提示。
请只从本 GitHub Release 下载，并用随附的 `SHA256SUMS.txt` 核对文件。

## 这次完成了什么

- 新增产品化首页、首次试说区、历史、听写、快捷键、词典、结构化诊断和关于页。
- 程序资源与用户数据彻底分离；配置、历史和用户词典保存到
  `%LOCALAPPDATA%\VoiceFlow`。
- 覆盖升级只替换程序目录，卸载默认保留用户数据。
- 安装态不再依赖 `venv`、源码脚本或仓库路径。
- 离线安装包内置经过版本与 SHA-256 固定的 SenseVoice 模型。
- 快捷键到胶囊真实 Qt 首帧 P95 为 23 ms。
- 短语音停止到输出 P95 为 455 ms；两分钟渐进式长听写停止到输出
  P95 为 504 ms（各 20 次可重复测试）。
- 中英文产品网站、平台选择和 GitHub Pages 自动部署已就绪。

## 已验证

- Windows 11 x64 本机覆盖安装、启动、退出与用户数据保留。
- 临时干净目录安装、冻结态启动、模型校验、卸载与数据保留。
- 161 项自动化测试、500 次生命周期循环、完整 ASR 集成。
- 100%、125%、150%、200% 显示缩放 UI 截图门。
- 安装包内模型、Qt/PySide6、Chromium 和第三方许可资产。

## 已知限制

- 这是未签名的公开 Beta，不是稳定版。
- 当前仅支持 Windows 10 22H2 / Windows 11 x64 CPU 路径。
- macOS 版本尚未发布。全局输入、辅助功能权限、签名和 notarization
  必须在真实 macOS 环境完成，不能用未经验证的占位包代替。
- 自动粘贴只能确认已发送按键；文字会始终先保留在剪贴板和本地历史。

---

The first complete offline Beta for regular Windows users. It includes the
default SenseVoice model and requires no Python. This build is currently
unsigned, so Windows may show a reputation warning. Download only from this
Release and verify `SHA256SUMS.txt`.

macOS is not released. Accessibility, global input, signing, and notarization
must pass on real macOS hardware before a download is offered.
