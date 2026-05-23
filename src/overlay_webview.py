"""
VoiceFlow 悬浮窗。Qt 主线程 + 信号桥接，所有跨线程 UI 操作线程安全。
"""

import os
import sys
import json

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSystemTrayIcon, QMenu,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QSize, QObject, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QScreen, QIcon, QAction, QPixmap, QPainter


class OverlayWindow:

    def __init__(self):
        self.window = None
        self.web_view = None
        self._bridge = None
        self._tray = None
        self._html_path = os.path.join(os.path.dirname(__file__), "overlay.html")
        self._on_ready = None

    def start(self, on_ready=None):
        self._on_ready = on_ready
        self._run()

    def _run(self):
        app = QApplication(sys.argv)

        # ---- 主窗口 ----
        self.window = QMainWindow()
        self.window.setWindowTitle("VoiceFlow")
        self.window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.window.setFixedSize(QSize(700, 56))

        screen = app.primaryScreen()
        geo = screen.availableGeometry()
        x = (geo.width() - 700) // 2 + geo.x()
        y = geo.y() + geo.height() - 56 - 60
        self.window.move(x, y)

        # ---- WebView ----
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl.fromLocalFile(self._html_path))
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        self._bridge = _Bridge(self.web_view)
        # 连接 show/hide 信号（线程安全）
        self._bridge.show_requested.connect(self._show)
        self._bridge.hide_requested.connect(self._hide)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)
        self.window.setCentralWidget(central)

        # ---- 托盘 ----
        try:
            self._setup_tray()
            self.window.hide()
        except Exception as e:
            print(f"[托盘] 启动失败: {e}", flush=True)
            self._tray = None
            self.window.show()

        if self._on_ready:
            self._on_ready()

        app.exec()

    # ============================================================
    # 托盘
    # ============================================================

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()

        # 画图标
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setPen(Qt.GlobalColor.white)
        p.drawEllipse(4, 4, 24, 24)
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "V")
        p.end()
        self._tray.setIcon(QIcon(px))
        self._tray.setToolTip("VoiceFlow")
        self._tray.setVisible(True)

        menu = QMenu()
        show_act = QAction("显示窗口")
        show_act.triggered.connect(self._show)
        menu.addAction(show_act)
        quit_act = QAction("退出")
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.window and self.window.isVisible():
                self._hide()
            else:
                self._show()

    def _show(self):
        if self.window:
            self.window.show()

    def _hide(self):
        if self.window:
            self.window.hide()

    def quit(self):
        QApplication.instance().quit()

    # ============================================================
    # 对外接口 — 线程安全（通过 _Bridge 信号）
    # ============================================================

    def _js(self, code):
        if self._bridge:
            self._bridge.js_requested.emit(code)

    def show_recording(self):
        self._js("showRecording()")

    def update_streaming(self, text):
        self._js(f"updateStreaming({json.dumps(text, ensure_ascii=False)})")

    def show_processing(self):
        self._js("showProcessing()")

    def show_result(self, text):
        self._js(f"showResult({json.dumps(text, ensure_ascii=False)})")

    def show_error(self, msg):
        self._js(f"showError({json.dumps(msg, ensure_ascii=False)})")

    def show_window(self):
        if self._bridge:
            self._bridge.show_requested.emit()

    def hide_after(self, ms=2000):
        QTimer.singleShot(ms, self._hide)


# ============================================================
# 信号桥 — 所有跨线程 Qt 操作经过这里
# ============================================================

class _Bridge(QObject):
    js_requested = pyqtSignal(str)
    show_requested = pyqtSignal()
    hide_requested = pyqtSignal()

    def __init__(self, web_view):
        super().__init__()
        self._web_view = web_view
        self.js_requested.connect(self._run_js)
        # show/hide 信号连接到自身的方法只是为了统一管理，
        # 实际执行由 OverlayWindow._show/_hide 通过外部连接完成
        # 这里只做 JS 桥接

    @pyqtSlot(str)
    def _run_js(self, code):
        if self._web_view and self._web_view.page():
            self._web_view.page().runJavaScript(code)
