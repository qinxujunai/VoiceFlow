from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_FILES = (
    "src/main.py",
    "src/overlay_webview.py",
    "src/hotkey_manager.py",
    "src/output_handler.py",
    "src/text_cleaner.py",
    "src/transcriber.py",
    "src/audio_capture.py",
    "src/recording_session.py",
    "src/vocabulary.py",
    "scripts/doctor.py",
    "scripts/verify.py",
    "scripts/benchmark_models.py",
    "scripts/add_correction.py",
    "test_integration.py",
)


def _run(label: str, command: list[str]) -> int:
    print(f"\n== {label} ==", flush=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=_quality_gate_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n", flush=True)
    if completed.returncode != 0:
        print(f"\nFAILED: {label} ({completed.returncode})", flush=True)
    return completed.returncode


def _quality_gate_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _force_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Run the non-interactive VoiceFlow quality gate.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip the slower integration test while keeping doctor, compile, pytest, and benchmark.",
    )
    parser.add_argument("--benchmark-limit", type=int, default=3)
    args = parser.parse_args()

    commands = [
        ("doctor", [sys.executable, "scripts/doctor.py"]),
        ("py_compile", [sys.executable, "-m", "py_compile", *PYTHON_FILES]),
        ("pytest", [sys.executable, "-m", "pytest", "tests", "-q"]),
        ("benchmark", [sys.executable, "scripts/benchmark_models.py", "--limit", str(args.benchmark_limit)]),
    ]
    if not args.quick:
        commands.append(("integration", [sys.executable, "test_integration.py"]))

    for label, command in commands:
        return_code = _run(label, command)
        if return_code != 0:
            return return_code

    print("\nVoiceFlow verify: ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
