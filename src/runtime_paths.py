"""Runtime path discovery and non-destructive user-data migration."""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


DATA_SCHEMA_VERSION = 1


class RuntimeMode(Enum):
    SOURCE = "source"
    FROZEN = "frozen"


@dataclass(frozen=True)
class MigrationReport:
    schema_version: int
    copied: tuple[str, ...]


@dataclass(frozen=True)
class AppPaths:
    """Separates immutable application resources from writable user data."""

    mode: RuntimeMode
    install_dir: Path
    data_dir: Path
    executable: Path
    config_override: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "install_dir", Path(self.install_dir).resolve())
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        object.__setattr__(self, "executable", Path(self.executable).resolve())
        if self.config_override is not None:
            object.__setattr__(
                self,
                "config_override",
                Path(self.config_override).resolve(),
            )

    @classmethod
    def discover(
        cls,
        config_path: str | Path | None = None,
        *,
        frozen: bool | None = None,
        install_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
        executable: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> AppPaths:
        is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        if config_path is not None:
            config = Path(config_path).resolve()
            root = config.parent
            return cls(
                mode=RuntimeMode.FROZEN if is_frozen else RuntimeMode.SOURCE,
                install_dir=Path(install_dir).resolve() if install_dir else root,
                data_dir=Path(data_dir).resolve() if data_dir else root,
                executable=Path(executable).resolve() if executable else Path(sys.executable),
                config_override=config,
            )

        mode = RuntimeMode.FROZEN if is_frozen else RuntimeMode.SOURCE
        resolved_executable = Path(executable or sys.executable).resolve()
        if install_dir is None:
            if is_frozen:
                install_dir = Path(
                    getattr(sys, "_MEIPASS", resolved_executable.parent)
                )
            else:
                install_dir = Path(__file__).resolve().parents[1]

        if data_dir is None:
            env = os.environ if environ is None else environ
            local_app_data = env.get("LOCALAPPDATA")
            if local_app_data:
                data_dir = Path(local_app_data) / "VoiceFlow"
            else:
                data_dir = Path.home() / "AppData" / "Local" / "VoiceFlow"

        return cls(
            mode=mode,
            install_dir=Path(install_dir),
            data_dir=Path(data_dir),
            executable=resolved_executable,
        )

    @property
    def config_file(self) -> Path:
        return self.config_override or self.data_dir / "config.yaml"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def history_file(self) -> Path:
        return self.logs_dir / "history.jsonl"

    @property
    def legacy_history_file(self) -> Path:
        return self.logs_dir / "history.txt"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge-base"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def schema_file(self) -> Path:
        return self.data_dir / "runtime-state.json"

    @property
    def manifest_file(self) -> Path:
        return self.install_dir / "model-manifest.json"

    @property
    def asset_roots(self) -> tuple[Path, ...]:
        if self.data_dir == self.install_dir:
            return (self.data_dir,)
        return (self.data_dir, self.install_dir)

    def resolve_asset(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        for root in self.asset_roots:
            candidate = root / path
            if candidate.exists():
                return candidate
        return self.data_dir / path

    def install_resource(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else self.install_dir / path


def _copy_if_missing(source: Path, destination: Path) -> bool:
    if not source.is_file() or destination.exists():
        return False
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.migrating")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return True


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def prepare_runtime_layout(
    paths: AppPaths,
    *,
    legacy_root: str | Path | None = None,
) -> MigrationReport:
    """Create writable directories and copy legacy user data without overwrites.

    Model files are deliberately not copied. ``resolve_asset`` keeps an existing
    source-tree or bundled model usable while all future writable model storage
    lives under ``data_dir/models``.
    """

    legacy = Path(legacy_root).resolve() if legacy_root else paths.install_dir
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.knowledge_dir.mkdir(parents=True, exist_ok=True)
    paths.models_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    if _copy_if_missing(legacy / "config.yaml", paths.config_file):
        copied.append("config.yaml")
    if not paths.config_file.is_file():
        raise FileNotFoundError(
            f"VoiceFlow runtime config is missing: {paths.config_file}"
        )

    legacy_knowledge = legacy / "knowledge-base"
    if legacy_knowledge.is_dir():
        for source in sorted(path for path in legacy_knowledge.rglob("*") if path.is_file()):
            relative = source.relative_to(legacy)
            destination = paths.data_dir / relative
            if _copy_if_missing(source, destination):
                copied.append(relative.as_posix())

    for filename in ("history.jsonl", "history.txt"):
        source = legacy / "logs" / filename
        destination = paths.logs_dir / filename
        if _copy_if_missing(source, destination):
            copied.append(f"logs/{filename}")

    _write_json_atomic(
        paths.schema_file,
        {
            "schema_version": DATA_SCHEMA_VERSION,
            "install_dir": str(paths.install_dir),
            "runtime_mode": paths.mode.value,
        },
    )
    return MigrationReport(
        schema_version=DATA_SCHEMA_VERSION,
        copied=tuple(copied),
    )
