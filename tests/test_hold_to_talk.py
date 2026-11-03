from __future__ import annotations

import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _manager(tmp_path, events, recording, mode=None):
    from hotkey_manager import HotkeyManager

    config = tmp_path / "config.yaml"
    text = "hotkeys:\n  push_to_talk: [f2, xbutton1]\n  cancel: escape\n"
    if mode:
        text += f"  trigger_mode: {mode}\n"
    config.write_text(text, encoding="utf-8")
    manager = HotkeyManager(
        config_path=str(config),
        callbacks={
            "on_record_toggle": lambda triggered_at: events.append(("toggle", triggered_at)),
            "on_record_release": lambda pressed_at, released_at: events.append(
                ("release", pressed_at, released_at)
            ),
            "can_record_toggle": lambda: True,
            "is_recording": lambda: recording[0],
        },
    )
    manager.hold_to_talk_s = 0.05
    return manager


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    return True


def test_default_trigger_mode_is_hold_or_tap():
    from hotkey_manager import HotkeyManager

    assert HotkeyManager.HOLD_TO_TALK_S == 0.3
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "trigger_mode: auto" in config


def test_holding_a_key_stops_the_recording_it_started_when_released(tmp_path):
    events, recording = [], [False]
    manager = _manager(tmp_path, events, recording)
    try:
        for source in ("f2", "xbutton1"):
            events.clear()
            recording[0] = False
            manager._handle_trigger(source, pressed=True)
            assert _wait_until(lambda: len(events) == 1)
            recording[0] = True
            time.sleep(0.08)
            manager._handle_trigger(source, pressed=False)
            assert _wait_until(lambda: len(events) == 2)
            (toggle, pressed_at), (release, release_pressed_at, released_at) = events
            assert (toggle, release) == ("toggle", "release")
            assert release_pressed_at == pressed_at
            assert released_at > pressed_at
    finally:
        manager.stop()


def test_a_quick_tap_keeps_recording_until_the_next_tap(tmp_path):
    events, recording = [], [False]
    manager = _manager(tmp_path, events, recording)
    manager.hold_to_talk_s = 0.3
    try:
        manager._handle_trigger("f2", pressed=True)
        manager._handle_trigger("f2", pressed=False)
        assert _wait_until(lambda: len(events) == 1)
        time.sleep(0.05)
        assert [event[0] for event in events] == ["toggle"]
    finally:
        manager.stop()


def test_holding_the_key_that_stops_a_recording_sends_no_second_stop(tmp_path):
    events, recording = [], [True]
    manager = _manager(tmp_path, events, recording)
    try:
        manager._handle_trigger("f2", pressed=True)
        assert _wait_until(lambda: len(events) == 1)
        recording[0] = False
        time.sleep(0.08)
        manager._handle_trigger("f2", pressed=False)
        time.sleep(0.05)
        assert [event[0] for event in events] == ["toggle"]
    finally:
        manager.stop()


def test_toggle_mode_never_stops_on_release(tmp_path):
    events, recording = [], [False]
    manager = _manager(tmp_path, events, recording, mode="toggle")
    try:
        manager._handle_trigger("f2", pressed=True)
        assert _wait_until(lambda: len(events) == 1)
        recording[0] = True
        time.sleep(0.08)
        manager._handle_trigger("f2", pressed=False)
        time.sleep(0.05)
        assert [event[0] for event in events] == ["toggle"]
    finally:
        manager.stop()


def test_controller_release_waits_for_the_start_instead_of_answering_please_wait():
    from app_controller import AppController

    started = threading.Event()
    finish_start = threading.Event()
    calls, messages = [], []

    def record(triggered_at=None):
        calls.append(("record", triggered_at))
        started.set()
        finish_start.wait(1.0)
        controller.mark_recording()

    controller = AppController(
        on_record_toggle=record,
        on_record_release=lambda pressed_at, released_at: calls.append(("release", pressed_at, released_at)),
        on_status=messages.append,
    )
    controller.mark_ready()
    assert controller.toggle_recording(triggered_at=1.0, source="f2").accepted
    assert started.wait(1.0)

    releaser = threading.Thread(target=lambda: controller.release_recording(1.0, 1.4))
    releaser.start()
    time.sleep(0.05)
    finish_start.set()
    releaser.join(2.0)

    assert _wait_until(lambda: len(calls) == 2)
    assert calls == [("record", 1.0), ("release", 1.0, 1.4)]
    assert "稍等一下" not in messages


def test_release_stops_only_the_recording_that_press_started():
    import main as vf
    from recording_state import RecordingState

    stops = []
    system = object.__new__(vf.VoiceInputSystem)
    system._recording_state = type("State", (), {"current": RecordingState.RECORDING})()
    system._recording_trigger_at = 5.0
    system._on_record_stop = stops.append

    system._on_record_release(4.0, 4.5)
    assert stops == []
    system._on_record_release(5.0, 5.6)
    assert stops == [5.6]
    system._recording_state.current = RecordingState.IDLE
    system._on_record_release(5.0, 5.9)
    assert stops == [5.6]
