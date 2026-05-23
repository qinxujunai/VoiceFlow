"""
Small lifecycle wrapper around AudioCapture.
"""

import time
from dataclasses import dataclass


@dataclass
class RecordingResult:
    audio_data: object
    duration: float


class RecordingSession:
    def __init__(self, audio, clock=None):
        self.audio = audio
        self.clock = clock or time.time
        self.started_at = None

    @property
    def is_active(self):
        return self.started_at is not None and self.audio.is_recording

    def start(self):
        if self.is_active:
            return
        self.audio.start_recording()
        self.started_at = self.clock()

    def stop(self):
        started_at = self.started_at or self.clock()
        audio_data = self.audio.stop_recording()
        duration = max(0.0, self.clock() - started_at)
        self.started_at = None
        return RecordingResult(audio_data=audio_data, duration=duration)

    def cancel(self):
        if self.audio.is_recording:
            self.audio.cancel_recording()
        self.started_at = None
