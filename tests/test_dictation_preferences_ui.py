import os
import shutil
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def window(tmp_path):
    from app_controller import AppController
    from dictation_preferences import DictationPreferencesStore
    from overlay_webview import _SettingsWindow
    from qt_compat import QApplication
    from runtime_paths import AppPaths, RuntimeMode

    app = QApplication.instance() or QApplication([])
    data = tmp_path / "data"
    data.mkdir()
    paths = AppPaths(mode=RuntimeMode.FROZEN, install_dir=ROOT, data_dir=data,
                     executable=Path(sys.executable))
    shutil.copy2(ROOT / "config.yaml", paths.config_file)
    store = DictationPreferencesStore(paths.dictation_preferences_file)

    def query():
        return {**store.snapshot(), "last_app": "msedge.exe"}

    controller = AppController(on_query_dictation_preferences=query,
                              on_update_dictation_preferences=lambda options: store.update(**options))
    ui = _SettingsWindow(paths=paths, controller=controller)
    yield app, ui, store, query
    ui.close()
    app.processEvents()


def test_sentence_end_controls_preview_and_save_explicit_application_scope(window):
    app, ui, store, query = window
    ui._apply_dictation_preferences(query())
    assert ui.sentence_end_combo.count() == 3
    ui.dictation_scope_combo.setCurrentIndex(ui.dictation_scope_combo.findData("msedge.exe"))
    assert "所有网站" in ui.dictation_scope_note.text()
    ui.sentence_end_combo.setCurrentIndex(ui.sentence_end_combo.findData("omit_period"))
    assert "你好。" not in ui.sentence_end_sample.text()
    assert "你好" in ui.sentence_end_sample.text()
    ui._save_dictation_preferences()
    deadline = time.monotonic() + 2
    while ui._dictation_save_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert not ui._dictation_save_in_progress
    assert store.options_for("msedge.exe").sentence_end == "omit_period"
    assert store.options_for("chrome.exe").sentence_end == "preserve"
    assert "下一次" in ui.status_badge.text()


def test_tray_sentence_end_menu_uses_the_same_live_store_without_new_hotkeys(window):
    from overlay_webview import OverlayWindow
    from qt_compat import QMenu

    _app, ui, store, query = window
    overlay = object.__new__(OverlayWindow)
    overlay.controller = ui.controller
    overlay._tray_menu = QMenu()
    overlay._tray_actions = []
    overlay._setup_sentence_end_menu()
    overlay._refresh_sentence_end_menu()
    actions = overlay._sentence_end_menu.actions()
    assert [action.text() for action in actions] == ["保留识别标点", "省略最后一个句号", "补全句末句号"]
    assert actions[0].isChecked()
    store.update(sentence_end="complete_period", preserve_format=False)
    overlay._refresh_sentence_end_menu()
    assert actions[2].isChecked()
    assert all(action.shortcut().isEmpty() for action in actions)
    overlay._tray_menu.close()


def test_dictation_settings_fit_the_supported_minimum_window(window):
    app, ui, _store, query = window
    ui._apply_dictation_preferences(query())
    ui.resize(980, 660)
    ui.show()
    app.processEvents()
    assert ui.height() <= 660
    assert ui.save_settings_button.isVisible()
    ui.dictation_scroll.ensureWidgetVisible(ui.save_settings_button)
    app.processEvents()
    position = ui.save_settings_button.mapTo(ui, ui.save_settings_button.rect().bottomRight())
    assert position.y() < 660
    fields = [ui.language_combo, ui.microphone_combo, ui.dictation_scope_combo, ui.sentence_end_combo]
    for first, second in zip(fields, fields[1:]):
        assert first.geometry().bottom() < second.geometry().top()


def test_preferences_save_failure_keeps_live_policy_and_shows_failure(window, monkeypatch):
    app, ui, store, query = window
    ui._apply_dictation_preferences(query())
    monkeypatch.setattr(store, "_write", lambda *_args: (_ for _ in ()).throw(OSError("fixture disk failure")))
    ui.sentence_end_combo.setCurrentIndex(ui.sentence_end_combo.findData("omit_period"))
    ui._save_dictation_preferences()
    deadline = time.monotonic() + 2
    while ui._dictation_save_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert "未保存" in ui.status_badge.text()
    assert store.options_for("notepad.exe").sentence_end == "preserve"


def test_settings_can_remove_an_application_override(window):
    app, ui, store, query = window
    store.update(sentence_end="omit_period", preserve_format=False, app_id="msedge.exe")
    ui._apply_dictation_preferences(query())
    ui.dictation_scope_combo.setCurrentIndex(ui.dictation_scope_combo.findData("msedge.exe"))
    assert ui.follow_default_button.isEnabled()
    ui.follow_default_button.click()
    deadline = time.monotonic() + 2
    while ui._dictation_save_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert "msedge.exe" not in store.snapshot()["apps"]
    assert not ui.follow_default_button.isEnabled()
    assert "默认" in ui.status_badge.text()


def test_stale_open_settings_refreshes_instead_of_overwriting_tray_change(window):
    app, ui, store, query = window
    ui._apply_dictation_preferences(query())
    store.update(sentence_end="complete_period", preserve_format=False)
    ui.preserve_format_check.setChecked(True)
    ui._save_dictation_preferences()
    deadline = time.monotonic() + 2
    while ui._dictation_save_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert store.options_for("notepad.exe").sentence_end == "complete_period"
    assert not store.options_for("notepad.exe").preserve_format
    assert ui.sentence_end_combo.currentData() == "complete_period"
    assert "重新保存" in ui.status_badge.text()


def test_open_settings_releases_custom_colors_when_high_contrast_changes(window, monkeypatch):
    from PySide6.QtCore import QEvent

    app, ui, _store, _query = window
    assert ui.styleSheet()
    monkeypatch.setattr(ui, "_high_contrast_enabled", lambda: True)
    app.sendEvent(ui, QEvent(QEvent.Type.ApplicationPaletteChange))
    assert ui.styleSheet() == ""
    monkeypatch.setattr(ui, "_high_contrast_enabled", lambda: False)
    app.sendEvent(ui, QEvent(QEvent.Type.ApplicationPaletteChange))
    assert ui.styleSheet() == ui._style()
