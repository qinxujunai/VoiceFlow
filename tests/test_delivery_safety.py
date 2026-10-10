"""Stop-time delivery guards: never paste into a later focus or clipboard."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _coordinator(tmp_path, *, after_copy=None):
    from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard

    state = {"text": "", "target": TargetSnapshot(101, 202, "edit", True, True, True),
             "pastes": 0}

    def copy(text):
        state["text"] = text
        if after_copy:
            after_copy(state)

    def dispatch():
        state["pastes"] += 1
        return True

    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(copy=copy, paste=lambda: state["text"],
                                    retry_delays=(0.0,)),
        inspect_target=lambda: state["target"], dispatch_paste=dispatch,
        ledger_dir=tmp_path / "pending",
    )
    return coordinator, state


def test_focus_change_during_clipboard_write_never_receives_paste(tmp_path):
    from delivery import TargetSnapshot

    def change(state):
        state["target"] = TargetSnapshot(303, 404, "other", True, True, True)

    coordinator, state = _coordinator(tmp_path, after_copy=change)
    result = coordinator.deliver("保留完整文字", start_target=None, session_id="focus-race")
    assert state["pastes"] == 0
    assert result.clipboard_verified
    assert result.reason == "target_changed"
    assert (tmp_path / "pending" / "focus-race.json").is_file()


def test_dispatch_alone_is_never_confirmed_insertion(tmp_path):
    coordinator, state = _coordinator(tmp_path)
    result = coordinator.deliver("已发送不等于已输入", start_target=None, session_id="unverified")
    assert state["pastes"] == 1
    assert result.paste_dispatched
    assert result.landed_confirmed is False
    assert result.output_status == "clipboard_verified_paste_dispatched"


def test_clipboard_competition_after_readback_never_pastes_other_text(tmp_path):
    coordinator, state = _coordinator(tmp_path)
    reads = 0

    def read():
        nonlocal reads
        reads += 1
        return state["text"] if reads == 1 else "另一个程序的新内容"

    coordinator.clipboard._paste = read
    result = coordinator.deliver("我的文字", start_target=None, session_id="clipboard-race")
    assert state["pastes"] == 0
    assert result.reason == "clipboard_changed"
    assert not result.clipboard_verified
    assert result.recovery_saved
    assert result.output_status == "recovery_saved_clipboard_unavailable"
    assert (tmp_path / "pending" / "clipboard-race.json").is_file()


def test_focus_change_while_transcribing_preserves_stop_target(tmp_path):
    from delivery import TargetSnapshot

    coordinator, state = _coordinator(tmp_path)
    stop = state["target"]
    state["target"] = TargetSnapshot(303, 404, "other", True, True, True)
    result = coordinator.deliver("停止时的文字", start_target=None, stop_target=stop,
                                 session_id="transcription-focus-race")
    assert state["pastes"] == 0
    assert result.reason == "target_changed"


@pytest.mark.parametrize("reason", ["password", "disabled", "read_only"])
def test_positive_nonwritable_evidence_blocks_paste(reason):
    from delivery import TargetSnapshot

    target = TargetSnapshot(101, 202, "edit", False, True, True,
                            rejection_reason=reason)
    assert not target.paste_decision_from(None).allowed
    assert target.paste_decision_from(None).reason == reason


def test_history_keeps_confirmation_separate_from_dispatch(tmp_path):
    from history_store import HistoryStore

    history = HistoryStore(tmp_path / "history.jsonl")
    history.append(corrected_text="终稿", paste_dispatched=True, landed_confirmed=False)
    assert history.read_recent(1)[0]["landed_confirmed"] is False


def test_unknown_integrity_is_reported_separately_from_higher_integrity():
    from delivery import TargetSnapshot

    unknown = TargetSnapshot(101, 202, "edit", True, None, True)
    assert unknown.paste_decision_from(None).reason == "target_integrity_unknown"


@pytest.mark.parametrize("changed", [
    {"document_id": 2}, {"selection_start": 4}, {"selection_end": 7},
    {"document_length": 20},
])
def test_same_window_editor_changes_do_not_receive_stale_dictation(changed):
    from dataclasses import replace
    from delivery import TargetSnapshot

    stop = TargetSnapshot(101, 202, "editor", True, True, True,
                          document_id=1, selection_start=3, selection_end=3,
                          document_length=10)
    assert not replace(stop, **changed).same_input_context(stop)
    assert replace(stop).same_input_context(stop)
