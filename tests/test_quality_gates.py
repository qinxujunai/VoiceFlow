from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_stability_gate_completes_500_cycles():
    import stability_gate

    result = stability_gate.run_cycles(500)

    assert result["passed"] is True
    assert result["completed_cycles"] == 500
    assert result["final_state"] == "idle"


def test_performance_gate_enforces_p95_and_sample_coverage(tmp_path):
    import performance_gate

    history = tmp_path / "history.jsonl"
    rows = []
    for _ in range(20):
        rows.append({
            "duration": 10,
            "trigger_to_feedback_ms": 80,
            "stop_to_paste_ms": 650,
            "preview_first_model_delta_ms": 700,
            "preview_first_paint_ms": 780,
            "preview_update_gap_ms": 420,
            "preview_queue_delay_ms": 80,
            "preview_max_chunk_chars": 2,
        })
        rows.append({
            "duration": 120,
            "trigger_to_feedback_ms": 90,
            "stop_to_paste_ms": 2400,
        })
    history.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = performance_gate.analyze_history(history, minimum_samples=20)

    assert result["passed"] is True
    assert result["metrics"]["trigger_to_feedback_p95_ms"] == 90


def test_performance_gate_rejects_missing_release_evidence(tmp_path):
    import performance_gate

    result = performance_gate.analyze_history(tmp_path / "missing.jsonl", minimum_samples=20)

    assert result["passed"] is False
    assert len(result["failures"]) == 4


def test_performance_gate_prefers_explicit_reproducible_evidence(tmp_path):
    import json
    import performance_gate

    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps(
            {
                "trigger_to_feedback_ms": 500,
                "stop_to_paste_ms": 5000,
                "duration": 120,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.jsonl"
    rows = []
    for _ in range(20):
        rows.extend(
            (
                {"trigger_to_feedback_ms": 50},
                {
                    "stop_to_paste_ms": 500,
                    "duration": 10,
                    "preview_first_model_delta_ms": 700,
                    "preview_first_paint_ms": 780,
                    "preview_update_gap_ms": 420,
                    "preview_queue_delay_ms": 80,
                    "preview_max_chunk_chars": 2,
                },
                {"stop_to_paste_ms": 2200, "duration": 120},
            )
        )
    evidence.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = performance_gate.analyze_history(
        history,
        minimum_samples=20,
        evidence_path=evidence,
    )

    assert result["passed"] is True
    assert result["metrics"]["feedback_samples"] == 20
    assert result["metrics"]["short_samples"] == 20
    assert result["metrics"]["two_minute_samples"] == 20
    assert result["metrics"]["preview_samples"] == 20


def test_performance_gate_rejects_slow_or_chunky_preview(tmp_path):
    import performance_gate

    history = tmp_path / "history.jsonl"
    rows = []
    for _ in range(20):
        rows.append(
            {
                "duration": 10,
                "trigger_to_feedback_ms": 50,
                "stop_to_paste_ms": 500,
                "preview_first_model_delta_ms": 950,
                "preview_first_paint_ms": 1050,
                "preview_update_gap_ms": 600,
                "preview_queue_delay_ms": 300,
                "preview_max_chunk_chars": 5,
            }
        )
        rows.append({"duration": 120, "stop_to_paste_ms": 2200})
    history.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = performance_gate.analyze_history(history, minimum_samples=20)

    assert result["passed"] is False
    assert any("preview first paint" in item for item in result["failures"])
    assert any("preview update gap" in item for item in result["failures"])
    assert any("preview chunk" in item for item in result["failures"])
