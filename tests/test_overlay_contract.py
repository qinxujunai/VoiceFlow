from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_streaming_update_writes_text_before_measuring_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text")
    text_write_idx = html.index("txt.textContent = displayText;", set_width_idx)
    measure_idx = html.index("var est = measureTextWidth(displayText);", set_width_idx)

    assert text_write_idx < measure_idx
    assert "setWidthForText(text, true)" in html[html.index("function updateStreaming(text, sessionId)"):]


def test_streaming_pill_width_animates_and_keeps_content_driven_growth():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text")
    set_width_block = html[set_width_idx:html.index("let _tickerRaf", set_width_idx)]
    streaming_block = html[html.index("function updateStreaming(text, sessionId)"):html.index("function showProcessing()")]

    assert "width 180ms cubic-bezier(0.2, 0, 0, 1)" in html
    assert "let maxStreamingWidth = MIN_WIDTH;" in html
    assert "var est = measureTextWidth(displayText);" in set_width_block
    assert "Math.max(maxStreamingWidth, width)" in set_width_block
    assert "maxStreamingWidth = width;" in set_width_block
    assert "setWidthForText(text, true)" in streaming_block
    assert "ticker.style.textAlign = 'center';" not in streaming_block


def test_streaming_pill_keeps_system_overlay_width_not_banner_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    set_width_idx = html.index("function setWidthForText(text")
    set_width_block = html[set_width_idx:html.index("let _tickerRaf", set_width_idx)]

    assert "max-width: 312px;" in html
    assert "const MAX_WIDTH = 312;" in html
    assert "clamp(50 + est + 36, MIN_WIDTH, MAX_WIDTH)" in set_width_block


def test_streaming_pill_caps_rendered_text_for_long_dictation_performance():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    display_idx = html.index("function displayTextForPill(text)")
    set_width_idx = html.index("function setWidthForText(text")
    display_block = html[display_idx:set_width_idx]
    set_width_block = html[set_width_idx:html.index("let _tickerTarget", set_width_idx)]

    assert "const MAX_DISPLAY_CHARS = 72;" in html
    assert "DISPLAY_HEAD_CHARS" not in html
    assert "const DISPLAY_TAIL_CHARS = 72;" in html
    assert "'… ' + text.slice(-DISPLAY_TAIL_CHARS)" in display_block
    assert "var displayText = displayTextForPill(text);" in set_width_block
    assert "txt.textContent = displayText;" in set_width_block
    assert "measureTextWidth(displayText)" in set_width_block


def test_streaming_ticker_only_overflows_after_reaching_max_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    ticker_idx = html.index("function updateTickerOffset")
    ticker_block = html[ticker_idx:html.index("function resetTextMotion", ticker_idx)]

    assert "text-align: center;" in html[html.index(".ticker {"):html.index(".ticker.overflowing")]
    assert "const overflow = Math.max(0, txt.scrollWidth - tickerW);" in ticker_block
    assert "ticker.classList.toggle('overflowing', overflow > 0);" in ticker_block
    assert "ticker.style.textAlign = 'center';" in ticker_block
    assert "var nextTarget = overflow > 0 ? -overflow : 0;" in ticker_block


def test_streaming_ticker_jumps_to_latest_tail_without_visual_backlog():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    ticker_idx = html.index("function updateTickerOffset")
    ticker_block = html[ticker_idx:html.index("function resetTextMotion", ticker_idx)]
    smooth_block = html[html.index("function smoothTicker()"):ticker_idx]

    assert "marquee" not in html
    assert "text-replace" not in html
    assert "tickerTrack" not in html
    assert "_tickerCurrent += (_tickerTarget - _tickerCurrent) * 0.32;" in smooth_block
    assert "mode === 'live'" in ticker_block
    assert "setTickerOffset(nextTarget);" in ticker_block


