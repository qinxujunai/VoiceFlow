# VoiceFlow 0.3.0

开口，文字就位；每一句都能找回。

当前同版本修复构建：`build 260810.1`

## 本次更新

- SenseVoice 默认改为自动中英检测，减少英文被识别成中文或混合怪串；仍可手动固定中文、English 或粤语。
- 新增可恢复录音会话。录制、识别、剪贴板或交付阶段意外退出后，重启仍可恢复文字或本地音频。
- 所有终稿先写入并反读验证剪贴板；只有目标仍是同一个可编辑控件时才发送粘贴。
- 修复微信及 UIA Text、Legacy、Win32 富文本输入框被误判为不可编辑的问题；鼠标移出输入框不会影响上屏。
- 聊天记录、按钮、桌面等非输入区域仍只复制，不会为了“看起来成功”而盲目发送粘贴。
- 焦点变化、未知控件或权限不兼容时不冒险粘贴，明确显示“已复制到剪贴板”。
- 胶囊只显示模型已确认的文字，长英文和中文都按真实像素宽度平滑扩展，不回滚、不重播、不泄漏模型控制符。
- 设置后台收敛为状态、听写、词典和历史四个任务；普通用户无需选择、下载或维护模型。
- 胶囊预览与权威终稿使用统一文字颜色，录音条保持稳定红色；完成后明确显示“已完成”。
- 自然停顿后的权威文字更快回填，停止后的短任务不再绕行冗长状态。
- 一小时音频覆盖、剪贴板竞争、焦点安全、状态机故障注入、高 DPI 和真实 WebEngine 进入发布质量门槛。

## 下载

Windows 10 / 11 x64 用户下载：

`VoiceFlow-0.3.0-Windows-x64.exe`

安装包已经包含 SenseVoice 终稿模型和双语流式预览模型，安装后无需额外下载模型。

SHA-256：`AE9C91A446261E5FF08F7960D94060FE5F143AB2D9B101CB8ACE2E3FAECB4731`

当前 Windows 安装包未代码签名，Windows 可能显示安全提示。

---

VoiceFlow 0.3.0 adds recoverable recording sessions, verified clipboard-first
delivery, focus-safe paste dispatch, automatic Chinese-English detection, and
a quieter capsule with faster pause correction. The reviewed default models
are bundled for a fully offline, no-setup experience. Build 260810.1 also
restores paste dispatch for verified rich-text chat editors while keeping
non-editable surfaces clipboard-only. The Windows installer is not code-signed.
