"""Truthful clipboard-first delivery and conservative target classification."""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass, replace
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable


logger = logging.getLogger("voiceflow.delivery")

_SYSTEM_SURFACE_CLASSES = {
    "progman",
    "workerw",
    "shell_traywnd",
    "shell_secondarytraywnd",
}

_BLOCKED_TARGET_REASONS = {
    "password", "secure_desktop", "own_process", "disabled", "read_only", "ime_composition",
}


class EditableEvidence(str, Enum):
    NONE = "none"
    UIA_VALUE_WRITABLE = "uia_value_writable"
    UIA_TEXT_WRITABLE = "uia_text_writable"
    LEGACY_TEXT = "legacy_text"
    WIN32_EDIT = "win32_edit"


class TargetClassification(str, Enum):
    EDITABLE = "editable"
    TRANSIENT_UNKNOWN = "transient_unknown"
    DEFINITELY_BLOCKED = "definitely_blocked"


@dataclass(frozen=True)
class TargetDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class ClipboardWriteResult:
    verified: bool
    attempts: int
    error: str = ""


@dataclass(frozen=True)
class TargetSnapshot:
    window_handle: int | None
    process_id: int | None
    element_id: str
    editable: bool
    integrity_compatible: bool | None
    known: bool
    editable_evidence: EditableEvidence = EditableEvidence.NONE
    provider: str = ""
    control_type: str = ""
    rejection_reason: str = ""
    runtime_id: str = ""
    foreground_class: str = ""
    focus_window_handle: int | None = None
    caret_window_handle: int | None = None
    document_id: int | None = None
    selection_start: int | None = None
    selection_end: int | None = None
    document_length: int | None = None
    executable_name: str = ""
    text_encoding: str = ""
    line_ending: str = ""
    ime_composing: bool | None = None

    @property
    def classification(self) -> TargetClassification:
        if (
            not self.known
            or not self.window_handle
            or not self.process_id
            or not self.integrity_compatible
            or self.rejection_reason in _BLOCKED_TARGET_REASONS
            or self.foreground_class.casefold() in _SYSTEM_SURFACE_CLASSES
            or self.ime_composing is True
        ):
            return TargetClassification.DEFINITELY_BLOCKED
        if self.editable:
            return TargetClassification.EDITABLE
        return TargetClassification.TRANSIENT_UNKNOWN

    def paste_decision_from(self, previous: "TargetSnapshot | None") -> TargetDecision:
        if self.ime_composing is True:
            return TargetDecision(False, "ime_composition")
        if not self.known:
            return TargetDecision(False, "stop_target_unknown")
        if not self.window_handle or not self.process_id:
            return TargetDecision(False, "stop_target_unknown")
        if self.integrity_compatible is None:
            return TargetDecision(False, "target_integrity_unknown")
        if not self.integrity_compatible:
            return TargetDecision(False, "target_integrity_incompatible")
        if self.foreground_class.casefold() in _SYSTEM_SURFACE_CLASSES:
            return TargetDecision(False, "system_surface")
        if self.rejection_reason in _BLOCKED_TARGET_REASONS:
            return TargetDecision(False, self.rejection_reason)
        return TargetDecision(True, "current_foreground_target")

    def can_receive_paste_from(self, previous: "TargetSnapshot | None") -> bool:
        return self.paste_decision_from(previous).allowed

    def same_input_context(self, expected: "TargetSnapshot") -> bool:
        if self.ime_composing is True or expected.ime_composing is True:
            return False
        if (self.window_handle, self.process_id) != (
            expected.window_handle, expected.process_id
        ):
            return False
        if self.focus_window_handle and expected.focus_window_handle:
            if self.focus_window_handle != expected.focus_window_handle:
                return False
        if self.provider == expected.provider == "uia":
            if self.element_id != expected.element_id:
                return False
            if expected.runtime_id and self.runtime_id != expected.runtime_id:
                return False
        for name in ("document_id", "selection_start", "selection_end", "document_length"):
            value = getattr(expected, name)
            if value is not None and getattr(self, name) != value:
                return False
        return True


@dataclass(frozen=True)
class TargetObservation:
    observed_at: float
    snapshot: TargetSnapshot
    window_handle: int | None
    process_id: int | None
    control_type: str
    foreground_class: str
    focus_window_handle: int | None
    caret_window_handle: int | None
    editable_evidence: EditableEvidence
    classification: TargetClassification
    rejection_reason: str

    @classmethod
    def from_snapshot(
        cls,
        snapshot: TargetSnapshot,
        *,
        observed_at: float | None = None,
    ) -> "TargetObservation":
        return cls(
            observed_at=time.monotonic() if observed_at is None else float(observed_at),
            snapshot=snapshot,
            window_handle=snapshot.window_handle,
            process_id=snapshot.process_id,
            control_type=snapshot.control_type,
            foreground_class=snapshot.foreground_class,
            focus_window_handle=snapshot.focus_window_handle,
            caret_window_handle=snapshot.caret_window_handle,
            editable_evidence=snapshot.editable_evidence,
            classification=snapshot.classification,
            rejection_reason=snapshot.rejection_reason,
        )


