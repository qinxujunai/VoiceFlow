from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_processing_rejects_start_stop_and_cancel_until_completed():
    from recording_state import RecordingState, RecordingStateMachine

    state = RecordingStateMachine()

    assert state.claim_start() is True
    assert state.claim_stop() is True
    assert state.current is RecordingState.PROCESSING
    assert state.claim_start() is False
    assert state.claim_stop() is False
    assert state.claim_cancel() is False
    assert state.complete_processing() is True
    assert state.current is RecordingState.IDLE


def test_rapid_alternating_triggers_complete_500_cycles_without_drift():
    from recording_state import RecordingState, RecordingStateMachine

    state = RecordingStateMachine()

    for _ in range(500):
        assert state.claim_start() is True
        assert state.claim_start() is False
        assert state.claim_stop() is True
        assert state.claim_stop() is False
        assert state.complete_processing() is True

    assert state.current is RecordingState.IDLE
    assert state.completed_cycles == 500


def test_cancel_returns_recording_to_idle_without_completed_cycle():
    from recording_state import RecordingState, RecordingStateMachine

    state = RecordingStateMachine()

    assert state.claim_start() is True
    assert state.claim_cancel() is True

    assert state.current is RecordingState.IDLE
    assert state.completed_cycles == 0
