"""Evaluate recorded VoiceFlow responsiveness metrics against release gates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def analyze_history(
    path: str | Path,
    minimum_samples: int = 20,
    evidence_path: str | Path | None = None,
) -> dict:
    history_path = Path(path)
    if evidence_path is not None and Path(evidence_path).exists():
        history_path = Path(evidence_path)
    rows = []
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    feedback = [float(row["trigger_to_feedback_ms"]) for row in rows if "trigger_to_feedback_ms" in row]
    short = [
        float(row["stop_to_paste_ms"])
        for row in rows
        if "stop_to_paste_ms" in row and float(row.get("duration", 0)) <= 20
    ]
    two_minute = [
        float(row["stop_to_paste_ms"])
        for row in rows
        if "stop_to_paste_ms" in row and 110 <= float(row.get("duration", 0)) <= 150
    ]
    preview_model = [
        float(row["preview_first_model_delta_ms"])
        for row in rows
        if "preview_first_model_delta_ms" in row
    ]
    preview_paint = [
        float(row["preview_first_paint_ms"])
        for row in rows
        if "preview_first_paint_ms" in row
    ]
    preview_gap = [
        float(row["preview_update_gap_ms"])
        for row in rows
        if "preview_update_gap_ms" in row
    ]
    preview_queue = [
        float(row["preview_queue_delay_ms"])
        for row in rows
        if "preview_queue_delay_ms" in row
    ]
    preview_chunks = [
        float(row["preview_max_chunk_chars"])
        for row in rows
        if "preview_max_chunk_chars" in row
    ]
    metrics = {
        "trigger_to_feedback_p95_ms": _p95(feedback),
        "short_stop_to_paste_p95_ms": _p95(short),
        "two_minute_stop_to_paste_p95_ms": _p95(two_minute),
        "preview_first_model_delta_p95_ms": _p95(preview_model),
        "preview_first_paint_p95_ms": _p95(preview_paint),
        "preview_update_gap_p95_ms": _p95(preview_gap),
        "preview_queue_delay_p95_ms": _p95(preview_queue),
        "preview_chunk_chars_p95": _p95(preview_chunks),
        "feedback_samples": len(feedback),
        "short_samples": len(short),
        "two_minute_samples": len(two_minute),
        "preview_samples": len(preview_paint),
    }
    failures = []
    for key, count in (
        ("feedback", len(feedback)),
        ("short", len(short)),
        ("two_minute", len(two_minute)),
        ("preview", len(preview_paint)),
    ):
        if count < minimum_samples:
            failures.append(f"{key}: requires {minimum_samples} samples, found {count}")
    if metrics["trigger_to_feedback_p95_ms"] is not None and metrics["trigger_to_feedback_p95_ms"] >= 100:
        failures.append("trigger-to-feedback P95 must be below 100 ms")
    if metrics["short_stop_to_paste_p95_ms"] is not None and metrics["short_stop_to_paste_p95_ms"] > 700:
        failures.append("short stop-to-paste P95 exceeds 700 ms")
    if metrics["two_minute_stop_to_paste_p95_ms"] is not None and metrics["two_minute_stop_to_paste_p95_ms"] > 2500:
        failures.append("two-minute stop-to-paste P95 exceeds 2.5 seconds")
    if metrics["preview_first_model_delta_p95_ms"] is not None and metrics["preview_first_model_delta_p95_ms"] > 900:
        failures.append("preview first model delta P95 exceeds 900 ms")
    if metrics["preview_first_paint_p95_ms"] is not None and metrics["preview_first_paint_p95_ms"] > 900:
        failures.append("preview first paint P95 exceeds 900 ms")
    if metrics["preview_update_gap_p95_ms"] is not None and metrics["preview_update_gap_p95_ms"] > 450:
        failures.append("preview update gap P95 exceeds 450 ms")
    if metrics["preview_queue_delay_p95_ms"] is not None and metrics["preview_queue_delay_p95_ms"] > 250:
        failures.append("preview queue delay P95 exceeds 250 ms")
    if metrics["preview_chunk_chars_p95"] is not None and metrics["preview_chunk_chars_p95"] > 2:
        failures.append("preview chunk-size P95 exceeds 2 characters")
    if preview_chunks and max(preview_chunks) > 4:
        failures.append("preview chunk hard limit exceeds 4 characters")
    return {"passed": not failures, "metrics": metrics, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceFlow release performance gate")
    parser.add_argument("--history", default=str(ROOT / "logs" / "history.jsonl"))
    parser.add_argument(
        "--evidence",
        default=str(ROOT / "logs" / "performance-evidence.jsonl"),
    )
    parser.add_argument("--minimum-samples", type=int, default=20)
    args = parser.parse_args()
    result = analyze_history(
        args.history,
        args.minimum_samples,
        evidence_path=args.evidence,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
