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


def test_release_during_press_validation_stops_the_same_recording(tmp_path):
    events, recording = [], [False]
    manager = _manager(tmp_path, events, recording)
    entered, resume = threading.Event(), threading.Event()

    def can_toggle():
        if threading.current_thread().name == "press-validation":
            entered.set()
            resume.wait(2)
        return True

    manager.callbacks["can_record_toggle"] = can_toggle
    press = threading.Thread(name="press-validation", target=manager._handle_trigger, args=("f2", True))
    release = threading.Thread(target=manager._handle_trigger, args=("f2", False))
    try:
        press.start()
        assert entered.wait(1)
        time.sleep(0.08)
        release.start()
        release.join(0.1)
        resume.set()
        press.join(1)
        release.join(1)
        assert _wait_until(lambda: len(events) == 2)
        assert events[0][0] == "toggle"
        assert events[1][0] == "release"
        assert events[1][1] == events[0][1]
    finally:
        resume.set()
        press.join(1)
        if release.ident is not None:
            release.join(1)
        manager.stop()


def test_duplicate_release_during_validation_cannot_turn_a_tap_into_hold(tmp_path):
    events, recording = [], [False]
    manager = _manager(tmp_path, events, recording)
    entered, resume = threading.Event(), threading.Event()

    def can_toggle():
        if threading.current_thread().name == "press-validation":
            entered.set()
            resume.wait(2)
        return True

    manager.callbacks["can_record_toggle"] = can_toggle
    press = threading.Thread(name="press-validation", target=manager._handle_trigger, args=("f2", True))
    try:
        press.start()
        assert entered.wait(1)
        manager._handle_trigger("f2", False)
        time.sleep(0.08)
        manager._handle_trigger("f2", False)
        resume.set()
        press.join(1)
        assert _wait_until(lambda: bool(events))
        time.sleep(0.05)
        assert [event[0] for event in events] == ["toggle"]
    finally:
        resume.set()
        press.join(1)
        manager.stop()


def test_failed_press_validation_does_not_disable_key(tmp_path):
    import pytest

    events, recording = [], [False]
    manager = _manager(tmp_path, events, recording)
    manager.callbacks["can_record_toggle"] = lambda: (_ for _ in ()).throw(RuntimeError("failure"))
    try:
        with pytest.raises(RuntimeError):
            manager._handle_trigger("f2", True)
        manager._handle_trigger("f2", False)
        manager.callbacks["can_record_toggle"] = lambda: True
        assert manager._handle_trigger("f2", True)
        assert _wait_until(lambda: bool(events))
    finally:
        manager.stop()


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


def test_release_during_slow_start_is_not_lost():
    from app_controller import AppController

    started, finish = threading.Event(), threading.Event()
    calls = []

    def record(triggered_at):
        started.set()
        finish.wait(2)
        controller.mark_recording()

    controller = AppController(on_record_toggle=record,
        on_record_release=lambda pressed, released: calls.append((pressed, released)))
    controller.mark_ready()
    assert controller.toggle_recording(1.0).accepted
    assert started.wait(1)
    controller.release_recording(1.0, 1.5)
    finish.set()
    assert _wait_until(lambda: calls == [(1.0, 1.5)])


def test_other_key_release_cannot_replace_the_starting_key():
    from app_controller import AppController

    started, finish = threading.Event(), threading.Event()
    calls = []

    def record(triggered_at):
        started.set()
        finish.wait(2)
        controller.mark_recording()

    controller = AppController(on_record_toggle=record,
        on_record_release=lambda pressed, released: calls.append((pressed, released)))
    controller.mark_ready()
    assert controller.toggle_recording(1.0).accepted
    assert started.wait(1)
    controller.release_recording(1.0, 1.5)
    controller.release_recording(2.0, 2.5)
    finish.set()
    assert _wait_until(lambda: bool(calls))
    time.sleep(0.05)
    assert calls == [(1.0, 1.5)]


