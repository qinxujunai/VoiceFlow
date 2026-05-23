# VoiceFlow

VoiceFlow 是一个 Windows 本地语音输入工具：按 **F2** 开始说话，再按 **F2** 停止，文字会粘贴到当前光标位置。目标不是做一个炫技 ASR demo，而是做一个日常可依赖的系统级输入基础设施。

核心原则：

- 本地优先：默认不上传语音，不依赖云服务。
- 低摩擦：F2 是唯一主入口，Esc 取消。
- 不丢字：粘贴失败时保留剪贴板兜底，并写入本地历史。
- 懂你的词：AI/工程术语、公司词、个人修正词表持续积累。
- 视觉克制：底部居中胶囊只表达当前状态，不抢注意力。

## 使用

```bash
双击 start.bat
# 或
venv\Scripts\python.exe src\main.py
```

快捷键：

| 按键 | 功能 |
| --- | --- |
| F2 / 鼠标上侧键 | 开始录音 / 停止并粘贴 |
| Esc | 取消本次录音 |

## 当前能力

- SenseVoice-Small + sherpa-onnx 本地 ASR。
- 录音期间预览转写，停止后用完整音频生成最终文本。
- 规则清理：口头禅、中英文空格、常见音近词修正。
- 分层词库：内置 AI 术语、用户词典、错词修正、常用短语。
- 剪贴板粘贴 + 失败兜底。
- `logs/history.jsonl` 记录原始文本、清理后文本和输出状态。
- PyQt6 WebView 底部居中胶囊 + 系统托盘状态图标。

## 项目结构

```text
VoiceFlow/
├── src/
│   ├── main.py              # 主流程编排
│   ├── recording_session.py # 录音生命周期
│   ├── audio_capture.py     # 麦克风采集
│   ├── transcriber.py       # sherpa-onnx ASR
│   ├── vocabulary.py        # 分层词库
│   ├── text_cleaner.py      # 文本清理和修正
│   ├── output_handler.py    # 粘贴与兜底
│   ├── history_store.py     # JSONL 历史
│   ├── ui_state.py          # UI 状态定义
│   ├── overlay_webview.py   # 悬浮胶囊 + 托盘
│   ├── overlay.html         # 胶囊 UI
│   └── tray_icon.py         # 运行时托盘图标
├── knowledge-base/
│   ├── builtin-ai.txt
│   ├── corrections.txt
│   ├── user-dictionary.txt
│   ├── phrases.txt
│   └── legacy lists...
├── scripts/
├── config.yaml
├── start.bat
└── test_integration.py
```

## 词库

优先编辑这些文件：

- `knowledge-base/corrections.txt`：错词修正，格式 `错词=正确词`。
- `knowledge-base/user-dictionary.txt`：人名、项目名、公司名。
- `knowledge-base/phrases.txt`：希望完整保留的常用短语。
- `knowledge-base/builtin-ai.txt`：通用 AI/工程术语。

旧的 `ai-terms.txt`、`company-terms.txt`、`user-custom.txt` 仍会加载，用于兼容已有内容。

## 验证

```bash
venv\Scripts\python.exe -m py_compile src\*.py
venv\Scripts\python.exe -m pytest tests -q
venv\Scripts\python.exe test_integration.py
```

## 路线图

优先级从高到低：

1. 胶囊 UI 细节继续打磨：缩放、多显示器、长文本。
2. 词库学习闭环：从历史中把用户修正写回 `corrections.txt`。
3. 真实安装包：PyInstaller build smoke、正式 exe 图标、模型缺失引导。
4. 可选高级引擎：Qwen3-ASR 实验模式，不进入默认路径。
5. 可选本地整理文字模式：默认关闭，不能破坏低延迟主链路。