@contextmanager
def _mta_initializer():
    if sys.platform != "win32":
        yield
        return
    sys.coinit_flags = 0
    was_loaded = "comtypes" in sys.modules
    import comtypes

    if was_loaded:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    try:
        yield
    finally:
        comtypes.CoUninitialize()


@contextmanager
def _uia_focus_subscription(notify: Callable[[], None]):
    if sys.platform != "win32":
        yield
        return
    client = None
    handler = None
    try:
        from comtypes import COMObject
        from uiautomation import uiautomation as automation

        core = automation._AutomationClient.instance().UIAutomationCore
        client = automation._AutomationClient.instance().IUIAutomation

        class Handler(COMObject):
            _com_interfaces_ = [core.IUIAutomationFocusChangedEventHandler]

            def HandleFocusChangedEvent(self, _sender):
                notify()
                return 0

        handler = Handler()
        client.AddFocusChangedEventHandler(None, handler)
    except Exception:
        client = None
        handler = None
        logger.exception("UI Automation focus subscription unavailable")
    try:
        yield
    finally:
        if client is not None and handler is not None:
            try:
                client.RemoveFocusChangedEventHandler(handler)
            except Exception:
                logger.exception("UI Automation focus subscription cleanup failed")


class FocusMonitor:
    """Own UI Automation on one MTA worker and retain a bounded focus trace."""

    def __init__(
        self,
        *,
        inspector: Callable[[], TargetSnapshot] | None = None,
        initializer: Callable | None = None,
        subscriber: Callable | None = None,
        insertion_verifier: Callable[[TargetSnapshot, str], bool] | None = None,
        max_observations: int = 64,
        poll_interval: float = 0.25,
    ):
        self._inspector = inspector or inspect_current_target
        self._initializer = initializer or _mta_initializer
        self._subscriber = subscriber or _uia_focus_subscription
        self._insertion_verifier = insertion_verifier
        self._observations = deque(maxlen=max(1, int(max_observations)))
        self._poll_interval = max(0.01, float(poll_interval))
        self._requests = queue.Queue(maxsize=8)
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._active = threading.Event()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._focus_event_marker = object()
        self._focus_event_pending = threading.Event()
        self._focus_event_lock = threading.Lock()

    def start_tracking(self, *, wait: bool = True) -> TargetObservation:
        if wait:
            self.warmup()
        else:
            self._ensure_started()
        self._active.set()
        return self.observe(timeout=0.25 if wait else 0.0)

    def warmup(self, timeout: float = 1.0) -> bool:
        self._ensure_started()
        return self._ready.wait(max(0.0, float(timeout)))

    def stop_tracking(self):
        self._active.clear()

    def observe(self, timeout: float = 0.25) -> TargetObservation:
        result = self._submit(self._sample, timeout)
        return result if isinstance(result, TargetObservation) else TargetObservation.from_snapshot(
            TargetSnapshot(None, None, "", False, False, False),
        )

    def verify_insertion(self, expected: TargetSnapshot, text: str, timeout: float = 0.25) -> bool:
        def verify():
            if self._insertion_verifier is not None:
                return self._insertion_verifier(expected, text)
            from insertion_verification import verify_native_insertion
            return verify_native_insertion(expected, text)

        return self._submit(verify, min(0.25, max(0.0, timeout))) is True

    def _submit(self, operation, timeout):
        self._ensure_started()
        completed = threading.Event()
        result = []
        try:
            self._requests.put_nowait((completed, result, operation))
        except queue.Full:
            completed.set()
        if completed.wait(max(0.0, float(timeout))) and result:
            return result[0]
        completed.set()
        return None

    def trace(self) -> tuple[TargetObservation, ...]:
        with self._lock:
            return tuple(self._observations)

    def shutdown(self):
        self._stop.set()
        self._active.set()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        if thread is None or not thread.is_alive():
            self._thread = None
        self._ready.clear()

    def _ensure_started(self):
        with self._start_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="voiceflow-focus-monitor",
                daemon=True,
            )
            self._thread.start()

    def _run(self):
        with self._initializer():
            with self._subscriber(self._notify_focus_changed):
                self._ready.set()
                while not self._stop.is_set():
                    timeout = self._poll_interval if self._active.is_set() else 0.5
                    try:
                        request = self._requests.get(timeout=timeout)
                    except queue.Empty:
                        if self._active.is_set():
                            self._sample()
                        continue
                    if request is None:
                        break
                    if request is self._focus_event_marker:
                        with self._focus_event_lock:
                            self._focus_event_pending.clear()
                        if self._active.is_set():
                            self._sample()
                        continue
                    completed, result, operation = request
                    if completed.is_set():
                        continue
                    try:
                        value = operation()
                    except Exception:
                        value = None
                    result.append(value)
                    completed.set()

    def _notify_focus_changed(self):
        if self._stop.is_set():
            return
        with self._focus_event_lock:
            if self._focus_event_pending.is_set():
                return
            self._focus_event_pending.set()
            try:
                self._requests.put_nowait(self._focus_event_marker)
            except queue.Full:
                self._focus_event_pending.clear()

    def _sample(self) -> TargetObservation:
        try:
            snapshot = self._inspector()
        except Exception:
            snapshot = TargetSnapshot(None, None, "", False, False, False)
        observation = TargetObservation.from_snapshot(snapshot)
        with self._lock:
            self._observations.append(observation)
        return observation


