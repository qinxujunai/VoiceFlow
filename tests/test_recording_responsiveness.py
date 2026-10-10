"""Slow optional services must not delay the recording feedback or lifecycle."""

from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import numpy as np

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_preview_session_start_does_not_block_recording_or_feed_after_cancel():
    from main import VoiceInputSystem

    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    feeds = []

    class SlowPreview:
        def create_session(self):
            entered.set()
            assert release.wait(2.0)
            return object()

        def close_session(self, _session):
            closed.set()

    system = object.__new__(VoiceInputSystem)
    system.preview_transcriber = SlowPreview()
    system._stream_generation = 1
    system._final_cache_state_lock = threading.Lock()
    system._audio_sample_count = lambda: 0
    system._snapshot_final_cache = lambda: ([], 0)
    system._next_final_segment_range = lambda *_: None
    system._feed_preview_audio = lambda *_: feeds.append(True)
    # Start in another thread so the old synchronous implementation can be
    # released after the assertion without leaving the test hung.
    starter = threading.Thread(target=lambda: system._start_streaming(1))
    started = time.perf_counter()
    starter.start()
    assert entered.wait(1.0)
    try:
        starter.join(0.15)
        assert not starter.is_alive(), "recording waited for optional preview IPC"
        assert time.perf_counter() - started < 0.5
        preview_thread = system._stream_thread
        system._stop_streaming()
    finally:
        release.set()
        starter.join(2.0)
        if system._stream_stop_event is not None:
            system._stop_streaming()
    assert closed.wait(1.0)
    preview_thread.join(1.0)
    assert not feeds


def test_recording_feedback_precedes_slow_focus_inspection():
    from main import VoiceInputSystem
    from recording_state import RecordingStateMachine

    calls = []
    system = object.__new__(VoiceInputSystem)
    system._recording_state = RecordingStateMachine()
    system._stream_generation = 0
    system._recovery_enabled = False
    system._recovery_journal = None
    def capture_target(*, wait=True):
        assert not wait
        calls.append("focus")

    system.output_handler = SimpleNamespace(capture_target=capture_target)
    system.overlay = SimpleNamespace(show_recording=lambda *_: calls.append("feedback"))
    system.session = SimpleNamespace(start=lambda: calls.append("audio"))
    system.controller = SimpleNamespace(mark_recording=lambda: None)
    system._reset_final_cache = lambda: None
    system._start_streaming = lambda *_: None
    system._on_record_start(time.perf_counter())
    assert calls == ["feedback", "focus", "audio"]


def test_preview_catches_up_in_small_pcm_blocks_without_skipping_samples():
    from main import VoiceInputSystem

    pcm = np.arange(16000, dtype=np.int16)
    received = []

    def accept_pcm(_session, block, _rate):
        received.append(block.copy())
        return SimpleNamespace(text="", endpoint_final=False, hypothesis_diverged=False, delta="")

    system = object.__new__(VoiceInputSystem)
    system.audio = SimpleNamespace(sample_rate=16000)
    system._stream_generation = 1
    system._speech_onset_sample = 0
    system._audio_sample_count = lambda: len(pcm)
    system._audio_snapshot = lambda start, end: pcm[start:end]
    preview = SimpleNamespace(accept_pcm=accept_pcm)
    next_sample = 0
    while next_sample < len(pcm):
        next_sample = system._feed_preview_audio(preview, object(), next_sample, 1)
    assert max(map(len, received)) <= 1600
    assert np.concatenate(received).tolist() == pcm.tolist()
