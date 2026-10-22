"""The 听写 page: input and punctuation preferences, one save transaction."""

import logging
import sys
import threading
import copy

from qt_compat import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QScrollArea,
    Qt,
    Slot,
)

from settings_store import is_autostart_enabled
from runtime_services import ModelState
from platform_utils import trigger_summary
from punctuation import SENTENCE_END_CHOICES, apply_sentence_end
from dictation_preferences import application_preserves_format, normalize_app_id, PreferencesChangedError

logger = logging.getLogger("voiceflow.ui")


class PreferencesMixin:
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
