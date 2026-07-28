from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_reports_current_runtime_ok():
    from scripts import doctor

    result = doctor.run_doctor(ROOT)

    assert result["ok"] is True
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["active_engine"]["detail"] == "sensevoice"
    assert checks["provider"]["detail"] == "cpu"
    assert checks["num_threads"]["detail"].endswith("(auto)")
    assert checks["preview_model_path"]["status"] == "ok"
    assert checks["preview_tokens_path"]["status"] == "ok"
    assert checks["python_version"]["status"] == "ok"
    assert checks["app_icon"]["status"] == "ok"
    assert checks["silero_vad_model"]["status"] == "ok"
    assert checks["logs_dir"]["status"] == "ok"


def test_doctor_reports_missing_active_model(tmp_path):
    from scripts import doctor

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config["engine"]["sensevoice"]["model_path"] = "models/sensevoice/missing.onnx"
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = doctor.run_doctor(tmp_path)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["ok"] is False
    assert checks["model_path"]["status"] == "missing"


def test_doctor_reports_missing_streaming_preview_model(tmp_path):
    from scripts import doctor

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config["streaming_preview"]["model_path"] = "models/streaming-preview/missing.onnx"
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )

    result = doctor.run_doctor(tmp_path)
    checks = {item["name"]: item for item in result["checks"]}

    assert result["ok"] is False
    assert checks["preview_model_path"]["status"] == "missing"


def test_doctor_treats_intentionally_unbundled_packaged_preview_as_warning(tmp_path):
    from scripts import doctor

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )
    (tmp_path / "VoiceFlow.exe").write_bytes(b"packaged-runtime-marker")

    result = doctor.run_doctor(tmp_path)
    checks = {item["name"]: item for item in result["checks"]}

    assert checks["preview_model_path"]["status"] == "warning"
    assert checks["preview_tokens_path"]["status"] == "warning"
    assert "quiet capsule" in checks["preview_model_path"]["detail"]


def test_doctor_checks_qwen_asset_contract(tmp_path):
    from scripts import doctor

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config["engine"]["active"] = "qwen3-asr"
    qwen_dir = tmp_path / "models" / "qwen3-asr"
    (qwen_dir / "tokenizer").mkdir(parents=True)
    for filename in ("conv_frontend.onnx", "encoder.int8.onnx"):
        (qwen_dir / filename).write_text(filename, encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )

    result = doctor.run_doctor(tmp_path)
    checks = {item["name"]: item for item in result["checks"]}

    assert result["ok"] is False
    assert checks["decoder_path"]["status"] == "missing"
    assert checks["tokenizer_path"]["status"] == "ok"


def test_doctor_treats_missing_shortcut_as_warning(monkeypatch, tmp_path):
    from scripts import doctor

    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    result = doctor.run_doctor(ROOT)
    checks = {item["name"]: item for item in result["checks"]}

    assert checks["desktop_shortcut"]["status"] == "warning"
    assert result["ok"] is True
