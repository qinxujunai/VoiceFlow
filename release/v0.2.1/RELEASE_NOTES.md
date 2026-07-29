# VoiceFlow 0.2.1

开口，文字就位。

VoiceFlow 是 Windows 上的离线语音输入工具。按 `F2` 开始说话，再按一次，
文字会回到当前光标处。安装包已经包含离线模型，不需要 Python。

## 本次更新

- 胶囊文字只向前追加，不再回刷、倒退或重复播放。
- 实时文字统一使用一种颜色，不再出现灰色尾部和颜色渐变。
- 修复 20～44 秒录音可能只保留尾部的问题。
- 停止录音后验证完整音频覆盖，异常时自动使用完整录音重新识别。
- 清理旧安装包带入的私人词条，同时保留用户自己添加的词典内容。
- 修复全新 Windows 构建环境中的预览模型下载与校验。

## 下载

普通用户只需下载 `VoiceFlow-0.2.1-Windows-x64.exe`。

- Windows 10 / 11 x64
- 核心听写可断网使用
- 结果保留在剪贴板和本地历史

> 当前安装包尚未完成 Authenticode 代码签名，Windows 可能显示信誉提示。
> 请只从本 Release 或 VoiceFlow 官网下载。

SHA-256：

```text
E1B52CC42B97340BEE18B298788B936324B5DB108AB533B9F1977107E4817C84
```

---

## English

VoiceFlow 0.2.1 stabilizes live preview, preserves complete stopped audio,
removes private seed vocabulary, and uses one consistent color for streaming
text. Download `VoiceFlow-0.2.1-Windows-x64.exe` for Windows 10 or 11 x64.

The installer is not yet Authenticode-signed, so Windows may show a reputation
warning. Download only from this Release or the VoiceFlow product site.
