"""
VoiceFlow 悬浮窗。Qt 主线程 + 信号桥接，所有跨线程 UI 操作线程安全。
"""

import json
import logging
import os
import sys
import time
import threading
import copy
import tempfile
from datetime import datetime
from pathlib import Path

from qt_compat import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSystemTrayIcon, QMenu, QLabel, QPushButton,
    QGridLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLineEdit, QStackedWidget,
    QListView, QAbstractItemView,
    QCheckBox, QComboBox, QMessageBox, QScrollArea,
    Qt, QUrl, QSize, QObject, Signal, Slot, QTimer,
    QAction, QLocalServer, QLocalSocket, QEvent,
    QIcon, QPixmap, QPainter, QPen, QColor, QRectF, QPointF,
)

from tray_icon import (
    TRAY_ICON_ERROR,
    TRAY_ICON_IDLE,
    TRAY_ICON_PROCESSING,
    TRAY_ICON_RECORDING,
    build_tray_icon,
)
from ui_state import UiState, display_for_state
from history_store import HistoryStore
from settings_store import (
    is_autostart_enabled,
    onboarding_completed,
    set_autostart,
    set_onboarding_completed,
    update_runtime_settings,
)
from runtime_paths import AppPaths, RuntimeMode
from version import APP_VERSION, display_version
from update_checker import check_latest_release
from runtime_services import (
    ModelManager,
    ModelState,
    format_diagnostics,
    run_runtime_diagnostics,
)
from platform_utils import (
    data_location_label,
    icon_asset_name,
    open_path,
    platform_label,
    trigger_instruction,
    trigger_summary,
    system_high_contrast_enabled,
)
from recovery_session import RecoverySessionStore
from runtime_monitor import UiStallDetector
from capsule_native import NativeCapsuleBridge, NativeCapsuleView
from punctuation import SENTENCE_END_CHOICES, apply_sentence_end
from dictation_preferences import application_preserves_format, normalize_app_id, PreferencesChangedError


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


