"""Pinned model inventory and offline integrity verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_model_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("models"), dict):
        raise ValueError(f"unsupported model manifest: {manifest_path}")
    return data


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_assets(model_dir: str | Path, model: dict[str, Any]) -> list[str]:
    base = Path(model_dir)
    errors: list[str] = []
    for asset in model.get("files", []):
        path = base / asset["path"]
        if not path.is_file():
            errors.append(f"missing: {asset['path']}")
            continue
        actual_size = path.stat().st_size
        expected_size = int(asset["size"])
        if actual_size != expected_size:
            errors.append(
                f"size mismatch: {asset['path']} expected={expected_size} actual={actual_size}"
            )
            continue
        actual_hash = sha256_file(path)
        if actual_hash.lower() != str(asset["sha256"]).lower():
            errors.append(f"sha256 mismatch: {asset['path']}")
    return errors
