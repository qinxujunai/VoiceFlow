"""Installed-safe model management and diagnostics services."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

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


@dataclass(frozen=True)
class ModelStatus:
    engine: str
    state: ModelState
    missing: tuple[str, ...]


class ModelManager:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def status(self, engine: str, config: dict[str, Any]) -> ModelStatus:
        engine_config = config.get("engine", {}).get(engine, {})
        missing: list[str] = []
        for key in ENGINE_ASSET_KEYS.get(engine, ()):
            raw_path = str(engine_config.get(key, "")).strip()
            resolved = self.paths.resolve_asset(raw_path) if raw_path else None
            if not raw_path or resolved is None or not resolved.exists():
                missing.append(key)
        state = ModelState.READY if engine_config and not missing else ModelState.MISSING
        return ModelStatus(engine=engine, state=state, missing=tuple(missing))

    def selectable_engines(self, config: dict[str, Any]) -> tuple[str, ...]:
        engine_config = config.get("engine", {})
        configured = tuple(
            name
            for name, value in engine_config.items()
            if name != "active" and isinstance(value, dict)
        )
        if self.paths.mode is RuntimeMode.SOURCE:
            return configured

        ready = tuple(
            name
            for name in configured
            if self.status(name, config).state is ModelState.READY
        )
        if ready:
            return ready
        active = str(engine_config.get("active", "sensevoice"))
        return (active,) if active in configured else ()

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
