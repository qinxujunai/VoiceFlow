"""Measure streaming-preview emission independently from the final ASR."""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from audio_activity import find_speech_onset
from runtime_paths import AppPaths
from streaming_transcriber import OnlinePreviewTranscriber


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = min(
        len(ordered) - 1,
        max(0, int(round((len(ordered) - 1) * percentile / 100))),
    )
    return ordered[index]


def _read_wav(path: Path):
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2:
            raise ValueError(f"Only 16-bit PCM WAV is supported: {path}")
        rate = source.getframerate()
        channels = source.getnchannels()
        pcm = np.frombuffer(
            source.readframes(source.getnframes()),
            dtype=np.int16,
        )
    if channels > 1:
        pcm = pcm.reshape(-1, channels)[:, 0]
    return pcm.copy(), rate


def evaluate_pcm(
    preview,
    pcm,
    sample_rate,
    *,
    chunk_ms=80,
    append_interval_ms=80,
):
    samples = np.asarray(pcm, dtype=np.int16).reshape(-1)
    onset_sample = find_speech_onset(
        samples,
        sample_rate,
        rms_threshold=0.002,
        min_active_ms=90,
    )
    session = preview.create_session()
    chunk_samples = max(1, int(sample_rate * chunk_ms / 1000))
    first_delta_ms = None
    update_audio_ms = []
    chunks = []
    divergence_count = 0
    queue_delays = []
    next_display_ms = 0.0
    decode_started = time.perf_counter()

    for start in range(0, len(samples), chunk_samples):
        end = min(len(samples), start + chunk_samples)
        event = preview.accept_pcm(session, samples[start:end], sample_rate)
        if event.hypothesis_diverged:
            divergence_count += 1
        if not event.delta:
            continue
        arrival_ms = end / sample_rate * 1000
        relative_ms = (
            None
            if onset_sample is None
            else max(0.0, (end - onset_sample) / sample_rate * 1000)
        )
        if first_delta_ms is None:
            first_delta_ms = relative_ms
        update_audio_ms.append(arrival_ms)
        chunks.append(len(event.delta))
        for _character in event.delta:
            display_ms = max(arrival_ms, next_display_ms)
            queue_delays.append(display_ms - arrival_ms)
            next_display_ms = display_ms + append_interval_ms

    decode_ms = (time.perf_counter() - decode_started) * 1000
    update_gaps = [
        current - previous
        for previous, current in zip(update_audio_ms, update_audio_ms[1:])
    ]
    return {
        "duration_ms": round(len(samples) / sample_rate * 1000, 3),
        "speech_onset_ms": (
            None
            if onset_sample is None
            else round(onset_sample / sample_rate * 1000, 3)
        ),
        "first_delta_ms": (
            None if first_delta_ms is None else round(first_delta_ms, 3)
        ),
        "update_gap_p95_ms": _percentile(update_gaps, 95),
        "max_chunk_chars": max(chunks, default=0),
        "chunk_chars_p95": _percentile(chunks, 95),
        "queue_delay_p95_ms": _percentile(queue_delays, 95),
        "divergence_count": divergence_count,
        "decode_ms": round(decode_ms, 3),
        "committed_text": session.committed_text,
    }


def _gate(result):
    failures = []
    first_delta = result.get("first_delta_ms")
    if first_delta is None or first_delta > 900:
        failures.append(f"first delta {first_delta}ms exceeds 900ms")
    gap = result.get("update_gap_p95_ms")
    if gap is not None and gap > 450:
        failures.append(f"update gap P95 {gap}ms exceeds 450ms")
    chunk = result.get("chunk_chars_p95")
    if chunk is not None and chunk > 2:
        failures.append(f"chunk size P95 {chunk} exceeds 2 chars")
    if result.get("max_chunk_chars", 0) > 4:
        failures.append("chunk hard limit exceeds 4 chars")
    queue = result.get("queue_delay_p95_ms")
    if queue is not None and queue > 250:
        failures.append(f"queue delay P95 {queue}ms exceeds 250ms")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config.yaml",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        default=ROOT / "models" / "sensevoice" / "test_wavs" / "zh.wav",
    )
    parser.add_argument("--chunk-ms", type=int, default=80)
    parser.add_argument("--append-interval-ms", type=int, default=80)
    parser.add_argument(
        "--candidate",
        default=None,
        help="pinned model id from model-manifest.json",
    )
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    if args.candidate:
        manifest = json.loads(
            (ROOT / "model-manifest.json").read_text(encoding="utf-8")
        )
        model = manifest["models"].get(args.candidate)
        if model is None:
            raise SystemExit(f"Unknown streaming candidate: {args.candidate}")
        target = model["target_dir"]
        files = {item["path"] for item in model["files"]}
        preview_config = {
            "enabled": True,
            "runtime_engine": model["runtime_engine"],
            "provider": "cpu",
            "num_threads": "auto",
            "tokens_path": f"{target}/tokens.txt",
            "stability_guard_chars": 1,
        }
        if model["runtime_engine"] == "online-paraformer":
            preview_config.update(
                {
                    "encoder_path": f"{target}/encoder.int8.onnx",
                    "decoder_path": f"{target}/decoder.int8.onnx",
                }
            )
        elif "model.int8.onnx" in files:
            preview_config["model_path"] = f"{target}/model.int8.onnx"
        else:
            raise SystemExit(
                f"Unsupported streaming candidate layout: {args.candidate}"
            )
        config["streaming_preview"] = preview_config
    paths = AppPaths.discover(config_path=args.config)
    pcm, rate = _read_wav(args.audio)
    preview = OnlinePreviewTranscriber.from_config(
        config,
        resolve_asset=paths.resolve_asset,
        sample_rate=rate,
    )
    result = evaluate_pcm(
        preview,
        pcm,
        rate,
        chunk_ms=args.chunk_ms,
        append_interval_ms=args.append_interval_ms,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failures = _gate(result)
    if args.enforce and failures:
        raise SystemExit("Streaming preview gate failed:\n- " + "\n- ".join(failures))


if __name__ == "__main__":
    main()
