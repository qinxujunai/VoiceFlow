# VoiceFlow

> 免费、开源、完全本地的语音转文字工具。按一下快捷键，说话，安静后文字自动粘贴到光标位置。

---

## 🎯 为什么做这个

在跟 AI 对话、写代码、聊天的场景里，打字是一个瓶颈——你想得快，手跟不上。而市面上的解决方案各有各的问题：

| 痛点 | 具体场景 | VoiceFlow 的方案 |
|------|---------|-----------------|
| **输入法卡顿** | 打着打着切输入法崩了、卡死、丢字 | 语音直出，不经过输入法 |
| **国外产品付费 + 中文差** | Wispr Flow $10/月，Speakly 订阅制 | 完全免费开源，SenseVoice 原生中文 |
| **怕丢** | 讲了一大段话崩了，什么都没留下 | 粘贴失败自动存剪贴板 + 本地历史 |
| **隐私** | 语音数据上传云端 | 100% 本地运行，数据不出本机 |
| **通用模型不懂你的词** | 说"Cursor"识别成"科瑟" | 文本修正引擎，越用越懂你 |

---

## ✨ 核心功能

- **一键录音** — 按 F2 开始说话，安静 1.5 秒自动停止粘贴
- **流式显示** — 说话时文字实时出现在悬浮条上
- **VAD 静音检测** — Push-to-Talk 模式下自动识别说话结束，无需手动松键
- **系统托盘** — 启动后最小化到托盘，只在录音时弹出悬浮窗
- **文字清理** — 自动去口头禅（嗯、啊、那个）、中英文加空格、常见错字修正
- **防丢兜底** — 粘贴失败时自动存剪贴板 + 写入历史文件
- **全局可用** — 在任何应用（微信、Word、浏览器、IDE）中使用
- **热词修正** — 按 Ctrl+Alt+H 弹出对话框，输入错误→正确映射

---

## ⌨️ 快捷键

| 功能 | 快捷键 | 说明 |
|------|--------|------|
| 录音 | **F2** | 按一下开始说话，安静 1.5 秒自动停止，文字粘贴 |
| 取消 | **Esc** | 丢弃本次录音 |

---

## 🏗️ 技术架构

```
VoiceFlow/
├── src/
│   ├── main.py              # 主入口、管道编排
│   ├── audio_capture.py     # 麦克风采集 + VAD 静音检测
│   ├── transcriber.py       # Sherpa-ONNX + SenseVoice 语音识别
│   ├── text_cleaner.py      # 文字后处理（规则清理 + 错字修正）
│   ├── output_handler.py    # 文字注入 + 兜底机制
│   ├── hotkey_manager.py    # 全局快捷键监听
│   ├── overlay_webview.py   # PyQt6 悬浮窗 + 系统托盘
│   └── overlay.html         # 苹果风格毛玻璃 UI
├── models/sensevoice/       # SenseVoice 模型文件 (229MB)
├── knowledge-base/          # 修正词表（260+ AI 术语）
├── config.yaml              # 配置文件
├── start.bat                # 一键启动
├── VoiceFlow.spec           # PyInstaller 打包配置
└── README.md
```

**技术栈：**
- 语音识别：Sherpa-ONNX + SenseVoice-Small（阿里开源，234M 参数）
- VAD：能量检测，零额外依赖
- 音频采集：sounddevice
- 热键：pynput（吞键模式，不和输入法冲突）
- 文字注入：pyperclip + pyautogui（含兜底）
- UI：PyQt6 WebView + HTML/CSS 毛玻璃

---

## 🚀 快速开始

### 环境要求
- Windows 10/11
- Python 3.10+
- 麦克风

### 安装

```bash
git clone https://github.com/yourname/VoiceFlow.git
cd VoiceFlow

# 创建虚拟环境 + 安装依赖
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 下载模型
python scripts/download_models.py
```

### 使用

双击 `start.bat`，或在终端：

```bash
venv\Scripts\python.exe src\main.py
```

启动后托盘出现 VoiceFlow 图标。按 **F2** 开始说话，安静 1.5 秒后文字自动粘贴。

---

## 📊 性能

| 指标 | 数值 |
|------|------|
| 识别延迟 | RTF 0.026（处理 1 秒音频仅需 0.026 秒） |
| 文字清理延迟 | < 1ms（纯正则） |
| 模型大小 | 229MB（int8） |
| 内存占用 | ~200MB |
| 支持语言 | 中文、英文、日文、韩文、粤语 |

---

## 🆚 对比

| 特性 | VoiceFlow | Wispr Flow | Speakly |
|------|-----------|------------|---------|
| **价格** | 免费 | $10/月 | 订阅制 |
| **离线** | ✅ | ❌ | 部分 |
| **VAD 自动停** | ✅ | ✅ | ✅ |
| **系统托盘** | ✅ | ✅ | ✅ |
| **热词修正** | ✅ | ❌ | ❌ |
| **防丢兜底** | ✅ | ❌ | ❌ |
| **开源** | ✅ | ❌ | ❌ |

---

## 📄 许可证

MIT License
