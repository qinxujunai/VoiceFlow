from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parents[1]


def test_windows_ci_forces_utf8_for_chinese_diagnostics():
    workflow = (ROOT / ".github" / "workflows" / "windows-quality.yml").read_text(
        encoding="utf-8"
    )

    assert 'PYTHONUTF8: "1"' in workflow
    assert "scripts/smoke_packaged_runtime.ps1" in workflow
    assert "scripts/smoke_installer.ps1" in workflow
    assert "/DINCLUDE_SENSEVOICE=1" in workflow
    assert "/DINCLUDE_STREAMING_PREVIEW=1" in workflow
    assert "scripts/download_models.py --engine streaming-preview" in workflow
    assert "scripts/benchmark_models.py --limit 5 --strict-output" in workflow
    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert workflow.count("persist-credentials: false") == 3


def test_quick_verify_rejects_pathological_model_output():
    verify = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")

    assert '"--strict-output"' in verify


def test_public_release_excludes_unlicensed_preview_and_requires_signing():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert (
        "check_release_models.py sensevoice-small-int8 "
        "streaming-zipformer-small-ctc-zh-int8"
        not in release
    )
    assert "download_models.py --engine streaming-preview" not in release
    assert "/DINCLUDE_STREAMING_PREVIEW=1" not in release
    assert "WINDOWS_CERTIFICATE_BASE64" in release
    assert "signtool" in release.lower()
    assert "Get-AuthenticodeSignature" in release


def test_windows_ci_pins_third_party_actions_to_reviewed_commits():
    workflow = (ROOT / ".github" / "workflows" / "windows-quality.yml").read_text(
        encoding="utf-8"
    )

    for floating_tag in (
        "actions/checkout@v7",
        "actions/setup-python@v6",
        "actions/cache@v6",
        "actions/upload-artifact@v7",
    ):
        assert floating_tag not in workflow
    for commit in (
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "ece7cb06caefa5fff74198d8649806c4678c61a1",
        "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ):
        assert commit in workflow


def test_product_site_deploy_is_pinned_and_uses_only_site_assets():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
        encoding="utf-8"
    )

    assert "path: site" in workflow
    assert "permissions:" in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "persist-credentials: false" in workflow
    for floating_tag in (
        "actions/checkout@v7",
        "actions/configure-pages@v5",
        "actions/upload-pages-artifact@v4",
        "actions/deploy-pages@v4",
    ):
        assert floating_tag not in workflow
    for commit in (
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "983d7736d9b0ae728b81ab479565c72886d7745b",
        "7b1f4a764d45c48632c6b24a0339c27f5614fb0b",
        "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
    ):
        assert commit in workflow


def test_product_site_is_bilingual_and_truthful_about_windows_download():
    index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    copy = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

    assert '<html lang="zh-CN">' in index
    assert 'data-language="zh"' in index
    assert 'data-language="en"' in index
    assert "VoiceFlow-0.2.1-Windows-x64.exe" in index
    assert "releases/latest/download" not in index
    assert "releases/download/v0.2.1/" in index
    assert "macOS" not in index
    assert "Not available yet" not in copy
    assert index.count("data-download") == 1
    assert "尚未代码签名" not in index
    assert "not code-signed yet" not in copy
    assert "Beta" not in index
    assert "Beta" not in copy


def test_product_site_has_complete_bilingual_copy_and_truthful_social_image():
    index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    copy = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

    html_keys = set(re.findall(r'data-i18n(?:-alt)?="([^"]+)"', index))
    zh_block, en_block = copy.split("  en: {", 1)
    zh_keys = set(re.findall(r"^\s{4}([A-Za-z]\w*):", zh_block, re.MULTILINE))
    en_keys = set(re.findall(r"^\s{4}([A-Za-z]\w*):", en_block, re.MULTILINE))

    assert html_keys <= zh_keys
    assert html_keys <= en_keys
    assert 'property="og:image" content="https://qinxujunai.github.io/VoiceFlow/assets/voiceflow-demo.svg"' in index
    assert "voiceflow-demo.svg" in index
    assert "voiceflow-app-home" not in index
    assert "voiceflow-ambient" not in index


def test_ui_capture_uses_sanitized_product_fixtures_by_default():
    capture = (ROOT / "scripts" / "capture_ui_states.py").read_text(
        encoding="utf-8"
    )

    assert "def _sanitized_paths" in capture
    assert "--live-data" in capture
    assert "Default output uses sanitized fixtures." in capture


