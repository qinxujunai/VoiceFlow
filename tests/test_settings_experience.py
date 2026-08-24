from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "src" / "overlay_webview.py"


def _block(source, start, end):
    return source.split(start, 1)[1].split(end, 1)[0]


def test_primary_status_pages_hide_model_and_thread_implementation_details():
    source = OVERLAY.read_text(encoding="utf-8")
    home = _block(source, "def _home_page", "def _recent_page")
    dictation = _block(source, "def _status_page", "def _dictionary_page")
    refresh_home = _block(source, "def _refresh_home", "def _dictionary_path")

    for block in (home, dictation, refresh_home):
        assert "SenseVoice" not in block
        assert "离线模型" not in block
        assert "识别线程" not in block
    assert '"本地处理"' in home
    assert "录音和文字不会上传" in source


def test_sidebar_version_is_two_lines_and_the_shell_avoids_a_double_border():
    source = OVERLAY.read_text(encoding="utf-8")

    assert 'QLabel(f"{display_version()}\\n{platform_label()}")' in source
    assert "self.setMinimumSize(980, 660)" in source
    assert "QStackedWidget#contentStack {" in source
    assert "QWidget#contentPage {" in source


def test_settings_home_uses_a_quiet_command_center_hierarchy():
    source = OVERLAY.read_text(encoding="utf-8")
    shell = _block(source, "class _SettingsWindow", "def _show_primary_page")
    home = _block(source, "def _home_page", "def _recent_page")

    assert "sidebar_panel.setFixedWidth(176)" in shell
    assert 'self.home_ready_title = QLabel("VoiceFlow 已就绪")' in home
    assert 'self.trial_button = QPushButton("试说一句")' not in home
    assert 'self.practice_box.setPlaceholderText("识别结果会出现在这里")' in home
    assert 'for title in ("麦克风", "本地处理", "快捷键")' not in home
    assert 'readiness_title = QLabel("准备状态")' not in home
    assert "heroPanel" not in home


def test_settings_shell_keeps_diagnostics_auxiliary_and_no_model_marketplace():
    source = OVERLAY.read_text(encoding="utf-8")
    settings = _block(source, "class _SettingsWindow", "class OverlayWindow")

    assert 'for label in ("状态", "听写", "词典", "历史")' in settings
    assert 'QPushButton("运行检查")' in settings
    assert "model_download_button" not in settings
    assert "self.model_manager.start_download" not in settings


def test_dictionary_uses_an_entry_list_instead_of_a_raw_file_editor():
    source = OVERLAY.read_text(encoding="utf-8")
    dictionary = _block(source, "def _dictionary_page", "def _diagnostics_page")

    assert "self.dictionary_list = QListWidget()" in dictionary
    assert "self.dictionary_input = QLineEdit()" in dictionary
    assert "添加" in dictionary
    assert "删除所选" in dictionary
    assert "dictionary_editors" not in dictionary
    assert 'setPlaceholderText("错误词=正确词")' in source


def test_dictionary_exposes_bundled_ai_terms_as_read_only_product_content():
    source = OVERLAY.read_text(encoding="utf-8")
    dictionary = _block(source, "def _dictionary_page", "def _diagnostics_page")
    rendering = _block(source, "def _render_dictionary_section", "def _change_dictionary_section")

    assert 'self.dictionary_section.addItem("内置 AI 术语", "builtin-ai.txt")' in dictionary
    assert 'readonly = filename == "builtin-ai.txt"' in rendering
    assert "self.dictionary_add_button.setEnabled(not readonly)" in rendering
    assert "self.dictionary_remove_button.setEnabled(not readonly)" in rendering
    assert "self.dictionary_input.setEnabled(not readonly)" in rendering
    assert "内置术语随 VoiceFlow 更新" in rendering


def test_dictionary_copy_explains_what_each_entry_can_reliably_change():
    source = OVERLAY.read_text(encoding="utf-8")
    dictionary = _block(source, "def _dictionary_page", "def _diagnostics_page")
    rendering = _block(source, "def _render_dictionary_section", "def _change_dictionary_section")
    saving = _block(source, "def _save_dictionary", "def _valid_correction")

    assert "英文术语会规范大小写" in dictionary
    assert "误识别请使用确定性纠错" in rendering
    assert 'self._set_status_badge("词典已保存")' in saving
    assert "词典已保存，重启后生效" not in saving


def test_help_and_settings_labels_are_short_and_task_oriented():
    source = OVERLAY.read_text(encoding="utf-8")
    shell = _block(source, "class _SettingsWindow", "def _show_primary_page")
    settings = _block(source, "def _status_page", "def _dictionary_page")

    assert 'help_menu.addAction("运行检查")' in shell
    assert 'help_menu.addAction("关于 VoiceFlow")' in shell
    assert 'self.help_button = QPushButton("帮助")' in shell
    assert '"听写",\n                "选择语言、麦克风和启动方式。"' in settings


def test_each_history_card_owns_copy_and_repaste_actions():
    source = OVERLAY.read_text(encoding="utf-8")
    recent = _block(source, "def _recent_page", "def _status_page")
    card = _block(source, "def _history_card", "def _empty_card")

    assert "self.copy_button" not in recent
    assert "self.repaste_button" not in recent
    assert 'QPushButton("复制全部")' in recent
    assert 'QPushButton("复制")' in card
    assert 'QPushButton("再次粘贴")' in card
    assert 'QPushButton("删除")' in card
    assert 'QPushButton("清空历史")' in recent


def test_ui_evidence_captures_the_current_sidebar_order():
    script = (ROOT / "scripts" / "capture_ui_states.py").read_text(
        encoding="utf-8"
    )

    assert '(0, "status")' in script
    assert '(1, "dictation")' in script
    assert '(2, "dictionary")' in script
    assert '(3, "history")' in script
    assert '(3, "settings")' not in script


def test_history_uses_the_same_short_truthful_status_words_as_the_capsule():
    source = OVERLAY.read_text(encoding="utf-8")
    labels = _block(source, "def _output_status_label", "def _format_timestamp")

    assert '"clipboard_verified_paste_dispatched": "已完成"' in labels
    assert '"clipboard_verified_only": "已复制"' in labels
    assert '"recovery_saved_clipboard_unavailable": "已保存"' in labels
    assert "已复制并发送粘贴" not in labels
    assert '}.get(status, "未知")' in labels


def test_history_actions_use_the_verified_delivery_callbacks():
    source = OVERLAY.read_text(encoding="utf-8")
    copy_action = _block(source, "def _copy_text", "def _repaste_selected")
    repaste_action = _block(source, "def _repaste_text", "def _refresh_recovery")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    assert "pyperclip.copy" not in copy_action
    assert "self._run_history_action(text, self._on_copy_text" in copy_action
    assert "self._run_history_action(text, self._on_repaste_text" in repaste_action
    assert "threading.Thread(" in repaste_action
    assert "self._output_status_label(status)" in repaste_action
    assert "return self.output_handler.copy_only(text)" in main
    assert "return self.output_handler.output(text)" in main
