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
    STREAM_PREVIEW_WINDOW_SECONDS = 18.0
    STREAM_FULL_PREVIEW_MAX_SECONDS = 45.0
    FINAL_SEGMENT_SECONDS = 18.0
    FINAL_SEGMENT_OVERLAP_SECONDS = 1.0
    FINAL_SEGMENT_HOLD_SECONDS = 2.0
    SEGMENTED_FINAL_MIN_SECONDS = 45.0
    FINALIZING_VISIBLE_AFTER_SECONDS = 20.0
    FINAL_TEXT_HOLD_SHORT_MS = 700
    FINAL_TEXT_HOLD_LONG_MS = 1400

    def __init__(self, config_path=None):
        self.base_dir = self._resolve_base_dir(config_path)
        if config_path is None:
            config_path = os.path.join(self.base_dir, "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.config_path = config_path
        self._is_processing = False
        self._actively_recording = False
        self._shutdown_started = False
        self._streaming = False
        self._stream_generation = 0
        self._latest_text = ""  # 后台转写的最新结果
        self._final_segments = []
        self._finalized_audio_len = 0
        self._final_cache_lock = threading.Lock()
        self._transcribe_lock = threading.Lock()
        self.overlay = OverlayWindow()
        self.history = HistoryStore(os.path.join(self.base_dir, "logs", "history.jsonl"))

    def _resolve_base_dir(self, config_path=None):
        if config_path:
            return os.path.dirname(os.path.abspath(config_path))

        dev_root = os.path.dirname(os.path.dirname(__file__))
        if not getattr(sys, "frozen", False):
            return dev_root

        candidates = [
            os.getcwd(),
            os.path.dirname(sys.executable),
            getattr(sys, "_MEIPASS", ""),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(os.path.join(candidate, "config.yaml")):
                return candidate
        return os.path.dirname(sys.executable)

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
            on_output_text=self._output_text,
            on_open_dictionary=self._open_dictionary,
            on_quit=self.shutdown,
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
            self._stream_generation += 1
            generation = self._stream_generation
            self.overlay.show_recording(generation)
            self._latest_text = ""
            self._reset_final_cache()
            self._start_streaming(generation)
            print("[录音] 开始", flush=True)
        except Exception as e:
            self._actively_recording = False
            self.overlay.show_error(str(e))
            print(f"[错误] {e}", flush=True)

    def _on_record_stop(self):
        if not self._actively_recording:
            return
        self._actively_recording = False
        self._is_processing = True
        final_generation = self._stop_streaming()

        try:
            result = self.session.stop()
            data = result.audio_data
            if len(data) == 0:
                self.overlay.show_error("无音频")
                self.overlay.hide_after(2000)
                self._is_processing = False
                return

            duration = result.duration or (len(data) / self.audio.sample_rate)
            if self._should_show_finalizing(duration):
                self.overlay.show_finalizing(final_generation)

            raw_text = self._transcribe_final_text(data)
            text = self.cleaner.clean(raw_text) if raw_text else ""

            # Safety: if final transcription empty but streaming had text, use streaming text
            if not text and self._latest_text:
                text = self.cleaner.clean(self._latest_text)

            if text:
                print(f"[转写] {text} ({duration:.1f}s)", flush=True)
                output_status = self.output_handler.output(text)
                segment_count = len(self._snapshot_final_cache()[0])
                self.history.append(
                    raw_text=raw_text,
                    clean_text=text,
                    corrected_text=text,
                    output_status=output_status,
                    duration=duration,
                    model=self._active_engine_name(),
                    segment_count=segment_count,
                    final_length=len(text),
                    final_tail=text[-10:],
                )
                self.overlay.show_final_text(text, final_generation)
                self.overlay.hide_after(self._final_text_hold_ms(duration))
            else:
                self.overlay.hide_after(0)

        except Exception as e:
            self.overlay.show_error(str(e))
            self.history.append(output_status="error", error=str(e))
            import traceback
            traceback.print_exc()
        finally:
            self._is_processing = False

    def _stream_preview_interval(self, elapsed_seconds):
        if elapsed_seconds < 30:
            return 0.6
        if elapsed_seconds < 120:
            return 2.0
        return 4.0

    def _stream_preview_audio(self, chunk):
        max_samples = int(self.audio.sample_rate * self.STREAM_PREVIEW_WINDOW_SECONDS)
        if max_samples <= 0 or len(chunk) <= max_samples:
            return chunk
        return chunk[-max_samples:]

    def _stream_preview_text(self, chunk, finalized_len=0, *, prefer_complete=False):
        elapsed = len(chunk) / self.audio.sample_rate
        if prefer_complete and elapsed <= self.STREAM_FULL_PREVIEW_MAX_SECONDS:
            return self._transcribe_audio(chunk, blocking=False)

        parts, cached_len = self._snapshot_final_cache()
        if parts and cached_len > 0:
            overlap_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_OVERLAP_SECONDS)
            start = max(0, cached_len - overlap_samples)
            tail = chunk[start:]
            tail_text = self._transcribe_audio(tail, blocking=False) if len(tail) else ""
            if tail_text is None:
                return None
            return self._join_transcript_parts(parts + [tail_text])

        preview_audio = chunk if prefer_complete else self._stream_preview_audio(chunk)
        return self._transcribe_audio(preview_audio, blocking=False)

    def _reset_final_cache(self):
        with self._final_cache_lock:
            self._final_segments = []
            self._finalized_audio_len = 0

    def _next_final_segment(self, chunk, finalized_audio_len):
        segment_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_SECONDS)
        overlap_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_OVERLAP_SECONDS)
        hold_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_HOLD_SECONDS)
        stable_len = max(0, len(chunk) - hold_samples)
        if segment_samples <= 0 or stable_len - finalized_audio_len < segment_samples:
            return None, finalized_audio_len
        start = max(0, finalized_audio_len - overlap_samples)
        end = finalized_audio_len + segment_samples
        return chunk[start:end], end

    def _append_final_segment(self, text, finalized_audio_len):
        if not text:
            return
        with self._final_cache_lock:
            self._final_segments.append(text.strip())
            self._finalized_audio_len = finalized_audio_len

    def _snapshot_final_cache(self):
        lock = getattr(self, "_final_cache_lock", None)
        if lock is None:
            return list(getattr(self, "_final_segments", [])), getattr(self, "_finalized_audio_len", 0)
        with lock:
            return list(self._final_segments), self._finalized_audio_len

    def _join_transcript_parts(self, parts):
        joined = ""
        for part in parts:
            part = (part or "").strip()
            if not part:
                continue
            joined = self._merge_transcript_pair(joined, part) if joined else part
        return joined.strip()

    def _merge_transcript_pair(self, left, right):
        left = (left or "").rstrip()
        right = (right or "").lstrip()
        if not left:
            return right
        if not right:
            return left
        max_overlap = min(len(left), len(right), 80)
        for size in range(max_overlap, 0, -1):
            if left[-size:] == right[:size]:
                return left + right[size:]
        return f"{left} {right}"

    def _should_use_segmented_final(self, data, parts, finalized_audio_len):
        duration = len(data) / self.audio.sample_rate
        return (
            duration >= self.SEGMENTED_FINAL_MIN_SECONDS
            and bool(parts)
            and 0 < finalized_audio_len < len(data)
        )

    def _transcribe_final_text(self, data):
        parts, finalized_audio_len = self._snapshot_final_cache()
        if self._should_use_segmented_final(data, parts, finalized_audio_len):
            overlap_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_OVERLAP_SECONDS)
            tail_start = max(0, finalized_audio_len - overlap_samples)
            tail = data[tail_start:]
            tail_text = self._transcribe_audio(tail) if len(tail) else ""
            return self._join_transcript_parts(parts + [tail_text])
        return self._transcribe_audio(data)

    def _transcribe_audio(self, audio_data, *, blocking=True):
        lock = getattr(self, "_transcribe_lock", None)
        if lock is None:
            return self.transcriber.transcribe(audio_data, self.audio.sample_rate)
        acquired = lock.acquire(blocking=blocking)
        if not acquired:
            return None
        try:
            return self.transcriber.transcribe(audio_data, self.audio.sample_rate)
        finally:
            lock.release()

    def _should_show_finalizing(self, duration):
        return duration >= self.FINALIZING_VISIBLE_AFTER_SECONDS

    def _final_text_hold_ms(self, duration):
        if duration >= self.FINALIZING_VISIBLE_AFTER_SECONDS:
            return self.FINAL_TEXT_HOLD_LONG_MS
        return self.FINAL_TEXT_HOLD_SHORT_MS

    def _active_engine_name(self):
        return self.config.get("engine", {}).get("active", "sensevoice")

    def _start_streaming(self, generation):
        """后台 ASR 线程：录音期间用最近窗口做预览，停止后仍完整转写"""
        self._streaming = True

        last_len = 0
        last_pause_refresh_len = 0
        def loop():
            nonlocal last_len, last_pause_refresh_len
            while self._streaming:
                try:
                    buf = self.audio._audio_buffer
                    if buf:
                        chunk = np.concatenate(buf, axis=0).flatten()
                        _, finalized_len = self._snapshot_final_cache()
                        segment, segment_end = self._next_final_segment(chunk, finalized_len)
                        if segment is not None:
                            segment_text = self._transcribe_audio(segment, blocking=False)
                            if segment_text:
                                self._append_final_segment(segment_text, segment_end)
                            time.sleep(0.05)
                            continue

                        new_samples = len(chunk) - last_len
                        elapsed = len(chunk) / self.audio.sample_rate
                        min_new_seconds = self._stream_preview_interval(elapsed)

                        if new_samples > self.audio.sample_rate * min_new_seconds or last_len == 0:
                            # A pause is a correction point: refresh the visible text instead of skipping it.
                            new_audio = chunk[last_len:] if last_len > 0 else chunk
                            window = min(len(new_audio), self.audio.sample_rate // 2)
                            rms = float(np.sqrt(np.mean(new_audio[-window:].astype(np.float64)**2))) / 32768.0
                            if rms < 0.008 and last_len > 0:
                                if len(chunk) - last_pause_refresh_len >= int(self.audio.sample_rate * 0.8):
                                    text = self._stream_preview_text(
                                        chunk,
                                        finalized_len,
                                        prefer_complete=True,
                                    )
                                    if text is None:
                                        time.sleep(0.25)
                                        continue
                                    last_pause_refresh_len = len(chunk)
                                    if text:
                                        self._latest_text = text
                                        clean = self.cleaner.clean(text)
                                        if clean and generation == self._stream_generation:
                                            self.overlay.update_correction(clean, generation)
                                last_len = len(chunk)
                                time.sleep(0.25)
                                continue
                            text = self._stream_preview_text(
                                chunk,
                                finalized_len,
                                prefer_complete=False,
                            )
                            if text is None:
                                time.sleep(0.25)
                                continue
                            last_len = len(chunk)
                            if text:
                                self._latest_text = text
                                clean = self.cleaner.clean(text)
                                # Filter short English-only hallucinations
                                if clean:
                                    stripped = clean.strip()
                                    ascii_chars = sum(1 for c in stripped if ord(c) < 128)
                                    if ascii_chars == len(stripped) and len(stripped) <= 8:
                                        pass  # skip short English-only (likely hallucination)
                                    else:
                                        if generation == self._stream_generation:
                                            self.overlay.update_streaming(clean, generation)
                except Exception:
                    pass
                time.sleep(0.25)

        self._stream_thread = threading.Thread(target=loop, daemon=True)
        self._stream_thread.start()

    def _stop_streaming(self):
        self._streaming = False
        self._stream_generation += 1
        final_generation = self._stream_generation
        if hasattr(self, "_stream_thread") and self._stream_thread:
            self._stream_thread.join(timeout=0.2)
            self._stream_thread = None
        return final_generation

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
        text = (last.get("corrected_text") or last.get("clean_text", "")) if last else ""
        if text:
            import pyperclip
            pyperclip.copy(text)
            self.overlay.show_result("已复制上一次结果")
            self.overlay.hide_after(1200)

    def _repaste_last_text(self):
        last = self.history.last()
        text = (last.get("corrected_text") or last.get("clean_text", "")) if last else ""
        self._output_text(text)

    def _output_text(self, text):
        if text and hasattr(self, "output_handler"):
            self.output_handler.output(text)

    def _open_dictionary(self):
        os.startfile(os.path.join(self.base_dir, "knowledge-base"))

    # ---- 生命周期 ----

    def start(self):
        ptt_raw = self.config.get("hotkeys", {}).get("push_to_talk", "f2")
        if isinstance(ptt_raw, list):
            ptt = " / ".join(k.upper() for k in ptt_raw)
        else:
            ptt = ptt_raw.upper()
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        print(f"\n  VoiceFlow | {engine} | {ptt.upper()}=录音/停止  Esc=取消\n", flush=True)

        self._install_console_handler()
        self.overlay.start(on_ready=self._on_overlay_ready)
        self.shutdown()

    def _install_console_handler(self):
        if os.name != "nt":
            return
        try:
            import ctypes

            handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            def handler(ctrl_type):
                self.shutdown()
                return False

            self._console_handler_ref = handler_type(handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_handler_ref, True)
        except Exception:
            pass

    def _on_overlay_ready(self):
        from PyQt6.QtCore import QTimer

        def on_done():
            try:
                self._start_hotkeys()
                self.overlay.show_idle()
                self.overlay.show_settings_window()
                print("  说点什么吧", flush=True)
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
        if self._shutdown_started:
            return
        self._shutdown_started = True

        self._stop_streaming()
        if self._actively_recording and hasattr(self, "session"):
            try:
                self.session.cancel()
            except Exception:
                pass
            self._actively_recording = False

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
