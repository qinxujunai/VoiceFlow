# VoiceFlow 0.3.0

开口，文字就位；每一句都能找回。

## 本次更新

- SenseVoice 默认改为自动中英检测，减少英文被识别成中文或混合怪串；仍可手动固定中文、English 或粤语。
- 新增可恢复录音会话。录制、识别、剪贴板或交付阶段意外退出后，重启仍可恢复文字或本地音频。
- 所有终稿先写入并反读验证剪贴板；只有目标仍是同一个可编辑控件时才发送粘贴。
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

---

VoiceFlow 0.3.0 adds recoverable recording sessions, verified clipboard-first
delivery, focus-safe paste dispatch, automatic Chinese-English detection, and
a quieter capsule with faster pause correction. The reviewed default models
are bundled for a fully offline, no-setup experience.
