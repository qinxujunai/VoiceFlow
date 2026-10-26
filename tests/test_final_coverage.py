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


# Stop latency (2026-10-26): pieces are cut inside the speaker's pauses while recording, so the stop path
# only recognizes the last piece. See docs/stop-latency-evaluation-2026-10-26.md.

def _audio_system(pcm):
    system = _system()
    system._audio_snapshot = lambda start, end: pcm[max(0, int(start)):int(end)]
    return system


def test_pause_cut_moves_back_to_the_silence_before_the_late_endpoint():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    noise = np.random.default_rng(1).normal(0, 30, 10 * rate)   # a microphone's noise floor
    pcm = (noise + np.where(np.arange(10 * rate) % 400 < 200, 3000, -3000)).astype(np.int16)
    pcm[int(5.0 * rate):int(5.6 * rate)] = noise[int(5.0 * rate):int(5.6 * rate)].astype(np.int16)
    system = _audio_system(pcm)
    # the preview recognizer reported the pause late, when the next phrase had already started
    cut, in_pause = VoiceInputSystem._quiet_cut(system, 0, int(6.0 * rate))
    assert in_pause is True
    assert int(5.0 * rate) <= cut <= int(5.6 * rate)


def test_an_endpoint_without_a_quiet_stretch_is_not_treated_as_a_pause():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    speech = np.where(np.arange(20 * rate) % 400 < 200, 3000, -3000).astype(np.int16)  # no dip at all
    system = _audio_system(speech)
    assert VoiceInputSystem._quiet_cut(system, 0, 18 * rate) == (18 * rate, False)


def test_pause_cut_keeps_the_endpoint_when_audio_is_unavailable():
    from main import VoiceInputSystem

    system = _system()  # no audio buffer
    assert VoiceInputSystem._quiet_cut(system, 0, 6 * FakeAudio.sample_rate) == (6 * FakeAudio.sample_rate, False)


def test_pause_cut_never_makes_a_piece_shorter_than_four_seconds():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    pcm = np.where(np.arange(10 * rate) % 400 < 200, 3000, -3000).astype(np.int16)
    pcm[int(2.3 * rate):int(2.6 * rate)] = 0                     # a pause too early to cut at
    pcm[int(4.2 * rate):int(4.6 * rate)] = 0
    system = _audio_system(pcm)
    cut, in_pause = VoiceInputSystem._quiet_cut(system, 0, int(5.0 * rate))
    assert in_pause and cut >= 4 * rate


def test_pieces_need_four_seconds_before_a_pause_ends_one():
    from main import VoiceInputSystem

    system = _system()
    rate = system.audio.sample_rate
    system._preview_endpoint_samples = [3 * rate]
    assert VoiceInputSystem._next_final_segment_range(system, 6 * rate, 0) is None
    system._preview_endpoint_samples = [3 * rate, int(4.5 * rate)]
    assert VoiceInputSystem._next_final_segment_range(system, 6 * rate, 0) == (0, int(4.5 * rate))


def test_a_piece_after_a_pause_cut_starts_exactly_at_the_cut():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = system.audio.sample_rate
    system._final_segments = [FinalSegmentCoverage(0, 5 * rate, "第一句", True, cut_in_pause=True)]
    system._finalized_audio_len = 5 * rate
    system._preview_endpoint_samples = [10 * rate]
    assert VoiceInputSystem._next_final_segment_range(system, 11 * rate, 5 * rate) == (5 * rate, 10 * rate)
    # a forced cut (no pause for 18 s) still re-reads one second so no word is lost
    system._final_segments = [FinalSegmentCoverage(0, 5 * rate, "第一句", True)]
    assert VoiceInputSystem._next_final_segment_range(system, 11 * rate, 5 * rate) == (4 * rate, 10 * rate)


