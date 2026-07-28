from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _read_pcm(path):
    with wave.open(str(path), "rb") as source:
        assert source.getnchannels() == 1
        assert source.getsampwidth() == 2
        rate = source.getframerate()
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
    return rate, pcm


def test_real_streaming_preview_is_incremental_monotonic_and_realtime():
    from streaming_transcriber import OnlinePreviewTranscriber

    model = ROOT / "models" / "streaming-preview" / "model.int8.onnx"
    tokens = ROOT / "models" / "streaming-preview" / "tokens.txt"
    wav = ROOT / "models" / "sensevoice" / "test_wavs" / "zh.wav"
    if not model.is_file() or not tokens.is_file() or not wav.is_file():
        pytest.skip("pinned streaming-preview smoke assets are not installed")

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    rate, source_pcm = _read_pcm(wav)
    pcm = np.tile(source_pcm, 6)
    transcriber = OnlinePreviewTranscriber.from_config(
        config,
        resolve_asset=lambda raw: ROOT / raw,
        sample_rate=rate,
    )
    session = transcriber.create_session()
    chunk_samples = max(1, rate // 10)
    changes = 0
    retractions = 0
    first_text_audio_ms = None
    previous = ""
    started = time.perf_counter()

    for end in range(chunk_samples, len(pcm) + chunk_samples, chunk_samples):
        start = end - chunk_samples
        update = transcriber.accept_pcm(
            session,
            pcm[start:min(end, len(pcm))],
            rate,
        )
        visible = session.committed_text
        if visible != previous:
            changes += 1
            if previous and not visible.startswith(previous):
                retractions += 1
            previous = visible
        if update.delta and first_text_audio_ms is None:
            first_text_audio_ms = min(end, len(pcm)) / rate * 1000

    elapsed = time.perf_counter() - started
    duration = len(pcm) / rate

    assert first_text_audio_ms is not None
    assert first_text_audio_ms <= 2000
    assert changes >= 12
    assert retractions == 0
    assert session.fed_samples == len(pcm)
    assert elapsed / duration < 0.1
