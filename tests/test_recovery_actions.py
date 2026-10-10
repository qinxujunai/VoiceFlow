import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_controller_recovery_actions_only_copy_and_never_dispatch():
    from app_controller import AppController

    copied = []
    finished = threading.Event()

    def copy_last():
        copied.append("last")
        finished.set()

    def forbidden(*_args):
        raise AssertionError("recovery action must not dispatch a paste")

    controller = AppController(on_copy_last=copy_last,
                              on_copy_text=copied.append, on_repaste_last=forbidden,
                              on_output_text=forbidden)
    controller.repaste_last()
    assert finished.wait(1)
    controller.output_text("historical final")
    assert copied == ["last", "historical final"]


def test_tray_copy_never_waits_for_clipboard_or_history_on_the_ui_thread():
    from app_controller import AppController

    entered = threading.Event()
    release = threading.Event()

    def blocked_clipboard():
        entered.set()
        release.wait(1)

    controller = AppController(on_copy_last=blocked_clipboard)
    try:
        started = time.perf_counter()
        result = controller.copy_last()
        assert time.perf_counter() - started < .05
        assert result.accepted
        assert entered.wait(1)
        assert not controller.copy_last().accepted
    finally:
        release.set()


def test_settings_legacy_repaste_copies_without_calling_the_paste_callback():
    from overlay_webview import _SettingsWindow

    copied = []
    ui = SimpleNamespace(_copy_text=copied.append)
    _SettingsWindow._repaste_text(ui, "历史终稿")
    assert copied == ["历史终稿"]


@pytest.fixture
def window(tmp_path):
    from overlay_webview import _SettingsWindow
    from qt_compat import QApplication
    from runtime_paths import AppPaths, RuntimeMode

    app = QApplication.instance() or QApplication([])
    paths = AppPaths(mode=RuntimeMode.FROZEN, install_dir=Path(__file__).resolve().parents[1],
                     data_dir=tmp_path, executable=Path(sys.executable))
    paths.config_file.write_text("ui:\n  onboarding_completed: false\n", encoding="utf-8")
    ui = _SettingsWindow(paths=paths)
    ui.onboarding_panel.setVisible(True)
    yield app, ui
    ui.close()
    app.processEvents()


def test_history_card_has_copy_and_delete_without_a_paste_action(window):
    from qt_compat import QPushButton

    _app, ui = window
    card = ui._history_card("历史终稿", "输入未确认", "fixture")
    labels = [button.text() for button in card.findChildren(QPushButton)]
    assert labels == ["复制", "删除"]


def test_manual_first_use_confirmation_requires_user_attestation(window):
    from settings_store import onboarding_completed

    app, ui = window
    assert not ui.confirm_onboarding_button.isEnabled()
    ui.complete_onboarding(manual=True)
    assert not onboarding_completed(ui.paths.config_file)
    ui.onboarding_confirm_check.setChecked(True)
    assert ui.confirm_onboarding_button.isEnabled()
    ui.confirm_onboarding_button.click()
    deadline = time.monotonic() + 2
    while ui._onboarding_save_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not ui._onboarding_save_in_progress
    assert onboarding_completed(ui.paths.config_file)
    assert ui.onboarding_panel.isHidden()
    assert "已确认" in ui.status_badge.text()


def test_first_use_save_failure_never_claims_completion(window, monkeypatch):
    from settings_store import onboarding_completed

    app, ui = window

    def unavailable(*_args):
        raise OSError("fixture configuration occupied")

    monkeypatch.setattr("overlay_webview.set_onboarding_completed", unavailable)
    ui.onboarding_confirm_check.setChecked(True)
    ui.confirm_onboarding_button.click()
    deadline = time.monotonic() + 2
    while ui._onboarding_save_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not onboarding_completed(ui.paths.config_file)
    assert not ui.onboarding_panel.isHidden()
    assert "未保存" in ui.status_badge.text()
