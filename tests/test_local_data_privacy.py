"""Explicit deletion must not resurrect final text from a pending delivery."""

import hashlib
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app_controller import AppController
from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard
from history_store import HistoryStore
from main import VoiceInputSystem
from output_handler import OutputHandler
from recording_state import RecordingStateMachine
from recovery_session import RecoverySessionStore


def fixture(tmp_path):
    clipboard = {"text": ""}
    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(copy=lambda value: clipboard.update(text=value),
                                    paste=lambda: clipboard["text"], retry_delays=(0.0,)),
        inspect_target=lambda: TargetSnapshot(101, 202, "fixture", True, True, True),
        dispatch_paste=lambda: pytest.fail("data operations must never paste"),
        ledger_dir=tmp_path / "delivery-pending")
    output = object.__new__(OutputHandler)
    output._coordinator = coordinator
    output.last_text = "最后的私密终稿🙂"
    output._focus_monitor = SimpleNamespace(stop_tracking=lambda: None)
    output._prepare_text = lambda value: value
    output._log_focus_trace = lambda _value: None
    app = object.__new__(VoiceInputSystem)
    app._recording_state = RecordingStateMachine()
    app.controller = AppController()
    app.controller.mark_ready()
    app.history = HistoryStore(tmp_path / "history.jsonl")
    app._recovery_store = RecoverySessionStore(tmp_path / "recovery")
    app.output_handler = output
    app._latest_text = "最后的预览"
    app._final_cache_lock = threading.Lock()
    app._final_segments = ["最后的分段"]
    app.overlay = SimpleNamespace(show_error=Mock(), show_result=Mock(), hide_after=Mock())
    text = output.last_text
    app.history.append(corrected_text=text, session_id="fixture")
    coordinator._write_pending("fixture", text, hashlib.sha256(text.encode()).hexdigest())
    return app, coordinator, clipboard


def test_clear_local_removes_pending_temporary_and_memory_without_touching_clipboard(tmp_path):
    app, coordinator, clipboard = fixture(tmp_path)
    temporary = coordinator.ledger_dir / ".interrupted.json.tmp"
    temporary.write_text("unfinished private final", encoding="utf-8")
    clipboard["text"] = "Windows clipboard belongs to the user"
    result = app._clear_local_dictation_data()
    assert result["pending_deliveries"] == 2
    assert list(coordinator.ledger_dir.iterdir()) == []
    assert app.history.last() is None
    assert app.output_handler.last_text == ""
    assert app._latest_text == ""
    assert app._final_segments == []
    assert coordinator.recover_pending_to_clipboard() == []
    assert clipboard["text"] == "Windows clipboard belongs to the user"


def test_pending_removal_failure_is_visible_and_history_stays_available(tmp_path):
    app, coordinator, _ = fixture(tmp_path)
    blocked = coordinator.ledger_dir / "blocked.json"
    blocked.mkdir()
    with pytest.raises(OSError):
        app._clear_local_dictation_data()
    assert app.history.last()["corrected_text"] == "最后的私密终稿🙂"
    assert blocked.is_dir()


def test_copy_reserves_idle_until_pending_write_and_clipboard_finish(tmp_path):
    app, coordinator, clipboard = fixture(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = app.output_handler.copy_only

    def slow_copy(value):
        entered.set()
        assert release.wait(3)
        return original(value)

    app.output_handler.copy_only = slow_copy
    thread = threading.Thread(target=lambda: app._copy_last_text())
    thread.start()
    try:
        assert entered.wait(3)
        with pytest.raises(RuntimeError):
            app._clear_local_dictation_data()
        assert not app._recording_state.claim_start()
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive()
    assert clipboard["text"] == "最后的私密终稿🙂"


def test_copy_cannot_publish_an_old_final_during_clear(tmp_path):
    app, _, clipboard = fixture(tmp_path)
    with app._recording_state.idle_operation() as claimed:
        assert claimed
        assert app._copy_text("old final") == "busy"
    assert clipboard["text"] == ""


def test_startup_does_not_allow_clear_or_recovery_before_pending_replay_finishes(tmp_path):
    app, coordinator, _ = fixture(tmp_path)
    app.controller = AppController()
    with pytest.raises(RuntimeError):
        app._clear_local_dictation_data()
    assert app._recover_session("fixture")["ok"] is False
    assert (coordinator.ledger_dir / "fixture.json").is_file()


def test_clear_history_prevents_pending_replay_and_clears_last_result(tmp_path):
    app, coordinator, _ = fixture(tmp_path)
    assert app._clear_history() == 1
    assert coordinator.recover_pending_to_clipboard() == []
    assert app.output_handler.last_text == ""


def test_delete_history_removes_matching_pending_but_keeps_other_final(tmp_path):
    app, coordinator, _ = fixture(tmp_path)
    coordinator._write_pending("other", "other text", hashlib.sha256(b"other text").hexdigest())
    row = app.history.read_recent()[0]
    token = app._delete_history_entry(row["_entry_id"])
    assert token and app.history.last() is None
    assert not (coordinator.ledger_dir / "fixture.json").exists()
    assert (coordinator.ledger_dir / "other.json").is_file()


@pytest.mark.parametrize("other_id", ["other", "recovered-other"])
def test_delete_history_keeps_unrelated_pending_with_identical_text(tmp_path, other_id):
    app, coordinator, _ = fixture(tmp_path)
    row = app.history.read_recent()[0]
    text = row["corrected_text"]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    coordinator._write_pending(other_id, text, digest)
    coordinator._write_pending("recovered-fixture", text, digest)
    token = app._delete_history_entry(row["_entry_id"])
    assert token and app.history.last() is None
    assert not (coordinator.ledger_dir / "fixture.json").exists()
    assert not (coordinator.ledger_dir / "recovered-fixture.json").exists()
    assert (coordinator.ledger_dir / f"{other_id}.json").is_file()
    recovered = coordinator.recover_pending_to_clipboard()
    assert [(entry["session_id"], entry["text"]) for entry in recovered] == [(other_id, text)]


@pytest.mark.parametrize("session_id", [None, ""])
def test_delete_legacy_history_without_session_id_does_not_guess_pending_ownership(tmp_path, session_id):
    app, coordinator, _ = fixture(tmp_path)
    text = app.output_handler.last_text
    app.history.clear()
    app.history.append(corrected_text=text, session_id=session_id)
    row = app.history.read_recent()[0]
    token = app._delete_history_entry(row["_entry_id"])
    assert token and app.history.last() is None
    assert (coordinator.ledger_dir / "fixture.json").is_file()
    assert app.output_handler.last_text == ""


def test_pending_cleanup_refuses_a_directory_link_and_preserves_target(tmp_path):
    app, coordinator, _ = fixture(tmp_path)
    # A root link must never turn an app cleanup into removal elsewhere.
    external = tmp_path / "outside"
    external.mkdir()
    private = external / "fixture.json"
    private.write_text("external data", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("directory symlinks unavailable")
        import _winapi
        _winapi.CreateJunction(str(external), str(link))
    coordinator.ledger_dir = link
    with pytest.raises(OSError):
        app._clear_local_dictation_data()
    assert private.read_text(encoding="utf-8") == "external data"
