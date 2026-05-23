# AGENTS.md — VoiceFlow

## 项目定位
本地语音转文字。按 F2 说话，安静 1.5 秒自动粘贴。免费、开源、离线。

## 技术栈
- Python 3.14 / Windows
- Sherpa-ONNX + SenseVoice-Small（ASR）
- sounddevice（麦克风 + VAD 能量检测）
- keyboard（全局热键）
- pyperclip + pyautogui（文字注入）
- PyQt6 WebView + HTML/CSS（悬浮窗 + 系统托盘）
- config.yaml（一切行为配置）

## 快捷键
| 功能 | 按键 |
|------|------|
| 录音 | F2 |
| 取消 | Esc |

## 文件结构
```
src/
├── main.py            # 入口、管道编排
├── audio_capture.py   # 麦克风 + VAD
├── transcriber.py     # sherpa-onnx ASR
├── text_cleaner.py    # 文本后处理
├── output_handler.py  # 文字注入 + 兜底
├── hotkey_manager.py  # 快捷键
├── overlay_webview.py # PyQt6 悬浮窗 + 托盘
└── overlay.html       # 毛玻璃 UI
config.yaml
start.bat
```

## 编程准则 — Karpathy 四原则

### 1. 先思考再编码
- 动代码前说出假设。不确定就问，不要猜
- 多种理解 → 列出选项
- 有更简单做法 → 说出来

### 2. 简约至上
- 没要求的不写。只用一次的代码不建抽象层
- 不可能出现的场景不加错误处理
- 200 行能缩到 50 行就缩

### 3. 精准编辑
- 只动必须动的，不碰相邻代码、不顺手重构
- 匹配已有风格
- 看到废代码 → 提一句，不要直接删

### 4. 目标驱动
- 任务 = 可验证目标 + 编号步骤 + 每步验证条件

## 设计决策
- ❌ 不做 AI 校对 / LLM 润色
- ❌ 不引入新模型、不联网
- ✅ text_cleaner 规则后处理（零延迟）
- ✅ 粘贴兜底（永不丢字）
