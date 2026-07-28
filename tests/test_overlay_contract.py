import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_streaming_delta_queue_is_monotonic_and_uses_a_fixed_cadence():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    update_start = html.index(
        "function updateStreaming(confirmedText, provisionalText, sessionId)"
    )
    update_block = html[update_start:html.index("function appendStreaming(", update_start)]
    drain_start = html.index("function drainStreamingQueue()")
    drain_block = html[drain_start:html.index("function cancelStreamingQueue()", drain_start)]

    assert "const STREAM_APPEND_INTERVAL_MS = 80;" in html
    assert "streamingTargetConfirmed = nextConfirmed;" in update_block
    assert "streamingTargetProvisional = nextProvisional;" in update_block
    assert "cancelStreamingQueue();" not in update_block
    assert "drainStreamingQueue();" in update_block
    assert "displayedStreamingText.push(" in drain_block
    assert "setTimeout(drainStreamingQueue, STREAM_APPEND_INTERVAL_MS)" in drain_block
    assert "Math.ceil(" not in update_block
    assert "Math.max(0, 250 - queueDelayMs)" not in update_block


def test_streaming_renders_confirmed_text_and_a_replaceable_provisional_tail():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    update_start = html.index(
        "function updateStreaming(confirmedText, provisionalText, sessionId)"
    )
    update_block = html[
        update_start:html.index("function appendStreaming(", update_start)
    ]

    assert ".ticker-provisional" in html
    assert "streamingTargetConfirmed" in update_block
    assert "streamingTargetProvisional" in update_block
    assert "commonGraphemePrefix" in update_block
    assert "txt.replaceChildren(confirmedNode, provisionalNode)" in html
    assert "innerHTML" not in html
    assert "def update_streaming(self, confirmed, provisional, session_id):" in overlay
    assert "self.overlay.update_streaming(" in main


def test_streaming_pill_grows_monotonically_with_each_visible_character():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    update_start = html.index(
        "function updateStreaming(confirmedText, provisionalText, sessionId)"
    )
    update_block = html[update_start:html.index("function appendStreaming(", update_start)]
    drain_start = html.index("function drainStreamingQueue()")
    drain_block = html[drain_start:html.index("function cancelStreamingQueue()", drain_start)]

    assert "const STREAM_GROWTH_PER_GRAPHEME = 10;" in html
    assert "function growStreamingWidthTo(characterCount)" in html
    assert "Math.max(streamingTargetWidth, target)" in html
    assert "growStreamingWidthTo(displayedStreamingText.length);" in drain_block
    assert "growStreamingWidthTo(displayedStreamingText.length);" in update_block
    assert "if (!streamingExpanded)" not in update_block
    assert "measureTextWidth(provisionalText)" not in update_block


def test_streaming_tail_is_cropped_without_horizontal_translation():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    render_start = html.index("function renderStreamingTail()")
    render_block = html[render_start:html.index("function drainStreamingQueue()", render_start)]

    assert "const STREAM_VISIBLE_GRAPHEMES = 20;" in html
    assert "displayedStreamingText.length - STREAM_VISIBLE_GRAPHEMES" in render_block
    assert "displayedStreamingText.slice(start)" in render_block
    assert "translateX" not in html
    assert "--ticker-offset" not in html
    assert "horizontalOffset: 0" in html


def test_processing_and_final_summary_cancel_pending_characters():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    processing = html[
        html.index("function showProcessing()"):
        html.index("function showFinalizing(")
    ]
    final = html[
        html.index("function showFinalSummary("):
        html.index("function showResult(")
    ]

    assert "cancelStreamingQueue();" in processing
    assert "resetTextMotion();" in final
    assert "`已复制 · ${count}字`" in final


def test_reduced_motion_appends_the_confirmed_delta_immediately():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    update_start = html.index(
        "function updateStreaming(confirmedText, provisionalText, sessionId)"
    )
    update_block = html[update_start:html.index("function appendStreaming(", update_start)]

    assert "prefers-reduced-motion: reduce" in update_block
    assert "displayedStreamingText = nextTarget.slice();" in update_block
    assert "renderStreamingTail();" in update_block


