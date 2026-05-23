# Local STT Toolkit — 设计文档

> 本地语音输入基础设施：完全离线、高准确率、支持自定义词表的系统级语音转文字方案
>
> 创建时间：2026-05-23
> 目标硬件：RTX 3060 Laptop (6GB VRAM) + Windows 11 + WSL2

---

## 1. 问题定义

### 1.1 核心痛点（三层）

| 痛点层级 | 具体表现 | 为什么现有方案不行 |
|---|---|---|
| **第一层：输入法卡顿** | 打一半切输入法崩溃、卡死、丢字——心态炸裂 | 语音直出不经过输入法，根治问题 |
| **第二层：国外产品贵 + 中文差** | Wispr Flow $10/月、Speakly 订阅制、Typeless $30/月；对中国文化背景词汇识别拉胯 | SenseVoice 原生中文 + 热词注入，零成本 |
| **第三层：怕丢** | 对着麦克风讲了一大段话，软件崩了，什么都没留下 | 兜底机制：粘贴失败 → 存剪贴板 + 本地历史 |

### 1.2 重新框定问题

这不是一个"语音转文字工具"，而是一个**值得信赖的语音输入基础设施**：

```
错误思路：找模型 → 跑起来 → 加 AI 校对 → 堆功能
    ↓ 问题：越堆越重，显存吃满，延迟上去，还是不可靠

正确思路：把三件最有价值的事做到极致
    听得准（热词注入）→ 出得快（规则清理，0ms延迟）→ 不丢字（兜底机制）
```

核心差异：
- **不做 AI 校对**——那是噱头，用零延迟的规则清理替代
- **不做云**——100% 本地，零联网
- **不怕崩**——兜底机制保证你说的每一个字都不会丢

### 1.3 为什么不引入 AI 校对

| 原因 | 解释 |
|------|------|
| **延迟** | 本地 LLM 校对增加 500ms-1s，云端增加 700ms+。语音输入的核心竞争力是"松手就出字" |
| **显存** | RTX 3060 6GB 本来跑着 Ollama/ComfyUI，再加校对模型直接爆显存 |
| **收益** | 90% 的"润色"需求（去口头禅、补标点、中英文空格）用正则规则 0ms 搞定 |
| **复杂度** | AI 校对需要模型管理、prompt 工程、流式对接、错误回退——维护成本远大于用户感知收益 |
| **竞品验证** | Typeless 的 AI 重写延迟 3-5 秒，用户抱怨最多的是"慢"，不是"不够智能" |

> 总结：AI 校对解决的不是真实痛点。用户要的是"快"和"准"，不是"一段看起来像AI写的文字"。

---

## 2. 2026 开源 ASR 技术全景

### 2.1 HuggingFace Open ASR Leaderboard 当前排名（2026.5）

**英文全球排名：**
| 排名 | 模型 | WER | 参数量 | RTFx | 来源 |
|---|---|---|---|---|---|
| 1 | Cohere Transcribe | 5.42% | 2B | 524.88 | Cohere |
| 2 | Canary-Qwen 2.5B | 5.63% | 2.5B | 418 | NVIDIA |
| 3 | IBM Granite Speech | 5.52% | - | - | IBM |
| 4 | Whisper Large-v3 | 6.41% | 1.5B | - | OpenAI |

**中文排名（CER，越低越好）：**
| 排名 | 模型 | CER | 参数量 | 流式 | 来源 | 发布时间 |
|---|---|---|---|---|---|---|
| 1 | FireRedASR2-LLM | 2.89% | - | ❌ | 小红书 | 2026.3 |
| 2 | SenseVoice-Small | 2.96% | 234M | ❌ | 阿里 FunAudioLLM | 2024.7 |
| 3 | Qwen3-ASR | ~3.5% | 0.6B/1.7B | ✅ | 阿里 Qwen | 2026.1 |
| 4 | FunASR Paraformer | ~4% | 220M | ✅ | 阿里达摩院 | 2023 |

### 2.2 关键项目详解

#### sherpa-onnx — 统一推理框架（★ 核心依赖）

