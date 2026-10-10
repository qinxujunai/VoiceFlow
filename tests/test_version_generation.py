"""One source controls application, PE and installer versions."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_generated_metadata_uses_source_version_and_build(tmp_path):
    from sync_version import sync_versions

    source = tmp_path / "src" / "version.py"
    source.parent.mkdir()
    source.write_text('APP_VERSION = "1.2.3-rc.1"\nBUILD_ID = "261007.9"\nWINDOWS_REVISION = 7\n')
    metadata = sync_versions(tmp_path)
    assert metadata["app_version"] == "1.2.3-rc.1"
    assert metadata["file_version"] == "1.2.3.7"
    include = (tmp_path / "installer" / "version.iss").read_text()
    assert '#define MyAppVersion "1.2.3-rc.1"' in include
    assert '#define MyAppBuildId "261007.9"' in include
    assert '#define MyAppFileVersion "1.2.3.7"' in include
    resource = (tmp_path / "assets" / "version_info.txt").read_text()
    assert "filevers=(1, 2, 3, 7)" in resource
    assert "1.2.3-rc.1+261007.9" in resource
    assert sync_versions(tmp_path, check=True) == metadata


def test_version_check_rejects_stale_outputs_without_overwriting(tmp_path):
    from sync_version import sync_versions

    source = tmp_path / "src" / "version.py"
    source.parent.mkdir()
    source.write_text('APP_VERSION = "1.2.3"\nBUILD_ID = "261007.9"\nWINDOWS_REVISION = 7\n')
    sync_versions(tmp_path)
    include = tmp_path / "installer" / "version.iss"
    include.write_text("stale data")
    with pytest.raises(ValueError, match="stale"):
        sync_versions(tmp_path, check=True)
    assert include.read_text() == "stale data"


@pytest.mark.parametrize("version,build,revision", [
    ("1.2", "261007.1", 1), ("1.2.3", 'bad"value', 1),
    ("1.2.3", "261007.1", True), ("1.2.3", "261007.1", 65536),
    ("65536.2.3", "261007.1", 1),
])
def test_invalid_version_inputs_cannot_generate_installer_script(tmp_path, version, build, revision):
    from sync_version import sync_versions

    source = tmp_path / "src" / "version.py"
    source.parent.mkdir()
    source.write_text(f"APP_VERSION = {version!r}\nBUILD_ID = {build!r}\nWINDOWS_REVISION = {revision!r}\n")
    with pytest.raises(ValueError):
        sync_versions(tmp_path)
    assert not (tmp_path / "installer").exists()


def test_release_tag_mismatch_is_rejected_before_metadata_changes(tmp_path):
    from sync_version import sync_versions

    source = tmp_path / "src" / "version.py"
    source.parent.mkdir()
    source.write_text('APP_VERSION = "1.2.3"\nBUILD_ID = "261007.1"\nWINDOWS_REVISION = 1\n')
    with pytest.raises(ValueError, match="tag"):
        sync_versions(tmp_path, tag="v9.9.9")
    assert not (tmp_path / "assets").exists()


def test_current_version_metadata_is_generated_and_installer_consumes_it():
    from sync_version import sync_versions

    sync_versions(ROOT, check=True)
    installer = (ROOT / "installer" / "VoiceFlow.iss").read_text(encoding="utf-8")
    assert '#include "version.iss"' in installer
    assert "#define MyAppVersion" not in installer
    assert "VersionInfoVersion={#MyAppFileVersion}" in installer
    spec = (ROOT / "VoiceFlow.spec").read_text(encoding="utf-8")
    assert "sync_versions(PROJECT_ROOT)" in spec
