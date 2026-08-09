"""Destructive-to-temporary-data flagship reliability stress gate."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from delivery import DeliveryCoordinator, TargetSnapshot, VerifiedClipboard, inspect_current_target
from recording_state import RecordingState, RecordingStateMachine
from recovery_session import RecoverySessionStore
from safe_text import SafeTextBoundary


def stress_state_machine(cycles: int = 10_000) -> dict:
    rng = random.Random(20260809)
    machine = RecordingStateMachine()
    outcomes = {"complete": 0, "cancel": 0, "recoverable": 0, "error": 0}
    for _ in range(cycles):
        assert machine.current is RecordingState.IDLE
        assert machine.claim_start()
        if rng.random() < 0.04:
            assert machine.claim_cancel()
            outcomes["cancel"] += 1
            continue
        assert machine.mark_recording()
        if rng.random() < 0.03:
            assert machine.mark_error()
            assert machine.mark_recoverable()
            assert machine.acknowledge_recovery()
            outcomes["error"] += 1
            continue
        assert machine.claim_stop()
        if rng.random() < 0.05:
            assert machine.mark_recoverable()
            assert machine.acknowledge_recovery()
            outcomes["recoverable"] += 1
            continue
        assert machine.mark_delivering()
        if rng.random() < 0.05:
            assert machine.mark_recoverable()
            assert machine.acknowledge_recovery()
            outcomes["recoverable"] += 1
            continue
        assert machine.mark_complete()
        assert machine.complete_processing()
        outcomes["complete"] += 1
    assert machine.current is RecordingState.IDLE
    return {"cycles": cycles, "outcomes": outcomes}


def stress_one_hour_recovery() -> dict:
    sample_rate = 16_000
    total_samples = sample_rate * 60 * 60
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="voiceflow-hour-") as temporary:
        store = RecoverySessionStore(Path(temporary) / "recovery", retention_hours=24)
        journal = store.start_session(
            session_id="one-hour",
            sample_rate=sample_rate,
            channels=1,
            dtype="int16",
            model="sensevoice",
        )
        audio = np.zeros(total_samples, dtype=np.int16)
        chunk_samples = sample_rate * 10
        accepted = 0
        for start in range(0, total_samples, chunk_samples):
            accepted += int(journal.append_pcm(audio[start:start + chunk_samples]))
        journal.close_interrupted()
        sessions = store.list_recoverable()
        assert len(sessions) == 1
        assert sessions[0].sample_count == total_samples
        assert sessions[0].pcm_path.stat().st_size == total_samples * 2
        assert accepted == 360
        elapsed = time.perf_counter() - started
        return {
            "samples": total_samples,
            "pcm_bytes": total_samples * 2,
            "chunks": accepted,
            "elapsed_seconds": round(elapsed, 3),
        }


def stress_delivery_faults(cases: int = 5_000) -> dict:
    rng = random.Random(20260809)
    verified = 0
    retained = 0
    with tempfile.TemporaryDirectory(prefix="voiceflow-delivery-") as temporary:
        ledger = Path(temporary) / "pending"
        target = TargetSnapshot(1, 2, "uia:Edit:1", True, True, True)
        for index in range(cases):
            stored = {"text": ""}
            fail_writes = rng.randrange(0, 8)
            calls = {"count": 0}

            def copy(value):
                calls["count"] += 1
                if calls["count"] <= fail_writes:
                    raise RuntimeError("clipboard locked")
                stored["text"] = value

            clipboard = VerifiedClipboard(
                copy=copy,
                paste=lambda: stored["text"],
                sleeper=lambda _delay: None,
            )
            coordinator = DeliveryCoordinator(
                clipboard=clipboard,
                inspect_target=lambda: target,
                dispatch_paste=lambda: True,
                ledger_dir=ledger,
            )
            session_id = f"fault-{index}"
            result = coordinator.deliver(
                f"case-{index}-中英😊",
                start_target=target,
                session_id=session_id,
            )
            if result.clipboard_verified:
                verified += 1
                assert stored["text"] == f"case-{index}-中英😊"
                assert coordinator.acknowledge(session_id)
            else:
                retained += 1
                assert result.paste_dispatched is False
                assert (ledger / f"{session_id}.json").is_file()
        assert verified + retained == cases
    return {"cases": cases, "verified": verified, "recovery_retained": retained}


def stress_safe_text(cases: int = 50_000) -> dict:
    rng = random.Random(20260809)
    boundary = SafeTextBoundary()
    alphabet = list("中文English 123，。😊") + ["\x00", "\x1f", "\ue000"]
    changed = 0
    rejected = 0
    for index in range(cases):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))
        if index % 97 == 0:
            text += "<|Speech|>"
        result = boundary.sanitize(text)
        changed += int(result.changed)
        rejected += int(result.rejected)
        assert "\x00" not in result.text
        assert "\x1f" not in result.text
        assert "\ue000" not in result.text
        assert "<|Speech|>" not in result.text
    return {"cases": cases, "changed": changed, "rejected": rejected}


def measure_focus_inspection(calls: int = 200) -> dict:
    durations = []
    known = 0
    for _ in range(calls):
        started = time.perf_counter()
        target = inspect_current_target()
        durations.append((time.perf_counter() - started) * 1000)
        known += int(target.known)
    durations.sort()
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]
    return {
        "calls": calls,
        "known": known,
        "p95_ms": round(p95, 3),
        "max_ms": round(max(durations), 3),
    }


def main() -> int:
    result = {
        "state_machine": stress_state_machine(),
        "one_hour_recovery": stress_one_hour_recovery(),
        "delivery_faults": stress_delivery_faults(),
        "safe_text_fuzz": stress_safe_text(),
        "focus_inspection": measure_focus_inspection(),
    }
    result["passed"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
