from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_character_error_rate_ignores_spacing_and_punctuation():
    from model_lab import character_error_rate

    assert character_error_rate("你好，VoiceFlow。", "你好 VoiceFlow") == 0
    assert character_error_rate("打开", "关上") == 1


def test_summary_reports_weighted_product_metrics():
    from model_lab import summarize_results

    rows = [
        {
            "duration_seconds": 10,
            "stop_to_ready_ms": 500,
            "clean_cer": 0.10,
            "term_hits": 2,
            "term_total": 2,
            "blank_error": False,
            "hallucination": False,
            "digit_error": False,
            "is_long_tail": False,
            "tail_complete": True,
        },
        {
            "duration_seconds": 120,
            "stop_to_ready_ms": 1800,
            "clean_cer": 0.20,
            "term_hits": 1,
            "term_total": 2,
            "blank_error": False,
            "hallucination": False,
            "digit_error": True,
            "is_long_tail": True,
            "tail_complete": True,
        },
    ]

    summary = summarize_results(
        "challenger",
        rows,
        load_ms=300,
        peak_memory_bytes=1_000_000_000,
        offline=True,
        package_ready=True,
        stability_cycles=500,
        stability_failures=0,
    )

    assert summary["clean_cer"] == 0.15
    assert summary["term_hit_rate"] == 0.75
    assert summary["tail_completeness"] == 1.0
    assert summary["short_latency_p95_ms"] == 500
    assert summary["two_minute_latency_p95_ms"] == 1800


def test_hard_gates_reject_tail_loss_single_character_loss_and_latency():
    from model_lab import evaluate_hard_gates

    summary = {
        "model_id": "broken",
        "tail_completeness": 0.5,
        "single_character_losses": 1,
        "short_latency_p95_ms": 701,
        "two_minute_latency_p95_ms": 2501,
        "stability_cycles": 500,
        "stability_failures": 0,
        "offline": True,
        "package_ready": True,
        "peak_memory_bytes": 1_000_000_000,
        "clean_cer": 0.1,
        "term_hit_rate": 0.8,
    }

    gate = evaluate_hard_gates(summary)

    assert gate["passed"] is False
    assert {reason["code"] for reason in gate["reasons"]} >= {
        "tail_incomplete",
        "single_character_loss",
        "short_latency",
        "two_minute_latency",
    }


def test_challenger_must_improve_cer_or_terms_before_promotion():
    from model_lab import evaluate_hard_gates

    baseline = {"clean_cer": 0.20, "term_hit_rate": 0.60}
    challenger = {
        "model_id": "challenger",
        "tail_completeness": 1.0,
        "single_character_losses": 0,
        "short_latency_p95_ms": 500,
        "two_minute_latency_p95_ms": 1800,
        "stability_cycles": 500,
        "stability_failures": 0,
        "offline": True,
        "package_ready": True,
        "peak_memory_bytes": 1_000_000_000,
        "clean_cer": 0.19,
        "term_hit_rate": 0.61,
    }

    gate = evaluate_hard_gates(challenger, baseline=baseline)

    assert gate["passed"] is False
    assert "insufficient_accuracy_gain" in {item["code"] for item in gate["reasons"]}


def test_only_passing_highest_score_can_win():
    from model_lab import select_winner

    winner = select_winner([
        {"model_id": "fast", "score": 82.0, "hard_gate": {"passed": True}},
        {"model_id": "accurate-but-broken", "score": 95.0, "hard_gate": {"passed": False}},
        {"model_id": "balanced", "score": 88.0, "hard_gate": {"passed": True}},
    ])

    assert winner["model_id"] == "balanced"


def test_evaluator_accepts_expected_alias_and_relative_audio(tmp_path):
    scripts = ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import evaluate_asr

    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"wav")
    manifest = tmp_path / "samples.jsonl"
    manifest.write_text(
        '{"id":"short","audio":"sample.wav","expected":"开","terms":[]}\n',
        encoding="utf-8",
    )

    samples = evaluate_asr._load_samples(manifest)

    assert samples[0]["reference"] == "开"
    assert samples[0]["audio"] == audio


def test_default_promotion_preserves_config_comments(tmp_path):
    scripts = ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import evaluate_asr

    config = tmp_path / "config.yaml"
    config.write_text(
        '# keep this comment\nengine:\n  active: "sensevoice"\n',
        encoding="utf-8",
    )

    evaluate_asr._promote_engine(config, "qwen3-asr")

    updated = config.read_text(encoding="utf-8")
    assert "# keep this comment" in updated
    assert 'active: "qwen3-asr"' in updated
