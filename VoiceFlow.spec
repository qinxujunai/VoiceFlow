# -*- mode: python ; coding: utf-8 -*-
"""
VoiceFlow PyInstaller 打包配置
构建命令：pyinstaller VoiceFlow.spec
输出：dist/VoiceFlow.exe（单文件，双击即用）
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=[
        # HTML 悬浮窗
        (str(PROJECT_ROOT / "src" / "overlay.html"), "src"),
        # 配置文件
        (str(PROJECT_ROOT / "config.yaml"), "."),
        # 知识库
        (str(PROJECT_ROOT / "knowledge-base"), "knowledge-base"),
        # 模型文件（太大，排除；用户自己下载）
        # (str(PROJECT_ROOT / "models"), "models"),
    ],
    hiddenimports=[
        "sherpa_onnx",
        "sounddevice",
        "numpy",
        "pynput",
        "pyperclip",
        "pyautogui",
        "yaml",
        "PyQt6",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "tkinter",
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
    console=True,  # 显示控制台窗口（方便调试）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: 加图标
)
