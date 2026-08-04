"""
快捷键：F2 / 鼠标侧键 / 右 Ctrl 切换录音（按一下开始，再按一下停止），Esc 取消。
"""

import os
import sys
import time
import threading
import yaml
from pynput import mouse
from pynput import keyboard as pynput_keyboard


class HotkeyManager:

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

        self.callbacks = callbacks or {}
        self.platform_name = platform_name or sys.platform
        self._lock = threading.Lock()
        self._last_event_time = 0
        self._mouse_listener = None
        self._pynput_kb_listener = None
        self._keyboard_backend = None
        # Map pynput mouse buttons to config names
        self._mouse_buttons = {
            mouse.Button.x1: "xbutton1",
            mouse.Button.x2: "xbutton2",
        }

    def _on_ptt(self, event):
        if event.event_type != "down":
            return
        self._trigger_ptt()

    def _trigger_ptt(self):
        now = time.time()
        event_time = time.perf_counter()
        with self._lock:
            if now - self._last_event_time < 0.5:
                return
            self._last_event_time = now
        cb = self.callbacks.get("on_record_toggle")
        if cb:
            threading.Thread(target=cb, args=(event_time,), daemon=True).start()

    def _on_mouse_click(self, x, y, button, pressed):
        if not pressed:
            return
        btn_name = self._mouse_buttons.get(button)
        if btn_name not in self.ptt_keys:
            return
        self._trigger_ptt()

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
            self._trigger_ptt()

    def _start_pynput_keyboard(self):
        self._pynput_kb_listener = pynput_keyboard.Listener(
            on_press=self._on_pynput_key_press
        )
        self._pynput_kb_listener.start()

    def _start_windows_keyboard(self, keyboard_keys, needs_right_ctrl):
        import keyboard

        self._keyboard_backend = keyboard
        for key in keyboard_keys:
            keyboard.on_press_key(key, self._on_ptt, suppress=True)
        if needs_right_ctrl:
            self._start_pynput_keyboard()
        keyboard.add_hotkey(self.cancel_key, self._on_cancel, suppress=False)

    def start(self):
        mouse_keys = [k for k in self.ptt_keys if k in ("xbutton1", "xbutton2", "mouse4", "mouse5")]
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
