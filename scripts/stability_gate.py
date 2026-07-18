"""Fast deterministic lifecycle regression gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from recording_state import RecordingState, RecordingStateMachine  # noqa: E402


def run_cycles(cycles: int) -> dict:
    state = RecordingStateMachine()
    failures = []
    for index in range(cycles):
        if not state.claim_start():
            failures.append({"cycle": index, "transition": "start"})
            break
        if state.claim_start():
            failures.append({"cycle": index, "transition": "duplicate_start"})
            break
        if not state.claim_stop():
            failures.append({"cycle": index, "transition": "stop"})
            break
        if state.claim_cancel() or state.claim_stop():
            failures.append({"cycle": index, "transition": "processing_reentry"})
            break
        if not state.complete_processing():
            failures.append({"cycle": index, "transition": "complete"})
            break
    passed = (
        not failures
        and state.current is RecordingState.IDLE
        and state.completed_cycles == cycles
    )
    return {
        "passed": passed,
        "requested_cycles": cycles,
        "completed_cycles": state.completed_cycles,
        "final_state": state.current.value,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="VoiceFlow recording lifecycle gate")
    parser.add_argument("--cycles", type=int, default=500)
    args = parser.parse_args()
    result = run_cycles(args.cycles)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
