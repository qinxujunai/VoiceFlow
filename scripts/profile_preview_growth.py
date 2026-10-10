"""Measure the current preview wire format with bounded real process queues.

Synthetic text isolates serialization/IPC growth. This does not measure ASR,
audio capture, Qt painting, an installed build, or end-to-end preview latency.
"""

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import math
import multiprocessing
from multiprocessing.reduction import ForkingPickler
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from streaming_transcriber import PreviewEvent


def load_wire_module(source):
    spec = importlib.util.spec_from_file_location("measured_preview_wire", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def response_payload(characters, request_id, pack_event):
    return {
        "kind": "response", "request_id": request_id, "ok": True,
        "event": pack_event(PreviewEvent(
            text="本轮片段" * 20, delta="测", segment_id=1,
            audio_end_sample=1600, committed_text="测" * characters,
            provisional_text="尚未稳定", endpoint_final=False)),
    }


def wire_worker(commands, responses, source):
    module = load_wire_module(source)
    pack_event = getattr(module, "_preview_event_payload", asdict)
    responses.put({"ready": True})
    while True:
        command = commands.get()
        if command is None:
            return
        assert len(command["pcm"]) == 3200
        responses.put(response_payload(command["characters"], command["request_id"], pack_event))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--source", type=Path, default=ROOT / "src" / "preview_worker.py")
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("at least 20 samples required")
    context = multiprocessing.get_context("spawn")
    commands, responses = context.Queue(maxsize=4), context.Queue(maxsize=4)
    module = load_wire_module(args.source)
    pack_event = getattr(module, "_preview_event_payload", asdict)
    worker = context.Process(target=wire_worker, args=(commands, responses, args.source))
    worker.start()
    rows = []
    try:
        assert responses.get(timeout=10) == {"ready": True}
        for duration in (0, 60, 600, 3600):
            characters = duration * 6
            timings = []
            command = {"kind": "accept_pcm", "session_id": "sanitized-growth",
                       "sample_rate": 16000, "pcm": bytes(3200),
                       "characters": characters, "request_id": "fixture-request"}
            for index in range(args.samples + 10):
                started = time.perf_counter_ns()
                commands.put(command, timeout=2)
                response = responses.get(timeout=2)
                elapsed_ms = (time.perf_counter_ns() - started) / 1e6
                event = response["event"]
                if "committed_characters" in event:
                    assert event["committed_characters"] == characters
                else:
                    assert event["committed_text"] == "测" * characters
                if index >= 10:
                    timings.append(elapsed_ms)
            wire_bytes = len(ForkingPickler.dumps(response_payload(characters, "fixture-request", pack_event)))
            rows.append({
                "synthetic_elapsed_seconds": duration,
                "committed_characters": characters,
                "response_serialized_bytes": wire_bytes,
                "samples": len(timings),
                "roundtrip_p50_ms": statistics.median(timings),
                "roundtrip_p95_ms": sorted(timings)[math.ceil(len(timings) * .95) - 1],
                "roundtrip_worst_ms": max(timings),
            })
        # Exact sum of the measured current wire format at 10 updates/second,
        # six synthetic Chinese characters/second. No timing-loop extrapolation.
        cumulative = {}
        for duration in (60, 600, 3600):
            total = sum(len(ForkingPickler.dumps(response_payload(index * 6 // 10,
                                                                  "fixture-request", pack_event)))
                        for index in range(1, duration * 10 + 1))
            cumulative[str(duration)] = total
    finally:
        commands.put(None, timeout=2)
        worker.join(5)
        if worker.is_alive():
            worker.terminate()
            worker.join(2)
        commands.close()
        responses.close()
    if worker.exitcode != 0:
        raise RuntimeError(f"wire fixture worker exit {worker.exitcode}")
    report = {
        "kind": "synthetic_preview_serialization_growth",
        "python": platform.python_version(),
        "source_sha256": {
            "preview_worker.py": hashlib.sha256(args.source.read_bytes()).hexdigest(),
            "streaming_transcriber.py": hashlib.sha256((ROOT / "src" / "streaming_transcriber.py").read_bytes()).hexdigest()},
        "conditions": {
            "native_asr": False, "installed_build": False, "qt": False,
            "pcm_block_ms": 100, "updates_per_second": 10,
            "synthetic_chinese_characters_per_second": 6,
            "bounded_queue_capacity": 4, "in_flight_requests": 1,
            "warmup_per_bucket": 10,
            "wire_payload": "delta plus committed length" if hasattr(module, "_preview_event_payload")
                            else "asdict(PreviewEvent), including full committed_text",
        },
        "rows": rows, "cumulative_response_bytes": cumulative,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
