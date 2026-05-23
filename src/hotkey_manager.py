"""
快捷键：F2 切换录音（按一下开始，再按一下停止），Esc 取消。
"""

import os
import time
import threading
import keyboard
import yaml
from pynput import mouse


class HotkeyManager:

    def __init__(self, config_path=None, callbacks=None):
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
        self._recording = False
        self._lock = threading.Lock()
        self._last_event_time = 0
        self._mouse_listener = None
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
        with self._lock:
            if now - self._last_event_time < 0.5:
                return
            self._last_event_time = now
            self._recording = not self._recording
            cb_name = "on_record_start" if self._recording else "on_record_stop"
        cb = self.callbacks.get(cb_name)
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _on_mouse_click(self, x, y, button, pressed):
        if not pressed:
            return
        btn_name = self._mouse_buttons.get(button)
        if btn_name not in self.ptt_keys:
            return
        now = time.time()
        with self._lock:
            if now - self._last_event_time < 0.5:
                return
            self._last_event_time = now
            self._recording = not self._recording
            cb_name = "on_record_start" if self._recording else "on_record_stop"
        cb = self.callbacks.get(cb_name)
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _on_cancel(self):
        with self._lock:
            if self._recording:
                self._recording = False
        cb = self.callbacks.get("on_record_cancel")
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def start(self):
        mouse_keys = [k for k in self.ptt_keys if k in ("xbutton1", "xbutton2", "mouse4", "mouse5")]
        kb_keys = [k for k in self.ptt_keys if k not in ("xbutton1", "xbutton2", "mouse4", "mouse5")]
        for key in kb_keys:
            keyboard.on_press_key(key, self._on_ptt, suppress=True)
        if mouse_keys:
            self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
            self._mouse_listener.start()
        keyboard.add_hotkey(self.cancel_key, self._on_cancel, suppress=False)
        display_keys = "+".join(k.upper() for k in self.ptt_keys)
        print(f"[热键] {display_keys}=录音, {self.cancel_key.upper()}=取消", flush=True)

    def stop(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass

    @property
    def is_recording(self):
        return self._recording
