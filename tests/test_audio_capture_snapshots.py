import sys
import threading
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
