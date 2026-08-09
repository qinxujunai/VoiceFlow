# VoiceFlow 0.3.0

开口，文字就位；每一句都能找回。

## 本次更新

- SenseVoice 默认改为自动中英检测，减少英文被识别成中文或混合怪串；仍可手动固定中文、English 或粤语。
- 新增可恢复录音会话。录制、识别、剪贴板或交付阶段意外退出后，重启仍可恢复文字或本地音频。
- 所有终稿先写入并反读验证剪贴板；只有目标仍是同一个可编辑控件时才发送粘贴。
- 焦点变化、未知控件或权限不兼容时不冒险粘贴，明确显示“已复制到剪贴板”。
- 胶囊只显示模型已确认的文字，长英文和中文都按真实像素宽度平滑扩展，不回滚、不重播、不泄漏模型控制符。
- 设置后台收敛为状态、听写、词典和历史四个任务；提供模型大小、速度、内存和证据说明。
- 可选 Qwen3-ASR 0.6B 支持应用内固定版本下载、进度、取消、SHA-256 校验和启动失败回滚；当前仍标记为实验模型，不宣称比默认模型更准。
- 一小时音频覆盖、剪贴板竞争、焦点安全、状态机故障注入、高 DPI 和真实 WebEngine 进入发布质量门槛。

## 下载

Windows 10 / 11 x64 用户下载：

`VoiceFlow-0.3.0-Windows-x64.exe`

安装包包含默认 SenseVoice 终稿模型和双语流式预览模型；其他实验模型按需下载，不扩大默认安装包。

---

VoiceFlow 0.3.0 adds recoverable recording sessions, verified clipboard-first
delivery, focus-safe paste dispatch, automatic Chinese-English detection, and
an honest in-app model center. The bundled default remains fully offline and
optional models are downloaded only after explicit user action.
