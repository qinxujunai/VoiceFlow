"""Block public publication while artifact compliance is incomplete.

This is a consistency gate for recorded review outcomes, not a license audit or
a replacement for schema, signature, checksum and installed-payload checks.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def check_release_compliance(materials: Path) -> None:
    provenance = json.loads((materials / "BUILD_PROVENANCE.json").read_text(encoding="utf-8"))
    sbom = json.loads((materials / "SBOM.cdx.json").read_text(encoding="utf-8"))
    if provenance.get("license_review_complete") is not True:
        raise ValueError("Release license review is incomplete")
    compositions = sbom.get("compositions")
    if (not isinstance(compositions, list) or not compositions
            or any(not isinstance(row, dict) or row.get("aggregate") != "complete"
                   for row in compositions)):
        raise ValueError("Release SBOM composition is incomplete")
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        raise ValueError("Unsupported release SBOM format")
    component = sbom["metadata"]["component"]
    properties = {}
    for row in component["properties"]:
        name = row["name"]
        if name in properties:
            raise ValueError("Duplicate release SBOM property")
        properties[name] = row["value"]
    record = provenance["build_record"]
    expected = {"voiceflow:build-id": record["build_id"],
                "voiceflow:source-inputs-sha256": record["source_inputs_sha256"],
                "voiceflow:installer-sha256": provenance["installer"]["sha256"]}
    if (not isinstance(record["app_version"], str) or not record["app_version"]
            or component.get("version") != record["app_version"]
            or not isinstance(record["build_id"], str) or not record["build_id"]
            or any(properties.get(name) != value for name, value in expected.items())):
        raise ValueError("Release SBOM and provenance identify different artifacts")
    for name in ("voiceflow:source-inputs-sha256", "voiceflow:installer-sha256"):
        if not isinstance(expected[name], str) or not re.fullmatch(r"[0-9a-f]{64}", expected[name]):
            raise ValueError("Invalid release artifact SHA256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials", type=Path)
    args = parser.parse_args()
    check_release_compliance(args.materials)
    print("Recorded release compliance is complete and identifies matching artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
