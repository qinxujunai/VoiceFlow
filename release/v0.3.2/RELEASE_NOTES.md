# VoiceFlow 0.3.2

后台不再拖住听写，快捷键不再静默失效。

发布构建：`build 260825.2`

## 本次更新

- 设置窗口、托盘和快捷键统一连接到稳定的应用控制器，按钮不再因为启动先后顺序拿到空回调。
- 全局快捷键先注册，音频和识别在受监管的独立进程中准备；驱动或识别异常不能冻结设置窗口。
- 音频、实时预览和终稿进程都有心跳、会话代号和有界 IPC；一次健康检查失败不会让监督线程静默退出。
- 删除会与 F2 录音状态竞争并可能导致设置窗口异常的“试说”按钮。状态页仍保留普通文本框，聚焦后直接按 F2 即可测试真实听写链路。
- 历史页提供复制、再次粘贴、单条删除、5 秒撤销和确认后清空全部；安装包明确拒绝携带任何本地 `history.jsonl`。
- 设置页的文件读取、诊断和历史操作使用有界后台任务，导航不会等待模型或磁盘操作。
- 第二次启动会恢复现有设置窗口；安装器创建桌面和开始菜单快捷方式，并使用完整多尺寸图标。
- 保持完全离线、固定内置模型、现有胶囊颜色与静默成功消失行为，不增加模型下载或切换入口。
- 安装器升级会保留当前用户的配置、词典和历史；卸载不会误删用户数据。

## 验证

- 完整自动测试、500 次录音生命周期、10,000 组随机状态序列、故障注入、安全文本模糊测试和 DPI 截图门禁。
- 最终安装器通过隔离安装、模型 SHA-256、热键就绪、进程心跳、升级保留和卸载数据边界检查。
- 具体工程证据见仓库中的 `docs/release-evidence-0.3.2.md`。这些门禁不等同于自然语料准确率宣传。

## 下载

Windows 10 / 11 x64 用户下载：

`VoiceFlow-0.3.2-Windows-x64.exe`

安装包已经包含默认终稿模型和双语流式预览模型，安装后无需额外下载模型。

精确 SHA-256 请以本 Release 同时附带的 `SHA256SUMS.txt` 为准。

当前 Windows 安装包未代码签名，Windows 可能显示安全提示。

---

VoiceFlow 0.3.2 gives the settings UI, tray, and hotkeys one stable controller,
and isolates audio, live preview, and final recognition behind supervised
process boundaries. Hotkeys register before model readiness; failed health
ticks cannot silently stop supervision. The competing Trial button has been
removed, while the normal F2 path remains the only recording interaction.
History supports per-entry deletion, undo, and confirmed clear-all, and the
installer is required to contain no personal `history.jsonl`. The release keeps
the existing quiet capsule, fixed bundled offline models, and clipboard-first
delivery. Build 260825.2 is not code-signed.
