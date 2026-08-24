from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from runtime_monitor import UiStallDetector  # noqa: E402


def test_ui_stall_detector_reports_once_until_the_event_loop_ticks_again():
    detector = UiStallDetector(threshold_ms=50, initial_time=10.0)

    assert detector.poll(10.040) is None
    assert detector.poll(10.075) == 75.0
    assert detector.poll(10.100) is None

    detector.tick(10.110)

    assert detector.poll(10.170) == 60.0
