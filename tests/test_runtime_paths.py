from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_frozen_runtime_separates_install_resources_from_user_data(tmp_path):
    from runtime_paths import AppPaths, RuntimeMode

    install_dir = tmp_path / "Program Files" / "VoiceFlow"
    local_app_data = tmp_path / "LocalAppData"
    executable = install_dir / "VoiceFlow.exe"

    paths = AppPaths.discover(
        frozen=True,
        install_dir=install_dir,
        executable=executable,
        environ={"LOCALAPPDATA": str(local_app_data)},
        platform_name="win32",
    )

    assert paths.mode is RuntimeMode.FROZEN
    assert paths.install_dir == install_dir.resolve()
    assert paths.data_dir == (local_app_data / "VoiceFlow").resolve()
    assert paths.config_file == paths.data_dir / "config.yaml"
    assert paths.logs_dir == paths.data_dir / "logs"
    assert paths.knowledge_dir == paths.data_dir / "knowledge-base"
    assert paths.models_dir == paths.data_dir / "models"
    assert paths.executable == executable.resolve()


def test_asset_resolution_prefers_user_data_and_falls_back_to_install(tmp_path):
    from runtime_paths import AppPaths, RuntimeMode

    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    bundled = install_dir / "models" / "sensevoice" / "model.int8.onnx"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"bundled")
    paths = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=install_dir / "VoiceFlow.exe",
    )

    assert paths.resolve_asset("models/sensevoice/model.int8.onnx") == bundled

    user_copy = data_dir / "models" / "sensevoice" / "model.int8.onnx"
    user_copy.parent.mkdir(parents=True)
    user_copy.write_bytes(b"user")

    assert paths.resolve_asset("models/sensevoice/model.int8.onnx") == user_copy


def test_runtime_migration_is_non_destructive_idempotent_and_does_not_copy_models(
    tmp_path,
):
    from runtime_paths import (
        DATA_SCHEMA_VERSION,
        AppPaths,
        RuntimeMode,
        prepare_runtime_layout,
    )

    install_dir = tmp_path / "legacy-source"
    data_dir = tmp_path / "user-data"
    (install_dir / "knowledge-base").mkdir(parents=True)
    (install_dir / "logs").mkdir()
    (install_dir / "models" / "sensevoice").mkdir(parents=True)
    (install_dir / "config.yaml").write_text("engine:\n  active: sensevoice\n", encoding="utf-8")
    (install_dir / "knowledge-base" / "user-dictionary.txt").write_text(
        "VoiceFlow\n",
        encoding="utf-8",
    )
    (install_dir / "logs" / "history.jsonl").write_text(
        '{"clean_text":"legacy"}\n',
        encoding="utf-8",
    )
    legacy_model = install_dir / "models" / "sensevoice" / "model.int8.onnx"
    legacy_model.write_bytes(b"large-model-placeholder")
    paths = AppPaths(
        mode=RuntimeMode.SOURCE,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=tmp_path / "python.exe",
    )

    first = prepare_runtime_layout(paths)

    assert paths.config_file.read_text(encoding="utf-8") == "engine:\n  active: sensevoice\n"
    assert (paths.knowledge_dir / "user-dictionary.txt").read_text(
        encoding="utf-8"
    ) == "VoiceFlow\n"
    assert paths.history_file.read_text(encoding="utf-8") == '{"clean_text":"legacy"}\n'
    assert not (paths.models_dir / "sensevoice" / "model.int8.onnx").exists()
    assert paths.resolve_asset("models/sensevoice/model.int8.onnx") == legacy_model
    assert first.schema_version == DATA_SCHEMA_VERSION
    assert set(first.copied) == {
        "config.yaml",
        "knowledge-base/user-dictionary.txt",
        "logs/history.jsonl",
    }

    paths.config_file.write_text("user-owned: true\n", encoding="utf-8")
    (paths.knowledge_dir / "user-dictionary.txt").write_text(
        "用户修改\n",
        encoding="utf-8",
    )
    second = prepare_runtime_layout(paths)

    assert paths.config_file.read_text(encoding="utf-8") == "user-owned: true\n"
    assert (paths.knowledge_dir / "user-dictionary.txt").read_text(
        encoding="utf-8"
    ) == "用户修改\n"
    assert second.copied == ()
    state = json.loads(paths.schema_file.read_text(encoding="utf-8"))
    assert state["schema_version"] == DATA_SCHEMA_VERSION
    assert state["install_dir"] == str(install_dir.resolve())


def test_v3_migration_changes_the_legacy_sensevoice_default_to_auto_once(tmp_path):
    from runtime_paths import DATA_SCHEMA_VERSION, AppPaths, RuntimeMode, prepare_runtime_layout

    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    install_dir.mkdir()
    data_dir.mkdir()
    (install_dir / "config.yaml").write_text(
        'engine:\n  active: "sensevoice"\n  sensevoice:\n    language: "auto"\n',
        encoding="utf-8",
    )
    (data_dir / "config.yaml").write_text(
        '# user settings\nengine:\n  active: "sensevoice"\n  sensevoice:\n'
        '    language: "zh"              # legacy default\n',
        encoding="utf-8",
    )
    (data_dir / "runtime-state.json").write_text(
        json.dumps({"schema_version": 2}),
        encoding="utf-8",
    )
    paths = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=install_dir,
        data_dir=data_dir,
        executable=install_dir / "VoiceFlow.exe",
    )

    report = prepare_runtime_layout(paths)

    assert DATA_SCHEMA_VERSION == 3
    assert 'language: "auto"              # legacy default' in paths.config_file.read_text(
        encoding="utf-8"
    )
    assert "config.yaml: sensevoice language auto" in report.sanitized

    paths.config_file.write_text(
        paths.config_file.read_text(encoding="utf-8").replace(
            'language: "auto"', 'language: "zh"'
        ),
        encoding="utf-8",
    )
    second = prepare_runtime_layout(paths)

    assert 'language: "zh"' in paths.config_file.read_text(encoding="utf-8")
    assert "config.yaml: sensevoice language auto" not in second.sanitized


def test_explicit_config_keeps_test_and_maintainer_workflows_isolated(tmp_path):
    from runtime_paths import AppPaths

    config = tmp_path / "fixture" / "config.yaml"
    config.parent.mkdir()
    config.write_text("engine: {}\n", encoding="utf-8")

    paths = AppPaths.discover(config_path=config)

    assert paths.config_file == config.resolve()
    assert paths.data_dir == config.parent.resolve()
    assert paths.install_dir == config.parent.resolve()


def test_explicit_config_still_detects_packaged_runtime(tmp_path, monkeypatch):
    from runtime_paths import AppPaths, RuntimeMode

    config = tmp_path / "data" / "config.yaml"
    config.parent.mkdir()
    config.write_text("engine: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    paths = AppPaths.discover(
        config_path=config,
        executable=tmp_path / "install" / "VoiceFlow.exe",
    )

    assert paths.mode is RuntimeMode.FROZEN
