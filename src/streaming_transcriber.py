"""Low-latency local ASR used only for the recording capsule preview."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np

from performance_profile import preview_thread_count


@dataclass(frozen=True)
class PreviewEvent:
    text: str
    delta: str
    segment_id: int
    audio_end_sample: int
    committed_text: str = ""
    provisional_text: str = ""
    endpoint_final: bool = False
    hypothesis_diverged: bool = False


PreviewUpdate = PreviewEvent


@dataclass
class PreviewPerformance:
    speech_onset_sample: int | None = None
    first_model_delta_ms: float | None = None
    first_preview_paint_ms: float | None = None
    update_gap_ms: float | None = None
    queue_delay_ms: float | None = None
    max_chunk_chars: int = 0
    divergence_count: int = 0


@dataclass
class OnlinePreviewSession:
    stream: object
    committed_text: str = ""
    latest_text: str = ""
    fed_samples: int = 0
    segment_id: int = 0
    segment_committed_text: str = ""
    previous_hypothesis: str = ""
    hypothesis_diverged: bool = False


class OnlinePreviewTranscriber:
    """Decode preview tokens without allowing UI rollback or replay."""

    LIVE_SENTENCE_PUNCTUATION = str.maketrans(
        "",
        "",
        "，。！？；：,.!?;:…",
    )
    MODEL_CONTROL_TOKEN = re.compile(
        r"<\|[^<>]*\|>|</?(?:unk|blk|blank|eps|s)>",
        flags=re.IGNORECASE,
    )

    def __init__(
        self,
        recognizer,
        *,
        sample_rate: int = 16000,
        stability_guard_chars: int = 1,
    ):
        self.recognizer = recognizer
        self.sample_rate = int(sample_rate)
        self.stability_guard_chars = max(0, int(stability_guard_chars))

    @classmethod
    def from_recognizer(
        cls,
        recognizer,
        *,
        sample_rate: int = 16000,
        stability_guard_chars: int = 1,
    ):
        return cls(
            recognizer,
            sample_rate=sample_rate,
            stability_guard_chars=stability_guard_chars,
        )

    @classmethod
    def from_config(cls, config, *, resolve_asset, sample_rate: int = 16000):
        preview = config.get("streaming_preview", {})
        if not preview.get("enabled", True):
            raise RuntimeError("streaming preview is disabled")

        tokens = Path(
            resolve_asset(
                preview.get("tokens_path", "models/streaming-preview/tokens.txt")
            )
        )
        runtime_engine = preview.get("runtime_engine", "online-zipformer-ctc")
        if runtime_engine in {"online-paraformer", "online-transducer"}:
            encoder = Path(resolve_asset(preview.get("encoder_path", "")))
            decoder = Path(resolve_asset(preview.get("decoder_path", "")))
            if runtime_engine == "online-transducer":
                joiner = Path(resolve_asset(preview.get("joiner_path", "")))
                assets = (encoder, decoder, joiner, tokens)
            else:
                assets = (encoder, decoder, tokens)
        elif runtime_engine == "online-zipformer-ctc":
            model = Path(
                resolve_asset(
                    preview.get(
                        "model_path",
                        "models/streaming-preview/model.int8.onnx",
                    )
                )
            )
            assets = (model, tokens)
        else:
            raise ValueError(f"unsupported streaming preview engine: {runtime_engine}")
        missing = [str(path) for path in assets if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "streaming preview assets are missing: " + ", ".join(missing)
            )

        import sherpa_onnx

        thread_mode = str(
            config.get("performance", {}).get("thread_mode", "auto")
        ).lower()
        requested_threads = (
            preview.get("num_threads", "auto")
            if thread_mode == "manual"
            else "auto"
        )
        common = {
            "tokens": str(tokens),
            "num_threads": preview_thread_count(requested_threads),
            "sample_rate": int(sample_rate),
            "enable_endpoint_detection": True,
            "provider": preview.get("provider", "cpu"),
        }
        if runtime_engine == "online-paraformer":
            recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                encoder=str(encoder),
                decoder=str(decoder),
                **common,
            )
        elif runtime_engine == "online-transducer":
            recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                encoder=str(encoder),
                decoder=str(decoder),
                joiner=str(joiner),
                **common,
            )
        else:
            recognizer = sherpa_onnx.OnlineRecognizer.from_zipformer2_ctc(
                model=str(model),
                **common,
            )
        return cls(
            recognizer,
            sample_rate=sample_rate,
            stability_guard_chars=preview.get("stability_guard_chars", 1),
        )

    def create_session(self) -> OnlinePreviewSession:
        return OnlinePreviewSession(stream=self.recognizer.create_stream())

    def accept_pcm(
        self,
        session: OnlinePreviewSession,
        pcm,
        sample_rate: int,
    ) -> PreviewEvent:
        sample_rate = int(sample_rate)
        if sample_rate != self.sample_rate:
            raise ValueError(
                f"streaming preview expects {self.sample_rate} Hz, got {sample_rate} Hz"
            )

        samples = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if not len(samples):
            provisional = self._provisional_text(
                session.segment_committed_text,
                session.latest_text,
            )
            return PreviewEvent(
                text=session.latest_text,
                delta="",
                segment_id=session.segment_id,
                audio_end_sample=session.fed_samples,
                committed_text=session.committed_text,
                provisional_text=provisional,
            )

        waveform = samples.astype(np.float32) / 32768.0
        session.stream.accept_waveform(sample_rate, waveform)
        session.fed_samples += len(samples)
        while self.recognizer.is_ready(session.stream):
            self.recognizer.decode_stream(session.stream)

        text = self._live_preview_text(
            str(self.recognizer.get_result(session.stream) or "")
        )
        session.latest_text = text
        diverged = False
        stable_prefix = self._stable_prefix(session.previous_hypothesis, text)
        delta = self._segment_delta(session.segment_committed_text, stable_prefix)
        if (
            session.segment_committed_text
            and not text.startswith(session.segment_committed_text)
        ):
            diverged = True
            session.hypothesis_diverged = True
            delta = ""
        if delta:
            session.segment_committed_text += delta
            session.committed_text += delta
        session.previous_hypothesis = text
        provisional = (
            ""
            if diverged
            else self._provisional_text(session.segment_committed_text, text)
        )

        endpoint_final = self._is_endpoint(session.stream)
        event_segment_id = session.segment_id
        if endpoint_final:
            if (
                not session.hypothesis_diverged
                and text.startswith(session.segment_committed_text)
            ):
                remainder = text[len(session.segment_committed_text):]
                if remainder:
                    delta += remainder
                    session.committed_text += remainder
            provisional = ""
            self._reset_segment(session)

        return PreviewEvent(
            text=text,
            delta=delta,
            segment_id=event_segment_id,
            audio_end_sample=session.fed_samples,
            committed_text=session.committed_text,
            provisional_text=provisional,
            endpoint_final=endpoint_final,
            hypothesis_diverged=diverged,
        )

    @classmethod
    def _live_preview_text(cls, value: str) -> str:
        value = cls.MODEL_CONTROL_TOKEN.sub(" ", value)
        value = value.translate(cls.LIVE_SENTENCE_PUNCTUATION)
        value = " ".join(value.split())
        letters = [char for char in value if char.isalpha()]
        if letters and all(not char.islower() for char in letters):
            value = value.capitalize()
        return value

    @staticmethod
    def _provisional_text(committed: str, hypothesis: str) -> str:
        if hypothesis.startswith(committed):
            return hypothesis[len(committed):]
        return ""

    def _stable_prefix(self, previous: str, current: str) -> str:
        if not previous or not current:
            return ""
        size = 0
        for left, right in zip(previous, current):
            if left != right:
                break
            size += 1
        size = max(0, size - self.stability_guard_chars)
        return current[:size]

    @staticmethod
    def _segment_delta(committed: str, stable_prefix: str) -> str:
        if stable_prefix.startswith(committed):
            return stable_prefix[len(committed):]
        return ""

    def _is_endpoint(self, stream) -> bool:
        check = getattr(self.recognizer, "is_endpoint", None)
        return bool(check(stream)) if check is not None else False

    def _reset_segment(self, session: OnlinePreviewSession) -> None:
        reset = getattr(self.recognizer, "reset", None)
        if reset is not None:
            reset(session.stream)
        session.segment_id += 1
        session.segment_committed_text = ""
        session.previous_hypothesis = ""
        session.latest_text = ""
        session.hypothesis_diverged = False
