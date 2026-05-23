# -*- mode: python ; coding: utf-8 -*-
"""
VoiceFlow PyInstaller release build.
Build: venv\\Scripts\\pyinstaller.exe VoiceFlow.spec
Output: dist\\VoiceFlow.exe
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
        # Vocabulary files.
        (str(PROJECT_ROOT / "knowledge-base"), "knowledge-base"),
        (str(PROJECT_ROOT / "assets" / "voiceflow.ico"), "assets"),
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
        "PyQt6",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
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
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VoiceFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "voiceflow.ico"),
)
