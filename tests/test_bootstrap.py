from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_rejects_broken_python_executable(tmp_path):
    from scripts import bootstrap

    fake_python = tmp_path / "python.exe"
    fake_python.write_text("not a real executable", encoding="utf-8")

    assert bootstrap.is_python_usable(fake_python) is False


def test_start_bat_runs_bootstrap_before_launching_app():
    start = (ROOT / "start.bat").read_text(encoding="utf-8")

    assert 'venv\\Scripts\\python.exe -c "import sys"' in start
    assert "scripts\\bootstrap.py --ensure-shortcut" in start
    assert start.index("scripts\\bootstrap.py --ensure-shortcut") < start.index("venv\\Scripts\\python.exe -u src\\main.py")


def test_frozen_worker_dispatch_happens_before_heavy_main_imports():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    assert source.index("multiprocessing.freeze_support()") < source.index("import yaml")
    assert source.index("multiprocessing.freeze_support()") < source.index("import numpy")


def test_desktop_shortcut_uses_windowed_launcher_not_bat():
    shortcut = (ROOT / "scripts" / "create_shortcut.ps1").read_text(encoding="utf-8")

    assert 'venv\\Scripts\\pythonw.exe' in shortcut
    assert 'scripts\\launch_voiceflow.pyw' in shortcut
    assert "$Shortcut.TargetPath = $Pythonw" in shortcut
    assert "$Shortcut.Arguments" in shortcut
    assert "$Shortcut.TargetPath = $StartBat" not in shortcut


def test_windowed_launcher_opens_visible_setup_only_when_repair_is_needed():
    launcher = (ROOT / "scripts" / "launch_voiceflow.pyw").read_text(encoding="utf-8")

    assert "CREATE_NO_WINDOW" in launcher
    assert "CREATE_NEW_CONSOLE" in launcher
    assert '"bootstrap.py"' in launcher
    assert '"start.bat"' in launcher
    assert "stdout=subprocess.DEVNULL" in launcher


def test_bootstrap_only_downloads_models_after_visible_confirmation():
    source = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")

    assert "download_models.py" in source
    assert "[str(VENV_PYTHON), \"scripts/download_models.py\"]" in source
    assert "VoiceFlow is offline by default and will not download models silently." in source
    assert "if not sys.stdin.isatty():" in source
    assert "Download the default SenseVoice model now? [y/N]" in source
    assert "snapshot_download" not in source


def test_bootstrap_has_fast_path_and_does_not_hash_large_models():
    source = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")

    assert "def is_fast_path_ready()" in source
    assert "BOOTSTRAP_STATE" in source
    assert "_file_signature(path, include_hash=False)" in source
    assert "Fast startup check ok." in source


def test_bootstrap_shortcut_points_to_desktop_lnk(monkeypatch, tmp_path):
    from scripts import bootstrap

    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    assert bootstrap.desktop_shortcut_path() == tmp_path / "Desktop" / "VoiceFlow.lnk"


def test_bootstrap_uses_current_interpreter_as_valid_python():
    from scripts import bootstrap

    assert bootstrap.is_python_usable(sys.executable) is True


def test_bootstrap_rejects_incompatible_python_without_replacing_existing_venv(monkeypatch):
    from scripts import bootstrap
    import subprocess
    import pytest

    monkeypatch.setattr(bootstrap, "_run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, "3.11 64\n"))
    monkeypatch.setattr(bootstrap, "_safe_remove_venv", lambda: pytest.fail("must preserve the existing venv"))
    monkeypatch.setattr(bootstrap, "_install_requirements", lambda: pytest.fail("must not install with the wrong ABI"))
    with pytest.raises(RuntimeError, match="3.12.*64"):
        bootstrap.ensure_venv(sys.executable)


def test_bootstrap_repairs_stale_native_build_even_if_imports_succeed(monkeypatch):
    from scripts import bootstrap

    calls = []
    monkeypatch.setattr(bootstrap, "_require_supported_python", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "is_python_usable", lambda *_args: True)
    monkeypatch.setattr(bootstrap, "_missing_imports", lambda: [])
    monkeypatch.setattr(bootstrap, "_native_runtime_ready", lambda: False)
    monkeypatch.setattr(bootstrap, "_install_requirements", lambda: calls.append("install"))
    bootstrap.ensure_venv(sys.executable)
    assert calls == ["install"]


def test_bootstrap_checks_wheel_hash_before_install_and_native_afterwards(monkeypatch):
    from scripts import bootstrap
    import subprocess

    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "")
    monkeypatch.setattr(bootstrap, "_run", run)
    bootstrap._install_requirements()
    assert commands[0][-1] == "--hash-only"
    assert commands[1][-2:] == ["-r", str(bootstrap.REQUIREMENTS)]
    assert commands[2][-1].endswith("asr_runtime_assets.py")


def test_bootstrap_fast_path_checks_native_runtime(monkeypatch):
    from scripts import bootstrap

    monkeypatch.setattr(bootstrap, "is_python_usable", lambda *_args: True)
    monkeypatch.setattr(bootstrap, "_models_present", lambda: True)
    monkeypatch.setattr(bootstrap, "_startup_signature", lambda: {"fixture": 1})
    monkeypatch.setattr(bootstrap, "_read_bootstrap_state", lambda: {"signature": {"fixture": 1}})
    monkeypatch.setattr(bootstrap, "_native_runtime_ready", lambda: False)
    assert bootstrap.is_fast_path_ready() is False


def test_bootstrap_startup_signature_tracks_native_input_changes(monkeypatch, tmp_path):
    from scripts import bootstrap
    import json

    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    (assets / "asr-runtime.json").write_text(json.dumps({"wheel": {"file": "fixture.whl"}}))
    wheel = assets / "fixture.whl"
    wheel.write_bytes(b"before")
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "MODEL_FILES", ())
    import hashlib
    manifest = {"schema_version": 1, "wheel": {"file": "fixture.whl", "bytes": 6,
                "sha256": hashlib.sha256(b"before").hexdigest()}}
    (assets / "asr-runtime.json").write_text(json.dumps(manifest))
    before = bootstrap._startup_signature()
    wheel.write_bytes(b"after")
    manifest["wheel"].update(bytes=5, sha256=hashlib.sha256(b"after").hexdigest())
    (assets / "asr-runtime.json").write_text(json.dumps(manifest))
    assert bootstrap._startup_signature() != before