def test_streaming_ticker_keeps_motion_when_text_changes_at_same_width():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    ticker_idx = html.index("function updateTickerOffset")
    ticker_block = html[ticker_idx:html.index("function resetTextMotion", ticker_idx)]
    streaming_block = html[html.index("function updateStreaming(text, sessionId)"):html.index("function showProcessing()")]

    assert "STREAMING_MOTION_NUDGE" not in html
    assert "function updateTickerOffset(targetWidth, mode)" in html
    assert "restartTextRefresh" not in html
    assert "updateTickerOffset(width, 'live');" in streaming_block
    assert "if (nextTarget > _tickerCurrent)" in ticker_block


def test_preview_mailbox_keeps_only_the_latest_pending_ui_value():
    from overlay_webview import _LatestPreviewMailbox

    mailbox = _LatestPreviewMailbox()
    mailbox.put("old")
    mailbox.put("new")

    assert mailbox.take() == "new"
    assert mailbox.take() is None


def test_streaming_bridge_uses_coalesced_preview_channel():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "preview_js_requested = Signal(str)" in overlay
    assert "self._bridge.preview_js_requested.emit" in overlay
    assert "def _queue_preview_js" in overlay
    assert "QTimer.singleShot(16, self._flush_preview_js)" in overlay


def test_pause_correction_is_distinct_and_non_flashing():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    correction_block = html[html.index("function updateCorrection(text, sessionId)"):html.index("function showProcessing()")]
    stream_idx = main.index("def _start_streaming")
    stop_idx = main.index("def _stop_streaming", stream_idx)
    stream_block = main[stream_idx:stop_idx]

    assert ".pill.streaming.corrected" in html
    assert "text-replace" not in html
    assert "pill.className = 'pill streaming corrected';" in correction_block
    assert "updateTickerOffset(width, 'settled');" in correction_block
    assert "correctionTimer = setTimeout" in correction_block
    assert "def update_correction(self, text, session_id):" in overlay
    assert "updateCorrection({json.dumps(text, ensure_ascii=False)}, {int(session_id)})" in overlay
    assert "self.overlay.update_correction(clean, generation)" in stream_block


def test_finalizing_and_final_text_are_session_guarded():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "function showFinalizing(sessionId)" in html
    assert "activeSession = sessionId;" in html[html.index("function showFinalizing(sessionId)"):html.index("function showDone()")]
    assert "pill.className = 'pill finalizing';" in html
    assert "function showFinalText(text, sessionId)" in html
    final_text_block = html[html.index("function showFinalText(text, sessionId)"):html.index("function showResult(msg)")]
    assert "if (sessionId < activeSession) return;" in final_text_block
    assert "pill.className = 'pill final_ready success';" in final_text_block
    assert "resetTextMotion();" in final_text_block
    assert "updateTickerOffset(width, 'final')" in final_text_block
    assert "def show_finalizing(self, session_id):" in overlay
    assert "showFinalizing({int(session_id)})" in overlay
    assert "def show_final_text(self, text, session_id):" in overlay
    assert "showFinalText({json.dumps(text, ensure_ascii=False)}, {int(session_id)})" in overlay


def test_overlay_exposes_status_to_assistive_technology_and_reduces_motion():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "animation-duration: 1ms !important;" in html


def test_settings_have_keyboard_and_narrator_names_for_primary_controls():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert 'for label in ("历史", "听写", "快捷键", "诊断")' in overlay
    assert 'self.sidebar.setAccessibleName("设置导航")' in overlay
    assert 'self.search_box.setAccessibleName("搜索历史转录")' in overlay
    assert 'self.model_combo.setAccessibleName("识别模型")' in overlay
    assert 'self.language_combo.setAccessibleName("识别语言")' in overlay
    assert 'self.microphone_combo.setAccessibleName("麦克风")' in overlay
    assert 'self.doctor_text.setAccessibleName("诊断结果")' in overlay


def test_history_does_not_expose_internal_output_status_codes():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert '"clipboard_copied_paste_sent": "已复制并发送粘贴"' in overlay
    assert 'status = self._output_status_label' in overlay


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


