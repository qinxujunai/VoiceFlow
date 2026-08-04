"""Small platform services shared by source and frozen runtimes."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


def default_data_dir(
    environ: Mapping[str, str] | None = None,
    *,
    platform_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    platform_value = sys.platform if platform_name is None else platform_name
    home_dir = Path.home() if home is None else Path(home)

    if platform_value == "darwin":
        return home_dir / "Library" / "Application Support" / "VoiceFlow"
    if platform_value == "win32":
        local_app_data = env.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "VoiceFlow"
        return home_dir / "AppData" / "Local" / "VoiceFlow"

    xdg_data_home = env.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "VoiceFlow"
    return home_dir / ".local" / "share" / "VoiceFlow"


def open_path(path: str | Path) -> None:
    resolved = str(Path(path).resolve())
    if sys.platform == "win32":
        os.startfile(resolved)
        return
    command = ["open", resolved] if sys.platform == "darwin" else ["xdg-open", resolved]
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def paste_modifier(platform_name: str | None = None) -> str:
    platform_value = sys.platform if platform_name is None else platform_name
    return "command" if platform_value == "darwin" else "ctrl"


def platform_label(platform_name: str | None = None) -> str:
    platform_value = sys.platform if platform_name is None else platform_name
    if platform_value == "darwin":
        return "macOS"
    if platform_value == "win32":
        return "Windows x64"
    return "Desktop"


def icon_asset_name(platform_name: str | None = None) -> str:
    platform_value = sys.platform if platform_name is None else platform_name
    return "voiceflow.png" if platform_value == "darwin" else "voiceflow.ico"


def data_location_label(data_dir: str | Path, platform_name: str | None = None) -> str:
    platform_value = sys.platform if platform_name is None else platform_name
    if platform_value == "darwin":
        return "~/Library/Application Support/VoiceFlow"
    if platform_value == "win32":
        return r"%LOCALAPPDATA%\VoiceFlow"
    return str(Path(data_dir))


def trigger_summary(platform_name: str | None = None) -> str:
    platform_value = sys.platform if platform_name is None else platform_name
    if platform_value == "darwin":
        return "F2 · 鼠标侧键 · 托盘菜单"
    return "F2 · 右 Ctrl · 鼠标侧键"


def trigger_instruction(platform_name: str | None = None) -> str:
    platform_value = sys.platform if platform_name is None else platform_name
    if platform_value == "darwin":
        return "按 F2 或从托盘菜单开始说话，再触发一次完成。"
    return "按 F2 开始说话，再按一次完成。"
