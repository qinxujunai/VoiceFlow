"""Measure the shipped native capsule; --legacy compares the retired renderer."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWidgets import QApplication


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


def measure_legacy():
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineWidgets import QWebEngineView
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


def main():
    if "--legacy" in sys.argv:
        return measure_legacy()
    sys.path.insert(0, str(ROOT / "src"))
    from capsule_native import NativeCapsuleView, split_graphemes
    from qt_compat import QFontMetricsF, Qt

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    view.resize(380, 48)
    view.show()
    app.processEvents()
    painted = []
    view.preview_painted.connect(lambda generation: painted.append(
        {"session_id": generation, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
    ))
    view.present("prepare_recording", [1])
    started = time.perf_counter()
    view.present("append_streaming", [SAMPLE, 1])
    frames = []
    previous = -1
    while time.perf_counter() - started < 3:
        app.processEvents()
        length = len(view.state.text)
        if length != previous:
            frames.append({"elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                           "length": length, "width": view._target_width, "horizontal_offset": 0})
            previous = length
        if not view.state.pending:
            break
        time.sleep(0.003)
    before = view.state.text
    before_width = view._target_width
    view.present("append_streaming", [FOLLOW_UP, 1])
    _wait(app, lambda: not view.state.pending)
    after = view.state.text
    fill = {}
    for generation, (name, text) in enumerate((("chinese", WIDTH_CHINESE), ("english", WIDTH_ENGLISH)), 2):
        view.present("prepare_recording", [generation])
        view.present("append_streaming", [text, generation])
        _wait(app, lambda: not view.state.pending and not view.frame_timer.isActive())
        metrics = QFontMetricsF(view.font())
        chars = split_graphemes(view.state.text)
        available = view._width - 50
        while chars and metrics.horizontalAdvance("".join(chars)) > available:
            chars.pop(0)
        fill[name] = {"fillRatio": metrics.horizontalAdvance("".join(chars)) / available,
                      "pillWidth": view._width}
    intervals = [b["elapsed_ms"] - a["elapsed_ms"] for a, b in zip(frames, frames[1:])]
    passed = (bool(painted) and painted[0]["session_id"] == 1 and painted[0]["elapsed_ms"] <= 100
              and [f["length"] for f in frames] == list(range(1, len(SAMPLE) + 1))
              and bool(intervals) and max(intervals) <= 110 and frames[-1]["elapsed_ms"] <= 650
              and before == SAMPLE and after == SAMPLE + FOLLOW_UP
              and view.MAX_WIDTH >= before_width
              and all(0.72 <= value["fillRatio"] <= 1.02 for value in fill.values()))
    result = {"renderer": "native-qt", "passed": passed, "frames": frames,
              "first_paint_ack_ms": painted[0]["elapsed_ms"] if painted else None,
              "intervals_ms": intervals, "language_fill": fill,
              "recording_frame_intervals_ms": list(view.frame_intervals_ms),
              "recording_paint_durations_ms": list(view.paint_durations_ms),
              "evidence_scope": "native Qt event-loop and paint measurement; no microphone or ASR"}
    view.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
