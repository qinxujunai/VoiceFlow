from __future__ import annotations

import json
import os
import sys
import time
import types
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_recovery_journal_preserves_pcm_and_discovers_interrupted_session(tmp_path):
    from recovery_session import RecoverySessionStore

    store = RecoverySessionStore(tmp_path / "recovery", retention_hours=24)
    journal = store.start_session(
        session_id="session-001",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )

    journal.append_pcm(np.array([1, 2, 3, 4], dtype=np.int16))
    journal.append_pcm(np.array([5, 6], dtype=np.int16))
    journal.mark_state("recording", preview_text="已经确认")
    journal.close_interrupted()

    recovered = store.list_recoverable()

    assert len(recovered) == 1
    assert recovered[0].session_id == "session-001"
    assert recovered[0].sample_count == 6
    assert recovered[0].preview_text == "已经确认"
    assert recovered[0].pcm_path.read_bytes() == np.array(
        [1, 2, 3, 4, 5, 6], dtype=np.int16
    ).tobytes()


def test_recovery_journal_success_removes_audio_only_after_delivery(tmp_path):
    from recovery_session import RecoverySessionStore

    store = RecoverySessionStore(tmp_path / "recovery", retention_hours=24)
    journal = store.start_session(
        session_id="session-002",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )
    journal.append_pcm(np.arange(10, dtype=np.int16))
    session_dir = journal.session_dir

    journal.mark_delivered("text-sha")

    assert not session_dir.exists()
    assert store.list_recoverable() == []


def test_recovery_store_purges_sessions_older_than_retention(tmp_path):
    from recovery_session import RecoverySessionStore

    root = tmp_path / "recovery"
    store = RecoverySessionStore(root, retention_hours=24)
    journal = store.start_session(
        session_id="expired",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )
    journal.append_pcm(np.ones(4, dtype=np.int16))
    journal.close_interrupted()
    old = time.time() - (25 * 60 * 60)
    os.utime(journal.metadata_path, (old, old))

    removed = store.purge_expired(now=time.time())

    assert removed == ("expired",)
    assert not journal.session_dir.exists()


def test_recovery_store_reads_and_deletes_only_exact_session(tmp_path):
    from recovery_session import RecoverySessionStore

    store = RecoverySessionStore(tmp_path / "recovery", retention_hours=24)
    journal = store.start_session(
        session_id="recover-me",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )
    journal.append_pcm(np.array([7, 8, 9], dtype=np.int16))
    journal.close_interrupted()

    assert store.read_pcm("recover-me").tolist() == [7, 8, 9]
    assert store.read_pcm("../escape").size == 0
    assert store.delete("../escape") is False
    assert store.delete("recover-me") is True
    assert store.list_recoverable() == []


def test_verified_clipboard_retries_and_requires_exact_readback():
    from delivery import VerifiedClipboard

    stored = {"value": ""}
    attempts = []

    def copy(value):
        attempts.append(value)
        if len(attempts) == 1:
            raise RuntimeError("clipboard locked")
        stored["value"] = value

    clipboard = VerifiedClipboard(
        copy=copy,
        paste=lambda: stored["value"],
        sleeper=lambda _delay: None,
        retry_delays=(0.0, 0.0, 0.0),
    )

    result = clipboard.write_verified("中英 mixed 😊")

    assert result.verified is True
    assert result.attempts == 2
    assert stored["value"] == "中英 mixed 😊"


def test_verified_clipboard_never_claims_success_on_mismatched_readback():
    from delivery import VerifiedClipboard

    clipboard = VerifiedClipboard(
        copy=lambda _value: None,
        paste=lambda: "旧内容",
        sleeper=lambda _delay: None,
        retry_delays=(0.0, 0.0),
    )

    result = clipboard.write_verified("新内容")

    assert result.verified is False
    assert result.attempts == 2
    assert result.error == "clipboard_readback_mismatch"