@dataclass(frozen=True)
class DeliveryResult:
    clipboard_verified: bool
    paste_dispatched: bool
    clipboard_only: bool
    recovery_saved: bool
    reason: str
    attempts: int
    text_sha256: str
    target_evidence: str
    landed_confirmed: bool = False

    @property
    def output_status(self) -> str:
        if self.landed_confirmed:
            return "landed_confirmed"
        if self.paste_dispatched:
            return "clipboard_verified_paste_dispatched"
        if self.clipboard_verified:
            return "clipboard_verified_only"
        if self.recovery_saved:
            return "recovery_saved_clipboard_unavailable"
        return "delivery_failed"


@dataclass(frozen=True)
class PasteDispatchResult:
    dispatched: bool
    reason: str

    def __bool__(self):
        return self.dispatched


class VerifiedClipboard:
    def __init__(
        self,
        *,
        copy: Callable[[str], None],
        paste: Callable[[], str],
        sleeper: Callable[[float], None] = time.sleep,
        retry_delays: tuple[float, ...] = (0.0, 0.02, 0.05, 0.1, 0.2, 0.4),
    ):
        self._copy = copy
        self._paste = paste
        self._sleeper = sleeper
        self._retry_delays = tuple(retry_delays) or (0.0,)

    def write_verified(self, text: str) -> ClipboardWriteResult:
        last_error = "clipboard_unavailable"
        for attempt, delay in enumerate(self._retry_delays, start=1):
            if delay > 0:
                self._sleeper(delay)
            try:
                self._copy(text)
                actual = self._paste()
                if actual == text:
                    return ClipboardWriteResult(True, attempt)
                last_error = "clipboard_readback_mismatch"
            except Exception as exc:
                last_error = f"clipboard_error:{type(exc).__name__}"
        return ClipboardWriteResult(False, len(self._retry_delays), last_error)

    def still_contains(self, text: str) -> bool:
        try:
            return self._paste() == text
        except Exception:
            return False


