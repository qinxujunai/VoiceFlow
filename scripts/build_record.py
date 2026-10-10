"""Record runtime, build and bundled notice inputs before freezing the app.

This covers the listed build inputs, not every file in a dirty working tree.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess

from sync_version import read_version


INPUT_FILES = (
    "VoiceFlow.spec", ".gitattributes", "requirements.txt", "requirements.lock", "config.yaml", "model-manifest.json",
    "LICENSE", "THIRD_PARTY_NOTICES.md", "assets/version_info.txt",
    "assets/voiceflow.ico", "assets/silero_vad.onnx",
    "docs/sensevoice-redistribution-decision.md", "docs/qt-lgpl-compliance.md",
    "docs/streaming-preview-model-review.md",
    "docs/asr-runtime-build.md",
)
INPUT_TREES = ("src", "scripts", "installer", "licenses", "knowledge-base", "vendor/windows")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _input_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def create_build_record(root):
    root = Path(root).resolve(strict=True)
    paths = {root / name for name in INPUT_FILES if (root / name).is_file()}
    for name in INPUT_TREES:
        for path in (root / name).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                paths.add(path)
    rows = []
    for path in sorted(paths):
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("build input leaves the source directory")
        rows.append({"path": path.relative_to(root).as_posix(),
                     "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=10, check=False)
    metadata = read_version(root)
    return {
        "schema_version": 1,
        "evidence_scope": "runtime/build/bundled inputs; not a complete working-tree archive",
        "git_head": result.stdout.strip() if result.returncode == 0 else None,
        "app_version": metadata["app_version"], "build_id": metadata["build_id"],
        "file_version": metadata["file_version"],
        "python_version": platform.python_version(),
        "source_inputs": rows, "source_inputs_sha256": _input_digest(rows),
    }


def validate_build_record(root, record):
    if record.get("schema_version") != 1:
        raise ValueError("unsupported build record schema")
    if _input_digest(record.get("source_inputs")) != record.get("source_inputs_sha256"):
        raise ValueError("build record input digest differs")
    current = create_build_record(root)
    for key in ("app_version", "build_id", "file_version", "git_head"):
        if record.get(key) != current[key]:
            raise ValueError(f"build record {key} differs from current source")
    if record["source_inputs"] != current["source_inputs"]:
        raise ValueError("build source inputs changed; rebuild the frozen application")


def write_build_record(root, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(create_build_record(root), indent=2) + "\n",
                           encoding="utf-8")
    return destination
