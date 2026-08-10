from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _manager(tmp_path, callback):
    from hotkey_manager import HotkeyManager

    config = tmp_path / "config.yaml"
    config.write_text(
        "hotkeys:\n  push_to_talk: [f2]\n  cancel: escape\n",
        encoding="utf-8",
    )
    return HotkeyManager(
        config_path=str(config),
        callbacks={"on_record_toggle": callback},
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
        manager._handle_trigger("xbutton1", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        manager._handle_trigger("xbutton1", pressed=False)

        assert _wait_until(lambda: len(calls) == 2)
    finally:
        manager.stop()


def test_ten_thousand_fast_taps_are_delivered_once_and_in_order(tmp_path):
    calls = []
    manager = _manager(tmp_path, lambda triggered_at: calls.append(triggered_at))
    try:
        for _ in range(10_000):
            assert manager._handle_trigger("f2", pressed=True)
            assert not manager._handle_trigger("f2", pressed=False)

        assert _wait_until(lambda: len(calls) == 10_000, timeout=5.0)
        assert calls == sorted(calls)
    finally:
        manager.stop()
