from __future__ import annotations

import hashlib
import shutil
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_archive_model_download_extracts_only_pinned_verified_assets(
    monkeypatch,
    tmp_path,
):
    import download_models

    source = tmp_path / "source"
    archive_root = source / "upstream-model"
    archive_root.mkdir(parents=True)
    (archive_root / "model.int8.onnx").write_bytes(b"pinned-model")
    (archive_root / "tokens.txt").write_bytes(b"pinned-tokens")
    (archive_root / "ignored.bin").write_bytes(b"must-not-be-extracted")
    archive = tmp_path / "preview.tar.bz2"
    with tarfile.open(archive, "w:bz2") as bundle:
        bundle.add(archive_root, arcname="upstream-model")

    def asset(path):
        return {
            "path": path.name,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }

    download_models.MANIFEST = {
        "models": {
            "preview": {
                "target_dir": "models/preview",
                "source": {
                    "provider": "github_release_archive",
                    "url": "https://example.invalid/preview.tar.bz2",
                    "archive_root": "upstream-model",
                    "archive_size": archive.stat().st_size,
                    "archive_sha256": _sha256(archive),
                },
                "files": [
                    asset(archive_root / "model.int8.onnx"),
                    asset(archive_root / "tokens.txt"),
                ],
            }
        }
    }
    monkeypatch.setattr(
        download_models.urllib.request,
        "urlretrieve",
        lambda _url, destination: shutil.copy2(archive, destination),
    )
    target_root = tmp_path / "install"

    assert download_models._download_archive_model(target_root, "preview")
    target = target_root / "models" / "preview"
    assert (target / "model.int8.onnx").read_bytes() == b"pinned-model"
    assert (target / "tokens.txt").read_bytes() == b"pinned-tokens"
    assert not (target / "ignored.bin").exists()
