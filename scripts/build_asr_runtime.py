"""Rebuild the pinned Windows ASR extension in a new isolated directory.

Requires existing CMake, Visual Studio 2022 C++ Build Tools and Python 3.12 x64.
This never installs tools, replaces the project venv, or promotes its output.
MSVC paths/timestamps can affect bytes; bit reproducibility is not claimed.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile

from asr_runtime_assets import ROOT, EXTENSION, _checked_native, checked_wheel_path, load_manifest, validate_wheel


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download_input(row, cache, *, offline=False):
    name = row.get("file", row.get("archive"))
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]+", name):
        raise ValueError("Unsafe build input filename")
    cache = Path(cache).resolve(strict=True)
    path = cache / name
    if path.exists():
        if (not path.resolve(strict=True).is_relative_to(cache)
                or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]):
            raise ValueError("Cached build input integrity differs")
        return path
    if offline:
        raise FileNotFoundError(f"Offline build input is missing: {name}")
    url = urllib.parse.urlsplit(row["url"])
    if url.scheme != "https" or url.hostname not in {"github.com", "gitlab.com"} or url.username or url.password:
        raise ValueError("Unexpected build input source")
    temporary = cache / (name + ".download")
    with urllib.request.urlopen(row["url"], timeout=90) as response, temporary.open("xb") as handle:
        total = 0
        while block := response.read(1048576):
            total += len(block)
            if total > row["bytes"]:
                raise ValueError("Build input exceeds pinned bytes")
            handle.write(block)
    if temporary.stat().st_size != row["bytes"] or sha256(temporary) != row["sha256"]:
        raise ValueError("Downloaded build input integrity differs")
    if path.exists():
        raise FileExistsError(path)
    temporary.rename(path)
    return path


def extract_source(archive_path, destination, prefix):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    selected, seen = [], set()
    with tarfile.open(archive_path) as archive:
        for member in archive:
            if member.isdir():
                continue
            if not member.name.startswith(prefix):
                raise ValueError("Unexpected source archive root")
            name = member.name[len(prefix):]
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
                raise ValueError("Unsafe source archive entry")
            if name not in {"CMakeLists.txt", "LICENSE"} and not name.startswith(("cmake/", "sherpa-onnx/")):
                continue
            if not member.isfile() or name.casefold() in seen:
                raise ValueError("Unsafe or duplicate selected source entry")
            seen.add(name.casefold())
            selected.append((member, name))
        destination.mkdir()
        for member, name in selected:
            path = destination / name
            if not path.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Source archive entry leaves destination")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                shutil.copyfileobj(archive.extractfile(member), output)


def extract_dependency(archive_path, destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    files, seen, roots, total = [], set(), set(), 0
    def add(name, size, read):
        nonlocal total
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name
                or len(relative.parts) < 2):
            raise ValueError("Unsafe dependency archive entry")
        roots.add(relative.parts[0])
        inner = PurePosixPath(*relative.parts[1:]).as_posix()
        if inner.casefold() in seen or len(roots) != 1:
            raise ValueError("Duplicate or multiple-root dependency archive entry")
        seen.add(inner.casefold())
        total += size
        if size > 134217728 or total > 536870912 or len(files) >= 20000:
            raise ValueError("Oversized dependency archive")
        files.append((inner, read()))

    if Path(archive_path).suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Dependency archive links are unsupported")
                add(entry.filename, entry.file_size, lambda entry=entry: archive.read(entry))
    else:
        with tarfile.open(archive_path) as archive:
            for entry in archive:
                if entry.isdir():
                    continue
                if not entry.isfile():
                    raise ValueError("Dependency archive links or special entries are unsupported")
                add(entry.name, entry.size, lambda entry=entry: archive.extractfile(entry).read())
    if not files:
        raise ValueError("Empty dependency archive")
    destination.mkdir(parents=True)
    for name, raw in files:
        path = destination / name
        if not path.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Dependency archive entry leaves destination")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)


def prepare_dependency_sources(rows, cache, build, *, offline):
    options = ["-DFETCHCONTENT_FULLY_DISCONNECTED=ON", "-DFETCHCONTENT_UPDATES_DISCONNECTED=ON"]
    names = set()
    for row in rows:
        name = row["name"]
        if not re.fullmatch(r"[a-z0-9_-]+", name) or name in names:
            raise ValueError("Unexpected or duplicate dependency name")
        names.add(name)
        origin = download_input(row, cache, offline=offline)
        source = (Path(build) / "_deps" / (name + "-src")).resolve()
        extract_dependency(origin, source)
        options.append("-DFETCHCONTENT_SOURCE_DIR_" + name.upper() + "=" + str(source))
    return options


def patch_binding(raw):
    first = b'  /* Define "empty" TTS symbols */\n'
    second = b'  m.attr("OfflineTtsPocketModelConfig") = py::none();\n'
    if (raw.count(first) != 1 or raw.count(second) != 1
            or b'm.attr("GenerationConfig")' in raw
            or b'm.attr("OfflineTtsSupertonicModelConfig")' in raw):
        raise ValueError("Upstream disabled-TTS binding patch precondition differs")
    return raw.replace(first, first + b'  m.attr("GenerationConfig") = py::none();\n').replace(
        second, second + b'  m.attr("OfflineTtsSupertonicModelConfig") = py::none();\n')


def run_owned(command, log_path, *, timeout):
    started = time.perf_counter()
    cleanup = {"attempted": False}
    def record(process, failure=None):
        result = {"command": command, "pid": process.pid, "exit_code": process.poll(),
                  "elapsed_seconds": time.perf_counter() - started,
                  "failure": failure, "owned_tree_cleanup": cleanup}
        Path(str(log_path) + ".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    with Path(log_path).open("x", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = process.wait(timeout=timeout)
        except BaseException as exc:
            # This PID belongs to the still-open Popen handle. Only its owned
            # compiler subtree is cleaned up, never an executable-name match.
            try:
                if process.poll() is None:
                    cleanup["attempted"] = True
                    result = subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                            capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                    cleanup["exit_code"] = result.returncode
                    process.wait(timeout=10)
            except Exception as cleanup_error:
                cleanup["error"] = str(cleanup_error)
                raise RuntimeError(f"Owned compiler cleanup failed; see {log_path}.json") from cleanup_error
            finally:
                record(process, type(exc).__name__)
            raise
    result = record(process)
    if code:
        raise RuntimeError(f"Native build command failed; see {log_path}")
    return result


def package_rebuild(work, manifest, version, native, *, tools):
    previous = manifest["version"]
    old_dist = f"sherpa_onnx-{previous}.dist-info"
    new_dist = f"sherpa_onnx-{version}.dist-info"
    raw_native = Path(native).read_bytes()
    native_sha256 = hashlib.sha256(raw_native).hexdigest()
    _checked_native(raw_native, native_sha256)
    files = {}
    with zipfile.ZipFile(checked_wheel_path()) as archive:
        for entry in archive.infolist():
            if entry.filename == f"{old_dist}/RECORD":
                continue
            name = entry.filename.replace(old_dist + "/", new_dist + "/", 1)
            raw = archive.read(entry)
            if name == EXTENSION:
                raw = raw_native
            elif name == "sherpa_onnx/__init__.py":
                before = f"__version__ = '{previous}'\n".encode()
                if raw.count(before) != 1:
                    raise ValueError("Unexpected wrapper version source")
                raw = raw.replace(before, f"__version__ = '{version}'\n".encode())
            elif name == f"{new_dist}/METADATA":
                raw = raw.replace(f"\nVersion: {previous}\n".encode(), f"\nVersion: {version}\n".encode())
            elif name == f"{new_dist}/licenses/NATIVE-BUILD-NOTICE.json":
                notice = json.loads(raw)
                notice.update(wheel_version=version, native_extension_sha256=native_sha256,
                              local_patch_modified_date=manifest["local_patch"]["modified_date"],
                              status="experimental rebuild; new binary verification required",
                              paired_smoke={"scope": "not yet run on this rebuilt extension"},
                              build_procedure={"script_sha256": sha256(Path(__file__)),
                                               "input_manifest_sha256": sha256(ROOT / "vendor/windows/asr-runtime.json"),
                                               "tools": tools})
                notice["build_dependencies"] = [{"name": row["name"], "archive": {
                    key: row[key] for key in ("file", "url", "sha256", "bytes")}} for row in manifest["build_dependencies"]]
                dependencies = {row["name"]: row for row in manifest["build_dependencies"]}
                for row in notice["notices"]:
                    parts = row["file"].split(".dist-info/licenses/", 1)
                    if len(parts) != 2 or not re.fullmatch(r"sherpa_onnx-1\.13\.3\+voiceflow\.[1-9][0-9]*", parts[0]):
                        raise ValueError("Unexpected native notice source path")
                    row["file"] = new_dist + "/licenses/" + parts[1]
                    dependency = dependencies[parts[1].split("/", 1)[0]]
                    row.update(source_archive=dependency["url"], source_archive_sha256=dependency["sha256"])
                raw = (json.dumps(notice, indent=2) + "\n").encode()
            files[name] = raw
    records = io.StringIO(newline="")
    writer = csv.writer(records, lineterminator="\n")
    for name, raw in sorted(files.items()):
        writer.writerow((name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("="), len(raw)))
    writer.writerow((f"{new_dist}/RECORD", "", ""))
    files[f"{new_dist}/RECORD"] = records.getvalue().encode()
    output_root = work / "output"
    assets = output_root / "vendor/windows"
    assets.mkdir(parents=True)
    name = f"sherpa_onnx-{version}-cp312-cp312-win_amd64.whl"
    wheel = assets / name
    with zipfile.ZipFile(wheel, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, raw)
    rebuilt = dict(manifest)
    for name in ("paired_component_evidence", "metadata_repack_evidence",
                 "prior_build_cmake_network_fetch_observed", "observed_openfst_source"):
        rebuilt.pop(name, None)
    rebuilt.update(version=version, extension_sha256=native_sha256, extension_bytes=len(raw_native),
                   wheel={"file": wheel.name, "sha256": sha256(wheel), "bytes": wheel.stat().st_size},
                   status="experimental rebuild; no automatic promotion",
                   verification_scope="build and byte provenance checked; audio, pytest and frozen acceptance not yet run",
                   rebuild_tools=tools, bit_reproducibility_claimed=False)
    shutil.copy2(ROOT / "vendor/windows/asr-only.patch", assets / "asr-only.patch")
    (assets / "asr-runtime.json").write_text(json.dumps(rebuilt, indent=2) + "\n", encoding="utf-8")
    validate_wheel(output_root)
    return rebuilt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path, help="New isolated directory; existing directories are rejected")
    parser.add_argument("--cache-dir", type=Path, help="Existing pinned-download cache; offline mode never downloads")
    parser.add_argument("--cmake", required=True, type=Path)
    parser.add_argument("--vs-instance", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if os.name != "nt" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise RuntimeError("Native rebuild requires Windows and Python 3.12 x64")
    if not re.fullmatch(r"1\.13\.3\+voiceflow\.[1-9][0-9]*", args.version):
        raise ValueError("Use a distinct VoiceFlow local native version")
    cmake = args.cmake.resolve(strict=True)
    instance = args.vs_instance.resolve(strict=True)
    if not (instance / "VC/Auxiliary/Build/vcvars64.bat").is_file():
        raise ValueError("The selected Visual Studio instance lacks C++ Build Tools")
    validate_wheel()
    manifest = load_manifest()
    patch = ROOT / "vendor/windows" / manifest["local_patch"]["file"]
    if sha256(patch) != manifest["local_patch"]["sha256"]:
        raise ValueError("Native binding patch hash differs")
    work = args.work_dir.resolve()
    if work.exists():
        raise FileExistsError(work)
    work.mkdir(parents=True)
    cache = args.cache_dir.resolve(strict=True) if args.cache_dir else work / "cache"
    if not cache.exists():
        cache.mkdir()
    source_archive = download_input(manifest["source"], cache, offline=args.offline)
    source = work / "source"
    extract_source(source_archive, source, "sherpa-onnx-" + manifest["source"]["upstream_commit"] + "/")
    binding = source / "sherpa-onnx/python/csrc/sherpa-onnx.cc"
    binding.write_bytes(patch_binding(binding.read_bytes()))
    if sha256(binding) != manifest["patched_binding_sha256"]:
        raise ValueError("Patched native binding differs from reviewed source")
    build = work / "build"
    build.mkdir()
    dependency_options = prepare_dependency_sources(manifest["build_dependencies"], cache, build, offline=args.offline)
    tools = {"cmake_sha256": sha256(cmake), "python_version": sys.version,
             "cmake_version": subprocess.check_output([str(cmake), "--version"], text=True).splitlines()[0]}
    configure = [str(cmake), "-S", str(source), "-B", str(build), "-G", "Visual Studio 17 2022", "-A", "x64",
                 "-DCMAKE_GENERATOR_INSTANCE=" + str(instance), "-DCMAKE_BUILD_TYPE=Release",
                 "-DCMAKE_INSTALL_PREFIX=" + str(work / "unused-install-prefix"),
                 "-DCMAKE_EXPORT_PACKAGE_REGISTRY=OFF", "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
                 "-DPYTHON_EXECUTABLE=" + sys.executable, "-DPython_EXECUTABLE=" + sys.executable,
                 "-DSBPE_BUILD_PYTHON=OFF"]
    configure += [f"-D{name}={value}" for name, value in manifest["cmake_options"].items()]
    configure += dependency_options
    print("Configuring the isolated native build", flush=True)
    run_owned(configure, work / "configure.log", timeout=300)
    compiler_records = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(compiler_records) != 1:
        raise ValueError("Ambiguous compiler provenance")
    compiler_text = compiler_records[0].read_text(encoding="utf-8")
    compiler_match = re.search(r'set\(CMAKE_CXX_COMPILER "([^"]+)"\)', compiler_text)
    version_match = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', compiler_text)
    if not compiler_match or not version_match:
        raise ValueError("Compiler provenance is missing")
    compiler = Path(compiler_match[1]).resolve(strict=True)
    if not compiler.is_relative_to(instance):
        raise ValueError("Compiler is outside the selected Visual Studio instance")
    tools.update(compiler_version=version_match[1], compiler_sha256=sha256(compiler),
                 cmake_cache_sha256=sha256(build / "CMakeCache.txt"))
    print("Building the ASR-only extension", flush=True)
    run_owned([str(cmake), "--build", str(build), "--config", "Release", "--target", "_sherpa_onnx", "--parallel", "4"],
              work / "build.log", timeout=1800)
    native = build / "lib/Release/_sherpa_onnx.cp312-win_amd64.pyd"
    result = package_rebuild(work, manifest, args.version, native, tools=tools)
    (work / "rebuild-report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(work / "output"), "wheel": result["wheel"],
                      "installed": False, "promoted": False, "bit_reproducibility_claimed": False}, indent=2))


if __name__ == "__main__":
    main()
