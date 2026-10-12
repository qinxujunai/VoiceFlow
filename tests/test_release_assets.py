import hashlib
import json
import sys
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from generate_release_assets import generate_release_assets  # noqa: E402
from sync_version import read_version
import pytest
from build_record import write_build_record


@pytest.mark.parametrize("fault", ["changed", "missing", "duplicate", "unsafe"])
def test_copied_bundled_inputs_must_match_build_record(tmp_path, fault):
    from generate_release_assets import _checked_bundled_inputs

    payload = b"original notice\n"
    relative = "licenses/native/LICENSE.txt"
    record = {"source_inputs": [{"path": relative, "bytes": len(payload),
                                 "sha256": hashlib.sha256(payload).hexdigest()}]}
    row = dict(record["source_inputs"][0])
    inventory = {"files": [row]}
    assert _checked_bundled_inputs(record, inventory) == [row]
    if fault == "changed":
        row["sha256"] = "0" * 64
    elif fault == "missing":
        inventory["files"].clear()
    elif fault == "duplicate":
        inventory["files"].append(dict(row))
    else:
        record["source_inputs"][0]["path"] = "licenses/../private.txt"
    with pytest.raises(ValueError, match="bundled|inventory"):
        _checked_bundled_inputs(record, inventory)


@pytest.fixture
def frozen_build(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("generate_release_assets._checked_asr_runtime", lambda path: ([], {}))
    # This installer fixture contains the ordinary ASR models, not optional
    # punctuation weights. It must not depend on downloading that extra asset.
    import generate_release_assets as release_assets
    manifest = json.loads((PROJECT_ROOT / "model-manifest.json").read_text(encoding="utf-8"))
    manifest["models"] = {key: value for key, value in manifest["models"].items()
                          if value.get("role") != "final_punctuation"}
    fixture_manifest = tmp_path / "model-manifest.json"
    fixture_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    model_components = release_assets._model_components
    monkeypatch.setattr(release_assets, "_model_components",
                        lambda path: model_components(fixture_manifest))

    package = tmp_path / "package"
    package.mkdir()
    (package / "VoiceFlow.exe").write_bytes(b"frozen fixture")
    (package / "assets").mkdir()
    shutil.copyfile(PROJECT_ROOT / "assets/silero_vad.onnx", package / "assets/silero_vad.onnx")
    write_build_record(PROJECT_ROOT, package / "build-record.json")
    license_file = package / "licenses/fixture.txt"
    license_file.parent.mkdir()
    shutil.copyfile(PROJECT_ROOT / "licenses/Silero-MIT.txt", package / "licenses/Silero-MIT.txt")
    from generate_release_assets import BUNDLED_INPUT_FILES
    record = json.loads((package / "build-record.json").read_text())
    for row in record["source_inputs"]:
        name = row["path"]
        if name in BUNDLED_INPUT_FILES or name.startswith("licenses/"):
            destination = package / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / name, destination)
    license_file.write_bytes(b"fixture notice")
    notice_rows = [{"name": "pyperclip", "version": "1.11.0", "notices": [
        {"path": "licenses/fixture.txt", "sha256": hashlib.sha256(license_file.read_bytes()).hexdigest()}]}]
    import platform
    notice_rows.append({"name": "CPython", "version": platform.python_version(),
                        "notices": notice_rows[0]["notices"]})
    (package / "dependency-notices.json").write_text(json.dumps(notice_rows))
    site = tmp_path / "site-packages"
    site.mkdir()
    module = site / "pyperclip.py"
    module.write_text("# fixture\n")
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr(([("pyperclip", str(module), "PYMODULE")],)))
    owner = SimpleNamespace(metadata={"Name": "pyperclip", "License-Expression": "BSD-3-Clause"},
                            version="1.11.0", files=["pyperclip.py"],
                            locate_file=lambda path: site / path)
    monkeypatch.setattr("package_inventory.importlib.metadata.distributions", lambda: [owner])
    metadata = read_version()
    monkeypatch.setattr("generate_release_assets._pe_identity", lambda path: {
        "file_version": metadata["file_version"],
        "product_version": metadata["product_version"] if path.name == "VoiceFlow.exe" else metadata["app_version"],
        "text_file_version": metadata["file_version"] if path.name == "VoiceFlow.exe" else metadata["product_version"],
    }, raising=False)
    return {"package_dir": package, "analysis_toc": toc}


