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
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable


logger = logging.getLogger("voiceflow.delivery")

_SYSTEM_SURFACE_CLASSES = {
    "progman",
    "workerw",
    "shell_traywnd",
    "shell_secondarytraywnd",
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
    integrity_compatible: bool
    known: bool
    editable_evidence: EditableEvidence = EditableEvidence.NONE
    provider: str = ""
    control_type: str = ""
    rejection_reason: str = ""
    runtime_id: str = ""
    foreground_class: str = ""
    focus_window_handle: int | None = None
    caret_window_handle: int | None = None

    @property
    def classification(self) -> TargetClassification:
        if (
            not self.known
            or not self.window_handle
            or not self.process_id
            or not self.integrity_compatible
            or self.rejection_reason in {"password", "secure_desktop", "own_process"}
            or self.foreground_class.casefold() in _SYSTEM_SURFACE_CLASSES
        ):
            return TargetClassification.DEFINITELY_BLOCKED
        if self.editable:
            return TargetClassification.EDITABLE
        return TargetClassification.TRANSIENT_UNKNOWN

    def paste_decision_from(self, previous: "TargetSnapshot | None") -> TargetDecision:
        if not self.known:
            return TargetDecision(False, "stop_target_unknown")
        if not self.window_handle or not self.process_id:
            return TargetDecision(False, "stop_target_unknown")
        if not self.integrity_compatible:
            return TargetDecision(False, "target_integrity_incompatible")
        if self.foreground_class.casefold() in _SYSTEM_SURFACE_CLASSES:
            return TargetDecision(False, "system_surface")
        if self.rejection_reason in {"password", "secure_desktop", "own_process"}:
            return TargetDecision(False, self.rejection_reason)
        return TargetDecision(True, "current_foreground_target")

    def can_receive_paste_from(self, previous: "TargetSnapshot | None") -> bool:
        return self.paste_decision_from(previous).allowed


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
        max_observations: int = 64,
        poll_interval: float = 0.25,
    ):
        self._inspector = inspector or inspect_current_target
        self._initializer = initializer or _mta_initializer
        self._subscriber = subscriber or _uia_focus_subscription
        self._observations = deque(maxlen=max(1, int(max_observations)))
        self._poll_interval = max(0.01, float(poll_interval))
        self._requests = queue.Queue()
        self._lock = threading.Lock()
        self._active = threading.Event()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._focus_event_marker = object()
        self._focus_event_pending = threading.Event()
        self._focus_event_lock = threading.Lock()

    def start_tracking(self) -> TargetObservation:
        self.warmup()
        self._active.set()
        return self.observe()

    def warmup(self, timeout: float = 1.0) -> bool:
        self._ensure_started()
        return self._ready.wait(max(0.0, float(timeout)))

    def stop_tracking(self):
        self._active.clear()

    def observe(self, timeout: float = 0.25) -> TargetObservation:
        self._ensure_started()
        completed = threading.Event()
        result = []
        self._requests.put((completed, result))
        if completed.wait(max(0.0, float(timeout))) and result:
            return result[0]
        return TargetObservation.from_snapshot(
            TargetSnapshot(None, None, "", False, False, False),
        )

    def trace(self) -> tuple[TargetObservation, ...]:
        with self._lock:
            return tuple(self._observations)

    def shutdown(self):
        self._stop.set()
        self._active.set()
        self._requests.put(None)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
        self._ready.clear()

    def _ensure_started(self):
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
                    completed, result = request
                    observation = self._sample()
                    result.append(observation)
                    completed.set()

    def _notify_focus_changed(self):
        if self._stop.is_set():
            return
        with self._focus_event_lock:
            if self._focus_event_pending.is_set():
                return
            self._focus_event_pending.set()
            self._requests.put(self._focus_event_marker)

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

    @property
    def output_status(self) -> str:
        if self.paste_dispatched:
            return "clipboard_verified_paste_dispatched"
        if self.clipboard_verified:
            return "clipboard_verified_only"
        if self.recovery_saved:
            return "recovery_saved_clipboard_unavailable"
        return "delivery_failed"


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
    ):
        self.clipboard = clipboard
        self.inspect_target = inspect_target
        self.dispatch_paste = dispatch_paste
        self.ledger_dir = Path(ledger_dir)

    def deliver(
        self,
        text: str,
        *,
        start_target: TargetSnapshot | None,
        session_id: str,
        allow_paste: bool = True,
    ) -> DeliveryResult:
        prepared = str(text).strip()
        digest = hashlib.sha256(prepared.encode("utf-8")).hexdigest()
        self._write_pending(session_id, prepared, digest)
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
        if allow_paste and decision.allowed:
            try:
                paste_dispatched = bool(self.dispatch_paste())
                reason = "paste_dispatched" if paste_dispatched else "paste_dispatch_failed"
            except Exception:
                reason = "paste_dispatch_failed"
        elif allow_paste:
            reason = decision.reason
        else:
            reason = "clipboard_only_requested"

        return DeliveryResult(
            clipboard_verified=True,
            paste_dispatched=paste_dispatched,
            clipboard_only=not paste_dispatched,
            recovery_saved=False,
            reason=reason,
            attempts=clipboard_result.attempts,
            text_sha256=digest,
            target_evidence=_evidence_value(current_target.editable_evidence),
        )

    def acknowledge(self, session_id: str) -> bool:
        path = self._ledger_path(session_id)
        if path is None:
            return False
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

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
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "session_id": str(session_id),
                    "text": text,
                    "text_sha256": digest,
                    "created_at": time.time(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
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


def _window_class(user32, window_handle: int) -> str:
    if not window_handle:
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(window_handle, buffer, len(buffer))
    return buffer.value


def inspect_current_target() -> TargetSnapshot:
    if sys.platform != "win32":
        return TargetSnapshot(None, None, "", False, False, False)
    try:
        user32 = ctypes.windll.user32
        foreground = int(user32.GetForegroundWindow())
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
                rejection_reason=(
                    "own_process" if own_process else uia_target.rejection_reason
                ),
            )

        class_name = _window_class(user32, focus)
        normalized = class_name.casefold()
        style = int(user32.GetWindowLongW(focus, -16))
        editable = (
            bool(user32.IsWindowEnabled(focus))
            and not style & 0x0800
            and (
                normalized == "edit"
                or normalized.startswith("richedit")
                or normalized in {"scintilla", "richeditd2dpt"}
            )
        )
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
                else "" if editable else "not_editable"
            ),
            "",
            foreground_class,
            focus,
            caret or None,
        )
    except Exception:
        return TargetSnapshot(None, None, "", False, False, False)


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
        if enabled and accepts_focus and (focusable or contains_focused_descendant) and not password:
            evidence = _editable_uia_evidence(
                automation,
                control,
                control_type=control_type,
                class_name=class_name,
            )
        editable = evidence is not EditableEvidence.NONE
        runtime = ".".join(str(value) for value in runtime_id)
        if not enabled:
            rejection_reason = "disabled"
        elif password:
            rejection_reason = "password"
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
        )
    except Exception:
        return None


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
        user32 = ctypes.windll.user32
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


def _integrity_compatible(target_process_id: int) -> bool:
    if sys.platform != "win32":
        return False
    current = _process_integrity_level(os.getpid())
    target = _process_integrity_level(int(target_process_id))
    return current is not None and target is not None and current >= target


def _process_integrity_level(process_id: int) -> int | None:
    """Return the Windows integrity RID used by UIPI comparisons."""
    try:
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
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
            count_ptr = advapi32.GetSidSubAuthorityCount(sid)
            count = ctypes.cast(count_ptr, ctypes.POINTER(ctypes.c_ubyte)).contents.value
            rid_ptr = advapi32.GetSidSubAuthority(sid, count - 1)
            return int(ctypes.cast(rid_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value)
        finally:
            if token.value:
                kernel32.CloseHandle(token)
            kernel32.CloseHandle(process)
    except Exception:
        return None
