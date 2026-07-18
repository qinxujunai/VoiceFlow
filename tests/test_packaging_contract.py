from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]


def test_windows_ci_forces_utf8_for_chinese_diagnostics():
    workflow = (ROOT / ".github" / "workflows" / "windows-quality.yml").read_text(
        encoding="utf-8"
    )

    assert 'PYTHONUTF8: "1"' in workflow


def test_release_spec_bundles_runtime_assets():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")

    assert '(str(PROJECT_ROOT / "src" / "overlay.html"), "src")' in spec
    assert '(str(PROJECT_ROOT / "knowledge-base"), "knowledge-base")' in spec
    assert '(str(PROJECT_ROOT / "model-manifest.json"), ".")' in spec
    assert 'icon=str(PROJECT_ROOT / "assets" / "voiceflow.ico")' in spec
    assert "COLLECT(" in spec


def test_inno_installer_is_per_user_upgradeable_and_bundles_offline_default_model():
    installer = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in installer
    assert "DefaultDirName={localappdata}\\Programs\\VoiceFlow" in installer
    assert 'Source: "..\\models\\sensevoice\\*"' in installer
    assert 'DestDir: "{app}\\models\\sensevoice"' in installer
    assert "AppId={{" in installer
    assert "Uninstallable=yes" in installer


def test_public_beta_has_project_and_third_party_license_notices():
    assert (ROOT / "LICENSE").is_file()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "PySide6" in notices
    assert "LGPL-3.0" in notices
    assert "sherpa-onnx" in notices
    assert "Models are not part of the VoiceFlow source-code license" in notices


def test_release_uses_pyside6_lgpl_runtime_instead_of_pyqt_gpl():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")
    compatibility = (ROOT / "src" / "qt_compat.py").read_text(encoding="utf-8")

    assert "PySide6==6.11.1" in requirements
    assert "PyQt6" not in requirements
    assert '"PySide6"' in spec
    hidden_imports = spec.split("hiddenimports=[", 1)[1].split("],", 1)[0]
    assert "PyQt6" not in hidden_imports
    assert "PyQt5" not in hidden_imports
    assert '"PyQt6"' in spec and '"PyQt5"' in spec
    assert 'QT_BINDING = "PySide6"' in compatibility


def test_release_bundles_offline_silero_vad_asset():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")

    assert '"silero_vad.onnx"' in spec
    assert (ROOT / "assets" / "silero_vad.onnx").stat().st_size == 643854


def test_tray_uses_app_icon_and_keeps_exit_action():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert '"assets",' in overlay
    assert '"voiceflow.ico"' in overlay
    assert "build_tray_icon(TRAY_ICON_IDLE, icon_path)" in overlay
    assert 'QAction("退出", self._tray_menu)' in overlay


def test_generated_icon_contains_common_windows_sizes():
    script = (ROOT / "scripts" / "generate_icon.py").read_text(encoding="utf-8")
    icon = ROOT / "assets" / "voiceflow.ico"
    data = icon.read_bytes()
    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    sizes = set()
    for idx in range(count):
        width, height = struct.unpack_from("<BB", data, 6 + idx * 16)
        sizes.add((256 if width == 0 else width, 256 if height == 0 else height))

    assert reserved == 0
    assert icon_type == 1
    assert "SIZES = (16, 20, 24, 32, 48, 64, 128, 256)" in script
    assert {(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= sizes
