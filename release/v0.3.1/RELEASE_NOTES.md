# VoiceFlow 0.3.1

开口，文字就位；每一句都能找回。

发布构建：`build 260811.2`

## 本次更新

- 交付目标改为停止时的当前前台窗口；录音开始时的控件身份只用于诊断，不再因为聊天输入框内部的 `EditControl` / `GroupControl` 抖动而漏掉粘贴。
- 普通前台应用默认发送一次粘贴指令；桌面、系统安全界面、权限不兼容、VoiceFlow 自身非输入窗口或没有有效前台窗口时仍只复制。
- UI Automation 焦点读取收敛到独立 MTA 线程，并保留有界、无标题和无文本的隐私安全焦点轨迹。
- 终稿仍先进入剪贴板并逐字符反读验证；粘贴指令只发送一次，不自动重试，不把“已发送”写成“已被目标程序接收”。
- 自然停顿稳定窗调整为 320ms；停止后继续保持 350ms 内无等待文案、权威终稿原位替换的胶囊合同。
- 性能记录区分墙钟间隔和有效讲话间隔，静音不再被误算成预览模型卡顿。
- 保持现有胶囊颜色、尺寸、完成状态、固定内置模型和完全离线行为；普通设置页不增加模型下载或切换入口。
- 快捷键不再使用固定 500ms 防抖，而是按真实按下/松开边沿串行处理；快速连按不会被吞，长按也不会重复启停。
- 空录音安静取消，不再显示红色“无音频”；后台去除模型名和线程等工程术语，词典改为逐条管理，历史每条记录直接提供复制和再次粘贴。
- 官网中英文演示与真实胶囊一致：完成状态显示勾选和“已完成 / Done”，不再出现字符数或旧版复制文案。

## 下载

Windows 10 / 11 x64 用户下载：

`VoiceFlow-0.3.1-Windows-x64.exe`

安装包已经包含 SenseVoice 终稿模型和双语流式预览模型，安装后无需额外下载模型。

精确 SHA-256 请以本 Release 同时附带的 `SHA256SUMS.txt` 为准。

当前 Windows 安装包未代码签名，Windows 可能显示安全提示。

---

VoiceFlow 0.3.1 prioritizes the foreground target at stop time, preventing
transient accessibility-tree changes inside rich-text chat editors from
degrading delivery to clipboard-only. It keeps verified clipboard-first
delivery, bounded private focus diagnostics, a 320 ms pause stabilization
window, the existing quiet capsule, and the same fully offline bundled models.
Fast repeated triggers now follow physical key edges through one serialized
intent queue. The settings, dictionary, history, public copy, and bilingual
product demo now match the shipped behavior without model or thread jargon.
Build 260811.2 is not code-signed.
