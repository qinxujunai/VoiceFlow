"""
ASR 转写模块
使用 sherpa-onnx 加载 SenseVoice / Qwen3-ASR 模型进行语音识别
"""

import os
import yaml
from engine_adapter import create_engine_adapter


class Transcriber:
    """sherpa-onnx ASR 转写器"""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.base_dir = os.path.dirname(os.path.abspath(config_path))
        self.recognizer = None
        self.adapter = None
        self.current_engine = None

    def load_engine(self, engine_name=None):
        """加载指定的 ASR 引擎"""
        if engine_name is None:
            engine_name = self.config.get("engine", {}).get("active", "sensevoice")

        engine_cfg = self.config.get("engine", {}).get(engine_name, {})
        if not engine_cfg:
            raise ValueError(f"未找到引擎配置: {engine_name}")

        self.adapter = create_engine_adapter(engine_name, engine_cfg, self.base_dir)
        self.adapter.load()
        self.recognizer = self.adapter.recognizer
        self.current_engine = engine_name

    def transcribe(self, audio_data, sample_rate=16000):
        """
        转写音频数据

        Args:
            audio_data: numpy array, int16 格式的音频数据
            sample_rate: 采样率，默认 16000

        Returns:
            str: 转写文字
        """
        if self.adapter is None:
            raise RuntimeError("引擎未加载，请先调用 load_engine()")
        return self.adapter.transcribe(audio_data, sample_rate)
