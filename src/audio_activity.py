"""Cheap offline speech-presence checks before invoking ASR."""

from __future__ import annotations

import math

import numpy as np


class SileroSpeechDetector:
    """Isolated sherpa-onnx Silero VAD inference for one audio buffer."""

    def __init__(
        self,
        model_path,
        *,
        threshold: float = 0.5,
        min_speech_ms: int = 90,
        sample_rate: int = 16000,
    ):
        import sherpa_onnx

        silero = sherpa_onnx.SileroVadModelConfig(
            model=str(model_path),
            threshold=float(threshold),
            min_silence_duration=0.1,
            min_speech_duration=max(0.03, min_speech_ms / 1000),
            window_size=512,
            max_speech_duration=60,
        )
        self.config = sherpa_onnx.VadModelConfig(
            silero_vad=silero,
            sample_rate=int(sample_rate),
            num_threads=1,
            provider="cpu",
            debug=False,
        )
        if not self.config.validate():
            raise RuntimeError(f"Silero VAD 配置无效: {model_path}")
        self.sample_rate = int(sample_rate)

    def has_speech(self, audio_data, sample_rate: int) -> bool:
        if int(sample_rate) != self.sample_rate:
            raise ValueError(
                f"Silero VAD 需要 {self.sample_rate}Hz，收到 {sample_rate}Hz"
            )
        import sherpa_onnx

        audio = np.asarray(audio_data).reshape(-1)
        if audio.size == 0:
            return False
        if np.issubdtype(audio.dtype, np.integer):
            scale = float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max))
            samples = audio.astype(np.float32) / scale
        else:
            samples = audio.astype(np.float32)

        detector = sherpa_onnx.VoiceActivityDetector(self.config, 60)
        window_size = 512
        for start in range(0, samples.size, window_size):
            detector.accept_waveform(samples[start:start + window_size])
            if detector.is_speech_detected() or not detector.empty():
                return True
        detector.flush()
        return detector.is_speech_detected() or not detector.empty()


def has_speech_activity(
    audio_data,
    sample_rate: int,
    *,
    rms_threshold: float = 0.02,
    min_active_ms: int = 90,
    frame_ms: int = 30,
) -> bool:
    """Return whether PCM contains enough energetic frames to be speech.

    This is a presence gate, not endpointing: it never stops recording and it
    does not trim audio. Its only purpose is to keep silence and key-clicks away
    from recognizers that are forced to emit a token for every input.
    """
    audio = np.asarray(audio_data).reshape(-1)
    if audio.size == 0 or sample_rate <= 0:
        return False

    if np.issubdtype(audio.dtype, np.integer):
        scale = float(max(abs(np.iinfo(audio.dtype).min), np.iinfo(audio.dtype).max))
        samples = audio.astype(np.float64) / scale
    else:
        samples = audio.astype(np.float64)

    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    required_frames = max(1, math.ceil(min_active_ms / frame_ms))
    active_frames = 0
    for start in range(0, samples.size, frame_samples):
        frame = samples[start:start + frame_samples]
        if frame.size == 0:
            continue
        rms = float(np.sqrt(np.mean(frame * frame)))
        if rms >= rms_threshold:
            active_frames += 1
            if active_frames >= required_frames:
                return True
    return False


def has_lexical_content(text: str) -> bool:
    """Punctuation alone is not recoverable dictation content."""
    return any(character.isalnum() for character in str(text or ""))
