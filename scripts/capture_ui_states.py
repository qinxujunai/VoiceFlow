"""Capture real Qt/WebEngine UI states for visual review and regression baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from overlay_webview import _SettingsWindow  # noqa: E402
from runtime_paths import AppPaths, RuntimeMode  # noqa: E402
from runtime_services import run_runtime_diagnostics  # noqa: E402
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
    "streaming": "prepareRecording(2); appendStreaming('明早十点，把方案同步给团队。', 2); updateAudioLevel([0.032, 0.118, 0.061], 2)",
    "mixed": "prepareRecording(3); updateTranscriptState('明早十点，', '把方案同步给团队。', 3)",
    "settling": "prepareRecording(4); updateTranscriptState('', '明早十点，把方案同步给团队。', 4); showSettling(4)",
    "final_text": "prepareRecording(5); updateTranscriptState('', '明早十点，把方案同步给团队。', 5); showAuthoritativeFinal('明早十点，把方案同步给团队。', 5)",
    "completed": "prepareRecording(6); showAuthoritativeFinal('明早十点，把方案同步给团队。', 6); showDeliveryState('clipboard_verified_paste_dispatched', 6)",
    "clipboard": "prepareRecording(7); showDeliveryState('clipboard_verified_only', 7)",
    "saved": "prepareRecording(8); showDeliveryState('recovery_saved_clipboard_unavailable', 8)",
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


def _capture_settings(
    app: QApplication,
    output_dir: Path,
    paths: AppPaths | None = None,
) -> list[dict]:
    window = _SettingsWindow(paths=paths)
    window.refresh()
    window.show()
    captures = []
    primary_pages = (
        (0, "home"),
        (1, "dictionary"),
        (2, "history"),
        (3, "settings"),
    )
    for row, name in primary_pages:
        window.sidebar.setCurrentRow(row)
        for _ in range(5):
            app.processEvents()
        captures.append(_save_widget(window, output_dir / f"settings-{name}.png"))
    for index, name in ((4, "diagnostics"), (5, "about")):
        window._show_aux_page(index)
        if name == "diagnostics":
            window._finish_doctor(run_runtime_diagnostics(window.paths))
        for _ in range(5):
            app.processEvents()
        captures.append(_save_widget(window, output_dir / f"settings-{name}.png"))
    window.close()
    return captures


def _sanitized_paths(data_dir: Path) -> AppPaths:
    """Use product fixtures so UI evidence never publishes local user history."""
    paths = AppPaths(
        mode=RuntimeMode.FROZEN,
        install_dir=ROOT,
        data_dir=data_dir,
        executable=Path(sys.executable),
    )
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config.yaml", paths.config_file)
    shutil.copytree(
        ROOT / "knowledge-base",
        paths.knowledge_dir,
        dirs_exist_ok=True,
    )
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    entries = (
        {
            "timestamp": "2026-07-28T09:41:00",
            "clean_text": "开口说话，文字就会回到当前光标。",
            "corrected_text": "开口说话，文字就会回到当前光标。",
            "output_status": "clipboard_copied_paste_sent",
            "duration": 4.2,
        },
        {
            "timestamp": "2026-07-28T09:38:00",
            "clean_text": "核心听写离线完成，结果保留在剪贴板和本地历史。",
            "corrected_text": "核心听写离线完成，结果保留在剪贴板和本地历史。",
            "output_status": "clipboard_copied_paste_sent",
            "duration": 8.6,
        },
    )
    paths.history_file.write_text(
        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
        encoding="utf-8",
    )
    return paths


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
    parser.add_argument(
        "--live-data",
        action="store_true",
        help="Capture the current user data. Default output uses sanitized fixtures.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    app = QApplication.instance() or QApplication([])
    if args.live_data:
        captures = _capture_settings(app, output_dir)
        if not args.settings_only:
            captures.extend(_capture_overlay(app, output_dir))
    else:
        with tempfile.TemporaryDirectory(prefix="voiceflow-ui-") as temporary:
            captures = _capture_settings(
                app,
                output_dir,
                _sanitized_paths(Path(temporary) / "VoiceFlow"),
            )
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