def test_preview_mailbox_keeps_only_the_latest_pending_ui_value():
    from overlay_webview import _LatestPreviewMailbox

    mailbox = _LatestPreviewMailbox()
    mailbox.put("old")
    mailbox.put("new")

    assert mailbox.take() == "new"
    assert mailbox.take() is None


def test_recording_meter_is_driven_by_real_audio_without_animation_backlog():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    assert "function updateAudioLevel(levels, sessionId)" in html
    assert "meterScale(Number(level) || 0)" in html
    assert "animation: bar1" not in html
    assert "level_js_requested = Signal(str)" in overlay
    assert "self._level_mailbox = _LatestPreviewMailbox()" in overlay
    assert "def update_audio_level(self, levels, session_id):" in overlay
    assert "self.audio.set_level_callback(self._on_audio_levels)" in main


def test_streaming_bridge_preserves_every_ordered_delta():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    append_start = overlay.index("def append_streaming(self, delta, session_id):")
    append_end = overlay.index("def update_audio_level", append_start)
    append_block = overlay[append_start:append_end]

    assert "self._js(" in append_block
    assert "preview_js_requested" not in overlay
    assert "_preview_mailbox" not in overlay
    assert "_queue_preview_js" not in overlay


def test_online_preview_uses_one_monotonic_append_path():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stream_idx = main.index("def _start_streaming")
    stop_idx = main.index("def _stop_streaming", stream_idx)
    stream_block = main[stream_idx:stop_idx]

    assert "function updateCorrection" not in html
    assert "def update_correction" not in overlay
    assert main.count("self._update_preview_state(") == 1
    assert "_preview_accumulator" not in stream_block
    assert "_stream_preview_snapshot" not in stream_block
    assert "self.overlay.update_streaming(confirmed, provisional, generation)" in main


def test_finalizing_and_final_summary_are_session_guarded():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "function showFinalizing(sessionId)" in html
    assert "activeSession = sessionId;" in html[html.index("function showFinalizing(sessionId)"):html.index("function showDone()")]
    assert "pill.className = 'pill finalizing';" in html
    assert "function showFinalSummary(characterCount, sessionId)" in html
    final_block = html[html.index("function showFinalSummary(characterCount, sessionId)"):html.index("function showResult(msg)")]
    assert "if (sessionId < activeSession) return;" in final_block
    assert "pill.className = 'pill final_ready success';" in final_block
    assert "resetTextMotion();" in final_block
    assert "已复制 · ${count}字" in final_block
    assert "def show_finalizing(self, session_id):" in overlay
    assert "showFinalizing({int(session_id)})" in overlay
    assert "def show_final_summary(self, character_count, session_id):" in overlay
    assert "showFinalSummary({int(character_count)}, {int(session_id)})" in overlay


def test_overlay_exposes_status_to_assistive_technology_and_reduces_motion():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "animation-duration: 1ms !important;" in html


def test_settings_have_keyboard_and_narrator_names_for_primary_controls():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert (
        'for label in ("首页", "历史", "听写", "词典", "诊断", "关于")'
        in overlay
    )
    assert 'self.sidebar.setAccessibleName("设置导航")' in overlay
    assert 'self.search_box.setAccessibleName("搜索历史转录")' in overlay
    assert 'self.model_combo.setAccessibleName("识别模型")' in overlay
    assert 'self.language_combo.setAccessibleName("识别语言")' in overlay
    assert 'self.microphone_combo.setAccessibleName("麦克风")' in overlay
    assert 'self.doctor_list.setAccessibleName("诊断结果")' in overlay
    assert 'self.practice_box.setAccessibleName("VoiceFlow 试说输入框")' in overlay


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
    reset_motion = html[html.index("function resetTextMotion()"):]
    assert "streamingCharacterCount = 0;" in reset_motion
    assert "streamingTargetWidth = MIN_WIDTH;" in reset_motion
    assert "activeSession = sessionId;" in html


