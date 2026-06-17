from __future__ import annotations

import argparse
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
    "scripts/benchmark_models.py",
    "scripts/add_correction.py",
)


def _run(label: str, command: list[str]) -> int:
    print(f"\n== {label} ==", flush=True)
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        print(f"\nFAILED: {label} ({completed.returncode})", flush=True)
    return completed.returncode


def main() -> int:
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
