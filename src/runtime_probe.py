"""Isolated packaged worker measurements using a public WAV, never a microphone."""

import json
import os
import multiprocessing
from multiprocessing import shared_memory
from pathlib import Path
import threading
import time
import wave

import numpy as np


def fixture_audio_worker(commands, events, heartbeat, _config_path):
    """Exercise the real supervisor without recording or touching the clipboard."""
    from worker_lifecycle import watch_parent_exit
    watch_parent_exit()
    stop = threading.Event()
    memories = {}

    def pulse():
        while not stop.wait(0.1):
            heartbeat.value = time.monotonic()

    heartbeat.value = time.monotonic()
    threading.Thread(target=pulse, daemon=True).start()
    pcm = np.arange(1600, dtype=np.int16)
    events.put({"kind": "ready", "sample_rate": 16000, "channels": 1, "dtype": "int16"})
    try:
        while True:
            command = commands.get()
            kind = command["kind"]
            if kind == "shutdown":
                return
            request_id = command.get("request_id")
            response = {"kind": "response", "request_id": request_id, "ok": True}
            if kind == "start":
                events.put({"kind": "pcm", "payload": pcm.tobytes()})
            elif kind == "freeze":
                response["samples"] = len(pcm)
            elif kind == "stop":
                memory = shared_memory.SharedMemory(create=True, size=pcm.nbytes)
                np.ndarray(pcm.shape, dtype=np.int16, buffer=memory.buf)[:] = pcm
                memories[request_id] = memory
                response.update(shm_name=memory.name, samples=len(pcm))
            elif kind == "ack":
                memory = memories.pop(command["target_request_id"])
                memory.close()
                memory.unlink()
                response["reusable"] = True
            elif kind == "cancel":
                response["reusable"] = True
            events.put(response)
    finally:
        stop.set()
        for memory in memories.values():
            memory.close()
            memory.unlink()


def run_worker_probe(config_path, audio_path, output_path, *, cycles=20):
    from asr_worker import SupervisedTranscriber
    from audio_worker import SupervisedAudioCapture
    from preview_worker import SupervisedPreviewTranscriber
    from runtime_paths import AppPaths
    from version import BUILD_ID

    paths = AppPaths.discover(config_path=config_path)
    with wave.open(str(audio_path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("probe audio must be mono 16-bit PCM")
        rate = source.getframerate()
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
    report = {"build_id": BUILD_ID, "parent_pid": multiprocessing.current_process().pid,
              "audio_device": "fixture; no microphone", "sample": Path(audio_path).name,
              "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS")}
    capture = SupervisedAudioCapture(paths.config_file, worker_target=fixture_audio_worker)
    final = SupervisedTranscriber(paths.config_file, asset_roots=paths.asset_roots)
    preview = SupervisedPreviewTranscriber(paths.config_file, asset_roots=paths.asset_roots)
    try:
        started = time.perf_counter()
        capture.prepare()
        report["audio_worker_start_ms"] = round((time.perf_counter() - started) * 1000, 3)
        worker_pids = []
        elapsed = []
        for cycle in range(cycles):
            started = time.perf_counter()
            capture.start_recording()
            if cycle % 3 == 1:
                capture.cancel_recording()
            else:
                assert capture.freeze_recording() == 1600
                assert capture.stop_recording().tolist() == list(range(1600))
            capture.prepare()
            elapsed.append(round((time.perf_counter() - started) * 1000, 3))
            worker_pids.append(capture.worker_pid)
        report.update(cycles=cycles, audio_cycle_ms=elapsed, audio_worker_pids=worker_pids)
        started = time.perf_counter()
        final.load_engine("sensevoice")
        report["final_worker_start_ms"] = round((time.perf_counter() - started) * 1000, 3)
        started = time.perf_counter()
        text = final.transcribe(pcm, rate)
        report["final_public_sample_ms"] = round((time.perf_counter() - started) * 1000, 3)
        report["final_text_chars"] = len(text)
        started = time.perf_counter()
        preview.load()
        report["preview_worker_start_ms"] = round((time.perf_counter() - started) * 1000, 3)
        session = preview.create_session()
        started = time.perf_counter()
        deltas = 0
        for start in range(0, len(pcm), rate // 10):
            event = preview.accept_pcm(session, pcm[start:start + rate // 10], rate)
            deltas += bool(event.delta)
        report["preview_public_sample_decode_ms"] = round((time.perf_counter() - started) * 1000, 3)
        report["preview_delta_count"] = deltas
        preview.close_session(session)
        report["worker_pids"] = {"audio": capture.worker_pid, "final": final.worker_pid,
                                 "preview": preview.worker_pid}
        report["ok"] = len(set(worker_pids)) == 1 and bool(text) and deltas > 0
    except Exception as error:
        report.update(ok=False, error_type=type(error).__name__)
        raise
    finally:
        started = time.perf_counter()
        preview.shutdown()
        final.shutdown()
        capture.shutdown()
        report["shutdown_ms"] = round((time.perf_counter() - started) * 1000, 3)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
