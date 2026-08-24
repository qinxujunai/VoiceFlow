from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from overlay_webview import _SettingsWindow  # noqa: E402
from overlay_webview import OverlayWindow  # noqa: E402
from qt_compat import QApplication, QMessageBox  # noqa: E402
from runtime_paths import AppPaths, RuntimeMode  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def paths(tmp_path):
    data_dir = tmp_path / "VoiceFlow"
    data_dir.mkdir()
    result = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=ROOT,
        data_dir=data_dir,
        executable=Path(sys.executable),
    )
    shutil.copy2(ROOT / "config.yaml", result.config_file)
    shutil.copytree(ROOT / "knowledge-base", result.knowledge_dir)
    result.logs_dir.mkdir(parents=True, exist_ok=True)
    return result


def _pump_until(app, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_refresh_does_not_block_the_ui_or_duplicate_slow_device_queries(
    app, paths, monkeypatch
):
    import sounddevice

    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def slow_query_devices():
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        release.wait(timeout=1.0)
        return []

    monkeypatch.setattr(sounddevice, "query_devices", slow_query_devices)
    window = _SettingsWindow(paths=paths)
    try:
        began = time.perf_counter()
        for _ in range(25):
            window.refresh()
        elapsed = time.perf_counter() - began

        assert elapsed < 0.05
        assert started.wait(timeout=1.0)
        with calls_lock:
            assert calls == 1
    finally:
        release.set()
        _pump_until(app, lambda: not getattr(window, "_refresh_in_progress", False))
        window.close()


def test_diagnostics_is_single_flight_even_when_repeated_from_help(
    app, paths, monkeypatch
):
    import overlay_webview

    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def slow_diagnostics(_paths):
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        release.wait(timeout=1.0)
        return {"ok": True, "checks": []}

    monkeypatch.setattr(overlay_webview, "run_runtime_diagnostics", slow_diagnostics)
    window = _SettingsWindow(paths=paths)
    try:
        window._run_doctor()
        assert started.wait(timeout=1.0)
        for _ in range(100):
            window._show_aux_page(4)
        with calls_lock:
            assert calls == 1
    finally:
        release.set()
        _pump_until(app, lambda: not getattr(window, "_doctor_in_progress", False))
        window.close()


@pytest.mark.parametrize(
    ("method_name", "callback_name"),
    (("_copy_text", "on_copy_text"), ("_repaste_text", "on_repaste_text")),
)
def test_history_delivery_actions_never_wait_on_the_ui_thread(
    app, paths, method_name, callback_name
):
    started = threading.Event()
    release = threading.Event()

    def slow_delivery(_text):
        started.set()
        release.wait(timeout=1.0)
        return "clipboard_verified_only"

    kwargs = {callback_name: slow_delivery}
    window = _SettingsWindow(paths=paths, **kwargs)
    try:
        began = time.perf_counter()
        getattr(window, method_name)("不会丢失的文字")
        elapsed = time.perf_counter() - began

        assert elapsed < 0.05
        assert started.wait(timeout=1.0)
    finally:
        release.set()
        _pump_until(
            app,
            lambda: not getattr(window, "_history_action_in_progress", False),
        )
        window.close()


def test_deleting_recovery_audio_never_waits_on_the_ui_thread(
    app, paths, monkeypatch
):
    started = threading.Event()
    release = threading.Event()

    def slow_delete(_session_id):
        started.set()
        release.wait(timeout=1.0)
        return True

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    window = _SettingsWindow(paths=paths, on_delete_recovery=slow_delete)
    window.recovery_combo.addItem("可恢复录音", "session-1")
    try:
        began = time.perf_counter()
        window._delete_recovery()
        elapsed = time.perf_counter() - began

        assert elapsed < 0.05
        assert started.wait(timeout=1.0)
    finally:
        release.set()
        _pump_until(
            app,
            lambda: not getattr(window, "_recovery_action_in_progress", False),
        )
        window.close()


def test_history_cards_are_rendered_in_bounded_event_loop_batches(app, paths):
    window = _SettingsWindow(paths=paths)
    window._history_rows = [
        {
            "timestamp": "2026-08-15T12:00:00",
            "clean_text": f"第 {index} 条听写",
            "output_status": "clipboard_verified_only",
        }
        for index in range(80)
    ]
    try:
        window._render_history()

        assert window.history_list.count() == 8
        assert _pump_until(app, lambda: window.history_list.count() == 80)
    finally:
        window.close()


def test_history_reader_ignores_valid_json_that_is_not_a_history_record(app, paths):
    paths.history_file.write_text(
        '[]\n"not a record"\n{"clean_text": "保留这条"}\n',
        encoding="utf-8",
    )
    window = _SettingsWindow(paths=paths)
    try:
        rows = window._read_history_rows()
        assert len(rows) == 1
        assert rows[0]["clean_text"] == "保留这条"
        assert len(rows[0]["_entry_id"]) == 64
    finally:
        window.close()


def test_deleting_one_history_entry_never_waits_on_the_ui_thread(
    app, paths, monkeypatch
):
    started = threading.Event()
    release = threading.Event()

    def slow_delete(entry_id):
        assert entry_id == "entry-1"
        started.set()
        release.wait(timeout=1.0)
        return True

    window = _SettingsWindow(paths=paths, on_delete_history=slow_delete)
    try:
        began = time.perf_counter()
        window._delete_history_entry("entry-1")
        elapsed = time.perf_counter() - began

        assert elapsed < 0.05
        assert started.wait(timeout=1.0)
    finally:
        release.set()
        _pump_until(
            app,
            lambda: not getattr(window, "_history_action_in_progress", False),
        )
        window.close()


def test_single_history_delete_does_not_show_a_blocking_confirmation(
    app, paths, monkeypatch
):
    confirmation_calls = []
    deleted = threading.Event()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: confirmation_calls.append(True),
    )

    def delete(_entry_id):
        deleted.set()
        return {"line": '{"clean_text":"可撤销"}', "index": 0}

    window = _SettingsWindow(paths=paths, on_delete_history=delete)
    try:
        window.show()
        app.processEvents()
        window._delete_history_entry("entry-1")

        assert deleted.wait(timeout=1.0)
        assert confirmation_calls == []
        assert _pump_until(app, lambda: not window.undo_history_button.isHidden())
    finally:
        window.close()


