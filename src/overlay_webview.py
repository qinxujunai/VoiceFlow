"""
VoiceFlow 悬浮窗。Qt 主线程 + 信号桥接，所有跨线程 UI 操作线程安全。
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from pathlib import Path

from qt_compat import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSystemTrayIcon, QMenu, QLabel, QPushButton,
    QPlainTextEdit, QGridLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QLineEdit, QStackedWidget,
    QCheckBox, QComboBox, QMessageBox,
    QWebChannel, QWebEngineView, Qt, QUrl, QSize, QObject, Signal, Slot, QTimer,
    QAction, QLocalServer, QLocalSocket,
)

from tray_icon import (
    TRAY_ICON_ERROR,
    TRAY_ICON_IDLE,
    TRAY_ICON_PROCESSING,
    TRAY_ICON_RECORDING,
    build_tray_icon,
)
from ui_state import UiState, display_for_state
from settings_store import (
    is_autostart_enabled,
    onboarding_completed,
    set_autostart,
    set_onboarding_completed,
    update_runtime_settings,
)
from runtime_paths import AppPaths, RuntimeMode
from version import display_version
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
)
from recovery_session import RecoverySessionStore
from delivery import VerifiedClipboard


SINGLE_INSTANCE_NAME = "VoiceFlow.LocalFirstDictation"


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

    def __init__(
        self,
        on_copy_text=None,
        on_repaste_text=None,
        on_recover_session=None,
        on_delete_recovery=None,
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
        self.recovery_store = RecoverySessionStore(self.paths.recovery_dir)
        self._history_rows = []
        self._dictionary_entries = {}
        self._active_dictionary_filename = None
        self._last_diagnostics = None
        self._microphone_detected = False
        self._switch_in_progress = False
        self.setWindowTitle("VoiceFlow")
        self.setMinimumSize(940, 640)

        shell = QWidget()
        shell.setObjectName("appShell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setSpacing(14)

        sidebar_panel = QWidget()
        sidebar_panel.setObjectName("sidebarPanel")
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(14, 16, 14, 14)
        sidebar_layout.setSpacing(12)

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
        title.setObjectName("appTitle")
        subtitle = QLabel("离线语音输入")
        subtitle.setObjectName("appSubtitle")
        brand_copy.addWidget(title)
        brand_copy.addWidget(subtitle)
        brand.addWidget(brand_icon)
        brand.addLayout(brand_copy)
        brand.addStretch(1)
        sidebar_layout.addLayout(brand)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        for label in ("状态", "听写", "词典", "历史"):
            self.sidebar.addItem(QListWidgetItem(label))
        self.sidebar.setCurrentRow(0)
        self.sidebar.setAccessibleName("设置导航")
        sidebar_layout.addWidget(self.sidebar, 1)

        self.status_badge = QLabel("准备中")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAccessibleName("VoiceFlow 状态")
        sidebar_layout.addWidget(self.status_badge)
        help_menu = QMenu(self)
        diagnostics_action = help_menu.addAction("运行诊断")
        diagnostics_action.triggered.connect(lambda: self._show_aux_page(4))
        about_action = help_menu.addAction("帮助与关于")
        about_action.triggered.connect(lambda: self._show_aux_page(5))
        self.help_button = QPushButton("帮助与关于")
        self.help_button.setMenu(help_menu)
        self.help_button.setAccessibleName("帮助、诊断与关于")
        sidebar_layout.addWidget(self.help_button)
        build_label = QLabel(f"{display_version()}\n{platform_label()}")
        build_label.setObjectName("sidebarVersion")
        build_label.setToolTip(f"{display_version()} · {platform_label()}")
        sidebar_layout.addWidget(build_label)
        sidebar_panel.setFixedWidth(196)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.stack.addWidget(self._home_page())
        self.stack.addWidget(self._recent_page())
        self.stack.addWidget(self._status_page())
        self.stack.addWidget(self._dictionary_page())
        self.stack.addWidget(self._diagnostics_page())
        self.stack.addWidget(self._about_page())
        self.sidebar.currentRowChanged.connect(self._show_primary_page)

        body.addWidget(sidebar_panel)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(shell)
        if not self._high_contrast_enabled():
            self.setStyleSheet(self._style())
        self.doctor_finished.connect(self._finish_doctor)
        self.model_switch_finished.connect(self._finish_model_switch)
        self.recovery_finished.connect(self._finish_recovery)

    def _show_primary_page(self, row):
        page_by_row = {0: 0, 1: 2, 2: 3, 3: 1}
        if row in page_by_row:
            self.stack.setCurrentIndex(page_by_row[row])

    def _show_aux_page(self, index):
        self.sidebar.clearSelection()
        self.stack.setCurrentIndex(index)
        if index == 4:
            self._run_doctor()

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

    def _home_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(16)

        hero = QWidget()
        hero.setObjectName("heroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(8)
        self.home_ready_title = QLabel("按下，说话，文字就位。")
        self.home_ready_title.setObjectName("heroTitle")
        self.home_ready_subtitle = QLabel(
            "不切换窗口，不上传录音。识别结果会留在剪贴板和本地历史中。"
        )
        self.home_ready_subtitle.setObjectName("heroSubtitle")
        self.home_ready_subtitle.setWordWrap(True)
        hero_layout.addWidget(self.home_ready_title)
        hero_layout.addWidget(self.home_ready_subtitle)

        hero_actions = QHBoxLayout()
        self.trial_button = QPushButton("试说一次")
        self.trial_button.setObjectName("primaryButton")
        self.trial_button.setAccessibleName("开始一次试说")
        self.trial_button.clicked.connect(self._start_trial)
        hero_actions.addWidget(self.trial_button)
        hero_actions.addStretch(1)
        hero_layout.addLayout(hero_actions)
        layout.addWidget(hero)

        readiness_title = QLabel("准备状态")
        readiness_title.setObjectName("subsectionTitle")
        layout.addWidget(readiness_title)
        readiness = QWidget()
        readiness.setObjectName("readinessPanel")
        readiness_layout = QHBoxLayout(readiness)
        readiness_layout.setContentsMargins(12, 12, 12, 12)
        readiness_layout.setSpacing(10)
        values = []
        for title in ("麦克风", "本地处理", "快捷键"):
            item = QWidget()
            item.setObjectName("readinessItem")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(12, 9, 12, 9)
            item_layout.setSpacing(3)
            name = QLabel(title)
            name.setObjectName("readinessName")
            value = QLabel("正在检查")
            value.setObjectName("readinessValue")
            value.setAccessibleName(f"{title}状态")
            item_layout.addWidget(name)
            item_layout.addWidget(value)
            readiness_layout.addWidget(item, 1)
            values.append(value)
        self.home_microphone, self.home_model, self.home_hotkeys = values
        readiness.setFixedHeight(86)
        layout.addWidget(readiness)

        practice_label = QLabel("试说")
        practice_label.setObjectName("subsectionTitle")
        practice_note = QLabel(f"把光标放在下方。{trigger_instruction()}")
        practice_note.setObjectName("sectionSubtitle")
        self.practice_box = QPlainTextEdit()
        self.practice_box.setObjectName("practiceBox")
        self.practice_box.setAccessibleName("VoiceFlow 试说输入框")
        self.practice_box.setPlaceholderText("识别结果会像普通输入一样出现在这里")
        self.practice_box.setFixedHeight(82)
        layout.addWidget(practice_label)
        layout.addWidget(practice_note)
        layout.addWidget(self.practice_box)

        recent_header = QHBoxLayout()
        recent_title = QLabel("最近听写")
        recent_title.setObjectName("subsectionTitle")
        view_all = QPushButton("查看全部")
        view_all.setObjectName("textButton")
        view_all.clicked.connect(lambda: self.sidebar.setCurrentRow(3))
        recent_header.addWidget(recent_title)
        recent_header.addStretch(1)
        recent_header.addWidget(view_all)
        layout.addLayout(recent_header)
        self.home_recent_labels = []
        label = QLabel()
        label.setObjectName("recentLine")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.home_recent_labels.append(label)
        layout.addWidget(label)
        return page

    def _recent_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        layout.addLayout(self._section_header("历史", "查看、复制或再次粘贴最近结果"))

        self.recovery_panel = QWidget()
        self.recovery_panel.setObjectName("recoveryPanel")
        recovery_layout = QVBoxLayout(self.recovery_panel)
        recovery_layout.setContentsMargins(14, 12, 14, 12)
        recovery_layout.setSpacing(8)
        self.recovery_summary = QLabel("")
        self.recovery_summary.setObjectName("recoveryTitle")
        self.recovery_detail = QLabel("录音只保留 24 小时。恢复成功并写入历史后会立即删除。")
        self.recovery_detail.setObjectName("sectionSubtitle")
        self.recovery_detail.setWordWrap(True)
        self.recovery_combo = QComboBox()
        self.recovery_combo.setAccessibleName("可恢复录音")
        recovery_actions = QHBoxLayout()
        self.recover_button = QPushButton("重新识别并复制")
        self.recover_button.setObjectName("primaryButton")
        self.recover_button.clicked.connect(self._recover_selected_session)
        copy_preview = QPushButton("复制已有预览")
        copy_preview.clicked.connect(self._copy_recovery_preview)
        delete_recovery = QPushButton("删除录音")
        delete_recovery.clicked.connect(self._delete_recovery)
        recovery_actions.addWidget(self.recover_button)
        recovery_actions.addWidget(copy_preview)
        recovery_actions.addWidget(delete_recovery)
        recovery_actions.addStretch(1)
        recovery_layout.addWidget(self.recovery_summary)
        recovery_layout.addWidget(self.recovery_detail)
        recovery_layout.addWidget(self.recovery_combo)
        recovery_layout.addLayout(recovery_actions)
        layout.addWidget(self.recovery_panel)

        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索最近转录")
        self.search_box.setAccessibleName("搜索历史转录")
        self.search_box.textChanged.connect(self._render_history)
        toolbar.addWidget(self.search_box, 1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self._refresh_history)
        toolbar.addWidget(refresh)
        copy_all = QPushButton("复制全部")
        copy_all.clicked.connect(self._copy_all_visible)
        toolbar.addWidget(copy_all)
        layout.addLayout(toolbar)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.setAccessibleName("历史转录列表")
        self.history_list.itemDoubleClicked.connect(lambda item: self._copy_text(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.history_list, 1)

        return page

    def _status_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(16)
        layout.addLayout(
            self._section_header(
                "听写",
                "设置语言、麦克风和启动方式。所有识别均在本机完成。",
            )
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.language_combo = QComboBox()
        self.language_combo.setAccessibleName("识别语言")
        self.microphone_combo = QComboBox()
        self.microphone_combo.setAccessibleName("麦克风")
        self.autostart_check = QCheckBox(
            "登录系统后自动启动" if sys.platform == "darwin" else "登录 Windows 后自动启动"
        )
        self.autostart_check.setAccessibleName("开机自动启动 VoiceFlow")
        rows = (
            ("语言", self.language_combo),
            ("麦克风", self.microphone_combo),
        )
        for row, (name, value) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setObjectName("fieldName")
            value.setObjectName("fieldValue")
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value, row, 1)
        layout.addLayout(grid)
        layout.addWidget(self.autostart_check)

        privacy_panel = QWidget()
        privacy_panel.setObjectName("privacyPanel")
        privacy_layout = QVBoxLayout(privacy_panel)
        privacy_layout.setContentsMargins(14, 11, 14, 11)
        privacy_layout.setSpacing(3)
        privacy_title = QLabel("本地处理")
        privacy_title.setObjectName("readinessName")
        privacy_copy = QLabel("录音和文字不会上传")
        privacy_copy.setObjectName("hotkeyValue")
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(privacy_copy)
        layout.addWidget(privacy_panel)

        hotkey_panel = QWidget()
        hotkey_panel.setObjectName("hotkeyPanel")
        hotkey_layout = QHBoxLayout(hotkey_panel)
        hotkey_layout.setContentsMargins(14, 11, 12, 11)
        hotkey_layout.setSpacing(12)
        hotkey_copy = QVBoxLayout()
        hotkey_copy.setSpacing(2)
        hotkey_title = QLabel("开始与停止")
        hotkey_title.setObjectName("readinessName")
        hotkey_value = QLabel(f"{trigger_summary()}　　Esc 取消")
        hotkey_value.setObjectName("hotkeyValue")
        hotkey_copy.addWidget(hotkey_title)
        hotkey_copy.addWidget(hotkey_value)
        hotkey_layout.addLayout(hotkey_copy, 1)
        trial = QPushButton("试说")
        trial.clicked.connect(self._start_trial)
        hotkey_layout.addWidget(trial)
        layout.addWidget(hotkey_panel)

        actions = QHBoxLayout()
        self.save_settings_button = QPushButton("保存设置")
        self.save_settings_button.setObjectName("primaryButton")
        self.save_settings_button.setAccessibleName("保存听写设置")
        self.save_settings_button.clicked.connect(self._save_settings)
        actions.addWidget(self.save_settings_button)
        save_note = QLabel("保存后重新启动 VoiceFlow 生效")
        save_note.setObjectName("sectionSubtitle")
        actions.addWidget(save_note)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        return page

    def _dictionary_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)
        layout.addLayout(
            self._section_header(
                "词典",
                "补充专有词、常用短语和确定性纠错，不改变你的原意。",
            )
        )

        self.dictionary_section = QComboBox()
        self.dictionary_section.setAccessibleName("词典分区")
        self.dictionary_section.addItem("专有词", "user-dictionary.txt")
        self.dictionary_section.addItem("常用短语", "phrases.txt")
        self.dictionary_section.addItem("确定性纠错", "corrections.txt")
        layout.addWidget(self.dictionary_section)

        add_row = QHBoxLayout()
        self.dictionary_input = QLineEdit()
        self.dictionary_input.setAccessibleName("新增词典条目")
        self.dictionary_input.setPlaceholderText("添加专有词")
        self.dictionary_input.returnPressed.connect(self._add_dictionary_entry)
        add = QPushButton("添加")
        add.setObjectName("primaryButton")
        add.clicked.connect(self._add_dictionary_entry)
        add_row.addWidget(self.dictionary_input, 1)
        add_row.addWidget(add)
        layout.addLayout(add_row)

        self.dictionary_hint = QLabel("每项单独一行，双击可以修改。")
        self.dictionary_hint.setObjectName("sectionSubtitle")
        layout.addWidget(self.dictionary_hint)

        self.dictionary_list = QListWidget()
        self.dictionary_list.setObjectName("dictionaryList")
        self.dictionary_list.setAccessibleName("词典条目")
        self.dictionary_list.itemChanged.connect(self._dictionary_item_changed)
        layout.addWidget(self.dictionary_list, 1)

        self.dictionary_count = QLabel("0 项")
        self.dictionary_count.setObjectName("historyMeta")
        layout.addWidget(self.dictionary_count)

        self.dictionary_section.currentIndexChanged.connect(
            self._change_dictionary_section
        )
        self._active_dictionary_filename = self.dictionary_section.currentData()

        note = QLabel(
            "全部内容只保存在这台电脑。纠错只执行明确的“错误词=正确词”替换，"
            "不会调用生成模型改写意思。"
        )
        note.setObjectName("privacyNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        actions = QHBoxLayout()
        remove = QPushButton("删除所选")
        remove.clicked.connect(self._remove_dictionary_entries)
        save = QPushButton("保存词典")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_dictionary)
        open_folder = QPushButton("打开词典目录")
        open_folder.clicked.connect(
            lambda: open_path(self.paths.knowledge_dir)
        )
        actions.addWidget(remove)
        actions.addWidget(save)
        actions.addWidget(open_folder)
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _diagnostics_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
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
        layout.setContentsMargins(28, 26, 28, 24)
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
        layout.addStretch(1)
        return page

    def refresh(self):
        config = self._load_config()
        active = config.get("engine", {}).get("active", "sensevoice")
        ready = self._engine_ready(active, config)
        self._set_status_badge("就绪" if ready else "需要设置")
        self._refresh_settings_controls(config)
        self._refresh_history()
        self._refresh_home(config)
        self._load_dictionary()
        self._refresh_recovery()

    def _set_status_badge(self, text, attention=None):
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

    def needs_onboarding(self):
        return not onboarding_completed(self.paths.config_file)

    def complete_onboarding(self):
        if self.needs_onboarding():
            set_onboarding_completed(self.paths.config_file, True)
        self.home_ready_title.setText("VoiceFlow 已就绪")
        self.home_ready_subtitle.setText(
            "刚才的文字已保存在剪贴板和本地历史中。以后直接按快捷键说话即可。"
        )
        self._set_status_badge("首次听写完成")

    def _refresh_home(self, config):
        active = config.get("engine", {}).get("active", "sensevoice")
        model_ready = self._engine_ready(active, config)
        microphone_name = self.microphone_combo.currentText() or "未检测到"
        microphone_ready = self._microphone_detected
        all_ready = model_ready and microphone_ready
        self.home_ready_title.setText(
            "随时可以开始" if all_ready else "还需要完成一项设置"
        )
        self.home_ready_subtitle.setText(
            "完全离线。按快捷键开始说话，再按一次停止。"
            if all_ready
            else "完成下方检查后，就可以在任意输入框使用语音输入。"
        )
        self.home_microphone.setText(
            f"已检测 · {microphone_name}" if microphone_ready else "需要选择"
        )
        self.home_model.setText(
            "可用 · 录音和文字不会上传" if model_ready else "需要修复"
        )
        self.home_hotkeys.setText(trigger_summary())
        self.trial_button.setEnabled(all_ready)

    def _start_trial(self):
        self.sidebar.setCurrentRow(0)
        self.practice_box.setFocus()
        self._set_status_badge(trigger_instruction())

    def _dictionary_path(self, filename):
        return self.paths.knowledge_dir / filename

    def _load_dictionary(self):
        for filename in (
            "user-dictionary.txt",
            "phrases.txt",
            "corrections.txt",
        ):
            try:
                raw = self._dictionary_path(filename).read_text(encoding="utf-8")
                self._dictionary_entries[filename] = [
                    line
                    for line in raw.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
            except FileNotFoundError:
                self._dictionary_entries[filename] = []
            except Exception as error:
                self._dictionary_entries[filename] = []
                self._set_status_badge(f"词典读取失败: {error}")
        self._active_dictionary_filename = self.dictionary_section.currentData()
        self._render_dictionary_section()

    def _store_dictionary_section(self):
        filename = self._active_dictionary_filename
        if not filename or not hasattr(self, "dictionary_list"):
            return
        entries = []
        for index in range(self.dictionary_list.count()):
            value = self.dictionary_list.item(index).text().strip()
            if value and value not in entries:
                entries.append(value)
        self._dictionary_entries[filename] = entries

    def _render_dictionary_section(self):
        filename = self._active_dictionary_filename
        if not filename or not hasattr(self, "dictionary_list"):
            return
        self.dictionary_list.blockSignals(True)
        self.dictionary_list.clear()
        for value in self._dictionary_entries.get(filename, []):
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.dictionary_list.addItem(item)
        self.dictionary_list.blockSignals(False)
        corrections = filename == "corrections.txt"
        if corrections:
            self.dictionary_input.setPlaceholderText("错误词=正确词")
            self.dictionary_hint.setText("写成“错误词=正确词”，双击可以修改。")
        elif filename == "phrases.txt":
            self.dictionary_input.setPlaceholderText("添加常用短语")
            self.dictionary_hint.setText("添加经常完整说出的短语，双击可以修改。")
        else:
            self.dictionary_input.setPlaceholderText("添加专有词")
            self.dictionary_hint.setText("添加人名、品牌或项目名，双击可以修改。")
        self._update_dictionary_count()

    def _change_dictionary_section(self, _index):
        self._store_dictionary_section()
        self._active_dictionary_filename = self.dictionary_section.currentData()
        self._render_dictionary_section()

    def _valid_dictionary_entry(self, value):
        if self._active_dictionary_filename != "corrections.txt":
            return bool(value)
        if value.count("=") != 1:
            return False
        wrong, correct = (part.strip() for part in value.split("=", 1))
        return bool(wrong and correct)

    def _add_dictionary_entry(self):
        value = self.dictionary_input.text().strip()
        if not self._valid_dictionary_entry(value):
            message = (
                "请使用“错误词=正确词”"
                if self._active_dictionary_filename == "corrections.txt"
                else "请输入内容"
            )
            self._set_status_badge(message, attention=True)
            return
        existing = {
            self.dictionary_list.item(index).text().strip()
            for index in range(self.dictionary_list.count())
        }
        if value in existing:
            self._set_status_badge("词典中已有这一项")
            return
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.dictionary_list.addItem(item)
        self.dictionary_input.clear()
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已添加，保存后生效")

    def _remove_dictionary_entries(self):
        selected = self.dictionary_list.selectedItems()
        if not selected:
            self._set_status_badge("请选择要删除的内容")
            return
        for item in selected:
            self.dictionary_list.takeItem(self.dictionary_list.row(item))
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已移除，保存后生效")

    def _dictionary_item_changed(self, item):
        value = item.text().strip()
        if not self._valid_dictionary_entry(value):
            self._set_status_badge("这一项格式不正确", attention=True)
            return
        self.dictionary_list.blockSignals(True)
        item.setText(value)
        self.dictionary_list.blockSignals(False)
        self._store_dictionary_section()
        self._update_dictionary_count()

    def _update_dictionary_count(self):
        if hasattr(self, "dictionary_count"):
            self.dictionary_count.setText(f"{self.dictionary_list.count()} 项")

    def _save_dictionary(self):
        try:
            self._store_dictionary_section()
            for filename, entries in self._dictionary_entries.items():
                if filename == "corrections.txt" and any(
                    not self._valid_correction(value) for value in entries
                ):
                    raise ValueError("纠错内容需要使用“错误词=正确词”")
                path = self._dictionary_path(filename)
                path.parent.mkdir(parents=True, exist_ok=True)
                text = "\n".join(entries).strip()
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_text(
                    f"{text}\n" if text else "",
                    encoding="utf-8",
                )
                os.replace(temporary, path)
            self._set_status_badge("词典已保存，重启后生效")
        except Exception as error:
            self._set_status_badge(f"词典保存失败: {error}")

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

    def _engine_ready(self, engine, config):
        return self.model_manager.status(engine, config).state is ModelState.READY

    def _refresh_settings_controls(self, config):
        engine = config.get("engine", {})
        active = engine.get("active", "sensevoice")
        self._populate_language_options(active, config)

        self.microphone_combo.clear()
        self.microphone_combo.addItem("系统默认麦克风", None)
        self._microphone_detected = False
        try:
            import sounddevice as sd
            for index, device in enumerate(sd.query_devices()):
                if int(device.get("max_input_channels", 0)) > 0:
                    self._microphone_detected = True
                    self.microphone_combo.addItem(str(device.get("name", index)), index)
        except Exception:
            pass
        selected_device = config.get("audio", {}).get("device_index")
        selected_index = self.microphone_combo.findData(selected_device)
        self.microphone_combo.setCurrentIndex(max(0, selected_index))
        self.autostart_check.setChecked(is_autostart_enabled(self.paths))

    def _save_settings(self):
        config = self._load_config()
        engine = config.get("engine", {}).get("active", "sensevoice")
        if self._switch_in_progress:
            return
        if self.model_manager.status(engine, config).state is not ModelState.READY:
            self._set_status_badge("本机识别能力不可用，请重新安装 VoiceFlow")
            return
        self._switch_in_progress = True
        self.save_settings_button.setEnabled(False)
        self._set_status_badge("正在保存设置")
        payload = {
            "engine": engine,
            "language": self.language_combo.currentData(),
            "device_index": self.microphone_combo.currentData(),
            "autostart": self.autostart_check.isChecked(),
        }

        def run():
            try:
                status = self.model_manager.status(engine, config, verify=True)
                if status.state is not ModelState.READY:
                    raise RuntimeError("模型 SHA-256 完整性校验未通过")
                update_runtime_settings(
                    self.paths.config_file,
                    engine=engine,
                    language=payload["language"],
                    device_index=payload["device_index"],
                )
                payload["ok"] = True
            except Exception as error:
                payload["ok"] = False
                payload["error"] = str(error)
            self.model_switch_finished.emit(payload)

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_model_switch(self, payload):
        self._switch_in_progress = False
        self.save_settings_button.setEnabled(True)
        if not payload.get("ok"):
            self._set_status_badge(f"设置保存失败：{payload.get('error', '未知错误')}")
            return
        try:
            set_autostart(self.paths, bool(payload.get("autostart")))
        except Exception as error:
            self._set_status_badge(f"听写设置已保存；自动启动设置失败：{error}")
            return
        self._set_status_badge("设置已保存，重启后生效")

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
            "clipboard_verified_paste_dispatched": "已完成",
            "clipboard_verified_only": "已复制",
            "recovery_saved_clipboard_unavailable": "已保存",
            "clipboard_copied_paste_sent": "已完成",
            "clipboard_copied_integrity_warning": "已复制",
            "fallback": "已复制",
            "typed": "已输入",
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
        path = self.paths.history_file
        if not path.exists():
            self._history_rows = []
            self._render_history()
            self._refresh_home_history()
            return
        try:
            with path.open("r", encoding="utf-8") as f:
                rows = [line for line in f.read().splitlines() if line][-80:]
            parsed = []
            for row in reversed(rows):
                try:
                    parsed.append(json.loads(row))
                except Exception:
                    pass
            self._history_rows = parsed
            self._render_history()
            self._refresh_home_history()
        except Exception as e:
            self._history_rows = [{"error": f"历史读取失败: {e}"}]
            self._render_history()
            self._refresh_home_history()

    def _refresh_home_history(self):
        if not hasattr(self, "home_recent_labels"):
            return
        rows = []
        for row in self._history_rows:
            text = (
                row.get("corrected_text")
                or row.get("clean_text")
                or row.get("error")
                or ""
            ).strip()
            if text:
                rows.append(text)
            if len(rows) == len(self.home_recent_labels):
                break
        for index, label in enumerate(self.home_recent_labels):
            if index < len(rows):
                value = rows[index]
                label.setText(value if len(value) <= 72 else f"{value[:72]}…")
                label.show()
            elif index == 0:
                label.setText("完成第一次听写后，文字会出现在这里。")
                label.show()
            else:
                label.hide()

    def _render_history(self):
        if not hasattr(self, "history_list"):
            return
        query = self.search_box.text().strip().lower() if hasattr(self, "search_box") else ""
        self.history_list.clear()
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
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, text)
            item.setSizeHint(QSize(0, 104))
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
        display_text = text if len(text) <= 180 else f"{text[:180]}…"
        body = QLabel(display_text)
        body.setObjectName("historyText")
        body.setWordWrap(True)
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
        repaste = QPushButton("再次粘贴")
        repaste.setObjectName("inlineRepasteButton")
        repaste.clicked.connect(
            lambda _=False, value=text: self._repaste_text(value)
        )
        row.addWidget(repaste)
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
            self._set_status_badge("无可复制")
            return
        if not self._on_copy_text:
            self._set_status_badge("复制失败", attention=True)
            return
        status = self._on_copy_text(text)
        label = self._output_status_label(status)
        self._set_status_badge(label, attention=label in {"失败", "未知"})

    def _repaste_selected(self):
        text = self._selected_text()
        self._repaste_text(text)

    def _repaste_text(self, text):
        if not text:
            self._set_status_badge("无可粘贴")
            return
        if not self._on_repaste_text:
            self._set_status_badge("粘贴失败", attention=True)
            return
        status = self._on_repaste_text(text)
        label = self._output_status_label(status)
        self._set_status_badge(label, attention=label in {"失败", "未知"})

    def _refresh_recovery(self):
        sessions = self.recovery_store.list_recoverable()
        self.recovery_combo.clear()
        for session in sessions:
            minutes = session.sample_count / max(1, session.sample_rate) / 60
            created = datetime.fromtimestamp(session.created_at).strftime("%m月%d日 %H:%M")
            self.recovery_combo.addItem(
                f"{created} · {minutes:.1f} 分钟 · {session.model}",
                session.session_id,
            )
            index = self.recovery_combo.count() - 1
            self.recovery_combo.setItemData(
                index,
                session.preview_text,
                int(Qt.ItemDataRole.UserRole) + 1,
            )
        self.recovery_summary.setText(f"有 {len(sessions)} 段录音可以恢复")
        self.recovery_panel.setVisible(bool(sessions))

    def _recover_selected_session(self):
        session_id = self.recovery_combo.currentData()
        if not session_id or not self._on_recover_session:
            return
        self.recover_button.setEnabled(False)
        self._set_status_badge("正在从本地录音恢复文字")

        def run():
            try:
                result = self._on_recover_session(str(session_id))
            except Exception as error:
                result = {"ok": False, "error": str(error)}
            self.recovery_finished.emit(result)

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_recovery(self, result):
        self.recover_button.setEnabled(True)
        if result.get("ok"):
            self._set_status_badge("恢复完成，文字已复制到剪贴板")
            self._refresh_history()
            self._refresh_recovery()
        else:
            self._set_status_badge(f"恢复未完成：{result.get('error', '录音仍已保留')}")

    def _copy_recovery_preview(self):
        preview = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 1) or ""
        if not preview:
            self._set_status_badge("这段录音还没有可复制的预览文字")
            return
        import pyperclip

        result = VerifiedClipboard(copy=pyperclip.copy, paste=pyperclip.paste).write_verified(preview)
        self._set_status_badge(
            "预览文字已复制" if result.verified else "预览文字仍在恢复记录中"
        )

    def _delete_recovery(self):
        session_id = self.recovery_combo.currentData()
        if not session_id or not self._on_delete_recovery:
            return
        answer = QMessageBox.question(
            self,
            "删除恢复录音",
            "这段本地恢复录音将被永久删除。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._on_delete_recovery(str(session_id)):
            self._set_status_badge("恢复录音已删除")
            self._refresh_recovery()
        else:
            self._set_status_badge("没有找到这段恢复录音")

    def _copy_all_visible(self):
        texts = []
        for i in range(self.history_list.count()):
            text = self.history_list.item(i).data(Qt.ItemDataRole.UserRole)
            if text:
                texts.append(text)
        if not texts:
            self._set_status_badge("无可复制")
            return
        import pyperclip
        pyperclip.copy("\n\n".join(texts))
        self._set_status_badge("已复制")

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
        self.doctor_summary.setText("正在检查 VoiceFlow…")
        self.doctor_list.clear()
        self.doctor_button.setEnabled(False)

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
        import pyperclip

        pyperclip.copy(format_diagnostics(self._last_diagnostics))
        self._set_status_badge("诊断报告已复制")

    def _high_contrast_enabled(self):
        if os.name != "nt":
            return False
        try:
            import ctypes

            class HighContrast(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("dwFlags", ctypes.c_uint),
                    ("lpszDefaultScheme", ctypes.c_wchar_p),
                ]

            value = HighContrast()
            value.cbSize = ctypes.sizeof(value)
            ok = ctypes.windll.user32.SystemParametersInfoW(
                0x0042,
                value.cbSize,
                ctypes.byref(value),
                0,
            )
            return bool(ok and value.dwFlags & 0x00000001)
        except Exception:
            return False

    def _style(self):
        return """
        QWidget#appShell {
            background: #ececef;
            color: #1d1d1f;
            font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei";
            font-size: 14px;
        }
        QWidget#sidebarPanel {
            background: #f5f5f7;
            border: 1px solid #dedee3;
            border-radius: 16px;
        }
        QLabel#brandIcon {
            min-width: 32px;
            min-height: 32px;
        }
        QLabel#appTitle {
            font-size: 17px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#appSubtitle, QLabel#sectionSubtitle, QLabel#fieldName {
            color: #6e6e73;
        }
        QLabel#appSubtitle, QLabel#sidebarVersion {
            font-size: 12px;
            color: #86868b;
        }
        QLabel#statusBadge {
            padding: 7px 10px;
            border-radius: 10px;
            background: #eaf7ee;
            color: #24753d;
            border: 1px solid #d3ead9;
            font-weight: 600;
        }
        QLabel#statusBadge[attention="true"] {
            color: #9a5b00;
            background: #fff4df;
            border-color: #f0dfba;
        }
        QListWidget#sidebar {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#sidebar::item {
            min-height: 38px;
            padding-left: 12px;
            border-radius: 9px;
            color: #515154;
        }
        QListWidget#sidebar::item:selected {
            background: #e4e4e9;
            color: #1d1d1f;
            border: none;
            font-weight: 600;
        }
        QStackedWidget#contentStack {
            background: #fbfbfc;
            border: 1px solid #dedee3;
            border-radius: 16px;
        }
        QWidget#contentPage {
            background: transparent;
            border: none;
        }
        QLabel#sectionTitle {
            font-size: 22px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#heroTitle {
            font-size: 27px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#heroSubtitle, QLabel#bodyText {
            color: #515154;
            font-size: 14px;
        }
        QLabel#subsectionTitle, QLabel#aboutVersion {
            color: #1d1d1f;
            font-size: 14px;
            font-weight: 600;
        }
        QWidget#heroPanel {
            background: #ffffff;
            border: 1px solid #ececf0;
            border-radius: 16px;
        }
        QWidget#readinessPanel {
            background: transparent;
            border: none;
        }
        QWidget#readinessItem {
            background: #ffffff;
            border: 1px solid #ececf0;
            border-radius: 12px;
        }
        QWidget#hotkeyPanel, QWidget#recoveryPanel,
        QWidget#aboutHero, QWidget#privacyPanel {
            background: #ffffff;
            border: 1px solid #ececf0;
            border-radius: 13px;
        }
        QLabel#recoveryTitle {
            color: #8a5600;
            font-size: 14px;
            font-weight: 650;
        }
        QLabel#readinessName {
            color: #6e6e73;
            font-size: 12px;
            font-weight: 500;
        }
        QLabel#readinessValue {
            color: #248a3d;
            font-weight: 600;
        }
        QLabel#hotkeyValue {
            color: #3a3a3c;
            font-size: 13px;
        }
        QLabel#recentLine {
            color: #3a3a3c;
            padding: 11px 13px;
            background: #ffffff;
            border: 1px solid #ececf0;
            border-radius: 11px;
        }
        QLabel#diagnosticSummary {
            color: #3a3a3c;
            background: #f0f6ff;
            border: 1px solid #ececf0;
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
            padding: 4px 8px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#diagnosticOk {
            color: #24753d;
            background: #eaf7ee;
        }
        QLabel#diagnosticAttention {
            color: #9a5b00;
            background: #fff4df;
        }
        QLabel#aboutTitle {
            color: #1d1d1f;
            font-size: 22px;
            font-weight: 650;
        }
        QLabel#privacyNote {
            color: #515154;
            background: #f0f6ff;
            border: 1px solid #dce9fb;
            border-radius: 11px;
            padding: 11px 13px;
        }
        QLabel#fieldValue {
            color: #1d1d1f;
            font-weight: 500;
        }
        QLineEdit, QPlainTextEdit, QComboBox,
        QListWidget#historyList, QListWidget#diagnosticList,
        QListWidget#dictionaryList {
            border: 1px solid #d5d5da;
            border-radius: 9px;
            background: #ffffff;
            padding: 9px 11px;
            selection-background-color: #007aff;
            selection-color: #ffffff;
        }
        QComboBox {
            min-height: 32px;
        }
        QComboBox::drop-down {
            width: 32px;
            border: none;
        }
        QListWidget#historyList, QListWidget#diagnosticList,
        QListWidget#dictionaryList {
            outline: none;
            background: #f4f4f6;
        }
        QListWidget#historyList::item, QListWidget#diagnosticList::item,
        QListWidget#dictionaryList::item {
            padding: 0px;
            margin: 5px;
            border-radius: 10px;
            border: none;
            background: #ffffff;
        }
        QListWidget#historyList::item:selected,
        QListWidget#diagnosticList::item:selected,
        QListWidget#dictionaryList::item:selected {
            color: #1d1d1f;
            background: #eef5ff;
            border: 1px solid #c8dfff;
        }
        QWidget#historyCard, QWidget#emptyCard,
        QWidget#diagnosticCard {
            background: transparent;
        }
        QLabel#historyText {
            color: #1d1d1f;
            font-size: 14px;
            font-weight: 500;
        }
        QLabel#historyMeta {
            color: #86868b;
            font-size: 13px;
        }
        QPushButton {
            min-height: 34px;
            padding: 6px 15px;
            border-radius: 9px;
            border: 1px solid #d5d5da;
            background: #ffffff;
            color: #1d1d1f;
            font-weight: 500;
        }
        QPushButton:hover {
            background: #f2f2f5;
        }
        QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus,
        QComboBox:focus, QListWidget:focus {
            border: 2px solid #007aff;
        }
        QPushButton#primaryButton {
            background: #007aff;
            color: white;
            border: 1px solid #007aff;
            font-weight: 600;
        }
        QPushButton#primaryButton:hover {
            background: #006ee6;
            border-color: #006ee6;
        }
        QPushButton#primaryButton:disabled {
            background: #c7c7cc;
            border-color: #c7c7cc;
        }
        QPushButton#textButton {
            border: none;
            background: transparent;
            color: #007aff;
            padding-left: 8px;
            padding-right: 8px;
        }
        QPushButton#inlineCopyButton, QPushButton#inlineRepasteButton {
            min-width: 58px;
            min-height: 28px;
            padding: 3px 10px;
        }
        """


class OverlayWindow:

    def __init__(self, paths=None):
        if paths is None:
            project_root = os.path.dirname(os.path.dirname(__file__))
            paths = AppPaths.discover(
                config_path=os.path.join(project_root, "config.yaml")
            )
        self.paths = paths
        self.window = None
        self.web_view = None
        self._bridge = None
        self._tray = None
        self._tray_icons = {}
        self._on_record_toggle = None
        self._on_copy_last = None
        self._on_repaste_last = None
        self._on_copy_text = None
        self._on_output_text = None
        self._on_open_dictionary = None
        self._on_quit = None
        self._on_recording_painted = None
        self._on_preview_painted = None
        self._on_recover_session = None
        self._on_delete_recovery = None
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
        self._preview_paint_reporter = None
        self._web_channel = None

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

    def start(self, on_ready=None):
        self._on_ready = on_ready
        self._run()

    def _run(self):
        app = QApplication(sys.argv)
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

        # ---- WebView ----
        self.web_view = QWebEngineView()
        self._preview_paint_reporter = _PreviewPaintReporter()
        self._preview_paint_reporter.painted.connect(self._preview_painted)
        self._web_channel = QWebChannel(self.web_view.page())
        self._web_channel.registerObject(
            "voiceflowBridge",
            self._preview_paint_reporter,
        )
        self.web_view.page().setWebChannel(self._web_channel)
        self.web_view.setUrl(QUrl.fromLocalFile(self._html_path))
        self.web_view.setStyleSheet("background: transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        self._bridge = _Bridge(
            self.web_view,
            before_show=self._expect_recording_paint,
        )
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

        app.exec()

    def _notify_existing_instance(self):
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_NAME)
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
        if not server.listen(SINGLE_INSTANCE_NAME):
            QLocalServer.removeServer(SINGLE_INSTANCE_NAME)
            if not server.listen(SINGLE_INSTANCE_NAME):
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

    def _expect_recording_paint(self):
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
                paths=self.paths,
            )
        return self._settings_window

    def _show_settings(self):
        self._ensure_settings_window()
        self._settings_window.refresh()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _show_startup(self):
        window = self._ensure_settings_window()
        if window.needs_onboarding():
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

    def show_recording(self, session_id, triggered_at=None):
        self._cancel_pending_hide()
        self._tray_state(TRAY_ICON_RECORDING)
        if triggered_at is not None:
            with self._recording_feedback_lock:
                self._pending_recording_feedback = (
                    int(session_id),
                    float(triggered_at),
                )
        if self._bridge:
            self._bridge.js_then_show_requested.emit(f"prepareRecording({int(session_id)})")

    def append_streaming(self, delta, session_id):
        self._js(
            f"appendStreaming({json.dumps(delta, ensure_ascii=False)}, {int(session_id)})"
        )

    def update_transcript_state(self, state):
        self._js(
            "updateTranscriptState("
            f"{json.dumps(state.authoritative_prefix, ensure_ascii=False)}, "
            f"{json.dumps(state.draft_tail, ensure_ascii=False)}, "
            f"{int(state.session_id)})"
        )

    def show_authoritative_final(self, text, session_id):
        self._js(
            "showAuthoritativeFinal("
            f"{json.dumps(text, ensure_ascii=False)}, {int(session_id)})"
        )

    def update_audio_level(self, levels, session_id):
        if self._bridge:
            safe_levels = [max(0.0, min(float(level), 1.0)) for level in levels[:3]]
            self._bridge.level_js_requested.emit(
                f"updateAudioLevel({json.dumps(safe_levels)}, {int(session_id)})"
            )

    def show_processing(self):
        self._tray_state(TRAY_ICON_PROCESSING)
        self._js("showProcessing()")

    def show_settling(self, session_id):
        self._tray_state(TRAY_ICON_PROCESSING)
        self._js(f"showSettling({int(session_id)})")


    def show_delivery_state(self, status, session_id):
        self._tray_state(TRAY_ICON_IDLE)
        self._js(
            "showDeliveryState("
            f"{json.dumps(str(status))}, "
            f"{int(session_id)})"
        )


    def show_result(self, text):
        self._js(f"showResult({json.dumps(text, ensure_ascii=False)})")
        self._tray_state(TRAY_ICON_IDLE)

    def show_error(self, msg):
        self._tray_state(TRAY_ICON_ERROR)
        self._js(f"showState('error', {json.dumps(msg, ensure_ascii=False)})")

    def show_recovery_available(self, count):
        self._tray_state(TRAY_ICON_IDLE)
        self._js(f"showRecoveryAvailable({int(count)})")
        self.show_window()
        self.hide_after(3600)

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
        if not self._page_ready or not self._web_view or not self._web_view.page():
            self.hide_requested.emit()
            return
        self._web_view.page().runJavaScript(code, lambda _: QTimer.singleShot(50, self.hide_requested.emit))
