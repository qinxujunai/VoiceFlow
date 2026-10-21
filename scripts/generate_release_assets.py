"""Generate deterministic release metadata for a VoiceFlow installer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from sync_version import read_version
from build_record import validate_build_record
from package_inventory import inventory_package


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
BUNDLED_INPUT_FILES = {
    "LICENSE", "THIRD_PARTY_NOTICES.md", "config.yaml", "model-manifest.json",
    "assets/voiceflow.ico", "assets/silero_vad.onnx", "src/overlay.html",
    "docs/sensevoice-redistribution-decision.md", "docs/qt-lgpl-compliance.md",
    "docs/streaming-preview-model-review.md",
    "docs/asr-runtime-build.md",
    "docs/punctuation-model-review.md",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locked_versions(lock_path: Path) -> dict[str, str]:
    versions = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "--find-links ./vendor/windows":
            continue
        match = PIN_PATTERN.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported lock entry: {line}")
        name, version = match.groups()
        normalized_name = re.sub(r"[-_.]+", "-", name.lower())
        if normalized_name in versions:
            raise ValueError(f"Duplicate lock entry: {name}")
        versions[normalized_name] = version
    return versions


def _runtime_components(inventory, lock_path):
    versions = _locked_versions(lock_path)
    components = []
    for distribution in inventory["python_distributions"]:
        name, version = distribution["name"], distribution["version"]
        normalized = re.sub(r"[-_.]+", "-", name.lower())
        if versions.get(normalized) != version:
            raise ValueError(f"Packaged distribution differs from requirements.lock: {name}")
        purl = f"pkg:pypi/{normalized}@{version}"
        components.append({"type": "library", "name": name, "version": version,
                           "bom-ref": purl, "purl": purl,
                           "properties": [{"name": "voiceflow:attribution-basis",
                                           "value": "PyInstaller Analysis and distribution RECORD; shared ownership possible"}]})
    return components


def _file_component(name, digest):
    return {"type": "file", "name": name, "bom-ref": f"file:{name}",
            "hashes": [{"alg": "SHA-256", "content": digest}]}


def _checked_asr_runtime(package_dir):
    from asr_runtime_assets import check_frozen_runtime, load_manifest, validate_wheel

    wheel = validate_wheel(PROJECT_ROOT)
    native = check_frozen_runtime(package_dir, PROJECT_ROOT)
    manifest = load_manifest(PROJECT_ROOT)
    components = [{"type": "library", "name": "sherpa-onnx native ASR", "version": manifest["version"],
                   "bom-ref": "native:sherpa-onnx-asr", "hashes": [{"alg": "SHA-256", "content": native["extension_sha256"]}],
                   "externalReferences": [{"type": "vcs", "url": "https://github.com/k2-fsa/sherpa-onnx/tree/" + manifest["source"]["upstream_commit"]}],
                   "properties": [{"name": "voiceflow:local-patch-sha256", "value": manifest["local_patch"]["sha256"]},
                                  {"name": "voiceflow:features", "value": "TTS/C API/diarization/PortAudio/websocket disabled"},
                                  {"name": "voiceflow:license-review", "value": "incomplete"}]}]
    for dependency in manifest["build_dependencies"]:
        components.append({"type": "library", "name": dependency["name"], "version": dependency["file"],
                           "bom-ref": "native-build-input:" + dependency["name"],
                           "hashes": [{"alg": "SHA-256", "content": dependency["sha256"]}],
                           "externalReferences": [{"type": "distribution", "url": dependency["url"]}],
                           "properties": [{"name": "voiceflow:provenance-scope",
                                           "value": "native compilation input; static link contribution and license applicability require review"}]})
    provenance = {**native, "wheel_sha256": wheel["wheel_sha256"], "source": manifest["source"],
                  "local_patch": manifest["local_patch"], "build_dependencies": manifest["build_dependencies"],
                  "cmake_options": manifest["cmake_options"], "license_review_complete": False,
                  "baked_git_sha1_is_source_provenance": False}
    return components, provenance


def _checked_bundled_inputs(record, inventory):
    files = {}
    for row in inventory["files"]:
        if row["path"] in files:
            raise ValueError("Duplicate packaged inventory path")
        files[row["path"]] = row
    checked = []
    for source in record["source_inputs"]:
        name = source["path"]
        if name not in BUNDLED_INPUT_FILES and not name.startswith("licenses/"):
            continue
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts
                or ":" in name or "\\" in name):
            raise ValueError("Unsafe bundled input path")
        actual = files.get(name)
        if (not actual or actual["bytes"] != source["bytes"]
                or actual["sha256"] != source["sha256"]):
            raise ValueError(f"Packaged bundled input differs from its build source: {name}")
        checked.append({"path": name, "bytes": source["bytes"], "sha256": source["sha256"]})
    return checked


def _checked_notice_report(package_dir, inventory, python_version):
    report = json.loads((package_dir / "dependency-notices.json").read_text(encoding="utf-8"))
    expected = {row["name"]: row["version"] for row in inventory["python_distributions"]}
    actual = {}
    for owner in report:
        name, version = owner["name"], owner["version"]
        if name in actual:
            raise ValueError("Duplicate dependency notice owner")
        actual[name] = version
        for notice in owner["notices"]:
            relative = PurePosixPath(notice["path"])
            if (relative.is_absolute() or ".." in relative.parts
                    or ":" in str(relative) or "\\" in str(relative)):
                raise ValueError("Unsafe packaged notice path")
            path = (package_dir / relative).resolve(strict=True)
            if not path.is_relative_to(package_dir) or _sha256(path) != notice["sha256"]:
                raise ValueError("Packaged notice differs from its original build source")
    expected["CPython"] = python_version
    if expected != actual:
        raise ValueError("Packaged notice owners differ from actual distribution attribution")
    return report


def _pe_identity(path):
    import pefile

    with pefile.PE(str(path), fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        fixed = pe.VS_FIXEDFILEINFO[0]
        numbers = (fixed.FileVersionMS >> 16, fixed.FileVersionMS & 65535,
                   fixed.FileVersionLS >> 16, fixed.FileVersionLS & 65535)
        entries = {}
        for group in pe.FileInfo:
            for item in group:
                for table in getattr(item, "StringTable", ()):
                    entries.update({key.decode(): value.decode().strip()
                                    for key, value in table.entries.items()})
    return {"file_version": ".".join(str(number) for number in numbers),
            "product_version": entries.get("ProductVersion"),
            "text_file_version": entries.get("FileVersion")}


def _model_components(manifest_path: Path) -> list[dict[str, object]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components: list[dict[str, object]] = []
    for model_id, model in manifest.get("models", {}).items():
        if model.get("product_status") != "default":
            continue
        source = model.get("source", {})
        component: dict[str, object] = {
            "type": "machine-learning-model",
            "bom-ref": f"model:{model_id}",
            "name": model_id,
            "version": source.get("revision") or source.get("archive_sha256", "unknown"),
            "properties": [
                {
                    "name": "voiceflow:distribution-status",
                    "value": model.get("product_status", "unknown"),
                },
                {
                    "name": "voiceflow:engine",
                    "value": model.get("runtime_engine", "unknown"),
                },
            ],
        }
        components.append(component)
        for entry in model.get("files", []):
            if entry.get("package", True) is False:
                continue
            relative = Path(model["target_dir"]) / entry["path"]
            path = PROJECT_ROOT / relative
            if not path.resolve(strict=True).is_relative_to(PROJECT_ROOT.resolve()):
                raise ValueError("Model asset leaves the source directory")
            if path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
                raise ValueError(f"Model asset differs from its pinned manifest: {relative}")
            components.append(_file_component(relative.as_posix(), entry["sha256"]))
    return components


def _auxiliary_components(manifest_path, inventory):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = {row["path"]: row for row in inventory["files"]}
    components = []
    for name, asset in manifest.get("auxiliary_assets", {}).items():
        relative = PurePosixPath(asset["target"])
        license_relative = PurePosixPath(asset["license_file"])
        for path in (relative, license_relative):
            if (path.is_absolute() or ".." in path.parts
                    or ":" in str(path) or "\\" in str(path)):
                raise ValueError("Unsafe auxiliary asset path")
            resolved = (PROJECT_ROOT / path).resolve(strict=True)
            if not resolved.is_relative_to(PROJECT_ROOT.resolve()):
                raise ValueError("Auxiliary asset leaves the source directory")
        source = PROJECT_ROOT / relative
        packaged = files.get(str(relative))
        if (source.stat().st_size != asset["size"] or _sha256(source) != asset["sha256"]
                or not packaged or packaged["bytes"] != asset["size"]
                or packaged["sha256"] != asset["sha256"]):
            raise ValueError("Packaged auxiliary asset differs from its pinned manifest")
        license_path = PROJECT_ROOT / license_relative
        packaged_license = files.get(str(license_relative))
        if (_sha256(license_path) != asset["license_sha256"] or not packaged_license
                or packaged_license["sha256"] != asset["license_sha256"]):
            raise ValueError("Packaged auxiliary license differs from its pinned source")
        components.append({
            "type": "machine-learning-model", "name": name,
            "version": asset["sha256"], "bom-ref": f"auxiliary:{name}",
            "hashes": [{"alg": "SHA-256", "content": asset["sha256"]}],
            "licenses": [{"license": {"id": asset["license"]}}],
            "externalReferences": [{"type": "distribution", "url": asset["source"]},
                                   {"type": "license", "url": asset["license_source"]}],
            "properties": [{"name": "voiceflow:asset-path", "value": str(relative)},
                           {"name": "voiceflow:provenance-scope", "value": asset["provenance_scope"]}],
        })
    return components


def generate_release_assets(
    *,
    installer: Path,
    output_dir: Path,
    version: str,
    package_dir: Path,
    analysis_toc: Path,
) -> list[Path]:
    metadata = read_version(PROJECT_ROOT)
    if version != metadata["app_version"]:
        raise ValueError("release version does not match src/version.py")
    if installer.name != f"VoiceFlow-{version}-Windows-x64.exe":
        raise ValueError("installer filename does not match the source version")
    installer = installer.resolve(strict=True)
    package_dir = package_dir.resolve(strict=True)
    record = json.loads((package_dir / "build-record.json").read_text(encoding="utf-8"))
    validate_build_record(PROJECT_ROOT, record)
    application = package_dir / "VoiceFlow.exe"
    app_identity, installer_identity = _pe_identity(application), _pe_identity(installer)
    if (app_identity["file_version"] != metadata["file_version"]
            or app_identity["product_version"] != metadata["product_version"]
            or installer_identity["file_version"] != metadata["file_version"]
            or installer_identity["product_version"] != version
            or installer_identity["text_file_version"] != metadata["product_version"]):
        raise ValueError("Application/installer PE versions differ from the build source")
    inventory = inventory_package(package_dir, analysis_toc)
    if not inventory["complete_python_attribution"]:
        raise ValueError("Packaged Python source attribution is incomplete")
    notice_report = _checked_notice_report(package_dir, inventory, record["python_version"])
    components = _runtime_components(inventory, PROJECT_ROOT / "requirements.lock")
    native_components, native_provenance = _checked_asr_runtime(package_dir)
    components.extend(native_components)
    components.extend(_file_component("package/" + row["path"], row["sha256"])
                      for row in inventory["files"])
    components.append({"type": "library", "name": "CPython",
                       "version": record["python_version"], "bom-ref": "runtime:cpython"})
    components.extend(_model_components(PROJECT_ROOT / "model-manifest.json"))
    components.extend(_auxiliary_components(PROJECT_ROOT / "model-manifest.json", inventory))
    bundled_inputs = _checked_bundled_inputs(record, inventory)
    components.sort(
        key=lambda item: (
            str(item.get("type", "")),
            str(item.get("name", "")).lower(),
        )
    )

    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/qinxujunai/VoiceFlow/releases/tag/v{version}"
        f"?build={metadata['build_id']}&sha256={_sha256(installer)}",
    )
    installer_hash = _sha256(installer)
    provenance = {
        "schema_version": 1,
        "evidence_scope": "build inputs, frozen file inventory and installer identity; installed payload verification remains required",
        "build_record": record,
        "installer": {"name": installer.name, "bytes": installer.stat().st_size,
                      "sha256": installer_hash, "pe_identity": installer_identity},
        "application": {"sha256": _sha256(application), "pe_identity": app_identity},
        "analysis_sha256": inventory["analysis_sha256"],
        "package_files": inventory["files"],
        "python_distributions": [{"name": row["name"], "version": row["version"]}
                                 for row in inventory["python_distributions"]],
        "license_review_complete": False,
        "dependency_notices": notice_report,
        "verified_bundled_inputs": bundled_inputs,
        "native_asr_build": native_provenance,
    }
    sbom = {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "component": {
                "type": "application",
                "name": "VoiceFlow",
                "version": version,
                "purl": f"pkg:github/qinxujunai/VoiceFlow@v{version}",
                "properties": [
                    {"name": "voiceflow:build-id", "value": metadata["build_id"]},
                    {"name": "voiceflow:windows-file-version", "value": metadata["file_version"]},
                    {"name": "voiceflow:source-inputs-sha256", "value": record["source_inputs_sha256"]},
                    {"name": "voiceflow:installer-sha256", "value": installer_hash},
                    {"name": "voiceflow:evidence-scope", "value": provenance["evidence_scope"]},
                ],
            },
        },
        "components": components,
        "dependencies": [{"ref": f"application:voiceflow:{metadata['product_version']}",
                          "dependsOn": [row["bom-ref"] for row in components]}],
        "compositions": [{"aggregate": "incomplete"}],
    }
    sbom["metadata"]["component"]["bom-ref"] = f"application:voiceflow:{metadata['product_version']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    notices = output_dir / "THIRD_PARTY_NOTICES.md"
    shutil.copyfile(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md", notices)
    provenance_path = output_dir / "BUILD_PROVENANCE.json"
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    sbom_path = output_dir / "SBOM.cdx.json"
    sbom_path.write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checksum_targets = [installer, sbom_path, notices, provenance_path]
    checksums = output_dir / "SHA256SUMS.txt"
    checksums.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_targets),
        encoding="utf-8",
    )
    return [checksums, sbom_path, notices, provenance_path]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--analysis-toc", required=True, type=Path)
    args = parser.parse_args()
    assets = generate_release_assets(
        installer=args.installer,
        output_dir=args.output_dir,
        version=args.version,
        package_dir=args.package_dir,
        analysis_toc=args.analysis_toc,
    )
    for asset in assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
