from __future__ import annotations

import queue
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recovery_session import RecoveryJournal, RecoverySessionStore


def _start_journal(tmp_path):
    store = RecoverySessionStore(tmp_path / "recovery")
    journal = store.start_session(
        session_id="fault",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )
    return store, journal


def _close_in_background(journal):
    finished = threading.Event()
    errors = []

    def close():
        try:
            journal.close_interrupted()
        except Exception as error:
            errors.append(error)
        finally:
            finished.set()

    closer = threading.Thread(target=close, daemon=True)
    closer.start()
    return finished, errors, closer


def _wait_for_samples(journal, sample_count):
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with journal._metadata_lock:
            if journal._metadata["sample_count"] >= sample_count:
                return
        time.sleep(0.005)
    raise AssertionError("writer did not save the fixture PCM before the deadline")


def test_pcm_open_failure_is_observable_and_rejects_new_audio(tmp_path, monkeypatch):
    release_writer = threading.Event()
    original_writer = RecoveryJournal._writer_loop

    def gated_writer(journal):
        if release_writer.wait(timeout=2.0):
            original_writer(journal)

    monkeypatch.setattr(RecoveryJournal, "_writer_loop", gated_writer)
    _, journal = _start_journal(tmp_path)
    journal.pcm_path.mkdir()
    release_writer.set()
    journal._thread.join(timeout=2.0)
    try:
        assert not journal._thread.is_alive()
        assert journal._writer_error
        assert journal._metadata["writer_error"] == journal._writer_error
        assert not journal.append_pcm(np.array([1, 2, 3], dtype=np.int16))
    finally:
        journal.close_interrupted()


