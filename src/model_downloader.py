"""Explicit, cancellable pinned-model downloads for source and frozen builds."""

from __future__ import annotations

import re
import tarfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from model_catalog import profile_for_engine
from model_registry import load_model_manifest, sha256_file, verify_model_assets


class DownloadCancelled(RuntimeError):
    pass


_REVISION = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _safe_relative_path(raw: str) -> Path:
    value = Path(str(raw).replace("\\", "/"))
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise RuntimeError(f"unsafe model asset path: {raw}")
    return value


def _validate_download_url(raw: str) -> str:
    parsed = urllib.parse.urlparse(str(raw))
    host = (parsed.hostname or "").casefold()
    allowed = (
        host == "github.com"
        or host == "huggingface.co"
        or host.endswith(".githubusercontent.com")
        or host.endswith(".huggingface.co")
        or host.endswith(".hf.co")
        or host.endswith(".xethub.hf.co")
    )
    if parsed.scheme != "https" or not allowed or parsed.username or parsed.password:
        raise RuntimeError("model download URL is not allowlisted")
    return parsed.geturl()


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            _validate_download_url(newurl),
        )


class PinnedModelDownloader:
    def __init__(self, paths, *, cancelled, on_progress):
        self.paths = paths
        self.cancelled = cancelled
        self.on_progress = on_progress
        self.manifest = load_model_manifest(paths.manifest_file)
        self._completed_bytes = 0

    def download(self, engine: str) -> Path:
        profile = profile_for_engine(engine)
        model = self.manifest["models"][profile.model_id]
        if str(model.get("target_dir")) != profile.target_dir:
            raise RuntimeError("manifest target does not match the product catalog")
        target = self.paths.data_dir / _safe_relative_path(profile.target_dir)
        if target.exists() and not verify_model_assets(target, model):
            self.on_progress(100, "模型已通过 SHA-256 校验")
            return target
        partial = target.with_name(f"{target.name}.partial")
        partial.mkdir(parents=True, exist_ok=True)
        source = model["source"]
        if source.get("provider") == "github_release_archive":
            self._download_archive(model, partial)
        elif source.get("provider") == "huggingface":
            self._download_huggingface(model, partial)
        else:
            raise RuntimeError("unsupported pinned model provider")
        self._check_cancelled()
        errors = verify_model_assets(partial, model)
        if errors:
            raise RuntimeError("; ".join(errors))
        self.on_progress(97, "正在原子切换模型目录")
        self._activate(partial, target)
        self.on_progress(100, "下载并校验完成")
        return target

    def _download_huggingface(self, model: dict, partial: Path) -> None:
        source = model["source"]
        total = sum(int(asset["size"]) for asset in model["files"])
        self._completed_bytes = 0
        for asset in model["files"]:
            self._check_cancelled()
            asset_path = _safe_relative_path(asset["path"])
            destination = partial / asset_path
            if (
                destination.is_file()
                and destination.stat().st_size == int(asset["size"])
                and sha256_file(destination).lower() == asset["sha256"].lower()
            ):
                self._completed_bytes += int(asset["size"])
                self._report_bytes(self._completed_bytes, total, "正在下载固定版本")
                continue
            repository = str(source.get("repo_id", ""))
            revision = str(source.get("revision", ""))
            if not _REPOSITORY.fullmatch(repository) or not _REVISION.fullmatch(revision):
                raise RuntimeError("invalid pinned Hugging Face source")
            encoded_path = urllib.parse.quote(asset_path.as_posix(), safe="/")
            url = (
                f"https://huggingface.co/{repository}/resolve/"
                f"{revision}/{encoded_path}?download=true"
            )
            self._download_file(
                url,
                destination,
                expected_size=int(asset["size"]),
                base_completed=self._completed_bytes,
                total=total,
            )
            if sha256_file(destination).lower() != asset["sha256"].lower():
                raise RuntimeError(f"sha256 mismatch: {asset['path']}")
            self._completed_bytes += int(asset["size"])

    def _download_archive(self, model: dict, partial: Path) -> None:
        source = model["source"]
        archive = partial.with_suffix(".tar.bz2")
        self._download_file(
            _validate_download_url(source["url"]),
            archive,
            expected_size=int(source["archive_size"]),
            base_completed=0,
            total=int(source["archive_size"]),
        )
        if sha256_file(archive).lower() != source["archive_sha256"].lower():
            raise RuntimeError("archive sha256 mismatch")
        self.on_progress(94, "正在安全解压模型")
        root = source["archive_root"].rstrip("/")
        with tarfile.open(archive, "r:bz2") as bundle:
            members = {
                member.name.removeprefix("./"): member
                for member in bundle.getmembers()
            }
            for asset in model["files"]:
                self._check_cancelled()
                asset_path = _safe_relative_path(asset["path"])
                name = f"{root}/{asset_path.as_posix()}"
                member = members.get(name)
                if member is None or not member.isfile():
                    raise RuntimeError(f"archive member not found: {name}")
                destination = partial / asset_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                source_file = bundle.extractfile(member)
                if source_file is None:
                    raise RuntimeError(f"cannot read archive member: {name}")
                with source_file, destination.open("wb") as output:
                    while True:
                        self._check_cancelled()
                        chunk = source_file.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
        archive.unlink(missing_ok=True)

    def _download_file(
        self,
        url: str,
        destination: Path,
        *,
        expected_size: int,
        base_completed: int,
        total: int,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        offset = destination.stat().st_size if destination.is_file() else 0
        if offset > expected_size:
            destination.unlink()
            offset = 0
        headers = {"User-Agent": "VoiceFlow-ModelCenter/1"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(_validate_download_url(url), headers=headers)
        opener = urllib.request.build_opener(_AllowlistedRedirectHandler())
        with opener.open(request, timeout=45) as response:
            resumed = offset > 0 and getattr(response, "status", None) == 206
            if offset and not resumed:
                offset = 0
            mode = "ab" if resumed else "wb"
            with destination.open(mode) as output:
                downloaded = offset
                while True:
                    self._check_cancelled()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > expected_size:
                        raise RuntimeError("download exceeded pinned size")
                    self._report_bytes(
                        base_completed + downloaded,
                        total,
                        "正在下载固定版本",
                    )
        if destination.stat().st_size != expected_size:
            raise RuntimeError(
                f"download size mismatch: expected={expected_size} "
                f"actual={destination.stat().st_size}"
            )

    def _activate(self, partial: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if target.exists():
            backup = target.with_name(
                f"{target.name}.previous-{time.strftime('%Y%m%d-%H%M%S')}"
            )
            target.rename(backup)
        try:
            partial.rename(target)
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                backup.rename(target)
            raise

    def _report_bytes(self, current: int, total: int, detail: str) -> None:
        progress = 0 if total <= 0 else min(93, round(current * 93 / total))
        self.on_progress(progress, detail)

    def _check_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise DownloadCancelled("download cancelled")
