"""
Small lifecycle wrapper around AudioCapture.
"""

import time
from dataclasses import dataclass


@dataclass
class RecordingResult:
    audio_data: object
    duration: float
    start_sample: int = 0
    total_samples: int = 0


class RecordingSession:
    def __init__(self, audio, clock=None):
        self.audio = audio
        self.clock = clock or time.time
        self.started_at = None
        self.frozen_at = None

    @property
    def is_active(self):
        return self.started_at is not None and self.audio.is_recording

    def start(self):
        if self.is_active:
            return
        self.audio.start_recording()
        self.started_at = self.clock()
        self.frozen_at = None

    def stop(self):
        started_at = self.started_at or self.clock()
        audio_data = self.audio.stop_recording()
        ended_at = self.frozen_at if self.frozen_at is not None else self.clock()
        duration = max(0.0, ended_at - started_at)
        self.started_at = None
        self.frozen_at = None
        return RecordingResult(
            audio_data=audio_data,
            duration=duration,
            start_sample=getattr(self.audio, "last_buffer_start_sample", 0),
            total_samples=getattr(self.audio, "last_total_samples", len(audio_data)),
        )

    def freeze(self):
        """Latch the final sample before slower device teardown begins."""
        if self.started_at is None:
            return 0
        if self.frozen_at is None:
            self.frozen_at = self.clock()
        return self.audio.freeze_recording()

    def cancel(self):
        if self.audio.is_recording:
            self.audio.cancel_recording()
        self.started_at = None
        self.frozen_at = None
