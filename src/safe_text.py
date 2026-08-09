"""Model-agnostic text safety boundary."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class SafeTextResult:
    text: str
    changed: bool
    rejected: bool
    reasons: tuple[str, ...]


class SafeTextBoundary:
    MODEL_TOKEN = re.compile(r"<\|[^|<>]{1,80}\|>")
    REPEATED_CHAR = re.compile(r"(.)\1{31,}", re.DOTALL)
    REPEATED_PHRASE = re.compile(r"(.{2,24})\1{7,}", re.DOTALL)

    def sanitize(self, raw_text: str) -> SafeTextResult:
        original = str(raw_text or "")
        reasons: list[str] = []
        text, token_count = self.MODEL_TOKEN.subn("", original)
        if token_count:
            reasons.append("model_control_token")

        cleaned: list[str] = []
        saw_control = False
        saw_private = False
        for char in text:
            category = unicodedata.category(char)
            if category == "Co":
                saw_private = True
                continue
            if category in {"Cc", "Cf", "Cs"} and char not in {"\n", "\t"}:
                saw_control = True
                continue
            cleaned.append(char)
        if saw_control:
            reasons.append("unicode_control")
        if saw_private:
            reasons.append("private_use")

        text = "".join(cleaned)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text).strip()
        if self.REPEATED_CHAR.search(text) or self.REPEATED_PHRASE.search(text):
            reasons.append("pathological_repetition")
            return SafeTextResult("", True, True, tuple(reasons))
        return SafeTextResult(
            text=text,
            changed=text != original,
            rejected=False,
            reasons=tuple(reasons),
        )
