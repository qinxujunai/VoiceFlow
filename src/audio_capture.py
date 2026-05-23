"""
麦克风音频采集模块
使用 sounddevice 以 16kHz 采样率采集 PCM 音频
"""

import numpy as np
import sounddevice as sd
import threading
import queue
import time
import yaml
import os


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
        self._audio_buffer = []
        self._lock = threading.Lock()
        self._stream = None
        self._recording_start_time = None

        # VAD 状态
        self._last_speech_time = None
        self._on_silence_callback = None

    def start_recording(self):
        """开始录音"""
        if self._is_recording:
            return

        with self._lock:
            self._audio_buffer = []
            self._is_recording = True
            self._recording_start_time = time.time()
            self._last_speech_time = time.time()

        def audio_callback(indata, frames, time_info, status):
            if status:
                pass
            if self._is_recording:
                self._audio_buffer.append(indata.copy())
                # VAD：检查当前帧是否有语音活动
                if self.vad_enabled:
                    energy = np.abs(indata).mean() / 32768.0
                    if energy > self.vad_energy_threshold:
                        self._last_speech_time = time.time()

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
            raise RuntimeError(f"麦克风打开失败: {e}")

    def stop_recording(self):
        """停止录音，返回音频数据 (numpy array, int16)"""
        if not self._is_recording:
            return np.array([], dtype=np.int16)

        with self._lock:
            self._is_recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if not self._audio_buffer:
            return np.array([], dtype=np.int16)

        audio = np.concatenate(self._audio_buffer, axis=0)
        self._audio_buffer = []
        return audio.flatten()

    def cancel_recording(self):
        """取消录音，不返回数据"""
        with self._lock:
            self._is_recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._audio_buffer = []
        self._recording_start_time = None

    def set_silence_callback(self, callback):
        """设置静音超时回调"""
        self._on_silence_callback = callback

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
