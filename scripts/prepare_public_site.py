"""Render the public site only from a verified, published GitHub Release."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _request(url: str, *, token: str, accept: str) -> bytes:
    headers = {
        "Accept": accept,
        "User-Agent": "VoiceFlow-release-site-renderer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _load_release(path: str | None, *, repository: str, token: str) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    payload = _request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        token=token,
        accept="application/vnd.github+json",
    )
    return json.loads(payload.decode("utf-8"))


def _load_checksums(path: str | None, *, url: str, token: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    payload = _request(
        url,
        token=token,
        accept="application/octet-stream",
    )
    return payload.decode("utf-8")


def _asset_by_name(release: dict, name: str) -> dict:
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"release must contain exactly one asset named {name}")
    asset = matches[0]
    if asset.get("state") != "uploaded":
        raise ValueError(f"release asset is not uploaded: {name}")
    if int(asset.get("size") or 0) <= 0:
        raise ValueError(f"release asset is empty: {name}")
    url = str(asset.get("browser_download_url") or "")
    if not url.startswith("https://"):
        raise ValueError(f"release asset URL is not HTTPS: {name}")
    return asset


def _asset_digest(asset: dict) -> str:
    digest_field = str(asset.get("digest") or "").casefold()
    if not digest_field.startswith("sha256:"):
        raise ValueError(
            f"release asset is missing its GitHub SHA256 digest: {asset.get('name')}"
        )
    digest = digest_field.removeprefix("sha256:")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError(
            f"release asset has an invalid GitHub SHA256 digest: {asset.get('name')}"
        )
    return digest


def _checksum_for(text: str, installer_name: str) -> str:
    matches = []
    for line in text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, filename = parts
        filename = filename.lstrip("*").strip()
        if filename == installer_name:
            matches.append(digest.casefold())
    if len(matches) != 1 or not SHA256_PATTERN.fullmatch(matches[0]):
        raise ValueError("SHA256SUMS must contain exactly one valid installer digest")
    return matches[0]


def _validated_release(
    release: dict,
    *,
    checksums_file: str | None,
    token: str,
) -> dict:
    match = VERSION_PATTERN.fullmatch(str(release.get("tag_name") or ""))
    if match is None:
        raise ValueError("published release tag must use vMAJOR.MINOR.PATCH")
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("site deployment requires a published stable release")

    version = match.group("version")
    installer_name = f"VoiceFlow-{version}-Windows-x64.exe"
    installer = _asset_by_name(release, installer_name)
    checksums = _asset_by_name(release, "SHA256SUMS.txt")
    sbom = _asset_by_name(release, "SBOM.cdx.json")
    notices = _asset_by_name(release, "THIRD_PARTY_NOTICES.md")
    asset_digest = _asset_digest(installer)
    compliance_digests = {
        "SHA256SUMS.txt": _asset_digest(checksums),
        "SBOM.cdx.json": _asset_digest(sbom),
        "THIRD_PARTY_NOTICES.md": _asset_digest(notices),
    }

    checksum_text = _load_checksums(
        checksums_file,
        url=str(checksums["browser_download_url"]),
        token=token,
    )
    published_digest = _checksum_for(checksum_text, installer_name)
    if published_digest != asset_digest:
        raise ValueError("installer digest does not match SHA256SUMS.txt")

    return {
        "version": version,
        "tag": f"v{version}",
        "installer_name": installer_name,
        "installer_url": str(installer["browser_download_url"]),
        "installer_size": int(installer["size"]),
        "sha256": asset_digest,
        "compliance_sha256": compliance_digests,
    }


def _render_site(source_dir: Path, output_dir: Path, metadata: dict) -> None:
    if not source_dir.is_dir():
        raise ValueError(f"site source directory does not exist: {source_dir}")
    if output_dir.exists():
        raise ValueError(f"site output directory already exists: {output_dir}")
    if output_dir.resolve() == source_dir.resolve():
        raise ValueError("site output directory must differ from source")

    shutil.copytree(source_dir, output_dir)
    replacements = {
        "__VOICEFLOW_VERSION__": metadata["version"],
        "__VOICEFLOW_INSTALLER_URL__": metadata["installer_url"],
    }
    replaced = {marker: False for marker in replacements}
    for filename in ("index.html", "app.js"):
        path = output_dir / filename
        content = path.read_text(encoding="utf-8")
        for marker, value in replacements.items():
            if marker in content:
                replaced[marker] = True
                content = content.replace(marker, value)
        if "__VOICEFLOW_" in content:
            raise ValueError(f"unresolved release marker remains in {filename}")
        path.write_text(content, encoding="utf-8")
    missing = [marker for marker, found in replaced.items() if not found]
    if missing:
        raise ValueError(f"required release markers missing: {', '.join(missing)}")

    (output_dir / "release-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default=str(PROJECT_ROOT / "site"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--release-json")
    parser.add_argument("--checksums-file")
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", "qinxujunai/VoiceFlow"),
    )
    args = parser.parse_args()

    token = os.environ.get("VOICEFLOW_GITHUB_TOKEN", "")
    try:
        release = _load_release(
            args.release_json,
            repository=args.repository,
            token=token,
        )
        metadata = _validated_release(
            release,
            checksums_file=args.checksums_file,
            token=token,
        )
        _render_site(Path(args.site_dir), Path(args.output_dir), metadata)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"public site render failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
