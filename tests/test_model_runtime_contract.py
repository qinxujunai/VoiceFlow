from __future__ import annotations

import sys
import types
import hashlib
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


def test_qwen_download_contract_uses_real_sherpa_asset_layout():
    from scripts import download_models

    assert download_models.QWEN3_ASR_REQUIRED_FILES == (
        "conv_frontend.onnx",
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "tokenizer",
    )


def test_engine_capabilities_are_explicit_and_offline():
    from engine_adapter import create_engine_adapter

    sensevoice = create_engine_adapter("sensevoice", {}, ROOT)
    qwen = create_engine_adapter("qwen3-asr", {}, ROOT)
    fun_asr = create_engine_adapter("fun-asr-nano", {}, ROOT)

    assert sensevoice.capabilities.offline is True
    assert sensevoice.capabilities.supports_hotwords is False
    assert qwen.capabilities.offline is True
    assert qwen.capabilities.supports_hotwords is True
    assert fun_asr.capabilities.supports_hotwords is True


def test_funasr_adapter_passes_quantized_assets_to_sherpa(tmp_path, monkeypatch):
    from transcriber import Transcriber

    model_dir = tmp_path / "models" / "fun-asr-nano"
    tokenizer = model_dir / "Qwen3-0.6B"
    tokenizer.mkdir(parents=True)
    for filename in ("encoder_adaptor.int8.onnx", "llm.int8.onnx", "embedding.int8.onnx"):
        (model_dir / filename).write_text(filename, encoding="utf-8")
    captured = {}

    class FakeRecognizer:
        @classmethod
        def from_funasr_nano(cls, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(OfflineRecognizer=FakeRecognizer),
    )
    config = {
        "engine": {
            "active": "fun-asr-nano",
            "fun-asr-nano": {
                "encoder_adaptor_path": "models/fun-asr-nano/encoder_adaptor.int8.onnx",
                "llm_path": "models/fun-asr-nano/llm.int8.onnx",
                "embedding_path": "models/fun-asr-nano/embedding.int8.onnx",
                "tokenizer_path": "models/fun-asr-nano/Qwen3-0.6B",
                "provider": "cpu",
                "num_threads": 3,
                "language": "zh",
                "hotwords": "VoiceFlow",
            },
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    transcriber = Transcriber(str(config_path))
    transcriber.load_engine()

    assert captured["encoder_adaptor"] == str(model_dir / "encoder_adaptor.int8.onnx")
    assert captured["llm"] == str(model_dir / "llm.int8.onnx")
    assert captured["embedding"] == str(model_dir / "embedding.int8.onnx")
    assert captured["tokenizer"] == str(tokenizer)
    assert captured["language"] == "zh"
    assert captured["hotwords"] == "VoiceFlow"


def test_qwen_adapter_passes_all_required_assets_to_sherpa(tmp_path, monkeypatch):
    from transcriber import Transcriber

    qwen_dir = tmp_path / "models" / "qwen3-asr"
    tokenizer = qwen_dir / "tokenizer"
    tokenizer.mkdir(parents=True)
    for filename in ("conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx"):
        (qwen_dir / filename).write_text(filename, encoding="utf-8")

    captured = {}

    class FakeRecognizer:
        @classmethod
        def from_qwen3_asr(cls, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(OfflineRecognizer=FakeRecognizer),
    )
    config = {
        "engine": {
            "active": "qwen3-asr",
            "qwen3-asr": {
                "conv_frontend_path": "models/qwen3-asr/conv_frontend.onnx",
                "encoder_path": "models/qwen3-asr/encoder.int8.onnx",
                "decoder_path": "models/qwen3-asr/decoder.int8.onnx",
                "tokenizer_path": "models/qwen3-asr/tokenizer",
                "provider": "cpu",
                "num_threads": 4,
                "hotwords": "VoiceFlow Qwen",
            },
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    transcriber = Transcriber(str(config_path))
    transcriber.load_engine()

    assert captured["conv_frontend"] == str(qwen_dir / "conv_frontend.onnx")
    assert captured["encoder"] == str(qwen_dir / "encoder.int8.onnx")
    assert captured["decoder"] == str(qwen_dir / "decoder.int8.onnx")
    assert captured["tokenizer"] == str(tokenizer)
    assert captured["hotwords"] == "VoiceFlow Qwen"
    assert captured["num_threads"] == 4


def test_qwen_config_does_not_use_legacy_model_and_tokens_fields():
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    qwen = config["engine"]["qwen3-asr"]

    assert "model_path" not in qwen
    assert "tokens_path" not in qwen
    assert set((
        "conv_frontend_path",
        "encoder_path",
        "decoder_path",
        "tokenizer_path",
    )).issubset(qwen)


def test_model_manifest_pins_revision_license_size_and_sha256():
    from model_registry import load_model_manifest

    manifest = load_model_manifest(ROOT / "model-manifest.json")

    for model_id in (
        "sensevoice-small-int8",
        "qwen3-asr-0.6b-int8",
        "fun-asr-nano-0.8b-int8",
    ):
        model = manifest["models"][model_id]
        assert len(model["source"]["revision"]) == 40
        assert model["license"]["spdx"]
        assert model["download_bytes"] > 0
        for asset in model["files"]:
            assert asset["size"] > 0
            assert len(asset["sha256"]) == 64


def test_model_manifest_contains_all_fixed_lab_candidates():
    from model_registry import load_model_manifest

    models = load_model_manifest(ROOT / "model-manifest.json")["models"]

    assert set(models) == {
        "sensevoice-small-int8",
        "qwen3-asr-0.6b-int8",
        "fun-asr-nano-0.8b-int8",
        "qwen3-asr-1.7b-conditional",
        "whisper-large-v3-turbo-int8",
    }
    assert models["qwen3-asr-1.7b-conditional"]["eligible"] is False
    assert models["whisper-large-v3-turbo-int8"]["license"]["spdx"] == "MIT"


def test_whisper_adapter_uses_int8_encoder_decoder_and_tokens(tmp_path, monkeypatch):
    from transcriber import Transcriber

    model_dir = tmp_path / "models" / "whisper-turbo"
    model_dir.mkdir(parents=True)
    for filename in ("turbo-encoder.int8.onnx", "turbo-decoder.int8.onnx", "turbo-tokens.txt"):
        (model_dir / filename).write_text(filename, encoding="utf-8")
    captured = {}

    class FakeRecognizer:
        @classmethod
        def from_whisper(cls, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(OfflineRecognizer=FakeRecognizer),
    )
    config = {
        "engine": {
            "active": "whisper-turbo",
            "whisper-turbo": {
                "encoder_path": "models/whisper-turbo/turbo-encoder.int8.onnx",
                "decoder_path": "models/whisper-turbo/turbo-decoder.int8.onnx",
                "tokens_path": "models/whisper-turbo/turbo-tokens.txt",
                "language": "zh",
                "provider": "cpu",
                "num_threads": 2,
            },
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    transcriber = Transcriber(str(config_path))
    transcriber.load_engine()

    assert captured["encoder"] == str(model_dir / "turbo-encoder.int8.onnx")
    assert captured["decoder"] == str(model_dir / "turbo-decoder.int8.onnx")
    assert captured["tokens"] == str(model_dir / "turbo-tokens.txt")
    assert captured["language"] == "zh"


def test_asset_verification_detects_corruption(tmp_path):
    from model_registry import verify_model_assets

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    payload = b"voiceflow-model"
    (model_dir / "weights.onnx").write_bytes(payload)
    model = {
        "files": [{
            "path": "weights.onnx",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }],
    }

    assert verify_model_assets(model_dir, model) == []

    (model_dir / "weights.onnx").write_bytes(b"corrupt")

    errors = verify_model_assets(model_dir, model)
    assert errors
    assert "size mismatch" in errors[0]


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
