"""VoiceFlow Model Lab metrics, scoring, and hard promotion gates."""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Iterable


WEIGHTS = {
    "clean_cer": 35.0,
    "term_hit_rate": 20.0,
    "reliability": 10.0,
    "latency": 15.0,
    "tail_completeness": 10.0,
    "resources": 10.0,
}


def normalize_text(value: str) -> str:
    return "".join(
        char.casefold()
        for char in str(value or "")
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def character_error_rate(reference: str, hypothesis: str) -> float | None:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        return None
    previous = list(range(len(hyp) + 1))
    for row, ref_char in enumerate(ref, start=1):
        current = [row]
        for column, hyp_char in enumerate(hyp, start=1):
            cost = 0 if ref_char == hyp_char else 1
            current.append(min(
                previous[column] + 1,
                current[column - 1] + 1,
                previous[column - 1] + cost,
            ))
        previous = current
    return previous[-1] / len(ref)


def percentile(values: Iterable[float], percentile_value: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = max(1, math.ceil((percentile_value / 100.0) * len(ordered)))
    return ordered[rank - 1]


def summarize_results(
    model_id: str,
    rows: list[dict[str, Any]],
    *,
    load_ms: float,
    peak_memory_bytes: int,
    offline: bool,
    package_ready: bool,
    stability_cycles: int,
    stability_failures: int,
) -> dict[str, Any]:
    cer_values = [row["clean_cer"] for row in rows if row.get("clean_cer") is not None]
    term_hits = sum(int(row.get("term_hits", 0)) for row in rows)
    term_total = sum(int(row.get("term_total", 0)) for row in rows)
    error_count = sum(
        bool(row.get("blank_error"))
        or bool(row.get("hallucination"))
        or bool(row.get("digit_error"))
        for row in rows
    )
    long_rows = [row for row in rows if row.get("is_long_tail")]
    short_latencies = [
        row["stop_to_ready_ms"]
        for row in rows
        if float(row.get("duration_seconds", 0)) <= 20
    ]
    two_minute_latencies = [
        row["stop_to_ready_ms"]
        for row in rows
        if 110 <= float(row.get("duration_seconds", 0)) <= 150
    ]
    single_character_losses = sum(
        len(normalize_text(row.get("reference", ""))) == 1
        and not normalize_text(row.get("clean_text", ""))
        for row in rows
    )

    summary = {
        "model_id": model_id,
        "sample_count": len(rows),
        "clean_cer": round(sum(cer_values) / len(cer_values), 6) if cer_values else None,
        "term_hit_rate": round(term_hits / term_total, 6) if term_total else None,
        "reliability_rate": round(1 - (error_count / len(rows)), 6) if rows else None,
        "tail_completeness": (
            round(sum(bool(row.get("tail_complete")) for row in long_rows) / len(long_rows), 6)
            if long_rows else None
        ),
        "short_latency_p95_ms": percentile(short_latencies, 95),
        "two_minute_latency_p95_ms": percentile(two_minute_latencies, 95),
        "single_character_losses": single_character_losses,
        "load_ms": round(float(load_ms), 3),
        "peak_memory_bytes": int(peak_memory_bytes),
        "offline": bool(offline),
        "package_ready": bool(package_ready),
        "stability_cycles": int(stability_cycles),
        "stability_failures": int(stability_failures),
    }
    summary["score"] = score_summary(summary)
    return summary


def score_summary(summary: dict[str, Any]) -> float:
    clean_cer = summary.get("clean_cer")
    term_hit_rate = summary.get("term_hit_rate")
    reliability = summary.get("reliability_rate")
    tail = summary.get("tail_completeness")
    short_latency = summary.get("short_latency_p95_ms")
    long_latency = summary.get("two_minute_latency_p95_ms")
    peak_memory = int(summary.get("peak_memory_bytes", 0))

    cer_score = max(0.0, 1.0 - float(clean_cer)) if clean_cer is not None else 0.0
    term_score = float(term_hit_rate) if term_hit_rate is not None else 0.0
    reliability_score = float(reliability) if reliability is not None else 0.0
    tail_score = float(tail) if tail is not None else 0.0
    latency_parts = []
    if short_latency is not None:
        latency_parts.append(min(1.0, 700.0 / max(1.0, float(short_latency))))
    if long_latency is not None:
        latency_parts.append(min(1.0, 2500.0 / max(1.0, float(long_latency))))
    latency_score = sum(latency_parts) / len(latency_parts) if latency_parts else 0.0
    memory_score = min(1.0, 2_500_000_000 / max(1, peak_memory)) if peak_memory else 0.0
    resource_score = memory_score if summary.get("package_ready") and summary.get("offline") else 0.0

    score = (
        WEIGHTS["clean_cer"] * cer_score
        + WEIGHTS["term_hit_rate"] * term_score
        + WEIGHTS["reliability"] * reliability_score
        + WEIGHTS["latency"] * latency_score
        + WEIGHTS["tail_completeness"] * tail_score
        + WEIGHTS["resources"] * resource_score
    )
    return round(score, 3)


def evaluate_hard_gates(
    summary: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []

    def reject(code: str, detail: str) -> None:
        reasons.append({"code": code, "detail": detail})

    tail = summary.get("tail_completeness")
    if tail is not None and float(tail) < 1.0:
        reject("tail_incomplete", "long-recording tail completeness must be 100%")
    if int(summary.get("single_character_losses", 0)):
        reject("single_character_loss", "non-empty single-character output was lost")
    short_latency = summary.get("short_latency_p95_ms")
    if short_latency is not None and float(short_latency) > 700:
        reject("short_latency", "under-20-second P95 exceeds 700 ms")
    long_latency = summary.get("two_minute_latency_p95_ms")
    if long_latency is not None and float(long_latency) > 2500:
        reject("two_minute_latency", "two-minute P95 exceeds 2.5 seconds")
    if int(summary.get("stability_cycles", 0)) < 500:
        reject("stability_coverage", "fewer than 500 start/stop cycles were tested")
    if int(summary.get("stability_failures", 0)):
        reject("stability_failure", "start/stop stability failures were observed")
    if not summary.get("offline"):
        reject("network_dependency", "runtime requires network access")
    if not summary.get("package_ready"):
        reject("package_unready", "engine cannot be packaged reliably")
    if int(summary.get("peak_memory_bytes", 0)) > 2_500_000_000:
        reject("memory_limit", "peak process memory exceeds 2.5 GB")

    for key, label in (
        ("clean_cer", "CER references"),
        ("term_hit_rate", "term annotations"),
        ("tail_completeness", "long-tail samples"),
        ("short_latency_p95_ms", "short latency samples"),
        ("two_minute_latency_p95_ms", "two-minute latency samples"),
    ):
        if summary.get(key) is None:
            reject("insufficient_coverage", f"missing {label}")

    if baseline is not None:
        baseline_cer = baseline.get("clean_cer")
        challenger_cer = summary.get("clean_cer")
        baseline_terms = baseline.get("term_hit_rate")
        challenger_terms = summary.get("term_hit_rate")
        if None not in (baseline_cer, challenger_cer, baseline_terms, challenger_terms):
            cer_gain = (
                (float(baseline_cer) - float(challenger_cer)) / float(baseline_cer)
                if float(baseline_cer) > 0 else 0.0
            )
            term_gain = float(challenger_terms) - float(baseline_terms)
            if cer_gain < 0.15 and term_gain < 0.10:
                reject(
                    "insufficient_accuracy_gain",
                    "challenger improves neither CER by 15% nor term hits by 10 points",
                )

    return {"passed": not reasons, "reasons": reasons}


def select_winner(summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    passing = [item for item in summaries if item.get("hard_gate", {}).get("passed")]
    if not passing:
        return None
    return max(passing, key=lambda item: float(item.get("score", 0)))
