"""
Background scheduling for realtime text correction.
"""

from __future__ import annotations

import threading
import time

from correction_engine import CorrectionRequest


class RealtimeCorrectionScheduler:
    def __init__(
        self,
        engine,
        terms=None,
        min_interval_seconds=1.2,
        clock=None,
        run_async=True,
    ):
        self.engine = engine
        self.terms = list(terms or [])
        self.min_interval_seconds = min_interval_seconds
        self.clock = clock or time.time
        self.run_async = run_async
        self._lock = threading.Lock()
        self._request_id = 0
        self._active_generation = 0
        self._last_request_at = None
        self._thread = None

    def invalidate(self, generation):
        with self._lock:
            self._active_generation = generation
            self._request_id += 1

    def request_correction(self, text, generation, on_result, stable_text=""):
        text = (text or "").strip()
        if not text:
            return False

        now = self.clock()
        with self._lock:
            if (
                self._last_request_at is not None
                and now - self._last_request_at < self.min_interval_seconds
            ):
                return False
            self._last_request_at = now
            self._active_generation = generation
            self._request_id += 1
            request_id = self._request_id

        request = CorrectionRequest(text=text, stable_text=stable_text or "", terms=self.terms)

        if not self.run_async:
            corrected = self.engine.correct(request)
            self._publish(request_id, generation, text, corrected, on_result)
            return True

        thread = threading.Thread(
            target=self._run,
            args=(request_id, generation, request, on_result),
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return True

    def _run(self, request_id, generation, request, on_result):
        try:
            corrected = self.engine.correct(request)
        except Exception:
            corrected = request.text
        self._publish(request_id, generation, request.text, corrected, on_result)

    def _publish(self, request_id, generation, original, corrected, on_result):
        corrected = (corrected or original).strip()
        if not corrected or corrected == original:
            return
        with self._lock:
            if request_id != self._request_id or generation != self._active_generation:
                return
        on_result(corrected, generation)

    def wait(self, timeout=None):
        thread = self._thread
        if thread:
            thread.join(timeout=timeout)
