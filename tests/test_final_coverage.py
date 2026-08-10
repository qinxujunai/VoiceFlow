from __future__ import annotations

import sys
import threading
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FakeAudio:
    sample_rate = 16000


class LengthTranscriber:
    def __init__(self):
        self.lengths = []

    def transcribe(self, audio, sample_rate):
        self.lengths.append(len(audio))
        return f"text-{len(audio)}"


def _system():
    from main import VoiceInputSystem

    system = object.__new__(VoiceInputSystem)
    system.audio = FakeAudio()
    system.transcriber = LengthTranscriber()
    system._transcribe_lock = threading.Lock()
    system._speech_gate_enabled = False
    system._final_segments = []
    system._finalized_audio_len = 0
    system._final_cache_lock = threading.Lock()
    system._preview_endpoint_lock = threading.Lock()
    system._preview_endpoint_samples = []
    system._final_cache_idle = threading.Event()
    system._final_cache_idle.set()
    system._latest_text = ""
    return system


@pytest.mark.parametrize("seconds", [19, 20, 25, 44, 45])
def test_recordings_up_to_45_seconds_decode_the_complete_frozen_pcm(seconds):
    from main import VoiceInputSystem

    system = _system()
    samples = seconds * FakeAudio.sample_rate
    data = np.ones(samples, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(
        system,
        data,
        buffer_start_sample=0,
        total_samples=samples,
    )

    assert system.transcriber.lengths == [samples]
    assert result.captured_samples == samples
    assert result.covered_samples == samples
    assert result.coverage_ok is True
    assert result.final_source == "full_pcm"


def test_contiguous_long_segments_plus_tail_cover_the_stop_sample():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [
        FinalSegmentCoverage(0, 18 * rate, "first", True),
        FinalSegmentCoverage(17 * rate, 36 * rate, "second", True),
    ]
    system._finalized_audio_len = 36 * rate
    data = np.ones(46 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(
        system,
        data,
        buffer_start_sample=0,
        total_samples=len(data),
    )

    assert system.transcriber.lengths == [11 * rate]
    assert result.covered_samples == len(data)
    assert result.coverage_ok is True
    assert result.final_source == "segments_plus_tail"


def test_segment_gap_forces_a_complete_pcm_retry():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [
        FinalSegmentCoverage(0, 18 * rate, "first", True),
        FinalSegmentCoverage(20 * rate, 38 * rate, "second", True),
    ]
    system._finalized_audio_len = 38 * rate
    data = np.ones(60 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(
        system,
        data,
        buffer_start_sample=0,
        total_samples=len(data),
    )

    assert system.transcriber.lengths == [len(data)]
    assert result.covered_samples == len(data)
    assert result.coverage_ok is True
    assert result.final_source == "full_pcm_fallback"


def test_out_of_order_segments_force_a_complete_pcm_retry():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [
        FinalSegmentCoverage(17 * rate, 36 * rate, "second", True),
        FinalSegmentCoverage(0, 18 * rate, "first", True),
    ]
    system._finalized_audio_len = 36 * rate
    data = np.ones(60 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(
        system,
        data,
        buffer_start_sample=0,
        total_samples=len(data),
    )

    assert system.transcriber.lengths == [len(data)]
    assert result.coverage_ok is True
    assert result.final_source == "full_pcm_fallback"


def test_truncated_tail_is_never_reported_as_complete():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [
        FinalSegmentCoverage(0, 18 * rate, "first", True),
        FinalSegmentCoverage(17 * rate, 36 * rate, "second", True),
    ]
    system._finalized_audio_len = 36 * rate
    data = np.ones(20 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(
        system,
        data,
        buffer_start_sample=35 * rate,
        total_samples=60 * rate,
    )

    assert result.covered_samples < result.captured_samples
    assert result.coverage_ok is False


def test_stop_freezes_microphone_before_invalidating_preview():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_start = main.index("def _on_record_stop")
    stop_end = main.index("def _audio_sample_count", stop_start)
    stop_block = main[stop_start:stop_end]

    assert stop_block.index("self.session.freeze()") < stop_block.index(
        "final_generation = self._stop_streaming()"
    ) < stop_block.index("result = self.session.stop()")


def test_active_recording_never_discards_captured_pcm():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stream_start = main.index("def _start_streaming")
    stream_end = main.index("def _stop_streaming", stream_start)

    assert "discard_before" not in main[stream_start:stream_end]


def test_stop_preview_wait_is_bounded():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_start = main.index("def _stop_streaming")
    stop_end = main.index("def _final_text_from_cache", stop_start)
    stop_block = main[stop_start:stop_end]

    assert ".join(" not in stop_block
    assert "stop_event.set()" in stop_block


def test_stop_final_waits_for_the_inflight_cache_commit_before_snapshotting():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_start = main.index("def _on_record_stop")
    stop_end = main.index("def _audio_sample_count", stop_start)
    stop_block = main[stop_start:stop_end]

    assert stop_block.index("self._await_final_cache_handoff()") < stop_block.index(
        "final_result = self._transcribe_final_result("
    )


def test_final_cache_handoff_uses_a_bounded_event_instead_of_a_thread_join():
    from main import VoiceInputSystem

    system = _system()
    system._final_cache_idle.clear()
    timer = threading.Timer(0.02, system._final_cache_idle.set)
    timer.start()
    try:
        assert VoiceInputSystem._await_final_cache_handoff(system) is True
    finally:
        timer.cancel()


def test_stop_and_background_cache_claim_handoff_under_the_same_lock():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    loop_start = source.index("def final_cache_loop()")
    loop_end = source.index("self._stream_thread =", loop_start)
    stop_start = source.index("def _stop_streaming")
    stop_end = source.index("def _final_text_from_cache", stop_start)

    assert "with self._final_cache_state_lock:" in source[loop_start:loop_end]
    assert "with self._final_cache_state_lock:" in source[stop_start:stop_end]


def test_preview_worker_uses_a_session_local_stop_event():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stream_start = main.index("def _start_streaming")
    stream_end = main.index("def _stop_streaming", stream_start)
    stream_block = main[stream_start:stream_end]
    stop_end = main.index("def _final_text_from_cache", stream_end)
    stop_block = main[stream_end:stop_end]

    assert "stop_event = threading.Event()" in stream_block
    assert "while not stop_event.is_set():" in stream_block
    assert "stop_event.set()" in stop_block


def test_stop_failure_still_invalidates_streaming_preview():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_start = main.index("def _on_record_stop")
    stop_end = main.index("def _audio_sample_count", stop_start)
    stop_block = main[stop_start:stop_end]

    session_freeze = stop_block.index("self.session.freeze()")
    stop_streaming = stop_block.index("final_generation = self._stop_streaming()")
    session_stop = stop_block.index("result = self.session.stop()")
    assert session_freeze < stop_streaming < session_stop


def test_cached_segment_is_reused_for_a_25_second_recording():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [
        FinalSegmentCoverage(0, 18 * rate, "stable", True),
    ]
    system._finalized_audio_len = 18 * rate
    data = np.ones(25 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(
        system,
        data,
        buffer_start_sample=0,
        total_samples=len(data),
    )

    assert system.transcriber.lengths == [8 * rate]
    assert result.final_source == "segments_plus_tail"
    assert result.coverage_ok is True


def test_progressive_cache_prefers_a_stable_preview_endpoint():
    from main import VoiceInputSystem

    system = _system()
    rate = system.audio.sample_rate
    system._preview_endpoint_samples = [5 * rate, 10 * rate]

    segment_range = VoiceInputSystem._next_final_segment_range(
        system,
        12 * rate,
        0,
    )

    assert segment_range == (0, 10 * rate)


def test_progressive_cache_can_confirm_a_pause_without_a_multi_second_hold():
    from main import VoiceInputSystem

    system = _system()
    rate = system.audio.sample_rate
    system._preview_endpoint_samples = [int(10.5 * rate)]

    segment_range = VoiceInputSystem._next_final_segment_range(
        system,
        int(10.82 * rate),
        0,
    )

    assert VoiceInputSystem.FINAL_SEGMENT_HOLD_SECONDS == 0.32
    assert segment_range == (0, int(10.5 * rate))


def test_preview_endpoint_metadata_is_bounded_and_consumed_after_commit():
    from main import VoiceInputSystem

    system = _system()
    for sample_index in range(1, 401):
        VoiceInputSystem._note_preview_endpoint(system, sample_index)

    assert len(system._preview_endpoint_samples) <= VoiceInputSystem.PREVIEW_ENDPOINT_LIMIT
    last_endpoint = system._preview_endpoint_samples[-1]
    assert VoiceInputSystem._consume_preview_endpoint(system, last_endpoint) is True
    assert all(value > last_endpoint for value in system._preview_endpoint_samples)


def test_only_natural_endpoint_segments_replace_live_draft_with_authoritative_text():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    loop_start = source.index("def final_cache_loop()")
    loop_end = source.index("self._stream_thread =", loop_start)
    loop = source[loop_start:loop_end]

    assert "natural_endpoint = self._consume_preview_endpoint(" in loop
    assert "natural_endpoint" in loop
    assert "and authoritative" in loop
