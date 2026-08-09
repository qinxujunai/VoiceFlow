"""Verified clipboard-first delivery with conservative paste dispatch."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pyperclip
import yaml

from delivery import (
    DeliveryCoordinator,
    DeliveryResult,
    TargetSnapshot,
    VerifiedClipboard,
    inspect_current_target,
)
from platform_utils import paste_modifier


class OutputHandler:
    """Store text first, verify it, then dispatch paste only to a stable target."""

    def __init__(self, config_path=None, base_dir=None, overlay=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config.yaml",
            )
        with open(config_path, "r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)

        out_cfg = config.get("output", {})
        self.auto_space = bool(out_cfg.get("auto_space", False))
        self.auto_period = bool(out_cfg.get("auto_period", False))
        self.base_dir = Path(
            base_dir
            or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.history_file = str(self.base_dir / "logs" / "history.txt")
        self.overlay = overlay
        self.last_text = ""
        self._coordinator = DeliveryCoordinator(
            clipboard=VerifiedClipboard(copy=pyperclip.copy, paste=pyperclip.paste),
            inspect_target=inspect_current_target,
            dispatch_paste=self._dispatch_paste,
            ledger_dir=self.base_dir / "delivery-pending",
        )
        # Import COM/UIA and build its first focus object during startup, not on
        # the user's first recording trigger where it would delay feedback.
        try:
            inspect_current_target()
        except Exception:
            pass

    def capture_target(self) -> TargetSnapshot:
        return inspect_current_target()

    def deliver(
        self,
        text,
        *,
        start_target: TargetSnapshot | None,
        session_id: str,
        allow_paste: bool = True,
    ) -> DeliveryResult:
        prepared = self._prepare_text(text)
        self.last_text = prepared
        return self._coordinator.deliver(
            prepared,
            start_target=start_target,
            session_id=session_id,
            allow_paste=allow_paste,
        )

    def output(self, text, *, start_target=None, session_id=None):
        if not text:
            return "empty"
        delivery_id = session_id or f"legacy-{uuid.uuid4().hex}"
        result = self.deliver(
            text,
            start_target=start_target or self.capture_target(),
            session_id=delivery_id,
        )
        if result.clipboard_verified:
            self.acknowledge_delivery(delivery_id)
        return result.output_status

    def copy_only(self, text, *, session_id=None):
        if not text:
            return "empty"
        delivery_id = session_id or f"copy-{uuid.uuid4().hex}"
        result = self.deliver(
            text,
            start_target=None,
            session_id=delivery_id,
            allow_paste=False,
        )
        if result.clipboard_verified:
            self.acknowledge_delivery(delivery_id)
        return result.output_status

    def acknowledge_delivery(self, session_id):
        return self._coordinator.acknowledge(str(session_id))

    def recover_pending(self):
        return self._coordinator.recover_pending_to_clipboard()

    def repeat_last(self):
        if not self.last_text:
            return "empty"
        return self.output(self.last_text)

    def _prepare_text(self, text):
        prepared = str(text).strip()
        if (
            self.auto_period
            and prepared
            and prepared[-1] not in "。！？.!?,，；;：:"
        ):
            prepared += "。"
        return prepared

    def _dispatch_paste(self) -> bool:
        # Import only when delivery needs it. PyAutoGUI changes process DPI
        # awareness at import time, which otherwise races Qt's per-monitor setup.
        import pyautogui

        pyautogui.PAUSE = 0.01
        pyautogui.FAILSAFE = False
        pyautogui.hotkey(paste_modifier(), "v")
        return True

    def _paste(self, text):
        """Compatibility wrapper; status still means dispatched, never landed."""
        target = self.capture_target()
        return self.deliver(
            text,
            start_target=target,
            session_id=f"legacy-{uuid.uuid4().hex}",
        ).paste_dispatched

    def _fallback(self, text):
        """Persist legacy callers without claiming clipboard success."""
        path = Path(self.history_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"[{timestamp}] {text}\n")
        return False
