import sys
import wave
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_silero_gate_rejects_silence_and_accepts_short_real_speech():
    from audio_activity import SileroSpeechDetector

    detector = SileroSpeechDetector(
        ROOT / "assets" / "silero_vad.onnx",
        threshold=0.5,
        min_speech_ms=90,
    )
    silence = np.zeros(16000 * 2, dtype=np.int16)
    with wave.open(str(ROOT / "models" / "sensevoice" / "test_wavs" / "zh.wav"), "rb") as wav:
        speech = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).copy()

    assert detector.has_speech(silence, 16000) is False
    assert detector.has_speech(speech, 16000) is True
