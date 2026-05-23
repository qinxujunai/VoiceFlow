"""
Benchmark available VoiceFlow ASR model variants.

This does not change config.yaml. It probes local model files and reports
load time, transcription time, RTF, and output text for bundled test wavs.
"""

from __future__ import annotations

import argparse
import copy
import tempfile
import time
import wave
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys

sys.path.insert(0, str(SRC))

from transcriber import Transcriber  # noqa: E402


def _variant_configs(config):
    variants = []
    engine = config.get("engine", {})
    sense = copy.deepcopy(engine.get("sensevoice", {}))
    qwen = copy.deepcopy(engine.get("qwen3-asr", {}))

    if sense:
        int8 = copy.deepcopy(config)
        int8["engine"]["active"] = "sensevoice"
        int8["engine"]["sensevoice"]["model_path"] = "models/sensevoice/model.int8.onnx"
        variants.append(("sensevoice-int8", int8))

        fp32_path = ROOT / "models" / "sensevoice" / "model.onnx"
        if fp32_path.exists():
            fp32 = copy.deepcopy(config)
            fp32["engine"]["active"] = "sensevoice"
            fp32["engine"]["sensevoice"]["model_path"] = "models/sensevoice/model.onnx"
            variants.append(("sensevoice-fp32", fp32))

    qwen_model = ROOT / qwen.get("model_path", "")
    qwen_tokens = ROOT / qwen.get("tokens_path", "")
    if qwen and qwen_model.exists() and qwen_tokens.exists():
        qwen_cfg = copy.deepcopy(config)
        qwen_cfg["engine"]["active"] = "qwen3-asr"
        variants.append(("qwen3-asr", qwen_cfg))

    return variants


def _write_temp_config(config):
    handle = tempfile.NamedTemporaryFile(
        "w",
        suffix=".yaml",
        prefix=".benchmark-",
        dir=ROOT,
        delete=False,
        encoding="utf-8",
    )
    with handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    return handle.name


def _wav_files(limit=None):
    wav_dir = ROOT / "models" / "sensevoice" / "test_wavs"
    files = sorted(wav_dir.glob("*.wav"))
    return files[:limit] if limit else files


def _read_wav(path):
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise ValueError(f"Only 16-bit PCM wav is supported: {path}")

    import numpy as np

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]
    return audio.copy(), sample_rate


def benchmark(limit=None):
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    wavs = _wav_files(limit)
    if not wavs:
        raise SystemExit("No test wavs found under models/sensevoice/test_wavs")

    for name, cfg in _variant_configs(config):
        cfg_path = _write_temp_config(cfg)
        transcriber = Transcriber(cfg_path)

        t0 = time.time()
        transcriber.load_engine(cfg["engine"]["active"])
        load_time = time.time() - t0
        print(f"\n== {name} | load {load_time:.2f}s ==")

        for wav in wavs:
            audio, sample_rate = _read_wav(wav)
            duration = len(audio) / sample_rate
            t1 = time.time()
            text = transcriber.transcribe(audio, sample_rate)
            elapsed = time.time() - t1
            rtf = elapsed / duration if duration else 0
            print(f"{wav.stem:>6} | {elapsed:.2f}s | RTF {rtf:.3f} | {text}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark local VoiceFlow ASR models")
    parser.add_argument("--limit", type=int, default=None, help="limit number of wav files")
    args = parser.parse_args()
    benchmark(limit=args.limit)


if __name__ == "__main__":
    main()
