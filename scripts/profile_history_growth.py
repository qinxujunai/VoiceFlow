"""Measure recent-history reads against sanitized, reproducible local files."""

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("src/history_store.py"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=40)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("at least 20 samples are required")
    spec = importlib.util.spec_from_file_location("measured_history", args.source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    with tempfile.TemporaryDirectory(prefix="voiceflow-history-profile-") as folder:
        path = Path(folder) / "history.jsonl"
        for count in (1000, 10000, 100000):
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                for index in range(count):
                    stream.write(json.dumps({
                        "session_id": str(index),
                        "corrected_text": "sanitized source growth fixture " * 5,
                    }) + "\n")
            corpus_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            store = module.HistoryStore(path)
            expected = [str(index) for index in range(count - 1, count - 81, -1)]
            store.read_recent(80)
            timings = []
            for _ in range(args.samples):
                started = time.perf_counter_ns()
                rows = store.read_recent(80)
                timings.append((time.perf_counter_ns() - started) / 1e6)
                assert [row["session_id"] for row in rows] == expected
            tracemalloc.start()
            store.read_recent(80)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results.append({
                "rows": count,
                "bytes": path.stat().st_size,
                "corpus_sha256": corpus_hash,
                "samples": args.samples,
                "p50_ms": statistics.median(timings),
                "p95_ms": sorted(timings)[math.ceil(len(timings) * .95) - 1],
                "worst_ms": max(timings),
                "python_traced_peak_bytes": peak,
            })
    report = {
        "kind": "source_history_growth_profile",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "conditions": (
            "Local temporary files; warm sequential reads of 80 records; "
            "sanitized synthetic corpus; allocation measured separately from timing. "
            "Python traced allocation is not whole-process RAM. "
            "This is a source component measurement, not installed RC performance."
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
