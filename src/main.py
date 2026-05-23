"""
VoiceFlow — 本地语音转文字。F2 切换录音，Esc 取消。
按 F2 开始，说完再按 F2 停止粘贴。后台持续转写，停止时秒出结果。
"""

import os
import sys
import time
import argparse
import threading
import yaml
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from audio_capture import AudioCapture
from transcriber import Transcriber
from hotkey_manager import HotkeyManager
from output_handler import OutputHandler
from overlay_webview import OverlayWindow
from text_cleaner import TextCleaner


class _InitWorker(threading.Thread):
    def __init__(self, system, on_done, on_error):
        super().__init__(daemon=True)
        self.system = system
        self.on_done = on_done
        self.on_error = on_error

    def run(self):
        try:
            self.system._init_modules()
            self.on_done()
        except Exception as e:
            self.on_error(e)


class VoiceInputSystem:

    def __init__(self, config_path=None):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        if config_path is None:
            config_path = os.path.join(self.base_dir, "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.config_path = config_path
        self._is_processing = False
        self._streaming = False
        self._latest_text = ""  # 后台转写的最新结果
        self.overlay = OverlayWindow()

    def _init_modules(self):
        print("[启动] 音频...", flush=True)
        self.audio = AudioCapture(self.config_path)

        print("[启动] ASR...", flush=True)
        self.overlay.show_processing()
        self.transcriber = Transcriber(self.config_path)
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        self.transcriber.load_engine(engine)
        print(f"[启动] {engine}", flush=True)

        self.output_handler = OutputHandler(
            self.config_path, base_dir=self.base_dir, overlay=self.overlay
        )
        self.cleaner = TextCleaner(self.config, base_dir=self.base_dir)
        print("[启动] 就绪", flush=True)

    # ---- 录音 ----

    def _on_record_start(self):
        if self._is_processing:
            return
        try:
            self.audio.start_recording()
            self.overlay.show_window()
            self.overlay.show_recording()
            self._latest_text = ""
            self._start_streaming()
            print("[录音] 开始", flush=True)
        except Exception as e:
            self.overlay.show_error(str(e))
            print(f"[错误] {e}", flush=True)

    def _on_record_stop(self):
        if not self.audio.is_recording:
            return
        self._is_processing = True
        self._stop_streaming()

        try:
            data = self.audio.stop_recording()
            if len(data) == 0:
                self.overlay.show_error("无音频")
                self.overlay.hide_after(2000)
                self._is_processing = False
                return

            duration = len(data) / self.audio.sample_rate

            # 优先用后台累积的转写结果（够新就直接用）
            if self._latest_text and len(self._latest_text) > 2:
                text = self._latest_text
                print(f"[转写] (缓存) {text}", flush=True)
            else:
                self.overlay.show_processing()
                text = self.transcriber.transcribe(data, self.audio.sample_rate)

            if text:
                text = self.cleaner.clean(text)
                rtf = (time.time() - duration) / duration if duration > 0 else 0
                print(f"[转写] {text} ({duration:.1f}s)", flush=True)
                self.overlay.show_result(text)
                self.output_handler.output(text)
                self.overlay.hide_after(3000)
            else:
                self.overlay.show_error("无识别结果")
                self.overlay.hide_after(2000)

        except Exception as e:
            self.overlay.show_error(str(e))
            import traceback
            traceback.print_exc()
        finally:
            self._is_processing = False

    def _start_streaming(self):
        """后台 ASR 线程：录音期间持续转写，停止时结果已就绪"""
        self._streaming = True

        def loop():
            while self._streaming:
                try:
                    buf = self.audio._audio_buffer
                    if buf:
                        chunk = np.concatenate(buf, axis=0).flatten()
                        if len(chunk) > self.audio.sample_rate * 0.5:
                            text = self.transcriber.transcribe(chunk, self.audio.sample_rate)
                            if text:
                                self._latest_text = text
                except Exception:
                    pass
                time.sleep(0.3)

        threading.Thread(target=loop, daemon=True).start()

    def _stop_streaming(self):
        self._streaming = False

    def _on_record_cancel(self):
        if self.audio.is_recording:
            self._stop_streaming()
            self.audio.cancel_recording()
            self.overlay.hide_after(0)
        print("[录音] 已取消", flush=True)

    # ---- 生命周期 ----

    def start(self):
        ptt = self.config.get("hotkeys", {}).get("push_to_talk", "f2")
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        print(f"\n  VoiceFlow | {engine} | {ptt.upper()}=录音/停止  Esc=取消\n", flush=True)

        self.overlay.start(on_ready=self._on_overlay_ready)
        self.shutdown()

    def _on_overlay_ready(self):
        from PyQt6.QtCore import QTimer

        def on_done():
            try:
                self._start_hotkeys()
                print("  按 F2 开始说话", flush=True)
            except Exception as e:
                print(f"[错误] {e}", flush=True)

        def on_error(e):
            import traceback
            traceback.print_exc()

        QTimer.singleShot(100, lambda: _InitWorker(self, on_done, on_error).start())

    def _start_hotkeys(self):
        self.hotkey_mgr = HotkeyManager(
            config_path=self.config_path,
            callbacks={
                "on_record_start": self._on_record_start,
                "on_record_stop": self._on_record_stop,
                "on_record_cancel": self._on_record_cancel,
            },
        )
        self.hotkey_mgr.start()

    def shutdown(self):
        if hasattr(self, "hotkey_mgr"):
            self.hotkey_mgr.stop()
        print("\n[系统] 已退出", flush=True)


# ---- 测试 ----

def test_mode(config_path):
    print("\n=== 测试模式 ===")
    audio = AudioCapture(config_path)
    transcriber = Transcriber(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    engine = config.get("engine", {}).get("active", "sensevoice")
    print(f"引擎: {engine}")
    transcriber.load_engine(engine)

    for i in [3, 2, 1]:
        print(f"{i}...")
        time.sleep(1)
    print("开始!")
    audio.start_recording()
    time.sleep(5)
    data = audio.stop_recording()
    if len(data) == 0:
        print("无音频")
        return
    d = len(data) / audio.sample_rate
    print(f"录音: {d:.1f}s, 转写中...")
    t0 = time.time()
    text = transcriber.transcribe(data, audio.sample_rate)
    print(f"结果: {text}")
    print(f"耗时: {time.time()-t0:.2f}s, RTF: {(time.time()-t0)/d:.3f}")


def main():
    p = argparse.ArgumentParser(description="VoiceFlow")
    p.add_argument("--test", action="store_true")
    p.add_argument("--config", default=None)
    args = p.parse_args()

    config_path = args.config
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config.yaml"
        )

    if args.test:
        test_mode(config_path)
    else:
        VoiceInputSystem(config_path).start()


if __name__ == "__main__":
    main()
