"""Dictionary terms correct what the recognizer split or misheard (2026-11-03)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _cleaner(tmp_path, terms):
    from text_cleaner import TextCleaner

    knowledge = tmp_path / "knowledge-base"
    knowledge.mkdir()
    (knowledge / "builtin-ai.txt").write_text("\n".join(terms) + "\n", encoding="utf-8")
    config = {"cleaner": {"fix_mistakes": True, "auto_space_en": True},
              "hotwords": {"files": ["builtin-ai.txt"]}}
    return TextCleaner(config, base_dir=tmp_path)


TERMS = ["OpenAI", "Claude Code", "DeepSeek", "ChatGPT", "Cursor", "GitHub", "Transformer"]


@pytest.mark.parametrize("spoken,expected", [
    ("我在用open AI的接口", "我在用 OpenAI 的接口"),
    ("deep seek很便宜", "DeepSeek 很便宜"),
    ("比如cloud code和chat gpt", "比如 Claude Code 和 ChatGPT"),
    ("推到git hub上", "推到 GitHub 上"),
    ("这是transformer架构", "这是 Transformer 架构"),
])
def test_split_or_misheard_dictionary_terms_are_restored(tmp_path, spoken, expected):
    assert _cleaner(tmp_path, TERMS).clean(spoken) == expected


@pytest.mark.parametrize("spoken", [
    "the cloud is white",
    "open the door and close it",
    "a precursor of the idea",
    "we cloud the code",
    "cloudy code reviews",
    "I could code that in an hour",
    "we could code it in Python",
    "cold code paths are slow",
    "the cloud kid",
])
def test_ordinary_words_are_left_alone(tmp_path, spoken):
    assert _cleaner(tmp_path, TERMS).clean(spoken) == spoken


def test_sound_alike_words_need_five_letters_and_a_close_spelling(tmp_path):
    cleaner = _cleaner(tmp_path, TERMS + ["Big Data"])
    assert cleaner.clean("we need more bug data") == "we need more bug data"
    assert cleaner.clean("claud code is fast") == "Claude Code is fast"


@pytest.mark.parametrize("spoken", ["could\ncode", "Claude\nCode", "cloud\ncode", "open\nAI"])
def test_terms_are_never_joined_across_a_line_break(tmp_path, spoken):
    assert _cleaner(tmp_path, TERMS).clean(spoken) == spoken


def test_builtin_hugging_face_keeps_its_official_spacing():
    from text_cleaner import TextCleaner

    terms = (ROOT / "knowledge-base" / "builtin-ai.txt").read_text(encoding="utf-8").splitlines()
    assert "Hugging Face" in terms and "HuggingFace" not in terms
    cleaner = TextCleaner({"cleaner": {"fix_mistakes": True, "auto_space_en": True},
                           "hotwords": {"files": ["builtin-ai.txt"]}}, base_dir=ROOT)
    assert cleaner.clean("I uploaded it to Hugging Face") == "I uploaded it to Hugging Face"
    assert cleaner.clean("模型在huggingface上") == "模型在 Hugging Face 上"
