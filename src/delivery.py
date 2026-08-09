"""Truthful clipboard-first delivery and conservative target classification."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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

    def can_receive_paste_from(self, previous: "TargetSnapshot | None") -> bool:
        if previous is None:
            return False
        return (
            self.known
            and previous.known
            and self.editable
            and previous.editable
            and self.integrity_compatible
            and previous.integrity_compatible
            and self.window_handle == previous.window_handle
            and self.process_id == previous.process_id
            and self.element_id == previous.element_id
        )


@dataclass(frozen=True)
class DeliveryResult:
    clipboard_verified: bool
    paste_dispatched: bool
    clipboard_only: bool
    recovery_saved: bool
    reason: str
    attempts: int
    text_sha256: str

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
            )

        current_target = self.inspect_target()
        paste_dispatched = False
        reason = "clipboard_verified"
        if allow_paste and current_target.can_receive_paste_from(start_target):
            try:
                paste_dispatched = bool(self.dispatch_paste())
                reason = "paste_dispatched" if paste_dispatched else "paste_dispatch_failed"
            except Exception:
                reason = "paste_dispatch_failed"
        elif allow_paste:
            reason = "target_changed_or_not_editable"
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


def inspect_current_target() -> TargetSnapshot:
    if sys.platform != "win32":
        return TargetSnapshot(None, None, "", False, False, False)
    try:
        user32 = ctypes.windll.user32
        foreground = int(user32.GetForegroundWindow())
        process_id = ctypes.c_ulong()
        thread_id = int(user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id)))
        uia_target = _inspect_uia_target(
            foreground=foreground,
            foreground_process_id=int(process_id.value),
        )
        if uia_target is not None:
            return uia_target

        class GUITHREADINFO(ctypes.Structure):
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

        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return TargetSnapshot(foreground, int(process_id.value), "", False, False, False)
        focus = int(info.hwndFocus or foreground)
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(focus, buffer, len(buffer))
        class_name = buffer.value
        normalized = class_name.casefold()
        editable = (
            normalized == "edit"
            or normalized.startswith("richedit")
            or normalized in {"scintilla", "richeditd2dpt"}
        )
        return TargetSnapshot(
            foreground,
            int(process_id.value),
            f"{focus}:{class_name}",
            editable,
            _integrity_compatible(int(process_id.value)),
            bool(class_name),
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

        control = automation.GetFocusedControl()
        if control is None:
            return None
        process_id = int(control.ProcessId or foreground_process_id)
        if process_id != foreground_process_id:
            return None
        runtime_id = tuple(int(value) for value in control.GetRuntimeId())
        if not runtime_id:
            return None
        value_pattern = control.GetPattern(automation.PatternId.ValuePattern)
        editable = bool(
            value_pattern is not None
            and not value_pattern.IsReadOnly
            and control.IsEnabled
            and control.IsKeyboardFocusable
        )
        control_type = str(control.ControlTypeName or "Control")
        automation_id = str(control.AutomationId or "")
        runtime = ".".join(str(value) for value in runtime_id)
        return TargetSnapshot(
            window_handle=int(foreground),
            process_id=process_id,
            element_id=f"uia:{control_type}:{automation_id}:{runtime}",
            editable=editable,
            integrity_compatible=_integrity_compatible(process_id),
            known=True,
        )
    except Exception:
        return None


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
