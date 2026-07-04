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


def test_bootstrap_never_downloads_models_implicitly():
    source = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")

    assert "download_models.py" in source
    assert "[str(VENV_PYTHON), \"scripts/download_models.py\"]" not in source
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
