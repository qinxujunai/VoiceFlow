"""Small, comment-preserving runtime settings updates for config.yaml."""

from __future__ import annotations

import os
import plistlib
import re
import sys
import threading
import copy
from dataclasses import asdict
from functools import wraps
from pathlib import Path


MACOS_LAUNCH_AGENT_LABEL = "ai.voiceflow.app"
_config_update_lock = threading.RLock()


def save_settings_transaction(paths, preferences, payload):
    """Commit one viewed draft, retaining old values on any write failure."""
    import yaml
    from dictation_preferences import PreferencesChangedError, normalize_app_id

    engine, language = payload["engine"], payload["language"]
    device = payload["device_index"]
    enabled = payload["autostart"]
    if (engine != "sensevoice" or language not in {"auto", "zh", "en", "ja", "ko", "yue"}
            or isinstance(device, bool) or device is not None and (not isinstance(device, int) or device < 0)
            or not isinstance(enabled, bool)):
        raise ValueError("invalid runtime settings")
    draft = payload["preferences"]
    if draft.get("schema_version") != 1 or not isinstance(draft.get("apps"), dict) or len(draft["apps"]) > 128:
        raise ValueError("invalid preferences schema")
    candidate = {"schema_version": 1, "global": asdict(preferences._validate_options(draft["global"])),
                 "apps": {normalize_app_id(key): asdict(preferences._validate_options(value))
                          for key, value in draft["apps"].items()}}
    with _config_update_lock, preferences._write_lock:
        before = paths.config_file.read_bytes()
        config_text = before.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if config_text != payload["expected_config"] or preferences.snapshot() != payload["expected_preferences"]:
            raise PreferencesChangedError("settings changed; reload before saving")
        config = yaml.safe_load(config_text) or {}
        restart = (config.get("engine", {}).get(engine, {}).get("language") != language
                   or config.get("audio", {}).get("device_index") != device)
        previous_autostart = is_autostart_enabled(paths)
        autostart_snapshot = read_autostart_state()
        try:
            if restart:
                update_runtime_settings(paths.config_file, engine=engine, language=language, device_index=device)
            if enabled != previous_autostart:
                set_autostart(paths, enabled)
            preferences._write(candidate)
        except Exception:
            rollback_errors = []
            try:
                temporary = paths.config_file.with_suffix(".rollback.tmp")
                temporary.write_bytes(before)
                os.replace(temporary, paths.config_file)
            except Exception as error:
                rollback_errors.append(str(error))
            if enabled != previous_autostart:
                try:
                    restore_autostart_state(autostart_snapshot)
                except Exception as error:
                    rollback_errors.append(str(error))
            if rollback_errors:
                raise RuntimeError("settings rollback failed: " + "; ".join(rollback_errors))
            raise
        with preferences._lock:
            preferences._payload = copy.deepcopy(candidate)
            preferences.load_error = False
        return {"restart_required": restart, "preferences": candidate,
                "config_text": paths.config_file.read_text(encoding="utf-8")}


def _serialized_config_update(update):
    @wraps(update)
    def locked(*args, **kwargs):
        with _config_update_lock:
            return update(*args, **kwargs)
    return locked


def _yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{str(value).replace(chr(34), chr(92) + chr(34))}"'


def _replace_section_value(text: str, section: str, key: str, value) -> str:
    section_match = re.search(rf"(?m)^  {re.escape(section)}:\s*$", text)
    if not section_match:
        raise KeyError(f"missing config section: {section}")
    next_section = re.search(r"(?m)^  \S[^:]*:\s*$", text[section_match.end():])
    end = section_match.end() + next_section.start() if next_section else len(text)
    block = text[section_match.end():end]
    replacement = f"    {key}: {_yaml_scalar(value)}"
    updated, count = re.subn(
        rf"(?m)^    {re.escape(key)}:\s*[^#\r\n]*(?P<comment>\s+#.*)?$",
        lambda match: replacement + (match.group("comment") or ""),
        block,
        count=1,
    )
    if not count:
        updated = f"\n{replacement}" + block
    return text[:section_match.end()] + updated + text[end:]


@_serialized_config_update
def update_runtime_settings(
    config_path: str | Path,
    *,
    engine: str,
    language: str,
    device_index: int | None,
) -> None:
    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r'(?m)^(  active:\s*)["\'][^"\']+["\'](?P<comment>\s*(?:#.*)?)$',
        lambda match: f'{match.group(1)}"{engine}"{match.group("comment")}',
        text,
        count=1,
    )
    if count != 1:
        raise KeyError("missing engine.active")
    text = _replace_section_value(text, engine, "language", language)

    audio_match = re.search(r"(?m)^audio:\s*$", text)
    if not audio_match:
        raise KeyError("missing audio section")
    next_top = re.search(r"(?m)^\S[^:]*:\s*$", text[audio_match.end():])
    end = audio_match.end() + next_top.start() if next_top else len(text)
    block = text[audio_match.end():end]
    replacement = f"  device_index: {_yaml_scalar(device_index)}"
    block, count = re.subn(
        r"(?m)^  device_index:\s*[^#\r\n]*(?P<comment>\s+#.*)?$",
        lambda match: replacement + (match.group("comment") or ""),
        block,
        count=1,
    )
    if not count:
        block = f"\n{replacement}" + block
    text = text[:audio_match.end()] + block + text[end:]

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def onboarding_completed(config_path: str | Path) -> bool:
    import yaml

    try:
        config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return bool(config.get("ui", {}).get("onboarding_completed", False))