class _SettingsWindow(QMainWindow):
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

    def _home_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        self._home_layout = layout
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)

        intro = QVBoxLayout()
        intro.setSpacing(8)
        self.home_ready_title = QLabel("开口，文字就位。")
        self.home_ready_title.setWordWrap(True)
        self.home_ready_title.setObjectName("commandTitle")
        self.home_ready_subtitle = QLabel(
            f"按 {trigger_summary()} 开始说话，再按一次停止。录音与识别在本机完成。"
        )
        self.home_ready_subtitle.setObjectName("commandSubtitle")
        self.home_ready_subtitle.setWordWrap(True)
        intro.addWidget(self.home_ready_title)
        intro.addWidget(self.home_ready_subtitle)
        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(8)
        for text in ("F2", "右 Ctrl", "鼠标侧键"):
            key = QLabel(text)
            key.setObjectName("shortcutKey")
            shortcuts.addWidget(key)
        shortcuts.addStretch(1)
        intro.addLayout(shortcuts)
        layout.addLayout(intro)

        self.onboarding_panel = QWidget()
        onboarding_layout = QVBoxLayout(self.onboarding_panel)
        onboarding_layout.setContentsMargins(0, 0, 0, 0)
        onboarding_help = QLabel(
            "首次使用：把光标放到其他应用的输入位置，按快捷键说一句话，再按一次停止。"
            "检查文字是否正确出现；没有出现时，可在目标位置按 Ctrl+V。"
        )
        onboarding_help.setWordWrap(True)
        onboarding_layout.addWidget(onboarding_help)
        self.onboarding_confirm_check = QCheckBox("已确认目标应用输入正确")
        onboarding_layout.addWidget(self.onboarding_confirm_check)
        self.confirm_onboarding_button = QPushButton("完成首次使用")
        self.confirm_onboarding_button.setEnabled(False)
        self.confirm_onboarding_button.clicked.connect(lambda: self.complete_onboarding(manual=True))
        self.onboarding_confirm_check.toggled.connect(
            lambda checked: self.confirm_onboarding_button.setEnabled(
                checked and not self._onboarding_save_in_progress)
        )
        onboarding_layout.addWidget(self.confirm_onboarding_button)
        self.onboarding_panel.setVisible(False)
        layout.addWidget(self.onboarding_panel)

        settings_panel = QWidget()
        settings_panel.setObjectName("dictationSettingsPanel")
        settings_layout = QVBoxLayout(settings_panel)
        self._settings_panel_layout = settings_layout
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(8)

        # Grouped rows, as in macOS System Settings: a caption, then a card of label/control rows.
        def group(caption):
            title = QLabel(caption)
            title.setObjectName("groupCaption")
            settings_layout.addWidget(title)
            card = QWidget()
            card.setObjectName("groupCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 6, 16, 6)
            card_layout.setSpacing(0)
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(0)
            grid.setColumnStretch(0, 1)
            card_layout.addLayout(grid)
            settings_layout.addWidget(card)
            settings_layout.addSpacing(14)
            return card_layout, grid

        def add_row(grid, row, name, control):
            label = QLabel(name)
            label.setObjectName("fieldName")
            label.setMinimumHeight(44)
            control.setMinimumWidth(240)
            grid.addWidget(label, row, 0)
            grid.addWidget(control, row, 1)
            return label

        input_card, fields = group("输入")
        self.language_combo = QComboBox()
        self.language_combo.setAccessibleName("识别语言")
        self.microphone_combo = QComboBox()
        self.microphone_combo.setAccessibleName("麦克风")
        self.language_combo.setObjectName("fieldValue")
        self.microphone_combo.setObjectName("fieldValue")
        field_labels = [
            add_row(fields, row, name, value)
            for row, (name, value) in enumerate((
                ("识别语言", self.language_combo),
                ("麦克风", self.microphone_combo),
            ))
        ]
        self.autostart_check = QCheckBox(
            "登录系统后自动启动" if sys.platform == "darwin" else "登录 Windows 后自动启动"
        )
        self.autostart_check.setAccessibleName("开机自动启动 VoiceFlow")
        self.autostart_check.setMinimumHeight(44)
        input_card.addWidget(self.autostart_check)

        format_card, format_fields = group("标点与格式")
        self.dictation_scope_combo = QComboBox()
        self.dictation_scope_combo.setAccessibleName("句末策略适用范围")
        self.dictation_scope_combo.addItem("所有应用的默认值", None)
        self.sentence_end_combo = QComboBox()
        self.sentence_end_combo.setAccessibleName("句末标点")
        for value, label in SENTENCE_END_CHOICES:
            self.sentence_end_combo.addItem(label, value)
        field_labels += [
            add_row(format_fields, 0, "适用范围", self.dictation_scope_combo),
            add_row(format_fields, 1, "句末标点", self.sentence_end_combo),
        ]
        self.preserve_format_check = QCheckBox("保留格式")
        self.preserve_format_check.setAccessibleName("保留输入格式")
        self.preserve_format_check.setMinimumHeight(44)
        format_card.addWidget(self.preserve_format_check)
        self.sentence_end_sample = QLabel()
        self.sentence_end_sample.setObjectName("rowNote")
        self.sentence_end_sample.setWordWrap(True)
        self.dictation_scope_note = QLabel("应用设置优先；代码编辑器和终端默认保留格式。")
        self.dictation_scope_note.setObjectName("rowNote")
        self.dictation_scope_note.setWordWrap(True)
        format_card.addWidget(self.sentence_end_sample)
        format_card.addWidget(self.dictation_scope_note)
        sentence_actions = QHBoxLayout()
        self.follow_default_button = QPushButton("跟随默认值")
        self.follow_default_button.setObjectName("textButton")
        self.follow_default_button.setAccessibleName("移除此应用的标点与格式设置，跟随默认值")
        self.follow_default_button.setEnabled(False)
        self.follow_default_button.clicked.connect(self._draft_follow_default)
        sentence_actions.addWidget(self.follow_default_button)
        sentence_actions.addStretch(1)
        format_card.addLayout(sentence_actions)
        format_card.addSpacing(6)
        self.dictation_scope_combo.currentIndexChanged.connect(self._change_dictation_scope)
        self.sentence_end_combo.currentIndexChanged.connect(self._update_sentence_end_sample)
        self.preserve_format_check.toggled.connect(self._update_sentence_end_sample)
        self._update_sentence_end_sample()

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._settings_actions = actions
        save_note = QLabel("文字习惯下次听写生效；语言和麦克风更改需重启")
        save_note.setWordWrap(True)
        save_note.setObjectName("saveNote")
        actions.addWidget(save_note, 1)
        self.reload_settings_button = QPushButton("重新载入")
        self.reload_settings_button.clicked.connect(self._reload_settings)
        self.reload_settings_button.hide()
        actions.addWidget(self.reload_settings_button)
        self.save_settings_button = QPushButton("保存更改")
        self.save_settings_button.setObjectName("primaryButton")
        self.save_settings_button.setAccessibleName("保存听写设置")
        self.save_settings_button.clicked.connect(self._save_settings)
        actions.addWidget(self.save_settings_button)
        layout.addWidget(settings_panel)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.home_microphone = QLabel("麦克风 · 正在检查")
        self.home_microphone.setObjectName("systemStatusItem")
        self.home_model = QLabel("本地识别 · 正在检查")
        self.home_model.setObjectName("systemStatusItem")
        status_row.addWidget(self.home_microphone)
        status_row.addWidget(self.home_model)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        shortcut_hint = QLabel("文字会粘贴到当前光标；不能粘贴时，仍可从剪贴板取用。Esc 取消听写。")
        shortcut_hint.setWordWrap(True)
        shortcut_hint.setObjectName("sectionSubtitle")
        layout.addWidget(shortcut_hint)
        layout.addStretch(1)
        self.dictation_scroll = QScrollArea()
        self.dictation_scroll.setObjectName("dictationScroll")
        self.dictation_scroll.setAccessibleName("听写设置")
        self.dictation_scroll.setWidgetResizable(True)
        self.dictation_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.dictation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dictation_scroll.setWidget(page)
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.dictation_scroll, 1)
        footer = QWidget()
        footer.setObjectName("saveBar")
        footer.setLayout(actions)
        actions.setContentsMargins(40, 12, 40, 12)
        self._save_bar = footer
        outer.addWidget(footer)
        self._settings_grids = [
            (fields, field_labels[:2], (self.language_combo, self.microphone_combo)),
            (format_fields, field_labels[2:], (self.dictation_scope_combo, self.sentence_end_combo)),
        ]
        for widget in (self.language_combo, self.microphone_combo):
            widget.currentIndexChanged.connect(self._settings_changed)
        for widget in (self.autostart_check, self.preserve_format_check):
            widget.toggled.connect(self._settings_changed)
        self.sentence_end_combo.currentIndexChanged.connect(self._settings_changed)
        self.save_settings_button.setEnabled(False)
        return container

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

    def _recent_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(14)
        layout.addLayout(self._section_header("历史", "查看和复制最近结果。复制后，在需要的位置按 Ctrl+V。"))

        self.recovery_panel = QWidget()
        self.recovery_panel.setObjectName("recoveryPanel")
        recovery_layout = QVBoxLayout(self.recovery_panel)
        recovery_layout.setContentsMargins(14, 12, 14, 12)
        recovery_layout.setSpacing(8)
        self.recovery_summary = QLabel("")
        self.recovery_summary.setObjectName("recoveryTitle")
        self.recovery_detail = QLabel("尚未交付的录音不会自动删除。恢复并复制成功后删除；不再需要时可手动删除。")
        self.recovery_detail.setObjectName("sectionSubtitle")
        self.recovery_detail.setWordWrap(True)
        self.recovery_combo = QComboBox()
        self.recovery_combo.setAccessibleName("可恢复录音")
        recovery_actions = QHBoxLayout()
        self._recovery_actions = recovery_actions
        self.recover_button = QPushButton("重新识别并复制")
        self.recover_button.setObjectName("primaryButton")
        self.recover_button.clicked.connect(self._recover_selected_session)
        copy_preview = QPushButton("复制已有预览")
        copy_preview.clicked.connect(self._copy_recovery_preview)
        self.delete_recovery_button = QPushButton("删除录音")
        self.delete_recovery_button.clicked.connect(self._delete_recovery)
        self.recovery_combo.currentIndexChanged.connect(self._update_recovery_selection)
        recovery_actions.addWidget(self.recover_button)
        recovery_actions.addWidget(copy_preview)
        recovery_actions.addWidget(self.delete_recovery_button)
        recovery_actions.addStretch(1)
        recovery_layout.addWidget(self.recovery_summary)
        recovery_layout.addWidget(self.recovery_detail)
        recovery_layout.addWidget(self.recovery_combo)
        recovery_layout.addLayout(recovery_actions)
        self.recovery_panel.setVisible(False)
        layout.addWidget(self.recovery_panel)

        toolbar = QHBoxLayout()
        self._history_toolbar = toolbar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索最近转录")
        self.search_box.setAccessibleName("搜索历史转录")
        self.search_box.setClearButtonEnabled(True)
        self._history_search_timer = QTimer(self)
        self._history_search_timer.setSingleShot(True)
        self._history_search_timer.setInterval(140)
        self._history_search_timer.timeout.connect(self._render_history)
        self.search_box.textChanged.connect(
            lambda _text: self._history_search_timer.start()
        )
        toolbar.addWidget(self.search_box, 1)
        refresh = QPushButton("刷新")
        refresh.setObjectName("textButton")
        refresh.clicked.connect(self._refresh_history)
        toolbar.addWidget(refresh)
        copy_all = QPushButton("复制全部")
        copy_all.setObjectName("textButton")
        copy_all.clicked.connect(self._copy_all_visible)
        toolbar.addWidget(copy_all)
        clear_history = QPushButton("清空历史")
        clear_history.setObjectName("textButton")
        clear_history.clicked.connect(self._clear_history)
        toolbar.addWidget(clear_history)
        clear_local_data = QPushButton("清除本机数据")
        clear_local_data.setObjectName("destructiveTextButton")
        clear_local_data.clicked.connect(self._clear_local_data)
        toolbar.addWidget(clear_local_data)
        self.undo_history_button = QPushButton("撤销删除")
        self.undo_history_button.setObjectName("textButton")
        self.undo_history_button.setVisible(False)
        self.undo_history_button.clicked.connect(self._undo_history_delete)
        toolbar.addWidget(self.undo_history_button)
        layout.addLayout(toolbar)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.setAccessibleName("历史转录列表")
        self.history_list.itemDoubleClicked.connect(lambda item: self._copy_text(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.history_list, 1)

        return self._scrollable_page(page)

    def _dictionary_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(14)
        layout.addLayout(
            self._section_header(
                "词典",
                "英文术语会规范大小写；明确纠错不会改变你的原意。",
            )
        )

        self.dictionary_section = QComboBox()
        self.dictionary_section.setAccessibleName("词典分区")
        self.dictionary_section.addItem("内置 AI 术语", "builtin-ai.txt")
        self.dictionary_section.addItem("专有词", "user-dictionary.txt")
        self.dictionary_section.addItem("常用短语", "phrases.txt")
        self.dictionary_section.addItem("确定性纠错", "corrections.txt")
        self.dictionary_section.setMinimumWidth(180)
        self.dictionary_search = QLineEdit()
        self.dictionary_search.setPlaceholderText("搜索当前分类")
        self.dictionary_search.setAccessibleName("搜索词典")
        self.dictionary_search.setClearButtonEnabled(True)
        self.dictionary_search.textChanged.connect(self._filter_dictionary)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.dictionary_section)
        filter_row.addWidget(self.dictionary_search, 1)
        layout.addLayout(filter_row)
        dictionary_card = QWidget()
        dictionary_card.setObjectName("groupCard")
        card_layout = QVBoxLayout(dictionary_card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        add_row = QHBoxLayout()
        self._dictionary_add_row = add_row
        self.dictionary_input = QLineEdit()
        self.dictionary_input.setAccessibleName("新增词典条目")
        self.dictionary_input.setPlaceholderText("添加专有词")
        self.dictionary_input.returnPressed.connect(self._add_dictionary_entry)
        self.dictionary_correct_input = QLineEdit()
        self.dictionary_correct_input.setPlaceholderText("应改为")
        self.dictionary_correct_input.setAccessibleName("正确词")
        self.dictionary_correct_input.returnPressed.connect(self._add_dictionary_entry)
        self.dictionary_correct_input.hide()
        self.dictionary_add_button = QPushButton("添加")
        self.dictionary_add_button.setObjectName("primaryButton")
        self.dictionary_add_button.clicked.connect(self._add_dictionary_entry)
        add_row.addWidget(self.dictionary_input, 1)
        add_row.addWidget(self.dictionary_correct_input, 1)
        add_row.addWidget(self.dictionary_add_button)
        card_layout.addLayout(add_row)

        self.dictionary_hint = QLabel("每项单独一行，双击可以修改。")
        self.dictionary_hint.setObjectName("rowNote")
        self.dictionary_hint.setWordWrap(True)
        card_layout.addWidget(self.dictionary_hint)

        self.dictionary_list = QListWidget()
        self.dictionary_list.setObjectName("dictionaryList")
        self.dictionary_list.setAccessibleName("词典条目")
        self.dictionary_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.dictionary_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.dictionary_list.setWrapping(True)
        self.dictionary_list.setSpacing(8)
        self.dictionary_list.setMinimumHeight(180)
        self.dictionary_list.itemChanged.connect(self._dictionary_item_changed)
        card_layout.addWidget(self.dictionary_list, 1)
        layout.addWidget(dictionary_card, 1)

        self.dictionary_count = QLabel("0 项")
        self.dictionary_count.setObjectName("historyMeta")

        self.dictionary_section.currentIndexChanged.connect(
            self._change_dictionary_section
        )
        self._active_dictionary_filename = self.dictionary_section.currentData()

        note = QLabel(
            "词典只保存在这台电脑。纠错只按你指定的两个词替换，不改写你的意思。"
        )
        note.setObjectName("rowNote")
        note.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.dictionary_remove_button = QPushButton("删除所选")
        self.dictionary_remove_button.setObjectName("textButton")
        self._dictionary_actions = actions
        self.dictionary_remove_button.clicked.connect(
            self._remove_dictionary_entries
        )
        save = self.dictionary_save_button = QPushButton("保存词典")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_dictionary)
        open_folder = QPushButton("打开词典目录")
        open_folder.setObjectName("textButton")
        open_folder.clicked.connect(
            lambda: open_path(self.paths.knowledge_dir)
        )
        selection_actions = QHBoxLayout()
        selection_actions.setSpacing(6)
        self._dictionary_selection_actions = selection_actions
        selection_actions.addWidget(self.dictionary_count)
        self.dictionary_select_button = QPushButton("全选搜索结果")
        self.dictionary_select_button.setObjectName("textButton")
        self.dictionary_select_button.clicked.connect(self._select_dictionary_results)
        self.dictionary_clear_button = QPushButton("清空当前分类")
        self.dictionary_clear_button.setObjectName("destructiveTextButton")
        self.dictionary_clear_button.clicked.connect(self._clear_dictionary)
        selection_actions.addWidget(self.dictionary_select_button)
        selection_actions.addWidget(self.dictionary_remove_button)
        self.dictionary_undo_button = QPushButton("撤销删除")
        self.dictionary_undo_button.setObjectName("textButton")
        self.dictionary_undo_button.clicked.connect(self._undo_dictionary_delete)
        self.dictionary_undo_button.hide()
        selection_actions.addWidget(self.dictionary_undo_button)
        selection_actions.addWidget(self.dictionary_clear_button)
        selection_actions.addStretch(1)
        layout.addLayout(selection_actions)
        actions.addWidget(note, 1)
        actions.addWidget(open_folder)
        actions.addWidget(save)
        layout.addLayout(actions)
        return self._scrollable_page(page)

    @staticmethod
    def _scrollable_page(page):
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName("settingsPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _diagnostics_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addLayout(
            self._section_header(
                "诊断",
                "检查 VoiceFlow 是否已经准备好，并给出下一步。",
            )
        )
        header.addStretch(1)
        self.doctor_button = QPushButton("运行检查")
        self.doctor_button.setObjectName("primaryButton")
        self.doctor_button.setAccessibleName("运行 VoiceFlow 诊断")
        self.doctor_button.clicked.connect(self._run_doctor)
        header.addWidget(self.doctor_button)
        layout.addLayout(header)
        self.doctor_summary = QLabel("尚未运行检查")
        self.doctor_summary.setObjectName("diagnosticSummary")
        self.doctor_summary.setWordWrap(True)
        layout.addWidget(self.doctor_summary)
        self.doctor_list = QListWidget()
        self.doctor_list.setObjectName("diagnosticList")
        self.doctor_list.setAccessibleName("诊断结果")
        layout.addWidget(self.doctor_list, 1)
        actions = QHBoxLayout()
        copy_report = QPushButton("复制诊断报告")
        copy_report.clicked.connect(self._copy_diagnostics)
        open_data = QPushButton("打开数据目录")
        open_data.clicked.connect(lambda: open_path(self.paths.data_dir))
        actions.addWidget(copy_report)
        actions.addWidget(open_data)
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _about_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(16)

        about_hero = QWidget()
        about_hero.setObjectName("aboutHero")
        about_layout = QHBoxLayout(about_hero)
        about_layout.setContentsMargins(18, 16, 18, 16)
        about_layout.setSpacing(14)
        about_icon = QLabel()
        icon_path = str(
            self.paths.install_resource(f"assets/{icon_asset_name()}")
        )
        about_icon.setPixmap(
            build_tray_icon(TRAY_ICON_IDLE, icon_path).pixmap(48, 48)
        )
        about_copy = QVBoxLayout()
        about_copy.setSpacing(2)
        about_title = QLabel("VoiceFlow")
        about_title.setObjectName("aboutTitle")
        version = QLabel(f"版本 {display_version()} · {platform_label()}")
        version.setObjectName("aboutVersion")
        about_copy.addWidget(about_title)
        about_copy.addWidget(version)
        about_layout.addWidget(about_icon)
        about_layout.addLayout(about_copy)
        about_layout.addStretch(1)
        layout.addWidget(about_hero)

        privacy_panel = QWidget()
        privacy_panel.setObjectName("privacyPanel")
        privacy_layout = QVBoxLayout(privacy_panel)
        privacy_layout.setContentsMargins(18, 15, 18, 15)
        privacy_layout.setSpacing(5)
        privacy_title = QLabel("离线，是明确的产品边界")
        privacy_title.setObjectName("subsectionTitle")
        privacy = QLabel(
            "录音与识别默认只在本机完成。识别结果先进入剪贴板，"
            "即使自动粘贴没有落到输入框，仍可从剪贴板或本地历史找回。"
        )
        privacy.setObjectName("bodyText")
        privacy.setWordWrap(True)
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(privacy)
        layout.addWidget(privacy_panel)

        data_location = (
            data_location_label(self.paths.data_dir)
            if self.paths.mode is RuntimeMode.FROZEN
            else "项目目录（开发模式）"
        )
        data = QLabel(f"用户数据：{data_location}")
        data.setObjectName("sectionSubtitle")
        data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(data)
        actions = QHBoxLayout()
        open_data = QPushButton("打开数据目录")
        open_data.clicked.connect(lambda: open_path(self.paths.data_dir))
        open_licenses = QPushButton("查看第三方许可")
        open_licenses.clicked.connect(
            lambda: open_path(self.paths.install_resource("THIRD_PARTY_NOTICES.md"))
        )
        actions.addWidget(open_data)
        actions.addWidget(open_licenses)
        actions.addStretch(1)
        layout.addLayout(actions)

        update_row = QHBoxLayout()
        self.check_update_button = QPushButton("检查更新")
        self.check_update_button.clicked.connect(self._check_for_update)
        self.update_status = QLabel("仅在点击后检查；日常运行不会联网。")
        self.update_status.setObjectName("sectionSubtitle")
        self.update_status.setWordWrap(True)
        update_row.addWidget(self.check_update_button)
        update_row.addWidget(self.update_status, 1)
        layout.addLayout(update_row)
        layout.addStretch(1)
        return page

    def _check_for_update(self):
        if getattr(self, "_update_check_in_progress", False):
            return
        self._update_check_in_progress = True
        self.check_update_button.setEnabled(False)
        self.update_status.setText("正在核对稳定 Release 和 SHA-256…")

        def run():
            result = check_latest_release(APP_VERSION)
            self.update_finished.emit(result.as_dict())

        threading.Thread(
            target=run,
            name="voiceflow-update-check",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_update_check(self, result):
        self._update_check_in_progress = False
        self.check_update_button.setEnabled(True)
        state = result.get("state")
        if state == "available":
            url = result.get("installer_url", "")
            self.update_status.setText(
                f"{result.get('message', '发现新版本')} "
                f"<a href=\"{url}\">下载 VoiceFlow {result.get('latest_version', '')}</a>"
            )
            self.update_status.setOpenExternalLinks(True)
        else:
            self.update_status.setText(
                result.get("message", "更新检查未完成")
            )

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

    def _read_dictionary_entries(self):
        entries = {}
        for filename in (
            "builtin-ai.txt",
            "user-dictionary.txt",
            "phrases.txt",
            "corrections.txt",
        ):
            try:
                raw = self._dictionary_path(filename).read_text(encoding="utf-8")
                entries[filename] = [
                    line
                    for line in raw.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
            except FileNotFoundError:
                entries[filename] = []
        return entries

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

    def _dictionary_path(self, filename):
        return self.paths.knowledge_dir / filename

    def _load_dictionary(self):
        self._dictionary_entries = self._read_dictionary_entries()
        self._active_dictionary_filename = self.dictionary_section.currentData()
        self._render_dictionary_section()

    def _store_dictionary_section(self):
        filename = self._active_dictionary_filename
        if not filename or not hasattr(self, "dictionary_list"):
            return
        if filename == "builtin-ai.txt":
            return
        entries = []
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            value = (item.data(Qt.ItemDataRole.UserRole) or item.text()).strip()
            if value and value not in entries:
                entries.append(value)
        if entries != self._dictionary_entries.get(filename, []):
            self._dictionary_dirty = True
        self._dictionary_entries[filename] = entries

    def _render_dictionary_section(self):
        filename = self._active_dictionary_filename
        if not filename or not hasattr(self, "dictionary_list"):
            return
        self.dictionary_list.blockSignals(True)
        self.dictionary_list.clear()
        readonly = filename == "builtin-ai.txt"
        corrections = filename == "corrections.txt"
        self.dictionary_list.setViewMode(QListView.ViewMode.ListMode if corrections else QListView.ViewMode.IconMode)
        for value in self._dictionary_entries.get(filename, []):
            item = QListWidgetItem(value.replace("=", "  →  ", 1) if corrections else value)
            if corrections:
                item.setData(Qt.ItemDataRole.UserRole, value)
            if not readonly:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                if not corrections:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            if not corrections:
                item.setSizeHint(QSize(min(300, max(72, self.dictionary_list.fontMetrics().horizontalAdvance(value) + 46)), 40))
            self.dictionary_list.addItem(item)
        self.dictionary_list.blockSignals(False)
        self.dictionary_input.setEnabled(not readonly)
        self.dictionary_add_button.setEnabled(not readonly)
        self.dictionary_remove_button.setEnabled(not readonly)
        self.dictionary_select_button.setEnabled(not readonly)
        self.dictionary_clear_button.setEnabled(not readonly)
        self.dictionary_correct_input.setVisible(corrections)
        if readonly:
            self.dictionary_input.setPlaceholderText("内置术语不可编辑")
            self.dictionary_hint.setText(
                "内置术语随 VoiceFlow 更新；识别到相同英文时会规范大小写。"
            )
        elif corrections:
            self.dictionary_input.setPlaceholderText("识别成")
            self.dictionary_hint.setText("明确指定应改为哪个词。修改时删除旧项，再添加新项。")
        elif filename == "phrases.txt":
            self.dictionary_input.setPlaceholderText("添加常用短语")
            self.dictionary_hint.setText("添加经常完整说出的短语，双击可以修改。")
        else:
            self.dictionary_input.setPlaceholderText("添加专有词")
            self.dictionary_hint.setText(
                "添加人名、品牌或项目名；英文会规范大小写，误识别请使用确定性纠错。"
            )
        self._update_dictionary_count()
        self._filter_dictionary()

    def _change_dictionary_section(self, _index):
        self._store_dictionary_section()
        self._active_dictionary_filename = self.dictionary_section.currentData()
        self._render_dictionary_section()

    def _valid_dictionary_entry(self, value):
        if self._active_dictionary_filename == "builtin-ai.txt":
            return False
        if self._active_dictionary_filename != "corrections.txt":
            return bool(value)
        if value.count("=") != 1:
            return False
        wrong, correct = (part.strip() for part in value.split("=", 1))
        return bool(wrong and correct)

    def _add_dictionary_entry(self):
        value = self.dictionary_input.text().strip()
        if self._active_dictionary_filename == "corrections.txt" and self.dictionary_correct_input.text().strip():
            value += "=" + self.dictionary_correct_input.text().strip()
        if not self._valid_dictionary_entry(value):
            message = (
                "请使用“错误词=正确词”"
                if self._active_dictionary_filename == "corrections.txt"
                else "请输入内容"
            )
            self._set_status_badge(message, attention=True)
            return
        existing = {
            (self.dictionary_list.item(index).data(Qt.ItemDataRole.UserRole) or self.dictionary_list.item(index).text()).strip()
            for index in range(self.dictionary_list.count())
        }
        if value in existing:
            self._set_status_badge("词典中已有这一项")
            return
        self._store_dictionary_section()
        self._dictionary_entries[self._active_dictionary_filename].append(value)
        self._dictionary_dirty = True
        self._render_dictionary_section()
        self.dictionary_input.clear()
        self.dictionary_correct_input.clear()
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已添加，保存后生效")

    def _remove_dictionary_entries(self):
        if self._active_dictionary_filename == "builtin-ai.txt":
            self._set_status_badge("内置术语不可删除")
            return
        selected = [self.dictionary_list.item(index) for index in range(self.dictionary_list.count())
                    if self.dictionary_list.item(index).checkState() == Qt.CheckState.Checked]
        if not selected:
            selected = self.dictionary_list.selectedItems()
        if not selected:
            self._set_status_badge("请选择要删除的内容")
            return
        self._remember_dictionary_delete()
        for item in selected:
            self.dictionary_list.takeItem(self.dictionary_list.row(item))
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已移除，保存后生效")

    def _dictionary_item_changed(self, item):
        value = (item.data(Qt.ItemDataRole.UserRole) or item.text()).strip()
        if not self._valid_dictionary_entry(value):
            self._set_status_badge("这一项格式不正确", attention=True)
            return
        self.dictionary_list.blockSignals(True)
        if self._active_dictionary_filename != "corrections.txt":
            item.setText(value)
        self.dictionary_list.blockSignals(False)
        self._store_dictionary_section()
        self._update_dictionary_count()

    def _update_dictionary_count(self):
        if hasattr(self, "dictionary_count"):
            selected = sum(self.dictionary_list.item(index).checkState() == Qt.CheckState.Checked for index in range(self.dictionary_list.count()))
            self.dictionary_count.setText(f"{self.dictionary_list.count()} 项 · 已选 {selected} 项")

    def _filter_dictionary(self, *_args):
        query = self.dictionary_search.text().casefold().strip()
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            item.setHidden(query not in item.text().casefold())

    def _select_dictionary_results(self):
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            if not item.isHidden() and self._active_dictionary_filename != "builtin-ai.txt":
                item.setCheckState(Qt.CheckState.Checked)

    def _remember_dictionary_delete(self):
        self._store_dictionary_section()
        self._dictionary_undo = (self._active_dictionary_filename, list(self._dictionary_entries[self._active_dictionary_filename]))
        self.dictionary_undo_button.show()

    def _undo_dictionary_delete(self):
        if self._dictionary_undo:
            filename, entries = self._dictionary_undo
            self._store_dictionary_section()
            current = self._dictionary_entries[filename]
            self._dictionary_entries[filename] = entries + [value for value in current if value not in entries]
            self._dictionary_dirty = True
            self._dictionary_undo = None
            self.dictionary_undo_button.hide()
            if filename == self._active_dictionary_filename:
                self._render_dictionary_section()
            self._set_status_badge("已撤销删除，保存词典后生效")

    def _clear_dictionary(self):
        if self._active_dictionary_filename == "builtin-ai.txt":
            return
        count = self.dictionary_list.count()
        if not count or QMessageBox.question(self, "清空当前分类", f"清空“{self.dictionary_section.currentText()}”的 {count} 项？其他分类不受影响。") != QMessageBox.StandardButton.Yes:
            return
        self._remember_dictionary_delete()
        self.dictionary_list.clear()
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已清空当前分类，可以撤销；保存词典后生效")

    def _save_dictionary(self):
        if self._dictionary_save_in_progress:
            return
        self._store_dictionary_section()
        self._dictionary_generation += 1
        entries = copy.deepcopy(self._dictionary_entries)
        self._dictionary_save_in_progress = True
        self.dictionary_save_button.setEnabled(False)
        self._set_status_badge("正在保存词典")

        def run():
            originals, written = {}, []
            try:
                if any(not self._valid_correction(value) for value in entries.get("corrections.txt", [])):
                    raise ValueError("请检查纠错的两个词")
                for filename, values in entries.items():
                    if filename == "builtin-ai.txt":
                        continue
                    path = self._dictionary_path(filename)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    originals[path] = path.read_bytes() if path.exists() else None
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text("\n".join(values) + ("\n" if values else ""), encoding="utf-8")
                    os.replace(temporary, path)
                    written.append(path)
                result = {"ok": True, "entries": entries}
            except Exception as error:
                for path in reversed(written):
                    try:
                        if originals[path] is None:
                            path.unlink()
                        else:
                            temporary = path.with_suffix(".rollback.tmp")
                            temporary.write_bytes(originals[path])
                            os.replace(temporary, path)
                    except OSError:
                        logger.exception("dictionary rollback failed")
                result = {"ok": False, "error": str(error)}
            self.dictionary_finished.emit(result)

        threading.Thread(target=run, name="voiceflow-dictionary-save", daemon=True).start()

    @Slot(object)
    def _finish_dictionary_save(self, result):
        self._dictionary_generation += 1
        self._dictionary_save_in_progress = False
        self.dictionary_save_button.setEnabled(True)
        if result["ok"]:
            self._dictionary_dirty = self._dictionary_entries != result["entries"]
            self._set_status_badge("词典已保存" if not self._dictionary_dirty else "词典已保存；新的更改尚未保存")
        else:
            self._set_status_badge(f"词典保存失败，草稿已保留：{result['error']}", attention=True)

    @staticmethod
    def _valid_correction(value):
        if value.count("=") != 1:
            return False
        wrong, correct = (part.strip() for part in value.split("=", 1))
        return bool(wrong and correct)

    def _load_config(self):
        try:
            import yaml
            with self.paths.config_file.open("r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except Exception:
            return {}

    def _apply_dictation_preferences(self, snapshot, *, selected_app=None):
        self._dictation_preferences_snapshot = snapshot or {}
        self._preferences_draft = {key: copy.deepcopy(snapshot[key]) for key in ("schema_version", "global", "apps") if key in snapshot}
        current = selected_app if selected_app is not None else self.dictation_scope_combo.currentData()
        self.dictation_scope_combo.blockSignals(True)
        self.dictation_scope_combo.clear()
        self.dictation_scope_combo.addItem("所有应用的默认值", None)
        identities = set(self._dictation_preferences_snapshot.get("apps", {}))
        last_app = self._dictation_preferences_snapshot.get("last_app", "")
        if last_app:
            identities.add(last_app)
        for identity in sorted(identities):
            try:
                identity = normalize_app_id(identity)
            except ValueError:
                continue
            label = f"{identity} · 上次听写应用" if identity == last_app else identity
            self.dictation_scope_combo.addItem(label, identity)
        self.dictation_scope_combo.setCurrentIndex(max(0, self.dictation_scope_combo.findData(current)))
        self.dictation_scope_combo.blockSignals(False)
        available = self.controller is not None and bool(snapshot)
        self._change_dictation_scope()

    def _change_dictation_scope(self, *_args):
        snapshot = self._preferences_draft or self._dictation_preferences_snapshot
        loading = self._loading_settings
        self._loading_settings = True
        app_id = self.dictation_scope_combo.currentData()
        self.follow_default_button.setVisible(bool(app_id))
        self.follow_default_button.setEnabled(
            bool(self.controller and app_id in snapshot.get("apps", {}))
            and not self._dictation_save_in_progress)
        options = snapshot.get("apps", {}).get(app_id)
        if options is None:
            options = dict(snapshot.get("global", {"sentence_end": "preserve", "preserve_format": False}))
            if application_preserves_format(app_id):
                options["preserve_format"] = True
        self.sentence_end_combo.setCurrentIndex(max(0, self.sentence_end_combo.findData(options["sentence_end"])))
        self.preserve_format_check.setChecked(bool(options["preserve_format"]))
        if app_id in {"msedge.exe", "chrome.exe", "firefox.exe", "brave.exe"}:
            note = "此设置适用于这个浏览器的所有网站，不按网页分别记忆。"
        elif app_id:
            note = "仅在这个应用中使用；保存后会记住，其他应用不受影响。"
        else:
            note = "应用设置优先；代码编辑器和终端默认保留格式。"
        if snapshot.get("load_error"):
            note = "上次设置未能读取，暂用保留原样；重新保存可修复。 " + note
        self.dictation_scope_note.setText(note)
        self._update_sentence_end_sample()
        self._loading_settings = loading

    def _settings_values(self):
        return (self.language_combo.currentData(), self.microphone_combo.currentData(), self.autostart_check.isChecked(),
                copy.deepcopy(self._preferences_draft))

    def _settings_dirty(self):
        return self._settings_baseline is not None and self._settings_values() != self._settings_baseline

    def _settings_changed(self, *_args):
        if self._loading_settings or not hasattr(self, "save_settings_button"):
            return
        if self._preferences_draft and self.sender() in (self.sentence_end_combo, self.preserve_format_check):
            options = {"sentence_end": self.sentence_end_combo.currentData(), "preserve_format": self.preserve_format_check.isChecked()}
            identity = self.dictation_scope_combo.currentData()
            if identity:
                self._preferences_draft["apps"][identity] = options
            else:
                self._preferences_draft["global"] = options
        self.save_settings_button.setEnabled(self._settings_dirty() and not self._switch_in_progress)

    def _reload_settings(self):
        if self._settings_dirty() and QMessageBox.question(self, "重新载入设置", "放弃当前未保存的更改，载入最新设置？") != QMessageBox.StandardButton.Yes:
            return
        self._settings_baseline = None
        self.reload_settings_button.hide()
        self.refresh()

    def _draft_follow_default(self):
        identity = self.dictation_scope_combo.currentData()
        self._preferences_draft.get("apps", {}).pop(identity, None)
        self._change_dictation_scope()
        self._settings_changed()

    def _update_sentence_end_sample(self, *_args):
        mode = self.sentence_end_combo.currentData() or "preserve"
        preserve = self.preserve_format_check.isChecked()
        source = "你好。" if mode != "complete_period" else "你好"
        sample = apply_sentence_end(source, mode, preserve_format=preserve)
        self.sentence_end_sample.setText(f"示例：{sample}　/　Hello!　/　真的吗？")
        self.sentence_end_combo.setEnabled(not preserve)

    def _engine_ready(self, engine, config):
        return self.model_manager.status(engine, config).state is ModelState.READY

    def _refresh_settings_controls(self, config, microphones=None):
        engine = config.get("engine", {})
        active = engine.get("active", "sensevoice")
        self._populate_language_options(active, config)

        self.microphone_combo.clear()
        self.microphone_combo.addItem("系统默认麦克风", None)
        self._microphone_detected = False
        for name, index in microphones or ():
            self._microphone_detected = True
            self.microphone_combo.addItem(name, index)
        selected_device = config.get("audio", {}).get("device_index")
        selected_index = self.microphone_combo.findData(selected_device)
        self.microphone_combo.setCurrentIndex(max(0, selected_index))
        self.autostart_check.setChecked(is_autostart_enabled(self.paths))

    def _save_settings(self):
        config = self._load_config()
        engine = config.get("engine", {}).get("active", "sensevoice")
        if self._switch_in_progress:
            return
        self._switch_in_progress = True
        self.save_settings_button.setEnabled(False)
        self._set_status_badge("正在保存设置")
        payload = {
            "engine": engine,
            "language": self.language_combo.currentData(),
            "device_index": self.microphone_combo.currentData(),
            "autostart": self.autostart_check.isChecked(),
            "expected_config": self._config_snapshot,
            "expected_preferences": {key: copy.deepcopy(self._dictation_preferences_snapshot[key]) for key in ("schema_version", "global", "apps")},
            "preferences": copy.deepcopy(self._preferences_draft),
        }

        def run():
            try:
                result = self.controller.save_settings(payload)
                if not result:
                    raise RuntimeError("设置服务不可用")
                payload.update(result)
                payload["ok"] = True
            except Exception as error:
                payload["ok"] = False
                payload["error"] = str(error)
                payload["changed"] = isinstance(error, PreferencesChangedError)
            self.model_switch_finished.emit(payload)

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_model_switch(self, payload):
        self._switch_in_progress = False
        if not payload.get("ok"):
            self.reload_settings_button.setVisible(bool(payload.get("changed")))
            self._set_status_badge("设置已在其他位置更改。当前草稿已保留，请重新载入后保存。" if payload.get("changed") else "设置保存失败。草稿已保留，请重试或检查磁盘空间。", attention=True)
            self._operation_error = payload.get("error", "未知错误")
            self.operation_details_button.show()
            self._settings_changed()
            return
        self._config_snapshot = payload["config_text"]
        self._dictation_preferences_snapshot = copy.deepcopy(payload["preferences"])
        # Keep any edits made while the save worker was running as a new draft.
        self._settings_baseline = (payload["language"], payload["device_index"], payload["autostart"], copy.deepcopy(payload["preferences"]))
        self._settings_changed()
        self._set_status_badge("已保存。设备设置重启后生效。" if payload["restart_required"] else "已保存，下一次听写生效。")

    def _current_language_label(self):
        try:
            import yaml
            with self.paths.config_file.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            engine = config.get("engine", {})
            active = engine.get("active", "sensevoice")
            language = (engine.get(active) or {}).get("language", "auto")
            labels = {"zh": "中文优先", "en": "English 优先", "auto": "自动中英"}
            return labels.get(language, language)
        except Exception:
            return "配置读取失败"

    def _output_status_label(self, status):
        return {
            "landed_confirmed": "已输入",
            "clipboard_verified_paste_dispatched": "已复制，输入未确认",
            "clipboard_verified_only": "已复制",
            "recovery_saved_clipboard_unavailable": "已保存",
            "clipboard_copied_paste_sent": "已复制，输入未确认",
            "clipboard_copied_integrity_warning": "已复制",
            "fallback": "已复制",
            "typed": "输入未确认",
            "error": "失败",
            "unknown": "未知",
        }.get(status, "未知")

    def _format_timestamp(self, value):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.strftime("%m月%d日 %H:%M")
        except Exception:
            return value

    def _refresh_history(self):
        if self._history_refresh_in_progress or self._refresh_in_progress:
            return
        self._history_refresh_in_progress = True
        self._set_status_badge("正在刷新历史")

        def run():
            try:
                payload = {"ok": True, "rows": self._read_history_rows()}
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
            self.history_refresh_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-history-refresh",
            daemon=True,
        ).start()

    def _read_history_rows(self):
        if self._on_read_history:
            return list(self._on_read_history())
        return HistoryStore(self.paths.history_file).read_recent(80)

    @Slot(object)
    def _finish_history_refresh(self, payload):
        self._history_refresh_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge(
                f"历史读取失败：{payload.get('error', '未知错误')}",
                attention=True,
            )
            return
        self._history_rows = payload["rows"]
        self._render_history()
        self._set_status_badge("历史已刷新")

    def _render_history(self):
        if not hasattr(self, "history_list"):
            return
        query = self.search_box.text().strip().lower() if hasattr(self, "search_box") else ""
        self._history_render_generation += 1
        generation = self._history_render_generation
        self.history_list.clear()
        cards = []
        for row in self._history_rows:
            text = row.get("corrected_text") or row.get("clean_text") or row.get("error") or ""
            if query and query not in text.lower():
                continue
            timestamp = self._format_timestamp(row.get("timestamp", ""))
            duration = row.get("duration")
            status = self._output_status_label(row.get("output_status", "unknown"))
            tail = row.get("final_tail", "")
            meta_parts = [part for part in (timestamp, f"{float(duration):.1f}s" if duration is not None else "", status) if part]
            if tail:
                meta_parts.append(f"尾部 {tail}")
            cards.append((text, " · ".join(meta_parts), row.get("_entry_id", "")))
        self._pending_history_cards = cards
        if not cards:
            empty = QListWidgetItem()
            empty.setData(Qt.ItemDataRole.UserRole, "")
            empty.setSizeHint(QSize(0, 180))
            self.history_list.addItem(empty)
            self.history_list.setItemWidget(empty, self._empty_card())
            return
        self._render_history_batch(generation)

    def _render_history_batch(self, generation):
        if generation != self._history_render_generation:
            return
        batch = self._pending_history_cards[:8]
        del self._pending_history_cards[: len(batch)]
        for text, meta, entry_id in batch:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, text)
            item.setSizeHint(QSize(0, 104))
            self.history_list.addItem(item)
            self.history_list.setItemWidget(
                item,
                self._history_card(text, meta, entry_id),
            )
        QTimer.singleShot(0, self._resize_history_cards)
        if self._pending_history_cards:
            QTimer.singleShot(
                0,
                lambda active=generation: self._render_history_batch(active),
            )

    def _history_card(self, text, meta, entry_id=""):
        card = QWidget()
        card.setObjectName("historyCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(12)

        text_group = QVBoxLayout()
        text_group.setSpacing(4)
        display_text = text if len(text) <= 180 else f"{text[:180]}…"
        body = QLabel(display_text)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setObjectName("historyText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setToolTip(text)
        info = QLabel(meta)
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setObjectName("historyMeta")
        text_group.addWidget(body)
        text_group.addWidget(info)
        record = next((record for record in self._history_rows if record.get("_entry_id") == entry_id), {})
        if len(text) > 180 or record.get("raw_text") or record.get("output_status"):
            details = QPushButton("查看详情")
            details.setObjectName("inlineCopyButton")
            detail_text = QLabel()
            detail_text.setTextFormat(Qt.TextFormat.PlainText)
            detail_text.setWordWrap(True)
            detail_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_text.setText("终稿：\n" + text + ("\n\n原始识别：\n" + record["raw_text"] if record.get("raw_text") else "")
                                + "\n\n交付：" + self._output_status_label(record.get("output_status", "unknown")))
            detail_text.hide()
            def toggle_details():
                detail_text.setVisible(detail_text.isHidden())
                details.setText("收起详情" if detail_text.isVisible() else "查看详情")
                QTimer.singleShot(0, self._resize_history_cards)
            details.clicked.connect(toggle_details)
            text_group.addWidget(details)
            text_group.addWidget(detail_text)
        row.addLayout(text_group, 1)

        copy = QPushButton("复制")
        copy.setObjectName("inlineCopyButton")
        copy.clicked.connect(lambda _=False, value=text: self._copy_text(value))
        row.addWidget(copy)
        delete = QPushButton("删除")
        delete.setObjectName("inlineDeleteButton")
        delete.setEnabled(bool(entry_id))
        delete.clicked.connect(
            lambda _=False, value=entry_id: self._delete_history_entry(value)
        )
        row.addWidget(delete)
        return card

    def _resize_history_cards(self):
        for index in range(self.history_list.count()):
            item = self.history_list.item(index)
            widget = self.history_list.itemWidget(item)
            if widget:
                width = max(1, self.history_list.viewport().width())
                # Item margins and frame can make the card narrower than the viewport; size for the narrower one.
                if 0 < widget.width() < width:
                    width = widget.width()
                layout = widget.layout()
                height = max(widget.minimumSizeHint().height(), layout.heightForWidth(width))
                item.setSizeHint(QSize(width, height))

    def _delete_history_entry(self, entry_id):
        if not entry_id or not self._on_delete_history:
            self._set_status_badge("暂时无法删除", attention=True)
            return
        self._run_history_mutation("delete", entry_id)

    def _clear_history(self):
        if not self._history_rows:
            self._set_status_badge("没有历史记录")
            return
        if not self._on_clear_history:
            self._set_status_badge("暂时无法清空", attention=True)
            return
        answer = QMessageBox.question(
            self,
            "清空全部历史",
            "将永久删除全部本地听写历史（包括未显示的记录）和待交付文字，保留可恢复录音。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._clear_history_undo()
        self._run_history_mutation("clear")

    def _clear_local_data(self):
        if not self._on_clear_local_data or self._history_action_in_progress:
            self._set_status_badge("暂时无法清除本机数据", attention=True)
            return
        answer = QMessageBox.question(
            self,
            "清除本机听写数据",
            "将永久删除本地历史、待交付文字和未交付录音，保留配置、词典和模型。"
            "Windows 剪贴板及其历史、同步记录需自行清理。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._clear_history_undo()
        self._run_history_mutation("clear_local")

    def _undo_history_delete(self):
        token = self._history_undo_token
        if token is None or not self._on_restore_history:
            return
        self._history_undo_token = None
        self.undo_history_button.setVisible(False)
        self._run_history_mutation("restore", token=token)

    def _clear_history_undo(self):
        self._history_undo_generation += 1
        self._history_undo_token = None
        if hasattr(self, "undo_history_button"):
            self.undo_history_button.setVisible(False)

    def _run_history_mutation(self, action, entry_id="", token=None):
        if self._history_action_in_progress:
            return
        self._history_action_in_progress = True
        self._set_status_badge("正在删除历史")

        def run():
            try:
                undo_token = None
                if action == "clear":
                    changed = int(self._on_clear_history())
                elif action == "clear_local":
                    result = self._on_clear_local_data()
                    changed = int(
                        result.get("history_entries", 0)
                        + result.get("recovery_sessions", 0)
                        + result.get("pending_deliveries", 0)
                    )
                elif action == "restore":
                    changed = int(bool(self._on_restore_history(token)))
                else:
                    undo_token = self._on_delete_history(entry_id)
                    changed = int(bool(undo_token))
                payload = {
                    "ok": True,
                    "action": action,
                    "changed": changed,
                    "undo_token": undo_token,
                }
            except Exception as error:
                payload = {"ok": False, "action": action, "error": str(error)}
            self.history_mutation_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-history-delete",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_history_mutation(self, payload):
        self._history_action_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge(
                f"历史删除失败：{payload.get('error', '未知错误')}",
                attention=True,
            )
            return
        action = payload.get("action")
        if action == "delete" and payload.get("undo_token"):
            self._history_undo_token = payload["undo_token"]
            self._history_undo_generation += 1
            generation = self._history_undo_generation
            self.undo_history_button.setVisible(True)
            QTimer.singleShot(
                5000,
                lambda active=generation: (
                    self._clear_history_undo()
                    if active == self._history_undo_generation
                    else None
                ),
            )
            self._set_status_badge("历史已删除，可撤销")
        elif action == "restore":
            self._set_status_badge("已恢复")
        elif action == "clear_local":
            self._set_status_badge("本机听写数据已清除")
        else:
            self._set_status_badge("历史已清空")
        self._refresh_history()

    def _empty_card(self):
        card = QWidget()
        card.setObjectName("emptyCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 40, 14, 40)
        layout.setSpacing(6)
        title = QLabel("暂无转录")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note = QLabel(f"按 {trigger_summary()} 说一句话，结果会出现在这里")
        note.setObjectName("historyMeta")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
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
            self._set_status_badge("无可复制")
            return
        if not self._on_copy_text:
            self._set_status_badge("复制失败", attention=True)
            return
        self._run_history_action(text, self._on_copy_text, "正在复制")

    def _repaste_selected(self):
        text = self._selected_text()
        self._repaste_text(text)

    def _repaste_text(self, text):
        self._copy_text(text)

    def _run_history_action(self, text, callback, pending_label):
        if self._history_action_in_progress:
            self._set_status_badge("上一项操作仍在进行")
            return
        self._history_action_in_progress = True
        self._set_status_badge(pending_label)

        def run():
            try:
                payload = {"ok": True, "status": callback(text)}
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
            self.history_action_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-history-action",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_history_action(self, payload):
        self._history_action_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge("操作失败", attention=True)
            return
        status = payload.get("status", "unknown")
        label = self._output_status_label(status)
        self._set_status_badge(label, attention=label in {"失败", "未知"})

    def _refresh_recovery(self):
        self._apply_recovery_sessions(self.recovery_store.list_recoverable())

    def _apply_recovery_sessions(self, sessions):
        self.recovery_combo.clear()
        for session in sessions:
            minutes = session.sample_count / max(1, session.sample_rate) / 60
            created = datetime.fromtimestamp(session.created_at).strftime("%m月%d日 %H:%M")
            self.recovery_combo.addItem(
                f"{created} · {minutes:.1f} 分钟" if session.can_recover else f"{created} · 信息损坏",
                session.session_id,
            )
            index = self.recovery_combo.count() - 1
            self.recovery_combo.setItemData(
                index,
                session.preview_text,
                int(Qt.ItemDataRole.UserRole) + 1,
            )
            self.recovery_combo.setItemData(index, session, int(Qt.ItemDataRole.UserRole) + 2)
        self.recovery_summary.setText(f"有 {len(sessions)} 段尚未交付的录音")
        self.recovery_panel.setVisible(bool(sessions))
        self._update_recovery_selection()

    def _update_recovery_selection(self, *_args):
        session = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 2)
        available = session is not None and session.can_recover
        self.recover_button.setEnabled(available and not self._recovery_action_in_progress)
        if session is not None and not session.can_recover:
            detail = "录音信息损坏，原文件已保留。无法可靠识别，不再需要时可手动删除。"
        elif session is not None and session.partial:
            detail = "这段录音可能只保存了部分内容，末尾可能缺失。恢复后仍保留原录音，不再需要时可手动删除。"
        else:
            detail = "尚未交付的录音不会自动删除。恢复并复制成功后删除；不再需要时可手动删除。"
        self.recovery_detail.setText(detail)

    def _recover_selected_session(self):
        session_id = self.recovery_combo.currentData()
        session = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 2)
        if (
            not session_id
            or session is None or not session.can_recover
            or not self._on_recover_session
            or self._recovery_action_in_progress
        ):
            return
        self._recovery_action_in_progress = True
        self.recover_button.setEnabled(False)
        self.delete_recovery_button.setEnabled(False)
        self._set_status_badge("正在从本地录音恢复文字")

        def run():
            try:
                result = self._on_recover_session(str(session_id))
            except Exception as error:
                result = {"ok": False, "error": str(error)}
            result = dict(result or {})
            result["action"] = "recover"
            self.recovery_finished.emit(result)

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_recovery(self, result):
        self._recovery_action_in_progress = False
        self.recover_button.setEnabled(True)
        self.delete_recovery_button.setEnabled(True)
        self._update_recovery_selection()
        if result.get("action") == "delete":
            if result.get("ok"):
                self._set_status_badge("恢复录音已删除")
                self.refresh()
            else:
                self._set_status_badge("没有找到这段恢复录音")
            return
        if result.get("ok"):
            message = ("已恢复保存的部分，文字已复制。原录音仍保留" if result.get("partial") else
                       "文字已复制到剪贴板，原录音仍保留" if result.get("recording_retained") else
                       "恢复完成，文字已复制到剪贴板")
            self._set_status_badge(message)
            self._refresh_history()
            self._refresh_recovery()
        else:
            self._set_status_badge(f"恢复未完成：{result.get('error', '录音仍已保留')}")

    def _copy_recovery_preview(self):
        preview = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 1) or ""
        if not preview:
            self._set_status_badge("这段录音还没有可复制的预览文字")
            return
        self._copy_text(preview)

    def _delete_recovery(self):
        session_id = self.recovery_combo.currentData()
        if (
            not session_id
            or not self._on_delete_recovery
            or self._recovery_action_in_progress
        ):
            return
        answer = QMessageBox.question(
            self,
            "删除恢复录音",
            "这段本地恢复录音将被永久删除。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._recovery_action_in_progress = True
        self.recover_button.setEnabled(False)
        self.delete_recovery_button.setEnabled(False)
        self._set_status_badge("正在删除恢复录音")

        def run():
            try:
                ok = bool(self._on_delete_recovery(str(session_id)))
                result = {"ok": ok, "action": "delete"}
            except Exception as error:
                result = {"ok": False, "action": "delete", "error": str(error)}
            self.recovery_finished.emit(result)

        threading.Thread(
            target=run,
            name="voiceflow-recovery-delete",
            daemon=True,
        ).start()

    def _copy_all_visible(self):
        texts = []
        for i in range(self.history_list.count()):
            text = self.history_list.item(i).data(Qt.ItemDataRole.UserRole)
            if text:
                texts.append(text)
        if not texts:
            self._set_status_badge("无可复制")
            return
        self._copy_text("\n\n".join(texts))

    def _populate_language_options(self, engine, config):
        configured = (
            config.get("engine", {}).get(engine, {}).get("language")
            or "auto"
        )
        options = (
            (("自动检测", "auto"),)
            if engine == "qwen3-asr"
            else (
                ("自动中英（推荐）", "auto"),
                ("中文优先", "zh"),
                ("English 优先", "en"),
                ("粤语", "yue"),
            )
        )
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for label, value in options:
            self.language_combo.addItem(label, value)
        self.language_combo.setCurrentIndex(
            max(0, self.language_combo.findData(configured))
        )
        self.language_combo.blockSignals(False)

    def _run_doctor(self):
        if self._doctor_in_progress:
            return
        self._doctor_in_progress = True
        self.doctor_summary.setText("正在检查 VoiceFlow…")
        self.doctor_list.clear()
        self.doctor_button.setEnabled(False)
        self.diagnostics_action.setEnabled(False)

        def run():
            try:
                result = run_runtime_diagnostics(self.paths)
                self.doctor_finished.emit(result)
            except Exception as error:
                self.doctor_finished.emit(
                    {
                        "ok": False,
                        "checks": [
                            {
                                "name": "diagnostics",
                                "status": "missing",
                                "detail": str(error),
                            }
                        ],
                    }
                )

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_doctor(self, result):
        self._doctor_in_progress = False
        self._last_diagnostics = result
        self.doctor_list.clear()
        labels = {
            "runtime_mode": "运行方式",
            "config": "配置",
            "config_parse": "配置格式",
            "data_directory": "数据目录",
            "logs_directory": "历史与日志",
            "knowledge_base": "词典",
            "active_model": "离线模型",
            "vad_model": "语音检测",
            "diagnostics": "诊断服务",
        }
        for check in result.get("checks", []):
            ok = check.get("status") == "ok"
            state = "正常" if ok else "需要处理"
            key = check.get("name")
            name = labels.get(key, key or "检查项")
            detail = check.get("detail", "")
            if key == "runtime_mode":
                detail = "已安装版本" if detail == "frozen" else "开发模式"
            elif key == "active_model" and detail == "sensevoice":
                detail = "SenseVoice 已验证"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, check)
            item.setSizeHint(QSize(0, 62))
            self.doctor_list.addItem(item)
            self.doctor_list.setItemWidget(
                item,
                self._diagnostic_card(state, name, detail, ok),
            )
        ok = bool(result.get("ok"))
        self.doctor_summary.setText(
            "一切正常，VoiceFlow 可以离线使用。"
            if ok
            else "发现需要处理的项目。请根据列表修复后再次检查。"
        )
        self.doctor_button.setEnabled(True)
        self.diagnostics_action.setEnabled(True)
        self._set_status_badge(
            "检查完成" if ok else "需要处理",
            attention=not ok,
        )

    def _diagnostic_card(self, state, name, detail, ok):
        card = QWidget()
        card.setObjectName("diagnosticCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(12)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel(name)
        title.setObjectName("diagnosticName")
        description = QLabel(detail)
        description.setObjectName("diagnosticDetail")
        description.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(description)
        layout.addLayout(copy, 1)

        badge = QLabel(state)
        badge.setObjectName(
            "diagnosticOk" if ok else "diagnosticAttention"
        )
        layout.addWidget(badge)
        return card

    def _copy_diagnostics(self):
        if not self._last_diagnostics:
            self._set_status_badge("请先运行检查")
            return
        self._copy_text(format_diagnostics(self._last_diagnostics))

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

    @staticmethod
    def _combo_arrow_path():
        """A small chevron for combo boxes, drawn once per process (QSS needs an image file)."""
        directory = Path(tempfile.gettempdir()) / "voiceflow-ui"
        path = directory / "chevron-down@2x.png"
        if not path.exists():
            directory.mkdir(parents=True, exist_ok=True)
            image = QPixmap(24, 24)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#6e6e73"), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QPointF(7, 10), QPointF(12, 15), QPointF(17, 10)])
            painter.end()
            image.save(str(path))
        return path.as_posix()

    def _style(self):
        # Quiet, native-feeling settings: light sidebar, grouped white cards on a soft grey canvas,
        # one dark primary button per page, text buttons for secondary actions.
        return """
        * {
            font-size: 13px;
        }
        QWidget#appShell {
            background: #f5f5f7;
            color: #1d1d1f;
        }
        QWidget#sidebarPanel {
            background: #ececef;
            border: none;
            border-right: 1px solid #dcdce1;
            border-radius: 0px;
        }
        QLabel#brandIcon {
            min-width: 32px;
            min-height: 32px;
        }
        QLabel#appTitle {
            font-size: 16px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#appSubtitle, QLabel#sidebarVersion {
            font-size: 11px;
            color: #6e6e73;
        }
        QListWidget#sidebar {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#sidebar::item {
            min-height: 36px;
            padding-left: 10px;
            border-radius: 8px;
            color: #1d1d1f;
        }
        QListWidget#sidebar::item:hover {
            background: rgba(0, 0, 0, 0.04);
        }
        QListWidget#sidebar::item:selected {
            background: rgba(0, 0, 0, 0.08);
            color: #1d1d1f;
            border: none;
            font-weight: 600;
        }
        QLabel#statusBadge {
            padding: 8px 10px;
            background: #ffffff;
            color: #1f7a3a;
            border: 1px solid #e0e0e5;
            border-radius: 8px;
            font-weight: 600;
        }
        QLabel#statusBadge[attention="true"] {
            color: #9a5b00;
            background: #fff8eb;
            border-color: #f2dfb8;
        }
        QWidget#sidebarPanel QPushButton {
            color: #3a3a3c;
            background: transparent;
            border: none;
            text-align: left;
            padding: 6px 10px;
            min-height: 30px;
        }
        QWidget#sidebarPanel QPushButton:hover {
            background: rgba(0, 0, 0, 0.05);
        }
        QPushButton::menu-indicator {
            subcontrol-position: right center;
            right: 8px;
        }
        QStackedWidget#contentStack {
            background: #f5f5f7;
            border: none;
            border-radius: 0px;
        }
        QScrollArea#settingsPageScroll, QScrollArea#dictationScroll {
            background: #f5f5f7;
            border: none;
        }
        QWidget#contentPage {
            background: transparent;
            border: none;
        }
        QLabel#sectionTitle, QLabel#commandTitle {
            font-size: 26px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#sectionSubtitle, QLabel#commandSubtitle, QLabel#bodyText {
            color: #6e6e73;
            font-size: 13px;
        }
        QLabel#commandSubtitle {
            font-size: 14px;
        }
        QLabel#groupCaption {
            color: #6e6e73;
            font-size: 12px;
            font-weight: 600;
            padding-left: 4px;
        }
        QWidget#groupCard, QWidget#recoveryPanel, QWidget#aboutHero, QWidget#privacyPanel {
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 12px;
        }
        QLabel#fieldName {
            color: #1d1d1f;
        }
        QLabel#rowNote, QLabel#saveNote {
            color: #6e6e73;
            font-size: 12px;
            padding: 2px 0px 6px 0px;
        }
        QCheckBox {
            spacing: 10px;
            color: #1d1d1f;
        }
        QWidget#groupCard QCheckBox {
            border-top: 1px solid #ececf0;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        QLabel#shortcutKey {
            color: #3a3a3c;
            background: #ffffff;
            border: 1px solid #d8d8dd;
            border-bottom: 2px solid #c7c7cc;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#systemStatusItem {
            color: #3a3a3c;
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 12px;
            padding: 5px 11px;
            font-size: 12px;
            font-weight: 550;
        }
        QWidget#saveBar {
            background: #fbfbfc;
            border-top: 1px solid #e3e3e8;
        }
        QLabel#recoveryTitle {
            color: #8a5600;
            font-size: 14px;
            font-weight: 650;
        }
        QLabel#subsectionTitle, QLabel#aboutVersion {
            color: #1d1d1f;
            font-size: 14px;
            font-weight: 600;
        }
        QLabel#aboutVersion {
            color: #6e6e73;
            font-weight: 500;
        }
        QLabel#aboutTitle {
            color: #1d1d1f;
            font-size: 22px;
            font-weight: 650;
        }
        QLabel#diagnosticSummary {
            color: #3a3a3c;
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 12px;
            padding: 13px;
        }
        QLabel#diagnosticName {
            color: #1d1d1f;
            font-weight: 600;
        }
        QLabel#diagnosticDetail {
            color: #6e6e73;
            font-size: 12px;
        }
        QLabel#diagnosticOk, QLabel#diagnosticAttention {
            padding: 3px 8px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#diagnosticOk {
            color: #1f7a3a;
            background: #eaf7ee;
        }
        QLabel#diagnosticAttention {
            color: #9a5b00;
            background: #fff4df;
        }
        QLabel#privacyNote {
            color: #515154;
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 11px;
            padding: 11px 13px;
        }
        QLabel#operationFeedback {
            color: #285b3a;
            background: #f0f8f2;
            border-top: 1px solid #dcebe1;
        }
        QLabel#operationFeedback[attention="true"] {
            color: #874914;
            background: #fff6ec;
            border-top-color: #f2e0c8;
        }
        QLabel#fieldValue {
            color: #1d1d1f;
            font-weight: 500;
        }
        QLineEdit, QComboBox {
            border: 1px solid #d8d8dd;
            border-radius: 8px;
            background: #ffffff;
            padding: 6px 10px;
            min-height: 20px;
            selection-background-color: #0a64d6;
            selection-color: #ffffff;
        }
        QComboBox {
            padding-right: 30px;
        }
        QComboBox:hover, QLineEdit:hover {
            border-color: #c2c2c8;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 26px;
            border: none;
        }
        QComboBox::down-arrow {
            image: url("__CHEVRON__");
            width: 12px;
            height: 12px;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #d8d8dd;
            border-radius: 8px;
            background: #ffffff;
            padding: 4px;
            selection-background-color: #e8f0fd;
            selection-color: #1d1d1f;
            outline: none;
        }
        QListWidget#historyList, QListWidget#diagnosticList, QListWidget#dictionaryList {
            border: 1px solid #e5e5ea;
            border-radius: 12px;
            background: #ffffff;
            padding: 4px;
            outline: none;
        }
        QListWidget#dictionaryList {
            border: none;
            padding: 0px;
        }
        QListWidget#historyList::item, QListWidget#diagnosticList::item {
            padding: 0px;
            margin: 0px;
            border: none;
            border-bottom: 1px solid #f0f0f3;
            background: transparent;
        }
        QListWidget#dictionaryList::item {
            padding: 0px 10px;
            margin: 3px;
            border: 1px solid #e5e5ea;
            border-radius: 15px;
            background: #f7f7f9;
        }
        QListWidget#historyList::item:selected, QListWidget#diagnosticList::item:selected {
            color: #1d1d1f;
            background: #f2f6fd;
            border-radius: 8px;
        }
        QListWidget#dictionaryList::item:selected {
            color: #1d1d1f;
            background: #e8f0fd;
            border-color: #b9cff3;
        }
        QWidget#historyCard, QWidget#emptyCard, QWidget#diagnosticCard {
            background: transparent;
        }
        QLabel#historyText {
            color: #1d1d1f;
            font-size: 14px;
            font-weight: 500;
        }
        QLabel#emptyTitle {
            color: #1d1d1f;
            font-size: 15px;
            font-weight: 600;
        }
        QLabel#historyMeta {
            color: #6e6e73;
            font-size: 12px;
        }
        QPushButton {
            min-height: 30px;
            padding: 4px 14px;
            border-radius: 8px;
            border: 1px solid #d8d8dd;
            background: #ffffff;
            color: #1d1d1f;
            font-weight: 500;
        }
        QPushButton:hover {
            background: #f5f5f7;
        }
        QPushButton:pressed {
            background: #ececef;
        }
        QPushButton:disabled {
            color: #aeaeb2;
            border-color: #e5e5ea;
        }
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus {
            border: 2px solid #0a64d6;
        }
        QPushButton#primaryButton {
            background: #1d1d1f;
            color: white;
            border: 1px solid #1d1d1f;
            font-weight: 600;
            padding: 4px 18px;
        }
        QPushButton#primaryButton:hover {
            background: #3a3a3c;
            border-color: #3a3a3c;
        }
        QPushButton#primaryButton:disabled {
            background: #d1d1d6;
            border-color: #d1d1d6;
            color: #ffffff;
        }
        QPushButton#textButton, QPushButton#destructiveTextButton {
            border: none;
            background: transparent;
            color: #0060c7;
            padding: 4px 8px;
            min-height: 28px;
        }
        QPushButton#destructiveTextButton {
            color: #c4271f;
        }
        QPushButton#textButton:hover, QPushButton#destructiveTextButton:hover {
            background: rgba(0, 0, 0, 0.04);
        }
        QPushButton#textButton:disabled, QPushButton#destructiveTextButton:disabled {
            color: #aeaeb2;
        }
        QPushButton#inlineCopyButton, QPushButton#inlineRepasteButton, QPushButton#inlineDeleteButton {
            min-width: 52px;
            min-height: 26px;
            padding: 2px 10px;
            font-size: 12px;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 0, 0, 0.18);
            border-radius: 3px;
            min-height: 32px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            height: 0px;
            background: transparent;
        }
        """.replace("__CHEVRON__", self._combo_arrow_path())


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