```
GitHub:   https://github.com/k2-fsa/sherpa-onnx
Stars:    5k+（极其活跃）
定位:     跨平台语音推理框架，不是模型，是"跑模型的引擎"
关键能力:
  - 内置 VAD（Silero VAD / FSMN-VAD）
  - 原生 hotwords（热词注入）支持
  - 实时麦克风流式转写
  - 支持 SenseVoice、Paraformer、Qwen3-ASR、Whisper 等多种模型
  - Python / C++ / Java / Swift / Flutter API
  - ONNX Runtime 后端，支持 CPU 和 GPU
安装:     pip install sherpa-onnx
```

#### SenseVoice-Small — 超轻量中文 SOTA（★ 主引擎）

```
GitHub:       https://github.com/FunAudioLLM/SenseVoice
HuggingFace:  https://huggingface.co/FunAudioLLM/SenseVoice
参数量:       234M（0.23B）
显存占用:     <1GB（甚至能跑在树莓派上）
中文 CER:     2.96%（AISHELL-1 测试集）
语言支持:     中/英/日/韩/粤语 + 50种语言
额外能力:     语言识别、情感检测、音频事件检测
导出格式:     ONNX（sherpa-onnx 直接支持）
```

#### Qwen3-ASR — 综合最强（★ 升级引擎）

```
GitHub:       https://github.com/QwenLM/Qwen3-ASR
HuggingFace:  https://huggingface.co/Qwen/Qwen3-ASR-0.6B
              https://huggingface.co/Qwen/Qwen3-ASR-1.7B
PyPI:         pip install qwen-asr
参数量:       0.6B / 1.7B
显存占用:     0.6B: ~2-3GB / 1.7B: ~4-7GB
语言支持:     52种语言和方言
关键能力:
  - prompt 注入：可以用文本上下文引导识别结果（等价于热词）
  - 流式转写：官方提供 Flask streaming demo
  - 歌唱识别：带 BGM 的歌词也能转
  - vLLM 后端：支持批量推理、异步服务
GGUF 格式:    huggingface.co/JamePeng2023/Qwen3-ASR-1.7B-GGUF（可用 llama.cpp 跑）
```

#### FunASR — 阿里达摩院语音工具包

```
GitHub:   https://github.com/modelscope/FunASR
Stars:    10k+
定位:     端到端语音识别工具包
关键能力:
  - Paraformer（中文 ASR，220M 参数）
  - FSMN-VAD（语音活动检测模型，我们用 sherpa-onnx 的版本）
  - 热词注入（hotword）机制的原始实现
  - SenseVoice 的推理后端之一
我们用途: 参考其热词机制设计，VAD 模型可选
```

#### OpenWhispr — 桌面语音输入参考

```
GitHub:   https://github.com/OpenWhispr/openwhispr
Stars:    429+
定位:     桌面语音听写应用，热键→说话→光标出字
平台:     Windows / macOS / Linux
引擎:     Whisper + NVIDIA Parakeet（本地）
交互:     全局热键，文字注入到当前光标
我们用途: 不 fork，只借鉴其交互设计和文字注入方案
```

#### 其他值得关注的项目

| 项目 | GitHub | 说明 |
|---|---|---|
| Maivi | github.com/MaximeRivest/maivi | 跨平台语音输入，Alt+Q 热键，CPU 也能跑 |
| faster-whisper | github.com/SYSTRAN/faster-whisper | Whisper CTranslate2 优化版，4x 速度提升 |
| whisper.cpp | github.com/ggerganov/whisper.cpp | Whisper C++ 实现，极低资源 |
| FireRedASR2 | github.com/FireRedTeam/FireRedASR | 中文 SOTA，但非流式，适合文件转写 |
| Microsoft VibeVoice | github.com/microsoft/VibeVoice | 支持 Customized Hotwords，60分钟长音频 |

---

## 3. 硬件约束分析

### 3.1 设备规格

```
GPU:   NVIDIA RTX 3060 Laptop
VRAM:  6GB GDDR6
CUDA:  13.2（通过 nvidia-smi.exe 确认）
CPU:   AMD Ryzen 7 5800H
RAM:   8GB（系统级，非 GPU）
```

