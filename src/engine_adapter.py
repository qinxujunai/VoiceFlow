"""Stable, offline ASR engine contracts used by VoiceFlow."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EngineCapabilities:
    languages: tuple[str, ...]
    offline: bool = True
    supports_hotwords: bool = False
    supports_language_hint: bool = False


class EngineAdapter(ABC):
    name: str
    capabilities: EngineCapabilities

    def __init__(
        self,
        config: dict[str, Any],
        base_dir: str | Path,
        *,
        asset_roots: Iterable[str | Path] | None = None,
    ):
        self.config = config
        self.base_dir = Path(base_dir)
        roots = tuple(Path(root) for root in (asset_roots or (self.base_dir,)))
        self.asset_roots = roots or (self.base_dir,)
        self.recognizer = None

    def _asset(self, key: str, label: str, *, directory: bool = False) -> str:
        raw_path = str(self.config.get(key, "")).strip()
        if raw_path:
            configured = Path(raw_path)
            candidates = (
                (configured,)
                if configured.is_absolute()
                else tuple(root / configured for root in self.asset_roots)
            )
            for path in candidates:
                exists = path.is_dir() if directory else path.is_file()
                if exists:
                    return str(path)
        kind = "目录" if directory else "文件"
        fallback = self.asset_roots[0] / raw_path
        raise FileNotFoundError(
            f"{label} {kind}不存在: {fallback}\n"
            "请在 VoiceFlow 设置中检查或修复本地模型"
        )

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError

    def transcribe(self, audio_data, sample_rate: int = 16000) -> str:
        if self.recognizer is None:
            raise RuntimeError("引擎未加载，请先调用 load_engine()")
        if len(audio_data) == 0:
            return ""

        audio_array = np.asarray(audio_data)
        if np.issubdtype(audio_array.dtype, np.integer):
            audio_float = audio_array.astype(np.float32) / 32768.0
        else:
            audio_float = audio_array.astype(np.float32)

        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio_float)
        self.recognizer.decode_stream(stream)
        return self._clean_result(stream.result.text.strip())

    def _clean_result(self, text: str) -> str:
        return text


class SenseVoiceAdapter(EngineAdapter):
    name = "sensevoice"
    capabilities = EngineCapabilities(
        languages=("zh", "en", "ja", "ko", "yue"),
        supports_language_hint=True,
    )

    def load(self) -> None:
        model = self._asset("model_path", "模型")
        tokens = self._asset("tokens_path", "tokens")
        import sherpa_onnx

        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=tokens,
            language=self.config.get("language", "zh"),
            use_itn=bool(self.config.get("use_itn", True)),
            num_threads=int(self.config.get("num_threads", 6)),
            provider=self.config.get("provider", "cpu"),
        )

    def _clean_result(self, text: str) -> str:
        import re

        return re.sub(r"^<\|[^|]*\|>", "", text).strip()


class Qwen3AsrAdapter(EngineAdapter):
    name = "qwen3-asr"
    capabilities = EngineCapabilities(
        languages=("auto", "zh", "en", "yue"),
        supports_hotwords=True,
        supports_language_hint=False,
    )

    def load(self) -> None:
        conv_frontend = self._asset("conv_frontend_path", "conv_frontend")
        encoder = self._asset("encoder_path", "encoder")
        decoder = self._asset("decoder_path", "decoder")
        tokenizer = self._asset("tokenizer_path", "tokenizer", directory=True)
        import sherpa_onnx

        self.recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=conv_frontend,
            encoder=encoder,
            decoder=decoder,
            tokenizer=tokenizer,
            num_threads=int(self.config.get("num_threads", 6)),
            sample_rate=int(self.config.get("sample_rate", 16000)),
            feature_dim=int(self.config.get("feature_dim", 128)),
            decoding_method=self.config.get("decoding_method", "greedy_search"),
            debug=bool(self.config.get("debug", False)),
            provider=self.config.get("provider", "cpu"),
            max_total_len=int(self.config.get("max_total_len", 512)),
            max_new_tokens=int(self.config.get("max_new_tokens", 128)),
            temperature=float(self.config.get("temperature", 0.000001)),
            top_p=float(self.config.get("top_p", 0.8)),
            seed=int(self.config.get("seed", 42)),
            hotwords=str(self.config.get("hotwords", "")),
        )


class FunAsrNanoAdapter(EngineAdapter):
    name = "fun-asr-nano"
    capabilities = EngineCapabilities(
        languages=("auto", "zh", "en", "yue", "ja", "ko"),
        supports_hotwords=True,
        supports_language_hint=True,
    )

    def load(self) -> None:
        encoder_adaptor = self._asset("encoder_adaptor_path", "encoder_adaptor")
        llm = self._asset("llm_path", "llm")
        embedding = self._asset("embedding_path", "embedding")
        tokenizer = self._asset("tokenizer_path", "tokenizer", directory=True)
        import sherpa_onnx

        language = str(self.config.get("language", "zh"))
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_funasr_nano(
            encoder_adaptor=encoder_adaptor,
            llm=llm,
            embedding=embedding,
            tokenizer=tokenizer,
            num_threads=int(self.config.get("num_threads", 6)),
            sample_rate=int(self.config.get("sample_rate", 16000)),
            feature_dim=int(self.config.get("feature_dim", 80)),
            decoding_method=self.config.get("decoding_method", "greedy_search"),
            debug=bool(self.config.get("debug", False)),
            provider=self.config.get("provider", "cpu"),
            system_prompt=self.config.get("system_prompt", "You are a helpful assistant."),
            user_prompt=self.config.get("user_prompt", "语音转写:"),
            max_new_tokens=int(self.config.get("max_new_tokens", 512)),
            temperature=float(self.config.get("temperature", 0.000001)),
            top_p=float(self.config.get("top_p", 0.8)),
            seed=int(self.config.get("seed", 42)),
            language="" if language == "auto" else language,
            itn=bool(self.config.get("use_itn", True)),
            hotwords=str(self.config.get("hotwords", "")),
        )


class WhisperTurboAdapter(EngineAdapter):
    name = "whisper-turbo"
    capabilities = EngineCapabilities(
        languages=("auto", "zh", "en", "yue"),
        supports_language_hint=True,
    )

    def load(self) -> None:
        encoder = self._asset("encoder_path", "encoder")
        decoder = self._asset("decoder_path", "decoder")
        tokens = self._asset("tokens_path", "tokens")
        import sherpa_onnx

        language = str(self.config.get("language", "zh"))
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=encoder,
            decoder=decoder,
            tokens=tokens,
            language="" if language == "auto" else language,
            task="transcribe",
            num_threads=int(self.config.get("num_threads", 6)),
            decoding_method=self.config.get("decoding_method", "greedy_search"),
            debug=bool(self.config.get("debug", False)),
            provider=self.config.get("provider", "cpu"),
            tail_paddings=int(self.config.get("tail_paddings", -1)),
        )


_ADAPTERS = {
    SenseVoiceAdapter.name: SenseVoiceAdapter,
    Qwen3AsrAdapter.name: Qwen3AsrAdapter,
    FunAsrNanoAdapter.name: FunAsrNanoAdapter,
    WhisperTurboAdapter.name: WhisperTurboAdapter,
}


def create_engine_adapter(
    engine_name: str,
    config: dict[str, Any],
    base_dir: str | Path,
    *,
    asset_roots: Iterable[str | Path] | None = None,
) -> EngineAdapter:
    try:
        adapter_type = _ADAPTERS[engine_name]
    except KeyError as exc:
        raise ValueError(f"不支持的引擎: {engine_name}") from exc
    return adapter_type(config, base_dir, asset_roots=asset_roots)
