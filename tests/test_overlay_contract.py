from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_streaming_update_writes_text_before_measuring_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text")
    text_write_idx = html.index("txt.textContent = text || '';", set_width_idx)
    measure_idx = html.index("var est = measureTextWidth(text);", set_width_idx)

    assert text_write_idx < measure_idx
    assert "setWidthForText(text, true)" in html[html.index("function updateStreaming(text, sessionId)"):]


def test_streaming_pill_width_animates_and_keeps_content_driven_growth():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text")
    set_width_block = html[set_width_idx:html.index("let _tickerTarget", set_width_idx)]
    streaming_block = html[html.index("function updateStreaming(text, sessionId)"):html.index("function showProcessing()")]

    assert "width 180ms cubic-bezier(0.2, 0, 0, 1)" in html
    assert "let maxStreamingWidth = MIN_WIDTH;" in html
    assert "var est = measureTextWidth(text);" in set_width_block
    assert "Math.max(maxStreamingWidth, width)" in set_width_block
    assert "maxStreamingWidth = width;" in set_width_block
    assert "setWidthForText(text, true)" in streaming_block
    assert "ticker.style.textAlign = 'center';" not in streaming_block


def test_streaming_ticker_only_overflows_after_reaching_max_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    ticker_idx = html.index("function updateTickerOffset")
    ticker_block = html[ticker_idx:html.index("function resetTextMotion", ticker_idx)]

    assert "text-align: center;" in html[html.index(".ticker {"):html.index(".ticker.overflowing")]
    assert "const overflow = Math.max(0, txt.scrollWidth - tickerW);" in ticker_block
    assert "_tickerTarget = overflow > 0 ? -overflow : 0;" in ticker_block
    assert "ticker.classList.toggle('overflowing', overflow > 0);" in ticker_block
    assert "ticker.style.textAlign = 'center';" in ticker_block


def test_recording_state_has_explicit_reset_entrypoints():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert "function resetHidden()" in html
    assert "function resetHiddenInstant()" in html
    assert "function prepareRecording(sessionId)" in html
    reset_block = html[html.index("function resetHidden()"):html.index("function prepareRecording(sessionId)")]
    instant_block = html[html.index("function resetHiddenInstant()"):html.index("function prepareRecording(sessionId)")]
    prepare_block = html[html.index("function prepareRecording(sessionId)"):html.index("function showState(state, label)")]
    assert "pill.style.removeProperty('--target-width');" not in reset_block
    assert "var keepNoWidthTransition = pill.classList.contains('no-width-transition');" in reset_block
    assert "var keepNoTransition = pill.classList.contains('no-transition');" in reset_block
    assert "pill.style.setProperty('--target-width', MIN_WIDTH + 'px');" in reset_block
    assert "if (keepNoTransition) classes.push('no-transition');" in reset_block
    assert "if (keepNoWidthTransition) classes.push('no-width-transition');" in reset_block
    assert "pill.className = classes.join(' ');" in reset_block
    assert "pill.classList.add('no-transition');" in instant_block
    assert "void pill.offsetWidth;" in instant_block
    assert "resetHidden();" in prepare_block
    assert "pill.className = 'pill listening no-width-transition';" in html
    assert "pill.classList.add('no-width-transition');" in prepare_block
    assert prepare_block.index("pill.classList.add('no-width-transition');") < prepare_block.index("resetHidden();")
    assert "pill.style.setProperty('--target-width', MIN_WIDTH + 'px');" in prepare_block
    assert "requestAnimationFrame(() => pill.classList.remove('no-width-transition'));" in html
    assert "maxStreamingWidth = MIN_WIDTH;" in html[html.index("function resetTextMotion()"):]
    assert "activeSession = sessionId;" in html


def test_recording_window_shows_after_js_state_preparation():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    start_idx = main.index("def _on_record_start")
    start_block = main[start_idx:main.index("def _on_record_stop", start_idx)]
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "self.overlay.show_window()" not in start_block
    assert "js_then_show_requested.emit(f\"prepareRecording({int(session_id)})\")" in overlay
    assert "runJavaScript(code, lambda _: self.show_requested.emit())" in overlay


def test_recording_start_cancels_pending_hide_timer():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    init_idx = overlay.index("def __init__(self):")
    run_idx = overlay.index("def _run(self):", init_idx)
    init_block = overlay[init_idx:run_idx]
    recording_idx = overlay.index("def show_recording(self, session_id):")
    streaming_idx = overlay.index("def update_streaming", recording_idx)
    recording_block = overlay[recording_idx:streaming_idx]

    assert "self._hide_timer = None" in init_block
    assert "self._cancel_pending_hide()" in recording_block


def test_hide_path_hides_window_before_resetting_dom():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    hide_idx = overlay.index("def _hide_and_idle")
    state_idx = overlay.index("def _set_tray_state", hide_idx)
    hide_block = overlay[hide_idx:state_idx]

    assert "self._bridge.js_then_hide_requested.emit(\"resetHiddenInstant()\")" in hide_block
    assert hide_block.index("resetHiddenInstant()") < hide_block.index("self._hide()")


def test_js_then_hide_allows_reset_to_paint_before_hiding():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    hide_idx = overlay.index("def _run_js_then_hide")
    hide_block = overlay[hide_idx:]

    assert "QTimer.singleShot(50, self.hide_requested.emit)" in hide_block


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
    processing_ticker_block = html[html.index(".processing .ticker"):html.index(".error .ticker")]

    assert ".pill.done" in html
    assert ".processing .mark::before" in html
    assert ".done .mark::before" in html
    assert "@keyframes spin" in html
    assert "function showDone()" in html
    assert "showState('processing'" not in processing_block
    assert "setWidthForText" not in processing_block
    assert "txt.textContent" not in processing_block
    assert "color: transparent;" not in processing_ticker_block
    assert "color: var(--text);" in processing_ticker_block
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
