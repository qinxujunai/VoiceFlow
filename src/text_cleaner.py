"""
文本后处理器 — SenseVoice 的热词等价系统
在 ASR 转写之后、粘贴之前运行。零延迟、零依赖，纯 Python 实现。

设计原则：SenseVoice 不支持 transducer 热词，用后处理修正替代。
修正词表从 knowledge-base/ 加载，支持运行时动态添加。
"""

import re
import os

from vocabulary import Vocabulary


_LATIN_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]+(?![A-Za-z0-9_])")


def _sound_key(word: str) -> tuple[str, int]:
    """Consonant skeleton and syllable count: 「cloud」 and 「Claude」 share (kld, 1); 「cloudy」 has 2 syllables."""
    w = word.lower().replace("ph", "f").replace("ck", "k").replace("q", "k").replace("x", "ks")
    w = re.sub(r"c(?=[eiy])", "s", w).replace("c", "k")
    syllables = len(re.findall(r"[aeiouy]+", re.sub(r"e$", "", w)))
    consonants = re.sub(r"(.)\1+", r"\1", w[0] + re.sub(r"[aeiouyhw]", "", w[1:]))
    return consonants, max(1, syllables)


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(min(previous[column] + 1, current[column - 1] + 1,
                               previous[column - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def _sounds_like(spoken: str, written: str) -> bool:
    """「cloud」 for 「Claude」: same consonants and syllables, spelled within two letters.

    Words under five letters must match exactly: could, cold, kid and bug are ordinary
    English that only shares consonants with Claude, Code and Big.
    """
    spoken, written = spoken.lower(), written.lower()
    if spoken == written:
        return True
    return (min(len(spoken), len(written)) >= 5 and _sound_key(spoken) == _sound_key(written)
            and _edit_distance(spoken, written) <= 2)


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
        self.term_sounds = self._build_term_sounds()
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
        """Build safe, token-boundary spelling normalization for ASCII terms.

        A term may also be heard split where its own words or capitals meet:
        「open AI」 -> OpenAI, 「chat gpt」 -> ChatGPT, 「git hub」 -> GitHub.
        A split never spans a line break.
        """
        if not self.vocabulary:
            return []
        terms = []
        for term in self.vocabulary.terms:
            if not term.isascii() or not any(char.isalpha() for char in term):
                continue
            parts = [part for word in re.split(r"[\s-]+", term)
                     for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", word)]
            if len(parts) > 1 and "".join(parts) == re.sub(r"[\s-]", "", term):
                body = r"[ \t-]*".join(re.escape(part) for part in parts)
            else:
                body = re.escape(term)
            pattern = re.compile(
                rf"(?<![A-Za-z0-9_]){body}(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
            terms.append((term, pattern))
        return sorted(terms, key=lambda item: len(item[0]), reverse=True)

    def _build_term_sounds(self):
        """Multi-word ASCII terms whose every word has three or more letters, matched word for word by sound."""
        if not self.vocabulary:
            return []
        sounds = []
        for term in self.vocabulary.terms:
            words = term.split()
            if (len(words) > 1 and term.isascii()
                    and all(word.isalpha() and len(word) >= 3 for word in words)):
                sounds.append((term, words))
        return sounds

    def _restore_misheard_terms(self, text: str) -> str:
        """「cloud code」 -> Claude Code: every word sounds like the term's word (see _sounds_like)."""
        for term, words in self.term_sounds:
            size = len(words)
            tokens = list(_LATIN_TOKEN_RE.finditer(text))
            # Right to left, so a replacement never moves the windows still to be checked.
            for start in range(len(tokens) - size, -1, -1):
                window = tokens[start:start + size]
                gaps = [text[a.end():b.start()] for a, b in zip(window, window[1:])]
                if any(not gap or gap.strip(" \t") for gap in gaps):
                    continue
                if not all(_sounds_like(token.group(), word) for token, word in zip(window, words)):
                    continue
                if text[window[0].start():window[-1].end()] != term:
                    text = text[:window[0].start()] + term + text[window[-1].end():]
        return text

    def _reload_corrections_if_changed(self):
        if not self.vocabulary:
            return
        signature = self._correction_files_signature()
        if signature == self._corrections_signature:
            return
        self.vocabulary.reload()
        self.corrections = self._build_corrections(self.base_dir)
        self.term_normalizations = self._build_term_normalizations()
        self.term_sounds = self._build_term_sounds()
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
        if self.term_sounds:
            text = self._restore_misheard_terms(text)
        return text

    def _add_punctuation(self, text: str) -> str:
        for pattern, replacement in self._compiled_punct:
            text = pattern.sub(replacement, text)
        return text
