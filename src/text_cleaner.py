"""
文本后处理器 — SenseVoice 的热词等价系统
在 ASR 转写之后、粘贴之前运行。零延迟、零依赖，纯 Python 实现。

设计原则：SenseVoice 不支持 transducer 热词，用后处理修正替代。
修正词表从 knowledge-base/ 加载，支持运行时动态添加。
"""

import re
import os

from vocabulary import Vocabulary


class TextCleaner:
    """ASR 输出文本清理器。所有规则通过 config.yaml 控制开关。"""

    def __init__(self, config=None, base_dir=None):
        cfg = config.get("cleaner", {}) if config else {}

        self.remove_fillers = cfg.get("remove_fillers", True)
        self.auto_space_en = cfg.get("auto_space_en", True)
        self.fix_mistakes = cfg.get("fix_mistakes", True)
        self.basic_punctuation = cfg.get("basic_punctuation", cfg.get("basic_punctuation", False))

        # --- 口头禅正则 ---
        self.filler_pattern = re.compile(
            r"\b(?:嗯|啊|额|哦|噢|啧|诶|"
            r"那个|就是说|然后然后|我想说的是|就是|你知道吧|你知道吗|知道吗)\b"
        )
        # "然后" 只去掉连续重复的
        self.then_dedup = re.compile(r"然后(然后)+")

        # --- 中英空格 ---
        self.cjk_en_boundary = re.compile(
            r"(?<=[\u4e00-\u9fff\u3400-\u4dbf])(?=[a-zA-Z0-9])|"
            r"(?<=[a-zA-Z0-9])(?=[\u4e00-\u9fff\u3400-\u4dbf])"
        )

        self.vocabulary = None
        if base_dir:
            hotword_files = config.get("hotwords", {}).get("files") if config else None
            self.vocabulary = Vocabulary(base_dir, files=hotword_files)

        # --- 修正词表：音近词 → 正确形式 ---
        self.corrections = self._build_corrections(base_dir)

        # --- 标点 ---
        self.punctuation_map = [
            (r"(但是|不过|然而|可是|但)(\s*)", r"\1，"),
            (r"(所以|因此|于是|那么)(\s*)", r"\1，"),
            (r"(首先|其次|最后|第一|第二|第三)(\s*)", r"\1，"),
            (r"(另外|此外|还有|而且|并且)(\s*)", r"\1，"),
            (r"(总的来说|总结一下|简单来说)(\s*)", r"\1，"),
            (r"(比如|例如|像)(\s*)", r"\1，"),
        ]
        self._compiled_punct = [(re.compile(p), r) for p, r in self.punctuation_map]
        self._ctrl_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    def _build_corrections(self, base_dir):
        """构建修正词表：内置映射 + knowledge-base 自定义文件"""
        # --- 内置：常见 SenseVoice 音近误识别 ---
        corrections = {
            # 开发工具 / AI 产品
            "科瑟": "Cursor", "扣瑟": "Cursor", "克瑟": "Cursor",
            "coach": "Cursor",
            "云代码": "Cloud Code", "cloud code": "Cloud Code", "cloudcode": "Cloud Code",
            "克劳德": "Claude",
            "开放代码": "OpenCode", "open code": "OpenCode", "opencode": "OpenCode",
            "coach code": "Codex", "扣dex": "Codex", "扣戴克斯": "Codex",
            "且gpt": "ChatGPT", "chat gpt": "ChatGPT",
            "扣派乐特": "Copilot", "copilot": "Copilot",
            "哈斯": "Hermes", "赫密斯": "Hermes",
            "温德瑟夫": "Windsurf",

            # 大模型 / AI
            "deepseek": "DeepSeek", "迪普斯克": "DeepSeek", "迪普西克": "DeepSeek",
            "deep sick": "DeepSeek",
            "拉玛": "LLaMA", "喇嘛": "LLaMA",
            "千问": "Qwen", "q问": "Qwen",
            "秘密欧": "MiMo", "米莫": "MiMo",
            "欧拉玛": "Ollama", "奥拉玛": "Ollama", "ollama": "Ollama",
            "克拉玛": "CLI",
            "hugging face": "HuggingFace", "哈根face": "HuggingFace",
            "兰钦": "LangChain", "lang chain": "LangChain",
            "comfy ui": "ComfyUI", "comfy": "ComfyUI",

            # 编程语言 / 框架
            "拍桑": "Python", "拍森": "Python", "排桑": "Python", "pison": "Python",
            "加瓦": "Java",
            "go浪": "Golang", "狗浪": "Golang",
            "js": "JavaScript",
            "ts": "TypeScript",
            "拉斯特": "Rust",
            "c加加": "C++", "c plus plus": "C++",
            "react": "React",
            "next js": "Next.js", "nex js": "Next.js",
            "fast api": "FastAPI", "fastapi": "FastAPI",
            "docker": "Docker", "多克": "Docker",
            "k8s": "Kubernetes", "k8": "Kubernetes", "库博内特斯": "Kubernetes",
            "酷博": "Kubernetes",
            "吉特": "Git", "git": "Git",
            "吉特哈布": "GitHub", "github": "GitHub", "give hub": "GitHub",

            # 技术概念
            "a p i": "API", "api": "API",
            "rest api": "REST API",
            "软": "RAG", "rag": "RAG",
            "微调": "微调", "fine tuning": "fine-tuning",
            "劳拉": "LoRA", "lora": "LoRA",
            "库达": "CUDA", "cuda": "CUDA",
            "托肯": "token",
            "哈鲁斯内选": "hallucination", "幻觉": "幻觉",
            "语音识别": "ASR", "asr": "ASR",
            "stt": "STT",
            "tts": "TTS",
            "v开头": "vLLM",
            "gp t": "GPT",

            # 口语修正
            "好滴": "好的", "好嘞": "好的",
            "欧克": "OK", "ok": "OK", "okay": "OK",
            "三Q": "谢谢",
            "拜拜": "再见",
            "嗯嗯": "", "啊啊": "",
            "额额": "",

            # 人物 / 账号
            "秦旭俊": "秦徐俊", "秦绪俊": "秦徐俊",

            # 格式修正
            "http": "HTTP", "https": "HTTPS",
            "url": "URL",
            "json": "JSON",
            "csv": "CSV",
            "sql": "SQL",
        }

        if self.vocabulary:
            corrections.update(self.vocabulary.corrections)

        return corrections

    @staticmethod
    def _read_lines(path):
        """读取文件的非注释行"""
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    lines.append(line)
        return lines

    def add_correction(self, wrong: str, correct: str, base_dir=None):
        """运行时添加修正对，持久化到 corrections.txt"""
        self.corrections[wrong.strip()] = correct.strip()
        if self.vocabulary:
            self.vocabulary.add_correction(wrong, correct)
        elif base_dir:
            path = os.path.join(base_dir, "knowledge-base", "corrections.txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{wrong}={correct}\n")

    # ================================================================
    # 主清理流程
    # ================================================================

    def clean(self, text: str) -> str:
        """清理 ASR 输出文本。返回清理后的文本。"""
        if not text or not text.strip():
            return text

        text = text.strip()

        if self.remove_fillers:
            text = self._strip_fillers(text)
        if self.fix_mistakes:
            text = self._fix_mistakes(text)
        if self.auto_space_en:
            text = self._add_cjk_en_space(text)
        if self.basic_punctuation:
            text = self._add_punctuation(text)

        # 清理多余空格和标点
        text = re.sub(r" {2,}", " ", text)
        text = re.sub(r"，{2,}", "，", text)
        text = re.sub(r"。{2,}", "。", text)
        # 去除非打印字符
        text = self._ctrl_re.sub("", text)

        stripped = text.strip()
        if not stripped:
            return ""
        import unicodedata
        meaningful = ''.join(c for c in stripped if not unicodedata.category(c).startswith("P") and not c.isspace())
        if len(meaningful) <= 1:
            return ""
        return stripped


    def clean_streaming(self, text: str) -> str:
        """Clean for streaming display: strip all punctuation for smooth flow."""
        if not text or not text.strip():
            return text
        text = text.strip()
        if self.remove_fillers:
            text = self._strip_fillers(text)
        if self.fix_mistakes:
            text = self._fix_mistakes(text)
        # Strip all punctuation for streaming
        import unicodedata
        text = ''.join(c for c in text if not unicodedata.category(c).startswith('P') and c != '\uff0c' and c != '\u3002' and c != '\uff01' and c != '\uff1f' and c != '\u3001' and c != '\uff1b' and c != '\uff1a' and c != '\u2026' and c != '\u2014' and c != '\u2018' and c != '\u2019' and c != '\u201c' and c != '\u201d')
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _strip_fillers(self, text: str) -> str:
        text = self.filler_pattern.sub("", text)
        text = self.then_dedup.sub("然后", text)
        text = re.sub(r"，,+", "，", text)
        text = re.sub(r"  +", " ", text)
        return text

    def _add_cjk_en_space(self, text: str) -> str:
        return self.cjk_en_boundary.sub(" ", text)

    def _fix_mistakes(self, text: str) -> str:
        for wrong, correct in self.corrections.items():
            if wrong in text:
                text = text.replace(wrong, correct)
        return text

    def _add_punctuation(self, text: str) -> str:
        for pattern, replacement in self._compiled_punct:
            text = pattern.sub(replacement, text)
        return text
