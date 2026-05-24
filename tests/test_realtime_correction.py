import threading
import time
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def test_disabled_correction_returns_original_text():
    from correction_engine import build_correction_engine

    engine = build_correction_engine({"correction": {"provider": "disabled"}})

    assert engine.correct("我正在用科瑟写代码", terms=["Cursor"]) == "我正在用科瑟写代码"


def test_timeout_returns_original_text():
    from correction_engine import CorrectionRequest, correct_with_timeout

    class SlowEngine:
        def correct(self, request):
            time.sleep(0.2)
            return "Cursor"

    request = CorrectionRequest(text="科瑟", stable_text="", terms=[])

    assert correct_with_timeout(SlowEngine(), request, timeout=0.01) == "科瑟"


def test_ollama_payload_disables_thinking_and_limits_output():
    from correction_engine import OllamaCorrectionEngine, CorrectionRequest

    engine = OllamaCorrectionEngine(
        model="qwen3.5:4b",
        url="http://localhost:11434",
        timeout=2.0,
        num_predict=80,
    )

    payload = engine._build_payload(
        CorrectionRequest(text="我正在用科瑟调试fast api", stable_text="", terms=["Cursor", "FastAPI"])
    )

    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_predict"] <= 120
    assert "只输出校对后的原句" in payload["messages"][0]["content"]


def test_scheduler_discards_stale_generation_result():
    from realtime_correction import RealtimeCorrectionScheduler

    class Engine:
        def __init__(self):
            self.release = threading.Event()

        def correct(self, request):
            self.release.wait(timeout=1)
            return request.text + "-corrected"

    results = []
    engine = Engine()
    scheduler = RealtimeCorrectionScheduler(engine, min_interval_seconds=0)

    scheduler.request_correction("旧文本", generation=1, on_result=lambda text, gen: results.append((gen, text)))
    scheduler.invalidate(generation=2)
    engine.release.set()
    scheduler.wait(timeout=1)

    assert results == []


def test_scheduler_rate_limits_continuous_streaming_requests():
    from realtime_correction import RealtimeCorrectionScheduler

    class Clock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            return self.now

    class Engine:
        def __init__(self):
            self.calls = []

        def correct(self, request):
            self.calls.append(request.text)
            return request.text

    clock = Clock()
    engine = Engine()
    scheduler = RealtimeCorrectionScheduler(engine, min_interval_seconds=1.0, clock=clock, run_async=False)

    scheduler.request_correction("第一段", generation=1, on_result=lambda text, gen: None)
    clock.now = 0.2
    scheduler.request_correction("第二段", generation=1, on_result=lambda text, gen: None)
    clock.now = 1.1
    scheduler.request_correction("第三段", generation=1, on_result=lambda text, gen: None)

    assert engine.calls == ["第一段", "第三段"]
