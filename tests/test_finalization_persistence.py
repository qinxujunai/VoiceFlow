from __future__ import annotations

import errno
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _finalization_fixture(tmp_path, *, clipboard_fails=False, ledger_fails=False):
    from app_controller import RuntimePhase
    from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard
    from history_store import HistoryStore
    from main import FinalTranscriptionResult, VoiceInputSystem
    from recording_state import RecordingStateMachine
    from recovery_session import RecoverySessionStore
    from safe_text import SafeTextBoundary

    pcm = np.arange(1600, dtype=np.int16)
    text = "保留完整终稿和录音🙂"
    session_id = "finalization-fixture"
    recovery = RecoverySessionStore(tmp_path / "recovery")
    journal = recovery.start_session(
        session_id=session_id, sample_rate=16000, channels=1,
        dtype="int16", model="fixture",
    )
    assert journal.append_pcm(pcm)
    journal.close_interrupted()
    target = TargetSnapshot(101, 202, "fixture-edit", True, True, True)
    observations = {"clipboard": "", "acknowledged": [], "errors": [], "states": []}

    def copy(value):
        if clipboard_fails:
            raise OSError("fixture clipboard unavailable")
        observations["clipboard"] = value

    def forbidden_paste():
        raise AssertionError("finalization persistence fixture must never inject keys")

    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(copy=copy, paste=lambda: observations["clipboard"],
                                    retry_delays=(0.0,)),
        inspect_target=lambda: target,
        dispatch_paste=forbidden_paste,
        ledger_dir=tmp_path / "pending",
    )
    if ledger_fails:
        coordinator.ledger_dir.mkdir()
        (coordinator.ledger_dir / f"{session_id}.json").mkdir()

    def deliver(value, **kwargs):
        # Preserve the production coordinator while selecting its explicit
        # clipboard-only path so this test cannot inject an actual paste.
        kwargs["allow_paste"] = False
        return coordinator.deliver(value, **kwargs)

    def acknowledge(value):
        observations["acknowledged"].append(value)
        return coordinator.acknowledge(value)

    system = object.__new__(VoiceInputSystem)
    system._recording_state = RecordingStateMachine()
    system._runtime_modules_lock = threading.RLock()
    system._runtime_supervisor_stop = threading.Event()
    assert system._recording_state.claim_start()
    assert system._recording_state.mark_recording()
    system.controller = SimpleNamespace(
        phase=RuntimePhase.RECORDING,
        mark_finalizing=lambda: None,
        mark_delivering=lambda: None,
        mark_ready=lambda **_kwargs: None,
        mark_degraded=lambda *_args, **_kwargs: None,
    )
    system.audio = SimpleNamespace(
        sample_rate=16000, recovery_error=None,
        set_recovery_sink=lambda _sink: None, prepare=lambda: None,
    )
    system.session = SimpleNamespace(
        freeze=lambda: len(pcm),
        stop=lambda: SimpleNamespace(audio_data=pcm, total_samples=len(pcm),
                                     start_sample=0, duration=0.1),
    )
    system.output_handler = SimpleNamespace(
        capture_stop_target=lambda: target,
        deliver=deliver,
        acknowledge_delivery=acknowledge,
        cancel_target_tracking=lambda: None,
    )
    system.overlay = SimpleNamespace(
        show_settling=lambda *_args: None,
        show_authoritative_final=lambda *_args: None,
        show_delivery_state=lambda status, *_args: observations["states"].append(status),
        show_error=lambda message: observations["errors"].append(message),
        show_canceled=lambda: observations["states"].append("canceled"),
        hide_after=lambda delay: observations.setdefault("hide_delays", []).append(delay),
        complete_onboarding=lambda: None,
    )
    system.history = HistoryStore(tmp_path / "history.jsonl")
    system._recovery_journal = journal
    system._active_session_id = session_id
    system._target_snapshot = target
    system._latest_text = ""
    system._safe_text = SafeTextBoundary()
    system.cleaner = SimpleNamespace(clean=lambda value: value)
    system.punctuation = SimpleNamespace(restore=lambda value: value)
    system._stop_streaming = lambda: 2
    system._await_final_cache_handoff = lambda: True
    system._transcribe_final_result = lambda *_args, **_kwargs: FinalTranscriptionResult(
        text=text, captured_samples=len(pcm), covered_samples=len(pcm),
        coverage_ok=True, final_source="fixture_full_pcm",
    )
    system._snapshot_final_cache = lambda: ([], 0)
    system._active_engine_name = lambda: "fixture"
    system.preview_transcriber = None
    system.transcriber = SimpleNamespace(worker_pid=None)
    system._worker_pids = lambda: {}
    system._oldest_worker_heartbeat = lambda: 0
    for name in (
        "_last_trigger_to_feedback_ms", "_preview_first_text_ms", "_speech_onset_sample",
        "_preview_first_model_delta_ms", "_preview_first_paint_ms", "_preview_update_gap_ms",
        "_preview_active_speech_update_gap_ms", "_preview_queue_delay_ms",
        "_preview_divergence_count", "_preview_update_count", "_preview_max_chunk_chars",
    ):
        setattr(system, name, None)
    return system, observations, recovery, pcm, text, session_id