### 3.2 模型-显存映射表

| 模型 | 参数量 | FP16 显存 | INT8 显存 | ONNX 显存 | 6GB 可行性 |
|---|---|---|---|---|---|
| SenseVoice-Small | 234M | ~0.5GB | ~0.3GB | ~0.5GB | ✅ 轻松 |
| Qwen3-ASR 0.6B | 600M | ~1.2GB | ~0.7GB | ~1GB | ✅ 轻松 |
| Qwen3-ASR 1.7B | 1.7B | ~3.4GB | ~2GB | ~3GB | ✅ 可用 |
| Whisper Large-v3 | 1.5B | ~3GB | ~1.5GB | ~2GB | ✅ 可用 |
| FireRedASR2-LLM | 未知 | 未知 | 未知 | 未知 | ⚠️ 待确认 |
| Canary-Qwen 2.5B | 2.5B | ~5GB | ~3GB | ~4GB | ⚠️ 刚好够 |

### 3.3 双引擎策略

```
日常使用：SenseVoice-Small（<1GB 显存，不挤占 ComfyUI/Ollama 资源）
高精度场景：Qwen3-ASR 0.6B（需要更准确时切换，~1GB 显存）
极限场景：Qwen3-ASR 1.7B（关闭其他 GPU 应用后使用，~3GB 显存）
```

通过 config.yaml 中的 `engine` 字段切换，无需改代码。

---

## 4. 架构设计

### 4.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互层                                │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │ 模式A: 长按   │    │ 模式B: 切换   │                           │
│  │ Push-to-Talk │    │    Toggle     │                           │
│  │     F2       │    │ Ctrl+Alt+V   │                           │
│  └──────┬───────┘    └──────┬───────┘                           │
│         └──────────┬────────┘                                   │
│                    ▼                                             │
│         ┌──────────────────┐                                    │
│         │  hotkey_manager  │  pynput 全局快捷键监听               │
│         └────────┬─────────┘                                    │
├──────────────────┼──────────────────────────────────────────────┤
│                  ▼            核心处理层                         │
│  ┌──────────────────────┐                                       │
│  │   audio_capture      │  sounddevice 麦克风采集                │
│  │   (16kHz PCM 流)     │  按住采集 / 松开停止                   │
│  └──────────┬───────────┘                                       │
│             ▼                                                   │
│  ┌──────────────────────┐    ┌──────────────────┐               │
│  │    transcriber       │◄───│  hotword_loader  │              │
│  │  sherpa-onnx ASR     │    │  加载知识库词表    │               │
│  │  + 热词注入          │    │  ai-terms.txt    │               │
│  └──────────┬───────────┘    │  company-terms   │               │
│             │                └──────────────────┘               │
│             ▼                                                   │
│  ┌──────────────────────┐                                       │
│  │   text_cleaner       │  正则规则清理（0ms 延迟）              │
│  │  - 去口头禅           │  纯 Python，零依赖，零模型            │
│  │  - 中英文空格         │                                       │
│  │  - 常见错字修正       │                                       │
│  │  - 基础标点           │                                       │
│  └──────────┬───────────┘                                       │
│             ▼                                                   │
│  ┌──────────────────────┐                                       │
│  │   output_handler     │  pyperclip → 剪贴板 + Ctrl+V          │
│  │  文字→当前光标位置    │  ┌─────────────────────────┐         │
│  │                      │  │ 兜底：粘贴失败 → 存剪贴板 │         │
│  │                      │  │      + 本地历史 + 提示   │         │
│  │                      │  └─────────────────────────┘         │
│  └──────────────────────┘                                       │
├─────────────────────────────────────────────────────────────────┤
│                        模型层                                    │
│  ┌────────────────┐                                             │
│  │ SenseVoice     │  234M 参数，<1GB 显存                       │
│  │ ONNX 格式      │  中英日韩粤 + 情绪检测                      │
│  └────────────────┘                                             │
│  模型路径: models/sensevoice/                                    │
│                                                                  │
│  ⚠️ 不引入 LLM 校对模型 —— 规则清理已覆盖 90% 场景               │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 数据流详解

