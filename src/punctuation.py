"""Fail-safe final-only punctuation."""

from __future__ import annotations

import re
import unicodedata


_SPACE_RE = re.compile(r"\s+")
_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’_-][A-Za-z0-9]+)*")
SENTENCE_END_CHOICES = (
    ("preserve", "保留识别标点"),
    ("omit_period", "省略最后一个句号"),
    ("complete_period", "补全句末句号"),
)
_TECHNICAL_RE = re.compile(
    r"https?://|www\.|[A-Za-z]:[\\/]|\\\\|(?:^|\s)/\S+|"
    r"\b\w+@\w+\.\w+|\b[vV]?\d+(?:\.\d+)+|"
    r"\b[\w-]+\.[A-Za-z][\w.-]*|[=<>`{}\[\]]|"
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|etc)\.$|(?:\b[A-Za-z]\.){2,}$",
    re.IGNORECASE,
)


def contains_technical_text(text: str) -> bool:
    return bool(_TECHNICAL_RE.search(str(text or "")))


def normalize_dictation_spacing(text: str) -> str:
    """Normalize presentation without guessing or replacing spoken words."""
    source = str(text or "")
    if contains_technical_text(source):
        return source
    candidate = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", "", source)
    candidate = re.sub(r"[ \t]+([，。！？；：、])", r"\1", candidate)
    candidate = re.sub(r"([，。！？；：、])[ \t]+", r"\1", candidate)
    # Three periods may be an intentional ellipsis; collapse only malformed
    # mixed runs or a doubled full stop.
    candidate = re.sub(r"([。！？])[，。、]*[，、][，。、]*", r"\1", candidate)
    candidate = re.sub(r"(?<!。)。。(?!。)", "。", candidate)
    candidate = re.sub(r"([，、；：])[，、；：]+", r"\1", candidate)
    return candidate if lexical_skeleton(candidate) == lexical_skeleton(source) else source


def apply_sentence_end(text: str, mode: str = "preserve", *, preserve_format=False) -> str:
    """Change only a natural sentence's final period; preserve uncertain text."""
    source = str(text or "")
    if preserve_format or mode == "preserve":
        return source
    if mode not in {value for value, _label in SENTENCE_END_CHOICES}:
        raise ValueError("invalid sentence end policy")
    body = source.rstrip()
    suffix = source[len(body):]
    if (not body or contains_technical_text(body)
            or any(marker in body for marker in ("…", "...", "。。。"))):
        return source
    if mode == "omit_period":
        if body.endswith(("。", ".")) and not body[:-1].endswith(("。", ".")):
            return body[:-1] + suffix
        return source
    if unicodedata.category(body[-1]).startswith("P"):
        return source
    if not any(unicodedata.category(character).startswith("L") for character in body):
        return source
    period = "。" if re.search(r"[\u3400-\u9fff]", body) else "."
    return body + period + suffix


def lexical_skeleton(text: str) -> str:
    return "".join(
        character
        for character in _SPACE_RE.sub("", str(text or ""))
        if character not in "，。！？；：、,.!?;:"
    )


class FinalPunctuationRestorer:
    """Accept punctuation only when every lexical character is preserved."""

    def __init__(self, backend=None):
        self.backend = backend

    def restore(self, text: str, *, preserve_format=False) -> str:
        if preserve_format:
            return str(text or "")
        source = str(text or "").strip()
        if not source or self.backend is None or contains_technical_text(source):
            return source
        try:
            candidate = str(self.backend(source) or "").strip()
        except Exception:
            return source
        if (lexical_skeleton(candidate) != lexical_skeleton(source)
                or _LATIN_WORD_RE.findall(candidate) != _LATIN_WORD_RE.findall(source)):
            return source
        return candidate or source
