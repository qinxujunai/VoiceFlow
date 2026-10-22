"""
VoiceFlow 悬浮窗。Qt 主线程 + 信号桥接，所有跨线程 UI 操作线程安全。
"""

import json
import logging
import os
import sys
import time
import threading
from pathlib import Path

from qt_compat import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSystemTrayIcon,
    QMenu,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QComboBox,
    QMessageBox,
    QScrollArea,
    Qt,
    QUrl,
    QSize,
    QObject,
    Signal,
    Slot,
    QTimer,
    QAction,
    QLocalServer,
    QLocalSocket,
    QEvent,
    QIcon,
    QPixmap,
    QPainter,
    QPen,
    QColor,
    QRectF,
)

from tray_icon import (
    TRAY_ICON_ERROR,
    TRAY_ICON_IDLE,
    TRAY_ICON_PROCESSING,
    TRAY_ICON_RECORDING,
    build_tray_icon,
)
from ui_state import UiState, display_for_state
from settings_store import onboarding_completed, set_onboarding_completed
from runtime_paths import AppPaths
from version import display_version
from runtime_services import ModelManager
from platform_utils import icon_asset_name, platform_label, trigger_summary, system_high_contrast_enabled
from recovery_session import RecoverySessionStore
from runtime_monitor import UiStallDetector
from capsule_native import NativeCapsuleBridge, NativeCapsuleView
from punctuation import SENTENCE_END_CHOICES
from settings_ui.preferences import PreferencesMixin
from settings_ui.dictionary import DictionaryMixin
from settings_ui.history import HistoryMixin
from settings_ui.diagnostics import DiagnosticsMixin
from settings_ui.style import StyleMixin


SINGLE_INSTANCE_NAME = "VoiceFlow.LocalFirstDictation"
logger = logging.getLogger("voiceflow.ui")


class _QuitCoordinator(QObject):
    finished = Signal(object)

    def __init__(self, cleanup, complete):
        super().__init__()
        self._cleanup = cleanup
        self._complete = complete
        self._running = False
        self._completed = False
        self.finished.connect(self._finish)

    def start(self):
        if self._running or self._completed:
            return False
        self._running = True
        threading.Thread(target=self._run, name="voiceflow-quit", daemon=False).start()
        return True

    def _run(self):
        error = None
        try:
            if self._cleanup:
                self._cleanup()
        except Exception as failure:
            logger.exception("runtime cleanup failed")
            error = failure
        self.finished.emit(error)

    @Slot(object)
    def _finish(self, error):
        self._running = False
        self._completed = error is None
        self._complete(error)


class _LatestPreviewMailbox:
    """One-slot mailbox so rendering can never build a preview backlog."""

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None

    def put(self, value):
        with self._lock:
            self._value = value

    def take(self):
        with self._lock:
            value = self._value
            self._value = None
            return value


class _PaintAwareWindow(QMainWindow):
    first_paint_completed = Signal()

    def __init__(self):
        super().__init__()
        self._first_paint_pending = False

    def expect_first_paint(self):
        self._first_paint_pending = True

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._first_paint_pending:
            return
        self._first_paint_pending = False
        QTimer.singleShot(0, self.first_paint_completed.emit)


class _PreviewPaintReporter(QObject):
    painted = Signal(int)

    @Slot(int)
    def previewPainted(self, session_id):
        self.painted.emit(int(session_id))