def test_a_release_never_waits_for_another_action_and_is_never_dropped():
    from app_controller import AppController, RuntimePhase

    cancel_started, finish_cancel = threading.Event(), threading.Event()
    calls, messages = [], []

    def cancel():
        cancel_started.set()
        finish_cancel.wait(2)

    controller = AppController(
        on_record_toggle=lambda triggered_at: controller.mark_recording(),
        on_record_release=lambda pressed, released: calls.append((pressed, released)),
        on_cancel=cancel,
        on_status=messages.append,
    )
    controller.mark_ready()
    assert controller.toggle_recording(1.0).accepted
    assert _wait_until(lambda: controller.phase is RuntimePhase.RECORDING
                       and not controller._action_in_flight)
    assert controller.cancel_recording().accepted
    assert cancel_started.wait(1)

    began = time.perf_counter()
    assert controller.release_recording(1.0, 1.5).accepted
    assert controller.release_recording(3.0, 3.5).accepted
    assert time.perf_counter() - began < 0.05
    finish_cancel.set()
    # Each release is matched to its own recording later; none is lost or answered with 稍等一下.
    assert _wait_until(lambda: calls == [(1.0, 1.5), (3.0, 3.5)])
    assert "稍等一下" not in messages


def test_a_hold_release_is_delivered_while_another_key_tap_waits(tmp_path):
    from hotkey_manager import HotkeyManager

    events = []
    first_running, finish_first = threading.Event(), threading.Event()

    def toggle(triggered_at):
        events.append(("toggle", triggered_at))
        if not first_running.is_set():
            first_running.set()
            finish_first.wait(1.0)

    config = tmp_path / "config.yaml"
    config.write_text("hotkeys:\n  push_to_talk: [f2, xbutton1]\n  cancel: escape\n", encoding="utf-8")
    manager = HotkeyManager(config_path=str(config), callbacks={
        "on_record_toggle": toggle,
        "on_record_release": lambda pressed_at, released_at: events.append(("release", pressed_at)),
        "can_record_toggle": lambda: True,
        "is_recording": lambda: False,
    })
    manager.hold_to_talk_s = 0.05
    try:
        assert manager._handle_trigger("f2", pressed=True)
        assert first_running.wait(1.0)
        time.sleep(0.08)
        assert manager._handle_trigger("xbutton1", pressed=True)
        assert manager._handle_trigger("f2", pressed=False)
        finish_first.set()
        assert _wait_until(lambda: any(kind == "release" for kind, _value in events))
        assert ("release", events[0][1]) in events
    finally:
        finish_first.set()
        manager.stop()


def test_one_escape_seen_by_both_keyboard_hooks_cancels_once(tmp_path):
    from hotkey_manager import HotkeyManager

    config = tmp_path / "config.yaml"
    config.write_text("hotkeys:\n  push_to_talk: [f2, right_ctrl]\n  cancel: escape\n", encoding="utf-8")
    cancels = []
    manager = HotkeyManager(config_path=str(config), callbacks={"on_record_cancel": lambda: cancels.append(1)})
    try:
        manager._on_cancel()
        manager._on_cancel()
        time.sleep(0.05)
        assert cancels == [1]
        time.sleep(manager.CANCEL_REPEAT_S)
        manager._on_cancel()
        assert _wait_until(lambda: len(cancels) == 2)
    finally:
        manager.stop()


def test_trigger_mode_saves_when_the_hotkeys_line_has_a_comment(tmp_path):
    import yaml
    from settings_store import update_trigger_mode

    config = tmp_path / "config.yaml"
    config.write_text("hotkeys:  # 快捷键\n  push_to_talk: [f2]\n  trigger_mode: auto  # 按住或轻按\n"
                      "engine:  # 识别\n  active: sensevoice\n", encoding="utf-8")
    update_trigger_mode(config, "toggle")
    text = config.read_text(encoding="utf-8")
    assert yaml.safe_load(text)["hotkeys"]["trigger_mode"] == "toggle"
    assert text.count("trigger_mode") == 1
    assert "# 快捷键" in text and "# 按住或轻按" in text and "# 识别" in text