def test_recording_window_shows_after_js_state_preparation():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    start_idx = main.index("def _on_record_start")
    start_block = main[start_idx:main.index("def _on_record_stop", start_idx)]
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "self.overlay.show_window()" not in start_block
    assert "js_then_show_requested.emit(f\"prepareRecording({int(session_id)})\")" in overlay
    assert "runJavaScript(code, lambda _: self.show_requested.emit())" in overlay
    assert "self.overlay.show_recording(generation, triggered_at)" in start_block
    assert start_block.index("self.overlay.show_recording") < start_block.index(
        "self.session.start()"
    )


def test_trigger_feedback_is_recorded_after_the_real_qt_paint():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "class _PaintAwareWindow(QMainWindow):" in overlay
    assert "first_paint_completed = Signal()" in overlay
    assert "QTimer.singleShot(0, self.first_paint_completed.emit)" in overlay
    assert "before_show=self._expect_recording_paint" in overlay
    assert "self._on_recording_painted(session_id, elapsed_ms)" in overlay
    assert "def _on_recording_painted(self, generation, elapsed_ms):" in main
    assert "self._last_trigger_to_feedback_ms = float(elapsed_ms)" in main
    assert "time.perf_counter() - triggered_at" not in main[
        main.index("def _on_record_start"):main.index("def _on_record_stop")
    ]


def test_first_preview_text_reports_after_two_browser_paint_frames():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    assert "qrc:///qtwebchannel/qwebchannel.js" in html
    assert "requestAnimationFrame(() => {" in html
    assert "nativeBridge.previewPainted(paintedSession)" in html
    assert "class _PreviewPaintReporter(QObject):" in overlay
    assert "self._on_preview_painted(session_id, time.perf_counter())" in overlay
    assert "def _on_preview_painted(self, generation, painted_at):" in main
    assert "self._preview_first_paint_ms" in main


def test_final_shortness_guard_uses_live_preview_text_not_removed_accumulator():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    final_start = main.index("def _transcribe_final_result")
    final_end = main.index("def _transcribe_final_text", final_start)
    final_block = main[final_start:final_end]

    assert "_preview_accumulator" not in final_block
    assert 'getattr(self, "_latest_text", "")' in final_block


def test_recording_start_cancels_pending_hide_timer():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    init_idx = overlay.index("def __init__(self):")
    run_idx = overlay.index("def _run(self):", init_idx)
    init_block = overlay[init_idx:run_idx]
    recording_idx = overlay.index("def show_recording(self, session_id, triggered_at=None):")
    streaming_idx = overlay.index("def append_streaming", recording_idx)
    recording_block = overlay[recording_idx:streaming_idx]

    assert "self._hide_timer = None" in init_block
    assert "self._cancel_pending_hide()" in recording_block


def test_app_launch_only_opens_onboarding_before_background_model_load():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    ready_idx = main.index("def _on_overlay_ready")
    start_hotkeys_idx = main.index("def _start_hotkeys", ready_idx)
    ready_block = main[ready_idx:start_hotkeys_idx]
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "self.overlay.show_startup_window()" in ready_block
    assert "def show_settings_window(self):" in overlay
    assert "def show_startup_window(self):" in overlay
    assert "settings_requested = Signal()" in overlay
    assert "startup_requested = Signal()" in overlay
    assert "self._bridge.settings_requested.connect(self._show_settings)" in overlay
    assert "self._bridge.startup_requested.connect(self._show_startup)" in overlay


def test_settings_window_has_recent_history_copy_controls():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "self.history_list = QListWidget()" in settings_block
    assert "setItemWidget(item, self._history_card" in settings_block
    assert "self.search_box.setPlaceholderText(\"搜索最近转录\")" in settings_block
    assert "QPushButton(\"复制\")" in settings_block
    assert "QPushButton(\"再次粘贴\")" in settings_block
    assert "QPushButton(\"复制全部\")" in settings_block
    assert "copy.clicked.connect(lambda _=False, value=text: self._copy_text(value))" in settings_block
    assert "meta_parts.append(f\"尾部 {tail}\")" in settings_block
    assert "pyperclip.copy(text)" in settings_block
    assert "pyperclip.copy(\"\\n\\n\".join(texts))" in settings_block
    assert "self._on_repaste_text(text)" in settings_block
    assert "self._set_status_badge(\"无可复制\")" in settings_block


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
    assert '"验证完整性"' in settings_block
    assert '"模型实验"' in settings_block
    assert "self.model_manager.selectable_engines(config)" in settings_block
    assert "download.clicked.connect(self._open_model_setup)" in settings_block
    assert "def _open_model_setup(self):" in settings_block
    assert "self.model_manager.open_setup" in settings_block


