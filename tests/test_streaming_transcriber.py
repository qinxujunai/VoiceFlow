from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FakeStream:
    def __init__(self):
        self.waveforms = []

    def accept_waveform(self, sample_rate, samples):
        self.waveforms.append((sample_rate, samples.copy()))


class FakeRecognizer:
    def __init__(self, hypotheses, endpoints=None):
        self.hypotheses = iter(hypotheses)
        self.endpoints = iter(endpoints or [])
        self.current = ""
        self.current_endpoint = False
        self.decode_count = 0
        self.reset_count = 0

    def create_stream(self):
        return FakeStream()

    def is_ready(self, _stream):
        return self.decode_count == 0

    def decode_stream(self, _stream):
        self.current = next(self.hypotheses)
        self.current_endpoint = next(self.endpoints, False)
        self.decode_count += 1

    def get_result(self, _stream):
        self.decode_count = 0
        return self.current

    def is_endpoint(self, _stream):
        return self.current_endpoint

    def reset(self, _stream):
        self.reset_count += 1
        self.current = ""
        self.current_endpoint = False


def test_online_preview_commits_only_stable_prefix_and_flushes_endpoint():
    from streaming_transcriber import OnlinePreviewTranscriber

    recognizer = FakeRecognizer(
        ["你好", "你好世界", "你好世界"],
        endpoints=[False, False, True],
    )
    transcriber = OnlinePreviewTranscriber.from_recognizer(
        recognizer,
        sample_rate=16000,
    )
    session = transcriber.create_session()

    first = transcriber.accept_pcm(
        session,
        np.array([0, 16384, -16384], dtype=np.int16),
        16000,
    )
    second = transcriber.accept_pcm(
        session,
        np.array([8192, -8192], dtype=np.int16),
        16000,
    )
    third = transcriber.accept_pcm(
        session,
        np.array([4096], dtype=np.int16),
        16000,
    )

    assert first.text == "你好"
    assert first.delta == ""
    assert first.provisional_text == "你好"
    assert second.text == "你好世界"
    assert second.delta == "你"
    assert second.provisional_text == "好世界"
    assert third.delta == "好世界"
    assert third.provisional_text == ""
    assert third.endpoint_final is True
    assert session.committed_text == "你好世界"
    assert session.segment_id == 1
    assert recognizer.reset_count == 1
    assert session.fed_samples == 6
    assert len(session.stream.waveforms) == 3
    assert session.stream.waveforms[0][0] == 16000
    np.testing.assert_allclose(
        session.stream.waveforms[0][1],
        np.array([0.0, 0.5, -0.5], dtype=np.float32),
    )


def test_online_preview_recovers_after_permanent_divergence_at_next_endpoint():
    from streaming_transcriber import OnlinePreviewTranscriber

    recognizer = FakeRecognizer(
        [
            "今天我们测试",
            "今天我们测试语音",
            "今天我门测试语音",
            "下一段",
            "下一段继续",
        ],
        endpoints=[False, False, True, False, True],
    )
    transcriber = OnlinePreviewTranscriber.from_recognizer(recognizer)
    session = transcriber.create_session()

    deltas = [
        transcriber.accept_pcm(
            session,
            np.ones(1600, dtype=np.int16),
            16000,
        ).delta
        for _ in range(5)
    ]

    assert deltas == ["", "今天我们测", "", "", "下一段继续"]
    assert session.committed_text == "今天我们测下一段继续"
    assert recognizer.reset_count == 2
    assert session.segment_id == 2


def test_online_preview_reports_divergence_without_retracting_committed_text():
    from streaming_transcriber import OnlinePreviewTranscriber

    recognizer = FakeRecognizer(
        ["开放语音", "开放语音输入", "开方语音输入"],
        endpoints=[False, False, False],
    )
    transcriber = OnlinePreviewTranscriber.from_recognizer(recognizer)
    session = transcriber.create_session()

    updates = [
        transcriber.accept_pcm(
            session,
            np.ones(1600, dtype=np.int16),
            16000,
        )
        for _ in range(3)
    ]

    assert updates[1].delta == "开放语"
    assert updates[1].provisional_text == "音输入"
    assert updates[2].delta == ""
    assert updates[2].provisional_text == ""
    assert updates[2].hypothesis_diverged is True
    assert session.committed_text == "开放语"


