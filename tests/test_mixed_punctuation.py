"""Mixed Chinese-English dictation: pause-cut seams must not leave full stops inside a sentence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_chinese_punctuation_is_rebuilt_inside_a_paragraph_that_also_holds_english():
    from punctuation import FinalPunctuationRestorer

    source = "时间的。话呢，我也不放在说是最后这个15分钟。And you have to know."
    # CT-Transformer rebuilds the Chinese stops but also lowercases and re-punctuates the English.
    candidate = "时间的话呢，我也不放在说是最后这个15分钟。and you have to know。"

    restored = FinalPunctuationRestorer(lambda _text: candidate).restore(source)

    assert restored == "时间的话呢，我也不放在说是最后这个15分钟。And you have to know."


def test_english_keeps_the_recognizers_punctuation_and_case():
    from punctuation import FinalPunctuationRestorer

    source = "Go home. The end"
    assert FinalPunctuationRestorer(lambda _text: "go home, the end.").restore(source) == source


@pytest.mark.parametrize("source,candidate", [
    ("你好 low-cost 方案", "你好low - cost方案。"),
    ("我在 go nowhere 说", "我在go now here说。"),
    ("今天天气很好。Yes", "今天天气不好。yes"),
])
def test_mixed_merge_still_rejects_any_word_change(source, candidate):
    from punctuation import FinalPunctuationRestorer

    assert FinalPunctuationRestorer(lambda _text: candidate).restore(source) == source


def _system():
    import main as vf

    return object.__new__(vf.VoiceInputSystem)


def test_a_seam_full_stop_before_a_lowercase_word_is_dropped():
    joined = _system()._join_transcript_parts(
        ["So you have to put your attention into.", "the really important things", "but. you have to care"],
        after_pause=[False, True, True],
    )

    assert joined == "So you have to put your attention into the really important things but. you have to care"


@pytest.mark.parametrize("left,right,expected", [
    ("So you have to put your attention into.", "Into the really important things",
     "So you have to put your attention into the really important things"),
    ("It's so important, but.", "but you have to know nobody cares",
     "It's so important, but you have to know nobody cares"),
    ("我觉得这个。", "这个方案可以", "我觉得这个方案可以"),
])
def test_an_overlap_seam_takes_the_punctuation_the_next_piece_heard(left, right, expected):
    assert _system()._merge_transcript_pair(left, right) == expected


@pytest.mark.parametrize("left,right", [
    ("We bought apples, pears, etc.", "and then left"),
    ("时间的。", "话呢"),
    ("I will speak English.", "I will"),
])
def test_seam_stops_that_may_be_real_are_kept(left, right):
    joined = _system()._join_transcript_parts([left, right], after_pause=[False, True])

    assert joined.startswith(left.rstrip())
