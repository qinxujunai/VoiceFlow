"""
ASR 转写模块
使用 sherpa-onnx 加载 SenseVoice / Qwen3-ASR 模型进行语音识别
"""

import os
import yaml
import numpy as np


class Transcriber:
    """sherpa-onnx ASR 转写器"""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.base_dir = os.path.dirname(os.path.abspath(config_path))
        self.recognizer = None
        self.current_engine = None

    def load_engine(self, engine_name=None):
        """加载指定的 ASR 引擎"""
        if engine_name is None:
            engine_name = self.config.get("engine", {}).get("active", "sensevoice")

        engine_cfg = self.config.get("engine", {}).get(engine_name, {})
        if not engine_cfg:
            raise ValueError(f"未找到引擎配置: {engine_name}")

        model_path = os.path.join(self.base_dir, engine_cfg.get("model_path", ""))
        tokens_path = os.path.join(self.base_dir, engine_cfg.get("tokens_path", ""))
        num_threads = int(engine_cfg.get("num_threads", 6))
        provider = engine_cfg.get("provider", "cpu")

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"模型文件不存在: {model_path}\n"
                f"请先运行: python scripts/download_models.py"
            )

        import sherpa_onnx

        # 注意：SenseVoice 不支持 hotwords_file 参数。
        # 热词/错字修正通过 text_cleaner.py 后处理实现（零延迟，零依赖）。

        if engine_name == "sensevoice":
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model_path,
                tokens=tokens_path,
                language=engine_cfg.get("language", "zh"),
                use_itn=engine_cfg.get("use_itn", True),
                num_threads=num_threads,
                provider=provider,
            )
        elif engine_name == "qwen3-asr":
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
                model=model_path,
                tokens=tokens_path,
                num_threads=num_threads,
                provider=provider,
            )
        else:
            raise ValueError(f"不支持的引擎: {engine_name}")

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
        if self.recognizer is None:
            raise RuntimeError("引擎未加载，请先调用 load_engine()")

        if len(audio_data) == 0:
            return ""

        # 转为 float32 归一化
        audio_float = audio_data.astype(np.float32) / 32768.0

        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio_float)
        self.recognizer.decode_stream(stream)
        result = stream.result

        text = result.text.strip()
        # 去除 SenseVoice 可能输出的语言/情感标签
        if self.current_engine == "sensevoice":
            import re
            text = re.sub(r"^<\|[^|]*\|>", "", text).strip()

        return text
