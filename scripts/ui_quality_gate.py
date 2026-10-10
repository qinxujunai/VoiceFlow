"""Settings capture completeness and glyph checks at four Qt scale factors.

This does not verify native monitor DPI, keyboard accessibility or Narrator.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(output_dir: str | Path, *, offscreen_windows_fonts: bool = False) -> dict:
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
                *(["--offscreen-windows-fonts"] if offscreen_windows_fonts else []),
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
        if manifest.get("fonts", {}).get("probe_glyph_count") != 13:
            failures.append({"scale": scale, "output": "missing font rendering evidence"})
            continue
        expected = {"settings-dictation.png", "settings-dictionary.png", "settings-history.png",
                    "settings-diagnostics.png", "settings-about.png"}
        actual = {Path(item["path"]).name for item in manifest.get("captures", [])}
        if actual != expected:
            failures.append({"scale": scale, "output": "missing settings captures"})
            continue
        captures.append({"scale": scale, "manifest": str((scale_dir / "manifest.json").resolve())})
    return {
        "passed": not failures, "captures": captures, "failures": failures,
        "evidence_scope": "capture completeness and Latin/Chinese glyph availability",
        "not_verified": ["native monitor DPI", "keyboard navigation", "Narrator",
                         "visual review", "final package"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceFlow UI quality gate")
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "ui-quality"))
    parser.add_argument("--offscreen-windows-fonts", action="store_true")
    args = parser.parse_args()
    result = run(args.output_dir, offscreen_windows_fonts=args.offscreen_windows_fonts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
