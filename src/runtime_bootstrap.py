"""Process-local budgets that must be applied before native libraries import."""

import os
import sys


def configure_packaged_audio_backend():
    # Windows packages contain the reviewed ordinary PortAudio variant. Ignore
    # a host's optional ASIO selection in this process before sounddevice loads.
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        os.environ.pop("SD_ENABLE_ASIO", None)


def configure_native_thread_pools():
    # PCM operations are small vector operations, not BLAS matrix workloads.
    # On Windows NumPy otherwise creates one OpenBLAS pool per worker, whose
    # 16 threads reserve roughly 480 MiB even in the idle microphone process.
    # Recognition retains its own explicit sherpa/ONNX thread budget.
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
