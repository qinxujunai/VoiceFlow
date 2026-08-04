# VoiceFlow 0.2.2

开口，文字就位。

## 本次更新

- 胶囊预览支持中文与英文，英文讲话不再显示模型控制符。
- 文字只向前追加，不回退、不重播，也不会左右往返。
- 首字立即绘制，后续保持固定节奏；胶囊不会用加速动画掩盖积压。
- 停止后仍以完整录音生成最终稿，预览错字不会覆盖最终结果。
- 长听写继续保留完整音频和分段覆盖校验，文本优先写入剪贴板与本地历史。
- 官网与应用说明进一步精简，下载入口指向本版本安装包。

## 下载

Windows 10 / 11 x64 用户只需下载：

`VoiceFlow-0.2.2-Windows-x64.exe`

安装后按 F2、右 Ctrl 或鼠标侧键开始，再按一次停止；Esc 取消。

---

VoiceFlow 0.2.2 adds a bilingual Chinese-English capsule preview, removes
model control tokens from English speech, and keeps every visible character
append-only. The complete stopped audio is still rechecked by the final model
before clipboard output, so the fast preview never replaces the recoverable
final transcript.
