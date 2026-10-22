import hashlib
import io
from pathlib import Path
import sys
import tarfile
import json
import os
import subprocess

import pytest

# Exercises Win32 APIs, struct layouts or Windows release artifacts; covered by Windows quality.
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only contract")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_no_tts_patch_adds_only_the_two_missing_placeholders():
    from build_asr_runtime import patch_binding

    raw = (b'// ASR code remains unchanged\n'
           b'  /* Define "empty" TTS symbols */\n'
           b'  m.attr("OfflineTtsKittenModelConfig") = py::none();\n'
           b'  m.attr("OfflineTtsPocketModelConfig") = py::none();\n')
    result = patch_binding(raw)
    assert result.count(b"\n") == raw.count(b"\n") + 2
    assert result.replace(b'  m.attr("GenerationConfig") = py::none();\n', b'').replace(
        b'  m.attr("OfflineTtsSupertonicModelConfig") = py::none();\n', b'') == raw
    with pytest.raises(ValueError, match="patch|binding"):
        patch_binding(result)


@pytest.mark.parametrize("fault", ["link", "traversal", "duplicate"])
def test_source_extraction_rejects_unsafe_selected_entries(tmp_path, fault):
    from build_asr_runtime import extract_source

    path = tmp_path / "source.tar.gz"
    prefix = "upstream-commit/"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo(prefix + "CMakeLists.txt")
        entry.size = 5
        archive.addfile(entry, io.BytesIO(b"cmake"))
        entry = tarfile.TarInfo(prefix + ("cmake/evil.cmake" if fault == "link" else
                                       "cmake/../../outside.py" if fault == "traversal" else "CMakeLists.txt"))
        if fault == "link":
            entry.type = tarfile.SYMTYPE
            entry.linkname = "../../outside.py"
        archive.addfile(entry)
    with pytest.raises(ValueError, match="source|archive|entry"):
        extract_source(path, tmp_path / "source", prefix)
    assert not (tmp_path / "outside.py").exists()


def test_source_extraction_skips_unneeded_platform_links(tmp_path):
    from build_asr_runtime import extract_source

    path = tmp_path / "source.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo("upstream/CMakeLists.txt")
        entry.size = 5
        archive.addfile(entry, io.BytesIO(b"cmake"))
        entry = tarfile.TarInfo("upstream/android/example-link")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../../outside.py"
        archive.addfile(entry)
    extract_source(path, tmp_path / "source", "upstream/")
    assert (tmp_path / "source/CMakeLists.txt").read_bytes() == b"cmake"
    assert not (tmp_path / "source/android").exists()


def test_cached_download_rejects_changed_bytes_and_does_not_overwrite(tmp_path):
    from build_asr_runtime import download_input

    row = {"file": "source.tar.gz", "url": "https://github.com/example/source.tar.gz",
           "bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
    path = tmp_path / row["file"]
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="hash|input|integrity"):
        download_input(row, tmp_path, offline=True)
    assert path.read_bytes() == b"bad"
    path.write_bytes(b"good")
    assert download_input(row, tmp_path, offline=True) == path


def test_offline_missing_input_never_uses_network(tmp_path, monkeypatch):
    import urllib.request
    from build_asr_runtime import download_input

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("unexpected network"))
    row = {"file": "missing.tar.gz", "url": "https://github.com/example/missing.tar.gz",
           "bytes": 4, "sha256": "0" * 64}
    with pytest.raises(FileNotFoundError):
        download_input(row, tmp_path, offline=True)


