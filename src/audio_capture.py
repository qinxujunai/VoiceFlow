"""
麦克风音频采集模块
使用 sounddevice 以 16kHz 采样率采集 PCM 音频
"""

import os
import queue
import threading
import time
from bisect import bisect_left, bisect_right

import numpy as np
import sounddevice as sd
import yaml


class AudioCapture:
    """麦克风音频采集器（含能量 VAD）"""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        audio_cfg = config.get("audio", {})
        self.sample_rate = audio_cfg.get("sample_rate", 16000)
        self.channels = audio_cfg.get("channels", 1)
        self.dtype = audio_cfg.get("dtype", "int16")
        self.device_index = audio_cfg.get("device_index", None)

        # VAD 配置
        vad_cfg = config.get("vad", {})
        self.vad_enabled = vad_cfg.get("enabled", True)
        self.vad_silence_timeout = vad_cfg.get("silence_timeout", 1.5)
        self.vad_min_recording = vad_cfg.get("min_recording", 1.0)
        self.vad_energy_threshold = vad_cfg.get("energy_threshold", 0.02)

        # 录音状态
        self._is_recording = False
        self._is_frozen = False
        self._audio_buffer = []
        self._audio_buffer_ends = []
        self._buffer_start_sample = 0
        self._total_samples = 0
        self._last_buffer_start_sample = 0
        self._last_total_samples = 0
        self._lock = threading.Lock()
        self._stream = None
        self._recording_start_time = None
        self._analysis_queue = None
        self._analysis_stop = None
        self._analysis_thread = None
        self._callback_status_count = 0
        self._recovery_sink = None
        self._recovery_drop_count = 0

        # VAD 状态
        self._last_speech_time = None
        self._on_silence_callback = None
        self._on_level_callback = None

    def start_recording(self):
        """开始录音"""
        if self._is_recording:
            return

        with self._lock:
            self._audio_buffer = []
            self._audio_buffer_ends = []
            self._buffer_start_sample = 0
            self._total_samples = 0
            self._last_buffer_start_sample = 0
            self._last_total_samples = 0
            self._is_recording = True
            self._is_frozen = False
            self._recording_start_time = time.time()
            self._last_speech_time = time.time()
            self._callback_status_count = 0
            self._recovery_drop_count = 0

        self._start_analysis_worker()

        def audio_callback(indata, _frames, _time_info, status):
            if status:
                self._callback_status_count += 1
            if self._is_recording:
                block = indata.copy()
                with self._lock:
                    if not self._is_recording:
                        return
                    self._audio_buffer.append(block)
                    self._total_samples += len(block)
                    self._audio_buffer_ends.append(self._total_samples)
                recovery_sink = self._recovery_sink
                if recovery_sink is not None and not recovery_sink.append_pcm(block):
                    self._recovery_drop_count += 1
                self._enqueue_analysis(block)

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                device=self.device_index,
                blocksize=int(self.sample_rate * 0.1),  # 100ms blocks
                callback=audio_callback,
            )
            self._stream.start()
        except Exception as e:
            self._is_recording = False
            self._stop_analysis_worker()
            raise RuntimeError(f"麦克风打开失败: {e}")

    def freeze_recording(self):
        """Atomically stop accepting PCM and latch the authoritative boundary."""
        with self._lock:
            if not self._is_recording:
                return self._last_total_samples if self._is_frozen else 0
            self._is_recording = False
            self._is_frozen = True
            self._last_buffer_start_sample = self._buffer_start_sample
            self._last_total_samples = self._total_samples
            return self._last_total_samples

    def stop_recording(self):
        """Close the device and return PCM captured through the frozen boundary."""
        if not self._is_recording and not self._is_frozen:
            return np.array([], dtype=np.int16)
        if self._is_recording:
            self.freeze_recording()

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._stop_analysis_worker()

        with self._lock:
            blocks = self._audio_buffer
            self._last_buffer_start_sample = self._buffer_start_sample
            self._last_total_samples = self._total_samples
            self._audio_buffer = []
            self._audio_buffer_ends = []
            self._buffer_start_sample = 0
            self._total_samples = 0
            self._is_frozen = False
        if not blocks:
            return np.array([], dtype=np.int16)

        audio = np.concatenate(blocks, axis=0)
        return audio.flatten()

    def cancel_recording(self):
        """取消录音，不返回数据"""
        with self._lock:
            self._is_recording = False
            self._is_frozen = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._stop_analysis_worker()
        with self._lock:
            self._audio_buffer = []
            self._audio_buffer_ends = []
            self._buffer_start_sample = 0
            self._total_samples = 0
        self._recording_start_time = None

    def set_silence_callback(self, callback):
        """设置静音超时回调"""
        self._on_silence_callback = callback

    def set_level_callback(self, callback):
        """Receive three real RMS samples for the compact recording meter."""
        self._on_level_callback = callback

    def set_recovery_sink(self, sink):
        """Attach a queue-backed recovery journal; the callback never writes disk."""
        self._recovery_sink = sink

    def _start_analysis_worker(self):
        analysis_queue = queue.Queue(maxsize=1)
        stop_event = threading.Event()
        self._analysis_queue = analysis_queue
        self._analysis_stop = stop_event

        def run():
            while not stop_event.is_set() or not analysis_queue.empty():
                try:
                    block = analysis_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if block is None:
                    break
                self._process_analysis_block(block)

        self._analysis_thread = threading.Thread(target=run, daemon=True)
        self._analysis_thread.start()

    def _stop_analysis_worker(self):
        stop_event = self._analysis_stop
        if stop_event is not None:
            stop_event.set()
        analysis_queue = self._analysis_queue
        if analysis_queue is not None:
            try:
                analysis_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                analysis_queue.put_nowait(None)
            except queue.Full:
                pass
        thread = self._analysis_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=0.05)
        self._analysis_thread = None
        self._analysis_stop = None
        self._analysis_queue = None

    def _enqueue_analysis(self, block):
        analysis_queue = self._analysis_queue
        if analysis_queue is None:
            return
        try:
            analysis_queue.put_nowait(block)
        except queue.Full:
            try:
                analysis_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                analysis_queue.put_nowait(block)
            except queue.Full:
                pass

    def _process_analysis_block(self, block):
        mono = block.reshape(-1).astype(np.float32) / 32768.0
        if self._on_level_callback is not None:
            windows = np.array_split(mono, 3)
            levels = [
                float(np.sqrt(np.mean(window * window))) if len(window) else 0.0
                for window in windows
            ]
            try:
                self._on_level_callback(levels)
            except Exception:
                pass
        if self.vad_enabled and float(np.abs(mono).mean()) > self.vad_energy_threshold:
            self._last_speech_time = time.time()

    def check_silence(self):
        """
        检查是否静音超时。
        返回 True 表示应该自动停止录音。
        """
        if not self._is_recording or not self.vad_enabled:
            return False
        elapsed = time.time() - (self._recording_start_time or 0)
        if elapsed < self.vad_min_recording:
            return False
        silence_duration = time.time() - (self._last_speech_time or 0)
        return silence_duration >= self.vad_silence_timeout

    @property
    def is_recording(self):
        return self._is_recording

    @property
    def is_frozen(self):
        return self._is_frozen

    @property
    def sample_count(self):
        with self._lock:
            return self._total_samples

    @property
    def buffer_start_sample(self):
        with self._lock:
            return self._buffer_start_sample

    @property
    def last_buffer_start_sample(self):
        with self._lock:
            return self._last_buffer_start_sample

    @property
    def last_total_samples(self):
        with self._lock:
            return self._last_total_samples

    @property
    def callback_status_count(self):
        return self._callback_status_count

    @property
    def recovery_drop_count(self):
        return self._recovery_drop_count

    def snapshot_audio(self, start_sample=0, end_sample=None):
        """Copy only the requested mono PCM range from the growing recording."""
        with self._lock:
            total = self._total_samples
            available_start = getattr(self, "_buffer_start_sample", 0)
            start = max(available_start, min(int(start_sample), total))
            end = total if end_sample is None else max(start, min(int(end_sample), total))
            if start >= end or not self._audio_buffer:
                return np.array([], dtype=np.int16)
            first = bisect_right(self._audio_buffer_ends, start)
            last = bisect_left(self._audio_buffer_ends, end) + 1
            blocks = tuple(self._audio_buffer[first:last])
            base = available_start if first == 0 else self._audio_buffer_ends[first - 1]
        if not blocks:
            return np.array([], dtype=np.int16)
        selected = np.concatenate(blocks, axis=0).flatten()
        return selected[start - base:end - base].copy()

    def discard_before(self, sample_index):
        """Release complete PCM blocks older than a globally indexed sample."""
        with self._lock:
            target = max(self._buffer_start_sample, min(int(sample_index), self._total_samples))
            drop_count = bisect_right(self._audio_buffer_ends, target)
            if drop_count <= 0:
                return self._buffer_start_sample
            self._buffer_start_sample = self._audio_buffer_ends[drop_count - 1]
            del self._audio_buffer[:drop_count]
            del self._audio_buffer_ends[:drop_count]
            return self._buffer_start_sample

    @staticmethod
    def list_devices():
        """列出所有音频输入设备"""
        devices = sd.query_devices()
        input_devices = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                input_devices.append({
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "sample_rate": d["default_samplerate"],
                })
        return input_devices
