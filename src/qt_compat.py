"""Qt binding surface. Release builds use PySide6 (LGPL)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES = []


def _prepare_frozen_qt_dll_search() -> None:
    """Keep a frozen PySide6 build independent from the host's Qt install."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return

    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidates = (
        bundle_root,
        bundle_root / "PySide6",
        bundle_root / "shiboken6",
    )
    paths = []
    for directory in candidates:
        if not directory.is_dir():
            continue
        directory_text = os.fspath(directory)
        if directory_text not in paths:
            paths.append(directory_text)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                _DLL_DIRECTORY_HANDLES.append(add_dll_directory(directory_text))
            except OSError:
                # PATH remains a compatible fallback on older Windows hosts.
                pass
    if paths:
        os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])


_prepare_frozen_qt_dll_search()

try:
    QT_BINDING = "PySide6"
    from PySide6.QtCore import Qt, QUrl, QSize, QObject, Signal, Slot, QTimer, QPointF
    from PySide6.QtGui import (
        QAction,
        QColor,
        QIcon,
        QPainter,
        QPen,
        QPixmap,
    )
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (
        QApplication,
        QGridLayout,
        QHBoxLayout,
        QCheckBox,
        QComboBox,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QMenu,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QStackedWidget,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
except ImportError as pyside_error:  # Development bridge for an existing pre-migration venv.
    QT_BINDING = "PyQt6"
    try:
        from PyQt6.QtCore import (
            Qt,
            QUrl,
            QSize,
            QObject,
            pyqtSignal as Signal,
            pyqtSlot as Slot,
            QTimer,
            QPointF,
        )
        from PyQt6.QtGui import (
            QAction,
            QColor,
            QIcon,
            QPainter,
            QPen,
            QPixmap,
        )
        from PyQt6.QtNetwork import QLocalServer, QLocalSocket
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWidgets import (
            QApplication,
            QGridLayout,
            QHBoxLayout,
            QCheckBox,
            QComboBox,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QMenu,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QStackedWidget,
            QSystemTrayIcon,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as pyqt_error:
        raise ImportError(
            "VoiceFlow could not load PySide6 or the development PyQt6 bridge: "
            f"PySide6={pyside_error}; PyQt6={pyqt_error}"
        ) from pyside_error
