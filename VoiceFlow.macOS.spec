# -*- mode: python ; coding: utf-8 -*-
"""VoiceFlow macOS onedir application bundle.

Build on the target architecture:
    python -m PyInstaller VoiceFlow.macOS.spec --noconfirm
"""

import os
from pathlib import Path


PROJECT_ROOT = Path(SPECPATH)
CODESIGN_IDENTITY = os.environ.get("VOICEFLOW_CODESIGN_IDENTITY") or None

a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "src" / "overlay.html"), "src"),
        (str(PROJECT_ROOT / "config.yaml"), "."),
        (str(PROJECT_ROOT / "model-manifest.json"), "."),
        (str(PROJECT_ROOT / "LICENSE"), "."),
        (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
        (str(PROJECT_ROOT / "licenses"), "licenses"),
        (str(PROJECT_ROOT / "knowledge-base"), "knowledge-base"),
        (str(PROJECT_ROOT / "assets" / "voiceflow.png"), "assets"),
        (str(PROJECT_ROOT / "assets" / "silero_vad.onnx"), "assets"),
        (str(PROJECT_ROOT / "models" / "sensevoice"), "models/sensevoice"),
        (
            str(PROJECT_ROOT / "models" / "streaming-preview"),
            "models/streaming-preview",
        ),
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
    ],
    hiddenimports=[
        "sherpa_onnx",
        "sounddevice",
        "numpy",
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
        "keyboard",
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
    upx=False,
    console=False,
    exclude_binaries=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=str(
        PROJECT_ROOT / "installer" / "macos" / "entitlements.plist"
    ),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VoiceFlow",
)

app = BUNDLE(
    coll,
    name="VoiceFlow.app",
    icon=str(PROJECT_ROOT / "assets" / "voiceflow.icns"),
    bundle_identifier="ai.voiceflow.app",
    info_plist={
        "CFBundleDisplayName": "VoiceFlow",
        "CFBundleShortVersionString": "0.2.2",
        "CFBundleVersion": "0.2.2",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": (
            "VoiceFlow 需要麦克风，把你的语音在本机转换为文字。"
        ),
    },
)