def test_app_launch_opens_settings_before_background_model_load():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    ready_idx = main.index("def _on_overlay_ready")
    start_hotkeys_idx = main.index("def _start_hotkeys", ready_idx)
    ready_block = main[ready_idx:start_hotkeys_idx]
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "self.overlay.show_settings_window()" in ready_block
    assert "def _on_overlay_ready(self):\n        from qt_compat import QTimer\n\n        self.overlay.show_settings_window()" in ready_block
    assert "def show_settings_window(self):" in overlay
    assert "settings_requested = Signal()" in overlay
    assert "self._bridge.settings_requested.connect(self._show_settings)" in overlay


def test_settings_window_has_recent_history_copy_controls():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "self.history_list = QListWidget()" in settings_block
    assert "setItemWidget(item, self._history_card" in settings_block
    assert "self.search_box.setPlaceholderText(\"搜索最近转录\")" in settings_block
    assert "QPushButton(\"复制\")" in settings_block
    assert "QPushButton(\"重新粘贴\")" in settings_block
    assert "QPushButton(\"复制全部\")" in settings_block
    assert "copy.clicked.connect(lambda _=False, value=text: self._copy_text(value))" in settings_block
    assert "meta_parts.append(f\"尾部 {tail}\")" in settings_block
    assert "pyperclip.copy(text)" in settings_block
    assert "pyperclip.copy(\"\\n\\n\".join(texts))" in settings_block
    assert "self._on_repaste_text(text)" in settings_block
    assert "self.status_badge.setText(\"无可复制\")" in settings_block


def test_settings_window_uses_app_shell_sidebar_not_default_tabs():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "QStackedWidget" in overlay
    assert "self.sidebar = QListWidget()" in settings_block
    assert "self.stack = QStackedWidget()" in settings_block
    assert "self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)" in settings_block
    assert "QTabWidget" not in overlay
    assert "QLabel#sectionTitle" in settings_block


def test_settings_status_page_exposes_language_and_model_setup_action():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "self.language_combo = QComboBox()" in settings_block
    assert '("语言", self.language_combo)' in settings_block
    assert "self.model_combo = QComboBox()" in settings_block
    assert "def _save_settings(self):" in settings_block
    assert "QPushButton(\"管理模型\")" in settings_block
    assert "download.clicked.connect(self._open_model_setup)" in settings_block
    assert "def _open_model_setup(self):" in settings_block
    assert "scripts\\\\download_models.py" in settings_block


def test_tray_primary_click_opens_settings_not_raw_overlay():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    activated_idx = overlay.index("def _on_tray_activated")
    show_idx = overlay.index("def _show", activated_idx)
    activated_block = overlay[activated_idx:show_idx]

    assert "self._show_settings()" in activated_block
    assert "self._hide()" not in activated_block


def test_overlay_enforces_single_instance_and_focuses_existing_window():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "SINGLE_INSTANCE_NAME" in overlay
    assert "QLocalServer" in overlay
    assert "QLocalSocket" in overlay
    assert "if self._notify_existing_instance():" in overlay
    assert "socket.write(b\"show\\n\")" in overlay
    assert "server.newConnection.connect(self._on_instance_message)" in overlay
    assert "self._show_settings()" in overlay[overlay.index("def _handle_instance_message"):overlay.index("def _setup_tray")]


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


def test_stop_flow_outputs_before_final_text_feedback():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_idx = main.index("def _on_record_stop")
    stream_idx = main.index("def _start_streaming", stop_idx)
    stop_block = main[stop_idx:stream_idx]

    assert "final_generation = self._stop_streaming()" in stop_block
    assert "self.overlay.show_finalizing(final_generation)" in stop_block
    assert "self.overlay.show_final_text(text, final_generation)" in stop_block
    assert stop_block.index("output_status = self.output_handler.output(text)") < stop_block.index("self.overlay.show_final_text(text, final_generation)")
    assert "self.overlay.show_done()" not in stop_block
    assert "self.overlay.show_result(text)" not in stop_block