def test_settings_merges_static_hotkey_help_into_dictation():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "def _hotkeys_page" not in settings_block
    assert "F2 · 右 Ctrl · 鼠标侧键 1 / 2" in settings_block
    assert 'trial.clicked.connect(self._start_trial)' in settings_block


def test_dictionary_exposes_words_phrases_and_deterministic_corrections():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert 'self.dictionary_section.addItem("专有词", "user-dictionary.txt")' in settings_block
    assert 'self.dictionary_section.addItem("常用短语", "phrases.txt")' in settings_block
    assert 'self.dictionary_section.addItem("确定性纠错", "corrections.txt")' in settings_block
    assert "不会调用生成模型改写意思" in settings_block


def test_settings_runtime_actions_do_not_depend_on_source_tree_tools():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "venv" not in settings_block
    assert "scripts\\\\download_models.py" not in settings_block
    assert "scripts/doctor.py" not in settings_block
    assert "run_runtime_diagnostics" in settings_block


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

    assert "function appendStreaming(delta, sessionId)" in html
    assert "if (sessionId !== activeSession) return;" in html
    assert "activeSession += 1;" in html[html.index("function showState(state, label)"):]
    assert "appendStreaming({json.dumps(delta, ensure_ascii=False)}, {int(session_id)})" in overlay


def test_stop_flow_outputs_before_final_summary_feedback():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_idx = main.index("def _on_record_stop")
    stream_idx = main.index("def _start_streaming", stop_idx)
    stop_block = main[stop_idx:stream_idx]

    assert "final_generation = self._stop_streaming()" in stop_block
    assert "self.overlay.show_finalizing(final_generation)" in stop_block
    assert "self.overlay.show_final_summary(len(text), final_generation)" in stop_block
    assert "self.output_handler.copy_only(text)" in stop_block
    assert stop_block.index("output_status = self.output_handler.output(text)") < stop_block.index("self.overlay.show_final_summary(len(text), final_generation)")
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
    assert "setWidthForLabel(label || '');" in html[html.index("function showState(state, label)"):html.index("function showRecording(sessionId)")]
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


def test_readme_demo_keeps_branded_overlay_geometry_and_copy():
    svg = (ROOT / "docs" / "voiceflow-demo.svg").read_text(encoding="utf-8")

    assert 'width="86" height="34" rx="17"' in svg
    assert "@keyframes pillState" in svg
    assert "34%, 88% { width: 236px; }" in svg
    assert "prefers-reduced-motion: reduce" in svg
    assert "明早十点，把方案同步给团队。" in svg
    assert "把声音收束成文字，把文字送回光标。" in svg
    assert "真实胶囊状态：录音预览 → 最终确认 → 剪贴板兜底" in svg


def test_readme_defaults_to_chinese_with_english_switch():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    english = (ROOT / "README.en.md").read_text(encoding="utf-8")

    assert '<strong>简体中文</strong> · <a href="README.en.md">English</a>' in readme
    assert "Windows 上的离线语音输入工具" in readme
    assert "## 为什么是 VoiceFlow" in readme
    assert "## 下载" in readme
    assert "## 使用" in readme
    assert "docs/voiceflow-demo.svg" in readme
    assert "面试" not in readme
    assert "Codex" not in readme
    assert "GitHub 右侧的语言统计" not in readme
    assert '<a href="README.md">简体中文</a> · <strong>English</strong>' in english
    assert "offline dictation for Windows" in english
    assert "## Why VoiceFlow" in english
    assert "## Download" in english
    assert "## Controls" in english
    assert "docs/voiceflow-demo.svg" in english
