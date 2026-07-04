"""
VoiceFlow 悬浮窗。Qt 主线程 + 信号桥接，所有跨线程 UI 操作线程安全。
"""

import os
import sys
import json
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSystemTrayIcon, QMenu, QLabel, QPushButton,
    QPlainTextEdit, QGridLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLineEdit, QStackedWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, QSize, QObject, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QScreen, QAction
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from tray_icon import (
    TRAY_ICON_ERROR,
    TRAY_ICON_IDLE,
    TRAY_ICON_PROCESSING,
    TRAY_ICON_RECORDING,
    build_tray_icon,
)
from ui_state import UiState, display_for_state


SINGLE_INSTANCE_NAME = "VoiceFlow.LocalFirstDictation"


class _SettingsWindow(QMainWindow):
    def __init__(self, on_repaste_text=None):
        super().__init__()
        self.root = os.path.dirname(os.path.dirname(__file__))
        self._on_repaste_text = on_repaste_text
        self._history_rows = []
        self.setWindowTitle("VoiceFlow")
        self.setMinimumSize(860, 560)

        shell = QWidget()
        shell.setObjectName("appShell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(22, 18, 22, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(2)
        title = QLabel("VoiceFlow")
        title.setObjectName("appTitle")
        subtitle = QLabel("本地优先语音输入")
        subtitle.setObjectName("appSubtitle")
        title_group.addWidget(title)
        title_group.addWidget(subtitle)
        header.addLayout(title_group)
        header.addStretch(1)
        self.status_badge = QLabel("准备中")
        self.status_badge.setObjectName("statusBadge")
        header.addWidget(self.status_badge)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        for label in ("最近转录", "状态", "诊断"):
            self.sidebar.addItem(QListWidgetItem(label))
        self.sidebar.setFixedWidth(132)
        self.sidebar.setCurrentRow(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.stack.addWidget(self._recent_page())
        self.stack.addWidget(self._status_page())
        self.stack.addWidget(self._diagnostics_page())
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)

        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(shell)
        self.setStyleSheet(self._style())

    def _section_header(self, title, subtitle):
        block = QVBoxLayout()
        block.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("sectionSubtitle")
        block.addWidget(label)
        block.addWidget(sub)
        return block

    def _recent_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addLayout(self._section_header("最近转录", "查看、复制或重新送达最近结果"))

        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索最近转录")
        self.search_box.textChanged.connect(self._render_history)
        toolbar.addWidget(self.search_box, 1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._refresh_history)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.itemDoubleClicked.connect(lambda item: self._copy_text(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.history_list, 1)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("primaryButton")
        self.copy_button.clicked.connect(self._copy_selected)
        self.repaste_button = QPushButton("重新粘贴")
        self.repaste_button.clicked.connect(self._repaste_selected)
        copy_all = QPushButton("复制全部")
        copy_all.clicked.connect(self._copy_all_visible)
        open_logs = QPushButton("打开日志")
        open_logs.clicked.connect(lambda: os.startfile(os.path.join(self.root, "logs")))
        actions.addWidget(self.copy_button)
        actions.addWidget(self.repaste_button)
        actions.addWidget(copy_all)
        actions.addWidget(open_logs)
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _status_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(16)
        layout.addLayout(self._section_header("运行状态", "启动、模型、快捷键和本地权限概览"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.model_status = QLabel()
        self.hotkey_status = QLabel("F2 / Right Ctrl / XButton1 / XButton2")
        self.mic_status = QLabel("使用系统默认麦克风")
        self.mode_status = QLabel("离线优先，无隐藏云调用")
        rows = (
            ("模型", self.model_status),
            ("快捷键", self.hotkey_status),
            ("麦克风", self.mic_status),
            ("模式", self.mode_status),
        )
        for row, (name, value) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setObjectName("fieldName")
            value.setObjectName("fieldValue")
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value, row, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _diagnostics_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addLayout(self._section_header("诊断", "检查依赖、模型、知识库和快捷方式"))
        header.addStretch(1)
        run = QPushButton("运行检查")
        run.setObjectName("primaryButton")
        run.clicked.connect(self._run_doctor)
        header.addWidget(run)
        layout.addLayout(header)
        self.doctor_text = QPlainTextEdit()
        self.doctor_text.setObjectName("doctorOutput")
        self.doctor_text.setReadOnly(True)
        self.doctor_text.setPlainText("点击“运行检查”查看当前环境状态。")
        layout.addWidget(self.doctor_text, 1)
        return page

    def refresh(self):
        model = os.path.join(self.root, "models", "sensevoice", "model.int8.onnx")
        tokens = os.path.join(self.root, "models", "sensevoice", "tokens.txt")
        ready = os.path.exists(model) and os.path.exists(tokens)
        self.status_badge.setText("就绪" if ready else "需要设置")
        self.model_status.setText("SenseVoice 已就绪" if ready else "模型缺失")
        self._refresh_history()

    def _refresh_history(self):
        path = os.path.join(self.root, "logs", "history.jsonl")
        if not os.path.exists(path):
            self._history_rows = []
            self._render_history()
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = [line for line in f.read().splitlines() if line][-80:]
            parsed = []
            for row in reversed(rows):
                try:
                    parsed.append(json.loads(row))
                except Exception:
                    pass
            self._history_rows = parsed
            self._render_history()
        except Exception as e:
            self._history_rows = [{"error": f"历史读取失败: {e}"}]
            self._render_history()

    def _render_history(self):
        if not hasattr(self, "history_list"):
            return
        query = self.search_box.text().strip().lower() if hasattr(self, "search_box") else ""
        self.history_list.clear()
        for row in self._history_rows:
            text = row.get("corrected_text") or row.get("clean_text") or row.get("error") or ""
            if query and query not in text.lower():
                continue
            timestamp = row.get("timestamp", "")
            duration = row.get("duration")
            status = row.get("output_status", "unknown")
            tail = row.get("final_tail", "")
            meta_parts = [part for part in (timestamp, f"{float(duration):.1f}s" if duration is not None else "", status) if part]
            if tail:
                meta_parts.append(f"尾部 {tail}")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, text)
            item.setSizeHint(QSize(0, 82))
            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, self._history_card(text, " · ".join(meta_parts)))
        if self.history_list.count() == 0:
            empty = QListWidgetItem()
            empty.setData(Qt.ItemDataRole.UserRole, "")
            empty.setSizeHint(QSize(0, 68))
            self.history_list.addItem(empty)
            self.history_list.setItemWidget(empty, self._empty_card())

    def _history_card(self, text, meta):
        card = QWidget()
        card.setObjectName("historyCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(12)

        text_group = QVBoxLayout()
        text_group.setSpacing(4)
        body = QLabel(text)
        body.setObjectName("historyText")
        body.setWordWrap(False)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setToolTip(text)
        info = QLabel(meta)
        info.setObjectName("historyMeta")
        text_group.addWidget(body)
        text_group.addWidget(info)
        row.addLayout(text_group, 1)

        copy = QPushButton("复制")
        copy.setObjectName("inlineCopyButton")
        copy.clicked.connect(lambda _=False, value=text: self._copy_text(value))
        row.addWidget(copy)
        return card

    def _empty_card(self):
        card = QWidget()
        card.setObjectName("emptyCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        title = QLabel("暂无转录")
        title.setObjectName("historyText")
        note = QLabel("开始一次语音输入后会出现在这里")
        note.setObjectName("historyMeta")
        layout.addWidget(title)
        layout.addWidget(note)
        return card

    def _selected_text(self):
        item = self.history_list.currentItem() if hasattr(self, "history_list") else None
        if not item and hasattr(self, "history_list") and self.history_list.count() > 0:
            item = self.history_list.item(0)
            self.history_list.setCurrentItem(item)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _copy_selected(self):
        text = self._selected_text()
        self._copy_text(text)

    def _copy_text(self, text):
        if not text:
            self.status_badge.setText("无可复制")
            return
        import pyperclip
        pyperclip.copy(text)
        self.status_badge.setText("已复制")

    def _repaste_selected(self):
        text = self._selected_text()
        if not text:
            self.status_badge.setText("无可粘贴")
            return
        if self._on_repaste_text:
            self._on_repaste_text(text)
            self.status_badge.setText("已粘贴")

    def _copy_all_visible(self):
        texts = []
        for i in range(self.history_list.count()):
            text = self.history_list.item(i).data(Qt.ItemDataRole.UserRole)
            if text:
                texts.append(text)
        if not texts:
            self.status_badge.setText("无可复制")
            return
        import pyperclip
        pyperclip.copy("\n\n".join(texts))
        self.status_badge.setText("已复制")

    def _run_doctor(self):
        python = os.path.join(self.root, "venv", "Scripts", "python.exe")
        self.doctor_text.setPlainText("正在检查...")
        try:
            completed = subprocess.run(
                [python, "scripts/doctor.py"],
                cwd=self.root,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.doctor_text.setPlainText(completed.stdout or "诊断完成")
            self.status_badge.setText("检查完成" if completed.returncode == 0 else "需要处理")
        except Exception as e:
            self.doctor_text.setPlainText(f"诊断失败: {e}")
            self.status_badge.setText("检查失败")

    def _style(self):
        return """
        QWidget#appShell {
            background: #f5f5f7;
            color: #1d1d1f;
            font-family: "Segoe UI", "Microsoft YaHei";
            font-size: 13px;
        }
        QLabel#appTitle {
            font-size: 24px;
            font-weight: 650;
            letter-spacing: 0px;
            color: #1d1d1f;
        }
        QLabel#appSubtitle, QLabel#sectionSubtitle, QLabel#fieldName {
            color: #6e6e73;
        }
        QLabel#statusBadge {
            padding: 6px 12px;
            border-radius: 14px;
            background: #ffffff;
            color: #1d1d1f;
            border: 1px solid rgba(0, 0, 0, 0.08);
        }
        QListWidget#sidebar {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#sidebar::item {
            min-height: 34px;
            padding-left: 12px;
            border-radius: 8px;
            color: #6e6e73;
        }
        QListWidget#sidebar::item:selected {
            background: #ffffff;
            color: #1d1d1f;
            border: 1px solid rgba(0, 0, 0, 0.08);
        }
        QStackedWidget#contentStack, QWidget#contentPage {
            background: #ffffff;
            border-radius: 12px;
        }
        QLabel#sectionTitle {
            font-size: 18px;
            font-weight: 620;
            color: #1d1d1f;
        }
        QLabel#fieldValue {
            color: #1d1d1f;
            font-weight: 500;
        }
        QLineEdit, QPlainTextEdit, QListWidget#historyList {
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 10px;
            background: #fbfbfd;
            padding: 8px;
            selection-background-color: #007aff;
        }
        QListWidget#historyList {
            outline: none;
        }
        QListWidget#historyList::item {
            padding: 0px;
            margin: 5px;
            border-radius: 10px;
            border: 1px solid rgba(0, 0, 0, 0.06);
            background: #ffffff;
        }
        QListWidget#historyList::item:selected {
            color: #1d1d1f;
            background: #eef5ff;
            border: 1px solid rgba(0, 122, 255, 0.24);
        }
        QWidget#historyCard, QWidget#emptyCard {
            background: transparent;
        }
        QLabel#historyText {
            color: #1d1d1f;
            font-size: 13px;
            font-weight: 500;
        }
        QLabel#historyMeta {
            color: #6e6e73;
            font-size: 12px;
        }
        QPlainTextEdit#doctorOutput {
            font-family: "Cascadia Mono", Consolas, monospace;
            font-size: 12px;
        }
        QPushButton {
            min-height: 30px;
            padding: 5px 14px;
            border-radius: 8px;
            border: 1px solid rgba(0, 0, 0, 0.10);
            background: #ffffff;
            color: #1d1d1f;
        }
        QPushButton:hover {
            background: #f2f2f7;
        }
        QPushButton#primaryButton {
            background: #007aff;
            color: white;
            border: 1px solid #007aff;
        }
        QPushButton#inlineCopyButton {
            min-width: 58px;
            min-height: 28px;
            padding: 3px 10px;
        }
        """


class OverlayWindow:

    def __init__(self):
        self.window = None
        self.web_view = None
        self._bridge = None
        self._tray = None
        self._tray_icons = {}
        self._on_copy_last = None
        self._on_repaste_last = None
        self._on_output_text = None
        self._on_open_dictionary = None
        self._on_quit = None
        self._html_path = os.path.join(os.path.dirname(__file__), "overlay.html")
        self._on_ready = None
        self._window_width = 380
        self._window_height = 48
        self._tray_menu = None
        self._tray_actions = []
        self._hide_timer = None
        self._settings_window = None
        self._single_instance_server = None

    def set_actions(
        self,
        on_copy_last=None,
        on_repaste_last=None,
        on_output_text=None,
        on_open_dictionary=None,
        on_quit=None,
    ):
        self._on_copy_last = on_copy_last
        self._on_repaste_last = on_repaste_last
        self._on_output_text = on_output_text
        self._on_open_dictionary = on_open_dictionary
        self._on_quit = on_quit

    def start(self, on_ready=None):
        self._on_ready = on_ready
        self._run()

    def _run(self):
        app = QApplication(sys.argv)
        if self._notify_existing_instance():
            return
        self._start_single_instance_server()

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
        self._bridge.settings_requested.connect(self._show_settings)

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

    def _notify_existing_instance(self):
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_NAME)
        if not socket.waitForConnected(120):
            socket.abort()
            return False
        socket.write(b"show\n")
        socket.flush()
        socket.waitForBytesWritten(120)
        socket.disconnectFromServer()
        return True

    def _start_single_instance_server(self):
        server = QLocalServer()
        if not server.listen(SINGLE_INSTANCE_NAME):
            QLocalServer.removeServer(SINGLE_INSTANCE_NAME)
            if not server.listen(SINGLE_INSTANCE_NAME):
                return
        server.newConnection.connect(self._on_instance_message)
        self._single_instance_server = server

    def _on_instance_message(self):
        if not self._single_instance_server:
            return
        while self._single_instance_server.hasPendingConnections():
            socket = self._single_instance_server.nextPendingConnection()
            socket.readyRead.connect(lambda sock=socket: self._handle_instance_message(sock))
            if socket.bytesAvailable():
                self._handle_instance_message(socket)

    def _handle_instance_message(self, socket):
        socket.readAll()
        socket.disconnectFromServer()
        self._show_settings()

    # ============================================================
    # 托盘
    # ============================================================

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets",
            "voiceflow.ico",
        )
        self._tray_icons = {
            TRAY_ICON_IDLE: build_tray_icon(TRAY_ICON_IDLE, icon_path),
            TRAY_ICON_RECORDING: build_tray_icon(TRAY_ICON_RECORDING, icon_path),
            TRAY_ICON_PROCESSING: build_tray_icon(TRAY_ICON_PROCESSING, icon_path),
            TRAY_ICON_ERROR: build_tray_icon(TRAY_ICON_ERROR, icon_path),
        }

        self._tray.setIcon(self._tray_icons[TRAY_ICON_IDLE])
        self._tray.setToolTip("VoiceFlow")
        self._tray.setVisible(True)

        self._tray_menu = QMenu()
        self._tray_actions = []

        show_act = QAction("打开设置", self._tray_menu)
        show_act.triggered.connect(self._show_settings)
        self._tray_menu.addAction(show_act)
        self._tray_actions.append(show_act)

        copy_last_act = QAction("复制上一次结果", self._tray_menu)
        copy_last_act.triggered.connect(self._copy_last)
        self._tray_menu.addAction(copy_last_act)
        self._tray_actions.append(copy_last_act)

        repaste_last_act = QAction("重新粘贴上一次结果", self._tray_menu)
        repaste_last_act.triggered.connect(self._repaste_last)
        self._tray_menu.addAction(repaste_last_act)
        self._tray_actions.append(repaste_last_act)

        dictionary_act = QAction("打开词库", self._tray_menu)
        dictionary_act.triggered.connect(self._open_dictionary)
        self._tray_menu.addAction(dictionary_act)
        self._tray_actions.append(dictionary_act)

        self._tray_menu.addSeparator()

        quit_act = QAction("退出", self._tray_menu)
        quit_act.triggered.connect(self.quit)
        self._tray_menu.addAction(quit_act)
        self._tray_actions.append(quit_act)

        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_settings()

    def _show(self):
        if self.window:
            self._center_window()
            self.window.show()

    def _hide(self):
        if self.window:
            self.window.hide()

    def _show_settings(self):
        if self._settings_window is None:
            self._settings_window = _SettingsWindow(on_repaste_text=self._on_output_text)
        self._settings_window.refresh()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _hide_after(self, ms=2000):
        self._cancel_pending_hide()
        self._hide_timer = QTimer(self.window)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_and_idle)
        self._hide_timer.start(ms)

    def _cancel_pending_hide(self):
        if self._hide_timer:
            self._hide_timer.stop()
            self._hide_timer.deleteLater()
            self._hide_timer = None

    def _hide_and_idle(self):
        self._hide_timer = None
        self._set_tray_state(TRAY_ICON_IDLE)
        if self._bridge:
            self._bridge.js_then_hide_requested.emit("resetHiddenInstant()")
            return
        self._hide()

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
        if self._tray:
            self._tray.setVisible(False)
        if self._on_quit:
            self._on_quit()
        app = QApplication.instance()
        if app:
            app.quit()

    # ============================================================
    # 对外接口 — 线程安全（通过 _Bridge 信号）
    # ============================================================

    def _js(self, code):
        if self._bridge:
            self._bridge.js_requested.emit(code)

    def _tray_state(self, state):
        if self._bridge:
            self._bridge.tray_state_requested.emit(state)

    def show_recording(self, session_id):
        self._cancel_pending_hide()
        self._tray_state(TRAY_ICON_RECORDING)
        if self._bridge:
            self._bridge.js_then_show_requested.emit(f"prepareRecording({int(session_id)})")

    def update_streaming(self, text, session_id):
        self._js(f"updateStreaming({json.dumps(text, ensure_ascii=False)}, {int(session_id)})")

    def show_processing(self):
        self._tray_state(TRAY_ICON_PROCESSING)
        self._js("showProcessing()")

    def show_finalizing(self, session_id):
        self._tray_state(TRAY_ICON_PROCESSING)
        self._js(f"showFinalizing({int(session_id)})")


    def show_done(self):
        self._tray_state(TRAY_ICON_IDLE)
        self._js(f"showDone()")

    def show_final_text(self, text, session_id):
        self._tray_state(TRAY_ICON_IDLE)
        self._js(f"showFinalText({json.dumps(text, ensure_ascii=False)}, {int(session_id)})")


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

    def show_settings_window(self):
        if self._bridge:
            self._bridge.settings_requested.emit()

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
    js_then_show_requested = pyqtSignal(str)
    js_then_hide_requested = pyqtSignal(str)
    hide_after_requested = pyqtSignal(int)
    tray_state_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, web_view):
        super().__init__()
        self._web_view = web_view
        self._page_ready = False
        self._pending_js = []
        self._web_view.loadFinished.connect(self._on_load_finished)
        self.js_requested.connect(self._run_js)
        self.js_then_show_requested.connect(self._run_js_then_show)
        self.js_then_hide_requested.connect(self._run_js_then_hide)
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

    @pyqtSlot(str)
    def _run_js_then_show(self, code):
        if not self._page_ready or not self._web_view or not self._web_view.page():
            return
        self._web_view.page().runJavaScript(code, lambda _: self.show_requested.emit())

    @pyqtSlot(str)
    def _run_js_then_hide(self, code):
        if not self._page_ready or not self._web_view or not self._web_view.page():
            self.hide_requested.emit()
            return
        self._web_view.page().runJavaScript(code, lambda _: QTimer.singleShot(50, self.hide_requested.emit))
