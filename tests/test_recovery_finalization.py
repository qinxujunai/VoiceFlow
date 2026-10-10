"""Recovery uses its recorded format and retains data on persistence failure."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard
from history_store import HistoryStore
from main import VoiceInputSystem
from recovery_session import RecoverySessionStore
from safe_text import SafeTextBoundary


def recovery_fixture(tmp_path, *, sample_rate=16000, partial=False):
    store = RecoverySessionStore(tmp_path / "recovery")
    journal = store.start_session(session_id="fixture", sample_rate=sample_rate,
                                  channels=1, dtype="int16", model="fixture")
    pcm = (np.sin(np.arange(sample_rate // 5) * .2) * 12000).astype(np.int16)
    assert journal.append_pcm(pcm)
    journal.close_interrupted()
    if partial:
        metadata = store.root / "fixture" / "session.json"
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        payload["accepted_sample_count"] = len(pcm) + 100
        payload["writer_error"] = "recovery_queue_full"
        metadata.write_text(json.dumps(payload), encoding="utf-8")
    observed = {"clipboard": "", "rates": [], "acknowledged": []}
    target = TargetSnapshot(101, 202, "fixture", True, True, True)

    def copy(text):
        observed["clipboard"] = text

    def recognize(audio, rate):
        assert np.array_equal(audio, pcm)
        observed["rates"].append(rate)
        return "恢复的完整文字🙂", True

    def forbidden_paste():
        raise AssertionError("recovery must not paste into the current window")

    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(copy=copy, paste=lambda: observed["clipboard"],
                                    retry_delays=(0.0,)),
        inspect_target=lambda: target, dispatch_paste=forbidden_paste,
        ledger_dir=tmp_path / "pending")

    def acknowledge(session_id):
        observed["acknowledged"].append(session_id)
        return coordinator.acknowledge(session_id)

    system = object.__new__(VoiceInputSystem)
    system.audio = SimpleNamespace(sample_rate=16000)
    system._speech_gate_enabled = True
    system._speech_rms_threshold = .002
    system._speech_min_active_ms = 90
    system.transcriber = SimpleNamespace(transcribe_with_activity=recognize)
    system._recovery_store = store
    system._safe_text = SafeTextBoundary()
    system.cleaner = SimpleNamespace(clean=lambda value: value)
    system.punctuation = SimpleNamespace(restore=lambda value: value)
    system.config = {}
    system.history = HistoryStore(tmp_path / "history.jsonl")
    system.output_handler = SimpleNamespace(deliver=coordinator.deliver,
                                           acknowledge_delivery=acknowledge)
    return system, store, observed, pcm


@pytest.mark.parametrize("rate", [8000, 48000])
def test_recovery_uses_the_recorded_rate_instead_of_the_current_device(tmp_path, rate):
    system, store, observed, _pcm = recovery_fixture(tmp_path, sample_rate=rate)
    result = system._recover_idle_session("fixture")
    assert result["ok"]
    assert observed["rates"] == [rate]
    assert observed["clipboard"] == system.history.last()["corrected_text"]
    assert not store.list_recoverable()


def test_recovery_history_failure_is_truthful_and_keeps_pcm_and_pending_final(tmp_path):
    system, store, observed, pcm = recovery_fixture(tmp_path)
    system.history.path.mkdir()
    result = system._recover_idle_session("fixture")
    assert not result["ok"]
    assert "剪贴板" in result["error"]
    assert "历史" in result["error"]
    assert observed["clipboard"] == "恢复的完整文字🙂"
    assert not observed["acknowledged"]
    assert np.array_equal(store.read_pcm("fixture"), pcm)
    assert (tmp_path / "pending" / "recovered-fixture.json").is_file()


def test_partial_recovery_does_not_claim_complete_coverage_or_delete_the_recording(tmp_path):
    system, store, observed, pcm = recovery_fixture(tmp_path, partial=True)
    result = system._recover_idle_session("fixture")
    assert result["ok"]
    assert result["partial"]
    assert result["recording_retained"]
    assert system.history.last()["coverage_ok"] is False
    assert system.history.last()["final_source"] == "recovered_partial_pcm"
    assert np.array_equal(store.read_pcm("fixture"), pcm)
    assert observed["clipboard"] == system.history.last()["corrected_text"]


def test_clipboard_failure_still_saves_recovered_final_to_history(tmp_path):
    system, store, observed, pcm = recovery_fixture(tmp_path)
    coordinator = system.output_handler.deliver.__self__

    def unavailable(_text):
        raise OSError("fixture clipboard occupied")

    coordinator.clipboard = VerifiedClipboard(copy=unavailable, paste=lambda: "",
                                              retry_delays=(0.0,))
    result = system._recover_idle_session("fixture")
    assert not result["ok"]
    assert "历史" in result["error"]
    assert system.history.last()["corrected_text"] == "恢复的完整文字🙂"
    assert not system.history.last()["clipboard_verified"]
    assert system.history.last()["recovery_saved"]
    assert not observed["acknowledged"]
    assert np.array_equal(store.read_pcm("fixture"), pcm)


def test_recovery_reports_a_recording_that_could_not_be_removed(tmp_path, monkeypatch):
    system, store, observed, pcm = recovery_fixture(tmp_path)
    monkeypatch.setattr("recovery_session.shutil.rmtree", lambda *_args, **_kwargs: None)
    result = system._recover_idle_session("fixture")
    assert result["ok"]
    assert result["recording_retained"]
    assert not result["partial"]
    assert np.array_equal(store.read_pcm("fixture"), pcm)
    assert observed["clipboard"] == system.history.last()["corrected_text"]
