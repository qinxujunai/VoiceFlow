"""Crash-safe staged model activation with exact-config rollback."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

import yaml


class ModelSwitchCoordinator:
    def __init__(self, state_dir: str | Path, config_path: str | Path):
        self.state_dir = Path(state_dir)
        self.config_path = Path(config_path)
        self.pending_path = self.state_dir / "pending.json"
        self.backup_path = self.state_dir / "config.before-switch.yaml"

    def pending(self) -> dict | None:
        try:
            value = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return value if isinstance(value, dict) else None

    def stage(self, *, engine: str, apply: Callable[[], None]) -> dict:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        original = self.config_path.read_bytes()
        previous = str(
            (yaml.safe_load(original.decode("utf-8")) or {})
            .get("engine", {})
            .get("active", "sensevoice")
        )
        self._atomic_write(self.backup_path, original)
        try:
            apply()
            payload = {
                "schema_version": 1,
                "previous_engine": previous,
                "candidate_engine": str(engine),
                "staged_at": time.time(),
                "status": "awaiting_startup_validation",
            }
            self._atomic_write(
                self.pending_path,
                json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            return payload
        except Exception:
            self._atomic_write(self.config_path, original)
            self._unlink(self.backup_path)
            raise

    def commit(self, engine: str) -> bool:
        pending = self.pending()
        if not pending or pending.get("candidate_engine") != str(engine):
            return False
        self._unlink(self.pending_path)
        self._unlink(self.backup_path)
        return True

    def rollback(self, reason: str = "") -> str | None:
        pending = self.pending()
        if not pending or not self.backup_path.is_file():
            return None
        previous = str(pending.get("previous_engine") or "sensevoice")
        backup = self.backup_path.read_bytes()
        self._atomic_write(self.config_path, backup)
        if reason:
            failure = {
                **pending,
                "status": "rolled_back",
                "reason": str(reason),
                "rolled_back_at": time.time(),
            }
            self._atomic_write(
                self.state_dir / "last-failure.json",
                json.dumps(failure, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        self._unlink(self.pending_path)
        self._unlink(self.backup_path)
        return previous

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
