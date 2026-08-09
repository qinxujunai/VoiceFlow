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
FOLLOW_UP = " English stays readable"
WIDTH_CHINESE = "这是中文预览宽度应该自然舒展并保持稳定清晰"
WIDTH_ENGLISH = "this is an english preview that should remain comfortably readable"


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


def _capsule_metrics(app, page):
    return json.loads(_javascript(
        app,
        page,
        """
        (() => {
            const range = document.createRange();
            range.selectNodeContents(txt);
            const textWidth = range.getBoundingClientRect().width;
            const tickerWidth = ticker.getBoundingClientRect().width;
            return JSON.stringify({
                text: txt.textContent,
                textWidth,
                tickerWidth,
                fillRatio: tickerWidth ? textWidth / tickerWidth : 0,
                pillWidth: pill.getBoundingClientRect().width
            });
        })()
        """,
    ))


def _measure_language_fill(app, page, text, session_id):
    _javascript(app, page, f"prepareRecording({session_id})")
    _javascript(
        app,
        page,
        "appendStreaming("
        f"{json.dumps(text, ensure_ascii=False)}, {session_id})",
    )
    _wait(
        app,
        lambda: json.loads(
            _javascript(
                app,
                page,
                "JSON.stringify(getStreamingDebugState())",
            )
        )["queueLength"] == 0,
    )
    _wait(
        app,
        lambda: abs(float(_javascript(
            app,
            page,
            "pill.getBoundingClientRect().width",
        )) - float(json.loads(_javascript(
            app,
            page,
            "JSON.stringify(getStreamingDebugState())",
        ))["targetWidth"])) < 1.0,
    )
    return _capsule_metrics(app, page)


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
        "appendStreaming("
        f"{json.dumps(SAMPLE, ensure_ascii=False)}, 1)",
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

    before_follow_up = json.loads(
        _javascript(
            app,
            view.page(),
            "JSON.stringify(getStreamingDebugState())",
        )
    )
    _javascript(
        app,
        view.page(),
        "appendStreaming("
        f"{json.dumps(FOLLOW_UP, ensure_ascii=False)}, 1)",
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
    after_follow_up = json.loads(
        _javascript(
            app,
            view.page(),
            "JSON.stringify(getStreamingDebugState())",
        )
    )
    chinese_metrics = _measure_language_fill(app, view.page(), WIDTH_CHINESE, 2)
    english_metrics = _measure_language_fill(app, view.page(), WIDTH_ENGLISH, 3)
    view.close()
    lengths = [frame["length"] for frame in frames]
    intervals = [
        frames[index]["elapsed_ms"] - frames[index - 1]["elapsed_ms"]
        for index in range(1, len(frames))
    ]
    widths = [frame["width"] for frame in frames]
    result = {
        "intervals_ms": intervals,
        "passed": (
            bool(frames)
            and bool(painted)
            and painted[0]["session_id"] == 1
            and frames[0]["elapsed_ms"] <= 100
            and painted[0]["elapsed_ms"] <= 300
            and lengths == list(range(1, len(SAMPLE) + 1))
            and bool(intervals)
            and 16 <= sorted(intervals)[len(intervals) // 2] <= 55
            and max(intervals) <= 110
            and frames[-1]["elapsed_ms"] <= 600
            and widths == sorted(widths)
            and all(frame["horizontal_offset"] == 0 for frame in frames)
            and before_follow_up["visibleText"] == SAMPLE
            and before_follow_up["confirmedText"] == SAMPLE
            and after_follow_up["confirmedText"] == SAMPLE + FOLLOW_UP
            and after_follow_up["visibleText"] == SAMPLE + FOLLOW_UP
            and after_follow_up["targetWidth"] >= before_follow_up["targetWidth"]
            and after_follow_up["horizontalOffset"] == 0
            and 0.72 <= chinese_metrics["fillRatio"] <= 1.02
            and 0.72 <= english_metrics["fillRatio"] <= 1.02
            and abs(
                chinese_metrics["pillWidth"] - english_metrics["pillWidth"]
            ) < 1.0
        ),
        "characters": len(SAMPLE),
        "first_character_ms": frames[0]["elapsed_ms"] if frames else None,
        "first_paint_ack_ms": painted[0]["elapsed_ms"] if painted else None,
        "median_interval_ms": (
            sorted(intervals)[len(intervals) // 2] if intervals else None
        ),
        "frames": frames,
        "language_fill": {
            "chinese": chinese_metrics,
            "english": english_metrics,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
