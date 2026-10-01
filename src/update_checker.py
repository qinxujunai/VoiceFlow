"""Explicit, integrity-first checks for the public Windows release."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from urllib.request import Request, urlopen


REPOSITORY = "qinxujunai/VoiceFlow"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD_ROOT = f"https://github.com/{REPOSITORY}/releases/download/"
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CHECKSUM_PATTERN = re.compile(r"^([0-9a-fA-F]{64})\s+[* ]?(.+?)\s*$")
MAX_RESPONSE_BYTES = 1024 * 1024


def _read_response(response) -> bytes:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Release response exceeds size limit")
    return data


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
        payload = json.loads(_read_response(response))
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned an invalid release response")
    return payload


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "VoiceFlow-update-check"})
    with urlopen(request, timeout=8) as response:
        return _read_response(response).decode("utf-8")


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
    """Offer only uploaded assets whose GitHub digests match the checksum manifest."""
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

    if not isinstance(payload, dict):
        return _invalid(current, "Release 响应格式无法校验")
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
    asset_map = {}
    for asset in assets:
        if not isinstance(asset, dict) or not asset.get("name"):
            continue
        name = str(asset["name"])
        if name in asset_map:
            return _invalid(current, "Release 资产名称重复", latest)
        asset_map[name] = asset
    installer = asset_map.get(expected_installer)
    checksums = asset_map.get("SHA256SUMS.txt")
    if not installer or not checksums:
        return _invalid(current, "安装包或 SHA256SUMS.txt 缺失", latest)
    for asset in (installer, checksums):
        size = asset.get("size")
        digest = asset.get("digest", "")
        if (
            asset.get("state") != "uploaded"
            or type(size) is not int or size <= 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        ):
            return _invalid(current, "Release 资产未上传完成或缺少可信摘要", latest)

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
    checksum_bytes = checksum_text.encode("utf-8")
    if (
        len(checksum_bytes) != checksums["size"]
        or hashlib.sha256(checksum_bytes).hexdigest() != checksums["digest"][7:]
    ):
        return _invalid(current, "校验文件与 GitHub 资产摘要不一致", latest)

    matches = []
    for line in checksum_text.splitlines():
        match = CHECKSUM_PATTERN.fullmatch(line.strip())
        if match and match.group(2) == expected_installer:
            matches.append(match.group(1).lower())
    if len(matches) != 1:
        return _invalid(current, "发布校验文件没有唯一匹配的安装包摘要", latest)
    if matches[0] != installer["digest"][7:]:
        return _invalid(current, "安装包与校验文件摘要不一致", latest)

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
