"""Stable action boundary between VoiceFlow's UI and runtime services."""

from __future__ import annotations

import logging
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable
from pathlib import Path


logger = logging.getLogger("voiceflow.controller")


class RuntimePhase(Enum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    ERROR = "error"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    DELIVERING = "delivering"


@dataclass(frozen=True)
class ActionResult:
    accepted: bool
    message: str = ""
    error_code: str = ""


class AppController:
    """Own user actions before any window or tray action is constructed.

    Native audio and recognition callbacks never execute on Qt's main thread.
    The queue is deliberately bounded so rapid taps cannot become future ghost
    recording actions.
    """

    def __init__(
        self,
        *,
        on_record_toggle: Callable | None = None,
        on_trial_toggle: Callable | None = None,
        on_cancel: Callable | None = None,
        on_copy_last: Callable | None = None,
        on_repaste_last: Callable | None = None,
        on_copy_text: Callable | None = None,
        on_output_text: Callable | None = None,
        on_open_dictionary: Callable | None = None,
        on_quit: Callable | None = None,
        on_recording_painted: Callable | None = None,
        on_preview_painted: Callable | None = None,
        on_recover_session: Callable | None = None,
        on_delete_recovery: Callable | None = None,
        on_read_history: Callable | None = None,
        on_delete_history: Callable | None = None,
        on_clear_history: Callable | None = None,
        on_restore_history: Callable | None = None,
        on_status: Callable[[str], None] | None = None,
        build_id: str = "",
        runtime_state_path: str | os.PathLike[str] | None = None,
    ):
        self._lock = threading.RLock()
        self._phase = RuntimePhase.STARTING
        self._last_error_code = ""
        self._hotkeys = "pending"
        self._worker = "starting"
        self._final_asr = "starting"
        self._preview_asr = "starting"
        self._worker_pid = 0
        self._worker_pids = {}
        self._last_heartbeat = 0.0
        self._build_id = build_id
        self._runtime_state_path = (
            Path(runtime_state_path) if runtime_state_path is not None else None
        )
        self._status_sink = on_status
        self._callbacks = {
            "record": on_record_toggle,
            "trial": on_trial_toggle,
            "cancel": on_cancel,
            "copy_last": on_copy_last,
            "repaste_last": on_repaste_last,
            "copy_text": on_copy_text,
            "output_text": on_output_text,
            "open_dictionary": on_open_dictionary,
            "quit": on_quit,
            "recording_painted": on_recording_painted,
            "preview_painted": on_preview_painted,
            "recover_session": on_recover_session,
            "delete_recovery": on_delete_recovery,
            "read_history": on_read_history,
            "delete_history": on_delete_history,
            "clear_history": on_clear_history,
            "restore_history": on_restore_history,
        }
        self._action_in_flight = False
        self._action_queue: queue.Queue = queue.Queue(maxsize=1)
        self._action_worker = threading.Thread(
            target=self._run_actions,
            name="voiceflow-app-actions",
            daemon=True,
        )
        self._action_worker.start()
        with self._lock:
            self._persist_locked()

    @property
    def phase(self) -> RuntimePhase:
        with self._lock:
            return self._phase

    def set_status_sink(self, sink: Callable[[str], None] | None):
        with self._lock:
            self._status_sink = sink

    def mark_hotkeys(self, state: str):
        with self._lock:
            self._hotkeys = str(state)
            self._persist_locked()

    def mark_ready(
        self,
        *,
        preview_ready: bool = True,
        worker_pid: int | None = None,
        worker_pids: dict[str, int | None] | None = None,
        last_heartbeat: float | None = None,
    ):
        with self._lock:
            self._phase = RuntimePhase.READY
            self._worker = "ready"
            self._final_asr = "ready"
            self._preview_asr = "ready" if preview_ready else "unavailable"
            self._last_error_code = ""
            if worker_pid is not None:
                self._worker_pid = int(worker_pid)
            if worker_pids is not None:
                self._worker_pids = {
                    str(name): int(pid)
                    for name, pid in worker_pids.items()
                    if pid is not None
                }
            if last_heartbeat is not None:
                self._last_heartbeat = float(last_heartbeat)
            self._persist_locked()

    def update_worker_health(self, *, worker_pids, last_heartbeat):
        with self._lock:
            self._worker_pids = {
                str(name): int(pid)
                for name, pid in worker_pids.items()
                if pid is not None
            }
            self._worker_pid = int(self._worker_pids.get("final", 0))
            self._last_heartbeat = float(last_heartbeat)
            self._persist_locked()

    def mark_recording(self):
        with self._lock:
            self._phase = RuntimePhase.RECORDING
            self._persist_locked()

    def mark_finalizing(self):
        with self._lock:
            self._phase = RuntimePhase.FINALIZING
            self._persist_locked()

    def mark_delivering(self):
        with self._lock:
            self._phase = RuntimePhase.DELIVERING
            self._persist_locked()

    def mark_degraded(self, _detail: str = "", *, error_code: str = "runtime_degraded"):
        with self._lock:
            self._phase = RuntimePhase.DEGRADED
            self._worker = "degraded"
            self._last_error_code = error_code
            self._persist_locked()

    def mark_error(self, _detail: str = "", *, error_code: str = "runtime_error"):
        with self._lock:
            self._phase = RuntimePhase.ERROR
            self._worker = "error"
            self._last_error_code = error_code
            self._persist_locked()

    def can_accept_recording_intent(self) -> bool:
        return self.phase not in {RuntimePhase.FINALIZING, RuntimePhase.DELIVERING}

    def toggle_recording(self, triggered_at=None, *, source="ui") -> ActionResult:
        phase = self.phase
        if phase is RuntimePhase.STARTING:
            return self._reject("正在准备", "runtime_starting", source)
        if phase in {RuntimePhase.DEGRADED, RuntimePhase.ERROR}:
            code = self.runtime_snapshot()["last_error_code"] or "runtime_unavailable"
            return self._reject("暂时无法听写", code, source)
        if phase in {RuntimePhase.FINALIZING, RuntimePhase.DELIVERING}:
            return self._reject("正在整理", "runtime_busy", source)
        return self._enqueue(
            "record_toggle",
            lambda: self._call("record", triggered_at),
        )

    def start_trial(self) -> ActionResult:
        phase = self.phase
        if phase is RuntimePhase.STARTING:
            return self._reject("正在准备", "runtime_starting", "trial")
        if phase in {RuntimePhase.DEGRADED, RuntimePhase.ERROR}:
            code = self.runtime_snapshot()["last_error_code"] or "runtime_unavailable"
            return self._reject("暂时无法听写", code, "trial")
        if phase in {RuntimePhase.FINALIZING, RuntimePhase.DELIVERING}:
            return self._reject("正在整理", "runtime_busy", "trial")
        return self._enqueue("trial_toggle", lambda: self._call("trial"))

    def cancel_recording(self):
        return self._enqueue("cancel", lambda: self._call("cancel"))

    def copy_last(self):
        return self._call("copy_last")

    def repaste_last(self):
        return self._call("repaste_last")

    def copy_text(self, text):
        return self._call("copy_text", text)

    def output_text(self, text):
        return self._call("output_text", text)

    def open_dictionary(self):
        return self._call("open_dictionary")

    def quit(self):
        return self._call("quit")

    def recording_painted(self, generation, elapsed_ms):
        return self._call("recording_painted", generation, elapsed_ms)

    def preview_painted(self, generation, painted_at):
        return self._call("preview_painted", generation, painted_at)

    def recover_session(self, session_id):
        return self._call("recover_session", session_id)

    def delete_recovery(self, session_id):
        return self._call("delete_recovery", session_id)

    def read_history(self):
        return self._call("read_history") or []

    def delete_history(self, entry_id):
        return self._call("delete_history", entry_id)

    def clear_history(self):
        return self._call("clear_history")

    def restore_history(self, token):
        return self._call("restore_history", token)

    def runtime_snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "build_id": self._build_id,
                "phase": self._phase.value,
                "hotkeys": self._hotkeys,
                "worker": self._worker,
                "final_asr": self._final_asr,
                "preview_asr": self._preview_asr,
                "last_error_code": self._last_error_code,
                "worker_pid": self._worker_pid,
                "worker_pids": dict(self._worker_pids),
                "last_heartbeat": self._last_heartbeat,
            }

    def _persist_locked(self):
        path = self._runtime_state_path
        if path is None:
            return
        payload = {}
        try:
            if path.is_file():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload.update(existing)
        except (OSError, ValueError):
            pass
        payload.update(
            {
                "build_id": self._build_id,
                "phase": self._phase.value,
                "hotkeys": self._hotkeys,
                "worker": self._worker,
                "final_asr": self._final_asr,
                "preview_asr": self._preview_asr,
                "last_error_code": self._last_error_code,
                "worker_pid": self._worker_pid,
                "worker_pids": dict(self._worker_pids),
                "last_heartbeat": self._last_heartbeat,
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _reject(self, message: str, code: str, source: str) -> ActionResult:
        logger.info(
            "action rejected",
            extra={
                "event": "action_rejected",
                "source": source,
                "phase": self.phase.value,
                "error_code": code,
            },
        )
        self._emit_status(message)
        return ActionResult(False, message, code)

    def _enqueue(self, name: str, callback: Callable) -> ActionResult:
        with self._lock:
            if self._action_in_flight:
                return self._reject("请稍候", "action_busy", name)
            self._action_in_flight = True
        try:
            self._action_queue.put_nowait((name, callback))
        except queue.Full:
            with self._lock:
                self._action_in_flight = False
            return self._reject("请稍候", "action_busy", name)
        return ActionResult(True, "", "")

    def _run_actions(self):
        while True:
            item = self._action_queue.get()
            try:
                if item is None:
                    return
                name, callback = item
                started = time.perf_counter()
                try:
                    callback()
                except Exception:
                    logger.exception("action_failed action=%s", name)
                    self._emit_status("需要处理")
                finally:
                    logger.info(
                        "action finished",
                        extra={
                            "event": "action_finished",
                            "action": name,
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000,
                                3,
                            ),
                        },
                    )
            finally:
                with self._lock:
                    self._action_in_flight = False
                self._action_queue.task_done()

    def _call(self, name: str, *args):
        callback = self._callbacks.get(name)
        if callback is None:
            logger.warning("action_unavailable action=%s", name)
            return None
        return callback(*args)

    def _emit_status(self, message: str):
        with self._lock:
            sink = self._status_sink
        if sink is not None:
            sink(message)
