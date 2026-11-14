"""When the automatic update check runs, and which versions were already announced.

The check reads only the latest version number (see ``update_checker``), at
most once a day, and only when 设置 → 每天自动检查更新 is on (the default).
State lives next to the user's data in ``update-check.json``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


CHECK_INTERVAL_SECONDS = 24 * 3600
STATE_FILENAME = "update-check.json"


def auto_check_enabled(config_path: str | Path) -> bool:
    """``updates.auto_check`` in config.yaml; on unless the person turned it off."""
    import yaml

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return True
    updates = config.get("updates")
    if not isinstance(updates, dict):
        return True
    return updates.get("auto_check", True) is not False


def _read(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


class UpdateSchedule:
    def __init__(self, data_dir: str | Path, *, clock=time.time) -> None:
        self.path = Path(data_dir) / STATE_FILENAME
        self.clock = clock

    def due(self) -> bool:
        last = _read(self.path).get("last_checked")
        if not isinstance(last, (int, float)):
            return True
        elapsed = self.clock() - float(last)
        # A clock moved backwards also counts as due, so a wrong date never stops checks.
        return elapsed >= CHECK_INTERVAL_SECONDS or elapsed < 0

    def record_check(self) -> None:
        state = _read(self.path)
        state["last_checked"] = self.clock()
        _write(self.path, state)

    def record_available(self, version: str) -> None:
        state = _read(self.path)
        state["available_version"] = version
        _write(self.path, state)

    def available_version(self, current_version: str) -> str:
        """A newer version found by an earlier check, so the tray item survives a restart offline."""
        from update_checker import _version

        version = str(_read(self.path).get("available_version") or "")
        found, current = _version(version), _version(current_version)
        return version if found and current and found > current else ""

    def should_announce(self, version: str) -> bool:
        return bool(version) and _read(self.path).get("announced_version") != version

    def record_announced(self, version: str) -> None:
        state = _read(self.path)
        state["announced_version"] = version
        _write(self.path, state)
