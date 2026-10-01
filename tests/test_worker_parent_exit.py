"""A crashed UI must not leave its native microphone process running."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


def test_audio_worker_exits_when_its_parent_is_killed(tmp_path):
    script = tmp_path / "parent.py"
    script.write_text('''
import multiprocessing as mp
import sys, time, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])

class Capture:
    sample_rate = 16000
    channels = 1
    dtype = "int16"
    is_recording = False
    def __init__(self, path): pass
    def set_pcm_callback(self, callback): pass
    def set_level_callback(self, callback): pass

def worker(commands, events, heartbeat):
    sys.modules["audio_capture"] = types.SimpleNamespace(AudioCapture=Capture)
    from audio_worker import _audio_worker_main
    _audio_worker_main(commands, events, heartbeat, "unused.yaml")

if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    commands, events = ctx.Queue(), ctx.Queue()
    child = ctx.Process(target=worker, args=(commands, events, ctx.Value("d", 0)), daemon=True)
    child.start()
    assert events.get(timeout=15)["kind"] == "ready"
    Path(sys.argv[2]).write_text(str(child.pid))
    while True: time.sleep(1)
''', encoding="utf-8")
    pid_file = tmp_path / "worker.pid"
    parent = subprocess.Popen(
        [sys.executable, str(script), str(Path(__file__).resolve().parents[1] / "src"), str(pid_file)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    child_pid = None
    eof = threading.Event()
    try:
        deadline = time.monotonic() + 20
        while not pid_file.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if not pid_file.exists():
            if parent.poll() is None:
                parent.kill()
            try:
                _, error = parent.communicate(timeout=5)
            except subprocess.TimeoutExpired as expired:
                error = expired.stderr or b""
            raise AssertionError(
                "isolated worker did not reach readiness: " + error.decode(errors="replace")
            )
        child_pid = int(pid_file.read_text())

        def read_to_exit():
            parent.stdout.read()
            eof.set()

        reader = threading.Thread(target=read_to_exit, daemon=True)
        reader.start()
        parent.kill()
        parent.wait(timeout=5)
        assert eof.wait(5), "native worker outlived the killed UI process"
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if child_pid is not None and not eof.is_set():
            try:
                os.kill(child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
