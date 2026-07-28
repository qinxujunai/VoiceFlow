"""Measure the real WebEngine capsule append cadence without recording audio."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "这是一次平稳的逐字显示测试"


class _PaintReporter(QObject):
    painted = Signal(int)

    @Slot(int)
    def previewPainted(self, session_id):
        self.painted.emit(int(session_id))


def _wait(app, predicate, timeout=5.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise TimeoutError("WebEngine motion measurement timed out")


def _javascript(app, page, script):
    result = []
    page.runJavaScript(script, lambda value: result.append(value))
    _wait(app, lambda: bool(result))
    return result[0]


def main():
    app = QApplication.instance() or QApplication([])
    view = QWebEngineView()
    reporter = _PaintReporter()
    painted = []
    reporter.painted.connect(
        lambda session_id: painted.append(
            {
                "session_id": session_id,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
    )
    channel = QWebChannel(view.page())
    channel.registerObject("voiceflowBridge", reporter)
    view.page().setWebChannel(channel)
    loaded = []
    view.loadFinished.connect(lambda ok: loaded.append(bool(ok)))
    view.setUrl(QUrl.fromLocalFile(str(ROOT / "src" / "overlay.html")))
    view.show()
    _wait(app, lambda: bool(loaded))
    if not loaded[-1]:
        raise RuntimeError("overlay.html failed to load")

    _javascript(app, view.page(), "prepareRecording(1)")
    started = time.perf_counter()
    _javascript(
        app,
        view.page(),
        "updateStreaming("
        f"'', {json.dumps(SAMPLE, ensure_ascii=False)}, 1)",
    )
    frames = []
    previous_length = -1

    while time.perf_counter() - started < 5.0:
        state = json.loads(
            _javascript(
                app,
                view.page(),
                "JSON.stringify(getStreamingDebugState())",
            )
        )
        current_length = len(state["visibleText"])
        if current_length != previous_length:
            frames.append({
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "length": current_length,
                "width": state["targetWidth"],
                "horizontal_offset": state["horizontalOffset"],
            })
            previous_length = current_length
        if current_length == len(SAMPLE) and state["queueLength"] == 0:
            break
        time.sleep(0.01)

    _javascript(
        app,
        view.page(),
        "updateStreaming("
        f"{json.dumps(SAMPLE, ensure_ascii=False)}, '', 1)",
    )
    promoted = json.loads(
        _javascript(
            app,
            view.page(),
            "JSON.stringify(getStreamingDebugState())",
        )
    )
    _javascript(app, view.page(), "prepareRecording(2)")
    _javascript(
        app,
        view.page(),
        "updateStreaming('稳定', '临时错误', 2)",
    )
    _wait(
        app,
        lambda: json.loads(
            _javascript(
                app,
                view.page(),
                "JSON.stringify(getStreamingDebugState())",
            )
        )["queueLength"] == 0,
    )
    before_correction = json.loads(
        _javascript(
            app,
            view.page(),
            "JSON.stringify(getStreamingDebugState())",
        )
    )
    _javascript(
        app,
        view.page(),
        "updateStreaming('稳定', '修正尾巴', 2)",
    )
    _wait(
        app,
        lambda: json.loads(
            _javascript(
                app,
                view.page(),
                "JSON.stringify(getStreamingDebugState())",
            )
        )["queueLength"] == 0,
    )
    after_correction = json.loads(
        _javascript(
            app,
            view.page(),
            "JSON.stringify(getStreamingDebugState())",
        )
    )
    view.close()
    lengths = [frame["length"] for frame in frames]
    intervals = [
        frames[index]["elapsed_ms"] - frames[index - 1]["elapsed_ms"]
        for index in range(1, len(frames))
    ]
    widths = [frame["width"] for frame in frames]
    result = {
        "passed": (
            bool(frames)
            and bool(painted)
            and painted[0]["session_id"] == 1
            and frames[0]["elapsed_ms"] <= 100
            and lengths == list(range(1, len(SAMPLE) + 1))
            and all(55 <= interval <= 130 for interval in intervals)
            and widths == sorted(widths)
            and all(frame["horizontal_offset"] == 0 for frame in frames)
            and promoted["visibleText"] == SAMPLE
            and promoted["confirmedText"] == SAMPLE
            and promoted["provisionalText"] == ""
            and before_correction["visibleText"] == "稳定临时错误"
            and after_correction["visibleText"] == "稳定修正尾巴"
            and after_correction["confirmedText"] == "稳定"
            and after_correction["targetWidth"] >= before_correction["targetWidth"]
            and after_correction["horizontalOffset"] == 0
        ),
        "characters": len(SAMPLE),
        "first_character_ms": frames[0]["elapsed_ms"] if frames else None,
        "first_paint_ack_ms": painted[0]["elapsed_ms"] if painted else None,
        "median_interval_ms": (
            sorted(intervals)[len(intervals) // 2] if intervals else None
        ),
        "frames": frames,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
