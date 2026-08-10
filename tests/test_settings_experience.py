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
    refresh_home = _block(source, "def _refresh_home", "def _start_trial")

    for block in (home, dictation, refresh_home):
        assert "SenseVoice" not in block
        assert "离线模型" not in block
        assert "识别线程" not in block
    assert '"本地处理"' in home
    assert "录音和文字不会上传" in source


def test_sidebar_version_is_two_lines_and_the_shell_avoids_a_double_border():
    source = OVERLAY.read_text(encoding="utf-8")

    assert 'QLabel(f"{display_version()}\\n{platform_label()}")' in source
    assert "self.setMinimumSize(940, 640)" in source
    assert "QStackedWidget#contentStack {" in source
    assert "QWidget#contentPage {" in source


def test_dictionary_uses_an_entry_list_instead_of_a_raw_file_editor():
    source = OVERLAY.read_text(encoding="utf-8")
    dictionary = _block(source, "def _dictionary_page", "def _diagnostics_page")

    assert "self.dictionary_list = QListWidget()" in dictionary
    assert "self.dictionary_input = QLineEdit()" in dictionary
    assert "添加" in dictionary
    assert "删除所选" in dictionary
    assert "dictionary_editors" not in dictionary
    assert 'setPlaceholderText("错误词=正确词")' in source


def test_each_history_card_owns_copy_and_repaste_actions():
    source = OVERLAY.read_text(encoding="utf-8")
    recent = _block(source, "def _recent_page", "def _status_page")
    card = _block(source, "def _history_card", "def _empty_card")

    assert "self.copy_button" not in recent
    assert "self.repaste_button" not in recent
    assert 'QPushButton("复制全部")' in recent
    assert 'QPushButton("复制")' in card
    assert 'QPushButton("再次粘贴")' in card


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
    assert "status = self._on_copy_text(text)" in copy_action
    assert "status = self._on_repaste_text(text)" in repaste_action
    assert "self._output_status_label(status)" in copy_action
    assert "self._output_status_label(status)" in repaste_action
    assert "return self.output_handler.copy_only(text)" in main
    assert "return self.output_handler.output(text)" in main
