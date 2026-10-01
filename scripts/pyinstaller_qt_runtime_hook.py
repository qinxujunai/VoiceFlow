"""Prepare bundled Qt DLL lookup before PySide6 imports any extension module."""

from __future__ import annotations

import os
import sys
from pathlib import Path


if sys.platform == "win32":
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidates = (
        bundle_root,
        bundle_root / "PySide6",
        bundle_root / "shiboken6",
    )
    paths = [os.fspath(path) for path in candidates if path.is_dir()]
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        for path in paths:
            try:
                # Keep handles alive for the lifetime of the process.
                globals().setdefault("_voiceflow_dll_handles", []).append(
                    add_dll_directory(path)
                )
            except OSError:
                pass
    if paths:
        os.environ["PATH"] = os.pathsep.join(
            paths + [os.environ.get("PATH", "")]
        )