```
1. 用户按住 F2（或按 Ctrl+Alt+V 开启 Toggle）
       ↓
2. hotkey_manager 捕获事件，通知 audio_capture 开始录音
       ↓
3. audio_capture 以 16kHz 采样率持续采集 PCM 音频流
       ↓
4. transcriber 将音频送入 sherpa-onnx ASR 引擎
   - 注入 hotword_loader 加载的热词列表（源头防错）
   - SenseVoice: 录音结束后一次性转写
       ↓
5. 用户松开按键（或 Toggle 再按一次停止）
       ↓
6. text_cleaner 对转写文字做规则后处理（0ms 延迟）
   - 去口头禅：嗯、啊、那个、就是说、然后然后
   - 中英文空格：用Python开发 → 用 Python 开发
   - 常见错字修正：七点云 → 奇点云
   - 基础标点补充
       ↓
7. output_handler 将清理后的文字注入当前光标位置
   - 正常路径：复制到剪贴板 + 模拟 Ctrl+V 粘贴
   - 兜底路径：粘贴失败 → 文字存剪贴板 + 本地历史
                → 悬浮窗提示 "粘贴失败，已存入剪贴板"
```

### 4.3 交互设计

#### 模式A — Push-to-Talk（精确控制）

```
场景：短句输入、即时回复、不想被打断的思考间隙

操作：
  按住 Ctrl+Alt+Space → 开始录音
  说话...
  松开 → 停止录音 → 文字出现在当前光标

特点：
  - 录音期间可以暂停思考，松手即停
  - 适合碎片化输入
  - 最低延迟
```

#### 模式B — Toggle（长段口述）

```
场景：长段口述、整理思路、会议记录、连续输出

操作：
  按 Ctrl+Alt+V → 开始录音（系统托盘图标变红）
  说话...暂停思考...继续说...暂停...继续...
  再按 Ctrl+Alt+V → 停止录音 → 文字输出

特点：
  - 录音期间可以随意暂停，不会被中断
  - 适合连续输出大段内容
  - 托盘图标显示录音状态
```

#### 快捷键配置

```yaml
# config.yaml
hotkeys:
  push_to_talk: "ctrl+alt+space"    # 模式A
  toggle: "ctrl+alt+v"              # 模式B
  cancel: "ctrl+alt+x"              # 取消本次录音（不输出）
```

---

## 5. AI 术语知识库设计

### 5.1 为什么需要知识库

通用 ASR 模型（Whisper/SenseVoice/Qwen3-ASR）训练数据以日常对话为主，对以下场景容易出错：

| 场景 | 你说了 | 模型可能输出 |
|---|---|---|
| 公司名 | 奇点云 | 七点云 / 气点云 |
| 产品名 | DataSim | data sim / 数据sim |
| 技术词 | embedding | 英bedding / 嵌入 |
| 模型名 | LLaMA | 拉马 / llama |
| 框架名 | LangChain | lang chain / 链链 |
| 人名 | 吴恩达 | 吴恩大 / 恩达 |

通过热词注入，告诉模型"这些词一定会出现，请优先匹配"。

### 5.2 热词机制工作原理

```
sherpa-onnx hotwords API：

1. 准备热词文件（每行一个词，可带权重）：
   奇点云/DataSim
   embedding/1.5
   RAG
   
2. 调用 ASR 时传入热词列表：
   recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
       model="models/sensevoice/model.onnx",
       hotwords_file="knowledge-base/all-terms.txt",
       ...
   )

3. 模型在解码时会偏向匹配热词
```

### 5.3 术语分类体系

```
knowledge-base/
├── ai-terms.txt          ← AI/ML 专业术语（最大，持续扩充）
│   格式示例：
│   RAG
│   embedding
│   fine-tuning/微调
│   transformer
│   LLaMA
│   GPT
│   BERT
│   token
│   prompt
│   agent
│   MCP
│   vector database
│   LangChain
│   LlamaIndex
│   vLLM
│   ONNX
│   LoRA
│   RLHF
│   ...
│
├── company-terms.txt     ← 业务/公司相关
│   格式示例：
│   奇点云
│   DataSim
│   StartDT
│   数据中台
│   智能营销
│   用户画像
│   ...
│
└── user-custom.txt       ← 你自己随时加的临时词
    （用完可以清空）
```

