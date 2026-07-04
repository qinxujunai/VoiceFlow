"""
Windowed VoiceFlow launcher.

Normal launches stay quiet and go straight to the tray app. If the local
environment needs repair, this launcher opens start.bat so setup feedback is
visible instead of failing silently.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def _python_usable() -> bool:
    try:
        completed = subprocess.run(
            [str(VENV_PYTHON), "-c", "import sys"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        return False
    return completed.returncode == 0


def _run_hidden(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def _open_setup_console() -> None:
    subprocess.Popen(
        ["cmd.exe", "/c", str(ROOT / "start.bat")],
        cwd=ROOT,
        creationflags=CREATE_NEW_CONSOLE,
    )


def main() -> None:
    if not _python_usable():
        _open_setup_console()
        return

    bootstrap = _run_hidden([
        str(VENV_PYTHON),
        str(ROOT / "scripts" / "bootstrap.py"),
        "--ensure-shortcut",
    ])
    if bootstrap.returncode != 0:
        _open_setup_console()
        return

    subprocess.Popen(
        [str(VENV_PYTHON), "-u", str(ROOT / "src" / "main.py")],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


if __name__ == "__main__":
    main()
