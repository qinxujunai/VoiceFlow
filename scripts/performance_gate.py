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
    metrics = {
        "trigger_to_feedback_p95_ms": _p95(feedback),
        "short_stop_to_paste_p95_ms": _p95(short),
        "two_minute_stop_to_paste_p95_ms": _p95(two_minute),
        "feedback_samples": len(feedback),
        "short_samples": len(short),
        "two_minute_samples": len(two_minute),
    }
    failures = []
    for key, count in (
        ("feedback", len(feedback)),
        ("short", len(short)),
        ("two_minute", len(two_minute)),
    ):
        if count < minimum_samples:
            failures.append(f"{key}: requires {minimum_samples} samples, found {count}")
    if metrics["trigger_to_feedback_p95_ms"] is not None and metrics["trigger_to_feedback_p95_ms"] >= 100:
        failures.append("trigger-to-feedback P95 must be below 100 ms")
    if metrics["short_stop_to_paste_p95_ms"] is not None and metrics["short_stop_to_paste_p95_ms"] > 700:
        failures.append("short stop-to-paste P95 exceeds 700 ms")
    if metrics["two_minute_stop_to_paste_p95_ms"] is not None and metrics["two_minute_stop_to_paste_p95_ms"] > 2500:
        failures.append("two-minute stop-to-paste P95 exceeds 2.5 seconds")
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