### 5.4 热词文件生成方式

初始版本：手动整理一份 AI 领域高频术语（约 200-500 个词）
后续优化：
- 从你的 Obsidian 笔记（PraxisOS vault）自动提取关键词
- 从你的会议记录/聊天记录中统计高频专业词
- 支持运行时动态添加（说一个词被识别错了，按快捷键加入词表）

---

## 6. 项目文件结构（详细）

```
E:\Files\Projects\local-stt-toolkit\
│
│── DESIGN.md                        本文档。总设计文档。
│                                      定位：项目的"宪法"，所有设计决策记录在此。
│                                      维护：每次架构变更都要更新。
│
│── README.md                        快速上手指南。
│                                      定位：给"未来的自己"或"其他人"看的。
│                                      内容：安装步骤、启动命令、快捷键说明。
│
│── config.yaml                      全局配置文件。
│                                      内容：
│                                        - 当前使用的引擎（sensevoice / qwen3-asr）
│                                        - 模型文件路径
│                                        - 热词文件路径
│                                        - 快捷键绑定
│                                        - 输出模式（光标注入 / 剪贴板）
│                                        - 音频采样率、设备选择
│
│── requirements.txt                 Python 依赖清单。
│                                      包含：sherpa-onnx, sounddevice, pynput, pyautogui, pyperclip, pyyaml
│
│── .gitignore                       Git 忽略规则。
│                                      忽略：models/（太大）、*.wav、__pycache__、.env
│
│── .env.example                     环境变量模板。
│                                      当前无需特殊环境变量，预留扩展。
│
│── models/                          模型文件存放目录。
│   │                                  注意：此目录被 gitignore，不入库。
│   │                                  模型通过 scripts/download_models.py 下载。
│   │
│   ├── sensevoice/                  SenseVoice-Small ONNX 模型
│   │   ├── model.onnx                 来源：huggingface.co/FunAudioLLM/SenseVoice
│   │   ├── tokens.txt                 大小：~500MB
│   │   └── ...
│   │
│   └── qwen3-asr/                   Qwen3-ASR ONNX 模型（Phase 2）
│       ├── model.onnx                 来源：huggingface.co/Qwen/Qwen3-ASR-0.6B
│       ├── tokens.txt                 大小：~1.2GB
│       └── ...
│
│── knowledge-base/                  自定义词表目录。
│   │                                  定位：你的核心资产，越用越准。
│   │
│   ├── ai-terms.txt                 AI/ML 专业术语。
│   │                                    来源：手动整理 + Obsidian 笔记提取。
│   │                                    数量：初始 200-500 词，持续扩充。
│   │
│   ├── company-terms.txt            业务/公司相关术语。
│   │                                    内容：奇点云、DataSim、产品名、客户名等。
│   │
│   └── user-custom.txt              用户自定义临时词。
│                                        用法：遇到识别错误的词，随时加入此文件。
│
│── src/                             核心源码目录。
│   │                                  语言：Python
│   │                                  总代码量估计：~500-800 行
│   │
│   ├── main.py                      入口文件。
│   │                                    职责：加载配置、初始化所有模块、启动事件循环。
│   │                                    启动命令：python src/main.py
│   │
│   ├── audio_capture.py             麦克风采集模块。
│   │                                    依赖：sounddevice
│   │                                    职责：以 16kHz 采样率采集 PCM 音频。
│   │                                    接口：
│   │                                      - start_recording() → 开始采集
│   │                                      - stop_recording() → 停止采集，返回音频数据
│   │                                      - get_audio_stream() → 获取实时音频流
│   │
│   ├── transcriber.py               ASR 转写模块。
│   │                                    依赖：sherpa-onnx
│   │                                    职责：加载模型、注入热词、执行转写。
│   │                                    接口：
│   │                                      - load_engine(engine_name) → 加载指定引擎
│   │                                      - transcribe(audio_data) → 返回转写文字
│   │                                      - set_hotwords(word_list) → 更新热词
│   │                                    支持引擎：
│   │                                      - sensevoice（默认）
│   │                                      - qwen3-asr
│   │
│   ├── hotkey_manager.py            全局快捷键模块。
│   │                                    依赖：pynput
│   │                                    职责：监听全局快捷键，触发录音开始/停止。
│   │                                    接口：
│   │                                      - register_ptt_hotkey(key_combo) → 注册 Push-to-Talk
│   │                                      - register_toggle_hotkey(key_combo) → 注册 Toggle
│   │                                      - register_cancel_hotkey(key_combo) → 注册取消
│   │                                    回调：
│   │                                      - on_record_start()
│   │                                      - on_record_stop()
│   │                                      - on_record_cancel()
│   │
│   ├── text_cleaner.py              文字后处理模块。
│   │                                    依赖：无（纯 Python 正则）
│   │                                    职责：在 ASR 输出后、粘贴前清理文字。
│   │                                    处理项：
│   │                                      - 去口头禅（嗯、啊、那个、就是说、然后然后...）
│   │                                      - 中英文间自动加空格
│   │                                      - 常见音近错字修正（从映射表读取）
│   │                                      - 基础标点补充
│   │                                    接口：
│   │                                      - clean(text) → 清理后的文字
│   │                                      - add_correction(wrong, correct) → 添加错字映射
│   │                                    性能：纯正则匹配，延迟 < 1ms
│   │
│   ├── output_handler.py            文字输出模块。
│   │                                    依赖：pyautogui / pyperclip
│   │                                    职责：将清理后的文字注入到当前活动窗口。
│   │                                    接口：
│   │                                      - output(text) → 粘贴到光标
│   │                                      - get_last_text() → 获取最近一次输出（兜底用）
│   │                                    兜底逻辑：
│   │                                      - 粘贴失败 → 文字存剪贴板 + 写入本地历史
│   │                                      - 悬浮窗提示 "粘贴失败，已存入剪贴板"
│   │                                    策略：
│   │                                      - 默认用剪贴板+粘贴（适用所有应用）
│   │
│   └── hotword_loader.py            热词加载模块。
│                                        依赖：无（纯文件读取）
│                                        职责：读取 knowledge-base/ 下所有词表文件，
│                                              合并为热词列表，传给 transcriber。
│                                        接口：
│                                          - load_all() → 返回合并后的词表
│                                          - add_hotword(word, category) → 运行时添加
│                                          - reload() → 重新加载所有词表
│                                        新增：支持热键触发运行时添加
│                                          Ctrl+Alt+H → 弹出输入框 → 写入 user-custom.txt
│                                        依赖：无（纯文件读取）
│                                        职责：读取 knowledge-base/ 下所有词表文件，
│                                              合并为热词列表，传给 transcriber。
│                                        接口：
│                                          - load_all_hotwords() → 返回合并后的词表
│                                          - add_hotword(word, category) → 运行时添加
│                                          - reload() → 重新加载所有词表
│
│── scripts/                         工具脚本目录。
│   │
│   ├── setup.py                     一键环境搭建。
│   │                                    功能：
│   │                                      1. 创建 Python 虚拟环境
│   │                                      2. 安装 requirements.txt
│   │                                      3. 调用 download_models.py 下载模型
│   │                                      4. 检测 GPU 可用性
│   │                                      5. 测试麦克风
│   │                                    运行：python scripts/setup.py
│   │
│   ├── download_models.py           模型下载脚本。
│   │                                    功能：
│   │                                      1. 从 HuggingFace 下载 SenseVoice-Small ONNX
│   │                                      2. 解压到 models/sensevoice/
│   │                                      3. （可选）下载 Qwen3-ASR ONNX
│   │                                    依赖：huggingface_hub
│   │                                    运行：python scripts/download_models.py [--engine qwen3-asr]
│   │
│   └── test_mic.py                  麦克风测试脚本。
│                                        功能：
│                                          1. 列出所有音频输入设备
│                                          2. 录制 5 秒音频
│                                          3. 播放回放
│                                          4. 用 ASR 转写验证
│                                        运行：python scripts/test_mic.py
│
└── .env.example                     环境变量模板。
                                       当前内容：（预留）
                                       # HF_TOKEN=your_huggingface_token（可选，加速模型下载）
```

