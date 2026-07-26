"""Record real Qt paint latency for the recording pill."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import overlay_webview  # noqa: E402
from overlay_webview import OverlayWindow  # noqa: E402
from qt_compat import QTimer  # noqa: E402
from runtime_paths import AppPaths  # noqa: E402


def _replace_feedback_rows(path: Path, measurements: list[float]) -> None:
    rows = []
    if path.exists():
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    rows = [row for row in rows if row.get("source") != "real_qt_paint"]
    measured_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    rows.extend(
        {
            "source": "real_qt_paint",
            "measured_at": measured_at,
            "trigger_to_feedback_ms": round(value, 3),
        }
        for value in measurements
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument(
        "--output",
        default=str(ROOT / "logs" / "performance-evidence.jsonl"),
    )
    args = parser.parse_args()
    if args.samples < 1:
        raise SystemExit("--samples must be positive")

    overlay_webview.SINGLE_INSTANCE_NAME = (
        f"VoiceFlow.Performance.{os.getpid()}"
    )
    paths = AppPaths.discover(config_path=ROOT / "config.yaml")
    overlay = OverlayWindow(paths)
    measurements = []
    next_session = 1
    finished = False

    def finish():
        nonlocal finished
        if finished:
            return
        finished = True
        _replace_feedback_rows(Path(args.output), measurements)
        print(
            json.dumps(
                {
                    "samples": len(measurements),
                    "measurements_ms": measurements,
                    "output": str(Path(args.output)),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        overlay.quit()

    def trigger():
        nonlocal next_session
        if len(measurements) >= args.samples:
            finish()
            return
        session_id = next_session
        next_session += 1
        overlay.show_recording(session_id, time.perf_counter())

    def painted(_session_id, elapsed_ms):
        measurements.append(round(float(elapsed_ms), 3))
        overlay._hide()
        QTimer.singleShot(80, trigger)

    def ready():
        overlay.set_actions(on_recording_painted=painted)
        overlay.web_view.loadFinished.connect(
            lambda ok: QTimer.singleShot(120, trigger) if ok else finish()
        )
        QTimer.singleShot(1500, trigger)

    overlay.start(on_ready=ready)
    return 0 if len(measurements) == args.samples else 1


if __name__ == "__main__":
    raise SystemExit(main())
