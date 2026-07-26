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


def test_pathological_output_rejects_repetition_and_impossible_text_rate():
    import benchmark_models

    assert benchmark_models._pathological_output_reason(
        "together. " + ("0" * 300),
        duration=4.6,
    )
    assert benchmark_models._pathological_output_reason(
        "hello " * 12,
        duration=3.0,
    )
    assert benchmark_models._pathological_output_reason(
        "这是正常语句但是长度与极短音频明显不匹配",
        duration=0.1,
    )


def test_pathological_output_accepts_normal_multilingual_transcription():
    import benchmark_models

    assert benchmark_models._pathological_output_reason(
        "开放时间早上九点至下午五点。",
        duration=5.7,
    ) is None
    assert benchmark_models._pathological_output_reason(
        "The tribal chieftain presented him with fifty pieces of gold.",
        duration=7.2,
    ) is None


def test_transcriber_reads_provider_and_thread_settings_from_config():
    adapter = (ROOT / "src" / "engine_adapter.py").read_text(encoding="utf-8")
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")

    assert 'self.config.get("provider", "cpu")' in adapter
    assert 'self.config.get("num_threads", 6)' in adapter
    assert 'provider: "cpu"' in config
    assert "num_threads: 6" in config
