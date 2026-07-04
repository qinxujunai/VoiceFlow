"""
VoiceFlow startup bootstrap.

This script intentionally uses only the Python standard library so start.bat can
run it from a system Python even when the project virtual environment is broken.
It may repair the local venv and install dependencies, but it never downloads
ASR models implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / "venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
REQUIREMENTS = ROOT / "requirements.txt"
BOOTSTRAP_STATE = ROOT / "logs" / "bootstrap-state.json"
BOOTSTRAP_VERSION = 2
MODEL_FILES = (
    ROOT / "models" / "sensevoice" / "model.int8.onnx",
    ROOT / "models" / "sensevoice" / "tokens.txt",
)

REQUIRED_IMPORTS = (
    "numpy",
    "sherpa_onnx",
    "sounddevice",
    "soundfile",
    "pyperclip",
    "PyQt6",
    "PyQt6.QtWebEngineWidgets",
    "pynput",
    "yaml",
)


def _run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def _print_output(completed: subprocess.CompletedProcess[str]) -> None:
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n", flush=True)


def _file_signature(path: Path, *, include_hash: bool = True) -> dict[str, object]:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    signature = {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    if include_hash:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        signature["sha256"] = digest.hexdigest()
    return signature


def _startup_signature() -> dict[str, object]:
    return {
        "version": BOOTSTRAP_VERSION,
        "requirements": _file_signature(REQUIREMENTS),
        "config": _file_signature(ROOT / "config.yaml"),
        "models": {
            str(path.relative_to(ROOT)): _file_signature(path, include_hash=False)
            for path in MODEL_FILES
        },
    }


def _models_present() -> bool:
    return all(path.exists() for path in MODEL_FILES)


def _read_bootstrap_state() -> dict[str, object]:
    try:
        return json.loads(BOOTSTRAP_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_bootstrap_state(signature: dict[str, object]) -> None:
    BOOTSTRAP_STATE.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_STATE.write_text(
        json.dumps({"signature": signature}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_fast_path_ready() -> bool:
    if not is_python_usable(VENV_PYTHON):
        return False
    if not _models_present():
        return False
    state = _read_bootstrap_state()
    return state.get("signature") == _startup_signature()


def is_python_usable(python: Path | str) -> bool:
    try:
        completed = _run([str(python), "-c", "import sys; print(sys.version)"])
    except OSError:
        return False
    return completed.returncode == 0


def _safe_remove_venv(root: Path = ROOT) -> None:
    target = (root / "venv").resolve()
    root_resolved = root.resolve()
    if target == root_resolved or root_resolved not in target.parents:
        raise RuntimeError(f"Refusing to remove unsafe venv path: {target}")
    if target.exists():
        shutil.rmtree(target)


def _create_venv(base_python: str) -> None:
    print("[Setup] Creating virtual environment...", flush=True)
    completed = _run([base_python, "-m", "venv", str(VENV_DIR)])
    _print_output(completed)
    if completed.returncode != 0:
        raise RuntimeError("Failed to create venv. Install Python 3.10+ and try again.")


def _install_requirements() -> None:
    print("[Setup] Installing dependencies...", flush=True)
    completed = _run([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    _print_output(completed)
    if completed.returncode != 0:
        raise RuntimeError("pip install failed.")


def _missing_imports() -> list[str]:
    code = (
        "import importlib, sys\n"
        f"mods = {REQUIRED_IMPORTS!r}\n"
        "missing = []\n"
        "for name in mods:\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "    except Exception:\n"
        "        missing.append(name)\n"
        "print('\\n'.join(missing))\n"
        "sys.exit(1 if missing else 0)\n"
    )
    completed = _run([str(VENV_PYTHON), "-c", code])
    if completed.returncode == 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def ensure_venv(base_python: str, *, force_install: bool = False) -> None:
    if VENV_PYTHON.exists() and not is_python_usable(VENV_PYTHON):
        print("[Setup] Existing venv is broken; rebuilding it.", flush=True)
        _safe_remove_venv()

    if not VENV_PYTHON.exists():
        _create_venv(base_python)
        force_install = True

    if not is_python_usable(VENV_PYTHON):
        raise RuntimeError("venv python is still not runnable after setup.")

    missing = _missing_imports()
    if force_install or missing:
        if missing:
            print(f"[Setup] Missing dependencies: {', '.join(missing)}", flush=True)
        _install_requirements()


def ensure_logs_dir(root: Path = ROOT) -> None:
    (root / "logs").mkdir(parents=True, exist_ok=True)


def desktop_shortcut_path(name: str = "VoiceFlow") -> Path:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    return desktop / f"{name}.lnk"


def ensure_shortcut(name: str = "VoiceFlow", *, force: bool = False) -> None:
    shortcut = desktop_shortcut_path(name)
    if shortcut.exists() and not force:
        return
    script = ROOT / "scripts" / "create_shortcut.ps1"
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ShortcutName",
            name,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    _print_output(completed)
    if completed.returncode != 0:
        print("[Setup] Shortcut creation failed; continuing without blocking launch.", flush=True)


def run_doctor() -> int:
    completed = _run([str(VENV_PYTHON), "scripts/doctor.py"])
    _print_output(completed)
    if completed.returncode != 0:
        print("", flush=True)
        print("[Setup] Runtime check failed.", flush=True)
        print("[Setup] If model files are missing, run:", flush=True)
        print("        venv\\Scripts\\python.exe scripts\\download_models.py", flush=True)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare VoiceFlow runtime before launch.")
    parser.add_argument("--base-python", default=sys.executable)
    parser.add_argument("--ensure-shortcut", action="store_true")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()

    try:
        ensure_logs_dir()
        if is_fast_path_ready():
            if args.ensure_shortcut:
                ensure_shortcut()
            print("[Setup] Fast startup check ok.", flush=True)
            return 0

        print("[Setup] Checking Python environment...", flush=True)
        ensure_venv(args.base_python)
        if args.ensure_shortcut:
            ensure_shortcut(force=True)
        if not args.skip_doctor:
            result = run_doctor()
            if result == 0:
                _write_bootstrap_state(_startup_signature())
            return result
        _write_bootstrap_state(_startup_signature())
        return 0
    except Exception as exc:
        print(f"[Setup] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
