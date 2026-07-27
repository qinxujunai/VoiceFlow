import hashlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from generate_release_assets import generate_release_assets  # noqa: E402


def test_release_assets_include_installer_sbom_and_notices(tmp_path):
    installer = tmp_path / "VoiceFlow-0.2.0-Windows-x64.exe"
    installer.write_bytes(b"voiceflow-installer")
    output_dir = tmp_path / "release"

    assets = generate_release_assets(
        installer=installer,
        output_dir=output_dir,
        version="0.2.0",
    )

    assert {path.name for path in assets} == {
        "SHA256SUMS.txt",
        "SBOM.cdx.json",
        "THIRD_PARTY_NOTICES.md",
    }
    checksum_lines = (output_dir / "SHA256SUMS.txt").read_text(
        encoding="utf-8"
    )
    expected_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
    assert (
        f"{expected_hash}  VoiceFlow-0.2.0-Windows-x64.exe"
        in checksum_lines
    )

    sbom = json.loads((output_dir / "SBOM.cdx.json").read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["metadata"]["component"]["version"] == "0.2.0"
    assert any(
        component["name"] == "sensevoice-small-int8"
        and component["type"] == "machine-learning-model"
        for component in sbom["components"]
    )
