from pathlib import Path


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