class DeliveryCoordinator:
    MAX_PENDING_BYTES = 4 * 1024 * 1024
    _SESSION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")

    def __init__(
        self,
        *,
        clipboard: VerifiedClipboard,
        inspect_target: Callable[[], TargetSnapshot],
        dispatch_paste: Callable[[], bool],
        ledger_dir: str | Path,
        dispatch_checked_paste: Callable[[TargetSnapshot, str], PasteDispatchResult] | None = None,
        verify_insertion: Callable[[TargetSnapshot, str], bool] | None = None,
    ):
        self.clipboard = clipboard
        self.inspect_target = inspect_target
        self.dispatch_paste = dispatch_paste
        self.dispatch_checked_paste = dispatch_checked_paste
        self.verify_insertion = verify_insertion
        self.ledger_dir = Path(ledger_dir)

    def deliver(
        self,
        text: str,
        *,
        start_target: TargetSnapshot | None,
        session_id: str,
        allow_paste: bool = True,
        stop_target: TargetSnapshot | None = None,
    ) -> DeliveryResult:
        prepared = str(text)
        digest = hashlib.sha256(prepared.encode("utf-8")).hexdigest()
        try:
            self._write_pending(session_id, prepared, digest)
        except OSError:
            clipboard_result = self.clipboard.write_verified(prepared)
            return DeliveryResult(
                clipboard_verified=clipboard_result.verified,
                paste_dispatched=False,
                clipboard_only=clipboard_result.verified,
                recovery_saved=False,
                reason="pending_write_failed",
                attempts=clipboard_result.attempts,
                text_sha256=digest,
                target_evidence=EditableEvidence.NONE.value,
            )
        expected_target = stop_target or self.inspect_target()
        clipboard_result = self.clipboard.write_verified(prepared)
        if not clipboard_result.verified:
            return DeliveryResult(
                clipboard_verified=False,
                paste_dispatched=False,
                clipboard_only=False,
                recovery_saved=True,
                reason=clipboard_result.error,
                attempts=clipboard_result.attempts,
                text_sha256=digest,
                target_evidence=EditableEvidence.NONE.value,
            )

        current_target = self.inspect_target()
        paste_dispatched = False
        landed_confirmed = False
        clipboard_current = not allow_paste or self.clipboard.still_contains(prepared)
        reason = "clipboard_verified"
        decision = current_target.paste_decision_from(start_target)
        logger.info(
            "delivery target decision session=%s reason=%s start_provider=%s "
            "start_control=%s start_evidence=%s stop_provider=%s stop_control=%s "
            "stop_evidence=%s",
            session_id,
            decision.reason,
            getattr(start_target, "provider", ""),
            getattr(start_target, "control_type", ""),
            _evidence_value(getattr(start_target, "editable_evidence", EditableEvidence.NONE)),
            current_target.provider,
            current_target.control_type,
            _evidence_value(current_target.editable_evidence),
        )
        if allow_paste and not current_target.same_input_context(expected_target):
            reason = "target_changed"
        elif allow_paste and not clipboard_current:
            reason = "clipboard_changed"
        elif allow_paste and decision.allowed:
            try:
                dispatch = (
                    self.dispatch_checked_paste(current_target, prepared)
                    if self.dispatch_checked_paste is not None else self.dispatch_paste()
                )
                paste_dispatched = bool(dispatch)
                reason = getattr(dispatch, "reason", "") or (
                    "paste_dispatched" if paste_dispatched else "paste_dispatch_failed"
                )
                if reason == "delivery_context_changed":
                    clipboard_current = self.clipboard.still_contains(prepared)
                    if not clipboard_current:
                        reason = "clipboard_changed"
                if paste_dispatched and self.verify_insertion is not None:
                    try:
                        landed_confirmed = self.verify_insertion(current_target, prepared) is True
                    except Exception:
                        landed_confirmed = False
            except Exception:
                reason = "paste_dispatch_failed"
        elif allow_paste:
            reason = decision.reason
        else:
            reason = "clipboard_only_requested"

        return DeliveryResult(
            clipboard_verified=clipboard_current,
            paste_dispatched=paste_dispatched,
            clipboard_only=clipboard_current and not paste_dispatched,
            recovery_saved=not clipboard_current,
            reason=reason,
            attempts=clipboard_result.attempts,
            text_sha256=digest,
            target_evidence=_evidence_value(current_target.editable_evidence),
            landed_confirmed=landed_confirmed,
        )

    def acknowledge(self, session_id: str) -> bool:
        path = self._ledger_path(session_id)
        if path is None:
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    def clear_pending(self, *, session_ids=None, text=None) -> int:
        """Remove owned flat ledger files without following directory links."""
        root = self.ledger_dir
        if root.is_symlink() or root.is_junction():
            raise OSError("待交付记录目录是链接，未清除，请检查本机数据目录")
        if not root.exists():
            return 0
        if not root.is_dir():
            raise OSError("待交付记录目录不可用")
        selected = set(str(value) for value in (session_ids or ()))
        digest = hashlib.sha256(str(text).encode("utf-8")).hexdigest() if text is not None else None
        remove_all = session_ids is None and text is None
        candidates = []
        for path in root.iterdir():
            name = path.name
            if name.startswith(".") and name.endswith(".json.tmp"):
                session_id = name[1:-9]
            elif name.endswith(".json"):
                session_id = name[:-5]
            else:
                continue
            if not self._SESSION_ID.fullmatch(session_id):
                continue
            if path.is_symlink() or path.is_junction() or not path.is_file():
                raise OSError("待交付记录包含异常文件，未完成清除")
            matches = remove_all or session_id in selected
            if not matches and digest is not None:
                try:
                    if path.stat().st_size <= self.MAX_PENDING_BYTES:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        matches = isinstance(payload, dict) and payload.get("text_sha256") == digest
                except (ValueError, UnicodeError):
                    pass
            if matches:
                candidates.append(path)
        # Validate the complete flat directory before removing the first file.
        for path in candidates:
            path.unlink()
        return len(candidates)

    def recover_pending_to_clipboard(self) -> list[dict]:
        recovered: list[dict] = []
        if not self.ledger_dir.is_dir():
            return recovered
        for path in sorted(self.ledger_dir.glob("*.json")):
            try:
                if path.is_symlink() or path.stat().st_size > self.MAX_PENDING_BYTES:
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                text = str(payload["text"])
                if len(text.encode("utf-8")) > self.MAX_PENDING_BYTES:
                    continue
                session_id = str(payload["session_id"])
                expected_path = self._ledger_path(session_id)
                if expected_path is None or expected_path.resolve() != path.resolve():
                    continue
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if digest != str(payload.get("text_sha256", "")):
                    continue
                result = self.clipboard.write_verified(text)
                if not result.verified:
                    continue
                recovered.append(
                    {
                        "session_id": session_id,
                        "text": text,
                        "text_sha256": digest,
                        "attempts": result.attempts,
                    }
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return recovered

    def _write_pending(self, session_id: str, text: str, digest: str) -> Path:
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        path = self._ledger_path(session_id)
        if path is None:
            raise ValueError("invalid delivery session id")
        if len(text.encode("utf-8")) > self.MAX_PENDING_BYTES:
            raise ValueError("pending delivery text is too large")
        temporary = path.with_name(f".{path.name}.tmp")
        content = json.dumps(
            {
                "schema_version": 1,
                "session_id": str(session_id),
                "text": text,
                "text_sha256": digest,
                "created_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return path

    def _ledger_path(self, session_id: str) -> Path | None:
        value = str(session_id)
        if not self._SESSION_ID.fullmatch(value):
            return None
        return self.ledger_dir / f"{value}.json"


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("hwndActive", ctypes.c_void_p),
        ("hwndFocus", ctypes.c_void_p),
        ("hwndCapture", ctypes.c_void_p),
        ("hwndMenuOwner", ctypes.c_void_p),
        ("hwndMoveSize", ctypes.c_void_p),
        ("hwndCaret", ctypes.c_void_p),
        ("rcCaret", ctypes.c_long * 4),
    ]


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _InputUnion)]


