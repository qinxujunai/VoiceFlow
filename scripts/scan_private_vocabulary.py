"""Fail when packaged text resources contain a retired private seed line."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime_paths import PRIVATE_ENTRY_SHA256


TEXT_SUFFIXES = frozenset({".cfg", ".ini", ".json", ".md", ".txt", ".yaml", ".yml"})


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def scan_tree(
    root: Path,
    *,
    private_hashes: frozenset[str] = PRIVATE_ENTRY_SHA256,
) -> list[str]:
    root = Path(root).resolve()
    matches: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if line.strip() and _digest(line) in private_hashes:
                relative = path.relative_to(root).as_posix()
                matches.append(f"{relative}:{line_number}")
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    matches = scan_tree(args.root)
    if matches:
        print("Private vocabulary gate failed:")
        for match in matches:
            print(f"- {match}")
        return 1
    print(f"Private vocabulary gate: ok ({args.root.resolve()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
