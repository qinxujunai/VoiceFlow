# AGENTS.md — VoiceFlow 项目共享上下文
# Claude Code & Hermes 协作开发，双方均读取此文件

---

## 项目定位
VoiceFlow = 本地语音转文字工具。免费、开源、离线。
按右 Ctrl 说话，安静 1.5 秒自动停止粘贴。对标 Wispr Flow（$10/月）。

## 技术栈
- Python 3.14（Windows）
- Sherpa-ONNX + SenseVoice-Small（ASR 引擎）
- sounddevice（麦克风 + 内置 VAD 能量检测）
- pynput（全局热键，吞键模式）
- pyperclip + pyautogui（文字注入）
- PyQt6 WebView + HTML/CSS（毛玻璃悬浮窗 + 系统托盘）
- config.yaml（一切行为配置）

## 快捷键
| 功能 | 快捷键 | 说明 |
|------|--------|------|
| Push-to-Talk | 右 Ctrl | 按一下开始，安静1.5秒自动停，粘贴文字 |
| Toggle | Ctrl+Shift+Win | 按一下开始，再按一下停（不自动停） |
| 取消 | Esc | 丢弃录音 |
| 添加修正 | Ctrl+Alt+H | 弹窗输入错误→正确映射 |

## 文件结构（关键文件）
```
src/
├── main.py            # 主入口、管道编排
├── audio_capture.py   # 麦克风采集 + VAD（check_silence()）
├── transcriber.py     # sherpa-onnx ASR（SenseVoice 不支持热词）
├── text_cleaner.py    # 文本后处理（新模块）
├── output_handler.py  # 文字注入 + 兜底机制
├── hotkey_manager.py  # 全局快捷键（吞键模式）
├── overlay_webview.py # PyQt6 悬浮窗 + 系统托盘
└── overlay.html       # 苹果风格毛玻璃 UI
config.yaml
start.bat
VoiceFlow.spec         # PyInstaller 打包
```

## 编程准则 — Karpathy 四原则（双方遵守）

### 1. 先思考再编码
- 动代码前说出假设。不确定就问，不要猜
- 多种理解 → 列出选项
- 有更简单做法 → 说出来
- 搞不清楚 → 停下来问

### 2. 简约至上
- 没要求的不写。只用一次的代码不建抽象层
- 不可能出现的场景不加错误处理
- 200 行能缩到 50 行就缩

### 3. 精准编辑
- 只动必须动的，不碰相邻代码、不顺手重构
- 匹配已有风格，哪怕你觉得自己的写法更好
- 看到废代码 → 提一句，不要直接删
- 自己改出的 orphans 自己清理

### 4. 目标驱动
- 任务 = 可验证目标 + 编号步骤 + 每步验证条件
- 标准越清晰，独立跑得越远

---

## 设计决策（不可违背）
- ❌ 不做 AI 校对 / LLM 润色
- ❌ 不引入新 AI 模型、不联网
- ✅ SenseVoice + text_cleaner 规则后处理 = 零延迟
- ✅ 粘贴兜底 = 永不丢字
- ✅ VAD 仅在 Push-to-Talk 模式生效

## 当前状态（2026-05-23）
- ✅ 核心管道跑通
- ✅ text_cleaner.py
- ✅ VAD 自动停
- ✅ 系统托盘
- ✅ start.bat 闪退修复
- 🔧 快捷键被输入法抢占（搜狗/微信 IME 在内核层拦截，keyboard 库 suppress 无效，Cloud Code 处理中）
- ⬜ PyInstaller 打包

## Hermes 最近改动
- audio_capture.py：+VAD 能量检测、check_silence()
- overlay_webview.py：+系统托盘、_setup_tray() 用代码画图标
- main.py：+VAD 自动停逻辑、_finalize_recording()、托盘联动、text_cleaner 管道
- text_cleaner.py：新建，100+ 修正映射
- output_handler.py：+粘贴兜底（存剪贴板+历史文件）
- config.yaml：快捷键改为 ctrl_r / ctrl+shift+win，新增 VAD 参数
- README.md：全部重写
- transcriber.py：删除死代码（SenseVoice 不支持 hotwords_file）
- 删除：hotword_loader 不再 import（text_cleaner 替代）
- 删除：models/_hotwords_cache.txt（死文件）
