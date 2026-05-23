"""
VoiceFlow — 本地语音转文字工具
按 F2 说话，安静 1.5 秒自动停止粘贴。免费、开源、离线。

使用方式:
  python src/main.py              # 正常启动
  python src/main.py --test       # 测试模式（录音 5 秒并转写）
"""

import os
import sys
import time
import argparse
import threading
import yaml

sys.path.insert(0, os.path.dirname(__file__))

from audio_capture import AudioCapture
from transcriber import Transcriber
from hotkey_manager import HotkeyManager
from output_handler import OutputHandler
from overlay_webview import OverlayWindow
from text_cleaner import TextCleaner


class _InitWorker(threading.Thread):
    """后台线程：加载 ASR 引擎（不阻塞 Qt）"""

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
        self._stream_thread = None
        self.overlay = OverlayWindow()

    def _init_modules(self):
        print("[启动] 音频采集...", flush=True)
        self.audio = AudioCapture(self.config_path)

        print("[启动] ASR 引擎...", flush=True)
        self.overlay.show_transcribing()
        self.transcriber = Transcriber(self.config_path)
        engine_name = self.config.get("engine", {}).get("active", "sensevoice")
        self.transcriber.load_engine(engine_name)
        print(f"[启动] 引擎: {engine_name}", flush=True)

        self.output_handler = OutputHandler(
            self.config_path, base_dir=self.base_dir, overlay=self.overlay
        )
        self.cleaner = TextCleaner(self.config, base_dir=self.base_dir)

        self.overlay.show_ready()
        print("[启动] 就绪", flush=True)

    # ---- 录音 ----

    def _on_record_start(self):
        if self._is_processing:
            return
        try:
            self.audio.start_recording()
            self.overlay.show_recording()
            self.overlay.show_for_recording()
            self._start_streaming()
            print("[录音] 开始", flush=True)
        except Exception as e:
            self.overlay.show_error(str(e))
            print(f"[错误] {e}", flush=True)

    def _start_streaming(self):
        self._streaming = True

        def loop():
            while self._streaming:
                try:
                    # VAD 静音检测 → 自动停止
                    if self.audio.check_silence():
                        self._is_processing = True
                        self._stop_streaming()
                        self._finish()
                        return

                    buf = self.audio._audio_buffer
                    if buf:
                        import numpy as np
                        chunk = np.concatenate(buf, axis=0).flatten()
                        if len(chunk) > self.audio.sample_rate * 0.5:
                            text = self.transcriber.transcribe(chunk, self.audio.sample_rate)
                            if text and self._streaming:
                                text = self.cleaner.clean(text)
                                self.overlay.update_streaming(text)
                except Exception:
                    pass
                time.sleep(0.4)

        self._stream_thread = threading.Thread(target=loop, daemon=True)
        self._stream_thread.start()

    def _stop_streaming(self):
        self._streaming = False

    def _finish(self):
        try:
            data = self.audio.stop_recording()
            if len(data) == 0:
                self.overlay.show_error("无音频")
                self._is_processing = False
                return

            duration = len(data) / self.audio.sample_rate
            print(f"[VAD] 静音停止, {duration:.1f}s", flush=True)
            self.overlay.show_transcribing()

            t0 = time.time()
            text = self.transcriber.transcribe(data, self.audio.sample_rate)
            elapsed = time.time() - t0

            if text:
                text = self.cleaner.clean(text)
                rtf = elapsed / duration if duration > 0 else 0
                print(f"[转写] {text} ({elapsed:.2f}s, RTF={rtf:.3f})", flush=True)
                self.overlay.show_result(text)
                self.overlay.hide_after_result()
                self.output_handler.output(text)
            else:
                self.overlay.show_error("无识别结果")
        except Exception as e:
            self.overlay.show_error(str(e))
            import traceback
            traceback.print_exc()
        finally:
            self._is_processing = False

    # ---- 取消 ----

    def _on_record_cancel(self):
        self._stop_streaming()
        self.audio.cancel_recording()
        self.overlay.show_cancelled()
        print("[录音] 已取消", flush=True)

    # ---- 生命周期 ----

    def start(self):
        ptt = self.config.get("hotkeys", {}).get("push_to_talk", "f2")
        cancel = self.config.get("hotkeys", {}).get("cancel", "escape")
        engine = self.config.get("engine", {}).get("active", "sensevoice")

        print("", flush=True)
        print(f"  VoiceFlow | 引擎={engine} | {ptt.upper()}=录音 {cancel}=取消", flush=True)
        print("", flush=True)

        self.overlay.start(on_ready=self._on_overlay_ready)
        self.shutdown()

    def _on_overlay_ready(self):
        from PyQt6.QtCore import QTimer

        def on_done():
            try:
                self._start_hotkeys()
                print("  按 F2 开始说话", flush=True)
            except Exception as e:
                print(f"[错误] 热键启动失败: {e}", flush=True)
                self.overlay.show_error(str(e))

        def on_error(e):
            print(f"[错误] 初始化失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.overlay.show_error(str(e))

        QTimer.singleShot(100, lambda: _InitWorker(self, on_done, on_error).start())

    def _start_hotkeys(self):
        self.hotkey_mgr = HotkeyManager(
            config_path=self.config_path,
            callbacks={
                "on_record_start": self._on_record_start,
                "on_record_cancel": self._on_record_cancel,
            },
        )
        self.hotkey_mgr.start()

    def shutdown(self):
        if hasattr(self, "hotkey_mgr"):
            self.hotkey_mgr.stop()
        print("\n[系统] 已退出", flush=True)


# ---- 测试模式 ----

def test_mode(config_path):
    print("\n" + "=" * 50)
    print("  测试模式 — 录制 5 秒音频并转写")
    print("=" * 50)

    audio = AudioCapture(config_path)
    transcriber = Transcriber(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    engine = config.get("engine", {}).get("active", "sensevoice")

    print(f"\n加载引擎: {engine}")
    transcriber.load_engine(engine)

    for i in [3, 2, 1]:
        print(f"{i}...")
        time.sleep(1)
    print("开始！")

    audio.start_recording()
    time.sleep(5)
    data = audio.stop_recording()

    if len(data) == 0:
        print("[错误] 未采集到音频")
        return

    duration = len(data) / audio.sample_rate
    print(f"\n录音完成: {duration:.1f}s")

    print("转写中...")
    t0 = time.time()
    text = transcriber.transcribe(data, audio.sample_rate)
    elapsed = time.time() - t0

    print(f"\n结果: {text}")
    print(f"耗时: {elapsed:.2f}s, RTF: {elapsed/duration:.3f}")


def main():
    parser = argparse.ArgumentParser(description="VoiceFlow — 本地语音转文字")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args()

    config_path = args.config
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config.yaml"
        )

    if args.test:
        test_mode(config_path)
    else:
        system = VoiceInputSystem(config_path)
        system.start()


if __name__ == "__main__":
    main()
