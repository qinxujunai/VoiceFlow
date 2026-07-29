import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_find_speech_onset_returns_first_frame_of_sustained_activity():
    from audio_activity import find_speech_onset

    sample_rate = 16000
    silence = np.zeros(1600, dtype=np.int16)
    speech = np.full(2400, 5000, dtype=np.int16)

    onset = find_speech_onset(
        np.concatenate((silence, speech)),
        sample_rate,
        rms_threshold=0.02,
        min_active_ms=90,
        frame_ms=30,
    )

    assert onset == 1600


def test_find_speech_onset_rejects_a_single_click():
    from audio_activity import find_speech_onset

    audio = np.zeros(3200, dtype=np.int16)
    audio[800:960] = 12000

    assert (
        find_speech_onset(
            audio,
            16000,
            rms_threshold=0.02,
            min_active_ms=90,
            frame_ms=30,
        )
        is None
    )
