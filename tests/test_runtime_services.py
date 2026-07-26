from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _paths(tmp_path, mode):
    from runtime_paths import AppPaths

    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    install_dir.mkdir()
    data_dir.mkdir()
    return AppPaths(
        mode=mode,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=install_dir / "VoiceFlow.exe",
    )


def test_model_manager_uses_user_first_install_fallback_asset_resolution(tmp_path):
    from runtime_paths import RuntimeMode
    from runtime_services import ModelManager, ModelState

    paths = _paths(tmp_path, RuntimeMode.FROZEN)
    model = paths.install_dir / "models" / "sensevoice" / "model.int8.onnx"
    tokens = paths.install_dir / "models" / "sensevoice" / "tokens.txt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    tokens.write_text("tokens", encoding="utf-8")
    config = {
        "engine": {
            "active": "sensevoice",
            "sensevoice": {
                "model_path": "models/sensevoice/model.int8.onnx",
                "tokens_path": "models/sensevoice/tokens.txt",
            },
        }
    }

    status = ModelManager(paths).status("sensevoice", config)

    assert status.state is ModelState.READY
    assert status.missing == ()


def test_frozen_model_choices_hide_unavailable_experimental_engines(tmp_path):
    from runtime_paths import RuntimeMode
    from runtime_services import ModelManager

    paths = _paths(tmp_path, RuntimeMode.FROZEN)
    model_dir = paths.install_dir / "models" / "sensevoice"
    model_dir.mkdir(parents=True)
    (model_dir / "model.int8.onnx").write_bytes(b"model")
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    config = {
        "engine": {
            "active": "sensevoice",
            "sensevoice": {
                "model_path": "models/sensevoice/model.int8.onnx",
                "tokens_path": "models/sensevoice/tokens.txt",
            },
            "qwen3-asr": {
                "encoder_path": "models/qwen3-asr/encoder.int8.onnx",
            },
        }
    }

    assert ModelManager(paths).selectable_engines(config) == ("sensevoice",)


def test_source_model_choices_keep_experimental_model_lab_engines(tmp_path):
    from runtime_paths import RuntimeMode
    from runtime_services import ModelManager

    paths = _paths(tmp_path, RuntimeMode.SOURCE)
    config = {
        "engine": {
            "active": "sensevoice",
            "sensevoice": {},
            "qwen3-asr": {},
        }
    }

    assert ModelManager(paths).selectable_engines(config) == (
        "sensevoice",
        "qwen3-asr",
    )


def test_frozen_model_setup_never_launches_source_downloader(tmp_path):
    from runtime_paths import RuntimeMode
    from runtime_services import ModelManager

    paths = _paths(tmp_path, RuntimeMode.FROZEN)
    manager = ModelManager(paths)

    assert manager.setup_command("sensevoice") is None
    assert "重新安装" in manager.open_setup("sensevoice", {})


def test_source_model_setup_writes_to_user_model_directory(tmp_path):
    from runtime_paths import RuntimeMode
    from runtime_services import ModelManager

    paths = _paths(tmp_path, RuntimeMode.SOURCE)
    script = paths.install_dir / "scripts" / "download_models.py"
    script.parent.mkdir()
    script.write_text("# fixture\n", encoding="utf-8")

    command = ModelManager(paths).setup_command("sensevoice")

    assert command is not None
    assert command[-2:] == ("--base-dir", str(paths.data_dir))


def test_source_model_setup_uses_console_python_from_windowed_launcher(tmp_path):
    from runtime_paths import AppPaths, RuntimeMode
    from runtime_services import ModelManager

    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    script = install_dir / "scripts" / "download_models.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fixture\n", encoding="utf-8")
    pythonw = tmp_path / "venv" / "Scripts" / "pythonw.exe"
    pythonw.parent.mkdir(parents=True)
    pythonw.write_bytes(b"")
    python = pythonw.with_name("python.exe")
    python.write_bytes(b"")
    paths = AppPaths(
        mode=RuntimeMode.SOURCE,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=pythonw,
    )

    command = ModelManager(paths).setup_command("sensevoice")

    assert command is not None
    assert command[0] == str(python.resolve())