def test_release_assets_include_installer_sbom_and_notices(tmp_path, frozen_build):
    metadata = read_version()
    version = metadata["app_version"]
    installer = tmp_path / f"VoiceFlow-{version}-Windows-x64.exe"
    installer.write_bytes(b"voiceflow-installer")
    output_dir = tmp_path / "release"

    assets = generate_release_assets(
        installer=installer,
        output_dir=output_dir,
        version=version,
        **frozen_build,
    )

    assert {path.name for path in assets} == {
        "SHA256SUMS.txt",
        "SBOM.cdx.json",
        "THIRD_PARTY_NOTICES.md",
        "BUILD_PROVENANCE.json",
    }
    checksum_lines = (output_dir / "SHA256SUMS.txt").read_text(
        encoding="utf-8"
    )
    expected_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    assert (
        f"{expected_hash}  VoiceFlow-{version}-Windows-x64.exe"
        in checksum_lines
    )

    sbom = json.loads((output_dir / "SBOM.cdx.json").read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["metadata"]["component"]["version"] == version
    properties = {row["name"]: row["value"] for row in sbom["metadata"]["component"]["properties"]}
    assert properties["voiceflow:build-id"] == metadata["build_id"]
    assert properties["voiceflow:windows-file-version"] == metadata["file_version"]
    assert any(
        component["name"] == "sensevoice-small-int8"
        and component["type"] == "machine-learning-model"
        for component in sbom["components"]
    )
    libraries = [row["name"] for row in sbom["components"] if row["type"] == "library"]
    assert libraries == ["CPython", "pyperclip"]
    assert "pytest" not in libraries
    assert any(row["type"] == "file" and row["name"] == "package/VoiceFlow.exe"
               for row in sbom["components"])
    model_files = [row["name"] for row in sbom["components"] if row["type"] == "file"
                   and row["name"].startswith("models/")]
    assert "models/sensevoice/tokens.txt" in model_files
    assert not any("test_wavs" in name for name in model_files)
    vad = next(row for row in sbom["components"] if row["bom-ref"] == "auxiliary:silero-vad")
    assert vad["type"] == "machine-learning-model"
    assert vad["licenses"] == [{"license": {"id": "MIT"}}]
    assert vad["hashes"][0]["content"] == hashlib.sha256(
        (frozen_build["package_dir"] / "assets/silero_vad.onnx").read_bytes()).hexdigest()
    provenance = json.loads((output_dir / "BUILD_PROVENANCE.json").read_text())
    assert provenance["installer"]["sha256"] == expected_hash
    assert provenance["build_record"]["build_id"] == metadata["build_id"]
    bundled = {row["path"] for row in provenance["verified_bundled_inputs"]}
    assert "licenses/qt-6.11.1/manifest.json" in bundled
    assert "THIRD_PARTY_NOTICES.md" in bundled
    assert str(PROJECT_ROOT) not in json.dumps(provenance)


def test_release_assets_reject_a_version_that_disagrees_with_source(tmp_path, frozen_build):
    installer = tmp_path / "VoiceFlow-99.9.9-Windows-x64.exe"
    installer.write_bytes(b"fixture")
    output = tmp_path / "release"
    with pytest.raises(ValueError, match="version"):
        generate_release_assets(installer=installer, output_dir=output, version="99.9.9", **frozen_build)
    assert not output.exists()


def test_release_assets_reject_changed_frozen_vad(tmp_path, frozen_build):
    metadata = read_version()
    installer = tmp_path / f"VoiceFlow-{metadata['app_version']}-Windows-x64.exe"
    installer.write_bytes(b"fixture")
    (frozen_build["package_dir"] / "assets/silero_vad.onnx").write_bytes(b"changed")
    output = tmp_path / "release"
    with pytest.raises(ValueError, match="auxiliary"):
        generate_release_assets(installer=installer, output_dir=output,
                                version=metadata["app_version"], **frozen_build)
    assert not output.exists()


def test_release_assets_reject_an_installer_filename_from_another_version(tmp_path, frozen_build):
    installer = tmp_path / "wrong-installer.exe"
    installer.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="installer"):
        generate_release_assets(installer=installer, output_dir=tmp_path / "release",
                                version=read_version()["app_version"], **frozen_build)


@pytest.mark.parametrize("fault", ["missing_record", "stale_source", "unattributed", "pe_version", "lock_version", "notice_hash", "notice_path", "bundled_license_changed", "bundled_license_missing"])
def test_release_assets_reject_unbound_builds_before_writing(tmp_path, frozen_build, monkeypatch, fault):
    metadata = read_version()
    installer = tmp_path / f"VoiceFlow-{metadata['app_version']}-Windows-x64.exe"
    installer.write_bytes(b"installer fixture")
    record = frozen_build["package_dir"] / "build-record.json"
    if fault == "missing_record":
        record.unlink()
    elif fault == "stale_source":
        payload = json.loads(record.read_text())
        payload["source_inputs"][0]["sha256"] = "0" * 64
        record.write_text(json.dumps(payload))
    elif fault == "unattributed":
        monkeypatch.setattr("package_inventory.importlib.metadata.distributions", lambda: [])
    elif fault == "pe_version":
        monkeypatch.setattr("generate_release_assets._pe_identity", lambda path: {
            "file_version": "9.9.9.9", "product_version": "9.9.9", "text_file_version": "9.9.9"})
    elif fault == "lock_version":
        monkeypatch.setattr("generate_release_assets._locked_versions", lambda path: {"pyperclip": "9.9.9"})
    elif fault == "notice_hash":
        (frozen_build["package_dir"] / "licenses/fixture.txt").write_bytes(b"changed")
    elif fault == "bundled_license_changed":
        (frozen_build["package_dir"] / "licenses/PortAudio-LICENSE.txt").write_bytes(b"changed")
    elif fault == "bundled_license_missing":
        (frozen_build["package_dir"] / "licenses/qt-6.11.1/manifest.json").unlink()
    else:
        notice_record = frozen_build["package_dir"] / "dependency-notices.json"
        payload = json.loads(notice_record.read_text())
        payload[0]["notices"][0]["path"] = "../private.txt"
        notice_record.write_text(json.dumps(payload))
    output = tmp_path / "release"
    with pytest.raises((ValueError, FileNotFoundError)):
        generate_release_assets(installer=installer, output_dir=output,
                                version=metadata["app_version"], **frozen_build)
    assert not output.exists()
