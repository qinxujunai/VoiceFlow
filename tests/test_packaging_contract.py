from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]


def test_release_spec_bundles_runtime_assets():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")

    assert '(str(PROJECT_ROOT / "src" / "overlay.html"), "src")' in spec
    assert '(str(PROJECT_ROOT / "knowledge-base"), "knowledge-base")' in spec
    assert 'icon=str(PROJECT_ROOT / "assets" / "voiceflow.ico")' in spec


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
