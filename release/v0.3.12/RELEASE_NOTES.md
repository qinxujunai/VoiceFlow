# VoiceFlow 0.3.12

## 中文

- 按住说话：按住 F2、右 Ctrl 或鼠标侧键说话，松开结束并尝试输入；轻按一下开始、再按一下结束也照常可用。设置 → 按键方式可以改成「只用轻按开关」。
- 粘贴发出后，胶囊直接淡出，不再停留显示「已复制到剪贴板」；只有粘贴发不出去时才提示「已复制，按 Ctrl+V 粘贴」。启动时不再弹出胶囊，取消时不再显示「已取消」。文字照常留在剪贴板和历史里。
- 减少长段落和中英混说分段处的多余句号（如「时间的。话呢」「into. the」）；标点仍可能出错。
- 词库术语能还原被拆开的写法和读音相近的多词术语，例如「open AI」→ OpenAI、「cloud code」→ Claude Code。
- 提示文字改得更短。

Windows 10/11 x64，核心听写离线运行。识别引擎和模型权重不变，本版不宣称准确率提升。
安装包未进行 Authenticode 签名，Windows 可能显示安全提示；请核对 Release 的 SHA-256。
macOS 尚无公开下载。

## English

- Hold to talk: hold F2, Right Ctrl or a mouse side button while speaking and release to finish and attempt insertion; a short tap still starts and a second tap finishes. Settings → 按键方式 can switch to taps only.
- After a paste is sent, the capsule fades out instead of holding "Copied to clipboard"; only a paste that could not be sent says "Copied, press Ctrl+V to paste". No capsule at startup and no "Cancelled" label. The text still stays in the clipboard and history.
- Reduces stray full stops at joins in long and mixed Chinese-English dictation; punctuation can still be wrong.
- Dictionary terms are restored when split apart or heard as similar-sounding words, for example "open AI" → OpenAI and "cloud code" → Claude Code.
- Shorter on-screen messages.

Windows 10/11 x64 with offline core dictation. Recognition engines and model weights are unchanged; no accuracy improvement is claimed.
The installer is not Authenticode signed and Windows may show a security prompt. Check the Release SHA-256 before installing.
No public macOS download is available.