def test_online_preview_removes_sentence_punctuation_from_live_hypotheses():
    from streaming_transcriber import OnlinePreviewTranscriber

    recognizer = FakeRecognizer(
        ["你好，世界。", "你好，世界。"],
        endpoints=[False, True],
    )
    transcriber = OnlinePreviewTranscriber.from_recognizer(
        recognizer,
        stability_guard_chars=0,
    )
    session = transcriber.create_session()

    first = transcriber.accept_pcm(
        session,
        np.ones(1600, dtype=np.int16),
        16000,
    )
    second = transcriber.accept_pcm(
        session,
        np.ones(1600, dtype=np.int16),
        16000,
    )

    assert first.text == "你好世界"
    assert first.provisional_text == "你好世界"
    assert second.delta == "你好世界"
    assert second.provisional_text == ""


def test_online_preview_never_exposes_model_control_tokens():
    from streaming_transcriber import OnlinePreviewTranscriber

    recognizer = FakeRecognizer(
        [
            "<unk><unk><blk><|en|>",
            "<unk> HELLO <s> WORLD </s> <eps>",
        ],
        endpoints=[False, True],
    )
    transcriber = OnlinePreviewTranscriber.from_recognizer(
        recognizer,
        stability_guard_chars=0,
    )
    session = transcriber.create_session()

    first = transcriber.accept_pcm(
        session,
        np.ones(1600, dtype=np.int16),
        16000,
    )
    second = transcriber.accept_pcm(
        session,
        np.ones(1600, dtype=np.int16),
        16000,
    )

    assert first.text == ""
    assert first.provisional_text == ""
    assert second.text == "Hello world"
    assert "<" not in second.text
    assert ">" not in second.text


def test_online_preview_rejects_a_mismatched_sample_rate():
    from streaming_transcriber import OnlinePreviewTranscriber

    transcriber = OnlinePreviewTranscriber.from_recognizer(FakeRecognizer([""]))
    session = transcriber.create_session()

    try:
        transcriber.accept_pcm(
            session,
            np.ones(1600, dtype=np.int16),
            48000,
        )
    except ValueError as exc:
        assert "16000" in str(exc)
        assert "48000" in str(exc)
    else:
        raise AssertionError("sample-rate mismatch must fail")


def test_online_preview_empty_pcm_does_not_touch_the_recognizer():
    from streaming_transcriber import OnlinePreviewTranscriber

    recognizer = FakeRecognizer(["不应读取"])
    transcriber = OnlinePreviewTranscriber.from_recognizer(recognizer)
    session = transcriber.create_session()

    update = transcriber.accept_pcm(
        session,
        np.array([], dtype=np.int16),
        16000,
    )

    assert update.text == ""
    assert update.delta == ""
    assert update.audio_end_sample == 0
    assert session.fed_samples == 0
    assert session.stream.waveforms == []


def test_existing_user_config_without_preview_section_uses_packaged_defaults(
    monkeypatch,
    tmp_path,
):
    from streaming_transcriber import OnlinePreviewTranscriber

    model_dir = tmp_path / "models" / "streaming-preview"
    model_dir.mkdir(parents=True)
    (model_dir / "encoder-epoch-99-avg-1.int8.onnx").write_bytes(b"encoder")
    (model_dir / "decoder-epoch-99-avg-1.onnx").write_bytes(b"decoder")
    (model_dir / "joiner-epoch-99-avg-1.int8.onnx").write_bytes(b"joiner")
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    calls = []

    class FakeOnlineRecognizer:
        @staticmethod
        def from_transducer(**kwargs):
            calls.append(kwargs)
            return FakeRecognizer([""])

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(OnlineRecognizer=FakeOnlineRecognizer),
    )

    transcriber = OnlinePreviewTranscriber.from_config(
        {},
        resolve_asset=lambda raw: tmp_path / raw,
        sample_rate=16000,
    )

    assert transcriber.sample_rate == 16000
    assert calls[0]["encoder"] == str(
        model_dir / "encoder-epoch-99-avg-1.int8.onnx"
    )
    assert calls[0]["decoder"] == str(
        model_dir / "decoder-epoch-99-avg-1.onnx"
    )
    assert calls[0]["joiner"] == str(
        model_dir / "joiner-epoch-99-avg-1.int8.onnx"
    )
    assert calls[0]["tokens"] == str(model_dir / "tokens.txt")
    assert calls[0]["num_threads"] >= 1
    assert calls[0]["enable_endpoint_detection"] is True


