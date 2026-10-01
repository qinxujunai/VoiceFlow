"""Active recording and recovery must survive a competing data-clear request."""

import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from main import VoiceInputSystem
from recording_state import RecordingState, RecordingStateMachine


def _app():
    return SimpleNamespace(
        _recording_state=RecordingStateMachine(),
        history=SimpleNamespace(clear=Mock(return_value=2)),
        _recovery_store=SimpleNamespace(clear_all=Mock(return_value=["session"])),
    )


@pytest.mark.parametrize("phase", ["arming", "recording", "finalizing", "delivering", "canceling"])
def test_clear_rejects_recording_without_touching_history_or_audio(phase):
    app = _app()
    app._recording_state.claim_start()
    if phase != "arming":
        app._recording_state.mark_recording()
    if phase in {"finalizing", "delivering"}:
        app._recording_state.claim_stop()
    if phase == "delivering":
        app._recording_state.mark_delivering()
    if phase == "canceling":
        app._recording_state.claim_cancel()
    with pytest.raises(RuntimeError):
        VoiceInputSystem._clear_local_dictation_data(app)
    app.history.clear.assert_not_called()
    app._recovery_store.clear_all.assert_not_called()


def test_cancel_failure_does_not_expose_active_audio_as_idle():
    app = _app()
    app._recording_state.claim_start()
    app._stop_streaming = Mock()
    app.controller = SimpleNamespace(mark_degraded=Mock())
    app.overlay = SimpleNamespace(show_error=Mock())
    app.session = SimpleNamespace(cancel=Mock(side_effect=OSError("device failed")))
    with pytest.raises(OSError):
        VoiceInputSystem._on_record_cancel(app)
    assert app._recording_state.current is RecordingState.ERROR
    app.controller.mark_degraded.assert_called_once()
    app.overlay.show_error.assert_called_once()
    with pytest.raises(RuntimeError):
        VoiceInputSystem._clear_local_dictation_data(app)
    app._recovery_store.clear_all.assert_not_called()


def test_clear_reserves_idle_against_recording_and_recovery_until_finished():
    app = _app()
    entered, finish = threading.Event(), threading.Event()

    def clear():
        entered.set()
        assert finish.wait(3)
        return 2

    app.history.clear.side_effect = clear
    thread = threading.Thread(target=lambda: VoiceInputSystem._clear_local_dictation_data(app))
    thread.start()
    try:
        assert entered.wait(3)
        assert not app._recording_state.claim_start()
        assert VoiceInputSystem._recover_session(app, "session")["ok"] is False
    finally:
        finish.set()
        thread.join(3)
    assert not thread.is_alive()
    assert app._recording_state.current is RecordingState.IDLE


def test_recovery_excludes_clear_and_releases_reservation_after_failure():
    app = _app()

    def recover(_):
        with pytest.raises(RuntimeError):
            VoiceInputSystem._clear_local_dictation_data(app)
        assert not app._recording_state.claim_start()
        raise OSError("read failed")

    app._recover_idle_session = recover
    with pytest.raises(OSError):
        VoiceInputSystem._recover_session(app, "session")
    assert app._recording_state.claim_start()
    app.history.clear.assert_not_called()


def test_failed_clear_releases_reservation_but_never_revives_shutdown():
    app = _app()
    app.history.clear.side_effect = OSError("write failed")
    with pytest.raises(OSError):
        VoiceInputSystem._clear_local_dictation_data(app)
    assert app._recording_state.current is RecordingState.IDLE
    with app._recording_state.idle_operation() as claimed:
        assert claimed
        app._recording_state.shutdown()
    assert app._recording_state.current is RecordingState.SHUTDOWN