def test_empty_stopped_pcm_preserves_actual_recovery_and_explains_next_step(tmp_path):
    system, observed, recovery, pcm, _text, session_id = _finalization_fixture(tmp_path)
    system.session.stop = lambda: SimpleNamespace(
        audio_data=np.empty(0, dtype=np.int16), total_samples=len(pcm),
        start_sample=0, duration=0.1,
    )

    system._on_record_stop()

    retained = recovery.list_recoverable()
    assert [entry.session_id for entry in retained] == [session_id]
    assert (retained[0].session_dir / "audio.pcm").read_bytes() == pcm.tobytes()
    assert "canceled" not in observed["states"]
    assert observed["clipboard"] == ""
    assert observed["errors"] and "设置" in observed["errors"][-1]
    assert system._recording_state.current.value == "idle"


def test_partial_final_is_identified_and_original_pcm_remains_recoverable(tmp_path):
    from main import FinalTranscriptionResult

    system, observed, recovery, pcm, text, session_id = _finalization_fixture(tmp_path)
    system._transcribe_final_result = lambda *_args, **_kwargs: FinalTranscriptionResult(
        text=text, captured_samples=len(pcm), covered_samples=len(pcm) // 2,
        coverage_ok=False, final_source="fixture_partial",
    )

    system._on_record_stop()

    assert observed["clipboard"] == text
    assert [entry.session_id for entry in recovery.list_recoverable()] == [session_id]
    assert observed["errors"] and "部分文字" in observed["errors"][-1]
    assert "设置" in observed["errors"][-1]
    assert system.history.read_recent(1)[0]["coverage_ok"] is False


def test_no_recognized_text_preserves_actual_pcm_and_explains_recovery(tmp_path):
    from main import FinalTranscriptionResult

    system, observed, recovery, pcm, _text, session_id = _finalization_fixture(tmp_path)
    system._transcribe_final_result = lambda *_args, **_kwargs: FinalTranscriptionResult(
        text="", captured_samples=len(pcm), covered_samples=len(pcm),
        coverage_ok=True, final_source="fixture_silence",
    )

    system._on_record_stop()

    assert [entry.session_id for entry in recovery.list_recoverable()] == [session_id]
    assert observed["clipboard"] == ""
    assert observed["errors"] and "没有识别到文字" in observed["errors"][-1]
    assert "设置" in observed["errors"][-1]


