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
        self.base_dir = base_dir

        self.auto_space_en = cfg.get("auto_space_en", True)
        self.fix_mistakes = cfg.get("fix_mistakes", True)
        self.basic_punctuation = cfg.get("basic_punctuation", cfg.get("basic_punctuation", False))

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
        self.term_normalizations = self._build_term_normalizations()
        self._corrections_signature = self._correction_files_signature()

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
        """Apply only the correction pairs visible in the managed dictionary."""
        return dict(self.vocabulary.corrections) if self.vocabulary else {}

    def _correction_files_signature(self):
        if not self.vocabulary:
            return None
        signature = []
        for filename in self.vocabulary.files:
            path = self.vocabulary.directory / filename
            if path.exists():
                stat = path.stat()
                signature.append((str(path), stat.st_mtime_ns, stat.st_size))
            else:
                signature.append((str(path), None, None))
        return tuple(signature)

    def _build_term_normalizations(self):
        """Build safe, token-boundary spelling normalization for ASCII terms."""
        if not self.vocabulary:
            return []
        terms = []
        for term in self.vocabulary.terms:
            if not term.isascii() or not any(char.isalpha() for char in term):
                continue
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
            terms.append((term, pattern))
        return sorted(terms, key=lambda item: len(item[0]), reverse=True)

    def _reload_corrections_if_changed(self):
        if not self.vocabulary:
            return
        signature = self._correction_files_signature()
        if signature == self._corrections_signature:
            return
        self.vocabulary.reload()
        self.corrections = self._build_corrections(self.base_dir)
        self.term_normalizations = self._build_term_normalizations()
        self._corrections_signature = signature

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
        self._corrections_signature = self._correction_files_signature()

    # ================================================================
    # 主清理流程
    # ================================================================

    def clean(self, text: str, *, preserve_format=False) -> str:
        """清理 ASR 输出文本。返回清理后的文本。"""
        if not text or not text.strip():
            return text
        if preserve_format:
            return text

        text = text.strip()

        if self.fix_mistakes:
            self._reload_corrections_if_changed()
            text = self._fix_mistakes(text)
        if self.auto_space_en:
            text = self._add_cjk_en_space(text)
        if self.basic_punctuation:
            text = self._add_punctuation(text)

        # 清理多余空格和标点
        text = re.sub(r" {2,}", " ", text)
        # 去除非打印字符
        text = self._ctrl_re.sub("", text)

        stripped = text.strip()
        if not stripped:
            return ""
        return stripped


    def _add_cjk_en_space(self, text: str) -> str:
        return self.cjk_en_boundary.sub(" ", text)

    def _fix_mistakes(self, text: str) -> str:
        for wrong, correct in sorted(self.corrections.items(), key=lambda item: len(item[0]), reverse=True):
            if not wrong or wrong not in text:
                continue
            if len(wrong) == 1:
                if text == wrong:
                    text = correct
                continue
            if wrong.isascii() and any(char.isalnum() for char in wrong):
                pattern = re.compile(
                    rf"(?<![A-Za-z0-9_.]){re.escape(wrong)}(?![A-Za-z0-9_.])"
                )
                text = pattern.sub(lambda _match: correct, text)
                continue
            text = text.replace(wrong, correct)
        for term, pattern in self.term_normalizations:
            text = pattern.sub(lambda _match, value=term: value, text)
        return text

    def _add_punctuation(self, text: str) -> str:
        for pattern, replacement in self._compiled_punct:
            text = pattern.sub(replacement, text)
        return text
