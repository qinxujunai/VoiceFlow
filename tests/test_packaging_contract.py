from pathlib import Path
import json
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


def test_installer_smoke_derives_the_artifact_from_the_source_version():
    script = (ROOT / "scripts" / "smoke_installer.ps1").read_text(
        encoding="utf-8"
    )

    assert '[string]$InstallerPath = ""' in script
    assert 'src\\version.py' in script
    assert "APP_VERSION\\s*=\\s*" in script
    assert "([^''\"]+)" in script
    assert '"VoiceFlow-$version-Windows-x64.exe"' in script
    assert 'VoiceFlow-0.3.0-Windows-x64.exe' not in script
    assert 'Could not read APP_VERSION' in script


def test_packaged_runtime_smoke_waits_for_an_explicit_ready_signal():
    script = (ROOT / "scripts" / "smoke_packaged_runtime.ps1").read_text(
        encoding="utf-8-sig"
    )

    assert '[int]$StartupTimeoutSeconds = 45' in script
    assert 'while (-not (Test-Path -LiteralPath $runtimeState))' in script
    assert '$process.Refresh()' in script
    assert 'Packaged VoiceFlow readiness timed out' in script
    assert 'Start-Sleep -Seconds $StartupSeconds' not in script


def test_quick_verify_rejects_pathological_model_output():
    verify = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")

    assert '"--strict-output"' in verify


def test_public_release_bundles_reviewed_preview_and_supports_truthful_signing():
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert (
        "check_release_models.py sensevoice-small-int8 "
        "streaming-zipformer-small-bilingual-zh-en-int8"
        in release
    )
    assert "download_models.py --engine streaming-preview" in release
    assert "/DINCLUDE_STREAMING_PREVIEW=1" in release
    assert "WINDOWS_CERTIFICATE_BASE64" in release
    assert "signtool" in release.lower()
    assert "Get-AuthenticodeSignature" in release
    assert "Unsigned build: release notes must disclose this state" in release
    assert 'release\\$env:GITHUB_REF_NAME\\SHA256SUMS.txt' in release
    assert 'release\\$env:GITHUB_REF_NAME\\SBOM.cdx.json' in release
    assert 'release\\$env:GITHUB_REF_NAME\\THIRD_PARTY_NOTICES.md' in release


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

    assert "path: ${{ runner.temp }}/voiceflow-site" in workflow
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
    assert "__VOICEFLOW_INSTALLER_URL__" in index
    assert "__VOICEFLOW_VERSION__" in index
    assert "v0.2.2" not in index + copy
    assert "macOS" not in index
    assert "Not available yet" not in copy
    assert index.count("data-download") == 1
    assert "未代码签名" in index
    assert "not code-signed" in copy
    assert "Beta" not in index
    assert "Beta" not in copy


def test_product_site_has_complete_bilingual_copy_and_truthful_social_image():
    index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    copy = (ROOT / "site" / "app.js").read_text(encoding="utf-8")

    html_keys = set(
        re.findall(r'data-i18n(?:-(?:alt|aria|href|src))?="([^"]+)"', index)
    )
    zh_block, en_block = copy.split("  en: {", 1)
    zh_keys = set(re.findall(r"^\s{4}([A-Za-z]\w*):", zh_block, re.MULTILINE))
    en_keys = set(re.findall(r"^\s{4}([A-Za-z]\w*):", en_block, re.MULTILINE))

    assert html_keys <= zh_keys
    assert html_keys <= en_keys
    assert 'property="og:image" content="https://qinxujunai.github.io/VoiceFlow/assets/voiceflow-demo.svg"' in index
    assert "voiceflow-demo.svg" in index
    assert "voiceflow-app-home" not in index
    assert "voiceflow-ambient" not in index