---

## 7. 实施路线图

### Phase 0 — 环境验证（预计 1 小时）

```
目标：确认硬件和基础环境可用

步骤：
  1. 在 Windows 侧安装 Python 3.12（已有）
  2. 创建虚拟环境：
     cd E:\Files\Projects\local-stt-toolkit
     python -m venv venv
     venv\Scripts\activate
  3. 安装核心依赖：
     pip install sherpa-onnx sounddevice pynput pyautogui pyperclip pyyaml
  4. 运行 download_models.py 下载 SenseVoice-Small ONNX
  5. 运行 test_mic.py 确认麦克风可用
  6. 用 sherpa-onnx 官方 demo 跑通一次转写

验收标准：
  □ sherpa-onnx 安装成功，import 无报错
  □ 模型文件存在于 models/sensevoice/
  □ 麦克风能采集到音频
  □ 说出"你好世界"能正确转写
```

### Phase 1 — 核心管道（已完成 ✅）

```
目标：热键录音 → 转写 → 文字输出到光标
状态：✓ 已实现
  - audio_capture.py ✓
  - transcriber.py ✓
  - hotkey_manager.py ✓
  - output_handler.py ✓
  - main.py ✓
```

### Phase 2 — 热词知识库（已完成 ✅）

```
目标：专业术语识别准确率提升
状态：✓ 已实现
  - hotword_loader.py ✓
  - knowledge-base/ 三个词表文件 ✓
  - 热词注入到 sherpa-onnx ✓
```

