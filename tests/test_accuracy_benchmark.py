import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_manifest_samples_keep_terms(tmp_path):
    import benchmark_models

    wav = tmp_path / "ai_terms.wav"
    wav.write_bytes(b"")
    manifest = tmp_path / "local.jsonl"
    manifest.write_text(
        '{"id":"ai_terms_001","audio":"ai_terms.wav","reference":"我用 Cursor 和 Codex","terms":["Cursor","Codex","Qwen"]}\n',
        encoding="utf-8",
    )

    samples = benchmark_models._eval_samples(manifest)

    assert samples == [
        {
            "id": "ai_terms_001",
            "audio": wav,
            "reference": "我用 Cursor 和 Codex",
            "terms": ["Cursor", "Codex", "Qwen"],
        }
    ]


def test_term_stats_reports_hits_and_missed_terms():
    import benchmark_models

    count, hits, missed = benchmark_models._term_stats(
        "我用 Cursor 调试 Qwen",
        ["Cursor", "Codex", "Qwen"],
    )

    assert count == 2
    assert hits == ["Cursor", "Qwen"]
    assert missed == ["Codex"]


def test_clean_cer_can_improve_over_raw_cer():
    import benchmark_models

    raw = benchmark_models._char_error_rate("我用Cursor", "我用科瑟")
    clean = benchmark_models._char_error_rate("我用Cursor", "我用Cursor")

    assert raw > 0
    assert clean == 0
