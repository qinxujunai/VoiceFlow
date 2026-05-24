from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_streaming_update_writes_text_before_measuring_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text)")
    text_write_idx = html.index("txt.textContent = text || '';", set_width_idx)
    measure_idx = html.index("var est = measureTextWidth(text);", set_width_idx)

    assert text_write_idx < measure_idx
    assert "setWidthForText(text);" in html[html.index("function updateStreaming(text, sessionId)"):]


def test_recording_state_has_explicit_reset_entrypoints():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert "function resetHidden()" in html
    assert "function prepareRecording(sessionId)" in html
    assert "resetHidden();" in html[html.index("function prepareRecording(sessionId)"):]
    assert "activeSession = sessionId;" in html


def test_recording_window_shows_after_js_state_preparation():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    start_idx = main.index("def _on_record_start")
    start_block = main[start_idx:main.index("def _on_record_stop", start_idx)]
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "self.overlay.show_window()" not in start_block
    assert "js_then_show_requested.emit(f\"prepareRecording({int(session_id)})\")" in overlay
    assert "runJavaScript(code, lambda _: self.show_requested.emit())" in overlay


def test_streaming_updates_are_session_guarded():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "function updateStreaming(text, sessionId)" in html
    assert "if (sessionId !== activeSession) return;" in html
    assert "activeSession += 1;" in html[html.index("function showState(state, label)"):]
    assert "updateStreaming({json.dumps(text, ensure_ascii=False)}, {int(session_id)})" in overlay
