"""Thread-safe recording lifecycle state machine."""

from __future__ import annotations

import threading
from enum import Enum


class RecordingState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    SHUTDOWN = "shutdown"


class RecordingStateMachine:
    def __init__(self):
        self._state = RecordingState.IDLE
        self._lock = threading.RLock()
        self.completed_cycles = 0

    @property
    def current(self) -> RecordingState:
        with self._lock:
            return self._state

    def claim_start(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.IDLE:
                return False
            self._state = RecordingState.RECORDING
            return True

    def abort_start(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.RECORDING:
                return False
            self._state = RecordingState.IDLE
            return True

    def claim_stop(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.RECORDING:
                return False
            self._state = RecordingState.PROCESSING
            return True

    def complete_processing(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.PROCESSING:
                return False
            self._state = RecordingState.IDLE
            self.completed_cycles += 1
            return True

    def claim_cancel(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.RECORDING:
                return False
            self._state = RecordingState.IDLE
            return True

    def shutdown(self) -> RecordingState:
        with self._lock:
            previous = self._state
            self._state = RecordingState.SHUTDOWN
            return previous
