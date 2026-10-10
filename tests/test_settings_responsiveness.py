from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from overlay_webview import _SettingsWindow  # noqa: E402
from overlay_webview import OverlayWindow  # noqa: E402
from qt_compat import QAction, QApplication, QMessageBox, QPushButton  # noqa: E402
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


def test_settings_readiness_follows_workers_instead_of_model_file_presence(app, paths):
    from app_controller import AppController

    controller = AppController()
    window = _SettingsWindow(paths=paths, controller=controller)
    try:
        window._sync_runtime_status(force=True)
        assert window.status_badge.text() == "正在准备"
        assert window.home_model.text() == "本地识别 · 正在准备"
        controller.mark_ready()
        window._sync_runtime_status()
        assert window.status_badge.text() == "就绪"
        controller.mark_degraded("fixture failure")
        window._sync_runtime_status()
        assert window.status_badge.text() == "需要处理"
        assert window.home_model.text() == "本地识别 · 需要检查"
    finally:
        window.close()


def test_tray_quit_keeps_qt_responsive_and_waits_for_cleanup_once(app, paths, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    completed = []
    ui_thread = threading.get_ident()

    def cleanup():
        calls.append(threading.get_ident())
        entered.set()
        release.wait(1)

    monkeypatch.setattr(app, "quit", lambda: completed.append(threading.get_ident()))
    overlay = OverlayWindow(paths)
    overlay._on_quit = cleanup
    began = time.perf_counter()
    try:
        overlay.quit()
        elapsed = time.perf_counter() - began
        assert elapsed < .05
        assert entered.wait(.5)
        overlay.quit()
        app.processEvents()
        assert completed == []
        assert len(calls) == 1 and calls[0] != ui_thread
    finally:
        release.set()
        _pump_until(app, lambda: bool(completed))
    assert completed == [ui_thread]


def test_failed_quit_keeps_tray_available_and_reports_failure(app, paths, monkeypatch):
    completed, errors, visible = [], [], []
    monkeypatch.setattr(app, "quit", lambda: completed.append(True))
    overlay = OverlayWindow(paths)
    overlay._tray = SimpleNamespace(
        setVisible=lambda value: visible.append(value),
        toolTip=lambda: "VoiceFlow", setToolTip=lambda _value: None,
    )
    overlay.show_error = errors.append

    def fail():
        raise OSError("fixture cleanup failure")

    overlay._on_quit = fail
    escaped = None
    try:
        overlay.quit()
    except Exception as error:
        escaped = error

    assert escaped is None
    assert _pump_until(app, lambda: bool(errors))
    assert completed == []
    assert False not in visible


def test_pending_quit_disables_tray_actions_and_failure_restores_previous_state(app, paths):
    release = threading.Event()
    errors = []
    tooltip = {"text": "VoiceFlow · 就绪"}
    overlay = OverlayWindow(paths)
    first, unavailable = QAction("退出"), QAction("不可用的动作")
    unavailable.setEnabled(False)
    overlay._tray_actions = [first, unavailable]
    overlay._tray = SimpleNamespace(
        toolTip=lambda: tooltip["text"],
        setToolTip=lambda value: tooltip.update(text=value),
        setVisible=lambda _value: None,
    )
    overlay.show_error = errors.append

    def fail_after_wait():
        release.wait(1)
        raise OSError("fixture failure")

    overlay._on_quit = fail_after_wait
    try:
        overlay.quit()
        assert not first.isEnabled() and not unavailable.isEnabled()
        assert "正在退出" in tooltip["text"]
    finally:
        release.set()
        _pump_until(app, lambda: bool(errors))
    assert first.isEnabled() and not unavailable.isEnabled()
    assert tooltip["text"] == "VoiceFlow · 就绪"


def test_refresh_does_not_block_the_ui_or_duplicate_slow_cached_device_queries(
    app, paths, monkeypatch
):
    import sounddevice
    from app_controller import AppController

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

    def forbidden_native_query():
        raise AssertionError("settings must not enumerate native audio devices")

    monkeypatch.setattr(sounddevice, "query_devices", forbidden_native_query)
    controller = AppController(on_query_microphones=slow_query_devices)
    window = _SettingsWindow(paths=paths, controller=controller)
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
            window._show_aux_page(3)
        with calls_lock:
            assert calls == 1
    finally:
        release.set()
        _pump_until(app, lambda: not getattr(window, "_doctor_in_progress", False))
        window.close()


@pytest.mark.parametrize(
    ("method_name", "callback_name"),
    (("_copy_text", "on_copy_text"), ("_repaste_text", "on_copy_text")),
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


def test_settings_exposes_no_competing_trial_button(app, paths):
    window = _SettingsWindow(paths=paths)
    try:
        window.show()
        app.processEvents()

        labels = [button.text() for button in window.findChildren(QPushButton)]
        assert "试说一句" not in labels
        assert "试说" not in labels
        assert "停止并查看" not in labels
        assert not hasattr(window, "trial_button")
        assert not hasattr(window, "practice_box")
    finally:
        window.close()


def test_settings_primary_navigation_and_font_are_consistent(app, paths):
    window = _SettingsWindow(paths=paths)
    try:
        assert [
            window.sidebar.item(index).text()
            for index in range(window.sidebar.count())
        ] == ["听写", "词典", "历史"]
        assert window.font().family() == app.font().family()
        assert window.language_combo.font().family() == app.font().family()
        assert window.microphone_combo.font().family() == app.font().family()

        for row, stack_index in ((0, 0), (1, 2), (2, 1)):
            window.sidebar.setCurrentRow(row)
            app.processEvents()
            assert window.stack.currentIndex() == stack_index
    finally:
        window.close()


def test_settings_navigation_survives_one_thousand_actions(
    app,
    paths,
):
    window = _SettingsWindow(paths=paths)
    try:
        window.show()
        app.processEvents()
        started = time.perf_counter()
        for index in range(1000):
            window.sidebar.setCurrentRow(index % 3)
            app.processEvents()
        elapsed = time.perf_counter() - started

        # Keep the guard at 10 ms per navigation; hosted Intel macOS runners
        # have materially lower Qt event-loop throughput than Windows.
        assert elapsed < 10.0
    finally:
        window.close()