@lru_cache(maxsize=1)
def _windows_libraries():
    """Declare the Windows ABI before passing pointer-sized handles or SIDs."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    signatures = (
        (user32.GetForegroundWindow, [], wintypes.HWND),
        (user32.GetWindowThreadProcessId,
         [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        (user32.GetGUIThreadInfo,
         [wintypes.DWORD, ctypes.POINTER(_GuiThreadInfo)], wintypes.BOOL),
        (user32.GetClassNameW,
         [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        (user32.GetWindowLongW, [wintypes.HWND, ctypes.c_int], wintypes.LONG),
        (user32.IsWindow, [wintypes.HWND], wintypes.BOOL),
        (user32.IsWindowEnabled, [wintypes.HWND], wintypes.BOOL),
        (user32.GetAsyncKeyState, [ctypes.c_int], ctypes.c_short),
        (user32.SendInput,
         [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int], wintypes.UINT),
        (user32.SendMessageTimeoutW,
         [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
          wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)], ctypes.c_ssize_t),
        (kernel32.OpenProcess,
         [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (kernel32.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
        (kernel32.QueryFullProcessImageNameW,
         [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        (advapi32.OpenProcessToken,
         [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)],
         wintypes.BOOL),
        (advapi32.GetTokenInformation,
         [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
          ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        (advapi32.IsValidSid, [wintypes.LPVOID], wintypes.BOOL),
        (advapi32.GetSidSubAuthorityCount,
         [wintypes.LPVOID], ctypes.POINTER(ctypes.c_ubyte)),
        (advapi32.GetSidSubAuthority,
         [wintypes.LPVOID, wintypes.DWORD], ctypes.POINTER(wintypes.DWORD)),
    )
    for function, arguments, result in signatures:
        function.argtypes = arguments
        function.restype = result
    return user32, kernel32, advapi32


def dispatch_windows_paste(*, guard: Callable[[], bool], terminal: bool = False,
                           modifier_timeout: float = 0.25) -> PasteDispatchResult:
    """Send one paste chord; event acceptance does not prove inserted text."""
    user32, _, _ = _windows_libraries()
    deadline = time.monotonic() + max(0.0, min(0.25, modifier_timeout))
    while any(user32.GetAsyncKeyState(key) & 0x8000
              for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        if time.monotonic() >= deadline:
            return PasteDispatchResult(False, "modifier_held")
        time.sleep(0.01)
    if not guard():
        return PasteDispatchResult(False, "delivery_context_changed")
    keys = [0x11, 0x10, 0x56] if terminal else [0x11, 0x56]
    events = (_Input * (len(keys) * 2))()
    for index, key in enumerate(keys + keys[::-1]):
        events[index].type = 1
        events[index].ki.wVk = key
        events[index].ki.dwFlags = 0 if index < len(keys) else 2
    sent = user32.SendInput(len(events), events, ctypes.sizeof(_Input))
    if sent == len(events):
        return PasteDispatchResult(True, "paste_dispatched")
    # A partial chord must not leave our synthetic modifier down. Release only
    # accepted down events; never retry V or release a pre-existing held key.
    held = []
    for event in events[:sent]:
        key = event.ki.wVk
        if event.ki.dwFlags == 0:
            held.append(key)
        elif key in held:
            held.remove(key)
    if held:
        release = (_Input * len(held))()
        for index, key in enumerate(held[::-1]):
            release[index].type = 1
            release[index].ki.wVk = key
            release[index].ki.dwFlags = 2
        user32.SendInput(len(release), release, ctypes.sizeof(_Input))
    return PasteDispatchResult(False, "paste_dispatch_partial" if sent else "paste_dispatch_failed")


def _window_class(user32, window_handle: int) -> str:
    if not window_handle:
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(window_handle, buffer, len(buffer))
    return buffer.value


@lru_cache(maxsize=1)
def _ime_library():
    api = ctypes.WinDLL("imm32", use_last_error=True)
    api.ImmGetContext.argtypes = [wintypes.HWND]
    api.ImmGetContext.restype = wintypes.HANDLE
    api.ImmGetCompositionStringW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
    api.ImmGetCompositionStringW.restype = wintypes.LONG
    api.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    api.ImmReleaseContext.restype = wintypes.BOOL
    return api


def _ime_composing(window_handle: int) -> bool | None:
    """Query only composition size; never retrieve the user's unfinished text."""
    if sys.platform != "win32" or not window_handle:
        return None
    try:
        api = _ime_library()
        context = api.ImmGetContext(window_handle)
        if not context:
            return None
        try:
            size = api.ImmGetCompositionStringW(context, 0x0008, None, 0)
            return size > 0 if size >= 0 else None
        finally:
            api.ImmReleaseContext(window_handle, context)
    except OSError:
        return None


