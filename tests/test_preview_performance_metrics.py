import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_preview_speech_onset_is_measured_from_pcm_not_hotkey(monkeypatch):
    import main
    from main import VoiceInputSystem
    from streaming_transcriber import PreviewEvent

    class FakeAudio:
        sample_rate = 16000
        sample_count = 4000

    class FakePreview:
        def accept_pcm(self, session, pcm, sample_rate):
            session.committed_text = "字"
            return PreviewEvent(
                text="字",
                delta="字",
                segment_id=0,
                audio_end_sample=len(pcm),
            )

    system = object.__new__(VoiceInputSystem)
    system.audio = FakeAudio()
    system._stream_generation = 3
    system._latest_text = ""
    system._preview_started_at = 100.0
    system._speech_onset_sample = None
    system._speech_onset_at = None
    system._preview_first_model_delta_ms = None
    system._preview_first_model_delta_at = None
    system._preview_first_paint_ms = None
    system._preview_first_text_ms = None
    system._preview_queue_delay_ms = None
    system._preview_last_delta_at = None
    system._preview_update_gap_ms = None
    system._preview_update_count = 0
    system._preview_max_chunk_chars = 0
    system._preview_divergence_count = 0
    system._preview_render_state = ("", "")
    silence = np.zeros(1600, dtype=np.int16)
    speech = np.full(2400, 5000, dtype=np.int16)
    system._audio_snapshot = lambda _start, _end: np.concatenate((silence, speech))
    system._update_preview_state = VoiceInputSystem._update_preview_state.__get__(
        system,
        VoiceInputSystem,
    )
    system.overlay = SimpleNamespace(update_streaming=lambda *_args: None)
    monkeypatch.setattr(main.time, "perf_counter", lambda: 100.4)

    VoiceInputSystem._feed_preview_audio(
        system,
        FakePreview(),
        SimpleNamespace(committed_text=""),
        0,
        3,
    )

    assert system._speech_onset_sample == 1600
    assert system._speech_onset_at == 100.1
    assert round(system._preview_first_model_delta_ms) == 300


def test_history_records_preview_pipeline_stages(tmp_path):
    from history_store import HistoryStore

    entry = HistoryStore(tmp_path / "history.jsonl").append(
        preview_speech_onset_sample=1600,
        preview_first_model_delta_ms=320.5,
        preview_first_paint_ms=401.2,
        preview_update_gap_ms=410.0,
        preview_queue_delay_ms=80.7,
        preview_divergence_count=2,
    )

    assert entry["preview_speech_onset_sample"] == 1600
    assert entry["preview_first_model_delta_ms"] == 320.5
    assert entry["preview_first_paint_ms"] == 401.2
    assert entry["preview_queue_delay_ms"] == 80.7
    assert entry["preview_divergence_count"] == 2