def test_product_site_localizes_demo_links_and_accessibility_labels():
    index = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    copy = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
    english_demo = (
        ROOT / "site" / "assets" / "voiceflow-demo.en.svg"
    ).read_text(encoding="utf-8")

    for key in ("brandHome", "primaryNav", "languageSwitch", "valuesAria"):
        assert f'data-i18n-aria="{key}"' in index
    assert 'data-i18n-src="demoSrc"' in index
    assert 'data-i18n-href="privacyHref"' in index
    assert 'demoSrc: "assets/voiceflow-demo.en.svg"' in copy
    assert "README.en.md#privacy-and-networking" in copy
    assert "Press once to start, again to finish" in english_demo
    assert "prefers-reduced-motion: reduce" in english_demo


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


def test_release_spec_bundles_uiautomation_native_clients():
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")

    assert 'collect_dynamic_libs("uiautomation")' in spec
    assert "binaries=UIAUTOMATION_BINARIES" in spec
    assert 'version=str(PROJECT_ROOT / "assets" / "version_info.txt")' in spec
    assert "COLLECT(" in spec
    assert '(str(PROJECT_ROOT / "licenses"), "licenses")' in spec
    assert "streaming-preview-model-review.md" in spec


def test_release_lock_and_notices_cover_windows_ui_automation_dependencies():
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "uiautomation==2.0.29" in lock
    assert "comtypes==1.4.13" in lock
    assert "comtypes-MIT.txt" in notices
    assert (ROOT / "licenses" / "comtypes-MIT.txt").is_file()


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
    for filename in (
        "encoder-epoch-99-avg-1.int8.onnx",
        "decoder-epoch-99-avg-1.onnx",
        "joiner-epoch-99-avg-1.int8.onnx",
        "tokens.txt",
    ):
        assert (
            f'Source: "..\\models\\streaming-preview\\{filename}"; '
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

    assert "filevers=(0, 3, 1, 4)" in version
    assert "prodvers=(0, 3, 1, 4)" in version
    assert "StringStruct('FileVersion', '0.3.1.4')" in version
    assert "StringStruct('ProductVersion', '0.3.1+260812.1')" in version
    assert "StringStruct('OriginalFilename', 'VoiceFlow.exe')" in version


def test_release_candidate_has_a_traceable_build_id_everywhere():
    application = (ROOT / "src" / "version.py").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    notes = (ROOT / "release" / "v0.3.1" / "RELEASE_NOTES.md").read_text(
        encoding="utf-8"
    )

    assert 'APP_VERSION = "0.3.1"' in application
    assert 'BUILD_ID = "260812.1"' in application
    assert "display_version()" in overlay
    assert '#define MyAppBuildId "260812.1"' in installer
    assert "VersionInfoVersion=0.3.1.4" in installer
    assert "build 260812.1" in notes


def test_release_notes_installer_and_checksum_are_consistent():
    installer = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    notes = (ROOT / "release" / "v0.3.1" / "RELEASE_NOTES.md").read_text(
        encoding="utf-8"
    )
    checksums = (ROOT / "release" / "v0.3.1" / "SHA256SUMS.txt").read_text(
        encoding="utf-8"
    )

    version = re.search(r'#define MyAppVersion "([^"]+)"', installer).group(1)
    installer_name = f"VoiceFlow-{version}-Windows-x64.exe"
    assert f"# VoiceFlow {version}" in notes
    assert installer_name in notes
    assert "SHA256SUMS.txt" in notes
    assert not re.search(r"SHA-256：`[A-F0-9]{64}`", notes)
    assert any(line.endswith(installer_name) for line in checksums.splitlines())


def test_development_audio_samples_are_explicitly_excluded_from_the_installer():
    manifest = json.loads((ROOT / "model-manifest.json").read_text(encoding="utf-8"))
    files = manifest["models"]["sensevoice-small-int8"]["files"]
    samples = [entry for entry in files if entry["path"].startswith("test_wavs/")]

    assert samples
    assert all(entry.get("package") is False for entry in samples)


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