def _editor_context(user32, focus: int) -> dict:
    """Read only selection/length/opaque document metadata, never document text."""
    class_name = _window_class(user32, focus).casefold()
    deadline = time.monotonic() + 0.04

    def message(number, wparam=0, lparam=0):
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms < 1:
            raise TimeoutError("editor metadata deadline")
        result = ctypes.c_size_t()
        if not user32.SendMessageTimeoutW(
            focus, number, wparam, lparam, 0x0023, remaining_ms, ctypes.byref(result)
        ):
            raise TimeoutError("editor metadata unavailable")
        return result.value

    try:
        if class_name == "scintilla":
            # Scintilla getters use scalar values only: no foreign-process buffer.
            doc = message(2357)  # SCI_GETDOCPOINTER, used only as an opaque identity
            caret = message(2008)  # SCI_GETCURRENTPOS
            anchor = message(2009)  # SCI_GETANCHOR
            length = message(2006)  # SCI_GETLENGTH (bytes, not Unicode characters)
            code_page = message(2137)  # SCI_GETCODEPAGE
            eol_mode = message(2030)  # SCI_GETEOLMODE
            convert_endings = message(2468)  # SCI_GETPASTECONVERTENDINGS
            return {"document_id": doc, "selection_start": min(caret, anchor),
                    "selection_end": max(caret, anchor), "document_length": length,
                    "text_encoding": "utf-8" if code_page == 65001 else "",
                    "line_ending": ({0: "\r\n", 1: "\r", 2: "\n"}.get(eol_mode, "")
                                    if convert_endings else "preserve")}
        if class_name == "edit" or class_name.startswith("richedit"):
            start, end = wintypes.DWORD(), wintypes.DWORD()
            message(0x00B0, ctypes.addressof(start), ctypes.addressof(end))  # EM_GETSEL
            return {"selection_start": start.value, "selection_end": end.value,
                    "document_length": message(0x000E),  # WM_GETTEXTLENGTH
                    "text_encoding": "utf-16-le" if class_name == "edit" else "",
                    "line_ending": "preserve" if class_name == "edit" else ""}
    except (OSError, TimeoutError):
        pass
    return {}


def inspect_current_target() -> TargetSnapshot:
    if sys.platform != "win32":
        return TargetSnapshot(None, None, "", False, False, False)
    try:
        user32, _, _ = _windows_libraries()
        foreground = int(user32.GetForegroundWindow() or 0)
        if not foreground:
            return TargetSnapshot(None, None, "", False, False, False)
        process_id = ctypes.c_ulong()
        thread_id = int(user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id)))
        foreground_process_id = int(process_id.value)
        foreground_class = _window_class(user32, foreground)
        info = _GuiThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        has_thread_info = bool(user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)))
        focus = int(info.hwndFocus or foreground) if has_thread_info else foreground
        caret = int(info.hwndCaret or 0) if has_thread_info else 0
        context = _editor_context(user32, focus)
        native_composition = _ime_composing(focus)
        context["executable_name"] = _process_executable_name(foreground_process_id)
        uia_target = _inspect_uia_target(
            foreground=foreground,
            foreground_process_id=foreground_process_id,
        )
        if uia_target is not None:
            own_process = foreground_process_id == os.getpid() and not uia_target.editable
            return replace(
                uia_target,
                foreground_class=foreground_class,
                focus_window_handle=focus,
                caret_window_handle=caret or None,
                **context,
                ime_composing=(True if native_composition is True
                               or uia_target.ime_composing is True else None),
                rejection_reason=(
                    "own_process" if own_process else uia_target.rejection_reason
                ),
            )

        class_name = _window_class(user32, focus)
        normalized = class_name.casefold()
        style = int(user32.GetWindowLongW(focus, -16))
        native_edit = (
                normalized == "edit"
                or normalized.startswith("richedit")
                or normalized in {"scintilla", "richeditd2dpt"}
        )
        enabled = bool(user32.IsWindowEnabled(focus))
        read_only = (normalized == "edit" or normalized.startswith("richedit")) and bool(style & 0x0800)
        editable = enabled and native_edit and not read_only
        return TargetSnapshot(
            foreground,
            foreground_process_id,
            f"{focus}:{class_name}",
            editable,
            _integrity_compatible(foreground_process_id),
            bool(foreground_class or class_name),
            EditableEvidence.WIN32_EDIT if editable else EditableEvidence.NONE,
            "win32",
            class_name,
            (
                "own_process"
                if foreground_process_id == os.getpid() and not editable
                else "disabled" if not enabled
                else "read_only" if read_only
                else "" if editable else "not_editable"
            ),
            "",
            foreground_class,
            focus,
            caret or None,
            **context,
            ime_composing=native_composition,
        )
    except Exception:
        return TargetSnapshot(None, None, "", False, False, False)


def inspect_foreground_target() -> TargetSnapshot:
    """Capture stop-time window and keyboard focus without entering a UIA provider."""
    if sys.platform != "win32":
        return TargetSnapshot(None, None, "", False, False, False)
    try:
        user32, _, _ = _windows_libraries()
        foreground = int(user32.GetForegroundWindow() or 0)
        process_id = wintypes.DWORD()
        thread_id = user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
        if not foreground or not process_id.value:
            return TargetSnapshot(None, None, "", False, False, False)
        info = _GuiThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        has_info = user32.GetGUIThreadInfo(thread_id, ctypes.byref(info))
        focus = int(info.hwndFocus or foreground) if has_info else foreground
        return TargetSnapshot(
            foreground, int(process_id.value), "", False,
            _integrity_compatible(process_id.value), True,
            provider="win32",
            foreground_class=_window_class(user32, foreground),
            focus_window_handle=focus,
            caret_window_handle=int(info.hwndCaret or 0) or None,
            executable_name=_process_executable_name(process_id.value),
            ime_composing=_ime_composing(focus),
            **_editor_context(user32, focus),
        )
    except Exception:
        return TargetSnapshot(None, None, "", False, False, False)


