import hashlib
import json
from pathlib import Path
import sys
import csv
import io
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_checked_asr_wheel_rejects_changed_or_missing_payload(tmp_path):
    from asr_runtime_assets import checked_wheel_path

    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    payload = b"pinned wheel fixture"
    wheel = assets / "sherpa_onnx-1.13.3+voiceflow.1-cp312-cp312-win_amd64.whl"
    wheel.write_bytes(payload)
    manifest = {"schema_version": 1, "wheel": {"file": wheel.name,
                "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}}
    path = assets / "asr-runtime.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert checked_wheel_path(tmp_path) == wheel
    wheel.write_bytes(payload + b"changed")
    with pytest.raises(ValueError, match="wheel.*(hash|bytes)|wheel integrity"):
        checked_wheel_path(tmp_path)
    wheel.unlink()
    with pytest.raises((FileNotFoundError, ValueError)):
        checked_wheel_path(tmp_path)


@pytest.mark.parametrize("filename", ["../outside.whl", "/outside.whl", "C:/outside.whl", "x\\outside.whl"])
def test_checked_asr_wheel_rejects_unsafe_manifest_filename(tmp_path, filename):
    from asr_runtime_assets import checked_wheel_path

    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    (assets / "asr-runtime.json").write_text(json.dumps({"schema_version": 1,
        "wheel": {"file": filename, "sha256": "0" * 64, "bytes": 1}}))
    with pytest.raises(ValueError, match="filename|unsafe"):
        checked_wheel_path(tmp_path)


def test_build_record_includes_vendored_native_wheel_and_manifest(tmp_path):
    from build_record import create_build_record, validate_build_record

    (tmp_path / "src").mkdir()
    (tmp_path / "src/version.py").write_text('APP_VERSION="1.2.3"\nBUILD_ID="fixture"\nWINDOWS_REVISION=4\n')
    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    wheel = assets / "runtime.whl"
    wheel.write_bytes(b"fixture")
    (assets / "asr-runtime.json").write_text("{}")
    record = create_build_record(tmp_path)
    paths = {row["path"] for row in record["source_inputs"]}
    assert {"vendor/windows/runtime.whl", "vendor/windows/asr-runtime.json"} <= paths
    wheel.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source inputs"):
        validate_build_record(tmp_path, record)


def test_locked_versions_accepts_only_the_repository_wheel_directory(tmp_path):
    from generate_release_assets import _locked_versions

    lock = tmp_path / "requirements.lock"
    lock.write_text("--find-links ./vendor/windows\nsherpa_onnx==1.13.3+voiceflow.1\n")
    assert _locked_versions(lock) == {"sherpa-onnx": "1.13.3+voiceflow.1"}
    lock.write_text("--find-links https://unreviewed.invalid/wheels\nsherpa_onnx==1.13.3\n")
    with pytest.raises(ValueError, match="Unsupported lock entry"):
        _locked_versions(lock)


def test_vendored_native_wheel_is_integrity_checked_without_loading_engine():
    from asr_runtime_assets import validate_wheel

    before = "sherpa_onnx.lib._sherpa_onnx" in sys.modules
    report = validate_wheel(ROOT)
    manifest = json.loads((ROOT / "vendor/windows/asr-runtime.json").read_text())
    assert report["extension_sha256"] == manifest["extension_sha256"]
    assert report["wheel_files"] == 30
    assert ("sherpa_onnx.lib._sherpa_onnx" in sys.modules) is before


def test_native_source_and_embedded_attribution_supplements_keep_original_bytes():
    from asr_runtime_assets import load_manifest
    import tarfile

    assert "licenses/native-asr/** -text" in (ROOT / ".gitattributes").read_text()

    manifest = load_manifest(ROOT)
    eigen = next(row for row in manifest["build_dependencies"] if row["name"] == "eigen")
    source = ROOT / "licenses/native-asr" / eigen["file"]
    assert source.stat().st_size == eigen["bytes"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == eigen["sha256"]
    with tarfile.open(source) as archive:
        assert any(name.endswith("/COPYING.MPL2") for name in archive.getnames())
    supplements = {
        "nlohmann-json-to_chars.hpp": "20b9bc4469ee490bc626d8dbcdee060a494292473df4bdbcecfe2f2145ed562d",
        "simple-sentencepiece-darts.h": "a0ff15abf69e2651dedef5acacf474b7b8d20ace8cd5dd79dd201e99ccfee91d",
        "onnxruntime_float16.h": "9b45e1bc0fe19d9d53f272b168f5cab616e26eb00136c3a1b78f394c9b1b6757",
    }
    for name, digest in supplements.items():
        assert hashlib.sha256((ROOT / "licenses/native-asr" / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("fault,reason", [("record", "RECORD hash"), ("unhashed", "RECORD hash"),
    ("incomplete", "Incomplete.*RECORD"), ("duplicate", "Duplicate"), ("unsafe", "Unsafe.*entry"),
    ("notice_missing", "notice index"), ("notice_path", "notice index"), ("patch_date", "modification date")])
def test_native_wheel_checks_internal_records_after_outer_hash_is_updated(tmp_path, fault, reason):
    from asr_runtime_assets import validate_wheel

    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    manifest = json.loads((ROOT / "vendor/windows/asr-runtime.json").read_text())
    path = ROOT / "vendor/windows" / manifest["wheel"]["file"]
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    record = next(name for name in files if name.endswith(".dist-info/RECORD"))
    if fault == "record":
        files["sherpa_onnx/utils.py"] += b"\n# changed fixture\n"
    elif fault in {"unhashed", "incomplete"}:
        rows = list(csv.reader(io.StringIO(files[record].decode())))
        rows = [row for row in rows if not (fault == "incomplete" and row[0] == "sherpa_onnx/utils.py")]
        for row in rows:
            if fault == "unhashed" and row[0] == "sherpa_onnx/utils.py":
                row[1:] = ["", ""]
        result = io.StringIO(newline="")
        csv.writer(result, lineterminator="\n").writerows(rows)
        files[record] = result.getvalue().encode()
    elif fault == "duplicate":
        files["SHERPA_ONNX/UTILS.PY"] = files["sherpa_onnx/utils.py"]
    elif fault in {"notice_missing", "notice_path", "patch_date"}:
        notice_path = next(name for name in files if name.endswith("/NATIVE-BUILD-NOTICE.json"))
        notice = json.loads(files[notice_path])
        if fault == "notice_missing":
            notice["notices"] = []
        elif fault == "notice_path":
            notice["notices"][0]["file"] = "old.dist-info/licenses/previous.txt"
        else:
            notice["local_patch_modified_date"] = "unknown"
        files[notice_path] = json.dumps(notice).encode()
        result = io.StringIO(newline="")
        import base64
        writer = csv.writer(result, lineterminator="\n")
        for name, raw in sorted(files.items()):
            if name != record:
                writer.writerow((name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("="), len(raw)))
        writer.writerow((record, "", ""))
        files[record] = result.getvalue().encode()
    else:
        files["../outside.py"] = b"unsafe"
    destination = assets / path.name
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    manifest["wheel"].update(bytes=destination.stat().st_size,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    (assets / "asr-runtime.json").write_text(json.dumps(manifest))
    (assets / "asr-only.patch").write_bytes((ROOT / "vendor/windows/asr-only.patch").read_bytes())
    with pytest.raises(ValueError, match=reason):
        validate_wheel(tmp_path)


@pytest.mark.parametrize("unexpected", ["sherpa-onnx-c-api.dll", "piper.dll", "espeak.dll"])
def test_frozen_asr_boundary_requires_only_the_pinned_extension_and_runtime(tmp_path, unexpected):
    from asr_runtime_assets import check_frozen_runtime

    manifest = json.loads((ROOT / "vendor/windows/asr-runtime.json").read_text())
    assets = tmp_path / "sherpa_onnx/lib"
    assets.mkdir(parents=True)
    with zipfile.ZipFile(ROOT / "vendor/windows" / manifest["wheel"]["file"]) as archive:
        (assets / "_sherpa_onnx.cp312-win_amd64.pyd").write_bytes(archive.read(
            "sherpa_onnx/lib/_sherpa_onnx.cp312-win_amd64.pyd"))
    import importlib.metadata
    core = importlib.metadata.distribution("sherpa-onnx-core")
    (assets / "onnxruntime.dll").write_bytes(Path(core.locate_file("sherpa_onnx/lib/onnxruntime.dll")).read_bytes())
    assert check_frozen_runtime(tmp_path)["native_engine_imported"] is False
    from generate_release_assets import _checked_asr_runtime
    components, provenance = _checked_asr_runtime(tmp_path)
    assert provenance["extension_sha256"] == manifest["extension_sha256"]
    assert provenance["license_review_complete"] is False
    deps = [row for row in components if row["bom-ref"].startswith("native-build-input:")]
    assert len(deps) == len(manifest["build_dependencies"]) == 10
    assert {row["hashes"][0]["content"] for row in deps} == {
        row["sha256"] for row in manifest["build_dependencies"]}
    (assets / unexpected).write_bytes(b"unreviewed native TTS payload")
    with pytest.raises(ValueError, match="Unexpected.*ASR|ASR.*payload"):
        check_frozen_runtime(tmp_path)
    (assets / unexpected).unlink()
    (assets / "onnxruntime.dll").write_bytes(b"changed")
    with pytest.raises(ValueError, match="ONNX Runtime"):
        check_frozen_runtime(tmp_path)


def test_native_patch_must_remain_inside_its_asset_directory(tmp_path):
    from asr_runtime_assets import validate_wheel
    import shutil

    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    manifest = json.loads((ROOT / "vendor/windows/asr-runtime.json").read_text())
    shutil.copyfile(ROOT / "vendor/windows" / manifest["wheel"]["file"], assets / manifest["wheel"]["file"])
    (assets.parent / "asr-only.patch").write_bytes((ROOT / "vendor/windows/asr-only.patch").read_bytes())
    manifest["local_patch"]["file"] = "../asr-only.patch"
    (assets / "asr-runtime.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="patch"):
        validate_wheel(tmp_path)


def test_native_dependency_archive_provenance_must_match_manifest(tmp_path):
    from asr_runtime_assets import validate_wheel
    import shutil

    assets = tmp_path / "vendor/windows"
    assets.mkdir(parents=True)
    manifest = json.loads((ROOT / "vendor/windows/asr-runtime.json").read_text())
    shutil.copyfile(ROOT / "vendor/windows" / manifest["wheel"]["file"], assets / manifest["wheel"]["file"])
    shutil.copyfile(ROOT / "vendor/windows/asr-only.patch", assets / "asr-only.patch")
    manifest["build_dependencies"][0]["sha256"] = "0" * 64
    (assets / "asr-runtime.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="dependency"):
        validate_wheel(tmp_path)