def test_quit_during_recording_keeps_real_journal_instead_of_canceling_it(tmp_path):
    system, _observed, recovery, pcm, _text, session_id = _finalization_fixture(tmp_path)
    system._shutdown_started = False
    system._runtime_supervisor_stop = threading.Event()
    journal = system._recovery_journal
    system.session.cancel = journal.close_without_recovery
    system.audio.shutdown = journal.close_interrupted
    system.transcriber.shutdown = lambda: None
    system.output_handler.shutdown = lambda: None

    system.shutdown()

    retained = recovery.list_recoverable()
    assert [entry.session_id for entry in retained] == [session_id]
    assert retained[0].pcm_path.read_bytes() == pcm.tobytes()
    assert system._recording_state.current.value == "shutdown"


def test_finalization_cannot_restart_microphone_or_auto_paste_after_quit(tmp_path):
    system, _observed, _recovery, _pcm, _text, _session_id = _finalization_fixture(tmp_path)
    prepared, paste_permissions = [], []
    transcribe = system._transcribe_final_result
    deliver = system.output_handler.deliver

    def exit_during_transcription(*args, **kwargs):
        system._recording_state.shutdown()
        return transcribe(*args, **kwargs)

    def record_permission(value, **kwargs):
        paste_permissions.append(kwargs["allow_paste"])
        return deliver(value, **kwargs)

    system._transcribe_final_result = exit_during_transcription
    system.output_handler.deliver = record_permission
    system.audio.prepare = lambda: prepared.append(True)

    system._on_record_stop()

    assert paste_permissions == [False]
    assert prepared == []
    assert system._recording_state.current.value == "shutdown"


def test_failed_service_cleanup_does_not_skip_audio_flush_and_can_retry(tmp_path):
    system, _observed, recovery, pcm, _text, session_id = _finalization_fixture(tmp_path)
    system._shutdown_started = False
    system._runtime_supervisor_stop = threading.Event()
    journal = system._recovery_journal
    flushed = []

    def flush_audio():
        journal.close_interrupted()
        flushed.append(True)

    def fail_asr():
        raise OSError("fixture final worker cleanup failure")

    system.audio.shutdown = flush_audio
    system.transcriber.shutdown = fail_asr
    system.output_handler.shutdown = lambda: None

    with pytest.raises(RuntimeError):
        system.shutdown()

    assert flushed == [True]
    retained = recovery.list_recoverable()
    assert [entry.session_id for entry in retained] == [session_id]
    assert retained[0].pcm_path.read_bytes() == pcm.tobytes()
    system.transcriber.shutdown = lambda: None
    system.shutdown()
    assert flushed == [True, True]


@pytest.mark.parametrize("failure", ["directory", "fsync"])
def test_history_failure_is_contained_and_keeps_clipboard_ledger_and_pcm(
    tmp_path, monkeypatch, failure
):
    system, observed, recovery, pcm, text, session_id = _finalization_fixture(tmp_path)
    if failure == "directory":
        system.history.path.mkdir()
    else:
        real_fsync = os.fsync

        def fail_history_sync(descriptor):
            if system.history.path.is_file() and os.path.samestat(
                os.fstat(descriptor), system.history.path.stat()
            ):
                raise OSError(errno.EIO, "fixture history synchronization failed")
            real_fsync(descriptor)

        monkeypatch.setattr(os, "fsync", fail_history_sync)

    escaped = None
    try:
        system._on_record_stop()
    except Exception as error:
        escaped = error

    assert escaped is None, "a second failed history append escaped finalization"
    assert observed["clipboard"] == text
    assert not observed["acknowledged"], "history failure acknowledged pending final text"
    pending = tmp_path / "pending" / f"{session_id}.json"
    assert pending.is_file()
    assert np.array_equal(recovery.read_pcm(session_id), pcm)
    messages = "\n".join(observed["errors"])
    assert "历史" in messages and "未保存" in messages
    assert "已复制" in messages or "剪贴板" in messages
    assert "录音已完整保存" not in messages


