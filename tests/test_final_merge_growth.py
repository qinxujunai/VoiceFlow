"""Overlap matching needs only its bounded boundary, not earlier dictation."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from main import VoiceInputSystem


def original_merge(left, right):
    left, right = (left or "").rstrip(), (right or "").lstrip()
    if not left:
        return right
    if not right:
        return left
    for size in range(min(len(left), len(right), 80), 1, -1):
        if left[-size:] == right[:size]:
            return left + right[size:]

    def normalized(value):
        chars, ends = [], []
        for index, char in enumerate(value):
            if char.isalnum() or "\u3400" <= char <= "\u9fff":
                chars.append(char.casefold())
                ends.append(index + 1)
        return chars, ends

    left_chars, _ = normalized(left)
    right_chars, ends = normalized(right)
    for size in range(min(len(left_chars), len(right_chars), 80), 1, -1):
        if left_chars[-size:] == right_chars[:size]:
            return left + right[ends[size - 1]:]
    return f"{left} {right}"


def test_long_merge_does_not_scan_previous_nonboundary_text():
    scanned = []

    class ObservedText(str):
        def rstrip(self, *args):
            return type(self)(super().rstrip(*args))

        def __iter__(self):
            for character in super().__iter__():
                scanned.append(1)
                yield character

        def __getitem__(self, index):
            if isinstance(index, int):
                scanned.append(1)
            return super().__getitem__(index)

    left = ObservedText("以前的内容" * 20000 + "上一段结尾")
    right = "下一段内容" * 20
    system = object.__new__(VoiceInputSystem)
    assert system._merge_transcript_pair(left, right) == f"{left} {right}"
    assert len(scanned) < 1000, "normalization re-read the full preceding dictation"


def test_boundary_optimization_preserves_existing_overlap_semantics():
    system = object.__new__(VoiceInputSystem)
    randomizer = random.Random(261007)
    alphabet = "甲乙丙AbCßİΣ3。，!? 🙂👩‍💻\n\t"
    pairs = [
        ("首段。甲，乙", "甲乙：后续"),
        ("甲" + "。" * 2000 + "乙丙", "乙，丙后续"),
        ("甲ßİ", "ßİ。尾部"), ("", ""), ("前文", ""), ("", "后文"),
    ]
    for _ in range(500):
        left = "".join(randomizer.choices(alphabet, k=randomizer.randint(1, 400)))
        boundary = "".join(randomizer.choices(alphabet, k=randomizer.randint(0, 100)))
        right = "".join(randomizer.choices(alphabet, k=randomizer.randint(0, 200)))
        pairs.append((left + boundary, boundary + right))
    for left, right in pairs:
        assert system._merge_transcript_pair(left, right) == original_merge(left, right)
