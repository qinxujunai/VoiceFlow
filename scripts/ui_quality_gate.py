"""Windows DPI and keyboard-accessibility smoke gate for the settings shell."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(output_dir: str | Path) -> dict:
    output = Path(output_dir)
    failures = []
    captures = []
    for scale in ("1", "1.25", "1.5", "2"):
        scale_dir = output / scale.replace(".", "_")
        env = os.environ.copy()
        env["QT_SCALE_FACTOR"] = scale
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "capture_ui_states.py"),
                "--settings-only",
                "--output-dir",
                str(scale_dir),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode != 0:
            failures.append({"scale": scale, "output": completed.stdout})
            continue
        manifest = json.loads((scale_dir / "manifest.json").read_text(encoding="utf-8"))
        if len(manifest.get("captures", [])) != 6:
            failures.append({"scale": scale, "output": "missing settings captures"})
            continue
        captures.append({"scale": scale, "manifest": str((scale_dir / "manifest.json").resolve())})
    return {"passed": not failures, "captures": captures, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceFlow UI quality gate")
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "ui-quality"))
    args = parser.parse_args()
    result = run(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
