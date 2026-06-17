"""
Add or update one VoiceFlow correction pair.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _force_utf8_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def update_correction(base_dir, wrong, correct):
    wrong = (wrong or "").strip()
    correct = (correct or "").strip()
    if not wrong or not correct:
        raise ValueError("wrong and correct must both be non-empty")

    path = Path(base_dir) / "knowledge-base" / "corrections.txt"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    updated = False
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                lines.append(line)
                continue
            existing_wrong, _ = stripped.split("=", 1)
            if existing_wrong.strip() == wrong:
                if not updated:
                    lines.append(f"{wrong}={correct}")
                    updated = True
                continue
            lines.append(line)

    if not updated:
        lines.append(f"{wrong}={correct}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, "updated" if updated else "added"


def main():
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Add or update a VoiceFlow correction")
    parser.add_argument("wrong", help="ASR text to replace")
    parser.add_argument("correct", help="preferred output text")
    parser.add_argument("--base-dir", default=str(ROOT), help="VoiceFlow project root")
    args = parser.parse_args()

    try:
        path, status = update_correction(args.base_dir, args.wrong, args.correct)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"{status}: {args.wrong}={args.correct} -> {path}")


if __name__ == "__main__":
    main()