def test_dead_writer_and_full_queue_close_bounded_without_losing_saved_pcm(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(RecoveryJournal, "METADATA_INTERVAL_SECONDS", 1e30)
    store, journal = _start_journal(tmp_path)
    original_pcm = np.array([101, -202, 303], dtype=np.int16)
    assert journal.append_pcm(original_pcm)
    _wait_for_samples(journal, len(original_pcm))

    # A directory at the atomic-write temporary path triggers real filesystem
    # failure without touching ACLs or exhausting disk space.
    temporary = journal.metadata_path.with_name(".session.json.tmp")
    temporary.mkdir()
    journal._last_metadata_write = 0.0
    journal.METADATA_INTERVAL_SECONDS = 0.0
    assert journal.append_pcm(np.array([404], dtype=np.int16))
    journal._thread.join(timeout=2.0)
    assert not journal._thread.is_alive()
    assert journal._writer_error
    temporary.rmdir()
    saved_pcm = journal.pcm_path.read_bytes()
    assert saved_pcm == np.append(original_pcm, np.int16(404)).tobytes()

    # Preserve the saturated queue that can remain when a writer dies. Closing
    # must not wait for a nonexistent consumer to free a sentinel slot.
    while not journal._queue.full():
        journal._queue.put_nowait(b"\x00\x00")
    finished, errors, closer = _close_in_background(journal)
    returned_in_time = finished.wait(timeout=1.0)
    try:
        assert returned_in_time, "close blocked on the dead writer's full queue"
        assert not errors
        assert journal.pcm_path.read_bytes() == saved_pcm
        assert store.read_pcm(journal.session_id).tobytes() == saved_pcm
        assert not journal.append_pcm(original_pcm)
    finally:
        # Unblock the broken implementation so the failing regression leaves
        # neither a helper thread nor a pending filesystem write behind.
        if not returned_in_time:
            try:
                journal._queue.get_nowait()
            except queue.Empty:
                pass
        closer.join(timeout=2.0)


def test_metadata_failure_during_close_still_stops_writer_and_preserves_pcm(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(RecoveryJournal, "METADATA_INTERVAL_SECONDS", 1e30)
    _, journal = _start_journal(tmp_path)
    original_pcm = np.array([71, -82, 93], dtype=np.int16)
    assert journal.append_pcm(original_pcm)
    _wait_for_samples(journal, len(original_pcm))
    temporary = journal.metadata_path.with_name(".session.json.tmp")
    temporary.mkdir()
    finished, _, closer = _close_in_background(journal)
    returned_in_time = finished.wait(timeout=6.0)
    try:
        assert returned_in_time, "metadata failure left close waiting indefinitely"
        assert not journal._thread.is_alive(), "metadata error bypassed writer shutdown"
        assert not journal.append_pcm(original_pcm)
        assert journal.pcm_path.read_bytes() == original_pcm.tobytes()
    finally:
        temporary.rmdir()
        journal._close_writer()
        closer.join(timeout=2.0)


def test_close_drains_accepted_pcm_and_records_the_fsync_boundary(tmp_path):
    store, journal = _start_journal(tmp_path)
    blocks = [np.arange(1600, dtype=np.int16) + offset for offset in range(40)]
    for block in blocks:
        assert journal.append_pcm(block)
    journal.close_interrupted()

    status = journal.status()
    assert status["closed"]
    assert not status["writer_error"]
    assert status["accepted_sample_count"] == 64000
    assert status["sample_count"] == status["durable_sample_count"] == 64000
    assert store.read_pcm(journal.session_id).tobytes() == np.concatenate(blocks).tobytes()


def test_disk_write_does_not_hold_the_callback_metadata_lock(tmp_path, monkeypatch):
    import recovery_session

    _, journal = _start_journal(tmp_path)
    entered_write = threading.Event()
    release_write = threading.Event()
    original_write = recovery_session._write_json_atomic

    def delayed_write(path, payload):
        entered_write.set()
        if not release_write.wait(timeout=2):
            raise OSError("fixture disk write timed out")
        original_write(path, payload)

    monkeypatch.setattr(recovery_session, "_write_json_atomic", delayed_write)
    assert journal.append_pcm(np.array([1, 2, 3], dtype=np.int16))
    assert entered_write.wait(timeout=1)
    callback_done = threading.Event()
    accepted = []

    def append():
        accepted.append(journal.append_pcm(np.array([4, 5, 6], dtype=np.int16)))
        callback_done.set()

    callback = threading.Thread(target=append, daemon=True)
    callback.start()
    try:
        assert callback_done.wait(timeout=0.1), "callback waited for the disk write"
        assert accepted == [True]
    finally:
        release_write.set()
        callback.join(timeout=2)
        journal.close_interrupted()


def test_recovery_budget_rejects_new_audio_without_deleting_saved_pcm(tmp_path):
    store = RecoverySessionStore(tmp_path / "recovery", max_storage_bytes=12,
                                 min_free_bytes=0)
    journal = store.start_session(session_id="bounded", sample_rate=16000,
                                  channels=1, dtype="int16", model="fixture")
    first = np.array([1, 2, 3], dtype=np.int16)
    assert journal.append_pcm(first)
    assert journal.append_pcm(first)
    assert not journal.append_pcm(np.array([4], dtype=np.int16))
    journal.close_interrupted()
    assert journal.writer_error == "recovery_storage_limit"
    assert store.read_pcm("bounded").tolist() == [1, 2, 3, 1, 2, 3]
    import pytest
    with pytest.raises(OSError, match="恢复录音"):
        store.start_session(session_id="full", sample_rate=16000,
                            channels=1, dtype="int16", model="fixture")
    assert store.read_pcm("bounded").tolist() == [1, 2, 3, 1, 2, 3]


def test_recovery_reports_actual_prefix_when_metadata_is_stale(tmp_path):
    store, journal = _start_journal(tmp_path)
    assert journal.append_pcm(np.array([10, 20, 30], dtype=np.int16))
    journal.close_interrupted()
    payload = json.loads(journal.metadata_path.read_text(encoding="utf-8"))
    payload.update(sample_count=0, durable_sample_count=0, accepted_sample_count=6)
    journal.metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    session = store.list_recoverable()[0]
    assert session.sample_count == 3
    assert session.durable_sample_count == 0
    assert session.partial
    assert session.can_recover
    assert store.read_pcm("fault").tolist() == [10, 20, 30]


def test_corrupt_metadata_remains_visible_without_guessing_audio_format(tmp_path):
    store, journal = _start_journal(tmp_path)
    assert journal.append_pcm(np.array([10, 20, 30], dtype=np.int16))
    journal.close_interrupted()
    journal.metadata_path.write_text("{invalid", encoding="utf-8")

    sessions = store.list_recoverable()
    assert len(sessions) == 1
    session = sessions[0]
    assert session.session_id == "fault"
    assert not session.can_recover
    assert session.partial
    assert session.error == "recovery_metadata_invalid"
    assert store.read_pcm("fault").size == 0
    assert journal.pcm_path.read_bytes() == np.array([10, 20, 30], dtype=np.int16).tobytes()


def test_truncated_pcm_preserves_complete_samples_and_reports_partial(tmp_path):
    store, journal = _start_journal(tmp_path)
    assert journal.append_pcm(np.array([10, 20, 30], dtype=np.int16))
    journal.close_interrupted()
    journal.pcm_path.write_bytes(journal.pcm_path.read_bytes()[:-1])

    session = store.list_recoverable()[0]
    assert session.sample_count == 2
    assert session.partial
    assert store.read_pcm("fault").tolist() == [10, 20]
    assert journal.pcm_path.stat().st_size == 5


@pytest.mark.parametrize("version", [2, True, "1"])
def test_unknown_recovery_schema_stays_visible_without_interpreting_pcm(tmp_path, version):
    store, journal = _start_journal(tmp_path)
    original_pcm = np.array([10, 20, 30], dtype=np.int16).tobytes()
    assert journal.append_pcm(np.array([10, 20, 30], dtype=np.int16))
    journal.close_interrupted()
    metadata = json.loads(journal.metadata_path.read_text(encoding="utf-8"))
    metadata["schema_version"] = version
    journal.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    session = store.list_recoverable()[0]
    assert not session.can_recover
    assert session.error == "recovery_metadata_invalid"
    assert store.read_pcm("fault").size == 0
    assert journal.pcm_path.read_bytes() == original_pcm