def _process_executable_name(process_id: int) -> str:
    """Read the executable identity, never a window title or document content."""
    if sys.platform != "win32" or not 0 < int(process_id) < 2**32:
        return ""
    _, kernel32, _ = _windows_libraries()
    process = kernel32.OpenProcess(0x1000, False, int(process_id))
    if not process:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
            return ""
        return Path(buffer.value).name.casefold()
    finally:
        kernel32.CloseHandle(process)


def _inspect_uia_target(
    *,
    foreground: int,
    foreground_process_id: int,
) -> TargetSnapshot | None:
    """Read the actual keyboard-focused UIA element when the provider exposes it."""
    try:
        import uiautomation as automation

        focused = automation.GetFocusedControl()
        if focused is None:
            return None
        process_id = int(focused.ProcessId or foreground_process_id)
        if process_id != foreground_process_id:
            return None
        first_snapshot = None
        control = focused
        for depth in range(8):
            snapshot = _snapshot_uia_control(
                automation,
                control,
                foreground=foreground,
                foreground_process_id=foreground_process_id,
                contains_focused_descendant=depth > 0,
            )
            if snapshot is not None:
                if first_snapshot is None:
                    first_snapshot = snapshot
                if snapshot.rejection_reason in _BLOCKED_TARGET_REASONS:
                    return snapshot
                if snapshot.editable:
                    return snapshot
            try:
                control = control.GetParentControl()
            except Exception:
                break
            if control is None or int(control.ProcessId or foreground_process_id) != foreground_process_id:
                break
        return first_snapshot
    except Exception:
        return None


def _snapshot_uia_control(
    automation,
    control,
    *,
    foreground: int,
    foreground_process_id: int,
    contains_focused_descendant: bool,
) -> TargetSnapshot | None:
    try:
        process_id = int(control.ProcessId or foreground_process_id)
        if process_id != foreground_process_id:
            return None
        runtime_id = tuple(int(value) for value in control.GetRuntimeId())
        if not runtime_id:
            return None
        enabled = bool(getattr(control, "IsEnabled", False))
        focusable = bool(getattr(control, "IsKeyboardFocusable", False))
        focused = bool(getattr(control, "HasKeyboardFocus", True))
        password = bool(getattr(control, "IsPassword", False))
        accepts_focus = focused or contains_focused_descendant
        control_type = str(getattr(control, "ControlTypeName", "") or "Control")
        automation_id = str(getattr(control, "AutomationId", "") or "")
        class_name = str(getattr(control, "ClassName", "") or "")
        evidence = EditableEvidence.NONE
        read_only = _uia_control_is_read_only(automation, control, control_type)
        composing = _uia_has_composition(automation, control)
        if enabled and accepts_focus and (focusable or contains_focused_descendant) and not password:
            evidence = EditableEvidence.NONE if read_only else _editable_uia_evidence(
                automation,
                control,
                control_type=control_type,
                class_name=class_name,
            )
        editable = evidence is not EditableEvidence.NONE
        runtime = ".".join(str(value) for value in runtime_id)
        if composing is True:
            rejection_reason = "ime_composition"
        elif not enabled:
            rejection_reason = "disabled"
        elif password:
            rejection_reason = "password"
        elif read_only:
            rejection_reason = "read_only"
        elif not accepts_focus:
            rejection_reason = "focus_not_confirmed"
        elif not focusable and not contains_focused_descendant:
            rejection_reason = "not_keyboard_focusable"
        elif not editable:
            rejection_reason = "no_writable_evidence"
        else:
            rejection_reason = ""
        if automation_id:
            identity_parts = ["uia", control_type, automation_id]
            if class_name:
                identity_parts.append(class_name)
            element_id = ":".join(identity_parts)
        else:
            element_id = f"uia:{control_type}:runtime:{runtime}"
        return TargetSnapshot(
            window_handle=int(foreground),
            process_id=process_id,
            element_id=element_id,
            editable=editable,
            integrity_compatible=_integrity_compatible(process_id),
            known=True,
            editable_evidence=evidence,
            provider="uia",
            control_type=control_type,
            rejection_reason=rejection_reason,
            runtime_id=runtime,
            ime_composing=composing,
        )
    except Exception:
        return None


def _uia_has_composition(automation, control) -> bool | None:
    pattern_id = getattr(automation.PatternId, "TextEditPattern", None)
    if pattern_id is None:
        return None
    try:
        pattern = control.GetPattern(pattern_id)
        return pattern.GetActiveComposition() is not None if pattern is not None else None
    except Exception:
        return None


