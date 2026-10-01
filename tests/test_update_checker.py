from __future__ import annotations

import sys
import hashlib
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from update_checker import RELEASES_API, check_latest_release


def _payload(version="0.4.0", *, include_checksum=True, digest="a" * 64, text=None):
    tag = f"v{version}"
    installer = f"VoiceFlow-{version}-Windows-x64.exe"
    text = text if text is not None else f"{digest}  {installer}\n"
    assets = [
        {
            "name": installer,
            "state": "uploaded",
            "size": 100,
            "digest": f"sha256:{digest}",
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
                "state": "uploaded",
                "size": len(text.encode("utf-8")),
                "digest": f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}",
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
    installer = "VoiceFlow-0.3.3-Windows-x64.exe"
    text = f"{'b' * 64}  *{installer}\n"
    payload = _payload("0.3.3", digest="b" * 64, text=text)
    result = check_latest_release(
        "0.3.3",
        fetch_json=lambda _url: payload,
        fetch_text=lambda _url: text,
    )

    assert result.state == "up_to_date"
    assert result.latest_version == "0.3.3"
    assert result.installer_sha256 == "b" * 64


@pytest.mark.parametrize("change", ["installer_digest", "checksum_digest", "size", "state", "duplicate"])
def test_update_rejects_inconsistent_or_incomplete_assets(change):
    payload = _payload()
    if change == "duplicate":
        payload["assets"].append(dict(payload["assets"][0]))
    elif change == "installer_digest":
        payload["assets"][0]["digest"] = "sha256:" + "b" * 64
    elif change == "checksum_digest":
        payload["assets"][1]["digest"] = "sha256:" + "b" * 64
    elif change == "size":
        payload["assets"][0]["size"] = 0
    else:
        payload["assets"][0]["state"] = "new"
    result = check_latest_release(
        "0.3.3", fetch_json=lambda _: payload,
        fetch_text=lambda _: f"{'a' * 64}  VoiceFlow-0.4.0-Windows-x64.exe\n",
    )
    assert result.state == "invalid"
    assert not result.installer_url


def test_release_response_is_bounded_and_malformed_payload_is_rejected():
    from io import BytesIO
    from update_checker import MAX_RESPONSE_BYTES, _read_response

    with pytest.raises(ValueError):
        _read_response(BytesIO(b"x" * (MAX_RESPONSE_BYTES + 1)))
    assert check_latest_release("0.3.3", fetch_json=lambda _: []).state == "invalid"
