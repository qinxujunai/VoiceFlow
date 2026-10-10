"""Check the pinned Windows ASR build without importing native engines."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = "sherpa_onnx/lib/_sherpa_onnx.cp312-win_amd64.pyd"


def _sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate ASR manifest key")
        result[key] = value
    return result


def load_manifest(root=ROOT):
    source_root = Path(root).resolve(strict=True)
    assets = (source_root / "vendor/windows").resolve(strict=True)
    if not assets.is_relative_to(source_root):
        raise ValueError("Unsafe ASR asset directory")
    path = assets / "asr-runtime.json"
    if not path.resolve(strict=True).is_relative_to(assets) or path.stat().st_size > 262144:
        raise ValueError("Unsafe ASR manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported ASR manifest schema")
    return manifest


def checked_wheel_path(root=ROOT):
    manifest = load_manifest(root)
    row = manifest["wheel"]
    name = row["file"]
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", name)
            or "/" in name or "\\" in name or ":" in name):
        raise ValueError("Unsafe ASR wheel filename")
    if (not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            or type(row["bytes"]) is not int or not 0 < row["bytes"] <= 67108864):
        raise ValueError("Invalid ASR wheel integrity metadata")
    assets = (Path(root) / "vendor/windows").resolve(strict=True)
    path = assets / name
    if not path.resolve(strict=True).is_relative_to(assets):
        raise ValueError("Unsafe ASR wheel path")
    if path.stat().st_size != row["bytes"] or _sha256(path) != row["sha256"]:
        raise ValueError("ASR wheel integrity differs from the pinned input")
    return path


def _checked_native(raw, expected):
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("ASR native extension hash differs")
    import pefile

    pe = pefile.PE(data=raw)
    try:
        exports = {symbol.name.decode("ascii") for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols
                   if symbol.name}
        if (pe.FILE_HEADER.Machine != 0x8664 or "PyInit__sherpa_onnx" not in exports
                or any("espeak" in name.lower() or "piper" in name.lower() for name in exports)):
            raise ValueError("ASR native extension contains unexpected features or ABI")
    finally:
        pe.close()


def validate_wheel(root=ROOT):
    manifest = load_manifest(root)
    path = checked_wheel_path(root)
    assets = (Path(root) / "vendor/windows").resolve(strict=True)
    patch = assets / manifest["local_patch"]["file"]
    if (manifest["local_patch"]["file"] != "asr-only.patch" or not patch.resolve(strict=True).is_relative_to(assets)
            or _sha256(patch) != manifest["local_patch"]["sha256"]):
        raise ValueError("ASR native source patch differs")
    version = manifest["version"]
    if not re.fullmatch(r"1\.13\.3\+voiceflow\.[1-9][0-9]*", version):
        raise ValueError("Unexpected local ASR version")
    dist = f"sherpa_onnx-{version}.dist-info"
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len({name.casefold() for name in names}):
            raise ValueError("Duplicate ASR wheel path")
        if sum(entry.file_size for entry in entries) > 67108864:
            raise ValueError("Oversized ASR wheel payload")
        for name in names:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
                raise ValueError("Unsafe ASR wheel entry")
        record_name = f"{dist}/RECORD"
        seen = set()
        for name, digest, length in csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))):
            if name in seen or name not in names:
                raise ValueError("Invalid ASR wheel RECORD path")
            seen.add(name)
            if name == record_name:
                if digest or length:
                    raise ValueError("Invalid ASR wheel RECORD self entry")
                continue
            raw = archive.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
            if digest != expected or str(len(raw)) != length:
                raise ValueError("ASR wheel RECORD hash differs")
        if seen != set(names):
            raise ValueError("Incomplete ASR wheel RECORD")
        metadata = archive.read(f"{dist}/METADATA").decode("utf-8")
        if (f"\nVersion: {version}\n" not in metadata
                or "\nName: sherpa-onnx\n" not in metadata
                or "\nRequires-Dist: sherpa-onnx-core==1.13.3\n" not in metadata):
            raise ValueError("ASR wheel metadata differs")
        if b"Tag: cp312-cp312-win_amd64\n" not in archive.read(f"{dist}/WHEEL"):
            raise ValueError("ASR wheel ABI differs")
        _checked_native(archive.read(EXTENSION), manifest["extension_sha256"])
        notice = json.loads(archive.read(f"{dist}/licenses/NATIVE-BUILD-NOTICE.json"))
        if (notice["native_extension_sha256"] != manifest["extension_sha256"]
                or notice["wheel_version"] != version
                or notice["local_patch_sha256"] != manifest["local_patch"]["sha256"]
                or notice["upstream_source"]["sha256"] != manifest["source"]["sha256"]):
            raise ValueError("ASR wheel provenance differs")
        dependencies = {row["name"]: {key: row[key] for key in ("file", "url", "sha256", "bytes")}
                        for row in manifest["build_dependencies"]}
        recorded_dependencies = {row["name"]: row["archive"] for row in notice["build_dependencies"]}
        if (len(dependencies) != len(manifest["build_dependencies"])
                or len(recorded_dependencies) != len(notice["build_dependencies"])
                or dependencies != recorded_dependencies):
            raise ValueError("ASR dependency archive provenance differs")
        if notice.get("local_patch_modified_date") != manifest["local_patch"]["modified_date"]:
            raise ValueError("ASR patch modification date differs")
        if hashlib.sha256(archive.read(f"{dist}/licenses/upstream-local.patch")).hexdigest() != manifest["local_patch"]["sha256"]:
            raise ValueError("ASR wheel patch differs")
        indexed_notices = [row["file"] for row in notice["notices"]]
        expected_notices = {name for name in names if name.startswith(f"{dist}/licenses/")} - {
            f"{dist}/licenses/NATIVE-BUILD-NOTICE.json", f"{dist}/licenses/upstream-local.patch",
            f"{dist}/licenses/sherpa-onnx/LICENSE"}
        if len(indexed_notices) != len(set(indexed_notices)) or set(indexed_notices) != expected_notices:
            raise ValueError("ASR native notice index is incomplete or duplicated")
        for row in notice["notices"]:
            if (not row["file"].startswith(f"{dist}/licenses/") or row["file"] not in names
                    or hashlib.sha256(archive.read(row["file"])).hexdigest() != row["sha256"]):
                raise ValueError("ASR native notice index differs")
            dependency = dependencies[row["file"].removeprefix(f"{dist}/licenses/").split("/", 1)[0]]
            if row["source_archive"] != dependency["url"] or row["source_archive_sha256"] != dependency["sha256"]:
                raise ValueError("ASR dependency notice source differs")
    return {"version": version, "wheel_sha256": manifest["wheel"]["sha256"],
            "extension_sha256": manifest["extension_sha256"], "wheel_files": len(names)}


def check_installed_runtime(root=ROOT):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise ValueError("Pinned ASR runtime requires Windows Python 3.12 x64")
    report = validate_wheel(root)
    manifest = load_manifest(root)
    distribution = importlib.metadata.distribution("sherpa-onnx")
    if distribution.version != manifest["version"]:
        raise ValueError("Installed ASR version differs; install the pinned local wheel")
    extension = Path(distribution.locate_file(EXTENSION))
    _checked_native(extension.read_bytes(), manifest["extension_sha256"])
    core = importlib.metadata.distribution("sherpa-onnx-core")
    dll = Path(core.locate_file("sherpa_onnx/lib/onnxruntime.dll"))
    if core.version != "1.13.3" or _sha256(dll) != manifest["onnxruntime_sha256"]:
        raise ValueError("Installed ASR ONNX Runtime differs")
    return {**report, "installed_extension_checked": True, "native_engine_imported": False}


def check_frozen_runtime(package_dir, root=ROOT):
    manifest = load_manifest(root)
    package = Path(package_dir).resolve(strict=True)
    extension = package / EXTENSION
    dll = package / "sherpa_onnx/lib/onnxruntime.dll"
    expected = {extension.resolve(strict=True), dll.resolve(strict=True)}
    for path in package.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in {".dll", ".pyd", ".lib"}:
            continue
        if (any(name in path.name.casefold() for name in ("sherpa", "onnxruntime", "espeak", "piper"))
                or "sherpa_onnx" in {part.casefold() for part in path.parts}):
            if path.resolve(strict=True) not in expected:
                raise ValueError(f"Unexpected frozen ASR native payload: {path.name}")
    if not all(path.is_relative_to(package) for path in expected):
        raise ValueError("Frozen ASR payload leaves package")
    _checked_native(extension.read_bytes(), manifest["extension_sha256"])
    if _sha256(dll) != manifest["onnxruntime_sha256"]:
        raise ValueError("Frozen ASR ONNX Runtime differs")
    return {"version": manifest["version"], "extension_sha256": manifest["extension_sha256"],
            "onnxruntime_sha256": manifest["onnxruntime_sha256"], "native_engine_imported": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--wheel-only", action="store_true")
    group.add_argument("--hash-only", action="store_true", help="Standard-library preflight before dependency installation")
    group.add_argument("--package-dir", type=Path, help="Check a frozen application's internal payload")
    args = parser.parse_args()
    if args.hash_only:
        path = checked_wheel_path(args.root)
        report = {"wheel": path.name, "sha256": _sha256(path)}
    elif args.package_dir:
        report = check_frozen_runtime(args.package_dir, args.root)
    else:
        report = validate_wheel(args.root) if args.wheel_only else check_installed_runtime(args.root)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
