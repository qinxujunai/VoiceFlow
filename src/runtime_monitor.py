"""Small privacy-safe runtime health detectors."""

from __future__ import annotations

import threading


class UiStallDetector:
    def __init__(self, *, threshold_ms=50.0, initial_time=0.0):
        self.threshold_seconds = max(0.001, float(threshold_ms) / 1000.0)
        self._last_tick = float(initial_time)
        self._reported = False
        self._lock = threading.Lock()

    def tick(self, now):
        with self._lock:
            self._last_tick = float(now)
            self._reported = False

    def poll(self, now):
        with self._lock:
            elapsed = float(now) - self._last_tick
            if elapsed <= self.threshold_seconds or self._reported:
                return None
            self._reported = True
        return round(elapsed * 1000.0, 3)