class _SettingsWindow(PreferencesMixin, DictionaryMixin, HistoryMixin, DiagnosticsMixin, StyleMixin, QMainWindow):
    doctor_finished = Signal(object)
    model_switch_finished = Signal(object)
    recovery_finished = Signal(object)
    refresh_finished = Signal(object)
    history_refresh_finished = Signal(object)
    history_action_finished = Signal(object)
    history_mutation_finished = Signal(object)
    update_finished = Signal(object)
    onboarding_finished = Signal(object)
    dictionary_finished = Signal(object)

    def __init__(
        self,
        on_copy_text=None,
        on_repaste_text=None,
        on_recover_session=None,
        on_delete_recovery=None,
        on_read_history=None,
        on_delete_history=None,
        on_clear_history=None,
        on_clear_local_data=None,
        on_restore_history=None,
        controller=None,
        paths=None,
    ):
        super().__init__()
        if paths is None:
            project_root = os.path.dirname(os.path.dirname(__file__))
            paths = AppPaths.discover(
                config_path=os.path.join(project_root, "config.yaml")
            )
        self.paths = paths
        self.root = str(self.paths.data_dir)
        self.model_manager = ModelManager(self.paths)
        self._on_copy_text = on_copy_text
        self._on_repaste_text = on_repaste_text
        self._on_recover_session = on_recover_session
        self._on_delete_recovery = on_delete_recovery
        self._on_read_history = on_read_history
        self._on_delete_history = on_delete_history
        self._on_clear_history = on_clear_history
        self._on_clear_local_data = on_clear_local_data
        self._on_restore_history = on_restore_history
        self._history_undo_token = None
        self._history_undo_generation = 0
        self.controller = controller
        self.recovery_store = RecoverySessionStore(self.paths.recovery_dir)
        self._history_rows = []
        self._dictionary_entries = {}
        self._active_dictionary_filename = None
        self._last_diagnostics = None
        self._microphone_detected = False
        self._switch_in_progress = False
        self._refresh_in_progress = False
        self._history_refresh_in_progress = False
        self._history_action_in_progress = False
        self._doctor_in_progress = False
        self._recovery_action_in_progress = False
        self._dictation_save_in_progress = False
        self._onboarding_save_in_progress = False
        self._onboarding_confirmed = False
        self._dictation_preferences_snapshot = {}
        self._preferences_draft = {}
        self._settings_baseline = None
        self._loading_settings = False
        self._dictionary_dirty = False
        self._dictionary_save_in_progress = False
        self._dictionary_undo = None
        self._dictionary_generation = 0
        self._history_render_generation = 0
        self.setWindowTitle("VoiceFlow")
        self.setMinimumSize(600, 460)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.setMinimumSize(min(600, available.width()), min(460, available.height()))
            self.resize(min(1040, available.width()), min(760, available.height()))

        shell = QWidget()
        shell.setObjectName("appShell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setSpacing(0)

        sidebar_panel = QWidget()
        self.sidebar_panel = sidebar_panel
        sidebar_panel.setObjectName("sidebarPanel")
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(16)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setObjectName("brandIcon")
        icon_path = str(
            self.paths.install_resource(f"assets/{icon_asset_name()}")
        )
        brand_icon.setPixmap(
            build_tray_icon(TRAY_ICON_IDLE, icon_path).pixmap(32, 32)
        )
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        title = QLabel("VoiceFlow")
        self.brand_title = title
        title.setObjectName("appTitle")
        subtitle = QLabel("离线语音输入")
        self.brand_subtitle = subtitle
        subtitle.setObjectName("appSubtitle")
        brand_copy.addWidget(title)
        brand_copy.addWidget(subtitle)
        brand.addWidget(brand_icon)
        brand.addLayout(brand_copy)
        brand.addStretch(1)
        sidebar_layout.addLayout(brand)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        for label in ("听写", "词典", "历史"):
            item = QListWidgetItem(label)
            item.setIcon(self._navigation_icon(self.sidebar.count()))
            self.sidebar.addItem(item)
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setCurrentRow(0)
        self.sidebar.setAccessibleName("主要导航")
        sidebar_layout.addWidget(self.sidebar, 1)

        self.status_badge = QLabel("准备中")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAccessibleName("VoiceFlow 状态")
        self.status_badge.setWordWrap(True)
        sidebar_layout.addWidget(self.status_badge)
        help_menu = QMenu(self)
        self.diagnostics_action = help_menu.addAction("运行检查")
        self.diagnostics_action.triggered.connect(lambda: self._show_aux_page(3))
        about_action = help_menu.addAction("关于 VoiceFlow")
        about_action.triggered.connect(lambda: self._show_aux_page(4))
        self.help_button = QPushButton("帮助")
        self.help_button.setMenu(help_menu)
        self.help_button.setAccessibleName("帮助、诊断与关于")
        sidebar_layout.addWidget(self.help_button)
        build_label = QLabel(f"{display_version()}\n{platform_label()}")
        self.build_label = build_label
        build_label.setObjectName("sidebarVersion")
        build_label.setToolTip(f"{display_version()} · {platform_label()}")
        sidebar_layout.addWidget(build_label)
        sidebar_panel.setFixedWidth(176)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.stack.addWidget(self._home_page())
        self.stack.addWidget(self._recent_page())
        self.stack.addWidget(self._dictionary_page())
        self.stack.addWidget(self._diagnostics_page())
        self.stack.addWidget(self._about_page())
        self.sidebar.currentRowChanged.connect(self._show_primary_page)

        body.addWidget(sidebar_panel)
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.stack, 1)
        body.addWidget(content_container, 1)
        root.addLayout(body, 1)
        self.operation_feedback = QLabel()
        self.operation_feedback.setObjectName("operationFeedback")
        self.operation_feedback.setWordWrap(True)
        self.operation_feedback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.operation_feedback.setContentsMargins(24, 8, 24, 12)
        self.operation_feedback.setAccessibleName("操作结果")
        self.operation_feedback.hide()
        content_layout.addWidget(self.operation_feedback)
        self.operation_details_button = QPushButton("查看错误详情")
        self.operation_details_button.hide()
        self.operation_details_button.clicked.connect(self._show_operation_details)
        content_layout.addWidget(self.operation_details_button)
        self.setCentralWidget(shell)
        self._system_style_ready = True
        self._high_contrast_active = None
        self._refresh_system_style()
        self.doctor_finished.connect(self._finish_doctor)
        self.model_switch_finished.connect(self._finish_model_switch)
        self.recovery_finished.connect(self._finish_recovery)
        self.refresh_finished.connect(self._finish_refresh)
        self.history_refresh_finished.connect(self._finish_history_refresh)
        self.history_action_finished.connect(self._finish_history_action)
        self.history_mutation_finished.connect(self._finish_history_mutation)
        self.update_finished.connect(self._finish_update_check)
        self.onboarding_finished.connect(self._finish_onboarding)
        self.dictionary_finished.connect(self._finish_dictionary_save)
        self._last_runtime_phase = None
        self._runtime_status_timer = QTimer(self)
        self._runtime_status_timer.setInterval(500)
        self._runtime_status_timer.timeout.connect(
            lambda: self._sync_runtime_status() if self.isVisible() else None
        )
        if callable(getattr(self.controller, "runtime_snapshot", None)):
            self._runtime_status_timer.start()

    def set_history_actions(
        self,
        read=None,
        delete=None,
        clear=None,
        restore=None,
        clear_local_data=None,
    ):
        self._on_read_history = read
        self._on_delete_history = delete
        self._on_clear_history = clear
        self._on_clear_local_data = clear_local_data
        self._on_restore_history = restore

    def _show_primary_page(self, row):
        page_by_row = {0: 0, 1: 2, 2: 1}
        if row in page_by_row:
            self.stack.setCurrentIndex(page_by_row[row])

    def _show_aux_page(self, index):
        self.sidebar.clearSelection()
        self.stack.setCurrentIndex(index)
        if index == 3:
            self._run_doctor()

    def _section_header(self, title, subtitle):
        block = QVBoxLayout()
        block.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setObjectName("sectionSubtitle")
        block.addWidget(label)
        block.addWidget(sub)
        return block

    def _navigation_icon(self, index):
        image = QPixmap(40, 40)
        image.setDevicePixelRatio(2)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#3a3a3c"), 1.5))
        if index == 0:
            for x, height in ((5, 7), (10, 14), (15, 10)):
                painter.drawLine(x, int(10 - height / 2), x, int(10 + height / 2))
        elif index == 1:
            painter.drawRoundedRect(QRectF(3, 3, 14, 14), 2, 2)
            painter.drawLine(7, 3, 7, 17)
            painter.drawLine(10, 7, 14, 7)
            painter.drawLine(10, 11, 14, 11)
        else:
            painter.drawEllipse(QRectF(3, 3, 14, 14))
            painter.drawLine(10, 6, 10, 10)
            painter.drawLine(10, 10, 14, 12)
        painter.end()
        return QIcon(image)

    def resizeEvent(self, event):
        compact = self.width() < 620
        if hasattr(self, "sidebar_panel"):
            self.sidebar_panel.setFixedWidth(96 if compact else 176)
            self.sidebar_panel.layout().setContentsMargins(10 if compact else 16, 20, 10 if compact else 16, 16)
            self.brand_title.setVisible(not compact)
            self.brand_subtitle.setVisible(not compact)
            self.build_label.setVisible(not compact)
        if hasattr(self, "_settings_grids"):
            self._home_layout.setContentsMargins(16 if compact else 40, 24, 16 if compact else 40, 24)
            self._settings_actions.setContentsMargins(16 if compact else 40, 12, 16 if compact else 40, 12)
            self._settings_actions.setDirection(QHBoxLayout.Direction.TopToBottom if compact else QHBoxLayout.Direction.LeftToRight)
            narrow = self.width() < 820
            for grid, labels, controls in self._settings_grids:
                for row, (label, control) in enumerate(zip(labels, controls)):
                    grid.removeWidget(label)
                    grid.removeWidget(control)
                    grid.addWidget(label, row * 2 if narrow else row, 0)
                    grid.addWidget(control, row * 2 + 1 if narrow else row, 0 if narrow else 1)
                    label.setMinimumHeight(30 if narrow else 44)
                    control.setMinimumWidth(0 if narrow else 240)
                    control.setMinimumContentsLength(8)
                    control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        super().resizeEvent(event)
        if hasattr(self, "history_list"):
            QTimer.singleShot(0, self._resize_history_cards)
        if hasattr(self, "_dictionary_actions"):
            for row in (self._dictionary_actions, self._dictionary_selection_actions, self._dictionary_add_row):
                row.setDirection(QHBoxLayout.Direction.TopToBottom if compact else QHBoxLayout.Direction.LeftToRight)
        if hasattr(self, "_history_toolbar"):
            for row in (self._history_toolbar, self._recovery_actions):
                row.setDirection(QHBoxLayout.Direction.TopToBottom if compact else QHBoxLayout.Direction.LeftToRight)

    def closeEvent(self, event):
        event.ignore()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    @staticmethod
    def _scrollable_page(page):
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName("settingsPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def refresh(self):
        if self._refresh_in_progress or self._history_refresh_in_progress:
            return
        self._refresh_in_progress = True
        self._set_status_badge("正在检查")
        dictionary_generation = self._dictionary_generation

        def run():
            try:
                import yaml
                config_text = self.paths.config_file.read_text(encoding="utf-8")
                config = yaml.safe_load(config_text) or {}
                active = config.get("engine", {}).get("active", "sensevoice")
                payload = {
                    "ok": True,
                    "config": config,
                    "config_text": config_text,
                    "ready": self._engine_ready(active, config),
                    "microphones": self._query_microphones(),
                    "history_rows": self._read_history_rows(),
                    "dictionary_entries": self._read_dictionary_entries(),
                    "dictionary_generation": dictionary_generation,
                    "recovery_sessions": self.recovery_store.list_recoverable(),
                    "dictation_preferences": (
                        self.controller.query_dictation_preferences() if self.controller else {}),
                }
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
            self.refresh_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-settings-refresh",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_refresh(self, payload):
        self._refresh_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge(
                f"状态刷新失败：{payload.get('error', '未知错误')}",
                attention=True,
            )
            return
        config = payload["config"]
        self._history_rows = payload["history_rows"]
        apply_dictionary = (not self._dictionary_dirty and not self._dictionary_save_in_progress
                            and payload.get("dictionary_generation") == self._dictionary_generation)
        if apply_dictionary:
            self._dictionary_entries = payload["dictionary_entries"]
        self._active_dictionary_filename = self.dictionary_section.currentData()
        if not self._settings_dirty() and not self._switch_in_progress:
            self._loading_settings = True
            self._refresh_settings_controls(config, payload["microphones"])
            self._apply_dictation_preferences(payload.get("dictation_preferences", {}))
            self._config_snapshot = payload["config_text"]
            self._settings_baseline = self._settings_values()
            self._loading_settings = False
            self._settings_changed()
        self._refresh_home(config)
        self._render_history()
        if apply_dictionary:
            self._render_dictionary_section()
        self._apply_recovery_sessions(payload["recovery_sessions"])
        self._set_status_badge("就绪" if payload["ready"] and self._microphone_detected else "需要设置")
        self._sync_runtime_status(force=True)

    def _sync_runtime_status(self, *, force=False):
        snapshot = getattr(self.controller, "runtime_snapshot", None)
        if not callable(snapshot):
            return
        state = snapshot()
        audio_pid = state.get("worker_pids", {}).get("audio", 0)
        if audio_pid and audio_pid != getattr(self, "_microphone_worker_pid", 0):
            self._microphone_worker_pid = audio_pid
            self._microphone_refresh_pending = True
        if getattr(self, "_microphone_refresh_pending", False) and not self._refresh_in_progress:
            self._microphone_refresh_pending = False
            self.refresh()
        phase = state["phase"]
        if not force and phase == self._last_runtime_phase:
            return
        self._last_runtime_phase = phase
        labels = {"starting": "正在准备", "ready": "就绪", "recording": "录音中",
                  "finalizing": "正在完成", "delivering": "正在交付"}
        self._set_status_badge(labels.get(phase, "需要处理"), attention=phase in {"degraded", "error"})
        readiness = "正在准备" if phase == "starting" else (
            "可用" if state["final_asr"] == "ready" and phase not in {"degraded", "error"} else "需要检查"
        )
        self.home_model.setText(f"本地识别 · {readiness}")

    def _query_microphones(self):
        query = getattr(self.controller, "query_microphones", None)
        return query() if query is not None else []

    def _set_status_badge(self, text, attention=None):
        if str(text) not in {"正在检查", "正在准备", "就绪", "需要设置", "需要处理", "录音中", "正在完成", "正在交付"}:
            self.operation_feedback.setText(str(text))
            self.operation_details_button.hide()
            self.operation_feedback.setProperty("attention", bool(attention))
            style = self.operation_feedback.style()
            style.unpolish(self.operation_feedback)
            style.polish(self.operation_feedback)
            self.operation_feedback.show()
            return
        if attention is None:
            attention = any(
                keyword in str(text)
                for keyword in ("失败", "需要", "请先", "不可用", "无可")
            )
        self.status_badge.setProperty("attention", bool(attention))
        self.status_badge.setText(str(text))
        style = self.status_badge.style()
        style.unpolish(self.status_badge)
        style.polish(self.status_badge)

    def _show_operation_details(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("操作详情")
        dialog.setText("更改尚未保存，当前草稿已保留。")
        dialog.setDetailedText(getattr(self, "_operation_error", ""))
        dialog.exec()

    def needs_onboarding(self):
        return not onboarding_completed(self.paths.config_file)

    def complete_onboarding(self, *, manual=False):
        if manual and not self.onboarding_confirm_check.isChecked():
            return
        if self._onboarding_save_in_progress:
            return
        self._onboarding_save_in_progress = True
        self.confirm_onboarding_button.setEnabled(False)

        def run():
            try:
                set_onboarding_completed(self.paths.config_file, True)
                result = {"ok": True}
            except Exception:
                logger.warning("first use state persistence failed")
                result = {"ok": False}
            self.onboarding_finished.emit(result)

        threading.Thread(target=run, name="voiceflow-first-use-save", daemon=True).start()

    @Slot(object)
    def _finish_onboarding(self, result):
        self._onboarding_save_in_progress = False
        if result.get("ok"):
            self._onboarding_confirmed = True
            self.onboarding_panel.hide()
            self._set_status_badge("首次听写已确认")
        else:
            self.confirm_onboarding_button.setEnabled(self.onboarding_confirm_check.isChecked())
            self._set_status_badge("首次使用状态未保存，请稍后重试", attention=True)

    def _refresh_home(self, config):
        self.onboarding_panel.setVisible(
            not self._onboarding_confirmed
            and not bool(config.get("ui", {}).get("onboarding_completed", False))
        )
        active = config.get("engine", {}).get("active", "sensevoice")
        model_ready = self._engine_ready(active, config)
        microphone_ready = self._microphone_detected
        all_ready = model_ready and microphone_ready
        self.home_ready_title.setText("开口，文字就位。")
        self.home_ready_subtitle.setText(
            f"按 {trigger_summary()} 开始说话，再按一次停止。录音与识别在本机完成。"
            if all_ready
            else "选择可用麦克风并确认本地识别可用后，即可开始听写。"
        )
        self.home_microphone.setText(
            "麦克风 · 可用" if microphone_ready else "麦克风 · 需要选择"
        )
        self.home_model.setText(
            "本地识别 · 可用" if model_ready else "本地识别 · 需要检查"
        )

    def event(self, event):
        if (getattr(self, "_system_style_ready", False) and event.type() in {
                QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange,
                QEvent.Type.ThemeChange}):
            self._refresh_system_style()
        return super().event(event)

    def showEvent(self, event):
        self._refresh_system_style()
        super().showEvent(event)

    def _refresh_system_style(self):
        high_contrast = self._high_contrast_enabled()
        if high_contrast != self._high_contrast_active:
            self._high_contrast_active = high_contrast
            self.setStyleSheet("" if high_contrast else self._style())

    def _high_contrast_enabled(self):
        return system_high_contrast_enabled()

class OverlayWindow:

    def __init__(self, paths=None, controller=None):
        if paths is None:
            project_root = os.path.dirname(os.path.dirname(__file__))
            paths = AppPaths.discover(
                config_path=os.path.join(project_root, "config.yaml")
            )
        self.paths = paths
        self.controller = controller
        self.window = None
        self.web_view = None
        self._native_renderer = os.environ.get("VOICEFLOW_CAPSULE_RENDERER", "native") != "webengine"
        self._bridge = None
        self._tray = None
        self._quit_coordinator = None
        self._quit_action_states = []
        self._quit_tooltip = ""
        self._tray_icons = {}
        self._on_record_toggle = (
            (lambda *_args: controller.toggle_recording(source="tray"))
            if controller else None
        )
        self._on_copy_last = controller.copy_last if controller else None
        self._on_repaste_last = controller.repaste_last if controller else None
        self._on_copy_text = controller.copy_text if controller else None
        self._on_output_text = controller.output_text if controller else None
        self._on_open_dictionary = controller.open_dictionary if controller else None
        self._on_quit = controller.quit if controller else None
        self._on_recording_painted = (
            controller.recording_painted if controller else None
        )
        self._on_preview_painted = controller.preview_painted if controller else None
        self._on_recover_session = controller.recover_session if controller else None
        self._on_delete_recovery = controller.delete_recovery if controller else None
        self._on_read_history = controller.read_history if controller else None
        self._on_delete_history = controller.delete_history if controller else None
        self._on_clear_history = controller.clear_history if controller else None
        self._on_clear_local_data = (
            controller.clear_local_data if controller else None
        )
        self._on_restore_history = controller.restore_history if controller else None
        self._recording_feedback_lock = threading.Lock()
        self._pending_recording_feedback = None
        self._html_path = str(self.paths.install_resource("src/overlay.html"))
        self._on_ready = None
        self._window_width = 380
        self._window_height = 48
        self._tray_menu = None
        self._tray_actions = []
        self._hide_timer = None
        self._settings_window = None
        self._single_instance_server = None
        self._instance_request_timer = None
        self._instance_request_path = Path(self.paths.data_dir) / "show-settings.request"
        instance_id = os.environ.get("VOICEFLOW_INSTANCE_ID", "").strip()
        self._instance_name = (
            f"{SINGLE_INSTANCE_NAME}.{instance_id}"
            if instance_id
            else SINGLE_INSTANCE_NAME
        )
        self._preview_paint_reporter = None
        self._web_channel = None
        self._ui_watchdog_timer = None
        self._ui_watchdog_stop = None

    def set_actions(
        self,
        on_record_toggle=None,
        on_copy_last=None,
        on_repaste_last=None,
        on_copy_text=None,
        on_output_text=None,
        on_open_dictionary=None,
        on_quit=None,
        on_recording_painted=None,
        on_preview_painted=None,
        on_recover_session=None,
        on_delete_recovery=None,
        on_read_history=None,
        on_delete_history=None,
        on_clear_history=None,
        on_clear_local_data=None,
        on_restore_history=None,
    ):
        self._on_record_toggle = on_record_toggle
        self._on_copy_last = on_copy_last
        self._on_repaste_last = on_repaste_last
        self._on_copy_text = on_copy_text
        self._on_output_text = on_output_text
        self._on_open_dictionary = on_open_dictionary
        self._on_quit = on_quit
        self._on_recording_painted = on_recording_painted
        self._on_preview_painted = on_preview_painted
        self._on_recover_session = on_recover_session
        self._on_delete_recovery = on_delete_recovery
        self._on_read_history = on_read_history
        self._on_delete_history = on_delete_history
        self._on_clear_history = on_clear_history
        self._on_clear_local_data = on_clear_local_data
        self._on_restore_history = on_restore_history
        if self._settings_window is not None:
            self._settings_window.set_history_actions(
                read=on_read_history,
                delete=on_delete_history,
                clear=on_clear_history,
                clear_local_data=on_clear_local_data,
                restore=on_restore_history,
            )

    def start(self, on_ready=None):
        self._on_ready = on_ready
        self._run()

    def _run(self):
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        if self._notify_existing_instance():
            return
        self._start_single_instance_server()
        self._start_instance_request_polling()

        # ---- 主窗口 ----
        self.window = _PaintAwareWindow()
        self.window.first_paint_completed.connect(self._recording_painted)
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

        if self._native_renderer:
            self.web_view = NativeCapsuleView()
            self.web_view.preview_painted.connect(self._preview_painted)
            self._bridge = NativeCapsuleBridge(self.web_view, self._expect_recording_paint)
        else:
            from qt_compat import QWebChannel, QWebEngineView
            self.web_view = QWebEngineView()
            self._preview_paint_reporter = _PreviewPaintReporter()
            self._preview_paint_reporter.painted.connect(self._preview_painted)
            self._web_channel = QWebChannel(self.web_view.page())
            self._web_channel.registerObject("voiceflowBridge", self._preview_paint_reporter)
            self.web_view.page().setWebChannel(self._web_channel)
            self.web_view.setUrl(QUrl.fromLocalFile(self._html_path))
            self.web_view.setStyleSheet("background: transparent;")
            self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
            self._bridge = _Bridge(self.web_view, before_show=self._expect_recording_paint)
        # 连接 show/hide 信号（线程安全）
        self._bridge.show_requested.connect(self._show)
        self._bridge.hide_requested.connect(self._hide)
        self._bridge.hide_after_requested.connect(self._hide_after)
        self._bridge.tray_state_requested.connect(self._set_tray_state)
        self._bridge.settings_requested.connect(self._show_settings)
        self._bridge.startup_requested.connect(self._show_startup)
        self._bridge.onboarding_completed_requested.connect(
            self._complete_onboarding
        )

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

        self._start_ui_watchdog(app)

        app.exec()

    def _start_ui_watchdog(self, app):
        detector = UiStallDetector(
            threshold_ms=50,
            initial_time=time.perf_counter(),
        )
        timer = QTimer()
        timer.setInterval(16)
        timer.timeout.connect(lambda: detector.tick(time.perf_counter()))
        timer.start()
        stop_event = threading.Event()

        def watch():
            while not stop_event.wait(0.025):
                stall_ms = detector.poll(time.perf_counter())
                if stall_ms is not None:
                    logger.warning(
                        "UI event loop stalled",
                        extra={"event": "ui_stall", "duration_ms": stall_ms,
                               "phase": self.controller.runtime_snapshot()["phase"] if self.controller else "unknown"},
                    )

        threading.Thread(
            target=watch,
            name="voiceflow-ui-watchdog",
            daemon=True,
        ).start()
        app.aboutToQuit.connect(stop_event.set)
        self._ui_watchdog_timer = timer
        self._ui_watchdog_stop = stop_event

    def _notify_existing_instance(self):
        socket = QLocalSocket()
        socket.connectToServer(self._instance_name)
        if not socket.waitForConnected(120):
            socket.abort()
            return False
        self._write_instance_request()
        socket.write(b"show\n")
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.waitForReadyRead(1500)
        socket.abort()
        return True

    def _start_single_instance_server(self):
        server = QLocalServer()
        if not server.listen(self._instance_name):
            QLocalServer.removeServer(self._instance_name)
            if not server.listen(self._instance_name):
                return
        server.newConnection.connect(self._on_instance_message)
        self._single_instance_server = server

    def _write_instance_request(self):
        request_path = self._instance_request_path
        temporary = request_path.with_name(
            f"{request_path.name}.{os.getpid()}.tmp"
        )
        try:
            request_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(f"{time.time():.6f}\n", encoding="utf-8")
            os.replace(temporary, request_path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _start_instance_request_polling(self):
        timer = QTimer()
        timer.setInterval(200)
        timer.timeout.connect(self._consume_instance_request)
        timer.start()
        self._instance_request_timer = timer

    def _consume_instance_request(self):
        request_path = self._instance_request_path
        try:
            requested_at = float(request_path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            return
        try:
            request_path.unlink(missing_ok=True)
        except OSError:
            return
        # Hosted Windows machines and user PCs can move wall time slightly
        # backwards while synchronizing.  A fresh atomic request remains valid
        # across that small correction, while genuinely stale files stay ignored.
        if -2 <= time.time() - requested_at <= 10:
            self._show_settings()

    def _on_instance_message(self):
        if not self._single_instance_server:
            return
        while self._single_instance_server.hasPendingConnections():
            socket = self._single_instance_server.nextPendingConnection()
            self._handle_instance_message(socket)

    def _handle_instance_message(self, socket):
        socket.readAll()
        self._show_settings()
        socket.write(b"shown\n")
        socket.flush()
        socket.disconnectFromServer()

    # ============================================================
    # 托盘
    # ============================================================

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        icon_path = str(
            self.paths.install_resource(f"assets/{icon_asset_name()}")
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

        dictate_act = QAction("开始 / 停止听写", self._tray_menu)
        if self._on_record_toggle:
            dictate_act.triggered.connect(self._on_record_toggle)
        else:
            dictate_act.setEnabled(False)
        self._tray_menu.addAction(dictate_act)
        self._tray_actions.append(dictate_act)

        self._tray_menu.addSeparator()

        show_act = QAction("打开设置", self._tray_menu)
        show_act.triggered.connect(self._show_settings)
        self._tray_menu.addAction(show_act)
        self._tray_actions.append(show_act)

        copy_last_act = QAction("复制上一次结果", self._tray_menu)
        copy_last_act.triggered.connect(self._copy_last)
        self._tray_menu.addAction(copy_last_act)
        self._tray_actions.append(copy_last_act)
        self._setup_sentence_end_menu()

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

    def _setup_sentence_end_menu(self):
        self._sentence_end_menu = self._tray_menu.addMenu("句末标点 · 默认值")
        self._tray_actions.append(self._sentence_end_menu.menuAction())
        for mode, label in SENTENCE_END_CHOICES:
            action = self._sentence_end_menu.addAction(label)
            action.setCheckable(True)
            action.setData(mode)
            action.triggered.connect(lambda _checked=False, value=mode: self._save_tray_sentence_end(value))
        self._sentence_end_menu.aboutToShow.connect(self._refresh_sentence_end_menu)

    def _refresh_sentence_end_menu(self):
        snapshot = self.controller.query_dictation_preferences() if self.controller else {}
        current = snapshot.get("global", {}).get("sentence_end", "preserve")
        for action in self._sentence_end_menu.actions():
            action.setChecked(action.data() == current)
            action.setEnabled(bool(snapshot) and not getattr(self, "_tray_sentence_save_in_progress", False))

    def _save_tray_sentence_end(self, mode):
        if self.controller is None or getattr(self, "_tray_sentence_save_in_progress", False):
            return
        self._tray_sentence_save_in_progress = True

        def run():
            try:
                snapshot = self.controller.query_dictation_preferences()
                result = self.controller.update_dictation_preferences({
                    "sentence_end": mode,
                    "preserve_format": snapshot.get("global", {}).get("preserve_format", False),
                    "expected": snapshot.get("global"),
                })
                if not result:
                    raise RuntimeError("settings unavailable")
            except Exception:
                self.show_error("标点设置未保存，请重试或检查磁盘空间")
            finally:
                self._tray_sentence_save_in_progress = False

        threading.Thread(target=run, name="voiceflow-tray-punctuation", daemon=True).start()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_settings()

    def _show(self):
        if self.window:
            self._center_window()
            self.window.show()

    def _expect_recording_paint(self):
        self._cancel_pending_hide()
        if self.window:
            self.window.expect_first_paint()

    def _recording_painted(self):
        with self._recording_feedback_lock:
            pending = self._pending_recording_feedback
            self._pending_recording_feedback = None
        if not pending or not self._on_recording_painted:
            return
        session_id, triggered_at = pending
        elapsed_ms = (time.perf_counter() - triggered_at) * 1000
        self._on_recording_painted(session_id, elapsed_ms)

    def _preview_painted(self, session_id):
        if self._on_preview_painted:
            self._on_preview_painted(session_id, time.perf_counter())

    def _hide(self):
        if self.window:
            self.window.hide()

    def _ensure_settings_window(self):
        if self._settings_window is None:
            self._settings_window = _SettingsWindow(
                on_copy_text=self._on_copy_text,
                on_repaste_text=self._on_output_text,
                on_recover_session=self._on_recover_session,
                on_delete_recovery=self._on_delete_recovery,
                on_read_history=self._on_read_history,
                on_delete_history=self._on_delete_history,
                on_clear_history=self._on_clear_history,
                on_clear_local_data=self._on_clear_local_data,
                on_restore_history=self._on_restore_history,
                controller=self.controller,
                paths=self.paths,
            )
        return self._settings_window

    def _show_settings(self):
        self._ensure_settings_window()
        self._settings_window.refresh()
        if self._settings_window.isMinimized():
            self._settings_window.showNormal()
        else:
            self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _show_startup(self):
        window = self._ensure_settings_window()
        if window.needs_onboarding() or not QSystemTrayIcon.isSystemTrayAvailable():
            self._show_settings()

    def _complete_onboarding(self):
        if self._settings_window is not None:
            self._settings_window.complete_onboarding()
            return
        if not onboarding_completed(self.paths.config_file):
            set_onboarding_completed(self.paths.config_file, True)

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
            if self._native("reset", hide=True):
                return
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
        self._copy_last()

    def _open_dictionary(self):
        if self._on_open_dictionary:
            self._on_open_dictionary()

    def quit(self):
        if self._quit_coordinator is None:
            self._quit_coordinator = _QuitCoordinator(self._on_quit, self._finish_quit)
        if self._quit_coordinator.start():
            self._quit_action_states = [(action, action.isEnabled()) for action in self._tray_actions]
            for action, _enabled in self._quit_action_states:
                action.setEnabled(False)
            if self._tray:
                self._quit_tooltip = self._tray.toolTip()
                self._tray.setToolTip("VoiceFlow · 正在退出")

    def _finish_quit(self, error):
        if error is not None:
            for action, enabled in self._quit_action_states:
                action.setEnabled(enabled)
            if self._tray:
                self._tray.setToolTip(self._quit_tooltip)
            self.show_error("退出未完成，请从托盘重试。")
            return
        if self._tray:
            self._tray.setVisible(False)
        app = QApplication.instance()
        if app:
            app.quit()

    # ============================================================
    # 对外接口 — 线程安全（通过 _Bridge 信号）
    # ============================================================

    def _js(self, code):
        if self._bridge:
            self._bridge.js_requested.emit(code)

    def _native(self, command, *args, show=False, hide=False):
        if not self._native_renderer:
            return False
        if self._bridge:
            signal = (self._bridge.render_then_show_requested if show else
                      self._bridge.render_then_hide_requested if hide else
                      self._bridge.render_requested)
            signal.emit(command, list(args))
        return True

    def _tray_state(self, state):
        if self._bridge:
            self._bridge.tray_state_requested.emit(state)

    def show_recording(self, session_id, triggered_at=None):
        self._tray_state(TRAY_ICON_RECORDING)
        if triggered_at is not None:
            with self._recording_feedback_lock:
                self._pending_recording_feedback = (
                    int(session_id),
                    float(triggered_at),
                )
        if self._bridge:
            if self._native("prepare_recording", int(session_id), show=True):
                return
            self._bridge.js_then_show_requested.emit(f"prepareRecording({int(session_id)})")

    def append_streaming(self, delta, session_id):
        if self._native("append_streaming", delta, int(session_id)):
            return
        self._js(
            f"appendStreaming({json.dumps(delta, ensure_ascii=False)}, {int(session_id)})"
        )

    def update_transcript_state(self, state):
        if self._native("transcript", state.authoritative_prefix, state.draft_tail, int(state.session_id)):
            return
        self._js(
            "updateTranscriptState("
            f"{json.dumps(state.authoritative_prefix, ensure_ascii=False)}, "
            f"{json.dumps(state.draft_tail, ensure_ascii=False)}, "
            f"{int(state.session_id)})"
        )

    def show_authoritative_final(self, text, session_id):
        if self._native("final", text, int(session_id)):
            return
        self._js(
            "showAuthoritativeFinal("
            f"{json.dumps(text, ensure_ascii=False)}, {int(session_id)})"
        )

    def update_audio_level(self, levels, session_id):
        if self._native("levels", [max(0.0, min(float(level), 1.0)) for level in levels[:3]], int(session_id)):
            return
        if self._bridge:
            safe_levels = [max(0.0, min(float(level), 1.0)) for level in levels[:3]]
            self._bridge.level_js_requested.emit(
                f"updateAudioLevel({json.dumps(safe_levels)}, {int(session_id)})"
            )

    def show_processing(self):
        self._tray_state(TRAY_ICON_PROCESSING)
        if self._native("processing"):
            return
        self._js("showProcessing()")

    def show_settling(self, session_id):
        self._tray_state(TRAY_ICON_PROCESSING)
        if self._native("settling", int(session_id)):
            return
        self._js(f"showSettling({int(session_id)})")


    def show_delivery_state(self, status, session_id):
        self._tray_state(TRAY_ICON_IDLE)
        if self._native("delivery", str(status), int(session_id)):
            return
        self._js(
            "showDeliveryState("
            f"{json.dumps(str(status))}, "
            f"{int(session_id)})"
        )


    def show_result(self, text):
        if self._native("label", "success", text):
            self._tray_state(TRAY_ICON_IDLE)
            return
        self._js(f"showResult({json.dumps(text, ensure_ascii=False)})")
        self._tray_state(TRAY_ICON_IDLE)

    def show_error(self, msg):
        self._tray_state(TRAY_ICON_ERROR)
        if self._native("label", "error", msg):
            return
        self._js(f"showState('error', {json.dumps(msg, ensure_ascii=False)})")

    def show_recovery_available(self, count):
        self._tray_state(TRAY_ICON_IDLE)
        if not self._native("label", "recovery", "有未完成的听写"):
            self._js(f"showRecoveryAvailable({int(count)})")
        self.show_window()
        self.hide_after(3600)

    def show_canceled(self):
        self._tray_state(TRAY_ICON_IDLE)
        display = display_for_state(UiState.CANCELED)
        if self._native("label", display.css_class, display.label):
            return
        self._js(f"showState({json.dumps(display.css_class)}, {json.dumps(display.label, ensure_ascii=False)})")

    def show_idle(self):
        self._tray_state(TRAY_ICON_IDLE)
        display = display_for_state(UiState.IDLE)
        if self._native("reset"):
            return
        self._js(f"showState({json.dumps(display.css_class)}, {json.dumps(display.label, ensure_ascii=False)})")

    def show_window(self):
        if self._bridge:
            self._bridge.show_requested.emit()

    def show_settings_window(self):
        if self._bridge:
            self._bridge.settings_requested.emit()

    def show_startup_window(self):
        if self._bridge:
            self._bridge.startup_requested.emit()

    def complete_onboarding(self):
        if self._bridge:
            self._bridge.onboarding_completed_requested.emit()

    def hide_after(self, ms=2000):
        if self._bridge:
            self._bridge.hide_after_requested.emit(ms)


# ============================================================
# 信号桥 — 所有跨线程 Qt 操作经过这里
# ============================================================

class _Bridge(QObject):
    js_requested = Signal(str)
    level_js_requested = Signal(str)
    show_requested = Signal()
    hide_requested = Signal()
    js_then_show_requested = Signal(str)
    js_then_hide_requested = Signal(str)
    hide_after_requested = Signal(int)
    tray_state_requested = Signal(str)
    settings_requested = Signal()
    startup_requested = Signal()
    onboarding_completed_requested = Signal()
    def __init__(self, web_view, before_show=None):
        super().__init__()
        self._web_view = web_view
        self._before_show = before_show
        self._page_ready = False
        self._pending_js = []
        self._level_mailbox = _LatestPreviewMailbox()
        self._level_flush_scheduled = False
        self._web_view.loadFinished.connect(self._on_load_finished)
        self.js_requested.connect(self._run_js)
        self.level_js_requested.connect(self._queue_level_js)
        self.js_then_show_requested.connect(self._run_js_then_show)
        self.js_then_hide_requested.connect(self._run_js_then_hide)
        # show/hide 信号连接到自身的方法只是为了统一管理，
        # 实际执行由 OverlayWindow._show/_hide 通过外部连接完成
        # 这里只做 JS 桥接

    @Slot(bool)
    def _on_load_finished(self, ok):
        if not ok:
            return
        self._page_ready = True
        for code in self._pending_js:
            self._run_js(code)
        self._pending_js = []

    @Slot(str)
    def _run_js(self, code):
        if not self._page_ready:
            self._pending_js.append(code)
            return
        if self._web_view and self._web_view.page():
            self._web_view.page().runJavaScript(code)

    @Slot(str)
    def _queue_level_js(self, code):
        self._level_mailbox.put(code)
        if self._level_flush_scheduled:
            return
        self._level_flush_scheduled = True
        QTimer.singleShot(16, self._flush_level_js)

    @Slot()
    def _flush_level_js(self):
        self._level_flush_scheduled = False
        code = self._level_mailbox.take()
        if code is not None:
            self._run_js(code)

    @Slot(str)
    def _run_js_then_show(self, code):
        if not self._page_ready or not self._web_view or not self._web_view.page():
            return
        if self._before_show:
            self._before_show()
        self._web_view.page().runJavaScript(code, lambda _: self.show_requested.emit())

    @Slot(str)
    def _run_js_then_hide(self, code):
        self.hide_requested.emit()
        if not self._page_ready or not self._web_view or not self._web_view.page():
            return
        self._web_view.page().runJavaScript(code)
