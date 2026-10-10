"""Replay public fixture audio through the real supervised preview worker.

Runs faster than wall clock. No microphone, clipboard, UI, or natural accuracy
claim. Deltas are hashed to compare the same native model before/after IPC edits.
"""

import argparse
import functools
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from runtime_bootstrap import configure_native_thread_pools
configure_native_thread_pools()

import numpy as np


def load_source(source):
    spec = importlib.util.spec_from_file_location("exercised_preview", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def worker_from_source(commands, responses, heartbeat, config, *, source):
    load_source(source)._preview_worker_main(commands, responses, heartbeat, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src" / "preview_worker.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    module = load_source(args.source)
    preview = module.SupervisedPreviewTranscriber(
        ROOT / "config.yaml", asset_roots=(ROOT,),
        worker_target=functools.partial(worker_from_source, source=args.source))
    started = time.perf_counter()
    preview.load()
    load_seconds = time.perf_counter() - started
    worker_pid = preview.worker_pid
    rows = []
    try:
        for language in ("zh", "en"):
            path = ROOT / "models" / "sensevoice" / "test_wavs" / f"{language}.wav"
            with wave.open(str(path), "rb") as wav:
                assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
                rate = wav.getframerate()
                original = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
            samples = np.tile(original, int(np.ceil(rate * args.seconds / len(original))))[:rate * args.seconds]
            session = preview.create_session()
            delta_hash, event_hash = hashlib.sha256(), hashlib.sha256()
            previous, updates, endpoints = "", 0, 0
            chunk_size = rate // 10
            started = time.perf_counter()
            for offset in range(0, len(samples), chunk_size):
                event = preview.accept_pcm(session, samples[offset:offset + chunk_size], rate)
                assert event.committed_text == previous + event.delta
                assert session.committed_text == event.committed_text
                previous = event.committed_text
                delta_hash.update(event.delta.encode("utf-8"))
                event_hash.update(json.dumps({
                    "delta": event.delta, "segment": event.segment_id,
                    "sample": event.audio_end_sample, "endpoint": event.endpoint_final,
                    "diverged": event.hypothesis_diverged,
                }, sort_keys=True, ensure_ascii=False).encode("utf-8"))
                updates += 1
                endpoints += int(event.endpoint_final)
            elapsed = time.perf_counter() - started
            preview.close_session(session)
            rows.append({
                "language": language, "samples": len(samples), "sample_rate": rate,
                "input_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                "updates": updates, "endpoints": endpoints,
                "committed_characters": len(previous),
                "delta_sha256": delta_hash.hexdigest(), "event_sha256": event_hash.hexdigest(),
                "duration_seconds": len(samples) / rate, "compute_seconds": elapsed,
                "real_time_factor": elapsed / (len(samples) / rate),
            })
    finally:
        preview.shutdown()
    report = {
        "kind": "real_native_supervised_preview_regression",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "load_seconds": load_seconds, "worker_pid": worker_pid,
        "worker_stopped": preview.worker_pid is None,
        "conditions": "Public repeated fixture audio, accelerated 100ms PCM blocks; no microphone/UI/package claim.",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
