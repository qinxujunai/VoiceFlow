from __future__ import annotations

import errno
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard
from history_store import HistoryStore


def _coordinator(tmp_path, *, clipboard_fails=False):
    state = {"clipboard": "", "copy_attempts": 0, "paste_attempts": 0}
    target = TargetSnapshot(101, 202, "fixture-edit", True, True, True)

    def copy(text):
        state["copy_attempts"] += 1
        if clipboard_fails:
            raise OSError("fixture clipboard is unavailable")
        state["clipboard"] = text

    def dispatch():
        state["paste_attempts"] += 1
        return True

    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=copy, paste=lambda: state["clipboard"], retry_delays=(0.0,)
        ),
        inspect_target=lambda: target,
        dispatch_paste=dispatch,
        ledger_dir=tmp_path / "pending",
    )
    return coordinator, state


def test_history_append_syncs_complete_file_before_return(tmp_path, monkeypatch):
    history_path = tmp_path / "history.jsonl"
    history = HistoryStore(history_path)
    real_fsync = os.fsync
    synchronized = []
    append_returned = False

    def observe_fsync(descriptor):
        assert not append_returned
        file_stat = os.fstat(descriptor)
        content = history_path.read_bytes()
        # Reading the real file from a separate descriptor proves the text
        # buffer was flushed before fsync, rather than only on context exit.
        assert file_stat.st_size == len(content) > 0
        assert file_stat.st_ino == history_path.stat().st_ino
        assert content.endswith(b"\n")
        assert json.loads(content)["corrected_text"] == "完整终稿🙂"
        real_fsync(descriptor)
        synchronized.append(file_stat.st_size)

    monkeypatch.setattr(os, "fsync", observe_fsync)
    entry = history.append(corrected_text="完整终稿🙂", session_id="durable-history")
    append_returned = True
    assert entry["corrected_text"] == "完整终稿🙂"
    assert synchronized, "append returned without synchronizing its real history file"


def test_history_fsync_failure_is_not_reported_as_successful_append(tmp_path, monkeypatch):
    history = HistoryStore(tmp_path / "history.jsonl")

    def fail_fsync(descriptor):
        assert os.fstat(descriptor).st_size > 0
        raise OSError(errno.EIO, "fixture history synchronization failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="history synchronization failed"):
        history.append(corrected_text="必须保留录音", session_id="history-failure")


def test_pending_ledger_syncs_complete_temporary_file_before_replace(tmp_path, monkeypatch):
    coordinator, _ = _coordinator(tmp_path)
    text = "已持久保存的终稿🙂"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    temporary = coordinator.ledger_dir / ".durable-ledger.json.tmp"
    published = coordinator.ledger_dir / "durable-ledger.json"
    real_fsync = os.fsync
    synchronized = []

    def observe_fsync(descriptor):
        assert not published.exists(), "pending ledger was published before synchronization"
        content = temporary.read_bytes()
        assert os.fstat(descriptor).st_size == len(content) > 0
        assert os.fstat(descriptor).st_ino == temporary.stat().st_ino
        assert content.endswith(b"\n")
        payload = json.loads(content)
        assert payload["text"] == text
        assert payload["text_sha256"] == digest
        real_fsync(descriptor)
        synchronized.append(True)

    monkeypatch.setattr(os, "fsync", observe_fsync)
    path = coordinator._write_pending("durable-ledger", text, digest)
    assert synchronized, "pending ledger was published without synchronizing its real file"
    assert path == published
    assert json.loads(published.read_text(encoding="utf-8"))["text"] == text


def test_pending_ledger_fsync_failure_aborts_successful_publication(tmp_path, monkeypatch):
    coordinator, _ = _coordinator(tmp_path)

    def fail_fsync(descriptor):
        assert os.fstat(descriptor).st_size > 0
        raise OSError(errno.EIO, "fixture ledger synchronization failed")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="ledger synchronization failed"):
        coordinator._write_pending("sync-failure", "保留终稿", "fixture-digest")
    assert not (coordinator.ledger_dir / "sync-failure.json").exists()


@pytest.mark.parametrize("clipboard_fails", [False, True], ids=["clipboard-ok", "both-fail"])
def test_real_ledger_path_failure_still_attempts_clipboard_and_never_pastes(
    tmp_path, clipboard_fails
):
    coordinator, state = _coordinator(tmp_path, clipboard_fails=clipboard_fails)
    coordinator.ledger_dir.mkdir()
    blocked_path = coordinator.ledger_dir / "blocked.json"
    blocked_path.mkdir()
    text = "落盘失败也尝试保全最后文字🙂"

    result = coordinator.deliver(text, start_target=None, session_id="blocked")

    assert state["copy_attempts"] == 1
    assert state["paste_attempts"] == 0
    assert not result.paste_dispatched
    assert not result.landed_confirmed
    assert not result.recovery_saved, "failed ledger write cannot mean saved text"
    assert result.reason.startswith("pending_write_failed")
    assert blocked_path.is_dir()
    if clipboard_fails:
        assert not result.clipboard_verified
        assert not result.clipboard_only
        assert result.output_status == "delivery_failed"
    else:
        assert state["clipboard"] == text
        assert result.clipboard_verified
        assert result.clipboard_only
        assert result.output_status == "clipboard_verified_only"
        assert result.reason == "pending_write_failed"


def test_acknowledgement_failure_never_obscures_verified_clipboard(tmp_path):
    coordinator, state = _coordinator(tmp_path)
    coordinator.ledger_dir.mkdir()
    blocked = coordinator.ledger_dir / "blocked.json"
    blocked.mkdir()
    result = coordinator.deliver("已保全的终稿", start_target=None,
                                 session_id="blocked", allow_paste=False)
    assert result.clipboard_verified
    assert coordinator.acknowledge("blocked") is False
    assert blocked.is_dir()
    assert state["clipboard"] == "已保全的终稿"
