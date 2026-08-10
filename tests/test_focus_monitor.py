import sys
import threading
import random
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def test_target_observation_preserves_privacy_safe_focus_evidence():
    from delivery import TargetClassification, TargetObservation, TargetSnapshot

    snapshot = TargetSnapshot(
        101,
        202,
        "uia:GroupControl:runtime:42.8",
        False,
        True,
        True,
        control_type="GroupControl",
        rejection_reason="no_writable_evidence",
        foreground_class="WeChatMainWndForPC",
        focus_window_handle=303,
        caret_window_handle=304,
    )

    observation = TargetObservation.from_snapshot(snapshot, observed_at=12.5)

    assert observation.observed_at == 12.5
    assert observation.window_handle == 101
    assert observation.process_id == 202
    assert observation.control_type == "GroupControl"
    assert observation.foreground_class == "WeChatMainWndForPC"
    assert observation.focus_window_handle == 303
    assert observation.caret_window_handle == 304
    assert observation.classification is TargetClassification.TRANSIENT_UNKNOWN
    assert not hasattr(observation, "window_title")


def test_current_desktop_and_voiceflow_windows_are_positive_paste_blocks():
    from delivery import TargetSnapshot

    desktop = TargetSnapshot(
        101,
        202,
        "desktop",
        False,
        True,
        True,
        foreground_class="Progman",
    )
    own_window = TargetSnapshot(
        303,
        404,
        "settings",
        False,
        True,
        True,
        rejection_reason="own_process",
    )

    assert desktop.paste_decision_from(None).allowed is False
    assert desktop.paste_decision_from(None).reason == "system_surface"
    assert own_window.paste_decision_from(None).allowed is False
    assert own_window.paste_decision_from(None).reason == "own_process"


def test_focus_monitor_owns_inspection_thread_and_bounds_trace():
    from delivery import FocusMonitor, TargetSnapshot

    caller_thread = threading.get_ident()
    inspection_threads = []
    initialized_threads = []
    uninitialized_threads = []
    subscribed_threads = []
    unsubscribed_threads = []
    counter = {"value": 0}

    @contextmanager
    def initializer():
        initialized_threads.append(threading.get_ident())
        try:
            yield
        finally:
            uninitialized_threads.append(threading.get_ident())

    @contextmanager
    def subscriber(_changed):
        subscribed_threads.append(threading.get_ident())
        try:
            yield
        finally:
            unsubscribed_threads.append(threading.get_ident())

    def inspect():
        inspection_threads.append(threading.get_ident())
        counter["value"] += 1
        return TargetSnapshot(
            101,
            202,
            f"editor-{counter['value']}",
            True,
            True,
            True,
        )

    monitor = FocusMonitor(
        inspector=inspect,
        initializer=initializer,
        subscriber=subscriber,
        max_observations=3,
        poll_interval=10.0,
    )
    try:
        monitor.start_tracking()
        for _ in range(5):
            assert monitor.observe(timeout=0.5).snapshot.editable is True
        trace = monitor.trace()
    finally:
        monitor.shutdown()

    assert inspection_threads
    assert all(thread_id != caller_thread for thread_id in inspection_threads)
    assert initialized_threads == [inspection_threads[0]]
    assert uninitialized_threads == [inspection_threads[0]]
    assert subscribed_threads == [inspection_threads[0]]
    assert unsubscribed_threads == [inspection_threads[0]]
    assert len(trace) == 3
    assert trace[-1].snapshot.element_id == "editor-6"


def test_focus_monitor_returns_definite_block_when_inspection_times_out():
    from delivery import FocusMonitor, TargetClassification

    entered = threading.Event()
    release = threading.Event()

    def inspect():
        entered.set()
        release.wait(1.0)
        raise RuntimeError("provider unavailable")

    monitor = FocusMonitor(inspector=inspect, poll_interval=10.0)
    try:
        monitor.start_tracking()
        assert entered.wait(0.5)
        observation = monitor.observe(timeout=0.01)
    finally:
        release.set()
        monitor.shutdown()

    assert observation.classification is TargetClassification.DEFINITELY_BLOCKED
    assert observation.snapshot.known is False


def test_focus_monitor_coalesces_focus_event_bursts():
    from delivery import FocusMonitor

    monitor = FocusMonitor(inspector=lambda: None)
    for _ in range(1000):
        monitor._notify_focus_changed()

    assert monitor._requests.qsize() == 1


def test_output_handler_tracks_focus_on_start_and_stops_after_delivery(tmp_path):
    from delivery import TargetObservation, TargetSnapshot
    from output_handler import OutputHandler

    snapshot = TargetSnapshot(101, 202, "editor", True, True, True)
    observation = TargetObservation.from_snapshot(snapshot)

    class FakeMonitor:
        def __init__(self):
            self.started = 0
            self.observed = 0
            self.stopped = 0

        def start_tracking(self):
            self.started += 1
            return observation

        def observe(self):
            self.observed += 1
            return observation

        def stop_tracking(self):
            self.stopped += 1

        def shutdown(self):
            pass

    monitor = FakeMonitor()
    handler = OutputHandler(
        base_dir=tmp_path,
        focus_monitor=monitor,
    )
    handler._coordinator.clipboard._copy = lambda _text: None
    handler._coordinator.clipboard._paste = lambda: "焦点线程交付"
    handler._coordinator.dispatch_paste = lambda: True

    start = handler.capture_target()
    result = handler.deliver(
        "焦点线程交付",
        start_target=start,
        session_id="focus-monitor-delivery",
    )

    assert result.paste_dispatched is True
    assert monitor.started == 1
    assert monitor.observed == 1
    assert monitor.stopped == 1


def test_ten_thousand_focus_traces_only_block_positive_failures():
    from delivery import TargetSnapshot

    rng = random.Random(260811)
    controls = ("EditControl", "GroupControl", "DocumentControl", "ButtonControl")
    for index in range(10_000):
        mode = rng.randrange(5)
        start = TargetSnapshot(
            rng.randrange(1, 5000),
            rng.randrange(1, 5000),
            f"start-{index}",
            rng.choice((True, False)),
            True,
            True,
        )
        if mode == 0:
            stop = TargetSnapshot(None, None, "", False, False, False)
            expected = False
        elif mode == 1:
            stop = TargetSnapshot(101, 202, "elevated", True, False, True)
            expected = False
        elif mode == 2:
            stop = TargetSnapshot(
                101,
                202,
                "desktop",
                False,
                True,
                True,
                foreground_class="WorkerW",
            )
            expected = False
        else:
            control = rng.choice(controls)
            stop = TargetSnapshot(
                rng.randrange(1, 5000),
                rng.randrange(1, 5000),
                f"stop-{index}",
                control == "EditControl",
                True,
                True,
                control_type=control,
                rejection_reason=(
                    "" if control == "EditControl" else "no_writable_evidence"
                ),
            )
            expected = True

        assert stop.paste_decision_from(start).allowed is expected