def test_a_long_dictation_reads_only_the_tail_after_its_last_pause_cut():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [FinalSegmentCoverage(0, 20 * rate, "先列出问题", True, cut_in_pause=True)]
    system._finalized_audio_len = 20 * rate
    data = np.ones(24 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(system, data, buffer_start_sample=0, total_samples=len(data))

    assert system.transcriber.lengths == [4 * rate]      # only the last piece, no overlap
    assert result.final_source == "segments_plus_tail"
    assert result.coverage_ok is True


def test_shorter_dictation_is_still_recognized_whole():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = _system()
    rate = FakeAudio.sample_rate
    system._final_segments = [FinalSegmentCoverage(0, 6 * rate, "很短", True, cut_in_pause=True)]
    system._finalized_audio_len = 6 * rate
    data = np.ones(11 * rate, dtype=np.int16)

    result = VoiceInputSystem._transcribe_final_result(system, data, buffer_start_sample=0, total_samples=len(data))

    assert system.transcriber.lengths == [len(data)]
    assert result.final_source == "full_pcm"


def test_chinese_pieces_meet_without_a_space_and_latin_words_keep_theirs():
    from main import VoiceInputSystem

    system = object.__new__(VoiceInputSystem)
    assert system._join_transcript_parts(["顺便把快递取了。", "明天早上要早点出门。"]) == "顺便把快递取了。明天早上要早点出门。"
    assert system._join_transcript_parts(["open the", "settings page"]) == "open the settings page"
    assert system._join_transcript_parts(["用 Claude", "写一个脚本"]) == "用 Claude 写一个脚本"
    assert system._join_transcript_parts(["重新排一下优先级。", "Z 核心"]) == "重新排一下优先级。Z 核心"
    assert system._join_transcript_parts(["要用中文", "Claude"]) == "要用中文 Claude"


def test_words_repeated_across_a_pause_cut_are_kept():
    from main import FinalSegmentCoverage, VoiceInputSystem

    system = object.__new__(VoiceInputSystem)
    after_pause = [FinalSegmentCoverage(0, 1, "第一步打开设置。", True, cut_in_pause=True)]
    assert system._join_segments(after_pause, "设置里找到快捷键") == "第一步打开设置。设置里找到快捷键"
    after_pause = [FinalSegmentCoverage(0, 1, "好的。", True, cut_in_pause=True)]
    assert system._join_segments(after_pause, "好的，我们开始吧") == "好的。好的，我们开始吧"
    # after a forced cut the next piece re-read one second, so the repeat is the overlap and is merged
    forced = [FinalSegmentCoverage(0, 1, "第一步打开设置", True)]
    assert system._join_segments(forced, "打开设置里找到快捷键") == "第一步打开设置里找到快捷键"


def _speculating_system(pcm):
    system = _audio_system(pcm)
    system._speculative_final = None
    system._speech_scan = (0, 0.0, 0)
    return system


def _speech(seconds, rate=FakeAudio.sample_rate):
    return np.where(np.arange(int(seconds * rate)) % 400 < 200, 3000, -3000).astype(np.int16)


def test_a_pause_after_speech_starts_a_background_guess_once():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    pcm = np.concatenate([_speech(3), np.zeros(int(0.4 * rate), np.int16)])
    system = _speculating_system(pcm)
    assert VoiceInputSystem._speculation_due(system, 3 * rate) is None          # still talking
    assert VoiceInputSystem._speculation_due(system, len(pcm)) == len(pcm)      # 0.4 s of quiet
    system._speculative_final = (len(pcm), "第一句")
    assert VoiceInputSystem._speculation_due(system, len(pcm)) is None          # nothing new said


def test_no_guess_for_recordings_that_use_pieces():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    pcm = np.concatenate([_speech(21), np.zeros(rate, np.int16)])
    system = _speculating_system(pcm)
    assert VoiceInputSystem._speculation_due(system, len(pcm)) is None


def test_the_guess_is_the_final_text_when_only_silence_follows_it():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    data = np.concatenate([np.ones(5 * rate, np.int16), np.zeros(rate, np.int16)])
    system = _system()
    system._speculative_final = (5 * rate, "已经识别好的整句")
    system._transcribe_audio = lambda audio, **_kw: ("", False)
    result = VoiceInputSystem._transcribe_final_result(system, data, buffer_start_sample=0, total_samples=len(data))
    assert result.text == "已经识别好的整句"
    assert result.final_source == "speculative_full"
    assert result.coverage_ok is True


def test_words_after_the_guess_make_the_whole_recording_be_recognized_again():
    from main import VoiceInputSystem

    rate = FakeAudio.sample_rate
    data = np.ones(8 * rate, np.int16)
    system = _system()
    system._speculative_final = (5 * rate, "前半句")
    calls = []
    def transcribe(audio, return_activity=False, **_kw):
        calls.append(len(audio))
        return ("后半句", True) if return_activity else "整句"
    system._transcribe_audio = transcribe
    result = VoiceInputSystem._transcribe_final_result(system, data, buffer_start_sample=0, total_samples=len(data))
    assert result.text == "整句"
    assert result.final_source == "full_pcm"
    assert calls == [3 * rate, 8 * rate]
