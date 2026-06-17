from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_sensevoice_download_contract_matches_active_config():
    from scripts import download_models

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sensevoice = config["engine"]["sensevoice"]

    assert Path(sensevoice["model_path"]).name in download_models.SENSEVOICE_REQUIRED_FILES
    assert Path(sensevoice["tokens_path"]).name in download_models.SENSEVOICE_REQUIRED_FILES
    assert "model.onnx" not in download_models.SENSEVOICE_REQUIRED_FILES


def test_download_skip_requires_all_expected_files(tmp_path):
    from scripts import download_models

    target_dir = tmp_path / "models" / "sensevoice"
    target_dir.mkdir(parents=True)
    (target_dir / "model.int8.onnx").write_text("model", encoding="utf-8")

    assert download_models._has_required_files(str(target_dir), download_models.SENSEVOICE_REQUIRED_FILES) is False

    (target_dir / "tokens.txt").write_text("tokens", encoding="utf-8")

    assert download_models._has_required_files(str(target_dir), download_models.SENSEVOICE_REQUIRED_FILES) is True


def test_transcriber_reports_missing_tokens_before_loading_sherpa(tmp_path):
    from transcriber import Transcriber

    model_path = tmp_path / "models" / "sensevoice" / "model.int8.onnx"
    model_path.parent.mkdir(parents=True)
    model_path.write_text("model", encoding="utf-8")
    config = {
        "engine": {
            "active": "sensevoice",
            "sensevoice": {
                "model_path": "models/sensevoice/model.int8.onnx",
                "tokens_path": "models/sensevoice/tokens.txt",
                "language": "zh",
                "use_itn": True,
                "provider": "cpu",
                "num_threads": 1,
            },
        }
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    transcriber = Transcriber(str(config_path))

    with pytest.raises(FileNotFoundError, match="tokens 文件不存在"):
        transcriber.load_engine()