### Phase 3 — 文字清理 + 兜底机制（当前重点 🔥）

```
目标：零延迟文字后处理 + 永远不丢字

步骤：
  1. 实现 text_cleaner.py
     - 去口头禅：正则匹配 (嗯|啊|那个|就是说|然后然后)+
     - 中英文空格：([一-鿿])([a-zA-Z]) → \1 \2
     - 常见错字修正：从映射表读取
     - 基础标点补充
     - 所有逻辑纯正则，零延迟（<1ms）
  
  2. 升级 output_handler.py — 兜底机制
     - 正常粘贴失败时，自动将文字存入系统剪贴板
     - 同时写入本地历史文件（双重保险）
     - 悬浮窗提示 "粘贴失败，已存入剪贴板"
  
  3. 升级 hotword_loader.py — 运行时添加
     - Ctrl+Alt+H → 弹出输入框 → 写入 user-custom.txt
     - 添加后自动 reload 引擎

验收标准：
  □ "嗯那个就是说今天天气很好然后然后" → "今天天气很好"
  □ "我用Python开发AI应用" → "我用 Python 开发 AI 应用"
  □ 粘贴失败时自动存剪贴板，悬浮窗有提示
  □ 按 Ctrl+Alt+H 能动态添加热词
```

### Phase 4 — 打磨（持续）

```
目标：提升日常使用体验

功能清单：
  - [ ] 录音历史记录
  - [ ] 系统托盘图标（显示录音状态：空闲/录音中）
  - [ ] 开机自启
  - [ ] 自定义热词管理界面
  - [ ] 一键安装包
```

### ❌ 不做的事

```
- [✗] AI 校对 / LLM 润色 — 噱头，增加延迟和显存负担
- [✗] 云端处理 — 破坏离线能力
- [✗] 多引擎并行 — SenseVoice 够好了，不增加复杂度
```

---

## 8. 关键指标

| 指标 | 目标值 | 说明 |
|---|---|---|
| RTF（实时因子） | < 0.3 | 转写耗时 < 音频时长的 30%（10 秒音频 < 3 秒转写） |
| 首字延迟 | < 500ms | Push-to-Talk 松手后到第一个字出现的延迟 |
| 中文 CER | < 3% | 字错误率，在标准测试集上 |
| 专业术语准确率 | > 90% | 热词列表中的词，识别正确率 |
| 显存占用 | < 1GB (SenseVoice) | 日常使用不挤占其他 GPU 应用 |
| 内存占用 | < 1GB | Python 进程的 RAM 占用 |

