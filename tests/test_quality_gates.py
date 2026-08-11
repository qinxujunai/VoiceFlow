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
            "trigger_to_feedback_ms": 40,
            "stop_to_paste_ms": 450,
            "preview_first_model_delta_ms": 700,
            "preview_first_paint_ms": 780,
            "preview_update_gap_ms": 420,
            "preview_active_speech_update_gap_ms": 390,
            "preview_queue_delay_ms": 80,
            "preview_max_chunk_chars": 2,
        })
        rows.append({
            "duration": 45,
            "stop_to_paste_ms": 650,
        })
        rows.append({
            "duration": 120,
            "trigger_to_feedback_ms": 45,
            "stop_to_paste_ms": 2400,
        })
    history.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = performance_gate.analyze_history(history, minimum_samples=20)

    assert result["passed"] is True
    assert result["metrics"]["trigger_to_feedback_p95_ms"] == 45
    assert result["metrics"]["preview_active_speech_update_gap_p95_ms"] == 390
    assert result["metrics"]["preview_gap_gate_source"] == "active_speech"


def test_performance_gate_rejects_missing_release_evidence(tmp_path):
    import performance_gate

    result = performance_gate.analyze_history(tmp_path / "missing.jsonl", minimum_samples=20)

    assert result["passed"] is False
    assert len(result["failures"]) == 5


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
                    "preview_active_speech_update_gap_ms": 390,
                    "preview_queue_delay_ms": 80,
                    "preview_max_chunk_chars": 2,
                },
                {"stop_to_paste_ms": 650, "duration": 45},
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
    assert result["metrics"]["medium_samples"] == 20
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
                "preview_first_model_delta_ms": 1400,
                "preview_first_paint_ms": 1450,
                "preview_model_update_gap_ms": 1400,
                "preview_queue_delay_ms": 400,
                "preview_visible_chunk_chars": 2,
                "preview_model_delta_chars": 17,
                "preview_model_delta_hard_max_chars": 18,
            }
        )
        rows.append({"duration": 45, "stop_to_paste_ms": 650})
        rows.append({"duration": 120, "stop_to_paste_ms": 2200})
    history.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = performance_gate.analyze_history(history, minimum_samples=20)

    assert result["passed"] is False
    assert any("preview first paint" in item for item in result["failures"])
    assert any("preview model update gap" in item for item in result["failures"])
    assert any("visible paint" in item for item in result["failures"])
    assert any("model delta" in item for item in result["failures"])


def test_pipeline_evidence_covers_short_medium_and_two_minute_buckets():
    source = (ROOT / "scripts" / "measure_pipeline_performance.py").read_text(
        encoding="utf-8"
    )

    assert 'parser.add_argument("--medium-seconds", type=int, default=45)' in source
    assert "args.medium_seconds" in source
    assert "start_target = output.capture_target()" in source
    assert "output.deliver(" in source
    assert "start_target=start_target" in source


def test_preview_evidence_keeps_model_batches_separate_from_visible_paint():
    import measure_pipeline_performance

    row = measure_pipeline_performance._preview_evidence_row(
        {
            "first_delta_ms": 1025.5,
            "update_gap_p95_ms": 660.0,
            "queue_delay_p95_ms": 48.0,
            "chunk_chars_p95": 2.0,
            "max_chunk_chars": 2,
            "divergence_count": 0,
            "committed_text": "private transcript",
            "preview_text": "private transcript",
        },
        case="zh",
        measured_at="2026-08-11T00:00:00+0800",
    )

    assert row["source"] == "deterministic_streaming_preview"
    assert row["preview_case"] == "zh"
    assert row["preview_first_model_delta_ms"] == 1025.5
    assert row["preview_first_paint_ms"] == 1073.5
    assert row["preview_model_update_gap_ms"] == 660.0
    assert row["preview_visible_chunk_chars"] == 1
    assert row["preview_model_delta_chars"] == 2.0
    assert "preview_text" not in row
    assert "committed_text" not in row


def test_performance_gate_scores_model_emission_and_visible_cadence_separately(tmp_path):
    import performance_gate

    evidence = tmp_path / "evidence.jsonl"
    rows = []
    for index in range(20):
        rows.extend(
            (
                {"trigger_to_feedback_ms": 40},
                {
                    "duration": 10,
                    "stop_to_paste_ms": 450,
                    "preview_case": "zh" if index % 2 == 0 else "en",
                    "preview_first_model_delta_ms": 1200,
                    "preview_first_paint_ms": 1248,
                    "preview_model_update_gap_ms": 1200,
                    "preview_queue_delay_ms": 300,
                    "preview_visible_chunk_chars": 1,
                    "preview_model_delta_chars": 12,
                },
                {"duration": 45, "stop_to_paste_ms": 650},
                {"duration": 120, "stop_to_paste_ms": 2200},
            )
        )
    evidence.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = performance_gate.analyze_history(evidence, minimum_samples=20)

    assert result["passed"] is True
    assert result["metrics"]["preview_model_update_gap_p95_ms"] == 1200
    assert result["metrics"]["preview_visible_chunk_chars_p95"] == 1
    assert result["metrics"]["preview_model_delta_chars_p95"] == 12
