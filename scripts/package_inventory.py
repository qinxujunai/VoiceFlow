"""Attribute a frozen package to build distributions, with checked file hashes.

This inventory supports SBOM/license review; it is not a complete license review.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_package(package_dir, analysis_toc):
    package = Path(package_dir).resolve(strict=True)
    analysis = Path(analysis_toc).resolve(strict=True)
    table = ast.literal_eval(analysis.read_text(encoding="utf-8"))
    sources = set()
    namespace_modules = set()
    for group in table:
        if not isinstance(group, list):
            continue
        for entry in group:
            if not isinstance(entry, tuple) or len(entry) != 3:
                continue
            destination, origin, kind = entry
            if kind not in {"PYMODULE", "PYMODULE-1", "PYMODULE-2", "PYSOURCE",
                            "BINARY", "EXTENSION", "DATA"}:
                continue
            if origin == "-" and kind.startswith("PYMODULE"):
                namespace_modules.add(destination)
                continue
            source = Path(origin).resolve(strict=True)
            if kind in {"BINARY", "EXTENSION", "DATA"}:
                artifact = package / destination
                if not artifact.is_file():
                    # The spec deliberately filters some Analysis entries.
                    continue
                if _sha256(source) != _sha256(artifact):
                    raise ValueError(f"Package file differs from its build source: {destination}")
            sources.add(source)

    owners = {}
    generated = []
    for distribution in importlib.metadata.distributions():
        matched = {
            Path(distribution.locate_file(entry)).resolve()
            for entry in distribution.files or ()
        } & sources
        # comtypes creates this one-line namespace initializer at runtime, so it
        # is absent from wheel RECORD. Attribute only its exact generator literal.
        if distribution.metadata["Name"].casefold() == "comtypes":
            initializer = Path(distribution.locate_file("comtypes/gen/__init__.py")).resolve()
            generator = Path(distribution.locate_file("comtypes/client/_code_cache.py")).resolve()
            expected = "# comtypes.gen package, directory for generated files.\n"
            if initializer in sources and generator.is_file():
                literals = {node.value for node in ast.walk(ast.parse(generator.read_text(encoding="utf-8")))
                            if isinstance(node, ast.Constant) and isinstance(node.value, str)}
                if expected in literals and initializer.read_text(encoding="utf-8") == expected:
                    matched.add(initializer)
                    generated.append({"path": str(initializer), "generator": str(generator),
                                      "generator_sha256": _sha256(generator)})
        if not matched:
            continue
        name = distribution.metadata["Name"]
        owners[name] = {
            "name": name, "version": distribution.version,
            "license_expression": distribution.metadata.get("License-Expression"),
            "sources": [
                {"path": str(path), "sha256": _sha256(path)}
                for path in sorted(matched)
            ],
        }
    attributed = {Path(item["path"]) for owner in owners.values() for item in owner["sources"]}
    unresolved = sorted(str(path) for path in sources - attributed
                        if "site-packages" in {part.casefold() for part in path.parts})
    files = [
        {"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
         "sha256": _sha256(path)}
        for path in sorted(package.rglob("*")) if path.is_file()
    ]
    return {
        "schema_version": 1,
        "evidence_scope": "frozen files and Python distribution attribution; license review remains required",
        "attribution_basis": "PyInstaller Analysis and current build environment; copied source hashes checked",
        "analysis_sha256": _sha256(analysis),
        "namespace_modules": sorted(namespace_modules),
        "generated_source_provenance": generated,
        "package_dir": str(package),
        "package_bytes": sum(item["bytes"] for item in files),
        "files": files,
        "python_distributions": sorted(owners.values(), key=lambda item: item["name"].casefold()),
        "unattributed_site_package_sources": unresolved,
        "complete_python_attribution": not unresolved,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--analysis-toc", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = inventory_package(args.package_dir, args.analysis_toc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"distributions": len(report["python_distributions"]),
                      "files": len(report["files"]),
                      "complete_python_attribution": report["complete_python_attribution"]}))
    return 0 if report["complete_python_attribution"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
