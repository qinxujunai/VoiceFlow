"""Generate deterministic release metadata for a VoiceFlow installer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locked_components(lock_path: Path) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported lock entry: {line}")
        name, version = match.groups()
        normalized_name = name.lower().replace("_", "-")
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{normalized_name}@{version}",
                "properties": [
                    {
                        "name": "voiceflow:source",
                        "value": "requirements.lock",
                    }
                ],
            }
        )
    return components


def _model_components(manifest_path: Path) -> list[dict[str, object]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components: list[dict[str, object]] = []
    for model_id, model in manifest.get("models", {}).items():
        if model.get("product_status") != "default":
            continue
        hashes = [
            {
                "alg": "SHA-256",
                "content": entry["sha256"],
            }
            for entry in model.get("files", [])
            if entry.get("path", "").endswith(".onnx") and entry.get("sha256")
        ]
        component: dict[str, object] = {
            "type": "machine-learning-model",
            "name": model_id,
            "version": model.get("revision", "unknown"),
            "properties": [
                {
                    "name": "voiceflow:distribution-status",
                    "value": model.get("product_status", "unknown"),
                },
                {
                    "name": "voiceflow:engine",
                    "value": model.get("engine", "unknown"),
                },
            ],
        }
        if hashes:
            component["hashes"] = hashes
        components.append(component)
    return components


def generate_release_assets(
    *,
    installer: Path,
    output_dir: Path,
    version: str,
) -> list[Path]:
    installer = installer.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    notices = output_dir / "THIRD_PARTY_NOTICES.md"
    shutil.copyfile(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md", notices)

    components = _locked_components(PROJECT_ROOT / "requirements.lock")
    components.extend(_model_components(PROJECT_ROOT / "model-manifest.json"))
    components.sort(
        key=lambda item: (
            str(item.get("type", "")),
            str(item.get("name", "")).lower(),
        )
    )

    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/qinxujunai/VoiceFlow/releases/tag/v{version}",
    )
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
            },
        },
        "components": components,
    }
    sbom_path = output_dir / "SBOM.cdx.json"
    sbom_path.write_text(
        json.dumps(sbom, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checksum_targets = [installer, sbom_path, notices]
    checksums = output_dir / "SHA256SUMS.txt"
    checksums.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_targets),
        encoding="utf-8",
    )
    return [checksums, sbom_path, notices]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    assets = generate_release_assets(
        installer=args.installer,
        output_dir=args.output_dir,
        version=args.version,
    )
    for asset in assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