def test_delivery_only_dispatches_paste_to_same_confirmed_editable_target(tmp_path):
    from delivery import (
        DeliveryCoordinator,
        TargetSnapshot,
        VerifiedClipboard,
    )

    current = TargetSnapshot(
        window_handle=101,
        process_id=202,
        element_id="editor-1",
        editable=True,
        integrity_compatible=True,
        known=True,
    )
    clipboard_value = {"value": ""}
    pasted = []
    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=lambda value: clipboard_value.__setitem__("value", value),
            paste=lambda: clipboard_value["value"],
            sleeper=lambda _delay: None,
            retry_delays=(0.0,),
        ),
        inspect_target=lambda: current,
        dispatch_paste=lambda: pasted.append(True) or True,
        ledger_dir=tmp_path / "delivery",
    )

    result = coordinator.deliver("完整文字", start_target=current, session_id="s1")

    assert result.clipboard_verified is True
    assert result.paste_dispatched is True
    assert result.clipboard_only is False
    assert pasted == [True]
    assert (tmp_path / "delivery" / "s1.json").exists()
    assert coordinator.acknowledge("s1") is True
    assert not (tmp_path / "delivery" / "s1.json").exists()


def test_delivery_uses_clipboard_only_when_focus_changed(tmp_path):
    from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard

    start = TargetSnapshot(101, 202, "editor-1", True, True, True)
    changed = TargetSnapshot(303, 404, "button-2", False, True, True)
    clipboard_value = {"value": ""}
    pasted = []
    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=lambda value: clipboard_value.__setitem__("value", value),
            paste=lambda: clipboard_value["value"],
            sleeper=lambda _delay: None,
            retry_delays=(0.0,),
        ),
        inspect_target=lambda: changed,
        dispatch_paste=lambda: pasted.append(True) or True,
        ledger_dir=tmp_path / "delivery",
    )

    result = coordinator.deliver("保底文字", start_target=start, session_id="s2")

    assert result.clipboard_verified is True
    assert result.paste_dispatched is False
    assert result.clipboard_only is True
    assert result.reason == "target_changed_or_not_editable"
    assert pasted == []


def test_delivery_keeps_pending_ledger_when_clipboard_cannot_be_verified(tmp_path):
    from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard

    start = TargetSnapshot(101, 202, "editor-1", True, True, True)
    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=lambda _value: None,
            paste=lambda: "different",
            sleeper=lambda _delay: None,
            retry_delays=(0.0,),
        ),
        inspect_target=lambda: start,
        dispatch_paste=lambda: True,
        ledger_dir=tmp_path / "delivery",
    )

    result = coordinator.deliver("必须保住", start_target=start, session_id="s3")

    ledger = tmp_path / "delivery" / "s3.json"
    assert result.clipboard_verified is False
    assert result.recovery_saved is True
    assert result.paste_dispatched is False
    assert ledger.is_file()
    assert json.loads(ledger.read_text(encoding="utf-8"))["text"] == "必须保住"


def test_pending_delivery_can_be_recovered_after_process_restart(tmp_path):
    from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard

    value = {"text": ""}
    first = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=lambda _text: None,
            paste=lambda: "mismatch",
            sleeper=lambda _delay: None,
            retry_delays=(0.0,),
        ),
        inspect_target=lambda: TargetSnapshot(None, None, "", False, False, False),
        dispatch_paste=lambda: False,
        ledger_dir=tmp_path / "delivery",
    )
    first.deliver("崩溃后仍可恢复", start_target=None, session_id="restart-1")
    second = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=lambda text: value.__setitem__("text", text),
            paste=lambda: value["text"],
            sleeper=lambda _delay: None,
            retry_delays=(0.0,),
        ),
        inspect_target=lambda: TargetSnapshot(None, None, "", False, False, False),
        dispatch_paste=lambda: False,
        ledger_dir=tmp_path / "delivery",
    )

    recovered = second.recover_pending_to_clipboard()

    assert recovered[0]["session_id"] == "restart-1"
    assert recovered[0]["text"] == "崩溃后仍可恢复"
    assert (tmp_path / "delivery" / "restart-1.json").exists()
    assert second.acknowledge("restart-1") is True


def test_delivery_ledger_rejects_session_path_traversal(tmp_path):
    import pytest
    from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard

    target = TargetSnapshot(None, None, "", False, False, False)
    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(
            copy=lambda _value: None,
            paste=lambda: "",
            sleeper=lambda _delay: None,
            retry_delays=(0.0,),
        ),
        inspect_target=lambda: target,
        dispatch_paste=lambda: False,
        ledger_dir=tmp_path / "delivery",
    )

    with pytest.raises(ValueError, match="session id"):
        coordinator.deliver("text", start_target=None, session_id="../escape")
    assert coordinator.acknowledge("../escape") is False
    assert not (tmp_path / "escape.json").exists()


