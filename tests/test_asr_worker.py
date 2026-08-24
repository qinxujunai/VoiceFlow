from __future__ import annotations

import multiprocessing
import sys
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from asr_worker import SupervisedTranscriber  # noqa: E402


def _fake_worker(command_queue, response_queue, heartbeat, _config, engine):
    from multiprocessing import shared_memory

    heartbeat.value = time.monotonic()
    response_queue.put({"kind": "ready", "engine": engine})
    while True:
        heartbeat.value = time.monotonic()
        try:
            command = command_queue.get(timeout=0.05)
        except Exception:
            continue
        if command["kind"] == "shutdown":
            return
        if command["kind"] != "transcribe":
            continue
        shm = shared_memory.SharedMemory(name=command["shm_name"])
        try:
            audio = np.ndarray(
                (command["samples"],),
                dtype=np.int16,
                buffer=shm.buf,
            )
            response_queue.put(
                {
                    "kind": "result",
                    "request_id": command["request_id"],
                    "text": f"samples={len(audio)};sum={int(audio.sum())}",
                }
            )
        finally:
            shm.close()


def test_supervised_transcriber_runs_in_a_child_process_and_uses_shared_pcm():
    transcriber = SupervisedTranscriber(
        "unused.yaml",
        worker_target=_fake_worker,
        startup_timeout=3.0,
        heartbeat_timeout=1.0,
    )
    try:
        transcriber.load_engine("sensevoice")
        parent_pid = multiprocessing.current_process().pid
        worker_pid = transcriber.worker_pid

        text = transcriber.transcribe(np.arange(1600, dtype=np.int16), 16000)

        assert worker_pid is not None
        assert worker_pid != parent_pid
        assert text == "samples=1600;sum=1279200"
        assert transcriber.is_ready is True
    finally:
        transcriber.shutdown()


def test_supervisor_rejects_use_before_the_engine_is_ready():
    transcriber = SupervisedTranscriber(
        "unused.yaml",
        worker_target=_fake_worker,
    )

    try:
        try:
            transcriber.transcribe(np.zeros(10, dtype=np.int16), 16000)
        except RuntimeError as error:
            assert "尚未就绪" in str(error)
        else:
            raise AssertionError("transcribe should require a ready worker")
    finally:
        transcriber.shutdown()