def test_overlay_has_processing_finalizing_spinner_and_final_checkmark():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    processing_idx = html.index("function showProcessing()")
    done_idx = html.index("function showFinalizing(sessionId)", processing_idx)
    processing_block = html[processing_idx:done_idx]
    processing_ticker_block = html[html.index(".processing .ticker"):html.index(".error .ticker")]

    assert ".pill.done" in html
    assert ".pill.finalizing" in html
    assert ".pill.final_ready" in html
    assert ".processing .mark::before" in html
    assert ".finalizing .mark::before" in html
    assert ".done .mark::before" in html
    assert ".final_ready .mark::before" in html
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


def test_overlay_processing_only_changes_mark_state():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    processing_css = html[html.index(".pill.processing"):html.index(".pill.done")]
    processing_idx = html.index("function showProcessing()")
    processing_block = html[processing_idx:html.index("function showFinalizing(sessionId)", processing_idx)]

    assert "--target-width" not in processing_css
    assert "pill.className = 'pill processing';" in processing_block
    assert "txt.textContent" not in processing_block
    assert "setWidthForText" not in processing_block
    assert "pill.style.setProperty('--target-width'" not in processing_block


def test_overlay_keeps_single_stable_mark_and_text_regions():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    pill_css = html[html.index(".pill {"):html.index(".pill.no-width-transition")]
    mark_css = html[html.index(".mark {"):html.index(".mark span")]
    body = html[html.index('<div id="pill"'):html.index("<script>")]

    assert "grid-template-columns: 18px minmax(0, 1fr);" in pill_css
    assert "width: 18px;" in mark_css
    assert body.count('class="mark"') == 1
    assert body.count('id="ticker"') == 1
    assert body.count('id="txt"') == 1


def test_readme_demo_uses_single_product_pill_state_machine():
    svg = (ROOT / "docs" / "voiceflow-demo.svg").read_text(encoding="utf-8")

    assert svg.count('id="demo-pill"') == 1
    assert svg.count('id="capsule"') == 1
    assert 'id="wave"' in svg
    assert 'id="check"' in svg
    assert 'id="liveText"' in svg
    assert 'id="finalText"' in svg
    assert "@keyframes waveState" in svg
    assert "@keyframes checkState" in svg
    assert "@keyframes liveTextState" in svg
    assert "@keyframes finalTextState" in svg
    assert 'id="demo-spinner"' not in svg
    assert "@keyframes spinnerState" not in svg
    assert "Cursor and Codex at the cursor" not in svg


def test_readme_demo_copies_real_overlay_geometry_and_expands_capsule():
    svg = (ROOT / "docs" / "voiceflow-demo.svg").read_text(encoding="utf-8")

    assert 'height="34"' in svg
    assert 'rx="17"' in svg
    assert 'width="86" height="34" rx="17"' in svg
    assert 'values="1;1;0;0;1"' in svg
    assert 'keyTimes="0;0.88;0.92;0.99;1"' in svg
    assert 'values="86;86;170;236;236;86;86"' in svg
    assert 'values="557 190;557 190;515 190;482 190;482 190;557 190;557 190"' in svg
    assert "明早十点，把方案同步给团队。" in svg
    assert "把声音收束成文字，把文字送回光标。" in svg
    assert "overflow=\"hidden\"" not in svg
    assert 'width="2"' in svg
    assert 'height="7"' in svg
    assert 'height="12"' in svg
    assert 'height="8"' in svg
    assert 'transform="translate(12 8)"' in svg
    assert 'M4.5 9.2 L7.5 12.2 L13.5 5.8' in svg
    assert 'stdDeviation="18"' in svg


def test_readme_defaults_to_chinese_with_english_switch():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    english = (ROOT / "README.en.md").read_text(encoding="utf-8")

    assert "https://img.shields.io/badge/中文-当前-111827" in readme
    assert "(README.en.md)" in readme
    assert "本地优先的 Windows 语音输入层" in readme
    assert "## 为什么这个项目值得看" in readme
    assert "## 技术栈" in readme
    assert "## 快速开始" in readme
    assert "https://img.shields.io/badge/English-Current-111827" in english
    assert "(README.md)" in english
    assert "local-first dictation for Windows" in english