def test_show_settings_restores_a_minimized_window_before_raising_it():
    calls = []

    class FakeSettings:
        def refresh(self):
            calls.append("refresh")

        def isMinimized(self):
            return True

        def showNormal(self):
            calls.append("showNormal")

        def show(self):
            calls.append("show")

        def raise_(self):
            calls.append("raise")

        def activateWindow(self):
            calls.append("activate")

    overlay = object.__new__(OverlayWindow)
    overlay._settings_window = FakeSettings()

    overlay._show_settings()

    assert calls == ["refresh", "showNormal", "raise", "activate"]


def test_trial_button_dispatches_a_real_controller_action(app, paths):
    class FakeController:
        def __init__(self):
            self.calls = 0

        def start_trial(self):
            self.calls += 1
            return type(
                "Result",
                (),
                {"accepted": True, "message": "正在聆听", "error_code": ""},
            )()

    controller = FakeController()
    window = _SettingsWindow(paths=paths, controller=controller)
    try:
        window.show()
        app.processEvents()
        window._start_trial()
        app.processEvents()

        assert controller.calls == 1
        assert window.trial_button.text() == "停止并查看"
        assert window.practice_box.hasFocus()
    finally:
        window.close()


def test_settings_navigation_and_trial_binding_survive_one_thousand_actions(
    app,
    paths,
):
    class FastController:
        def __init__(self):
            self.calls = 0

        def start_trial(self):
            self.calls += 1
            return type(
                "Result",
                (),
                {"accepted": True, "message": "", "error_code": ""},
            )()

    controller = FastController()
    window = _SettingsWindow(paths=paths, controller=controller)
    try:
        window.show()
        app.processEvents()
        started = time.perf_counter()
        for index in range(1000):
            window.sidebar.setCurrentRow(index % 4)
            window.trial_button.click()
            app.processEvents()
        elapsed = time.perf_counter() - started

        assert controller.calls == 1000
        assert elapsed < 5.0
    finally:
        window.close()
