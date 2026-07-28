import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_streaming_metrics_use_speech_onset_and_include_queue_delay():
    from evaluate_streaming_preview import evaluate_pcm
    from streaming_transcriber import PreviewEvent

    class Session:
        committed_text = ""

    class FakePreview:
        def __init__(self):
            self.events = iter(
                (
                    PreviewEvent("", "", 0, 800),
                    PreviewEvent("你好", "你好", 0, 1600),
                    PreviewEvent("你好世界", "世界", 0, 2400),
                )
            )

        def create_session(self):
            return Session()

        def accept_pcm(self, session, _pcm, _sample_rate):
            event = next(self.events)
            session.committed_text += event.delta
            return event

    pcm = np.concatenate(
        (
            np.zeros(800, dtype=np.int16),
            np.full(1600, 5000, dtype=np.int16),
        )
    )
    result = evaluate_pcm(
        FakePreview(),
        pcm,
        16000,
        chunk_ms=50,
        append_interval_ms=80,
    )

    assert result["speech_onset_ms"] == 50.0
    assert result["first_delta_ms"] == 50.0
    assert result["max_chunk_chars"] == 2
    assert result["queue_delay_p95_ms"] > 0
    assert result["committed_text"] == "你好世界"


def test_streaming_metrics_count_the_first_provisional_hypothesis_as_visible_text():
    from evaluate_streaming_preview import evaluate_pcm
    from streaming_transcriber import PreviewEvent

    class Session:
        committed_text = ""

    class FakePreview:
        def __init__(self):
            self.events = iter(
                (
                    PreviewEvent(
                        "你",
                        "",
                        0,
                        800,
                        committed_text="",
                        provisional_text="你",
                    ),
                    PreviewEvent(
                        "你好",
                        "你",
                        0,
                        1600,
                        committed_text="你",
                        provisional_text="好",
                    ),
                    PreviewEvent(
                        "你好",
                        "好",
                        0,
                        2400,
                        committed_text="你好",
                        provisional_text="",
                    ),
                )
            )

        def create_session(self):
            return Session()

        def accept_pcm(self, session, _pcm, _sample_rate):
            event = next(self.events)
            session.committed_text = event.committed_text
            return event

    pcm = np.concatenate(
        (
            np.zeros(800, dtype=np.int16),
            np.full(1600, 5000, dtype=np.int16),
        )
    )
    result = evaluate_pcm(
        FakePreview(),
        pcm,
        16000,
        chunk_ms=50,
        append_interval_ms=80,
    )

    assert result["first_delta_ms"] == 0.0
    assert result["max_chunk_chars"] == 1
    assert result["preview_text"] == "你好"
