"""
全局快捷键管理。极简：F2 录音，Esc 取消。
"""

import os
import time
import threading
import keyboard
import yaml


class HotkeyManager:

    def __init__(self, config_path=None, callbacks=None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "config.yaml"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        hk_cfg = config.get("hotkeys", {})
        self.ptt_key = hk_cfg.get("push_to_talk", "f2").lower().strip()
        self.cancel_key = hk_cfg.get("cancel", "escape").lower().strip()

        self.callbacks = callbacks or {}
        self._lock = threading.Lock()
        self._last_event_time = 0

    def _on_ptt(self, event):
        if event.event_type != "down":
            return
        now = time.time()
        with self._lock:
            if now - self._last_event_time < 0.5:
                return
            self._last_event_time = now
        cb = self.callbacks.get("on_record_start")
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _on_cancel(self):
        cb = self.callbacks.get("on_record_cancel")
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def start(self):
        keyboard.on_press_key(self.ptt_key, self._on_ptt, suppress=True)
        keyboard.add_hotkey(self.cancel_key, self._on_cancel, suppress=False)
        print(f"[热键] F2=录音, Esc=取消", flush=True)

    def stop(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
