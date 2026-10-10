from __future__ import annotations

import ast
import hashlib
import json
import multiprocessing
import os
import sys
import subprocess
import time
import types
import wave
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asr_worker import SupervisedTranscriber, _asr_worker_main


def _observed_native_vad_worker(commands, responses, heartbeat, worker_config, engine):
    import audio_activity

    trace_path = Path(worker_config["trace_path"])

    def trace(event, **fields):
        with trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, "pid": os.getpid(), **fields}) + "\n")

    original_init = audio_activity.SileroSpeechDetector.__init__
    original_has_speech = audio_activity.SileroSpeechDetector.has_speech

    def observed_init(detector, *args, **kwargs):
        original_init(detector, *args, **kwargs)
        trace("vad_initialized")

    def observed_has_speech(detector, audio, sample_rate):
        result = original_has_speech(detector, audio, sample_rate)
        trace("native_vad", has_speech=bool(result), samples=len(audio))
        return result

    audio_activity.SileroSpeechDetector.__init__ = observed_init
    audio_activity.SileroSpeechDetector.has_speech = observed_has_speech

    class ObservedTranscriber:
        def __init__(self, _config_path, *, asset_roots=None):
            pass

        def load_engine(self, _engine):
            pass

        def transcribe(self, audio, sample_rate):
            trace(
                "asr",
                samples=len(audio),
                sample_rate=sample_rate,
                pcm_sha256=hashlib.sha256(audio.tobytes()).hexdigest(),
            )
            return f"fixture ASR pid={os.getpid()}"

    replacement = types.ModuleType("transcriber")
    replacement.Transcriber = ObservedTranscriber
    sys.modules["transcriber"] = replacement
    _asr_worker_main(commands, responses, heartbeat, worker_config, engine)


def _public_chinese_pcm():
    wav_path = ROOT / "models" / "sensevoice" / "test_wavs" / "zh.wav"
    with wave.open(str(wav_path), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).copy()


@pytest.mark.parametrize("speech", [False, True], ids=["silence", "public-chinese"])
def test_production_asr_worker_owns_native_vad_and_preserves_full_pcm(tmp_path, speech):
    audio = _public_chinese_pcm() if speech else np.zeros(16000 * 2, dtype=np.int16)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "audio": {"sample_rate": 16000},
                "vad": {
                    "enabled": True,
                    "model_path": str(ROOT / "assets" / "silero_vad.onnx"),
                    "speech_probability_threshold": 0.5,
                    "asr_energy_floor": 0.002,
                    "min_speech_ms": 90,
                },
            }
        ),
        encoding="utf-8",
    )
    trace_path = tmp_path / "worker-trace.jsonl"
    context = multiprocessing.get_context("spawn")
    commands = context.Queue(maxsize=2)
    responses = context.Queue(maxsize=2)
    heartbeat = context.Value("d", time.monotonic())
    worker = context.Process(
        target=_observed_native_vad_worker,
        args=(
            commands,
            responses,
            heartbeat,
            {"config_path": str(config_path), "asset_roots": (str(ROOT),),
             "trace_path": str(trace_path)},
            "sensevoice",
        ),
        name="VoiceFlow-Test-ASR-Activity",
    )
    memory = shared_memory.SharedMemory(create=True, size=audio.nbytes)
    np.ndarray(audio.shape, dtype=np.int16, buffer=memory.buf)[:] = audio
    worker.start()
    worker_pid = worker.pid
    try:
        ready = responses.get(timeout=10.0)
        assert ready["kind"] == "ready", ready
        assert worker_pid != os.getpid()
        commands.put(
            {"kind": "transcribe", "request_id": "fixture", "shm_name": memory.name,
             "samples": len(audio), "sample_rate": 16000}
        )
        result = responses.get(timeout=10.0)
        assert result["kind"] == "result", result
        assert result.get("has_speech") is speech, "worker result omitted speech-presence proof"
        assert result["text"] == (f"fixture ASR pid={worker_pid}" if speech else "")
        trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        assert all(event["pid"] == worker_pid for event in trace)
        assert any(event["event"] == "vad_initialized" for event in trace)
        asr_events = [event for event in trace if event["event"] == "asr"]
        if speech:
            assert any(event["event"] == "native_vad" and event["has_speech"] for event in trace)
            assert len(asr_events) == 1
            assert asr_events[0]["samples"] == len(audio)
            assert asr_events[0]["sample_rate"] == 16000
            assert asr_events[0]["pcm_sha256"] == hashlib.sha256(audio.tobytes()).hexdigest()
        else:
            assert not asr_events, "silence reached ASR despite the enabled presence gate"
    finally:
        commands.put({"kind": "shutdown"}, timeout=1.0)
        worker.join(timeout=5.0)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2.0)
        memory.close()
        memory.unlink()
        for channel in (commands, responses):
            channel.cancel_join_thread()
            channel.close()
        worker.close()


def test_qt_host_does_not_construct_or_invoke_native_silero_vad():
    tree = ast.parse((SRC / "main.py").read_text(encoding="utf-8"))
    native_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Name) and function.id == "SileroSpeechDetector"
        ) or (
            isinstance(function, ast.Attribute)
            and function.attr in {"SileroSpeechDetector", "has_speech"}
        ):
            native_calls.append(node.lineno)
    assert not native_calls, f"Qt host still invokes native VAD at lines {native_calls}"


def test_importing_qt_host_does_not_load_native_microphone_or_recognizer():
    code = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); import main; "
        "print(json.dumps({name: name in sys.modules for name in "
        "('sounddevice', 'sherpa_onnx')}))"
    )
    result = subprocess.run([sys.executable, "-c", code, str(SRC)],
                            capture_output=True, text=True, check=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert json.loads(result.stdout) == {"sounddevice": False, "sherpa_onnx": False}


def test_settings_microphone_query_uses_controller_cache_without_native_calls():
    from overlay_webview import _SettingsWindow

    window = types.SimpleNamespace(controller=types.SimpleNamespace(
        query_microphones=lambda: [("Fixture input", 7)]
    ))
    assert _SettingsWindow._query_microphones(window) == [("Fixture input", 7)]


def test_real_supervised_baseline_accepts_public_speech_and_rejects_silence():
    transcriber = SupervisedTranscriber(ROOT / "config.yaml", asset_roots=(ROOT,))
    try:
        transcriber.load_engine("sensevoice")
        assert transcriber.worker_pid != os.getpid()
        text, speech = transcriber.transcribe_with_activity(_public_chinese_pcm(), 16000)
        assert speech
        assert "开放时间" in text
        text, speech = transcriber.transcribe_with_activity(np.zeros(32000, dtype=np.int16), 16000)
        assert (text, speech) == ("", False)
        assert transcriber.is_healthy
    finally:
        transcriber.shutdown()
    assert transcriber.worker_pid is None
