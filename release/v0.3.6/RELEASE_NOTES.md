# VoiceFlow 0.3.6

Windows 稳定性与数据安全补丁。发布构建：`build 261001.4`。

## 本次修复

- 修复主界面异常退出后原生子进程残留；三个工作进程在父进程退出后自动终止。
- 安装验证新增上一公开版本升级、卸载数据保留与强制退出后无残留进程检查。
- 修复官网三处文字对比度不足，并移除超出验证范围的绝对承诺。

- 清除本机数据、删除恢复录音与录音/恢复操作互斥，防止正在使用的录音被删除。
- 取消录音完成麦克风清理后才允许下一次录音；清理失败时保持阻塞状态。
- 手动更新检查核对 GitHub 安装包摘要、校验文件摘要和唯一安装包校验项；拒绝重复资产、未完成上传、空资产和过大响应。
- 官网发布入口同步核对版本化资产地址、校验文件长度和摘要，避免错误下载地址进入官网。
- 增加并发与异常资产回归测试，复核设置界面、流式胶囊、DPI、动画、故障恢复和安装生命周期。

## 下载与校验

Windows 10 / 11 x64 安装包：`VoiceFlow-0.3.6-Windows-x64.exe`。

仅从本 Release 下载匹配安装包，并用附带的 `SHA256SUMS.txt` 核对 SHA-256。发布同时附带 `SBOM.cdx.json` 和 `THIRD_PARTY_NOTICES.md`；官网在全部匹配资产通过校验后才显示入口。

安装包包含默认离线模型和双语流式预览模型。日常启动和听写不联网，只有点击检查更新才访问 GitHub。升级保留本机配置、词典和历史。

本项目尚未配置 Windows 代码签名证书，安装包未签名，Windows 可能显示安全提示。校验摘要不等于代码签名。自动化验证覆盖固定语料和隔离安装流程，不能证明所有设备、应用或自然语音均无缺陷。

---

VoiceFlow 0.3.6 fixes destructive local-data races and strengthens manual update integrity checks. The tag-driven Windows release includes its matching installer, SHA-256 manifest, SBOM, and third-party notices. The installer is unsigned; metadata verification does not replace code signing. Dictation remains local and offline by default.