def test_runtime_diagnostics_work_without_venv_or_maintainer_scripts(tmp_path):
    from runtime_paths import RuntimeMode, prepare_runtime_layout
    from runtime_services import format_diagnostics, run_runtime_diagnostics

    paths = _paths(tmp_path, RuntimeMode.FROZEN)
    (paths.install_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "engine": {
                    "active": "sensevoice",
                    "sensevoice": {
                        "model_path": "models/sensevoice/model.int8.onnx",
                        "tokens_path": "models/sensevoice/tokens.txt",
                    },
                },
                "vad": {
                    "enabled": True,
                    "model_path": "assets/silero_vad.onnx",
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    model_dir = paths.install_dir / "models" / "sensevoice"
    model_dir.mkdir(parents=True)
    (model_dir / "model.int8.onnx").write_bytes(b"model")
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    assets = paths.install_dir / "assets"
    assets.mkdir()
    (assets / "silero_vad.onnx").write_bytes(b"vad")
    prepare_runtime_layout(paths)

    result = run_runtime_diagnostics(paths)
    output = format_diagnostics(result)

    assert result["ok"] is True
    assert "frozen" in output
    assert "venv" not in output
    assert "scripts/doctor.py" not in output
    assert str(tmp_path) not in output
    assert "%VOICEFLOW_DATA%" in output
    assert "%VOICEFLOW_INSTALL%" in output


def test_engine_adapter_searches_user_then_bundled_asset_roots(tmp_path):
    from engine_adapter import EngineAdapter, EngineCapabilities

    class FixtureAdapter(EngineAdapter):
        name = "fixture"
        capabilities = EngineCapabilities(languages=("zh",))

        def load(self):
            return None

    data_dir = tmp_path / "data"
    install_dir = tmp_path / "install"
    bundled = install_dir / "models" / "fixture.onnx"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"bundled")
    adapter = FixtureAdapter(
        {"model_path": "models/fixture.onnx"},
        data_dir,
        asset_roots=(data_dir, install_dir),
    )

    assert adapter._asset("model_path", "模型") == str(bundled)

    user_model = data_dir / "models" / "fixture.onnx"
    user_model.parent.mkdir(parents=True)
    user_model.write_bytes(b"user")

    assert adapter._asset("model_path", "模型") == str(user_model)


def test_voice_input_system_routes_writes_to_user_data_and_assets_to_install(
    tmp_path,
    monkeypatch,
):
    from runtime_paths import AppPaths, RuntimeMode

    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    install_dir.mkdir()
    (install_dir / "knowledge-base").mkdir()
    (install_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "engine": {
                    "active": "sensevoice",
                    "sensevoice": {
                        "model_path": "models/sensevoice/model.int8.onnx",
                        "tokens_path": "models/sensevoice/tokens.txt",
                    },
                },
                "audio": {"sample_rate": 16000},
                "vad": {"enabled": False},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    paths = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=install_dir / "VoiceFlow.exe",
    )

    import main

    captured = {}

    class FakeOverlay:
        def __init__(self, received_paths):
            captured["paths"] = received_paths

    monkeypatch.setattr(main, "OverlayWindow", FakeOverlay)
    system = main.VoiceInputSystem(paths=paths)

    assert system.base_dir == str(data_dir.resolve())
    assert system.config_path == str(paths.config_file)
    assert system.history.path == paths.history_file
    assert captured["paths"] is paths


def test_hotword_loader_uses_writable_config_directory_for_user_vocabulary(tmp_path):
    from hotword_loader import HotwordLoader

    data_dir = tmp_path / "data"
    knowledge_dir = data_dir / "knowledge-base"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "user-dictionary.txt").write_text(
        "VoiceFlowRuntime\n",
        encoding="utf-8",
    )
    config = data_dir / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "hotwords": {
                    "enabled": True,
                    "directory": "knowledge-base",
                    "files": ["user-dictionary.txt"],
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    loader = HotwordLoader(config)

    assert loader.load_all() == ["VoiceFlowRuntime"]