---

## 9. 风险与备选方案

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| SenseVoice ONNX 导出有问题 | 低 | 无法使用 sherpa-onnx | 用 FunASR 直接推理，或用 faster-whisper |
| Qwen3-ASR 6GB 跑不动 | 中 | 无法升级引擎 | 只用 SenseVoice-Small（<1GB） |
| pynput 全局热键在某些应用中失效 | 中 | 热键冲突 | 改用组合键，或用 Windows 注册全局热键 |
| pyautogui 输入中文有编码问题 | 中 | 乱码 | 改用 pyperclip+Ctrl+V 粘贴方式 |
| 麦克风被其他应用占用 | 低 | 无法录音 | 提示用户关闭占用麦克风的应用 |
| WSL 无法访问 Windows 麦克风 | 高 | WSL 内无法录音 | 整个项目在 Windows 侧运行（用 Windows Python） |

### 重要：运行环境决策

```
本项目必须在 Windows 侧运行，原因：
  1. WSL2 无法直接访问 Windows 麦克风硬件
  2. 全局快捷键（pynput）需要 Windows 消息循环
  3. 文字注入（pyautogui）需要 Windows API

Python 环境：Windows 侧的 Python 3.12
项目路径：E:\Files\Projects\local-stt-toolkit\
启动方式：在 Windows Terminal / PowerShell 中运行
```

---

## 10. 参考链接汇总

| 资源 | URL |
|---|---|
| sherpa-onnx | https://github.com/k2-fsa/sherpa-onnx |
| sherpa-onnx 文档 | https://k2-fsa.github.io/sherpa/onnx/ |
| sherpa-onnx hotwords | https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html |
| SenseVoice GitHub | https://github.com/FunAudioLLM/SenseVoice |
| SenseVoice HuggingFace | https://huggingface.co/FunAudioLLM/SenseVoice |
| Qwen3-ASR GitHub | https://github.com/QwenLM/Qwen3-ASR |
| Qwen3-ASR 0.6B | https://huggingface.co/Qwen/Qwen3-ASR-0.6B |
| Qwen3-ASR 1.7B | https://huggingface.co/Qwen/Qwen3-ASR-1.7B |
| Qwen3-ASR vLLM 部署 | https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-ASR.html |
| Qwen3-ASR GGUF | https://huggingface.co/JamePeng2023/Qwen3-ASR-1.7B-GGUF |
| FunASR GitHub | https://github.com/modelscope/FunASR |
| OpenWhispr GitHub | https://github.com/OpenWhispr/openwhispr |
| Maivi GitHub | https://github.com/MaximeRivest/maivi |
| HuggingFace Open ASR Leaderboard | https://huggingface.co/spaces/hf-audio/open_asr_leaderboard |
| FireRedASR2 论文 | https://arxiv.org/html/2603.10420v1 |
| Qwen3-ASR 技术报告 | https://www.researchgate.net/publication/400236592_Qwen3-ASR_Technical_Report |
| ASR 2025-2026 深度对比 | https://ruoqijin.com/blog/asr-deep-dive-2025-2026 |
| Microsoft VibeVoice | https://github.com/microsoft/VibeVoice |

---

## 11. 术语表

| 术语 | 说明 |
|---|---|
| ASR | Automatic Speech Recognition，自动语音识别 |
| STT | Speech-to-Text，语音转文字 |
| CER | Character Error Rate，字错误率（中文用 CER 比 WER 更合理） |
| WER | Word Error Rate，词错误率（英文常用） |
| RTF | Real-Time Factor，实时因子（越小越快，<1 表示比实时快） |
| RTFx | Real-Time Factor 的倒数（越大越快，>1 表示比实时快） |
| VAD | Voice Activity Detection，语音活动检测 |
| ONNX | Open Neural Network Exchange，模型交换格式 |
| Hotwords | 热词/自定义词表，注入 ASR 引导识别 |
| Push-to-Talk | 按住说话，松开停止 |
| Toggle | 按一下开始，再按一下停止 |
