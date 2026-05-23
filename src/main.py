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
from history_store import HistoryStore
from recording_session import RecordingSession


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
        self._actively_recording = False
        self._streaming = False
        self._latest_text = ""  # 后台转写的最新结果
        self.overlay = OverlayWindow()
        self.history = HistoryStore(os.path.join(self.base_dir, "logs", "history.jsonl"))

    def _init_modules(self):
        print("[启动] 音频...", flush=True)
        self.audio = AudioCapture(self.config_path)
        self.session = RecordingSession(self.audio)

        print("[启动] ASR...", flush=True)
        self.overlay.show_processing()
        self.transcriber = Transcriber(self.config_path)
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        self.transcriber.load_engine(engine)
        print(f"[启动] {engine}", flush=True)

        self.output_handler = OutputHandler(
            self.config_path, base_dir=self.base_dir, overlay=self.overlay
        )
        self.overlay.set_actions(
            on_copy_last=self._copy_last_text,
            on_repaste_last=self._repaste_last_text,
            on_open_dictionary=self._open_dictionary,
        )
        self.cleaner = TextCleaner(self.config, base_dir=self.base_dir)
        print("[启动] 就绪", flush=True)

    # ---- 录音 ----

    def _on_record_start(self):
        if self._is_processing or self._actively_recording:
            return
        self._actively_recording = True
        try:
            self.session.start()
            self.overlay.show_window()
            self.overlay.show_recording()
            self._latest_text = ""
            self._start_streaming()
            print("[录音] 开始", flush=True)
        except Exception as e:
            self.overlay.show_error(str(e))
            print(f"[错误] {e}", flush=True)

    def _on_record_stop(self):
        if not self._actively_recording:
            return
        self._actively_recording = False
        self._is_processing = True
        self._stop_streaming()

        try:
            result = self.session.stop()
            data = result.audio_data
            if len(data) == 0:
                self.overlay.show_error("无音频")
                self.overlay.hide_after(2000)
                self._is_processing = False
                return

            raw_text = self.transcriber.transcribe(data, self.audio.sample_rate)
            text = self.cleaner.clean(raw_text) if raw_text else ""

            # Safety: if final transcription empty but streaming had text, use streaming text
            if not text and self._latest_text:
                text = self.cleaner.clean(self._latest_text)

            if text:
                duration = result.duration or (len(data) / self.audio.sample_rate)
                print(f"[杞啓] {text} ({duration:.1f}s)", flush=True)
                output_status = self.output_handler.output(text)
                self.history.append(
                    raw_text=raw_text,
                    clean_text=text,
                    output_status=output_status,
                )
                self.overlay.show_result(text)
                self.overlay.hide_after(280)
            else:
                self.overlay.hide_after(0)

        except Exception as e:
            self.overlay.show_error(str(e))
            self.history.append(output_status="error", error=str(e))
            import traceback
            traceback.print_exc()
        finally:
            self._is_processing = False

    def _start_streaming(self):
        """后台 ASR 线程：录音期间持续转写，停止时结果已就绪"""
        self._streaming = True

        last_len = 0
        def loop():
            nonlocal last_len
            while self._streaming:
                try:
                    buf = self.audio._audio_buffer
                    if buf:
                        chunk = np.concatenate(buf, axis=0).flatten()
                        new_samples = len(chunk) - last_len
                        if new_samples > self.audio.sample_rate * 0.6 or last_len == 0:
                            # Energy gate: skip transcription on silence
                            new_audio = chunk[last_len:] if last_len > 0 else chunk
                            window = min(len(new_audio), self.audio.sample_rate // 2)
                            rms = float(np.sqrt(np.mean(new_audio[-window:].astype(np.float64)**2))) / 32768.0
                            if rms < 0.008 and last_len > 0:
                                continue
                            text = self.transcriber.transcribe(chunk, self.audio.sample_rate)
                            last_len = len(chunk)
                            if text:
                                self._latest_text = text
                                clean = self.cleaner.clean(text)
                                if clean:
                                    self.overlay.update_streaming(clean)
                except Exception:
                    pass
                time.sleep(0.25)

        threading.Thread(target=loop, daemon=True).start()

    def _stop_streaming(self):
        self._streaming = False

    def _final_text_from_cache(self):
        raw_text = (self._latest_text or "").strip()
        if not raw_text:
            return "", "", False
        return raw_text, self.cleaner.clean(raw_text), True

    def _on_record_cancel(self):
        if self._actively_recording:
            self._actively_recording = False
            self._stop_streaming()
            self.session.cancel()
            self.overlay.show_canceled()
            self.overlay.hide_after(800)
        print("[录音] 已取消", flush=True)

    def _copy_last_text(self):
        last = self.history.last()
        text = last.get("clean_text", "") if last else ""
        if text:
            import pyperclip
            pyperclip.copy(text)
            self.overlay.show_result("已复制上一次结果")
            self.overlay.hide_after(1200)

    def _repaste_last_text(self):
        last = self.history.last()
        text = last.get("clean_text", "") if last else ""
        if text and hasattr(self, "output_handler"):
            self.output_handler.output(text)

    def _open_dictionary(self):
        os.startfile(os.path.join(self.base_dir, "knowledge-base"))

    # ---- 生命周期 ----

    def start(self):
        ptt_raw = self.config.get("hotkeys", {}).get("push_to_talk", "f2")
        ptt = ptt_raw if isinstance(ptt_raw, str) else "+".join(ptt_raw)
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        print(f"\n  VoiceFlow | {engine} | {ptt.upper()}=录音/停止  Esc=取消\n", flush=True)

        self.overlay.start(on_ready=self._on_overlay_ready)
        self.shutdown()

    def _on_overlay_ready(self):
        from PyQt6.QtCore import QTimer

        def on_done():
            try:
                self._start_hotkeys()
                self.overlay.show_idle()
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
