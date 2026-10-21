import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def punctuation_ready(commands, responses, _model):
    responses.put({"kind": "ready"})
    while True:
        command = commands.get()
        if command["kind"] == "shutdown":
            return
        responses.put({"kind": "result", "text": "有时候，我觉得停顿带来了很多句号。"})


def punctuation_hang(commands, responses, _model):
    responses.put({"kind": "ready"})
    commands.get()
    time.sleep(20)


def punctuation_unavailable(_commands, responses, _model):
    responses.put({"kind": "unavailable"})


def test_worker_is_separate_and_preserves_complete_text():
    from punctuation_worker import SupervisedPunctuation
    from punctuation import FinalPunctuationRestorer
    worker = SupervisedPunctuation("unused", worker_target=punctuation_ready)
    try:
        assert worker.load()
        restorer = FinalPunctuationRestorer(worker.restore)
        assert restorer.restore("有时候。我觉得。停顿。带来了很多。句号。") == "有时候，我觉得停顿带来了很多句号。"
        assert worker._process.pid != __import__("os").getpid()
        assert restorer.restore("x = 2") == "x = 2"
        assert restorer.restore("how are you") == "how are you"
        assert restorer.restore("  原文\n", preserve_format=True) == "  原文\n"
    finally:
        worker.shutdown()
    assert worker._process is None


def test_hung_worker_falls_back_and_cannot_leak_late_result():
    from punctuation_worker import SupervisedPunctuation
    worker = SupervisedPunctuation("unused", worker_target=punctuation_hang, timeout=.05)
    assert worker.load()
    started = time.monotonic()
    assert worker.restore("完整原文") == "完整原文"
    assert time.monotonic() - started < 1.5
    assert worker._process is None
    assert worker.restore("下一段原文") == "下一段原文"
    worker.shutdown()


def test_missing_or_corrupt_model_is_optional():
    from punctuation_worker import SupervisedPunctuation
    worker = SupervisedPunctuation("missing")
    assert not worker.load()
    assert worker.restore("不要丢失") == "不要丢失"
    worker.shutdown()


@pytest.mark.parametrize("source,candidate", [
    ("don't change this", "dont change this."),
    ("他说‘保持原文’", "他说保持原文。"),
    ("low-cost 方案", "low cost方案。"),
    ("low-cost 方案", "low - cost方案。"),
    ("go nowhere", "go now here."),
    ("今天天气很好", "今天天气不好。"),
])
def test_guard_rejects_lexical_punctuation_or_word_changes(source, candidate):
    from punctuation import FinalPunctuationRestorer
    assert FinalPunctuationRestorer(lambda _text: candidate).restore(source) == source
