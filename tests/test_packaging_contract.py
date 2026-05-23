from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_spec_bundles_runtime_assets():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")

    assert '(str(PROJECT_ROOT / "src" / "overlay.html"), "src")' in spec
    assert '(str(PROJECT_ROOT / "knowledge-base"), "knowledge-base")' in spec
    assert 'icon=str(PROJECT_ROOT / "assets" / "voiceflow.ico")' in spec
