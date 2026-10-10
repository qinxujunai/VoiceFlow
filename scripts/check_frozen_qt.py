"""Reject retired/unused rendering engines from a native Windows package."""

import argparse
from pathlib import Path


FORBIDDEN_PREFIXES = (
    "qt6qml", "qt6quick", "qt6webengine", "qt6virtualkeyboard", "qt6pdf",
    "qtqml", "qtquick", "qtwebengine", "qtvirtualkeyboard",
)
FORBIDDEN_NAMES = {"qpdf.dll", "qtvirtualkeyboardplugin.dll", "qtwebengineprocess.exe"}


def check_native_qt_package(package_dir):
    root = Path(package_dir).resolve(strict=True)
    forbidden = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_file()
        and (path.name.casefold() in FORBIDDEN_NAMES
             or path.name.casefold().startswith(FORBIDDEN_PREFIXES))
    )
    if forbidden:
        raise ValueError("Native package contains excluded Qt runtime files: " + ", ".join(forbidden))
    if not (root / "PySide6" / "plugins" / "platforms" / "qwindows.dll").is_file():
        raise ValueError("Native Windows Qt platform plugin is missing")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    args = parser.parse_args()
    check_native_qt_package(args.package_dir)
    print("Native Qt package boundary: ok")
