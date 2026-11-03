"""
快捷键：F2 / 鼠标侧键 / 右 Ctrl。按住说话、松开结束；或者轻按开始、再按一下结束。Esc 取消。

trigger_mode: auto（默认，按住超过 HOLD_TO_TALK_S 松开即结束，轻按则切换）或 toggle（只用轻按切换）。
"""

import os
import queue
import sys
import time
import threading
import yaml
from pynput import mouse
from pynput import keyboard as pynput_keyboard


class HotkeyManager:
    # A press held this long is hold-to-talk: releasing it stops the recording it started.
    HOLD_TO_TALK_S = 0.3
    TRIGGER_MODES = ("auto", "toggle")

    def __init__(self, config_path=None, callbacks=None, platform_name=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "config.yaml"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        hk_cfg = config.get("hotkeys", {})
        ptt_raw = hk_cfg.get("push_to_talk", "f2")
        if isinstance(ptt_raw, list):
            self.ptt_keys = [k.lower().strip() for k in ptt_raw]
        else:
            self.ptt_keys = [ptt_raw.lower().strip()]
        self.ptt_key = self.ptt_keys[0]  # primary key for display
        self.cancel_key = hk_cfg.get("cancel", "escape").lower().strip()
        self.trigger_mode = "auto"
        self.set_trigger_mode(hk_cfg.get("trigger_mode", "auto"))
        self.hold_to_talk_s = self.HOLD_TO_TALK_S

        self.callbacks = callbacks or {}
        self.platform_name = platform_name or sys.platform
        self._lock = threading.Lock()
        self._pressed_triggers = set()
        # source -> perf_counter of a press that started a recording (hold-to-talk candidates)
        self._start_presses = {}
        self._accepting_intents = True
        # Keep at most one tap waiting behind the callback that is currently
        # changing recording state. A long finalization must never replay a
        # backlog of stale taps as future start/stop actions.
        self._intent_queue = queue.Queue(maxsize=1)
        self._intent_worker = threading.Thread(
            target=self._dispatch_intents,
            name="voiceflow-hotkey-intents",
            daemon=True,
        )
        self._intent_worker.start()
        self._mouse_listener = None
        self._pynput_kb_listener = None
        self._keyboard_backend = None
        # Side-button constants are Windows-specific in pynput. Build the map
        # only from buttons the active backend actually exposes.
        self._mouse_buttons = {}
        for attribute, name in (("x1", "xbutton1"), ("x2", "xbutton2")):
            button = getattr(mouse.Button, attribute, None)
            if button is not None:
                self._mouse_buttons[button] = name

    def _on_ptt(self, event, source=None):
        event_type = getattr(event, "event_type", "")
        if event_type not in {"down", "up"}:
            return
        trigger = source or getattr(event, "name", None) or self.ptt_key
        self._handle_trigger(trigger, pressed=event_type == "down")

    def _trigger_ptt(self):
        """Emit one complete synthetic tap for tests and tray integrations."""
        source = "synthetic"
        self._handle_trigger(source, pressed=True)
        self._handle_trigger(source, pressed=False)

    def set_trigger_mode(self, mode):
        mode = str(mode or "auto").lower().strip()
        self.trigger_mode = mode if mode in self.TRIGGER_MODES else "auto"

    def _handle_trigger(self, source, pressed):
        """Accept physical key edges while rejecting only held-key repeats."""
        source = str(source).lower().strip()
        now = time.perf_counter()
        pressed_at = None
        with self._lock:
            if not self._accepting_intents:
                return False
            if pressed:
                if source in self._pressed_triggers:
                    return False
                self._pressed_triggers.add(source)
            else:
                self._pressed_triggers.discard(source)
                pressed_at = self._start_presses.pop(source, None)
                if (pressed_at is None or self.trigger_mode != "auto"
                        or now - pressed_at < self.hold_to_talk_s):
                    return False
        if not pressed:
            # Hold to talk: this release stops the recording that its press started.
            try:
                self._intent_queue.put_nowait(("release", pressed_at, now))
            except queue.Full:
                return False
            return True
        can_toggle = self.callbacks.get("can_record_toggle")
        if can_toggle and not can_toggle():
            return False
        is_recording = self.callbacks.get("is_recording")
        starts_recording = not (is_recording and is_recording())
        try:
            self._intent_queue.put_nowait(("toggle", now))
        except queue.Full:
            return False
        if starts_recording:
            with self._lock:
                self._start_presses[source] = now
        return True

    def _dispatch_intents(self):
        while True:
            intent = self._intent_queue.get()
            try:
                if intent is None:
                    return
                if intent[0] == "release":
                    callback = self.callbacks.get("on_record_release")
                    if callback:
                        callback(intent[1], intent[2])
                    continue
                can_toggle = self.callbacks.get("can_record_toggle")
                if can_toggle and not can_toggle():
                    continue
                callback = self.callbacks.get("on_record_toggle")
                if callback:
                    callback(intent[1])
            finally:
                self._intent_queue.task_done()

    def _on_mouse_click(self, x, y, button, pressed):
        btn_name = self._mouse_buttons.get(button)
        if btn_name not in self.ptt_keys:
            return
        self._handle_trigger(btn_name, pressed=pressed)

    def _on_cancel(self):
        cb = self.callbacks.get("on_record_cancel")
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _pynput_key_name(self, key):
        mapping = {
            pynput_keyboard.Key.ctrl_r: "right_ctrl",
            pynput_keyboard.Key.esc: "escape",
            pynput_keyboard.Key.f2: "f2",
        }
        return mapping.get(key)

    def _on_pynput_key_press(self, key):
        key_name = self._pynput_key_name(key)
        if key_name == self.cancel_key:
            self._on_cancel()
            return
        if key_name in self.ptt_keys:
            self._handle_trigger(key_name, pressed=True)

    def _on_pynput_key_release(self, key):
        key_name = self._pynput_key_name(key)
        if key_name in self.ptt_keys:
            self._handle_trigger(key_name, pressed=False)

    def _start_pynput_keyboard(self):
        self._pynput_kb_listener = pynput_keyboard.Listener(
            on_press=self._on_pynput_key_press,
            on_release=self._on_pynput_key_release,
        )
        self._pynput_kb_listener.start()

    def _start_windows_keyboard(self, keyboard_keys, needs_right_ctrl):
        import keyboard

        self._keyboard_backend = keyboard
        for key in keyboard_keys:
            keyboard.on_press_key(
                key,
                lambda event, trigger=key: self._on_ptt(event, trigger),
                suppress=True,
            )
            keyboard.on_release_key(
                key,
                lambda event, trigger=key: self._on_ptt(event, trigger),
                suppress=True,
            )
        if needs_right_ctrl:
            self._start_pynput_keyboard()
        keyboard.add_hotkey(self.cancel_key, self._on_cancel, suppress=False)

    def start(self):
        mouse_keys = [
            key for key in self.ptt_keys if key in self._mouse_buttons.values()
        ]
        kb_keys = [k for k in self.ptt_keys if k not in mouse_keys and k != "right_ctrl"]

        if self.platform_name == "win32":
            # pynput distinguishes right Ctrl on Windows while keyboard handles
            # suppressed single-key triggers and the cancel shortcut.
            self._start_windows_keyboard(kb_keys, "right_ctrl" in self.ptt_keys)
        else:
            # keyboard requires privileged device access on macOS. pynput uses
            # the system Input Monitoring / Accessibility permission instead.
            self._start_pynput_keyboard()

        if mouse_keys:
            self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
            self._mouse_listener.start()

        display_keys = " / ".join(k.upper() for k in self.ptt_keys)
        print(f"[热键] {display_keys}=录音, {self.cancel_key.upper()}=取消", flush=True)

    def stop(self):
        with self._lock:
            should_stop_worker = self._accepting_intents
            self._accepting_intents = False
            self._pressed_triggers.clear()
        if should_stop_worker:
            while True:
                try:
                    self._intent_queue.get_nowait()
                    self._intent_queue.task_done()
                except queue.Empty:
                    break
            self._intent_queue.put_nowait(None)
        if self._keyboard_backend is not None:
            try:
                self._keyboard_backend.unhook_all()
            except Exception:
                pass
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._pynput_kb_listener:
            try:
                self._pynput_kb_listener.stop()
            except Exception:
                pass
        if (
            should_stop_worker
            and threading.current_thread() is not self._intent_worker
        ):
            self._intent_worker.join(timeout=0.5)
