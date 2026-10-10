from __future__ import annotations

import sys
import threading
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from audio_worker import SupervisedAudioCapture  # noqa: E402


def _fake_audio_worker(commands, events, heartbeat, _config_path):
    stop = threading.Event()

    def pulse():
        while not stop.wait(0.05):
            heartbeat.value = time.monotonic()

    threading.Thread(target=pulse, daemon=True).start()
    heartbeat.value = time.monotonic()
    events.put(
        {
            "kind": "ready",
            "sample_rate": 16000,
            "channels": 1,
            "dtype": "int16",
        }
    )
    memories = {}
    try:
        while True:
            command = commands.get()
            kind = command["kind"]
            request_id = command.get("request_id")
            if kind == "shutdown":
                return
            if kind == "start":
                events.put({"kind": "response", "request_id": request_id, "ok": True})
                pcm = np.arange(1600, dtype=np.int16)
                events.put({"kind": "pcm", "payload": pcm.tobytes()})
            elif kind == "freeze":
                events.put(
                    {
                        "kind": "response",
                        "request_id": request_id,
                        "ok": True,
                        "samples": 1600,
                    }
                )
            elif kind == "stop":
                pcm = np.arange(1600, dtype=np.int16)
                memory = shared_memory.SharedMemory(create=True, size=pcm.nbytes)
                np.ndarray(pcm.shape, dtype=np.int16, buffer=memory.buf)[:] = pcm
                memories[request_id] = memory
                events.put(
                    {
                        "kind": "response",
                        "request_id": request_id,
                        "ok": True,
                        "shm_name": memory.name,
                        "samples": len(pcm),
                    }
                )
            elif kind == "ack":
                memory = memories.pop(command["target_request_id"], None)
                if memory is not None:
                    memory.close()
                    memory.unlink()
                events.put({"kind": "response", "request_id": request_id, "ok": True, "reusable": True})
            elif kind == "cancel":
                events.put({"kind": "response", "request_id": request_id, "ok": True, "reusable": True})
    finally:
        stop.set()
        for memory in memories.values():
            memory.close()
            try:
                memory.unlink()
            except FileNotFoundError:
                pass


def _blocking_stop_worker(commands, events, heartbeat, _config_path):
    stop = threading.Event()

    def pulse():
        while not stop.wait(0.05):
            heartbeat.value = time.monotonic()

    threading.Thread(target=pulse, daemon=True).start()
    events.put(
        {
            "kind": "ready",
            "sample_rate": 16000,
            "channels": 1,
            "dtype": "int16",
        }
    )
    try:
        while True:
            command = commands.get()
            request_id = command.get("request_id")
            if command["kind"] == "start":
                events.put({"kind": "response", "request_id": request_id, "ok": True})
                events.put(
                    {
                        "kind": "pcm",
                        "payload": np.arange(800, dtype=np.int16).tobytes(),
                    }
                )
            elif command["kind"] == "freeze":
                events.put(
                    {
                        "kind": "response",
                        "request_id": request_id,
                        "ok": True,
                        "samples": 800,
                    }
                )
            elif command["kind"] == "stop":
                time.sleep(10)
    finally:
        stop.set()


def _config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "audio:\n  sample_rate: 16000\n  channels: 1\n  dtype: int16\n",
        encoding="utf-8",
    )
    return path


def test_audio_device_lives_in_a_worker_and_returns_authoritative_pcm(tmp_path):
    capture = SupervisedAudioCapture(
        _config(tmp_path),
        worker_target=_fake_audio_worker,
        startup_timeout=3.0,
        command_timeout=1.0,
    )
    try:
        capture.start_recording()
        deadline = time.monotonic() + 1.0
        while capture.sample_count < 1600 and time.monotonic() < deadline:
            time.sleep(0.01)

        frozen = capture.freeze_recording()
        audio = capture.stop_recording()

        assert frozen == 1600
        assert audio.tolist() == list(range(1600))
        assert capture.is_recording is False
        assert capture.is_ready
        assert capture.last_total_samples == 1600
        assert capture.sample_count == 0
        assert capture._audio_buffer == []
        assert capture._audio_buffer_ends == []
        capture._accept_pcm(np.arange(1600, dtype=np.int16).tobytes())
        assert capture.sample_count == 0
    finally:
        capture.shutdown()


def test_successful_stop_and_cancel_reuse_worker_without_replaying_old_pcm(tmp_path):
    capture = SupervisedAudioCapture(
        _config(tmp_path),
        worker_target=_fake_audio_worker,
        startup_timeout=3.0,
        command_timeout=1.0,
    )
    try:
        capture.prepare()
        original_pid = capture.worker_pid
        for canceled in (False, True, False):
            capture.start_recording()
            deadline = time.monotonic() + 1.0
            while capture.sample_count < 1600 and time.monotonic() < deadline:
                time.sleep(0.005)
            if canceled:
                capture.cancel_recording()
                assert capture.sample_count == 0
                capture._accept_pcm(np.arange(1600, dtype=np.int16).tobytes())
                assert capture.sample_count == 0
            else:
                capture.freeze_recording()
                assert capture.stop_recording().tolist() == list(range(1600))
            assert capture.worker_pid == original_pid
            assert capture.is_healthy
    finally:
        capture.shutdown()
    assert capture.worker_pid is None


def test_blocked_driver_is_killed_and_mirrored_pcm_returns_without_freezing_ui(tmp_path):
    capture = SupervisedAudioCapture(
        _config(tmp_path),
        worker_target=_blocking_stop_worker,
        startup_timeout=3.0,
        command_timeout=0.25,
    )
    try:
        capture.start_recording()
        deadline = time.monotonic() + 1.0
        while capture.sample_count < 800 and time.monotonic() < deadline:
            time.sleep(0.01)
        capture.freeze_recording()

        started = time.perf_counter()
        audio = capture.stop_recording()
        elapsed = time.perf_counter() - started

        assert elapsed < 0.8
        assert audio.tolist() == list(range(800))
        assert capture.worker_pid is None
        assert capture.last_total_samples == 800
        assert capture.sample_count == 0
        assert capture._audio_buffer == []
    finally:
        capture.shutdown()
