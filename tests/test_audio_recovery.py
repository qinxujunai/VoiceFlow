from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import queue
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from audio_worker import SupervisedAudioCapture, _audio_worker_main
from recovery_session import RecoverySessionStore


SAMPLE_COUNT = 32 * 1600
_accepted_path = None


class _FixtureInputStream:
    """Replace only the physical microphone; retain the real capture callback."""

    def __init__(self, *, callback, **_options):
        self.callback = callback

    def start(self):
        audio = np.arange(SAMPLE_COUNT).astype(np.int16)
        for start in range(0, SAMPLE_COUNT, 1600):
            block = audio[start : start + 1600].reshape(-1, 1)
            self.callback(block, len(block), None, None)
        accepted_path = Path(_accepted_path)
        temporary = accepted_path.with_suffix(".tmp")
        temporary.write_text(str(SAMPLE_COUNT), encoding="ascii")
        os.replace(temporary, accepted_path)

    def abort(self):
        pass

    def close(self):
        pass


def _fixture_worker(commands, events, heartbeat, config_path):
    global _accepted_path
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    _accepted_path = config["fixture_accepted_path"]
    import audio_capture

    audio_capture.sd.InputStream = _FixtureInputStream
    _audio_worker_main(commands, events, heartbeat, config_path)


def _slow_persistence_worker(commands, events, heartbeat, config_path):
    from recovery_session import RecoveryJournal

    original_writer = RecoveryJournal._writer_loop

    def delayed_writer(journal):
        time.sleep(0.6)
        original_writer(journal)

    RecoveryJournal._writer_loop = delayed_writer
    _fixture_worker(commands, events, heartbeat, config_path)


def test_shutdown_allows_active_journal_to_finish_bounded_flush(tmp_path):
    config_path, accepted_path, recovery = _fixture_config(tmp_path)
    store = RecoverySessionStore(recovery["root"])
    capture = SupervisedAudioCapture(config_path, worker_target=_slow_persistence_worker,
                                     startup_timeout=3.0, command_timeout=2.0)
    try:
        capture.create_recovery_journal(store, session_id=recovery["session_id"],
                                        model="fixture")
        capture.start_recording()
        _wait_for_accepted(accepted_path)
        started = time.monotonic()
        capture.shutdown()
        assert time.monotonic() - started < 3.0
        _assert_recoverable_pcm(recovery)
        payload = json.loads((Path(recovery["root"]) / recovery["session_id"] /
                              "session.json").read_text(encoding="utf-8"))
        assert payload["durable_sample_count"] == SAMPLE_COUNT
    finally:
        capture.shutdown()


def _fixture_config(tmp_path):
    config_path = tmp_path / "audio.json"
    accepted_path = tmp_path / "accepted.txt"
    config_path.write_text(
        json.dumps(
            {
                "audio": {"sample_rate": 16000, "channels": 1, "dtype": "int16"},
                "vad": {"enabled": False},
                "fixture_accepted_path": str(accepted_path),
            }
        ),
        encoding="utf-8",
    )
    recovery = {
        "root": str(tmp_path / "recovery"),
        "session_id": "worker-owned",
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "int16",
        "model": "fixture",
    }
    return config_path, accepted_path, recovery


def _wait_for_accepted(path):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if path.exists():
            assert int(path.read_text(encoding="ascii")) == SAMPLE_COUNT
            return
        time.sleep(0.01)
    raise AssertionError("physical fixture callback did not accept PCM in time")


def _response(events, request_id):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.1)
        except queue.Empty:
            continue
        if event.get("kind") == "startup_error":
            raise AssertionError(event["error"])
        if event.get("request_id") == request_id:
            assert event.get("ok"), event
            return event
    raise AssertionError(f"worker did not answer {request_id} in time")


def _assert_recoverable_pcm(recovery):
    session_dir = Path(recovery["root"]) / recovery["session_id"]
    assert (session_dir / "audio.pcm").is_file(), "accepted PCM has no worker journal"
    metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    assert metadata["state"] == "recoverable"
    assert metadata["sample_count"] == SAMPLE_COUNT
    store = RecoverySessionStore(recovery["root"])
    sessions = store.list_recoverable()
    assert [session.session_id for session in sessions] == [recovery["session_id"]]
    np.testing.assert_array_equal(
        store.read_pcm(recovery["session_id"]),
        np.arange(SAMPLE_COUNT).astype(np.int16),
    )


def _release_channels(*channels):
    for channel in channels:
        channel.cancel_join_thread()
        channel.close()


def test_saturated_pcm_event_queue_keeps_complete_worker_recovery(tmp_path):
    context = multiprocessing.get_context("spawn")
    config_path, accepted_path, recovery = _fixture_config(tmp_path)
    commands = context.Queue(maxsize=8)
    events = context.Queue(maxsize=1)
    heartbeat = context.Value("d", time.monotonic())
    worker = context.Process(
        target=_fixture_worker,
        args=(commands, events, heartbeat, str(config_path)),
        name="VoiceFlow-Test-Recovery",
    )
    worker.start()
    try:
        assert events.get(timeout=5.0)["kind"] == "ready"
        commands.put({"kind": "start", "request_id": "start", "recovery": recovery})
        # Do not consume events until all 32 microphone blocks have arrived.
        # The one-slot IPC queue necessarily drops preview PCM notifications.
        _wait_for_accepted(accepted_path)
        _response(events, "start")
        commands.put({"kind": "freeze", "request_id": "freeze"})
        assert _response(events, "freeze")["samples"] == SAMPLE_COUNT
        commands.put({"kind": "shutdown"})
        worker.join(timeout=5.0)
        assert not worker.is_alive(), "recovery flush exceeded shutdown deadline"
        assert worker.exitcode == 0
        _assert_recoverable_pcm(recovery)
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2.0)
        _release_channels(commands, events)
        worker.close()


