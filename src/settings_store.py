"""Small, comment-preserving runtime settings updates for config.yaml."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


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


def autostart_command(root: str | Path) -> str:
    root_path = Path(root)
    pythonw = root_path / "venv" / "Scripts" / "pythonw.exe"
    launcher = root_path / "scripts" / "launch_voiceflow.pyw"
    return f'"{pythonw}" "{launcher}"'


def is_autostart_enabled(root: str | Path) -> bool:
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


def set_autostart(root: str | Path, enabled: bool) -> None:
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
