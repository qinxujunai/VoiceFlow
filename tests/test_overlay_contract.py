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


def test_hide_path_hides_window_before_resetting_dom():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    hide_idx = overlay.index("def _hide_and_idle")
    state_idx = overlay.index("def _set_tray_state", hide_idx)
    hide_block = overlay[hide_idx:state_idx]

    assert "js_then_hide_requested.emit" not in hide_block
    assert "self._hide()" in hide_block
    assert "self._bridge.js_requested.emit(\"resetHidden()\")" in hide_block
    assert hide_block.index("self._hide()") < hide_block.index("resetHidden()")


def test_streaming_updates_are_session_guarded():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "function updateStreaming(text, sessionId)" in html
    assert "if (sessionId !== activeSession) return;" in html
    assert "activeSession += 1;" in html[html.index("function showState(state, label)"):]
    assert "updateStreaming({json.dumps(text, ensure_ascii=False)}, {int(session_id)})" in overlay


def test_stop_flow_uses_processing_and_done_states():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_idx = main.index("def _on_record_stop")
    stream_idx = main.index("def _start_streaming", stop_idx)
    stop_block = main[stop_idx:stream_idx]

    assert "self.overlay.show_processing()" in stop_block
    assert stop_block.index("self.overlay.show_processing()") < stop_block.index("self._stop_streaming()")
    assert "self.overlay.show_done()" in stop_block
    assert "self.overlay.show_result(text)" not in stop_block


def test_overlay_has_processing_spinner_and_done_checkmark():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    processing_idx = html.index("function showProcessing()")
    done_idx = html.index("function showDone()", processing_idx)
    processing_block = html[processing_idx:done_idx]

    assert ".pill.done" in html
    assert ".processing .mark::before" in html
    assert ".done .mark::before" in html
    assert "@keyframes spin" in html
    assert "function showDone()" in html
    assert "showState('processing'" not in processing_block
    assert "setWidthForText" not in processing_block
    assert "txt.textContent" not in processing_block
    assert "pill.className = 'pill processing';" in processing_block
    assert "showState('done', '已完成')" in html
    assert "ticker.style.textAlign = 'center';" in html[html.index("function showState(state, label)"):html.index("function showRecording(sessionId)")]
    assert "position: absolute;" in html[html.index(".processing .mark::before"):html.index(".done .mark::before")]
    assert "inset: 2.5px;" in html[html.index(".processing .mark::before"):html.index(".done .mark::before")]
    assert "border-right: 1.8px solid var(--green);" in html
    assert "border-bottom: 1.8px solid var(--green);" in html
    assert "def show_done(self):" in overlay
    assert 'self._js("showProcessing()")' in overlay
    assert "showDone()" in overlay