def _isolated_parent(connection, config_path, recovery):
    context = multiprocessing.get_context("spawn")
    commands = context.Queue(maxsize=8)
    events = context.Queue(maxsize=8)
    heartbeat = context.Value("d", time.monotonic())
    worker = context.Process(
        target=_fixture_worker,
        args=(commands, events, heartbeat, config_path),
        name="VoiceFlow-Test-Orphan-Recovery",
    )
    worker.start()
    connection.send(worker.pid)
    connection.close()
    assert events.get(timeout=5.0)["kind"] == "ready"
    commands.put({"kind": "start", "request_id": "start", "recovery": recovery})
    # Stay alive and consume notifications as a normal UI receiver would. The
    # test terminates this owned process after the physical fixture is accepted.
    while True:
        events.get()


@pytest.mark.skipif(os.name != "nt", reason="Windows process-handle lifetime check")
def test_killed_isolated_parent_flushes_worker_pcm_and_exits_bounded(tmp_path):
    context = multiprocessing.get_context("spawn")
    config_path, accepted_path, recovery = _fixture_config(tmp_path)
    receiving, sending = context.Pipe(duplex=False)
    parent = context.Process(
        target=_isolated_parent,
        args=(sending, str(config_path), recovery),
        name="VoiceFlow-Test-Isolated-Parent",
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    worker_handle = None
    parent.start()
    sending.close()
    try:
        assert receiving.poll(timeout=5.0), "isolated parent did not identify its worker"
        worker_pid = receiving.recv()
        # Retain this exact owned process handle before terminating its parent;
        # cleanup never relies on a process name or a reusable PID lookup.
        worker_handle = kernel32.OpenProcess(0x00100000 | 0x0001, False, worker_pid)
        assert worker_handle, ctypes.WinError(ctypes.get_last_error())
        _wait_for_accepted(accepted_path)
        parent.terminate()
        parent.join(timeout=2.0)
        assert not parent.is_alive()
        assert kernel32.WaitForSingleObject(worker_handle, 5000) == 0, (
            "audio worker outlived its killed parent beyond the flush deadline"
        )
        _assert_recoverable_pcm(recovery)
    finally:
        if parent.is_alive():
            parent.terminate()
            parent.join(timeout=2.0)
        if worker_handle:
            if kernel32.WaitForSingleObject(worker_handle, 0) == 258:
                kernel32.TerminateProcess(worker_handle, 1)
                kernel32.WaitForSingleObject(worker_handle, 2000)
            kernel32.CloseHandle(worker_handle)
        receiving.close()
        parent.close()


def test_supervised_capture_uses_worker_journal_and_removes_it_after_delivery(tmp_path):
    config_path, accepted_path, recovery = _fixture_config(tmp_path)
    store = RecoverySessionStore(recovery["root"])
    capture = SupervisedAudioCapture(config_path, worker_target=_fixture_worker,
                                     startup_timeout=5.0, command_timeout=2.0)
    try:
        journal = capture.create_recovery_journal(
            store, session_id=recovery["session_id"], model="fixture"
        )
        capture.start_recording()
        _wait_for_accepted(accepted_path)
        capture.freeze_recording()
        audio = capture.stop_recording()
        np.testing.assert_array_equal(audio, np.arange(SAMPLE_COUNT).astype(np.int16))
        _assert_recoverable_pcm(recovery)
        assert not journal.writer_error
        # This method is called only after clipboard verification and history.
        journal.mark_delivered("verified-final-sha")
        assert not (Path(recovery["root"]) / recovery["session_id"]).exists()
    finally:
        capture.shutdown()
    assert not (Path(recovery["root"]) / recovery["session_id"]).exists()


def test_pcm_ipc_gap_never_concatenates_later_samples_at_the_wrong_offset(tmp_path):
    config_path, _, _ = _fixture_config(tmp_path)
    capture = SupervisedAudioCapture(config_path)
    first = np.array([1, 2, 3], dtype=np.int16)
    late = np.array([7, 8, 9], dtype=np.int16)
    capture._accept_pcm(first.tobytes(), start_sample=0)
    capture._accept_pcm(late.tobytes(), start_sample=6)
    assert capture.sample_count == 3
    assert capture.snapshot_audio().tolist() == [1, 2, 3]
    assert capture.preview_pcm_gap


def test_recovery_limit_is_reported_but_complete_stopped_audio_remains_available(tmp_path):
    config_path, accepted_path, recovery = _fixture_config(tmp_path)
    store = RecoverySessionStore(recovery["root"], max_storage_bytes=3200,
                                 min_free_bytes=0)
    capture = SupervisedAudioCapture(config_path, worker_target=_fixture_worker,
                                     startup_timeout=5.0, command_timeout=2.0)
    try:
        journal = capture.create_recovery_journal(store, session_id="limited", model="fixture")
        capture.start_recording()
        _wait_for_accepted(accepted_path)
        deadline = time.monotonic() + 2.0
        while not capture.recovery_error and time.monotonic() < deadline:
            time.sleep(0.01)
        assert capture.recovery_error == "recovery_storage_limit"
        capture.freeze_recording()
        audio = capture.stop_recording()
        np.testing.assert_array_equal(audio, np.arange(SAMPLE_COUNT).astype(np.int16))
        assert journal.close_interrupted()
        assert journal.writer_error == "recovery_storage_limit"
        assert store.read_pcm("limited").tolist() == list(range(1600))
    finally:
        capture.shutdown()
