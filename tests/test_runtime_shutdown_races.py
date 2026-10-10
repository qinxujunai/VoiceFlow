"""Exercise startup and health orchestration against a latched application exit."""

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_controller import RuntimePhase
from main import VoiceInputSystem, _InitWorker
from recording_state import RecordingStateMachine


def fixture():
    system = object.__new__(VoiceInputSystem)
    system._runtime_supervisor_stop = threading.Event()
    system._runtime_modules_lock = threading.RLock()
    system._runtime_supervisor_lock = threading.Lock()
    system._recording_state = RecordingStateMachine()
    system._shutdown_started = False
    system._recovery_journal = None
    system._stop_streaming = lambda: None
    return system


def test_init_worker_does_not_start_or_report_ready_after_exit():
    system = fixture()
    calls = []
    system._init_modules = lambda: calls.append("init")
    system._runtime_supervisor_stop.set()

    _InitWorker(system, lambda: calls.append("ready"), lambda _error: calls.append("error")).run()

    assert calls == []


def test_exit_during_audio_initialization_skips_asr_and_closes_audio(monkeypatch):
    system = fixture()
    entered, release = threading.Event(), threading.Event()
    calls = []
    system.config_path = "unused.yaml"

    class Audio:
        def set_level_callback(self, _callback):
            pass

        def prepare(self):
            entered.set()
            assert release.wait(2)
            calls.append("audio-ready")

        def shutdown(self):
            calls.append("audio-closed")

    monkeypatch.setattr("main.SupervisedAudioCapture", lambda _path: Audio())
    system._on_audio_levels = lambda _levels: None
    system.overlay = SimpleNamespace(show_processing=lambda: calls.append("ASR-started"))
    initialized = _InitWorker(system, lambda: calls.append("ready"), lambda _error: calls.append("error"))
    initialized.start()
    assert entered.wait(1)
    stopper = threading.Thread(target=system.shutdown)
    stopper.start()
    assert system._runtime_supervisor_stop.wait(1)
    release.set()
    initialized.join(3)
    stopper.join(3)

    assert not initialized.is_alive() and not stopper.is_alive()
    assert calls == ["audio-ready", "audio-closed"]


def test_health_tick_cannot_restart_workers_after_exit():
    system = fixture()
    restarted = []
    system.audio = SimpleNamespace(
        is_healthy=False, ensure_healthy=lambda: restarted.append("audio"),
        recovery_error=None,
    )
    system.transcriber = SimpleNamespace(
        is_healthy=False, ensure_healthy=lambda: restarted.append("ASR"),
    )
    system._worker_pids = lambda: {}
    system._oldest_worker_heartbeat = lambda: 0
    system.controller = SimpleNamespace(
        phase=RuntimePhase.READY, update_worker_health=lambda **_kwargs: None,
        mark_ready=lambda **_kwargs: None,
    )
    system._runtime_supervisor_stop.set()

    system._runtime_supervisor_tick()

    assert restarted == []


def test_unreadable_recovery_at_startup_does_not_blame_working_hotkeys(monkeypatch):
    from qt_compat import QTimer

    system = fixture()
    errors = []
    system.overlay = SimpleNamespace(
        show_startup_window=lambda: None, show_error=errors.append,
        show_idle=lambda: None, show_recovery_available=lambda _count: None,
    )
    system.controller = SimpleNamespace(mark_hotkeys=lambda _state: None,
                                        mark_ready=lambda **_kwargs: None)
    system._start_hotkeys = lambda: None
    system._start_runtime_supervisor = lambda: None
    system.preview_transcriber = None
    system.transcriber = SimpleNamespace(worker_pid=42)
    system._worker_pids = lambda: {}
    system._oldest_worker_heartbeat = lambda: 0
    system._recovery_store = SimpleNamespace(
        list_recoverable=lambda: (_ for _ in ()).throw(OSError("fixture recovery directory denied")))
    monkeypatch.setattr(QTimer, "singleShot", lambda _delay, callback: callback())
    monkeypatch.setattr("main._InitWorker", lambda _system, on_done, _on_error:
                        SimpleNamespace(start=on_done))

    system._on_overlay_ready()

    assert len(errors) == 1
    assert "录音" in errors[0] and "读取" in errors[0]
    assert "快捷键" not in errors[0]
