"""Measure the production final merge with deterministic nonoverlapping segments."""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src" / "main.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=40)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("at least 20 samples required")
    spec = importlib.util.spec_from_file_location("measured_final_merge", args.source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    system = object.__new__(module.VoiceInputSystem)
    rows = []
    for segments in (4, 34, 200):
        parts = [f"第{index:05d}段" + "本地听写保留完整内容与尾部" * 8 + f"结束{index:05d}。"
                 for index in range(segments)]
        expected = "".join(parts)  # pieces ending in Chinese punctuation join without a space
        assert system._join_transcript_parts(parts) == expected
        timings = []
        for _ in range(args.samples):
            started = time.perf_counter_ns()
            actual = system._join_transcript_parts(parts)
            timings.append((time.perf_counter_ns() - started) / 1e6)
            assert actual == expected
        tracemalloc.start()
        assert system._join_transcript_parts(parts) == expected
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append({
            "segments": segments, "represented_seconds_at_18s_per_segment": segments * 18,
            "characters": len(expected),
            "input_sha256": hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest(),
            "samples": len(timings), "p50_ms": statistics.median(timings),
            "p95_ms": sorted(timings)[math.ceil(len(timings) * .95) - 1],
            "worst_ms": max(timings), "python_traced_peak_bytes": peak,
        })
    report = {
        "kind": "synthetic_source_final_merge_growth",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "conditions": "Production merge, synthetic distinct 18-second segment text, warm sequential runs; allocation measured separately. No ASR/Qt/package/real-use claim.",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
