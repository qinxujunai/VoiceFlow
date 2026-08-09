import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def test_platform_data_directories_are_native():
    from platform_utils import default_data_dir

    assert default_data_dir(
        {}, platform_name="darwin", home="/Users/tester"
    ) == Path("/Users/tester/Library/Application Support/VoiceFlow")
    assert default_data_dir(
        {"LOCALAPPDATA": r"C:\Users\tester\AppData\Local"},
        platform_name="win32",
        home=r"C:\Users\tester",
    ) == Path(r"C:\Users\tester\AppData\Local") / "VoiceFlow"


def test_platform_output_and_icon_choices():
    from platform_utils import (
        icon_asset_name,
        paste_modifier,
        platform_label,
        trigger_instruction,
        trigger_summary,
    )

    assert paste_modifier("darwin") == "command"
    assert paste_modifier("win32") == "ctrl"
    assert icon_asset_name("darwin") == "voiceflow.png"
    assert icon_asset_name("win32") == "voiceflow.ico"
    assert platform_label("darwin") == "macOS"
    assert trigger_summary("darwin") == "F2 · 托盘菜单"
    assert "托盘菜单" in trigger_instruction("darwin")


def test_macos_autostart_payload_uses_the_real_runtime():
    from runtime_paths import RuntimeMode
    from settings_store import _macos_launch_agent_payload

    source = SimpleNamespace(
        mode=RuntimeMode.SOURCE,
        install_dir=Path("/Applications/VoiceFlow-src"),
        executable=Path("/Applications/VoiceFlow-src/venv/bin/python"),
    )
    frozen = SimpleNamespace(
        mode=RuntimeMode.FROZEN,
        install_dir=Path("/Applications/VoiceFlow.app/Contents/Frameworks"),
        executable=Path("/Applications/VoiceFlow.app/Contents/MacOS/VoiceFlow"),
    )

    source_payload = _macos_launch_agent_payload(source)
    frozen_payload = _macos_launch_agent_payload(frozen)
    source_entry = source_payload["ProgramArguments"][-1].replace("\\", "/")
    assert source_entry.endswith("src/main.py")
    frozen_program = frozen_payload["ProgramArguments"][0].replace("\\", "/")
    assert frozen_program.endswith("VoiceFlow.app/Contents/MacOS/VoiceFlow")
    assert source_payload["RunAtLoad"] is True


def test_macos_hotkeys_do_not_import_the_windows_keyboard_backend_at_module_load():
    source = (ROOT / "src" / "hotkey_manager.py").read_text(encoding="utf-8")
    imports = source.split("class HotkeyManager", 1)[0]

    assert not any(line.strip() == "import keyboard" for line in imports.splitlines())
    assert 'self.platform_name == "win32"' in source
    assert "_start_pynput_keyboard" in source


def test_macos_bundle_covers_both_runtime_models_and_permissions():
    spec = (ROOT / "VoiceFlow.macOS.spec").read_text(encoding="utf-8")
    entitlements = (
        ROOT / "installer" / "macos" / "entitlements.plist"
    ).read_text(encoding="utf-8")

    assert 'name="VoiceFlow.app"' in spec
    assert 'bundle_identifier="ai.voiceflow.app"' in spec
    assert 'os.environ.get("VOICEFLOW_CODESIGN_IDENTITY")' in spec
    assert "codesign_identity=CODESIGN_IDENTITY" in spec
    assert '"NSMicrophoneUsageDescription"' in spec
    assert '"models" / "sensevoice"' in spec
    assert '"models" / "streaming-preview"' in spec
    assert '"keyboard"' in spec.split("excludes=[", 1)[1]
    assert "com.apple.security.device.audio-input" in entitlements


def test_macos_quality_builds_apple_silicon_and_intel_without_publishing():
    workflow = (
        ROOT / ".github" / "workflows" / "macos-quality.yml"
    ).read_text(encoding="utf-8")

    assert "runner: macos-15" in workflow
    assert "runner: macos-15-intel" in workflow
    assert "VoiceFlow-0.3.0-macOS-Apple-Silicon" in workflow
    assert "VoiceFlow-0.3.0-macOS-Intel" in workflow
    assert "--runtime-smoke" in workflow
    assert "hdiutil verify" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "gh release" not in workflow
    assert "pip install -r requirements-macos.lock" in workflow


def test_macos_release_requires_native_signing_and_notarization():
    workflow = (
        ROOT / ".github" / "workflows" / "macos-release.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "runner: macos-15" in workflow
    assert "runner: macos-15-intel" in workflow
    assert "APPLE_DEVELOPER_ID_APPLICATION_CERT_BASE64" in workflow
    assert "APPLE_DEVELOPER_ID_APPLICATION_CERT_PASSWORD" in workflow
    assert "APPLE_ID" in workflow
    assert "APPLE_APP_SPECIFIC_PASSWORD" in workflow
    assert "APPLE_TEAM_ID" in workflow
    assert "codesign --verify --deep --strict" in workflow
    assert "xcrun notarytool submit" in workflow
    assert "xcrun stapler staple" in workflow
    assert "gh release upload" in workflow
    assert "--clobber" not in workflow


def test_macos_dependency_lock_excludes_windows_only_runtime_packages():
    lock = (ROOT / "requirements-macos.lock").read_text(encoding="utf-8")

    assert "pyobjc-core==" in lock
    assert "pyobjc-framework-applicationservices==" in lock
    assert "pyobjc-framework-quartz==" in lock
    assert "\nkeyboard==" not in f"\n{lock.lower()}"
    assert "pywin32-ctypes" not in lock.lower()


def test_platform_release_contract_prevents_placeholder_downloads():
    contract = (
        ROOT / "docs" / "platform-release-contract.md"
    ).read_text(encoding="utf-8")
    prose = " ".join(contract.split())

    assert "Apple Silicon and one for Intel" in prose
    assert "same signed Git tag" in prose
    assert "matching GitHub Release asset exists" in prose
    assert "10-minute recordings" in prose
    assert "preview must never replay or move backwards" in prose
