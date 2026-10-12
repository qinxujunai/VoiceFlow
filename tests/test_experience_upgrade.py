"""Behavioral regression guards for the unified offline experience."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_runtime_integrity_ignores_evaluation_audio_but_checks_weights(tmp_path):
    from model_registry import verify_model_assets

    weights = tmp_path / "model.onnx"
    weights.write_bytes(b"pinned weights")
    model = {"files": [
        {"path": "model.onnx", "size": 14,
         "sha256": hashlib.sha256(weights.read_bytes()).hexdigest()},
        {"path": "test_wavs/zh.wav", "size": 42, "sha256": "0" * 64},
    ]}
    assert verify_model_assets(tmp_path, model, runtime_only=True) == []
    assert verify_model_assets(tmp_path, model)
    weights.write_bytes(b"broken weights")
    assert verify_model_assets(tmp_path, model, runtime_only=True)


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    import settings_store
    from dictation_preferences import DictationPreferencesStore
    from runtime_paths import AppPaths, RuntimeMode

    paths = AppPaths(mode=RuntimeMode.FROZEN, install_dir=tmp_path, data_dir=tmp_path,
                     executable=tmp_path / "VoiceFlow.exe")
    paths.config_file.write_text(
        '# keep comments\nengine:\n  active: "sensevoice"\n  sensevoice:\n'
        '    language: "auto"\naudio:\n  device_index: null\n', encoding="utf-8")
    store = DictationPreferencesStore(paths.dictation_preferences_file)
    autostart = {"value": False}
    monkeypatch.setattr(settings_store, "is_autostart_enabled", lambda _p: autostart["value"])
    monkeypatch.setattr(settings_store, "set_autostart",
                        lambda _p, enabled: autostart.update(value=enabled))
    monkeypatch.setattr(settings_store, "read_autostart_state", lambda: autostart["value"])
    monkeypatch.setattr(settings_store, "restore_autostart_state", lambda saved: autostart.update(value=saved))
    payload = {"engine": "sensevoice", "language": "zh", "device_index": 2,
               "autostart": True, "expected_config": paths.config_file.read_text(encoding="utf-8"),
               "expected_preferences": store.snapshot(), "preferences": store.snapshot()}
    payload["preferences"]["global"]["sentence_end"] = "omit_period"
    return paths, store, payload, autostart


def test_unified_save_commits_all_settings(transaction):
    from settings_store import save_settings_transaction

    paths, store, payload, autostart = transaction
    result = save_settings_transaction(paths, store, payload)
    assert result["restart_required"]
    assert autostart["value"]
    assert store.options_for("notepad.exe").sentence_end == "omit_period"
    assert yaml.safe_load(paths.config_file.read_text(encoding="utf-8"))["audio"]["device_index"] == 2
    assert paths.config_file.read_text(encoding="utf-8").startswith("# keep comments")


def test_unified_save_rolls_back_config_and_autostart_on_preference_failure(transaction, monkeypatch):
    from settings_store import save_settings_transaction

    paths, store, payload, autostart = transaction
    before = paths.config_file.read_bytes()
    prefs = paths.dictation_preferences_file.read_bytes()
    monkeypatch.setattr(store, "_write", lambda _p: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        save_settings_transaction(paths, store, payload)
    assert paths.config_file.read_bytes() == before
    assert paths.dictation_preferences_file.read_bytes() == prefs
    assert store.options_for("notepad.exe").sentence_end == "preserve"
    assert not autostart["value"]


def test_unified_save_rejects_stale_preferences_before_any_write(transaction):
    from settings_store import save_settings_transaction
    from dictation_preferences import PreferencesChangedError

    paths, store, payload, autostart = transaction
    before = paths.config_file.read_bytes()
    store.update(sentence_end="complete_period", preserve_format=False)
    with pytest.raises(PreferencesChangedError):
        save_settings_transaction(paths, store, payload)
    assert paths.config_file.read_bytes() == before
    assert not autostart["value"]


def test_faithful_spacing_preserves_words_and_technical_text():
    from punctuation import normalize_dictation_spacing

    assert normalize_dictation_spacing("这 是 一个 想法 ， 继续。") == "这是一个想法，继续。"
    assert normalize_dictation_spacing("你好。。。，，继续") == "你好。继续"
    for technical in ("https://example.com/a?b=2", "版本 1.2.3", "x = 2", "E:\\my project\\a.py"):
        assert normalize_dictation_spacing(technical) == technical
    assert normalize_dictation_spacing("how are you") == "how are you"


def test_native_capsule_expands_in_steps_instead_of_retargeting_each_character(monkeypatch):
    from capsule_native import NativeCapsuleView
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    view.state.prepare_recording(1)
    view.state.show_final("你", 1)
    view._retarget_width(0)
    first = view._target_width
    view.state.show_final("你好", 1)
    view._retarget_width(.048)
    assert first == view._target_width
    assert view._target_width <= view.MAX_WIDTH
    view.close()


@pytest.fixture
def settings_ui(tmp_path):
    import shutil, time
    from app_controller import AppController
    from dictation_preferences import DictationPreferencesStore
    from overlay_webview import _SettingsWindow
    from qt_compat import QApplication
    from runtime_paths import AppPaths, RuntimeMode
    from settings_store import save_settings_transaction

    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(mode=RuntimeMode.FROZEN, install_dir=root, data_dir=tmp_path,
                     executable=Path(sys.executable))
    shutil.copy2(root / "config.yaml", paths.config_file)
    shutil.copytree(root / "knowledge-base", paths.knowledge_dir)
    store = DictationPreferencesStore(paths.dictation_preferences_file)
    controller = AppController(on_query_dictation_preferences=store.snapshot,
                              on_save_settings=lambda draft: save_settings_transaction(paths, store, draft))
    window = _SettingsWindow(paths=paths, controller=controller)
    window.refresh()
    deadline = time.monotonic() + 2
    while window._refresh_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    yield app, window, store
    window.hide()
    window._runtime_status_timer.stop()


def test_single_save_does_not_check_model_or_send_feedback_to_sidebar(settings_ui, monkeypatch):
    import time
    from qt_compat import QPushButton
    app, ui, store = settings_ui
    monkeypatch.setattr(ui.model_manager, "status", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("unrelated hash check")))
    ui.show()
    ui.sentence_end_combo.setCurrentIndex(ui.sentence_end_combo.findData("omit_period"))
    assert ui.save_settings_button.isEnabled()
    assert [button.text() for button in ui.findChildren(QPushButton) if button.isVisible() and button.text().startswith("保存")] == ["保存更改"]
    ui.save_settings_button.click()
    deadline = time.monotonic() + 2
    while ui._switch_in_progress and time.monotonic() < deadline:
        app.processEvents(); time.sleep(.005)
    assert store.options_for("notepad.exe").sentence_end == "omit_period"
    assert "已保存" in ui.operation_feedback.text()
    assert "已保存" not in ui.status_badge.text()
    assert not ui.save_settings_button.isEnabled()
    ui._set_status_badge("保存失败：" + "完整反馈" * 30, attention=True)
    app.processEvents()
    assert ui.operation_feedback.wordWrap()
    assert ui.operation_feedback.width() <= ui.width()


def test_feedback_changes_from_success_to_failure_without_stale_green(settings_ui):
    app, ui, _store = settings_ui
    ui.show()
    ui._set_status_badge("已保存", attention=False)
    app.processEvents()
    assert ui.operation_feedback.palette().windowText().color().name() == "#285b3a"
    ui._set_status_badge("保存失败，请重试", attention=True)
    app.processEvents()
    assert ui.operation_feedback.palette().windowText().color().name() == "#874914"


def test_dictionary_search_selection_undo_retains_subsequent_additions(settings_ui):
    from qt_compat import Qt
    app, ui, _store = settings_ui
    ui.dictionary_section.setCurrentIndex(ui.dictionary_section.findData("user-dictionary.txt"))
    ui._dictionary_entries["user-dictionary.txt"] = ["Alpha", "Beta", "Alphabet"]
    ui._render_dictionary_section()
    ui.dictionary_search.setText("Alpha")
    ui._select_dictionary_results()
    assert sum(ui.dictionary_list.item(i).checkState() == Qt.CheckState.Checked for i in range(3)) == 2
    ui._remove_dictionary_entries()
    assert ui._dictionary_entries["user-dictionary.txt"] == ["Beta"]
    ui.dictionary_input.setText("New")
    ui._add_dictionary_entry()
    ui._undo_dictionary_delete()
    assert ui._dictionary_entries["user-dictionary.txt"] == ["Alpha", "Beta", "Alphabet", "New"]
    ui.dictionary_section.setCurrentIndex(ui.dictionary_section.findData("builtin-ai.txt"))
    before = list(ui._dictionary_entries["builtin-ai.txt"])
    ui._clear_dictionary()
    ui._remove_dictionary_entries()
    assert ui._dictionary_entries["builtin-ai.txt"] == before


def test_close_keeps_window_recoverable_without_quitting(settings_ui, monkeypatch):
    from qt_compat import QSystemTrayIcon
    app, ui, _store = settings_ui
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    ui.show(); ui.close(); app.processEvents()
    assert ui.isHidden()
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    ui.show(); ui.close(); app.processEvents()
    assert ui.isMinimized() and not ui.isHidden()


def test_dictionary_completion_invalidates_refresh_started_during_save(settings_ui):
    _app, ui, _store = settings_ui
    ui._dictionary_generation += 1
    during_save = ui._dictionary_generation
    ui._dictionary_save_in_progress = True
    ui._finish_dictionary_save({"ok": True, "entries": ui._dictionary_entries})
    assert ui._dictionary_generation > during_save


def test_history_cards_use_plain_text_and_height_for_actual_width(settings_ui):
    from qt_compat import QLabel, QListWidgetItem, QPushButton, Qt
    app, ui, _store = settings_ui
    ui.show()
    ui._show_primary_page(2)
    text = "<b>原文</b>" + "这是包含自然停顿的长段记录。" * 100
    ui._history_rows = [{"_entry_id": "long", "raw_text": text}]
    card = ui._history_card(text, "刚刚", "long")
    item = QListWidgetItem(ui.history_list)
    ui.history_list.setItemWidget(item, card)
    ui.resize(640, 650)
    app.processEvents()
    for button in card.findChildren(QPushButton):
        if button.text() == "查看详情":
            button.click()
    app.processEvents()
    ui._resize_history_cards()
    assert all(label.textFormat() == Qt.TextFormat.PlainText
               for label in card.findChildren(QLabel))
    assert item.sizeHint().height() >= card.layout().heightForWidth(card.width())
