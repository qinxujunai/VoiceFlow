"""Measure source proxy PCM retention with real shared memory, without a microphone."""

import argparse
import ctypes
from ctypes import wintypes
import gc
import hashlib
import importlib.util
import json
import math
import multiprocessing
from multiprocessing import shared_memory
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from runtime_bootstrap import configure_native_thread_pools

configure_native_thread_pools()
import numpy as np


def private_bytes():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                "PrivateUsage",
            )
        ]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    api.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
    api.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not api(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.PrivateUsage


def measure(source, seconds, count, connection):
    spec = importlib.util.spec_from_file_location("measured_audio_proxy", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capture = module.SupervisedAudioCapture(ROOT / "config.yaml")
    payload = np.arange(1600, dtype=np.int16).tobytes()
    blocks = seconds * 10
    samples = blocks * 1600
    memory = shared_memory.SharedMemory(create=True, size=samples * 2)
    shared = np.ndarray((blocks, 1600), dtype=np.int16, buffer=memory.buf)
    shared[:] = np.frombuffer(payload, dtype=np.int16)
    expected_hash = hashlib.sha256(memory.buf).hexdigest()

    def request(kind, **_kwargs):
        if kind == "stop":
            return {"ok": True, "samples": samples, "shm_name": memory.name}
        if kind == "ack":
            return {"ok": True, "reusable": True}
        raise AssertionError(kind)

    capture._request = request
    capture._ensure_worker = lambda: None
    capture._terminate_worker = lambda: None
    timings = []
    snapshot_timings = []
    try:
        # Warm the same source path before the memory baseline.
        capture._is_frozen = True
        warm = capture.stop_recording()
        del warm
        gc.collect()
        baseline = private_bytes()
        first_idle = None
        for iteration in range(count):
            capture._audio_buffer = []
            capture._audio_buffer_ends = []
            capture._total_samples = 0
            if hasattr(capture, "_pcm_closed"):
                capture._pcm_closed = False
            for _ in range(blocks):
                capture._accept_pcm(payload)
            capture._last_total_samples = samples
            capture._is_frozen = True
            if iteration == 0:
                for _ in range(200):
                    started = time.perf_counter_ns()
                    tail = capture.snapshot_audio(samples - 1600, samples)
                    snapshot_timings.append((time.perf_counter_ns() - started) / 1e6)
                    assert tail.tobytes() == payload
                del tail
            started = time.perf_counter_ns()
            result = capture.stop_recording()
            timings.append((time.perf_counter_ns() - started) / 1e6)
            assert len(result) == samples
            assert hashlib.sha256(result).hexdigest() == expected_hash
            del result
            gc.collect()
            if first_idle is None:
                first_idle = private_bytes()
        def distribution(values):
            return {"samples": len(values), "p50_ms": statistics.median(values),
                    "p95_ms": sorted(values)[math.ceil(len(values) * .95) - 1],
                    "worst_ms": max(values)}
        connection.send({
            "represented_seconds": seconds, "pcm_bytes": samples * 2,
            "input_sha256": expected_hash, "stop": distribution(timings),
            "tail_snapshot": distribution(snapshot_timings),
            "retained_pcm_bytes": sum(block.nbytes for block in capture._audio_buffer),
            "retained_blocks": len(capture._audio_buffer),
            "warm_private_bytes": baseline, "first_idle_private_bytes": first_idle,
            "first_idle_private_growth_bytes": first_idle - baseline,
            "last_idle_private_bytes": private_bytes(),
        })
    finally:
        del shared
        memory.close()
        memory.unlink()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src" / "audio_worker.py")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("at least 20 samples required")
    context = multiprocessing.get_context("spawn")
    rows = []
    for seconds in (10, 60, 600, 3600):
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=measure, args=(args.source, seconds, args.samples, child))
        process.start()
        child.close()
        try:
            if not parent.poll(120):
                raise TimeoutError(f"PCM measurement timed out: {seconds}")
            rows.append(parent.recv())
            process.join(10)
            if process.exitcode != 0:
                raise RuntimeError(f"PCM measurement failed: {process.exitcode}")
        finally:
            if process.is_alive():
                process.terminate()
                process.join(5)
            parent.close()
    report = {
        "kind": "synthetic_source_pcm_lifecycle",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "conditions": "Same deterministic 16 kHz mono int16 100 ms blocks; production one-thread OpenBLAS budget before NumPy import. Production host accept/snapshot/stop; real shared memory; simulated stop/ack IPC. Separate child per duration, 20 warm stops. Windows PrivateUsage after dropping final copy; shared-memory mapping remains constant. No microphone/ASR/Qt/package/real-time-use claim.",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
