"""Capture real Qt/WebEngine UI states for visual review and regression baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from overlay_webview import _SettingsWindow  # noqa: E402
from qt_compat import (  # noqa: E402
    QApplication,
    QMainWindow,
    QSize,
    QUrl,
    QVBoxLayout,
    QWebEngineView,
    QWidget,
)


OVERLAY_STATES = {
    "recording": "prepareRecording(1); updateAudioLevel([0.018, 0.092, 0.044], 1)",
    "streaming": "prepareRecording(2); updateStreaming('正在整理 VoiceFlow 的完整转写', 2); updateAudioLevel([0.032, 0.118, 0.061], 2)",
    "correction": "prepareRecording(3); updateCorrection('正在整理 VoiceFlow 的完整转写', 3)",
    "finalizing": "prepareRecording(4); showFinalizing(4)",
    "completed": "prepareRecording(5); showFinalText('完整文字已保留', 5)",
    "error": "showState('error', '麦克风不可用')",
    "canceled": "showState('canceled', '已取消')",
}


def _wait(app: QApplication, predicate, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError("UI capture timed out")
        app.processEvents()
        time.sleep(0.01)


def _save_widget(widget, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = widget.grab()
    if not image.save(str(path)):
        raise RuntimeError(f"failed to save screenshot: {path}")
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "width": image.width(),
        "height": image.height(),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _capture_settings(app: QApplication, output_dir: Path) -> list[dict]:
    window = _SettingsWindow()
    window.refresh()
    window.show()
    captures = []
    names = ("history", "dictation", "hotkeys", "diagnostics")
    for index, name in enumerate(names):
        window.sidebar.setCurrentRow(index)
        for _ in range(5):
            app.processEvents()
        captures.append(_save_widget(window, output_dir / f"settings-{name}.png"))
    window.close()
    return captures


def _capture_overlay(app: QApplication, output_dir: Path) -> list[dict]:
    window = QMainWindow()
    window.setFixedSize(QSize(380, 48))
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    view = QWebEngineView()
    view.setStyleSheet("background: transparent;")
    layout.addWidget(view)
    window.setCentralWidget(central)
    loaded = []
    view.loadFinished.connect(lambda ok: loaded.append(bool(ok)))
    view.setUrl(QUrl.fromLocalFile(str(ROOT / "src" / "overlay.html")))
    window.show()
    _wait(app, lambda: bool(loaded))
    if not loaded[-1]:
        raise RuntimeError("overlay.html failed to load")

    captures = []
    for name, command in OVERLAY_STATES.items():
        completed = []
        view.page().runJavaScript(command, lambda _result: completed.append(True))
        _wait(app, lambda: bool(completed))
        for _ in range(25):
            app.processEvents()
            time.sleep(0.01)
        captures.append(_save_widget(window, output_dir / f"overlay-{name}.png"))
    window.close()
    return captures


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture VoiceFlow UI states")
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "ui-review"))
    parser.add_argument("--settings-only", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    app = QApplication.instance() or QApplication([])
    captures = _capture_settings(app, output_dir)
    if not args.settings_only:
        captures.extend(_capture_overlay(app, output_dir))
    manifest = {"schema_version": 1, "captures": captures}
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(manifest_path.resolve())
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