def _uia_control_is_read_only(automation, control, control_type: str) -> bool:
    if control_type not in {"EditControl", "DocumentControl"}:
        return False
    value_id = getattr(automation.PatternId, "ValuePattern", None)
    if value_id is not None:
        try:
            pattern = control.GetPattern(value_id)
            if pattern is not None and getattr(pattern, "IsReadOnly", None) is True:
                return True
        except Exception:
            pass
    attribute = getattr(getattr(automation, "TextAttributeId", None),
                        "IsReadOnlyAttribute", None)
    if attribute is None:
        return False
    for name in ("TextPattern", "TextEditPattern"):
        pattern_id = getattr(automation.PatternId, name, None)
        if pattern_id is None:
            continue
        try:
            pattern = control.GetPattern(pattern_id)
            selections = pattern.GetSelection() if pattern is not None else []
            if selections and all(
                selection.GetAttributeValue(attribute) is True for selection in selections
            ):
                return True
        except Exception:
            continue
    return False


def _editable_uia_evidence(
    automation,
    control,
    *,
    control_type: str,
    class_name: str,
) -> EditableEvidence:
    value_pattern_id = getattr(automation.PatternId, "ValuePattern", None)
    if value_pattern_id is not None and control_type == "EditControl":
        try:
            value_pattern = control.GetPattern(value_pattern_id)
            if value_pattern is not None and not bool(value_pattern.IsReadOnly):
                return EditableEvidence.UIA_VALUE_WRITABLE
        except Exception:
            pass

    text_attribute_id = getattr(
        getattr(automation, "TextAttributeId", None),
        "IsReadOnlyAttribute",
        None,
    )
    if text_attribute_id is not None and control_type in {
        "EditControl",
        "DocumentControl",
    }:
        for pattern_name in ("TextPattern", "TextEditPattern"):
            pattern_id = getattr(automation.PatternId, pattern_name, None)
            if pattern_id is None:
                continue
            try:
                text_pattern = control.GetPattern(pattern_id)
                if text_pattern is None:
                    continue
                selections = text_pattern.GetSelection()
                if any(
                    selection.GetAttributeValue(text_attribute_id) is False
                    for selection in selections
                ):
                    return EditableEvidence.UIA_TEXT_WRITABLE
            except Exception:
                continue

    legacy_pattern_id = getattr(
        automation.PatternId,
        "LegacyIAccessiblePattern",
        None,
    )
    if legacy_pattern_id is not None:
        try:
            legacy = control.GetPattern(legacy_pattern_id)
            role = int(legacy.Role) if legacy is not None else 0
            state = int(legacy.State) if legacy is not None else 0
            focused_and_focusable = state & 0x00100004 == 0x00100004
            unavailable_or_read_only = state & 0x00000041
            if role == 42 and focused_and_focusable and not unavailable_or_read_only:
                return EditableEvidence.LEGACY_TEXT
        except Exception:
            pass
    if _native_edit_handle_is_writable(control, class_name=class_name):
        return EditableEvidence.WIN32_EDIT
    return EditableEvidence.NONE


def _native_edit_handle_is_writable(control, *, class_name: str) -> bool:
    normalized = class_name.casefold()
    native_edit_class = (
        normalized == "edit"
        or normalized.startswith("richedit")
        or normalized in {"scintilla", "richeditd2dpt"}
    )
    if not native_edit_class or sys.platform != "win32":
        return False
    try:
        handle = int(getattr(control, "NativeWindowHandle", 0) or 0)
        if handle <= 0:
            return False
        user32, _, _ = _windows_libraries()
        if not user32.IsWindow(handle) or not user32.IsWindowEnabled(handle):
            return False
        style = int(user32.GetWindowLongW(handle, -16))
        return not bool(style & 0x0800)
    except Exception:
        return False


def _evidence_value(evidence) -> str:
    if isinstance(evidence, EditableEvidence):
        return evidence.value
    return str(evidence or EditableEvidence.NONE.value)


def _integrity_compatible(target_process_id: int) -> bool | None:
    if sys.platform != "win32":
        return False
    current = _process_integrity_level(os.getpid())
    target = _process_integrity_level(int(target_process_id))
    if current is None or target is None:
        return None
    return current >= target


def _process_integrity_level(process_id: int) -> int | None:
    """Return the Windows integrity RID used by UIPI comparisons."""
    try:
        if not 0 < int(process_id) < 0xFFFFFFFF:
            return None
        _, kernel32, advapi32 = _windows_libraries()
        process = kernel32.OpenProcess(0x1000, False, int(process_id))
        if not process:
            return None
        token = ctypes.c_void_p()
        try:
            if not advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
                return None
            required = ctypes.c_ulong()
            advapi32.GetTokenInformation(token, 25, None, 0, ctypes.byref(required))
            if not required.value:
                return None
            buffer = ctypes.create_string_buffer(required.value)
            if not advapi32.GetTokenInformation(
                token,
                25,
                buffer,
                required.value,
                ctypes.byref(required),
            ):
                return None
            sid = ctypes.c_void_p.from_buffer(buffer).value
            if not sid or not advapi32.IsValidSid(sid):
                return None
            count_ptr = advapi32.GetSidSubAuthorityCount(sid)
            if not count_ptr:
                return None
            count = count_ptr.contents.value
            if not count:
                return None
            rid_ptr = advapi32.GetSidSubAuthority(sid, count - 1)
            return int(rid_ptr.contents.value) if rid_ptr else None
        finally:
            if token.value:
                kernel32.CloseHandle(token)
            kernel32.CloseHandle(process)
    except Exception:
        return None
