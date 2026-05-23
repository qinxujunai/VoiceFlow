# VoiceFlow

> 声音落下，文字已在光标的尽头。

VoiceFlow。离线，即刻，不丢一字。

---

VoiceFlow 是一个 Windows 本地优先语音输入工具：按 **F2**、**右 Ctrl** 或鼠标侧键开始说话，再按一次停止，识别文本会先进入剪贴板，再尝试粘贴到当前光标位置。

它的产品底线很简单：**只要识别出了文字，文字就不能丢。** 即使当前没有可输入的聊天框，文本也必须留在剪贴板和本地历史里，用户可以直接 `Ctrl+V`。

## 使用

```bat
start.bat
```

也可以直接运行：

```bat
venv\Scripts\python.exe src\main.py
```

快捷键：

| 按键 | 功能 |
| --- | --- |
| F2 | 开始 / 停止语音输入 |
| 右 Ctrl | 开始 / 停止语音输入（pynput 虚拟键码区分左右，不干扰左 Ctrl） |
| 鼠标侧键 xbutton1 / xbutton2 | 开始 / 停止语音输入 |
| Esc | 取消本次录音，不输出文字 |

托盘图标右键菜单提供：显示窗口、复制上一次结果、重新粘贴上一次结果、打开词库、退出。

## 当前能力

- 默认引擎：SenseVoice-Small int8 + sherpa-onnx，本地 CPU 离线运行。
- 流式预览：录音时持续显示识别文本和标点，长录音时自动降低预览频率，避免卡顿。
- 最终输出：停止后用完整音频做最终转写，确保完整性；如果最终转写为空，会用流式缓存兜底。
- 输出兜底：先复制到剪贴板，再模拟 `Ctrl+V`；不会恢复旧剪贴板。
- 历史记录：每次有文字输出都会写入 `logs/history.jsonl`。
- 词库：内置 AI/开发术语、用户词典、短语和错词修正。
- UI：底部居中小胶囊，三条声波符号，文本从中心扩展并在长文本时左侧渐隐。

## 项目结构

```text
src/
  main.py              # 主流程和生命周期
  hotkey_manager.py    # F2 + 鼠标侧键
  recording_session.py # 录音会话
  audio_capture.py     # 麦克风采集
  transcriber.py       # sherpa-onnx ASR
  text_cleaner.py      # 规则清理和词库修正
  vocabulary.py        # 分层词库
  output_handler.py    # 剪贴板 + Ctrl+V + 兜底
  history_store.py     # JSONL 历史
  overlay_webview.py   # PyQt 悬浮窗和托盘
  overlay.html         # 胶囊 UI
  tray_icon.py         # 运行时托盘图标
scripts/
  benchmark_models.py  # 本地模型基准测试
  create_shortcut.ps1  # 创建桌面快捷方式
  generate_icon.py     # 生成 assets/voiceflow.ico
```

## 词库

优先维护这些文件：

- `knowledge-base/corrections.txt`：错词修正，格式 `wrong=correct`
- `knowledge-base/user-dictionary.txt`：人名、项目名、公司名
- `knowledge-base/phrases.txt`：希望完整保留的常用短语
- `knowledge-base/builtin-ai.txt`：通用 AI/工程术语

旧文件 `ai-terms.txt`、`company-terms.txt`、`user-custom.txt` 仍会加载，用于兼容已有内容。

## 验证

```bat
venv\Scripts\python.exe -m py_compile src\main.py src\overlay_webview.py src\hotkey_manager.py src\output_handler.py src\text_cleaner.py
venv\Scripts\python.exe -m pytest tests -q
venv\Scripts\python.exe test_integration.py
```

模型基准：

```bat
venv\Scripts\python.exe scripts\benchmark_models.py
```

创建桌面快捷方式：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
```

## 打包

```bat
venv\Scripts\pyinstaller.exe VoiceFlow.spec
```

`VoiceFlow.spec` 会打包 overlay、配置、词库和应用图标；模型文件默认不打进 exe，仍放在 `models/` 下。
