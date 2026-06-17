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
    assert checks["num_threads"]["detail"] == "6"


def test_doctor_reports_missing_active_model(tmp_path):
    from scripts import doctor

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config["engine"]["sensevoice"]["model_path"] = "models/sensevoice/missing.onnx"
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    result = doctor.run_doctor(tmp_path)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["ok"] is False
    assert checks["model_path"]["status"] == "missing"
