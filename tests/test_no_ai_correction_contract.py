from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_llm_correction_runtime_modules_remain():
    assert not (ROOT / "src" / "correction_engine.py").exists()
    assert not (ROOT / "src" / "realtime_correction.py").exists()


def test_main_runtime_has_no_llm_correction_path():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    forbidden = [
        "CorrectionRequest",
        "build_correction_engine",
        "correct_with_timeout",
        "RealtimeCorrectionScheduler",
        "_request_stream_correction",
        "_on_stream_correction",
        "_correct_final_text",
    ]
    for token in forbidden:
        assert token not in main


def test_config_and_docs_do_not_advertise_llm_correction():
    paths = [
        ROOT / "config.yaml",
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "DESIGN.md",
    ]
    forbidden = [
        "correction:",
        "AI 校对",
        "Ollama",
        "qwen3.5",
        "correction_engine.py",
        "realtime_correction.py",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token!r} should not appear in {path.name}"
