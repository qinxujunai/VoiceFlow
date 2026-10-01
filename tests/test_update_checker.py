from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from update_checker import RELEASES_API, check_latest_release


def _payload(version="0.4.0", *, include_checksum=True):
    tag = f"v{version}"
    installer = f"VoiceFlow-{version}-Windows-x64.exe"
    assets = [
        {
            "name": installer,
            "browser_download_url": (
                f"https://github.com/qinxujunai/VoiceFlow/releases/download/"
                f"{tag}/{installer}"
            ),
        }
    ]
    if include_checksum:
        assets.append(
            {
                "name": "SHA256SUMS.txt",
                "browser_download_url": (
                    "https://github.com/qinxujunai/VoiceFlow/releases/download/"
                    f"{tag}/SHA256SUMS.txt"
                ),
            }
        )
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": assets,
    }


def test_update_requires_a_matching_installer_checksum():
    payload = _payload()
    calls = []
    digest = "a" * 64
    installer = "VoiceFlow-0.4.0-Windows-x64.exe"

    def fetch_json(url):
        calls.append(("json", url))
        return payload

    def fetch_text(url):
        calls.append(("text", url))
        return f"{digest}  {installer}\n"

    result = check_latest_release(
        "0.3.3", fetch_json=fetch_json, fetch_text=fetch_text
    )

    assert result.state == "available"
    assert result.latest_version == "0.4.0"
    assert result.installer_sha256 == digest
    assert result.installer_url.endswith(f"/{installer}")
    assert calls[0] == ("json", RELEASES_API)


def test_update_does_not_offer_a_release_without_checksum_asset():
    result = check_latest_release(
        "0.3.3",
        fetch_json=lambda _url: _payload(include_checksum=False),
        fetch_text=lambda _url: "",
    )

    assert result.state == "invalid"
    assert "SHA256SUMS.txt" in result.message
    assert result.installer_url == ""


def test_update_reports_verified_current_release_as_up_to_date():
    payload = _payload("0.3.3")
    installer = "VoiceFlow-0.3.3-Windows-x64.exe"
    result = check_latest_release(
        "0.3.3",
        fetch_json=lambda _url: payload,
        fetch_text=lambda _url: f"{'b' * 64}  *{installer}\n",
    )

    assert result.state == "up_to_date"
    assert result.latest_version == "0.3.3"
    assert result.installer_sha256 == "b" * 64
