"""
VoiceFlow 悬浮窗口
输入法风格，屏幕底部居中
设计：Qt 必须在主线程运行，热键等其他模块在子线程
"""

import os
import sys
import json
import threading


class OverlayWindow:
    """输入法风格悬浮条（必须在主线程启动）"""

    def __init__(self):
        self.window = None
        self.web_view = None
        self._bridge = None
        self._html_path = os.path.join(os.path.dirname(__file__), "overlay.html")
        self._on_ready = None

    def start(self, on_ready=None):
        """
        在主线程启动 Qt 事件循环（阻塞）。
        on_ready: 窗口就绪后的回调
        """
        self._on_ready = on_ready
        self._run()

    def _run(self):
        """运行窗口（主线程）"""
        from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                     QSystemTrayIcon, QMenu)
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import Qt, QUrl, QSize, QObject, pyqtSignal, pyqtSlot
        from PyQt6.QtGui import QScreen, QIcon, QAction

        class _JsBridge(QObject):
            js_requested = pyqtSignal(str)

            def __init__(self, web_view):
                super().__init__()
                self._web_view = web_view
                self.js_requested.connect(self._execute_js)

            @pyqtSlot(str)
            def _execute_js(self, js_code):
                if self._web_view and self._web_view.page():
                    self._web_view.page().runJavaScript(js_code)

        app = QApplication(sys.argv)

        # 创建主窗口
        self.window = QMainWindow()
        self.window.setWindowTitle("VoiceFlow")
        self.window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 紧凑尺寸：420px 宽 + 少量边距，44px 高 + 进度条空间
        width, height = 440, 56
        self.window.setFixedSize(QSize(width, height))

        # 屏幕底部居中
        screen = app.primaryScreen()
        geo = screen.availableGeometry()
        x = (geo.width() - width) // 2 + geo.x()
        y = geo.y() + geo.height() - height - 60
        self.window.move(x, y)

        # WebView
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl.fromLocalFile(self._html_path))
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        self._bridge = _JsBridge(self.web_view)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)
        self.window.setCentralWidget(central_widget)

        self.window.show()

        # --- 系统托盘（失败时降级为普通窗口） ---
        try:
            self._setup_tray()
            self.window.hide()  # 成功了才隐藏
        except Exception as e:
            print(f"[托盘] 初始化失败 ({e})，使用窗口模式", flush=True)
            self._tray = None

        if self._on_ready:
            self._on_ready()

        app.exec()

    def _call_js(self, js_code):
        """调用 JavaScript（线程安全）"""
        if self._bridge:
            try:
                self._bridge.js_requested.emit(js_code)
            except Exception:
                pass

    def show_ready(self):
        self._call_js("showReady()")

    def show_recording(self):
        self._call_js("showRecording()")

    def update_streaming(self, text):
        """流式更新转写文字（录音期间实时调用）"""
        escaped = json.dumps(text, ensure_ascii=False)
        self._call_js(f"updateStreaming({escaped})")

    def show_transcribing(self):
        self._call_js("showTranscribing()")

    def show_result(self, text):
        escaped = json.dumps(text, ensure_ascii=False)
        self._call_js(f"showResult({escaped})")

    def show_error(self, msg):
        escaped = json.dumps(msg, ensure_ascii=False)
        self._call_js(f"showError({escaped})")

    def show_cancelled(self):
        self._call_js("showCancelled()")

    def quit(self):
        """退出 Qt 事件循环"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()

    def _setup_tray(self):
        """创建系统托盘图标"""
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QIcon, QAction

        self._tray = QSystemTrayIcon()

        # 用 1x1 像素图做图标（避免依赖外部文件）
        from PyQt6.QtGui import QPixmap, QPainter
        from PyQt6.QtCore import Qt as QtCore
        px = QPixmap(32, 32)
        px.fill(QtCore.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setPen(QtCore.GlobalColor.white)
        painter.drawEllipse(4, 4, 24, 24)
        painter.drawText(px.rect(), QtCore.AlignmentFlag.AlignCenter, "V")
        painter.end()
        self._tray.setIcon(QIcon(px))

        self._tray.setToolTip("VoiceFlow — 语音转文字")
        self._tray.setVisible(True)

        tray_menu = QMenu()
        show_action = QAction("显示窗口", self.window)
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)
        quit_action = QAction("退出 VoiceFlow", self.window)
        quit_action.triggered.connect(self.quit)
        tray_menu.addAction(quit_action)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)

    # --- 窗口显示控制 ---

    def _show_window(self):
        """显示悬浮窗口"""
        if self.window:
            self.window.show()

    def _hide_window(self):
        """隐藏悬浮窗口"""
        if self.window:
            self.window.hide()

    def show_for_recording(self):
        """录音时显示窗口"""
        self._show_window()

    def hide_after_result(self):
        """结果展示后延迟隐藏窗口"""
        if self._tray is None:
            return  # 没有托盘就不隐藏
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, self._hide_window)

    def _on_tray_activated(self, reason):
        """托盘图标点击事件"""
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.window and self.window.isVisible():
                self._hide_window()
            else:
                self._show_window()