def test_uia_focus_marks_only_writable_value_pattern_as_editable(monkeypatch):
    import delivery

    class Pattern:
        IsReadOnly = False

    class Control:
        ProcessId = 202
        ControlTypeName = "EditControl"
        AutomationId = "message-box"
        IsEnabled = True
        IsKeyboardFocusable = True

        @staticmethod
        def GetRuntimeId():
            return (42, 7, 9)

        @staticmethod
        def GetPattern(_pattern):
            return Pattern()

    fake = types.SimpleNamespace(
        GetFocusedControl=lambda: Control(),
        PatternId=types.SimpleNamespace(ValuePattern=10002),
    )
    monkeypatch.setitem(sys.modules, "uiautomation", fake)
    monkeypatch.setattr(delivery, "_integrity_compatible", lambda _pid: True)

    target = delivery._inspect_uia_target(
        foreground=101,
        foreground_process_id=202,
    )

    assert target is not None
    assert target.editable is True
    assert target.known is True
    assert target.element_id == "uia:EditControl:message-box:42.7.9"


def test_uia_focus_rejects_read_only_document(monkeypatch):
    import delivery

    class Pattern:
        IsReadOnly = True

    control = types.SimpleNamespace(
        ProcessId=202,
        ControlTypeName="DocumentControl",
        AutomationId="article",
        IsEnabled=True,
        IsKeyboardFocusable=True,
        GetRuntimeId=lambda: (42, 8),
        GetPattern=lambda _pattern: Pattern(),
    )
    fake = types.SimpleNamespace(
        GetFocusedControl=lambda: control,
        PatternId=types.SimpleNamespace(ValuePattern=10002),
    )
    monkeypatch.setitem(sys.modules, "uiautomation", fake)
    monkeypatch.setattr(delivery, "_integrity_compatible", lambda _pid: True)

    target = delivery._inspect_uia_target(
        foreground=101,
        foreground_process_id=202,
    )

    assert target is not None
    assert target.editable is False


def test_safe_text_boundary_removes_protocol_tokens_and_controls_without_rewriting_words():
    from safe_text import SafeTextBoundary

    boundary = SafeTextBoundary()
    raw = "<|zh|><|NEUTRAL|>Hello\x00 \u4e16\u754c\ue000<|Speech|> 😊"

    result = boundary.sanitize(raw)

    assert result.text == "Hello \u4e16\u754c 😊"
    assert result.changed is True
    assert result.rejected is False
    assert "model_control_token" in result.reasons
    assert "unicode_control" in result.reasons
    assert "private_use" in result.reasons


def test_safe_text_boundary_rejects_pathological_repetition():
    from safe_text import SafeTextBoundary

    result = SafeTextBoundary().sanitize("啊" * 80)

    assert result.rejected is True
    assert result.text == ""
    assert "pathological_repetition" in result.reasons


def test_main_connects_recovery_safe_text_and_truthful_delivery_in_order():
    source = (SRC / "main.py").read_text(encoding="utf-8")

    assert "RecoverySessionStore" in source
    assert "self.audio.set_recovery_sink(self._recovery_journal)" in source
    assert "self._safe_text.sanitize(raw_text)" in source
    assert "self._recording_state.mark_delivering()" in source
    assert "self.output_handler.deliver(" in source
    assert "self.overlay.show_authoritative_final(" in source
    assert "self.overlay.show_delivery_state(" in source
    assert source.index("self._safe_text.sanitize(raw_text)") < source.index(
        "self.output_handler.deliver("
    )


def test_audio_callback_only_enqueues_recovery_pcm_instead_of_writing_files():
    source = (SRC / "audio_capture.py").read_text(encoding="utf-8")
    callback_start = source.index("def audio_callback")
    callback_end = source.index("self._stream = sd.InputStream", callback_start)
    callback = source[callback_start:callback_end]

    assert "recovery_sink.append_pcm(block)" in callback
    assert ".open(" not in callback
    assert ".write(" not in callback
