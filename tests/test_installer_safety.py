"""Source guards complement actual compiled installer acceptance."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_never_kills_all_named_instances_or_closes_apps_implicitly():
    source = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    assert "taskkill" not in source.lower()
    assert "CloseApplications=no" in source
    assert '#include "runtime_guard.iss"' in source
    guard = (ROOT / "installer" / "runtime_guard.iss").read_text(encoding="utf-8")
    assert "function PrepareToInstall" in guard
    assert "function InitializeUninstall" in guard
    assert "ExecutablePath" in guard
    assert "CompareText" in guard
    assert "Terminate" not in guard


def test_installer_does_not_recursively_remove_unowned_files_or_legacy_vocabulary():
    source = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    assert 'Type: filesandordirs; Name: "{app}"' not in source
    assert "[InstallDelete]" not in source
    assert "[UninstallDelete]" not in source
    # Installed files are already tracked by Inno's own uninstall log.
    assert '[Files]' in source


def test_upgrade_retires_unsafe_legacy_uninstall_instructions():
    source = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    assert "UninstallLogMode=overwrite" in source


def test_ci_uses_the_verified_portable_compiler_instead_of_an_unpinned_install():
    for name in ("windows-quality.yml", "release.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "choco install innosetup" not in workflow
        assert "prepare_inno_compiler.ps1" in workflow
        assert "& $innoCompiler" in workflow
    script = (ROOT / "scripts" / "prepare_inno_compiler.ps1").read_text(encoding="utf-8")
    assert "is-6_7_3/innosetup-6.7.3.exe" in script
    assert "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732" in script
    assert "Get-AuthenticodeSignature" in script
    assert "/PORTABLE=1" in script
    assert "-WindowStyle Hidden" in script
