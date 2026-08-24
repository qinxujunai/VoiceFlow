import sys
import threading
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_snapshot_audio_copies_only_requested_sample_range():
    from audio_capture import AudioCapture

    capture = object.__new__(AudioCapture)
    capture._lock = threading.Lock()
    capture._audio_buffer = [
        np.arange(0, 4, dtype=np.int16).reshape(-1, 1),
        np.arange(4, 8, dtype=np.int16).reshape(-1, 1),
        np.arange(8, 12, dtype=np.int16).reshape(-1, 1),
    ]
    capture._audio_buffer_ends = [4, 8, 12]
    capture._total_samples = 12

    result = capture.snapshot_audio(5, 11)

    assert result.tolist() == [5, 6, 7, 8, 9, 10]
    assert capture.sample_count == 12


def test_discard_before_releases_old_blocks_without_changing_global_clock():
    from audio_capture import AudioCapture

    capture = object.__new__(AudioCapture)
    capture._lock = threading.Lock()
    capture._audio_buffer = [
        np.arange(start, start + 4, dtype=np.int16).reshape(-1, 1)
        for start in range(0, 20, 4)
    ]
    capture._audio_buffer_ends = [4, 8, 12, 16, 20]
    capture._buffer_start_sample = 0
    capture._total_samples = 20

    retained_from = capture.discard_before(13)

    assert retained_from == 12
    assert capture.sample_count == 20
    assert len(capture._audio_buffer) == 2
    assert capture.snapshot_audio(12, 20).tolist() == list(range(12, 20))


def test_level_and_vad_analysis_runs_outside_the_audio_callback():
    from audio_capture import AudioCapture

    capture = object.__new__(AudioCapture)
    capture._on_level_callback = None
    capture.vad_enabled = True
    capture.vad_energy_threshold = 0.02
    capture._last_speech_time = 0
    received = []
    capture._on_level_callback = received.append
    block = np.full((1600, 1), 4096, dtype=np.int16)

    before = time.time()
    capture._process_analysis_block(block)

    assert len(received) == 1
    assert len(received[0]) == 3
    assert all(level > 0 for level in received[0])
    assert capture._last_speech_time >= before


def test_audio_callback_keeps_signal_processing_in_latest_only_worker():
    source = (ROOT / "src" / "audio_capture.py").read_text(encoding="utf-8")
    callback_start = source.index("def audio_callback")
    stream_start = source.index("self._stream = sd.InputStream", callback_start)
    callback = source[callback_start:stream_start]

    assert "indata.copy()" in callback
    assert "self._enqueue_analysis(block)" in callback
    assert "astype(" not in callback
    assert "array_split(" not in callback
    assert "np.sqrt(" not in callback


def test_analysis_worker_owns_generation_specific_queue_and_stop_event():
    source = (ROOT / "src" / "audio_capture.py").read_text(encoding="utf-8")
    worker_start = source.index("def _start_analysis_worker")
    worker_stop = source.index("def _stop_analysis_worker", worker_start)
    worker = source[worker_start:worker_stop]

    assert "analysis_queue = queue.Queue(maxsize=1)" in worker
    assert "stop_event = threading.Event()" in worker
    assert "while not stop_event.is_set() or not analysis_queue.empty()" in worker
    assert "block = analysis_queue.get(timeout=0.1)" in worker


def test_ten_minutes_of_pcm_stays_within_the_25_mb_recovery_budget():
    sample_rate = 16000
    block_samples = sample_rate // 10
    blocks = [
        np.zeros((block_samples, 1), dtype=np.int16)
        for _ in range(10 * 60 * 10)
    ]

    payload_bytes = sum(block.nbytes for block in blocks)

    assert payload_bytes == 19_200_000
    assert payload_bytes <= 25 * 1024 * 1024


def test_analysis_worker_is_woken_with_a_sentinel_instead_of_polling_on_stop():
    source = (ROOT / "src" / "audio_capture.py").read_text(encoding="utf-8")
    start = source.index("def _start_analysis_worker")
    stop = source.index("def _stop_analysis_worker", start)
    enqueue = source.index("def _enqueue_analysis", stop)

    worker = source[start:stop]
    shutdown = source[stop:enqueue]

    assert "if block is None:" in worker
    assert "analysis_queue.put_nowait(None)" in shutdown
    assert "thread.join(timeout=0.05)" in shutdown


def test_freeze_recording_atomically_latches_the_final_sample_boundary():
    from audio_capture import AudioCapture

    capture = object.__new__(AudioCapture)
    capture._lock = threading.Lock()
    capture._is_recording = True
    capture._is_frozen = False
    capture._buffer_start_sample = 0
    capture._total_samples = 32000
    capture._last_buffer_start_sample = 0
    capture._last_total_samples = 0

    frozen_at = capture.freeze_recording()

    assert frozen_at == 32000
    assert capture._is_recording is False
    assert capture._is_frozen is True
    assert capture.last_total_samples == 32000


def test_stop_recording_returns_frozen_audio_when_driver_teardown_blocks():
    from audio_capture import AudioCapture

    release_abort = threading.Event()
    abort_started = threading.Event()
    close_called = threading.Event()

    class BlockingStream:
        def abort(self):
            abort_started.set()
            release_abort.wait(timeout=2.0)

        def close(self):
            close_called.set()

    capture = object.__new__(AudioCapture)
    capture._lock = threading.Lock()
    capture._is_recording = False
    capture._is_frozen = True
    capture._stream = BlockingStream()
    capture._audio_buffer = [np.arange(1600, dtype=np.int16).reshape(-1, 1)]
    capture._audio_buffer_ends = [1600]
    capture._buffer_start_sample = 0
    capture._total_samples = 1600
    capture._last_buffer_start_sample = 0
    capture._last_total_samples = 1600
    capture._analysis_stop = None
    capture._analysis_queue = None
    capture._analysis_thread = None
    capture._stream_teardown_threads = []

    started = time.perf_counter()
    audio = capture.stop_recording()
    elapsed = time.perf_counter() - started

    try:
        assert abort_started.wait(timeout=0.2)
        assert elapsed < 0.15
        assert audio.tolist() == list(range(1600))
        assert capture._stream is None
        assert not close_called.is_set()
    finally:
        release_abort.set()

    assert close_called.wait(timeout=0.5)
