from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _manager(tmp_path, callback, can_toggle=None):
    from hotkey_manager import HotkeyManager

    config = tmp_path / "config.yaml"
    config.write_text(
        "hotkeys:\n  push_to_talk: [f2]\n  cancel: escape\n",
        encoding="utf-8",
    )
    return HotkeyManager(
        config_path=str(config),
        callbacks={
            "on_record_toggle": callback,
            "can_record_toggle": can_toggle or (lambda: True),
        },
    )


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    return True


def test_a_released_key_can_toggle_again_inside_the_old_500ms_window(tmp_path):
    calls = []
    manager = _manager(tmp_path, lambda triggered_at: calls.append(triggered_at))
    try:
        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        time.sleep(0.12)
        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)

        assert _wait_until(lambda: len(calls) == 2)
        assert calls[1] > calls[0]
    finally:
        manager.stop()


def test_held_key_repeat_is_ignored_until_key_up(tmp_path):
    calls = []
    manager = _manager(tmp_path, lambda triggered_at: calls.append(triggered_at))
    try:
        for _ in range(20):
            manager._handle_trigger("f2", pressed=True)
        assert _wait_until(lambda: len(calls) == 1)

        manager._handle_trigger("f2", pressed=False)
        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        assert _wait_until(lambda: len(calls) == 2)
    finally:
        manager.stop()


def test_toggle_callbacks_are_serialized_in_press_order(tmp_path):
    first_started = threading.Event()
    release_first = threading.Event()
    events = []

    def callback(_triggered_at):
        index = len([event for event in events if event.endswith("start")]) + 1
        events.append(f"{index}-start")
        if index == 1:
            first_started.set()
            release_first.wait(timeout=1.0)
        events.append(f"{index}-end")

    manager = _manager(tmp_path, callback)
    try:
        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        assert first_started.wait(timeout=1.0)

        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        time.sleep(0.05)
        assert events == ["1-start"]

        release_first.set()
        assert _wait_until(lambda: len(events) == 4)
        assert events == ["1-start", "1-end", "2-start", "2-end"]
    finally:
        release_first.set()
        manager.stop()


def test_different_trigger_sources_do_not_debounce_each_other(tmp_path):
    calls = []
    manager = _manager(tmp_path, lambda triggered_at: calls.append(triggered_at))
    try:
        manager._handle_trigger("f2", pressed=True)
        assert _wait_until(lambda: len(calls) == 1)
        manager._handle_trigger("xbutton1", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        manager._handle_trigger("xbutton1", pressed=False)

        assert _wait_until(lambda: len(calls) == 2)
    finally:
        manager.stop()


def test_fast_taps_are_bounded_instead_of_replayed_after_busy_work(tmp_path):
    first_started = threading.Event()
    release_first = threading.Event()
    calls = []

    def callback(triggered_at):
        calls.append(triggered_at)
        if len(calls) == 1:
            first_started.set()
            release_first.wait(timeout=1.0)

    manager = _manager(tmp_path, callback)
    try:
        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        assert first_started.wait(timeout=1.0)

        for _ in range(10_000):
            manager._handle_trigger("f2", pressed=True)
            manager._handle_trigger("f2", pressed=False)

        release_first.set()
        assert _wait_until(lambda: manager._intent_queue.unfinished_tasks == 0)
        assert 1 <= len(calls) <= 2
    finally:
        release_first.set()
        manager.stop()


def test_two_taps_during_stop_cannot_restart_after_finalization(tmp_path):
    state = "recording"
    stop_started = threading.Event()
    release_stop = threading.Event()
    calls = []

    def can_toggle():
        return state in {"idle", "recording"}

    def callback(_triggered_at):
        nonlocal state
        calls.append(state)
        if state == "recording":
            state = "finalizing"
            stop_started.set()
            release_stop.wait(timeout=1.0)
            state = "idle"
        else:
            state = "recording"

    manager = _manager(tmp_path, callback, can_toggle=can_toggle)
    try:
        manager._trigger_ptt()
        assert stop_started.wait(timeout=1.0)

        manager._trigger_ptt()
        manager._trigger_ptt()
        release_stop.set()
        assert _wait_until(lambda: manager._intent_queue.unfinished_tasks == 0)
        assert calls == ["recording"]
        assert state == "idle"
    finally:
        release_stop.set()
        manager.stop()


def test_finalizing_state_rejects_taps_before_they_enter_the_queue(tmp_path):
    calls = []
    can_toggle = threading.Event()
    can_toggle.set()
    manager = _manager(
        tmp_path,
        lambda triggered_at: calls.append(triggered_at),
        can_toggle=can_toggle.is_set,
    )
    try:
        manager._trigger_ptt()
        assert _wait_until(lambda: len(calls) == 1)

        can_toggle.clear()
        for _ in range(100):
            assert not manager._handle_trigger("f2", pressed=True)
            manager._handle_trigger("f2", pressed=False)

        time.sleep(0.05)
        assert len(calls) == 1
        assert manager._intent_queue.unfinished_tasks == 0
    finally:
        manager.stop()


def test_stop_does_not_block_when_the_bounded_queue_is_full(tmp_path):
    callback_started = threading.Event()
    release_callback = threading.Event()

    def callback(_triggered_at):
        callback_started.set()
        release_callback.wait(timeout=1.0)

    manager = _manager(tmp_path, callback)
    manager._trigger_ptt()
    assert callback_started.wait(timeout=1.0)
    manager._trigger_ptt()
    manager._trigger_ptt()

    stopped = threading.Event()
    worker = threading.Thread(target=lambda: (manager.stop(), stopped.set()))
    worker.start()
    try:
        assert stopped.wait(timeout=0.75)
    finally:
        release_callback.set()
        worker.join(timeout=1.0)
