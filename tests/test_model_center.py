from __future__ import annotations

import json
import hashlib
import sys
import threading
import types
from pathlib import Path

import yaml
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_user_catalog_is_small_honest_and_evidence_backed():
    from model_catalog import user_model_profiles

    profiles = user_model_profiles()

    assert [profile.engine for profile in profiles] == ["sensevoice", "qwen3-asr"]
    assert profiles[0].recommended is True
    assert profiles[1].recommended is False
    assert profiles[1].availability == "lab"
    assert "小样本" in profiles[1].evidence_note
    assert profiles[0].download_bytes == 240500355
    assert profiles[1].download_bytes == 987015347
    assert profiles[0].short_p95_ms < profiles[1].short_p95_ms
    assert profiles[0].peak_memory_mb < profiles[1].peak_memory_mb


def test_model_status_distinguishes_missing_ready_and_corrupt(tmp_path):
    from model_catalog import profile_for_engine
    from runtime_paths import AppPaths, RuntimeMode
    from runtime_services import ModelManager, ModelState

    install = tmp_path / "install"
    data = tmp_path / "data"
    install.mkdir()
    data.mkdir()
    manifest = {
        "schema_version": 1,
        "models": {
            "sensevoice-small-int8": {
                "target_dir": "models/sensevoice",
                "files": [
                    {"path": "model.int8.onnx", "size": 3, "sha256": "0" * 64},
                    {"path": "tokens.txt", "size": 3, "sha256": "0" * 64},
                ],
            }
        },
    }
    (install / "model-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    config = {
        "engine": {
            "active": "sensevoice",
            "sensevoice": {
                "model_path": "models/sensevoice/model.int8.onnx",
                "tokens_path": "models/sensevoice/tokens.txt",
            },
        }
    }
    paths = AppPaths(
        mode=RuntimeMode.SOURCE,
        install_dir=install,
        data_dir=data,
        executable=Path(sys.executable),
    )
    manager = ModelManager(paths)

    assert manager.status("sensevoice", config).state is ModelState.MISSING
    target = data / profile_for_engine("sensevoice").target_dir
    target.mkdir(parents=True)
    (target / "model.int8.onnx").write_bytes(b"bad")
    (target / "tokens.txt").write_bytes(b"bad")
    assert manager.status("sensevoice", config, verify=True).state is ModelState.CORRUPT


def test_model_switch_is_staged_and_can_roll_back_exact_config(tmp_path):
    from model_switch import ModelSwitchCoordinator

    config_path = tmp_path / "config.yaml"
    original = {
        "engine": {
            "active": "sensevoice",
            "sensevoice": {"language": "zh"},
            "qwen3-asr": {"language": "auto"},
        },
        "audio": {"device_index": None},
    }
    config_path.write_text(yaml.safe_dump(original, allow_unicode=True), encoding="utf-8")
    switch = ModelSwitchCoordinator(tmp_path / "model-switch", config_path)

    switch.stage(
        engine="qwen3-asr",
        apply=lambda: config_path.write_text(
            yaml.safe_dump(
                {
                    **original,
                    "engine": {**original["engine"], "active": "qwen3-asr"},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        ),
    )

    assert switch.pending()["candidate_engine"] == "qwen3-asr"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["engine"]["active"] == "qwen3-asr"

    previous = switch.rollback("candidate failed to load")

    assert previous == "sensevoice"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
    assert switch.pending() is None


def test_model_switch_commit_removes_recovery_assets(tmp_path):
    from model_switch import ModelSwitchCoordinator

    config_path = tmp_path / "config.yaml"
    config_path.write_text("engine:\n  active: sensevoice\n", encoding="utf-8")
    switch = ModelSwitchCoordinator(tmp_path / "model-switch", config_path)
    switch.stage(engine="qwen3-asr", apply=lambda: None)

    switch.commit("qwen3-asr")

    assert switch.pending() is None
    assert not switch.backup_path.exists()


def test_model_download_progress_is_bounded(tmp_path):
    from runtime_services import downloaded_model_bytes

    partial = tmp_path / "models" / "qwen3-asr.partial"
    partial.mkdir(parents=True)
    (partial / "weights.part").write_bytes(b"x" * 64)

    assert downloaded_model_bytes(tmp_path, "models/qwen3-asr") == 64


def test_in_app_downloader_verifies_and_atomically_activates_huggingface_asset(
    tmp_path,
    monkeypatch,
):
    from model_downloader import PinnedModelDownloader
    from runtime_paths import AppPaths, RuntimeMode

    install = tmp_path / "install"
    data = tmp_path / "data"
    install.mkdir()
    data.mkdir()
    payload = b"voiceflow-model"
    manifest = {
        "schema_version": 1,
        "models": {
            "sensevoice-small-int8": {
                "target_dir": "models/sensevoice",
                "source": {
                    "provider": "huggingface",
                    "repo_id": "owner/model",
                    "revision": "a" * 40,
                },
                "files": [
                    {
                        "path": "model.int8.onnx",
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        },
    }
    (install / "model-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    paths = AppPaths(RuntimeMode.FROZEN, install, data, Path(sys.executable))
    progress = []

    class Response:
        status = 200

        def __init__(self):
            self._sent = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            if self._sent:
                return b""
            self._sent = True
            return payload

    opener = types.SimpleNamespace(open=lambda *_a, **_k: Response())
    monkeypatch.setattr(
        "model_downloader.urllib.request.build_opener",
        lambda *_handlers: opener,
    )
    downloader = PinnedModelDownloader(
        paths,
        cancelled=threading.Event(),
        on_progress=lambda percent, detail: progress.append((percent, detail)),
    )

    target = downloader.download("sensevoice")

    assert (target / "model.int8.onnx").read_bytes() == payload
    assert not target.with_name("sensevoice.partial").exists()
    assert progress[-1][0] == 100


def test_model_downloader_rejects_path_traversal_and_untrusted_hosts():
    from model_downloader import _safe_relative_path, _validate_download_url

    with pytest.raises(RuntimeError, match="unsafe"):
        _safe_relative_path("../../outside.onnx")
    with pytest.raises(RuntimeError, match="allowlisted"):
        _validate_download_url("http://127.0.0.1/model.onnx")
    with pytest.raises(RuntimeError, match="allowlisted"):
        _validate_download_url("https://example.com/model.onnx")
