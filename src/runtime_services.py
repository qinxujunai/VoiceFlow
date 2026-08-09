"""Installed-safe model management and diagnostics services."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from model_catalog import profile_for_engine, user_model_profiles
from model_registry import load_model_manifest, verify_model_assets
from model_downloader import DownloadCancelled, PinnedModelDownloader
from runtime_paths import AppPaths, RuntimeMode


ENGINE_ASSET_KEYS = {
    "sensevoice": ("model_path", "tokens_path"),
    "qwen3-asr": (
        "conv_frontend_path",
        "encoder_path",
        "decoder_path",
        "tokenizer_path",
    ),
    "fun-asr-nano": (
        "encoder_adaptor_path",
        "llm_path",
        "embedding_path",
        "tokenizer_path",
    ),
    "whisper-turbo": ("encoder_path", "decoder_path", "tokens_path"),
}


class ModelState(Enum):
    READY = "ready"
    MISSING = "missing"
    CORRUPT = "corrupt"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ModelStatus:
    engine: str
    state: ModelState
    missing: tuple[str, ...]


class ModelManager:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def status(
        self,
        engine: str,
        config: dict[str, Any],
        *,
        verify: bool = False,
    ) -> ModelStatus:
        engine_config = config.get("engine", {}).get(engine, {})
        missing: list[str] = []
        for key in ENGINE_ASSET_KEYS.get(engine, ()):
            raw_path = str(engine_config.get(key, "")).strip()
            resolved = self.paths.resolve_asset(raw_path) if raw_path else None
            if not raw_path or resolved is None or not resolved.exists():
                missing.append(key)
        state = ModelState.READY if engine_config and not missing else ModelState.MISSING
        if state is ModelState.READY and verify:
            try:
                profile = profile_for_engine(engine)
                manifest = load_model_manifest(self.paths.manifest_file)
                model = manifest["models"][profile.model_id]
                model_dir = self.paths.data_dir / profile.target_dir
                if not model_dir.exists():
                    model_dir = self.paths.install_dir / profile.target_dir
                errors = verify_model_assets(model_dir, model)
                if errors:
                    state = ModelState.CORRUPT
                    missing.extend(errors)
            except (KeyError, OSError, ValueError) as error:
                state = ModelState.CORRUPT
                missing.append(str(error))
        return ModelStatus(engine=engine, state=state, missing=tuple(missing))

    def selectable_engines(self, config: dict[str, Any]) -> tuple[str, ...]:
        configured = config.get("engine", {})
        return tuple(
            profile.engine
            for profile in user_model_profiles()
            if isinstance(configured.get(profile.engine), dict)
        )

    def setup_command(self, engine: str) -> tuple[str, ...] | None:
        if self.paths.mode is RuntimeMode.FROZEN:
            return None
        script = self.paths.install_dir / "scripts" / "download_models.py"
        if not script.is_file():
            return None
        executable = self.paths.executable
        if executable.name.lower() == "pythonw.exe":
            console_python = executable.with_name("python.exe")
            if console_python.is_file():
                executable = console_python
        if not executable.name.lower().startswith("python"):
            executable = Path(sys.executable)
        return (
            str(executable),
            str(script),
            "--engine",
            engine,
            "--base-dir",
            str(self.paths.data_dir),
        )

    def open_setup(self, engine: str, config: dict[str, Any]) -> str:
        command = self.setup_command(engine)
        if command is None:
            status = self.status(engine, config)
            if status.state is ModelState.READY:
                return "内置模型已就绪"
            return "安装包内模型缺失，请重新安装 VoiceFlow"

        creationflags = 0x00000010 if os.name == "nt" else 0
        subprocess.Popen(
            command,
            cwd=self.paths.install_dir,
            creationflags=creationflags,
        )
        return "模型管理已打开"

    def start_download(self, engine: str, on_update) -> "ModelDownloadTask":
        task = ModelDownloadTask(self, engine, on_update)
        task.start()
        return task


def downloaded_model_bytes(base_dir: str | Path, target_dir: str) -> int:
    base = Path(base_dir)
    target = base / target_dir
    partial = target.with_name(f"{target.name}.partial")
    archive = partial.with_suffix(".tar.bz2")
    total = archive.stat().st_size if archive.is_file() else 0
    if partial.is_dir():
        total += sum(
            path.stat().st_size
            for path in partial.rglob("*")
            if path.is_file()
        )
    return total


class ModelDownloadTask:
    """Background pinned download with bounded progress and cancellation."""

    def __init__(self, manager: ModelManager, engine: str, on_update):
        self.manager = manager
        self.engine = str(engine)
        self.on_update = on_update
        self._cancelled = threading.Event()
        self._process = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancelled.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def _emit(self, state: ModelState, progress: int, detail: str):
        self.on_update(
            {
                "engine": self.engine,
                "state": state.value,
                "progress": max(0, min(100, int(progress))),
                "detail": str(detail),
            }
        )

    def _run(self):
        try:
            self._emit(ModelState.DOWNLOADING, 0, "正在下载固定版本")
            downloader = PinnedModelDownloader(
                self.manager.paths,
                cancelled=self._cancelled,
                on_progress=lambda progress, detail: self._emit(
                    ModelState.VERIFYING if progress >= 94 else ModelState.DOWNLOADING,
                    progress,
                    detail,
                ),
            )
            downloader.download(self.engine)
            config = yaml.safe_load(
                self.manager.paths.config_file.read_text(encoding="utf-8")
            ) or {}
            status = self.manager.status(self.engine, config, verify=True)
            if status.state is not ModelState.READY:
                self._emit(ModelState.FAILED, 0, "完整性校验未通过")
                return
            self._emit(ModelState.READY, 100, "下载并校验完成")
        except DownloadCancelled:
            self._emit(ModelState.CANCELLED, 0, "下载已取消，可稍后继续")
        except Exception as error:
            self._emit(ModelState.FAILED, 0, f"模型下载失败：{error}")


def _check(name: str, ok: bool, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": "ok" if ok else "missing",
        "detail": detail,
    }


def _display_path(paths: AppPaths, path: Path) -> str:
    resolved = path.resolve()
    for root, label in (
        (paths.data_dir.resolve(), "%VOICEFLOW_DATA%"),
        (paths.install_dir.resolve(), "%VOICEFLOW_INSTALL%"),
    ):
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        return label if not relative.parts else str(Path(label) / relative)
    return resolved.name


def run_runtime_diagnostics(paths: AppPaths) -> dict[str, Any]:
    checks: list[dict[str, str]] = [
        _check("runtime_mode", True, paths.mode.value),
        _check(
            "config",
            paths.config_file.is_file(),
            _display_path(paths, paths.config_file),
        ),
        _check(
            "data_directory",
            paths.data_dir.is_dir() and os.access(paths.data_dir, os.W_OK),
            _display_path(paths, paths.data_dir),
        ),
        _check(
            "logs_directory",
            paths.logs_dir.is_dir(),
            _display_path(paths, paths.logs_dir),
        ),
        _check(
            "knowledge_base",
            paths.knowledge_dir.is_dir(),
            _display_path(paths, paths.knowledge_dir),
        ),
    ]

    config: dict[str, Any] = {}
    if paths.config_file.is_file():
        try:
            config = yaml.safe_load(paths.config_file.read_text(encoding="utf-8")) or {}
        except Exception:
            checks.append(_check("config_parse", False, "无法解析配置文件"))

    active = str(config.get("engine", {}).get("active", "sensevoice"))
    status = ModelManager(paths).status(active, config)
    checks.append(
        _check(
            "active_model",
            status.state is ModelState.READY,
            active if not status.missing else f"{active}: {', '.join(status.missing)}",
        )
    )

    vad = config.get("vad", {})
    if vad.get("enabled", True):
        raw_vad = str(vad.get("model_path", "assets/silero_vad.onnx"))
        vad_path = paths.resolve_asset(raw_vad)
        checks.append(
            _check(
                "vad_model",
                vad_path.is_file(),
                _display_path(paths, vad_path),
            )
        )

    ok = all(item["status"] == "ok" for item in checks)
    return {"ok": ok, "checks": checks}


def format_diagnostics(result: dict[str, Any]) -> str:
    lines = []
    for item in result.get("checks", []):
        label = "正常" if item.get("status") == "ok" else "缺失"
        lines.append(
            f"{label:<4} {item.get('name', ''):<20} {item.get('detail', '')}"
        )
    lines.extend(("", f"VoiceFlow 诊断: {'通过' if result.get('ok') else '需要处理'}"))
    return "\n".join(lines)
