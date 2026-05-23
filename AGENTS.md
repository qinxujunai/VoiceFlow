# AGENTS.md — VoiceFlow

## 这是什么

本地语音转文字工具。按 F2 开始说话，再按 F2 停止，文字粘贴到光标位置。完全离线、免费、开源。

## 运行

```bash
双击 start.bat
# 或
venv\Scripts\python.exe src\main.py
```

## 快捷键

| 按键 | 功能 |
|------|------|
| F2 | 开始录音 / 停止录音并粘贴 |
| Esc | 取消录音 |

## 技术栈

- Python 3.14（Windows）
- Sherpa-ONNX + SenseVoice-Small（ASR，234M 参数，RTF ~0.03）
- sounddevice（麦克风采集）
- keyboard（全局热键，suppress=True 拦截）
- pyperclip + pyautogui（剪贴板粘贴 + 兜底存本地历史）
- PyQt6 + QWebEngineView + HTML/CSS（悬浮胶囊窗 + 系统托盘）
- config.yaml（所有行为配置）

## 文件结构

```
VoiceFlow/
├── src/
│   ├── main.py            # 入口、管道编排（F2 切换 → ASR → 清理 → 粘贴）
│   ├── audio_capture.py   # 麦克风采集 + 能量 VAD（未启用）
│   ├── transcriber.py     # Sherpa-ONNX ASR（SenseVoice）
│   ├── text_cleaner.py    # 文本后处理（口头禅/错字修正/中英空格）
│   ├── output_handler.py  # 文字注入（剪贴板+粘贴+兜底）
│   ├── hotkey_manager.py  # F2 切换 + Esc 取消
│   ├── overlay_webview.py # PyQt6 悬浮窗 + 系统托盘
│   └── overlay.html       # 胶囊 UI（波形动画/流式文字）
├── knowledge-base/        # 热词修正词表（260+ AI 术语）
├── models/sensevoice/     # SenseVoice-Small ONNX 模型（不入库）
├── scripts/               # download_models.py / test_mic.py
├── config.yaml            # 配置文件
├── start.bat              # 一键启动
├── AGENTS.md              # 本文件
└── README.md              # 产品文档
```

## 已实现（v0.1）

- ✅ F2 切换录音（按一下开始，再按一下停止）
- ✅ ASR 转写（SenseVoice，中文 CER ~3%）
- ✅ 后台流式转写（录音期间持续识别，停止时结果已就绪）
- ✅ 流式文字显示（胶囊窗实时展示识别内容）
- ✅ 文本后处理（去口头禅、中英文空格、100+ 音近词修正）
- ✅ 剪贴板粘贴 + 兜底机制（失败时存剪贴板 + 本地历史）
- ✅ 系统托盘（最小化到托盘，录音时弹出胶囊）
- ✅ 苹果风格胶囊 UI（波形动画 + 辉光 + 流式文字）
- ✅ 一键启动（start.bat 自动创建 venv + 安装依赖）
- ✅ 测试模式（python src/main.py --test）

## 设计决策（不可违背）

- ❌ 不做 AI 校对 / LLM 润色
- ❌ 不引入新 AI 模型、不联网
- ❌ 不对输入法做软件层面的热键抢夺（block_key 方案已放弃，风险太高）
- ✅ text_cleaner 规则后处理（零延迟、零依赖）
- ✅ 粘贴兜底（永不丢字）
- ✅ F2 是唯一录音键（不搞多模式）

## 待做（v0.2+）

- [ ] 录音历史记录
- [ ] 运行时动态添加修正词（快捷键 → 弹窗 → 写入 knowledge-base）
- [ ] PyInstaller 打包（VoiceFlow.spec 已存在，待测试）
- [ ] 模型下载脚本测试（scripts/download_models.py）
- [ ] 多语言切换
- [ ] 安装包/发布流程

## 已知问题

- 快捷键可能跟某些应用冲突（F2 在 Excel 里是编辑单元格，在 IDE 里是重命名）。如果需要换键，改 config.yaml 的 `hotkeys.push_to_talk`，只改那里就行。
- Chinese IME（搜狗/微信）会抢右 Ctrl、Ctrl+Shift+Win 等组合键。F2 不冲突。
- PyQt6 WebView 首次加载需要 1-2 秒初始化。

## 编程准则 — Karpathy 四原则

### 1. 先思考再编码
- 动代码前说出假设。不确定就问，不要猜
- 有更简单做法 → 说出来

### 2. 简约至上
- 没要求的不写。只用一次的代码不建抽象层
- 200 行能缩到 50 行就缩

### 3. 精准编辑
- 只动必须动的，不碰相邻代码、不顺手重构
- 匹配已有风格
- 看到废代码 → 提一句，不要直接删

### 4. 目标驱动
- 任务 = 可验证目标 + 编号步骤 + 每步验证条件
