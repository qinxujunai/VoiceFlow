"""Qt binding surface. Release builds use PySide6 (LGPL)."""

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
except ImportError:  # Development bridge for an existing pre-migration venv.
    QT_BINDING = "PyQt6"
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
