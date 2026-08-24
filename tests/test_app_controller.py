from __future__ import annotations

import sys
import threading
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from app_controller import ActionResult, AppController, RuntimePhase  # noqa: E402


def test_starting_hotkey_reports_preparing_without_touching_recording_backend():
    calls = []
    messages = []
    controller = AppController(
        on_record_toggle=lambda triggered_at=None: calls.append(triggered_at),
        on_status=messages.append,
    )

    result = controller.toggle_recording(triggered_at=12.5, source="f2")

    assert result == ActionResult(False, "正在准备", "runtime_starting")
    assert calls == []
    assert messages == ["正在准备"]


def test_ready_controller_dispatches_recording_and_trial_through_stable_actions():
    recording = []
    trials = []
    recording_done = threading.Event()
    trial_done = threading.Event()

    def record(triggered_at=None):
        recording.append(triggered_at)
        recording_done.set()

    def trial():
        trials.append("trial")
        trial_done.set()

    controller = AppController(
        on_record_toggle=record,
        on_trial_toggle=trial,
    )
    controller.mark_ready()

    record_result = controller.toggle_recording(triggered_at=7.25, source="f2")
    assert record_result.accepted is True
    assert recording_done.wait(timeout=1.0)

    trial_result = controller.start_trial()

    assert trial_result.accepted is True
    assert trial_done.wait(timeout=1.0)
    assert recording == [7.25]
    assert trials == ["trial"]
    assert controller.phase is RuntimePhase.READY


def test_rapid_record_taps_do_not_queue_a_ghost_toggle():
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def slow_toggle(_triggered_at=None):
        calls.append("record")
        entered.set()
        release.wait(1.0)

    controller = AppController(on_record_toggle=slow_toggle)
    controller.mark_ready()

    first = controller.toggle_recording()
    assert entered.wait(1.0)
    second = controller.toggle_recording()
    release.set()

    assert first.accepted is True
    assert second.accepted is False
    assert second.error_code == "action_busy"
    assert calls == ["record"]


def test_degraded_controller_never_silently_swallows_recording_intent():
    messages = []
    controller = AppController(on_status=messages.append)
    controller.mark_degraded("模型不可用", error_code="model_unavailable")

    result = controller.toggle_recording(source="f2")

    assert result.accepted is False
    assert result.message == "暂时无法听写"
    assert result.error_code == "model_unavailable"
    assert messages[-1] == "暂时无法听写"


def test_controller_runtime_snapshot_contains_no_transcript_content():
    controller = AppController(build_id="260824.1")
    controller.mark_ready()

    snapshot = controller.runtime_snapshot()

    assert snapshot == {
        "build_id": "260824.1",
        "phase": "ready",
        "hotkeys": "pending",
        "worker": "ready",
        "final_asr": "ready",
        "preview_asr": "ready",
        "last_error_code": "",
        "worker_pid": 0,
        "worker_pids": {},
        "last_heartbeat": 0.0,
    }
    assert "text" not in snapshot
    assert "transcript" not in snapshot


def test_runtime_state_is_atomically_persisted_for_installer_health_checks(tmp_path):
    state_path = tmp_path / "runtime-state.json"
    controller = AppController(
        build_id="260824.2",
        runtime_state_path=state_path,
    )

    controller.mark_hotkeys("ready")
    controller.mark_ready(preview_ready=False)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["build_id"] == "260824.2"
    assert payload["phase"] == "ready"
    assert payload["hotkeys"] == "ready"
    assert payload["preview_asr"] == "unavailable"
    assert not list(tmp_path.glob("*.tmp"))
