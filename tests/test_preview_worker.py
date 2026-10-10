import multiprocessing
from pathlib import Path
import sys
import threading
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def fake_preview_worker(commands, responses, heartbeat, _worker_config):
    heartbeat.value = 1.0e12
    responses.put({"kind": "ready"})
    committed = {}
    while True:
        command = commands.get()
        if command["kind"] == "shutdown":
            return
        if command["kind"] == "create_session":
            committed[command["session_id"]] = ""
            responses.put(
                {
                    "kind": "response",
                    "request_id": command["request_id"],
                    "ok": True,
                }
            )
            continue
        if command["kind"] == "accept_pcm":
            from preview_worker import _preview_event_payload
            from streaming_transcriber import PreviewEvent
            session_id = command["session_id"]
            samples = np.frombuffer(command["pcm"], dtype=np.int16)
            delta = "测" if len(samples) else ""
            committed[session_id] += delta
            responses.put(
                {
                    "kind": "response",
                    "request_id": command["request_id"],
                    "ok": True,
                    "event": _preview_event_payload(PreviewEvent(
                        text=committed[session_id], delta=delta,
                        segment_id=0, audio_end_sample=len(samples),
                        committed_text=committed[session_id])),
                }
            )


def unready_preview_worker(commands, _responses, heartbeat, _worker_config):
    heartbeat.value = 1.0e12
    while commands.get().get("kind") != "shutdown":
        pass


def test_preview_health_reads_and_shutdown_do_not_wait_for_startup_timeout():
    from preview_worker import SupervisedPreviewTranscriber

    preview = SupervisedPreviewTranscriber(
        "unused.yaml", worker_target=unready_preview_worker, startup_timeout=2.0,
    )
    errors = []

    def load():
        try:
            preview.load()
        except RuntimeError as error:
            errors.append(error)

    loader = threading.Thread(target=load)
    loader.start()
    deadline = time.monotonic() + 1.0
    while preview._process is None and time.monotonic() < deadline:
        time.sleep(0.005)
    try:
        started = time.perf_counter()
        assert not preview.is_ready
        assert preview.worker_pid is None
        assert preview.last_heartbeat == 0.0
        assert time.perf_counter() - started < 0.15
        started = time.perf_counter()
        preview.shutdown()
        assert time.perf_counter() - started < 1.5
    finally:
        preview.shutdown()
        loader.join(3.0)
    assert not loader.is_alive()
    assert errors
    assert preview.worker_pid is None


def test_preview_model_and_session_live_outside_ui_process():
    from preview_worker import SupervisedPreviewTranscriber

    preview = SupervisedPreviewTranscriber(
        "unused.yaml",
        worker_target=fake_preview_worker,
        startup_timeout=2.0,
    )
    preview.load()
    try:
        assert preview.worker_pid != multiprocessing.current_process().pid
        session = preview.create_session()
        event = preview.accept_pcm(
            session,
            np.array([1, 2, 3], dtype=np.int16),
            16000,
        )
        assert event.delta == "测"
        assert session.committed_text == "测"
    finally:
        preview.shutdown()


def test_preview_worker_shutdown_is_idempotent():
    from preview_worker import SupervisedPreviewTranscriber

    preview = SupervisedPreviewTranscriber(
        "unused.yaml",
        worker_target=fake_preview_worker,
        startup_timeout=2.0,
    )
    preview.load()
    preview.shutdown()
    preview.shutdown()
    assert not preview.is_ready


def test_preview_readiness_and_shutdown_share_one_process_lifecycle_lock():
    from preview_worker import SupervisedPreviewTranscriber

    alive_check_entered = threading.Event()
    release_alive_check = threading.Event()
    shutdown_finished = threading.Event()
    errors = []

    class BlockingProcess:
        pid = 123

        def __init__(self):
            self._first_alive_check = True

        def is_alive(self):
            if self._first_alive_check:
                self._first_alive_check = False
                alive_check_entered.set()
                assert release_alive_check.wait(timeout=2.0)
                return True
            return getattr(self, "_alive", True)

        def terminate(self):
            self._alive = False

        def join(self, timeout=None):
            del timeout

    class Queue:
        def put_nowait(self, _value):
            pass

        def close(self):
            pass

        def cancel_join_thread(self):
            pass

    preview = SupervisedPreviewTranscriber("unused.yaml")
    preview._process = BlockingProcess()
    preview._ready = True
    preview._commands = Queue()
    preview._responses = Queue()

    def read_readiness():
        try:
            preview.is_ready
        except Exception as error:
            errors.append(error)

    reader = threading.Thread(target=read_readiness)
    reader.start()
    assert alive_check_entered.wait(timeout=1.0)

    stopper = threading.Thread(
        target=lambda: (preview.shutdown(), shutdown_finished.set())
    )
    stopper.start()
    try:
        assert not shutdown_finished.wait(timeout=0.05)
    finally:
        release_alive_check.set()
        reader.join(timeout=1.0)
        stopper.join(timeout=1.0)

    assert not reader.is_alive()
    assert not stopper.is_alive()
    assert not errors
    assert not preview.is_ready