@windows_only
def test_repack_updates_all_native_notice_paths_and_records_modification_date(tmp_path):
    from build_asr_runtime import package_rebuild
    from asr_runtime_assets import EXTENSION, checked_wheel_path, load_manifest
    import zipfile

    manifest = load_manifest()
    with zipfile.ZipFile(checked_wheel_path()) as archive:
        raw = archive.read(EXTENSION)
    native = tmp_path / "fixture.pyd"
    native.write_bytes(raw)
    result = package_rebuild(tmp_path, manifest, "1.13.3+voiceflow.99", native, tools={"fixture": True})
    assert "paired_component_evidence" not in result
    assert "metadata_repack_evidence" not in result
    assert "prior_build_cmake_network_fetch_observed" not in result
    assert "observed_openfst_source" not in result
    with zipfile.ZipFile(tmp_path / "output/vendor/windows" / result["wheel"]["file"]) as archive:
        notice = json.loads(archive.read("sherpa_onnx-1.13.3+voiceflow.99.dist-info/licenses/NATIVE-BUILD-NOTICE.json"))
        assert notice["local_patch_modified_date"] == manifest["local_patch"]["modified_date"]
        for row in notice["notices"]:
            assert row["file"].startswith("sherpa_onnx-1.13.3+voiceflow.99.dist-info/licenses/")
            assert hashlib.sha256(archive.read(row["file"])).hexdigest() == row["sha256"]


def test_dependencies_are_extracted_and_cmake_cannot_fetch_other_sources(tmp_path):
    from build_asr_runtime import prepare_dependency_sources

    cache = tmp_path / "cache"
    cache.mkdir()
    build = tmp_path / "build"
    build.mkdir()
    path = cache / "dependency.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo("dependency-commit/CMakeLists.txt")
        entry.size = 5
        archive.addfile(entry, io.BytesIO(b"cmake"))
    row = {"name": "dependency", "file": path.name, "bytes": path.stat().st_size,
           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    options = prepare_dependency_sources([row], cache, build, offline=True)
    assert "-DFETCHCONTENT_FULLY_DISCONNECTED=ON" in options
    assert "-DFETCHCONTENT_UPDATES_DISCONNECTED=ON" in options
    assert "-DFETCHCONTENT_SOURCE_DIR_DEPENDENCY=" + str((build / "_deps/dependency-src").resolve()) in options
    assert (build / "_deps/dependency-src/CMakeLists.txt").read_bytes() == b"cmake"


@pytest.mark.parametrize("fault", ["link", "traversal", "duplicate", "root"])
def test_dependency_archive_rejects_links_traversal_duplicates_and_multiple_roots(tmp_path, fault):
    from build_asr_runtime import extract_dependency

    path = tmp_path / "dependency.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo("root/header.h")
        entry.size = 4
        archive.addfile(entry, io.BytesIO(b"good"))
        entry = tarfile.TarInfo({"link": "root/link.h", "traversal": "root/../outside.h",
                               "duplicate": "root/HEADER.H", "root": "different/header.h"}[fault])
        if fault == "link":
            entry.type = tarfile.SYMTYPE
            entry.linkname = "header.h"
        archive.addfile(entry)
    with pytest.raises(ValueError, match="archive|dependency|entry"):
        extract_dependency(path, tmp_path / "source")
    assert not (tmp_path / "source").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows owned compiler subtree cleanup")
def test_native_build_timeout_records_owned_cleanup(tmp_path):
    from build_asr_runtime import run_owned

    child_file = tmp_path / "child.pid"
    code = ("import subprocess,sys,time; from pathlib import Path; "
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW); "
            "Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)")
    log = tmp_path / "owned.log"
    with pytest.raises(subprocess.TimeoutExpired):
        run_owned([sys.executable, "-c", code, str(child_file)], log, timeout=1)
    report = json.loads(Path(str(log) + ".json").read_text())
    assert report["failure"] == "TimeoutExpired"
    assert report["owned_tree_cleanup"]["attempted"] is True
    assert report["owned_tree_cleanup"]["exit_code"] == 0
    assert report["exit_code"] is not None
    assert child_file.is_file()
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    for pid in (report["pid"], int(child_file.read_text())):
        handle = kernel.OpenProcess(0x101000, False, pid)
        if handle:
            try:
                assert kernel.WaitForSingleObject(handle, 0) == 0
            finally:
                kernel.CloseHandle(handle)
        else:
            assert ctypes.get_last_error() == 87
