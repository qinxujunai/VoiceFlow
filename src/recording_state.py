"""Thread-safe recording lifecycle state machine."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from enum import Enum


class RecordingState(str, Enum):
    IDLE = "idle"
    MAINTENANCE = "maintenance"
    CANCELING = "canceling"
    ARMING = "arming"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    PROCESSING = "finalizing"
    DELIVERING = "delivering"
    COMPLETE = "complete"
    RECOVERABLE = "recoverable"
    ERROR = "error"
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
            self._state = RecordingState.ARMING
            return True

    @contextmanager
    def idle_operation(self):
        """Reserve idle atomically so recording and local data work cannot overlap."""
        with self._lock:
            claimed = self._state is RecordingState.IDLE
            if claimed:
                self._state = RecordingState.MAINTENANCE
        try:
            yield claimed
        finally:
            if claimed:
                with self._lock:
                    if self._state is RecordingState.MAINTENANCE:
                        self._state = RecordingState.IDLE

    def mark_recording(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.ARMING:
                return False
            self._state = RecordingState.RECORDING
            return True

    def abort_start(self) -> bool:
        with self._lock:
            if self._state not in {RecordingState.ARMING, RecordingState.RECORDING}:
                return False
            self._state = RecordingState.IDLE
            return True

    def claim_stop(self) -> bool:
        with self._lock:
            if self._state not in {RecordingState.ARMING, RecordingState.RECORDING}:
                return False
            self._state = RecordingState.FINALIZING
            return True

    def mark_delivering(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.FINALIZING:
                return False
            self._state = RecordingState.DELIVERING
            return True

    def mark_complete(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.DELIVERING:
                return False
            self._state = RecordingState.COMPLETE
            return True

    def mark_recoverable(self) -> bool:
        with self._lock:
            if self._state not in {
                RecordingState.ARMING,
                RecordingState.RECORDING,
                RecordingState.FINALIZING,
                RecordingState.DELIVERING,
                RecordingState.ERROR,
            }:
                return False
            self._state = RecordingState.RECOVERABLE
            return True

    def mark_error(self) -> bool:
        with self._lock:
            if self._state in {RecordingState.IDLE, RecordingState.SHUTDOWN}:
                return False
            self._state = RecordingState.ERROR
            return True

    def acknowledge_recovery(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.RECOVERABLE:
                return False
            self._state = RecordingState.IDLE
            return True

    def complete_processing(self) -> bool:
        with self._lock:
            if self._state not in {
                RecordingState.FINALIZING,
                RecordingState.DELIVERING,
                RecordingState.COMPLETE,
                RecordingState.ERROR,
            }:
                return False
            self._state = RecordingState.IDLE
            self.completed_cycles += 1
            return True

    def claim_cancel(self) -> bool:
        with self._lock:
            if self._state not in {RecordingState.ARMING, RecordingState.RECORDING}:
                return False
            self._state = RecordingState.CANCELING
            return True

    def complete_cancel(self) -> bool:
        with self._lock:
            if self._state is not RecordingState.CANCELING:
                return False
            self._state = RecordingState.IDLE
            return True

    def shutdown(self) -> RecordingState:
        with self._lock:
            previous = self._state
            self._state = RecordingState.SHUTDOWN
            return previous
