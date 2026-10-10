# -*- mode: python ; coding: utf-8 -*-
"""
VoiceFlow PyInstaller release build.
Build: venv\\Scripts\\python.exe -m PyInstaller VoiceFlow.spec
Output: dist\\VoiceFlow\\VoiceFlow.exe
"""

import sys
import json
import PyInstaller
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.config import CONF

PROJECT_ROOT = Path(SPECPATH)
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from sync_version import sync_versions
sync_versions(PROJECT_ROOT)
from build_record import write_build_record
from bundled_notices import collect_distribution_notices
from asr_runtime_assets import check_installed_runtime
check_installed_runtime(PROJECT_ROOT)
build_record = write_build_record(PROJECT_ROOT, Path(CONF["workpath"]) / "build-record.json")
UIAUTOMATION_BINARIES = collect_dynamic_libs("uiautomation")

a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=UIAUTOMATION_BINARIES,
    datas=[
        (str(build_record), "."),
        # Overlay UI.
        (str(PROJECT_ROOT / "src" / "overlay.html"), "src"),
        # Runtime config.
        (str(PROJECT_ROOT / "config.yaml"), "."),
        (str(PROJECT_ROOT / "model-manifest.json"), "."),
        (str(PROJECT_ROOT / "LICENSE"), "."),
        (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
        (str(PROJECT_ROOT / "licenses"), "licenses"),
        (
            str(PROJECT_ROOT / "docs" / "sensevoice-redistribution-decision.md"),
            "docs",
        ),
        (
            str(PROJECT_ROOT / "docs" / "qt-lgpl-compliance.md"),
            "docs",
        ),
        (
            str(PROJECT_ROOT / "docs" / "streaming-preview-model-review.md"),
            "docs",
        ),
        (str(PROJECT_ROOT / "docs" / "asr-runtime-build.md"), "docs"),
        # Vocabulary files.
        (str(PROJECT_ROOT / "knowledge-base"), "knowledge-base"),
        (str(PROJECT_ROOT / "assets" / "voiceflow.ico"), "assets"),
        (str(PROJECT_ROOT / "assets" / "silero_vad.onnx"), "assets"),
        # Models are intentionally not bundled because they are large.
        # (str(PROJECT_ROOT / "models"), "models"),
    ],
    hiddenimports=[
        "sherpa_onnx",
        "sounddevice",
        "numpy",
        "keyboard",
        "pynput",
        "pyperclip",
        "yaml",
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "uiautomation",
        "comtypes",
        "model_downloader",
    ],
    hookspath=[str(PROJECT_ROOT / "scripts" / "pyinstaller_hooks")],
    hooksconfig={},
    # Keep LGPL Python library portions inspectable and replaceable in the onedir.
    module_collection_mode={"pynput": "py", "PySide6": "py", "shiboken6": "py"},
    runtime_hooks=[
        # Install PyInstaller's supported worker dispatch before any GUI hook.
        str(Path(PyInstaller.__file__).parent / "hooks" / "rthooks" / "pyi_rth_multiprocessing.py"),
        str(PROJECT_ROOT / "scripts" / "pyinstaller_qt_runtime_hook.py"),
    ],
    excludes=[
        # Windows uses checked native paste. These optional cross-platform
        # automation/debugging helpers are not part of the Windows product.
        "pyautogui",
        "mouseinfo",
        "pymsgbox",
        "pyscreeze",
        "pygetwindow",
        "pyrect",
        "pytweening",
        "tkinter",
        "_tkinter",
        "matplotlib",
        "pandas",
        "scipy",
        "tensorflow",
        "torch",
        "PIL",
        "cv2",
        "PyQt5",
        "PyQt6",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtQml",
        "PySide6.QtQuick",
    ],
    noarchive=False,
    optimize=0,
)

# PyInstaller may discover an ICU pair from an unrelated host tool such as
# Poppler. Qt6Core expects the Windows ICU ABI; bundling that host pair makes
# the frozen app fail with WinError 127 before user data is initialized.
a.binaries = [
    entry
    for entry in a.binaries
    if Path(entry[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}
]

from check_frozen_qt import FORBIDDEN_NAMES, FORBIDDEN_PREFIXES
unexpected_asr = [entry[0] for entry in a.binaries
                  if Path(entry[0]).name.casefold().startswith("sherpa-onnx-")]
if unexpected_asr:
    raise ValueError(f"Unused ASR C/C++ API payload discovered: {unexpected_asr}")
# Ordinary microphone backends remain; optional ASIO is outside the reviewed
# Windows package. The runtime hook selects that same backend before spawning.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.casefold().endswith("-asio.dll")]
unexpected_qt = [
    entry[0] for entry in a.binaries
    if Path(entry[0]).name.casefold() in FORBIDDEN_NAMES
    or Path(entry[0]).name.casefold().startswith(FORBIDDEN_PREFIXES)
]
if unexpected_qt:
    raise ValueError(f"Native Qt package boundary violated: {unexpected_qt}")

# The release QtWebEngine runtime uses the normal .pak files and
# v8_context_snapshot.bin. The paired .debug.pak/.debug.bin files are for Qt
# debug builds, so do not ship the duplicate debug resources in a release.
a.datas = [
    entry
    for entry in a.datas
    if not Path(entry[0]).name.lower().endswith((".debug.pak", ".debug.bin"))
]

notice_datas, notice_report = collect_distribution_notices(a.pure + a.binaries + a.datas)
a.datas += notice_datas
python_notice = Path(sys.base_prefix) / "LICENSE.txt"
if not python_notice.is_file():
    raise ValueError("The build interpreter's original LICENSE.txt is required")
from build_record import sha256_file
a.datas.append(("licenses/CPython-LICENSE.txt", str(python_notice), "DATA"))
notice_report.append({"name": "CPython", "version": sys.version.split()[0],
                      "notices": [{"path": "licenses/CPython-LICENSE.txt",
                                   "sha256": sha256_file(python_notice)}]})
notice_record = Path(CONF["workpath"]) / "dependency-notices.json"
notice_record.write_text(json.dumps(notice_report, indent=2) + "\n", encoding="utf-8")
a.datas.append(("dependency-notices.json", str(notice_record), "DATA"))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="VoiceFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    exclude_binaries=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "voiceflow.ico"),
    version=str(PROJECT_ROOT / "assets" / "version_info.txt"),
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceFlow",
)
