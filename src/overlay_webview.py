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
from PyQt6.QtGui import QScreen, QAction

from tray_icon import (
    TRAY_ICON_ERROR,
    TRAY_ICON_IDLE,
    TRAY_ICON_PROCESSING,
    TRAY_ICON_RECORDING,
    build_tray_icon,
)
from ui_state import UiState, display_for_state


class OverlayWindow:

    def __init__(self):
        self.window = None
        self.web_view = None
        self._bridge = None
        self._tray = None
        self._tray_icons = {}
        self._on_copy_last = None
        self._on_repaste_last = None
        self._on_open_dictionary = None
        self._html_path = os.path.join(os.path.dirname(__file__), "overlay.html")
        self._on_ready = None
        self._window_width = 380
        self._window_height = 48

    def set_actions(self, on_copy_last=None, on_repaste_last=None, on_open_dictionary=None):
        self._on_copy_last = on_copy_last
        self._on_repaste_last = on_repaste_last
        self._on_open_dictionary = on_open_dictionary

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
        self.window.setFixedSize(QSize(self._window_width, self._window_height))
        self._center_window()

        # ---- WebView ----
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl.fromLocalFile(self._html_path))
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        self._bridge = _Bridge(self.web_view)
        # 连接 show/hide 信号（线程安全）
        self._bridge.show_requested.connect(self._show)
        self._bridge.hide_requested.connect(self._hide)
        self._bridge.hide_after_requested.connect(self._hide_after)
        self._bridge.tray_state_requested.connect(self._set_tray_state)

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
        self._tray_icons = {
            TRAY_ICON_IDLE: build_tray_icon(TRAY_ICON_IDLE),
            TRAY_ICON_RECORDING: build_tray_icon(TRAY_ICON_RECORDING),
            TRAY_ICON_PROCESSING: build_tray_icon(TRAY_ICON_PROCESSING),
            TRAY_ICON_ERROR: build_tray_icon(TRAY_ICON_ERROR),
        }

        self._tray.setIcon(self._tray_icons[TRAY_ICON_IDLE])
        self._tray.setToolTip("VoiceFlow")
        self._tray.setVisible(True)

        menu = QMenu()
        show_act = QAction("显示窗口")
        show_act.triggered.connect(self._show)
        menu.addAction(show_act)
        copy_last_act = QAction("复制上一次结果")
        copy_last_act.triggered.connect(self._copy_last)
        menu.addAction(copy_last_act)
        repaste_last_act = QAction("重新粘贴上一次结果")
        repaste_last_act.triggered.connect(self._repaste_last)
        menu.addAction(repaste_last_act)
        dictionary_act = QAction("打开词库")
        dictionary_act.triggered.connect(self._open_dictionary)
        menu.addAction(dictionary_act)
        menu.addSeparator()
        quit_act = QAction("退出")
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window and self.window.isVisible():
                self._hide()
            else:
                self._show()

    def _show(self):
        if self.window:
            self._center_window()
            self.window.show()

    def _hide(self):
        if self.window:
            self.window.hide()

    def _hide_after(self, ms=2000):
        QTimer.singleShot(ms, self._hide_and_idle)

    def _hide_and_idle(self):
        self._hide()
        self._set_tray_state(TRAY_ICON_IDLE)

    def _set_tray_state(self, state):
        if self._tray and state in self._tray_icons:
            self._tray.setIcon(self._tray_icons[state])

    def _center_window(self):
        app = QApplication.instance()
        if not app or not self.window:
            return
        screen = app.primaryScreen()
        geo = screen.availableGeometry()
        width = min(self._window_width, max(320, geo.width() - 32))
        if self.window.width() != width:
            self.window.setFixedSize(QSize(width, self._window_height))
        x = geo.x() + (geo.width() - width) // 2
        y = geo.y() + geo.height() - self._window_height - 52
        self.window.move(x, y)

    def _copy_last(self):
        if self._on_copy_last:
            self._on_copy_last()

    def _repaste_last(self):
        if self._on_repaste_last:
            self._on_repaste_last()

    def _open_dictionary(self):
        if self._on_open_dictionary:
            self._on_open_dictionary()

    def quit(self):
        QApplication.instance().quit()

    # ============================================================
    # 对外接口 — 线程安全（通过 _Bridge 信号）
    # ============================================================

    def _js(self, code):
        if self._bridge:
            self._bridge.js_requested.emit(code)

    def _tray_state(self, state):
        if self._bridge:
            self._bridge.tray_state_requested.emit(state)

    def show_recording(self):
        self._tray_state(TRAY_ICON_RECORDING)
        self._js("showRecording()")

    def update_streaming(self, text):
        self._js(f"updateStreaming({json.dumps(text, ensure_ascii=False)})")

    def show_processing(self):
        self._tray_state(TRAY_ICON_PROCESSING)
        display = display_for_state(UiState.PROCESSING)
        self._js(f"showState({json.dumps(display.css_class)}, {json.dumps(display.label, ensure_ascii=False)})")

    def show_result(self, text):
        self._js(f"showResult({json.dumps(text, ensure_ascii=False)})")
        self._tray_state(TRAY_ICON_IDLE)

    def show_error(self, msg):
        self._tray_state(TRAY_ICON_ERROR)
        self._js(f"showState('error', {json.dumps(msg, ensure_ascii=False)})")

    def show_canceled(self):
        self._tray_state(TRAY_ICON_IDLE)
        display = display_for_state(UiState.CANCELED)
        self._js(f"showState({json.dumps(display.css_class)}, {json.dumps(display.label, ensure_ascii=False)})")

    def show_idle(self):
        self._tray_state(TRAY_ICON_IDLE)
        display = display_for_state(UiState.IDLE)
        self._js(f"showState({json.dumps(display.css_class)}, {json.dumps(display.label, ensure_ascii=False)})")

    def show_window(self):
        if self._bridge:
            self._bridge.show_requested.emit()

    def hide_after(self, ms=2000):
        if self._bridge:
            self._bridge.hide_after_requested.emit(ms)


# ============================================================
# 信号桥 — 所有跨线程 Qt 操作经过这里
# ============================================================

class _Bridge(QObject):
    js_requested = pyqtSignal(str)
    show_requested = pyqtSignal()
    hide_requested = pyqtSignal()
    hide_after_requested = pyqtSignal(int)
    tray_state_requested = pyqtSignal(str)

    def __init__(self, web_view):
        super().__init__()
        self._web_view = web_view
        self._page_ready = False
        self._pending_js = []
        self._web_view.loadFinished.connect(self._on_load_finished)
        self.js_requested.connect(self._run_js)
        # show/hide 信号连接到自身的方法只是为了统一管理，
        # 实际执行由 OverlayWindow._show/_hide 通过外部连接完成
        # 这里只做 JS 桥接

    @pyqtSlot(bool)
    def _on_load_finished(self, ok):
        if not ok:
            return
        self._page_ready = True
        for code in self._pending_js:
            self._run_js(code)
        self._pending_js = []

    @pyqtSlot(str)
    def _run_js(self, code):
        if not self._page_ready:
            self._pending_js.append(code)
            return
        if self._web_view and self._web_view.page():
            self._web_view.page().runJavaScript(code)