def test_release_spec_bundles_runtime_assets():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")

    assert '(str(PROJECT_ROOT / "src" / "overlay.html"), "src")' in spec
    assert '(str(PROJECT_ROOT / "knowledge-base"), "knowledge-base")' in spec
    assert '(str(PROJECT_ROOT / "model-manifest.json"), ".")' in spec
    assert 'icon=str(PROJECT_ROOT / "assets" / "voiceflow.ico")' in spec
    assert 'version=str(PROJECT_ROOT / "assets" / "version_info.txt")' in spec
    assert "COLLECT(" in spec
    assert '(str(PROJECT_ROOT / "licenses"), "licenses")' in spec
    assert "streaming-preview-model-review.md" in spec


def test_inno_installer_is_per_user_upgradeable_and_bundles_offline_default_model():
    installer = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in installer
    assert "DefaultDirName={localappdata}\\Programs\\VoiceFlow" in installer
    assert "OutputBaseFilename=VoiceFlow-{#MyAppVersion}-Windows-x64" in installer
    assert (
        'Source: "..\\models\\sensevoice\\model.int8.onnx"; '
        'DestDir: "{app}\\models\\sensevoice"'
    ) in installer
    assert (
        'Source: "..\\models\\sensevoice\\tokens.txt"; '
        'DestDir: "{app}\\models\\sensevoice"'
    ) in installer
    assert (
        'Source: "..\\models\\streaming-preview\\model.int8.onnx"; '
        'DestDir: "{app}\\models\\streaming-preview"'
    ) in installer
    assert (
        'Source: "..\\models\\streaming-preview\\tokens.txt"; '
        'DestDir: "{app}\\models\\streaming-preview"'
    ) in installer
    assert 'Source: "..\\models\\sensevoice\\*"' not in installer
    assert ".cache" not in installer
    assert "AppId={{" in installer
    assert "Uninstallable=yes" in installer
    assert 'Name: "autostart"' not in installer
    assert r"Software\Microsoft\Windows\CurrentVersion\Run" not in installer
    assert r"%LOCALAPPDATA%\VoiceFlow" not in installer
    assert "#ifndef INCLUDE_STREAMING_PREVIEW" in installer
    assert (
        'Type: filesandordirs; Name: "{app}\\models\\streaming-preview"'
        in installer
    )


def test_windows_executable_has_product_version_metadata():
    version = (ROOT / "assets" / "version_info.txt").read_text(encoding="utf-8")

    assert "filevers=(0, 2, 1, 0)" in version
    assert "StringStruct('FileVersion', '0.2.1')" in version
    assert "StringStruct('ProductVersion', '0.2.1')" in version
    assert "StringStruct('OriginalFilename', 'VoiceFlow.exe')" in version


def test_public_release_has_project_and_third_party_license_notices():
    assert (ROOT / "LICENSE").is_file()
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "PySide6" in notices
    assert "LGPL-3.0" in notices
    assert "sherpa-onnx" in notices
    assert "Models are not part of the VoiceFlow source-code license" in notices
    assert (ROOT / "licenses" / "FunASR-MODEL-LICENSE.txt").is_file()


def test_qt_lgpl_and_chromium_notices_ship_with_replacement_instructions():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    compliance = (ROOT / "docs" / "qt-lgpl-compliance.md").read_text(
        encoding="utf-8"
    )

    for filename in (
        "Qt-LGPL-3.0-only.txt",
        "GPL-3.0-only.txt",
        "Chromium-BSD.txt",
    ):
        assert (ROOT / "licenses" / filename).is_file()
        assert filename in notices
    assert "73fb12a067c2e8f7a464a310aaee2860fa2b64d2" in compliance
    assert "59c81a3c2247b821b9b84b4eb8d939b77e07e276" in compliance
    assert "eb0793cc4b76e93cf669f586fd68c76019f40ec9" in compliance
    assert "replace" in compliance.lower()


def test_sensevoice_redistribution_decision_is_recorded_and_auditable():
    import json

    manifest = json.loads((ROOT / "model-manifest.json").read_text(encoding="utf-8"))
    license_info = manifest["models"]["sensevoice-small-int8"]["license"]
    decision = (ROOT / "docs" / "sensevoice-redistribution-decision.md").read_text(
        encoding="utf-8"
    )

    assert license_info["distribution_review_required"] is False
    assert license_info["distribution_decision"] == (
        "docs/sensevoice-redistribution-decision.md"
    )
    assert "2365baeacb507f821a0c8120fcee3d484dba7a07" in decision
    assert "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51" in decision
    assert "FunASR-MODEL-LICENSE.txt" in decision


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

    assert "icon_asset_name()" in overlay
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
    assert "ICO_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)" in script
    assert {(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= sizes


def test_generated_icon_includes_macos_and_png_assets():
    icns = ROOT / "assets" / "voiceflow.icns"
    png = ROOT / "assets" / "voiceflow.png"

    assert icns.read_bytes().startswith(b"icns")
    assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
