"""Explicit, integrity-first checks for the public Windows release."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.request import Request, urlopen


REPOSITORY = "qinxujunai/VoiceFlow"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD_ROOT = f"https://github.com/{REPOSITORY}/releases/download/"
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CHECKSUM_PATTERN = re.compile(r"^([0-9a-fA-F]{64})\s+[* ]?(.+?)\s*$")


@dataclass(frozen=True)
class UpdateResult:
    state: str
    current_version: str
    latest_version: str = ""
    installer_url: str = ""
    installer_sha256: str = ""
    message: str = ""

    def as_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}


def _version(value: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.fullmatch(str(value).removeprefix("v"))
    return tuple(int(part) for part in match.groups()) if match else None


def _fetch_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "VoiceFlow-update-check",
        },
    )
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned an invalid release response")
    return payload


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "VoiceFlow-update-check"})
    with urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8")


def _invalid(current: str, message: str, latest: str = "") -> UpdateResult:
    return UpdateResult(
        state="invalid",
        current_version=current,
        latest_version=latest,
        message=message,
    )


def check_latest_release(
    current_version: str,
    *,
    fetch_json=_fetch_json,
    fetch_text=_fetch_text,
) -> UpdateResult:
    """Return an update only when the public installer checksum is present."""
    current = str(current_version).removeprefix("v")
    if _version(current) is None:
        return _invalid(current, "当前版本号无法校验")
    try:
        payload = fetch_json(RELEASES_API)
    except Exception as error:
        return UpdateResult(
            state="unavailable",
            current_version=current,
            message=f"暂时无法检查更新：{type(error).__name__}",
        )

    tag = str(payload.get("tag_name", ""))
    latest = tag.removeprefix("v")
    latest_tuple = _version(latest)
    if latest_tuple is None or not tag.startswith("v"):
        return _invalid(current, "最新 Release 的版本号无法校验", latest)
    if payload.get("draft") or payload.get("prerelease"):
        return _invalid(current, "最新 Release 不是稳定版本", latest)

    assets = payload.get("assets")
    if not isinstance(assets, list):
        return _invalid(current, "最新 Release 缺少可验证资产", latest)
    expected_installer = f"VoiceFlow-{latest}-Windows-x64.exe"
    asset_map = {
        str(asset.get("name")): asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("name")
    }
    installer = asset_map.get(expected_installer)
    checksums = asset_map.get("SHA256SUMS.txt")
    if not installer or not checksums:
        return _invalid(current, "安装包或 SHA256SUMS.txt 缺失", latest)

    installer_url = str(installer.get("browser_download_url", ""))
    checksum_url = str(checksums.get("browser_download_url", ""))
    expected_prefix = f"{DOWNLOAD_ROOT}{tag}/"
    if (
        installer_url != f"{expected_prefix}{expected_installer}"
        or checksum_url != f"{expected_prefix}SHA256SUMS.txt"
    ):
        return _invalid(current, "Release 下载地址与版本标签不匹配", latest)
    try:
        checksum_text = fetch_text(checksum_url)
    except Exception as error:
        return _invalid(current, f"无法读取发布校验文件：{type(error).__name__}", latest)

    matches = []
    for line in checksum_text.splitlines():
        match = CHECKSUM_PATTERN.fullmatch(line.strip())
        if match and match.group(2) == expected_installer:
            matches.append(match.group(1).lower())
    if len(matches) != 1:
        return _invalid(current, "发布校验文件没有唯一匹配的安装包摘要", latest)

    if latest_tuple <= _version(current):
        return UpdateResult(
            state="up_to_date",
            current_version=current,
            latest_version=latest,
            installer_url=installer_url,
            installer_sha256=matches[0],
            message="已是最新稳定版本，安装包校验信息完整。",
        )
    return UpdateResult(
        state="available",
        current_version=current,
        latest_version=latest,
        installer_url=installer_url,
        installer_sha256=matches[0],
        message="发现新版本，安装包和 SHA-256 已核对。",
    )