@_serialized_config_update
def set_onboarding_completed(config_path: str | Path, completed: bool = True) -> None:
    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    ui_match = re.search(r"(?m)^ui:\s*$", text)
    replacement = f"  onboarding_completed: {_yaml_scalar(completed)}"
    if ui_match:
        next_top = re.search(r"(?m)^\S[^:]*:\s*$", text[ui_match.end():])
        end = ui_match.end() + next_top.start() if next_top else len(text)
        block = text[ui_match.end():end]
        block, count = re.subn(
            r"(?m)^  onboarding_completed:\s*[^#\r\n]*"
            r"(?P<comment>\s+#.*)?$",
            lambda match: replacement + (match.group("comment") or ""),
            block,
            count=1,
        )
        if not count:
            block = f"\n{replacement}" + block
        text = text[:ui_match.end()] + block + text[end:]
    else:
        separator = "" if text.endswith(("\n", "\r")) else "\n"
        text = f"{text}{separator}\nui:\n{replacement}\n"

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def autostart_command(root) -> str:
    mode = getattr(getattr(root, "mode", None), "value", None)
    if mode == "frozen":
        return f'"{Path(root.executable).resolve()}"'

    root_path = Path(getattr(root, "install_dir", root))
    runtime_executable = getattr(root, "executable", None)
    if runtime_executable:
        pythonw = Path(runtime_executable)
        if pythonw.name.lower() == "python.exe":
            windowed = pythonw.with_name("pythonw.exe")
            if windowed.exists():
                pythonw = windowed
    else:
        pythonw = root_path / "venv" / "Scripts" / "pythonw.exe"
    launcher = root_path / "scripts" / "launch_voiceflow.pyw"
    return f'"{pythonw}" "{launcher}"'


def _macos_launch_agent_path(home: str | Path | None = None) -> Path:
    home_dir = Path.home() if home is None else Path(home)
    return home_dir / "Library" / "LaunchAgents" / f"{MACOS_LAUNCH_AGENT_LABEL}.plist"


def _macos_program_arguments(root) -> list[str]:
    mode = getattr(getattr(root, "mode", None), "value", None)
    if mode == "frozen":
        return [str(Path(root.executable).resolve())]
    install_dir = Path(getattr(root, "install_dir", root)).resolve()
    executable = Path(getattr(root, "executable", sys.executable)).resolve()
    return [str(executable), str(install_dir / "src" / "main.py")]


def _macos_launch_agent_payload(root) -> dict:
    install_dir = Path(getattr(root, "install_dir", root)).resolve()
    return {
        "Label": MACOS_LAUNCH_AGENT_LABEL,
        "ProgramArguments": _macos_program_arguments(root),
        "RunAtLoad": True,
        "KeepAlive": False,
        "WorkingDirectory": str(install_dir),
        "ProcessType": "Interactive",
    }


def is_autostart_enabled(root) -> bool:
    if sys.platform == "darwin":
        path = _macos_launch_agent_path()
        try:
            with path.open("rb") as handle:
                payload = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException):
            return False
        return payload.get("ProgramArguments") == _macos_program_arguments(root)
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "VoiceFlow")
        return value == autostart_command(root)
    except OSError:
        return False


def read_autostart_state():
    if sys.platform == "darwin":
        path = _macos_launch_agent_path()
        return path.read_bytes() if path.exists() else None
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                return winreg.QueryValueEx(key, "VoiceFlow")
        except FileNotFoundError:
            return None
    return None


def restore_autostart_state(snapshot):
    if sys.platform == "darwin":
        path = _macos_launch_agent_path()
        if snapshot is None:
            path.unlink(missing_ok=True)
        else:
            temporary = path.with_suffix(".rollback.tmp")
            temporary.write_bytes(snapshot)
            os.replace(temporary, path)
    elif sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            if snapshot is None:
                try:
                    winreg.DeleteValue(key, "VoiceFlow")
                except FileNotFoundError:
                    pass
            else:
                value, value_type = snapshot
                winreg.SetValueEx(key, "VoiceFlow", 0, value_type, value)


def set_autostart(root, enabled: bool) -> None:
    if sys.platform == "darwin":
        path = _macos_launch_agent_path()
        if not enabled:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".plist.tmp")
        with temporary.open("wb") as handle:
            plistlib.dump(_macos_launch_agent_payload(root), handle, sort_keys=False)
        os.replace(temporary, path)
        return
    if sys.platform != "win32":
        return
    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                "VoiceFlow",
                0,
                winreg.REG_SZ,
                autostart_command(root),
            )
        else:
            try:
                winreg.DeleteValue(key, "VoiceFlow")
            except FileNotFoundError:
                pass
