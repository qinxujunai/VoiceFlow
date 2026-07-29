"""Fail-safe final-only punctuation."""

from __future__ import annotations

import re
import unicodedata


_SPACE_RE = re.compile(r"\s+")


def lexical_skeleton(text: str) -> str:
    return "".join(
        character
        for character in _SPACE_RE.sub("", str(text or ""))
        if not unicodedata.category(character).startswith("P")
    )


class FinalPunctuationRestorer:
    """Accept punctuation only when every lexical character is preserved."""

    def __init__(self, backend=None):
        self.backend = backend

    def restore(self, text: str) -> str:
        source = str(text or "").strip()
        if not source or self.backend is None:
            return source
        try:
            candidate = str(self.backend(source) or "").strip()
        except Exception:
            return source
        if lexical_skeleton(candidate) != lexical_skeleton(source):
            return source
        return candidate or source
