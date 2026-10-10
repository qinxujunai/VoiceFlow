"""Local, live sentence-end preferences with explicit executable scope."""

from __future__ import annotations

import copy
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from punctuation import SENTENCE_END_CHOICES


_MODES = {value for value, _label in SENTENCE_END_CHOICES}
_UNSET = object()
_FORMAT_APPS = {"code.exe", "windowsterminal.exe", "powershell.exe", "pwsh.exe",
                "cmd.exe", "pycharm64.exe"}


def application_preserves_format(app_id: str) -> bool:
    return str(app_id or "").casefold() in _FORMAT_APPS


def normalize_app_id(value: str) -> str:
    name = str(value or "").casefold()
    if (not name or len(name) > 128 or not name.endswith(".exe")
            or any(character in name for character in "\\/:\r\n\x00")):
        raise ValueError("invalid application identity")
    return name


@dataclass(frozen=True)
class DictationOptions:
    sentence_end: str = "preserve"
    preserve_format: bool = False


class PreferencesChangedError(ValueError):
    """The viewed scope changed before its replacement could be saved."""


class DictationPreferencesStore:
    def __init__(self, path: str | Path, *, legacy_output=None):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        legacy = (legacy_output or {}).get("auto_period") is True
        self._payload = {"schema_version": 1,
                         "global": asdict(DictationOptions("complete_period" if legacy else "preserve")),
                         "apps": {}}
        self.load_error = False
        try:
            if self.path.exists():
                if self.path.stat().st_size > 1024 * 1024:
                    raise ValueError("preferences exceed size limit")
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                    raise ValueError("invalid preferences schema")
                self._validate_options(payload["global"])
                apps = payload["apps"]
                if not isinstance(apps, dict) or len(apps) > 128:
                    raise ValueError("invalid application preferences")
                normalized = {}
                for app_id, options in apps.items():
                    normalized[normalize_app_id(app_id)] = asdict(self._validate_options(options))
                self._payload = {"schema_version": 1,
                                 "global": asdict(self._validate_options(payload["global"])),
                                 "apps": normalized}
            else:
                self._write(self._payload)
        except (OSError, ValueError, KeyError, TypeError):
            self.load_error = True
            self._payload = {"schema_version": 1, "global": asdict(DictationOptions()), "apps": {}}

    @staticmethod
    def _validate_options(options) -> DictationOptions:
        if (not isinstance(options, dict) or options.get("sentence_end") not in _MODES
                or not isinstance(options.get("preserve_format"), bool)):
            raise ValueError("invalid dictation preferences")
        return DictationOptions(options["sentence_end"], options["preserve_format"])

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._payload)

    def options_for(self, app_id: str, *, terminal=False) -> DictationOptions:
        try:
            identity = normalize_app_id(app_id)
        except ValueError:
            identity = ""
        with self._lock:
            options = self._payload["apps"].get(identity)
            if options is not None:
                return self._validate_options(options)
            global_options = self._validate_options(self._payload["global"])
            return DictationOptions(global_options.sentence_end,
                                    global_options.preserve_format or terminal or application_preserves_format(identity))

    def update(self, *, sentence_end=None, preserve_format=None, app_id=None,
               follow_default=False, expected=_UNSET) -> dict:
        identity = normalize_app_id(app_id) if app_id is not None else None
        if follow_default and identity is None:
            raise ValueError("only application overrides can follow the default")
        options = None if follow_default else self._validate_options(
            {"sentence_end": sentence_end, "preserve_format": preserve_format})
        with self._write_lock:
            with self._lock:
                candidate = copy.deepcopy(self._payload)
            current = candidate["global"] if identity is None else candidate["apps"].get(identity)
            if expected is not _UNSET and current != expected:
                raise PreferencesChangedError("dictation preferences changed")
            if follow_default:
                candidate["apps"].pop(identity, None)
            elif identity is None:
                candidate["global"] = asdict(options)
            else:
                if identity not in candidate["apps"] and len(candidate["apps"]) >= 128:
                    raise ValueError("application preference limit reached")
                candidate["apps"][identity] = asdict(options)
            self._write(candidate)
            with self._lock:
                self._payload = candidate
                self.load_error = False
                return copy.deepcopy(candidate)

    def _write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