def test_online_preview_can_load_the_bilingual_paraformer_candidate(
    monkeypatch,
    tmp_path,
):
    from streaming_transcriber import OnlinePreviewTranscriber

    model_dir = tmp_path / "models" / "streaming-paraformer-bilingual"
    model_dir.mkdir(parents=True)
    (model_dir / "encoder.int8.onnx").write_bytes(b"encoder")
    (model_dir / "decoder.int8.onnx").write_bytes(b"decoder")
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    calls = []

    class FakeOnlineRecognizer:
        @staticmethod
        def from_paraformer(**kwargs):
            calls.append(kwargs)
            return FakeRecognizer([""])

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(OnlineRecognizer=FakeOnlineRecognizer),
    )
    config = {
        "streaming_preview": {
            "runtime_engine": "online-paraformer",
            "encoder_path": "models/streaming-paraformer-bilingual/encoder.int8.onnx",
            "decoder_path": "models/streaming-paraformer-bilingual/decoder.int8.onnx",
            "tokens_path": "models/streaming-paraformer-bilingual/tokens.txt",
        }
    }

    OnlinePreviewTranscriber.from_config(
        config,
        resolve_asset=lambda raw: tmp_path / raw,
    )

    assert calls[0]["encoder"] == str(model_dir / "encoder.int8.onnx")
    assert calls[0]["decoder"] == str(model_dir / "decoder.int8.onnx")
    assert calls[0]["tokens"] == str(model_dir / "tokens.txt")
    assert calls[0]["enable_endpoint_detection"] is True


def test_online_preview_can_load_a_bilingual_transducer(
    monkeypatch,
    tmp_path,
):
    from streaming_transcriber import OnlinePreviewTranscriber

    model_dir = tmp_path / "models" / "streaming-preview"
    model_dir.mkdir(parents=True)
    (model_dir / "encoder-epoch-99-avg-1.int8.onnx").write_bytes(b"encoder")
    (model_dir / "decoder-epoch-99-avg-1.onnx").write_bytes(b"decoder")
    (model_dir / "joiner-epoch-99-avg-1.int8.onnx").write_bytes(b"joiner")
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    calls = []

    class FakeOnlineRecognizer:
        @staticmethod
        def from_transducer(**kwargs):
            calls.append(kwargs)
            return FakeRecognizer([""])

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(OnlineRecognizer=FakeOnlineRecognizer),
    )
    config = {
        "streaming_preview": {
            "runtime_engine": "online-transducer",
            "encoder_path": "models/streaming-preview/encoder-epoch-99-avg-1.int8.onnx",
            "decoder_path": "models/streaming-preview/decoder-epoch-99-avg-1.onnx",
            "joiner_path": "models/streaming-preview/joiner-epoch-99-avg-1.int8.onnx",
            "tokens_path": "models/streaming-preview/tokens.txt",
        }
    }

    OnlinePreviewTranscriber.from_config(
        config,
        resolve_asset=lambda raw: tmp_path / raw,
    )

    assert calls[0]["encoder"] == str(
        model_dir / "encoder-epoch-99-avg-1.int8.onnx"
    )
    assert calls[0]["decoder"] == str(
        model_dir / "decoder-epoch-99-avg-1.onnx"
    )
    assert calls[0]["joiner"] == str(
        model_dir / "joiner-epoch-99-avg-1.int8.onnx"
    )
    assert calls[0]["tokens"] == str(model_dir / "tokens.txt")
    assert calls[0]["enable_endpoint_detection"] is True


def test_voice_system_feeds_each_captured_sample_to_preview_exactly_once():
    from main import VoiceInputSystem
    from streaming_transcriber import PreviewUpdate

    class FakeAudio:
        sample_rate = 16000
        sample_count = 1600

    class FakePreview:
        def __init__(self):
            self.lengths = []

        def accept_pcm(self, session, pcm, sample_rate):
            self.lengths.append(len(pcm))
            session.committed_text += "字"
            return PreviewUpdate(
                text=session.committed_text,
                delta="字",
                segment_id=0,
                audio_end_sample=getattr(session, "fed_samples", 0),
            )

    system = object.__new__(VoiceInputSystem)
    system.audio = FakeAudio()
    system._stream_generation = 7
    system._latest_text = ""
    system._preview_first_text_ms = 1.0
    system._preview_started_at = None
    system._preview_update_count = 0
    system._preview_max_chunk_chars = 0
    ranges = []
    preview_deltas = []
    system._audio_snapshot = lambda start, end: (
        ranges.append((start, end))
        or np.ones(end - start, dtype=np.int16)
    )
    system._append_preview_delta = (
        lambda delta, generation: preview_deltas.append((delta, generation))
    )
    preview = FakePreview()
    session = SimpleNamespace(committed_text="")

    next_sample = VoiceInputSystem._feed_preview_audio(
        system,
        preview,
        session,
        0,
        7,
    )
    FakeAudio.sample_count = 2400
    next_sample = VoiceInputSystem._feed_preview_audio(
        system,
        preview,
        session,
        next_sample,
        7,
    )

    assert next_sample == 2400
    assert ranges == [(0, 1600), (1600, 2400)]
    assert preview.lengths == [1600, 800]
    assert preview_deltas == [("字", 7), ("字", 7)]