def test_successful_history_rescues_text_when_pending_and_clipboard_both_fail(tmp_path):
    system, observed, recovery, pcm, text, session_id = _finalization_fixture(
        tmp_path, clipboard_fails=True, ledger_fails=True
    )

    system._on_record_stop()

    assert observed["clipboard"] == ""
    assert system.history.last()["corrected_text"] == text
    assert system.history.last()["output_status"] == "recovery_saved_clipboard_unavailable"
    assert system.history.last()["recovery_saved"]
    assert np.array_equal(recovery.read_pcm(session_id), pcm)
    assert "delivery_failed" not in observed["states"], (
        "successfully saved history was presented as lost final text"
    )
    assert "recovery_saved_clipboard_unavailable" in observed["states"]


def test_copy_last_can_rescue_in_memory_final_when_history_cannot_be_read(tmp_path):
    from main import VoiceInputSystem

    system = object.__new__(VoiceInputSystem)
    from app_controller import RuntimePhase
    from recording_state import RecordingStateMachine
    system.controller = SimpleNamespace(phase=RuntimePhase.READY)
    system._recording_state = RecordingStateMachine()
    system.history = SimpleNamespace(last=lambda: (_ for _ in ()).throw(OSError("unavailable")))
    copies = []
    system.output_handler = SimpleNamespace(
        last_text="未丢失的终稿🙂",
        copy_only=lambda text: copies.append(text) or "clipboard_verified_only")
    system.overlay = SimpleNamespace(show_result=lambda *_args: None, hide_after=lambda *_args: None)
    system._copy_last_text()
    assert copies == ["未丢失的终稿🙂"]


def test_live_sentence_end_policy_produces_one_final_for_capsule_clipboard_and_history(tmp_path):
    from dictation_preferences import DictationPreferencesStore
    from main import FinalTranscriptionResult

    system, observed, _recovery, pcm, _text, _session = _finalization_fixture(tmp_path)
    system.dictation_preferences = DictationPreferencesStore(tmp_path / "dictation-preferences.json")
    system.dictation_preferences.update(sentence_end="omit_period", preserve_format=False)
    system.dictation_preferences.update(sentence_end="complete_period", preserve_format=False)
    finals = []
    system.overlay.show_authoritative_final = lambda text, *_args: finals.append(text)
    system._transcribe_final_result = lambda *_args, **_kwargs: FinalTranscriptionResult(
        text="会议结束", captured_samples=len(pcm), covered_samples=len(pcm),
        coverage_ok=True, final_source="fixture_full_pcm")
    system._on_record_stop()
    assert finals == ["会议结束。"]
    assert observed["clipboard"] == finals[0]
    assert system.history.last()["corrected_text"] == finals[0]


def test_silent_recording_stops_as_canceled_without_discarding_recovery(tmp_path):
    from main import FinalTranscriptionResult

    system, observed, recovery, pcm, _text, session_id = _finalization_fixture(tmp_path)
    silence = np.zeros_like(pcm)
    system.session.stop = lambda: SimpleNamespace(audio_data=silence, total_samples=len(silence), start_sample=0, duration=0.1)
    system._speech_gate_enabled = True
    system._speech_rms_threshold = 0.002
    system._speech_min_active_ms = 90
    system._transcribe_final_result = lambda *_args, **_kwargs: FinalTranscriptionResult(text="", captured_samples=len(silence), covered_samples=len(silence), coverage_ok=True, final_source="full_pcm")
    system._on_record_stop()
    assert observed["states"] == ["canceled"]
    assert not observed["errors"]
    assert observed["hide_delays"] == [800]
    assert [entry.session_id for entry in recovery.list_recoverable()] == [session_id]
    assert not observed["clipboard"]


def test_empty_audio_failure_dismisses_prompt_and_keeps_recovery(tmp_path):
    system, observed, recovery, pcm, _text, session_id = _finalization_fixture(tmp_path)
    system.session.stop = lambda: SimpleNamespace(audio_data=np.empty(0, dtype=np.int16), total_samples=len(pcm), start_sample=0, duration=0.1)
    system._on_record_stop()
    assert observed["errors"]
    assert observed["hide_delays"]
    assert [entry.session_id for entry in recovery.list_recoverable()] == [session_id]
