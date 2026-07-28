# -*- mode: python ; coding: utf-8 -*-
"""
VoiceFlow PyInstaller release build.
Build: venv\\Scripts\\pyinstaller.exe VoiceFlow.spec
Output: dist\\VoiceFlow\\VoiceFlow.exe
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH)

a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=[
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
        "pyautogui",
        "yaml",
        "PySide6",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pandas",
        "scipy",
        "tensorflow",
        "torch",
        "PIL",
        "cv2",
        "PyQt5",
        "PyQt6",
    ],
    noarchive=False,
    optimize=0,
)

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
