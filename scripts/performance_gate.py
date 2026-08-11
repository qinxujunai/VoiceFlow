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
        if "stop_to_paste_ms" in row and float(row.get("duration", 0)) <= 10
    ]
    medium = [
        float(row["stop_to_paste_ms"])
        for row in rows
        if (
            "stop_to_paste_ms" in row
            and 10 < float(row.get("duration", 0)) <= 60
        )
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
    preview_model_gap = [
        float(row["preview_model_update_gap_ms"])
        for row in rows
        if row.get("preview_model_update_gap_ms") is not None
    ]
    preview_active_gap = [
        float(row["preview_active_speech_update_gap_ms"])
        for row in rows
        if "preview_active_speech_update_gap_ms" in row
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
    preview_visible_chunks = [
        float(row["preview_visible_chunk_chars"])
        for row in rows
        if row.get("preview_visible_chunk_chars") is not None
    ]
    preview_model_chunks = [
        float(row["preview_model_delta_chars"])
        for row in rows
        if row.get("preview_model_delta_chars") is not None
    ]
    preview_model_chunk_max = [
        float(row["preview_model_delta_hard_max_chars"])
        for row in rows
        if row.get("preview_model_delta_hard_max_chars") is not None
    ]
    metrics = {
        "trigger_to_feedback_p95_ms": _p95(feedback),
        "short_stop_to_paste_p95_ms": _p95(short),
        "medium_stop_to_paste_p95_ms": _p95(medium),
        "two_minute_stop_to_paste_p95_ms": _p95(two_minute),
        "preview_first_model_delta_p95_ms": _p95(preview_model),
        "preview_first_paint_p95_ms": _p95(preview_paint),
        "preview_update_gap_p95_ms": _p95(preview_gap),
        "preview_model_update_gap_p95_ms": _p95(preview_model_gap),
        "preview_active_speech_update_gap_p95_ms": _p95(preview_active_gap),
        "preview_gap_gate_source": (
            "active_speech" if preview_active_gap else "wall_clock_legacy"
        ),
        "preview_queue_delay_p95_ms": _p95(preview_queue),
        "preview_chunk_chars_p95": _p95(preview_chunks),
        "preview_visible_chunk_chars_p95": _p95(preview_visible_chunks),
        "preview_model_delta_chars_p95": _p95(preview_model_chunks),
        "feedback_samples": len(feedback),
        "short_samples": len(short),
        "medium_samples": len(medium),
        "two_minute_samples": len(two_minute),
        "preview_samples": len(preview_paint),
    }
    failures = []
    for key, count in (
        ("feedback", len(feedback)),
        ("short", len(short)),
        ("medium", len(medium)),
        ("two_minute", len(two_minute)),
        ("preview", len(preview_paint)),
    ):
        if count < minimum_samples:
            failures.append(f"{key}: requires {minimum_samples} samples, found {count}")
    if metrics["trigger_to_feedback_p95_ms"] is not None and metrics["trigger_to_feedback_p95_ms"] > 50:
        failures.append("trigger-to-feedback P95 exceeds 50 ms")
    if metrics["short_stop_to_paste_p95_ms"] is not None and metrics["short_stop_to_paste_p95_ms"] > 500:
        failures.append("0-10 second stop-to-paste P95 exceeds 500 ms")
    if metrics["medium_stop_to_paste_p95_ms"] is not None and metrics["medium_stop_to_paste_p95_ms"] > 700:
        failures.append("10-60 second stop-to-paste P95 exceeds 700 ms")
    if metrics["two_minute_stop_to_paste_p95_ms"] is not None and metrics["two_minute_stop_to_paste_p95_ms"] > 2500:
        failures.append("two-minute stop-to-paste P95 exceeds 2.5 seconds")
    if metrics["preview_first_model_delta_p95_ms"] is not None and metrics["preview_first_model_delta_p95_ms"] > 1300:
        failures.append("preview first model delta P95 exceeds 1.3 seconds")
    if metrics["preview_first_paint_p95_ms"] is not None and metrics["preview_first_paint_p95_ms"] > 1300:
        failures.append("preview first paint P95 exceeds 1.3 seconds")
    if metrics["preview_model_update_gap_p95_ms"] is not None and metrics["preview_model_update_gap_p95_ms"] > 1300:
        failures.append("preview model update gap P95 exceeds 1.3 seconds")
    gated_preview_gap = (
        metrics["preview_active_speech_update_gap_p95_ms"]
        if preview_active_gap
        else metrics["preview_update_gap_p95_ms"]
    )
    if not preview_model_gap and gated_preview_gap is not None and gated_preview_gap > 1300:
        label = "preview active-speech update gap" if preview_active_gap else "preview update gap"
        failures.append(f"{label} P95 exceeds 1.3 seconds")
    if metrics["preview_queue_delay_p95_ms"] is not None and metrics["preview_queue_delay_p95_ms"] > 350:
        failures.append("preview queue delay P95 exceeds 350 ms")
    if preview_visible_chunks:
        if metrics["preview_visible_chunk_chars_p95"] > 1:
            failures.append("preview visible paint exceeds one character")
        if max(preview_visible_chunks) > 1:
            failures.append("preview visible paint hard limit exceeds one character")
    elif metrics["preview_chunk_chars_p95"] is not None and metrics["preview_chunk_chars_p95"] > 12:
        failures.append("legacy preview model chunk P95 exceeds 12 characters")
    if preview_model_chunks and metrics["preview_model_delta_chars_p95"] > 12:
        failures.append("preview model delta P95 exceeds 12 characters")
    if preview_model_chunk_max and max(preview_model_chunk_max) > 16:
        failures.append("preview model delta hard limit exceeds 16 characters")
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
