import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_streaming_delta_queue_is_monotonic_and_uses_an_adaptive_cadence():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    append_start = html.index("function appendStreaming(delta, sessionId)")
    append_block = html[append_start:html.index("function showProcessing()", append_start)]
    drain_start = html.index("function drainStreamingQueue()")
    drain_block = html[drain_start:html.index("function cancelStreamingQueue()", drain_start)]

    assert "const STREAM_BASE_INTERVAL_MS = 48;" in html
    assert "const STREAM_MIN_INTERVAL_MS = 17;" in html
    assert "streamingConfirmedQueue.push({value, enqueuedAt})" in append_block
    assert "streamingConfirmedQueue.shift()" in drain_block


def test_streaming_queue_is_bounded_and_catches_up_without_unbounded_transcript_arrays():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert "STREAM_HARD_LAG_MS = 600" in html
    assert "STREAM_VISIBLE_BUFFER_LIMIT" in html
    assert "coalesceStreamingBacklog" in html
    assert "streamingTargetConfirmed = [];" not in html
    assert "displayedStreamingText = [];" not in html


def test_delivery_state_uses_minimal_truthful_copy():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "function showDeliveryState(" in html
    assert "clipboard_verified_only: '已复制到剪贴板'" in html
    assert "if (status === 'clipboard_verified_paste_dispatched')" in html
    assert "pill.className = 'pill final_text delivery_dismissed';" in html
    assert ".pill.delivery_dismissed" in html
    assert "clipboard_verified_paste_dispatched: '已完成'" not in html
    assert "已复制并发送粘贴" not in html
    assert "check_only" not in html
    assert "def show_delivery_state(" in overlay


def test_streaming_renders_only_confirmed_append_only_text():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    assert "function updateStreaming(" not in html
    assert "streamingTargetProvisional" not in html
    assert "commonGraphemePrefix" not in html
    assert "renderStreamingTail();" in html
    assert "draftText.textContent =" in html
    assert "innerHTML" not in html
    assert "def append_streaming(self, delta, session_id):" in overlay
    assert "self.overlay.append_streaming(delta, generation)" in main
    assert "self.overlay.update_streaming(" not in main


def test_recording_text_uses_one_color_and_authoritative_updates_keep_the_red_meter():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    state_start = html.index("function updateTranscriptState(")
    state_block = html[state_start:html.index("function showAuthoritativeFinal(", state_start)]

    assert "transition: color" not in html
    assert ".ticker-draft" in html
    assert ".ticker-draft {\n    color: var(--text);\n}" in html
    assert "pill.className = 'pill streaming';" in state_block
    assert "'pill authoritative'" not in state_block
    assert ".ticker-provisional {" not in html


def test_streaming_pill_grows_monotonically_with_each_visible_character():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    append_start = html.index("function appendStreaming(delta, sessionId)")
    append_block = html[append_start:html.index("function showProcessing()", append_start)]
    drain_start = html.index("function drainStreamingQueue()")
    drain_block = html[drain_start:html.index("function cancelStreamingQueue()", drain_start)]
    visible_start = html.index("function appendVisibleGraphemes(")
    visible_block = html[visible_start:drain_start]

    assert "function measureRenderedTextWidth(text)" in html
    assert "textMeasureContext.measureText(text).width" in html
    assert "function growStreamingWidthTo(graphemes)" in html
    assert "Math.max(streamingTargetWidth, target)" in html
    assert "growStreamingWidthTo(streamingVisibleTail);" in visible_block
    assert "appendVisibleGraphemes([next.value]);" in drain_block
    assert "if (!streamingExpanded)" not in append_block
    assert "measureTextWidth(provisionalText)" not in append_block


def test_streaming_tail_is_cropped_without_horizontal_translation():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    render_start = html.index("function fitStreamingTailToWidth(")
    render_block = html[render_start:html.index("function drainStreamingQueue()", render_start)]

    assert "function fitStreamingTailToWidth(graphemes, maxTextWidth)" in render_block
    assert "measureRenderedTextWidth(candidate) > maxTextWidth" in render_block
    assert "fitStreamingTailToWidth(streamingVisibleTail, maxTextWidth)" in render_block
    assert "STREAM_VISIBLE_GRAPHEMES" not in html
    assert "translateX" not in html
    assert "--ticker-offset" not in html
    assert "horizontalOffset: 0" in html


def test_processing_and_authoritative_final_cancel_pending_characters():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    processing = html[
        html.index("function showProcessing()"):
        html.index("function showSettling(")
    ]
    final = html[
        html.index("function showAuthoritativeFinal("):
        html.index("function showSettling(")
    ]

    assert "cancelStreamingQueue();" in processing
    assert "cancelStreamingQueue();" in final
    assert "setTranscriptBuffers(text || '', '');" in final


def test_reduced_motion_appends_the_confirmed_delta_immediately():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    append_start = html.index("function appendStreaming(delta, sessionId)")
    append_block = html[append_start:html.index("function showProcessing()", append_start)]

    assert "prefers-reduced-motion: reduce" in append_block
    assert "appendVisibleGraphemes(immediate);" in append_block


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
    assert main.count("self._append_preview_delta(") == 1
    assert "_preview_accumulator" not in stream_block
    assert "_stream_preview_snapshot" not in stream_block
    assert "self.overlay.append_streaming(delta, generation)" in main


def test_settling_authoritative_final_and_delivery_are_session_guarded():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert "function showSettling(sessionId)" in html
    settling_block = html[html.index("function showSettling(sessionId)"):html.index("function showDeliveryState(")]
    assert "if (sessionId < activeSession) return;" in settling_block
    assert "pill.className = 'pill settling';" in settling_block
    assert "function showAuthoritativeFinal(text, sessionId)" in html
    final_block = html[html.index("function showAuthoritativeFinal(text, sessionId)"):html.index("function showSettling(sessionId)")]
    assert "if (sessionId < activeSession) return;" in final_block
    assert "pill.className = 'pill final_text';" in final_block
    assert "cancelStreamingQueue();" in final_block
    assert "def show_settling(self, session_id):" in overlay
    assert "showSettling({int(session_id)})" in overlay
    assert "def show_authoritative_final(self, text, session_id):" in overlay
    assert "showAuthoritativeFinal(" in overlay


def test_overlay_exposes_status_to_assistive_technology_and_reduces_motion():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "animation-duration: 1ms !important;" in html


def test_settings_have_keyboard_and_narrator_names_for_primary_controls():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert 'for label in ("状态", "词典", "历史", "设置")' in overlay
    assert 'self.sidebar.setAccessibleName("设置导航")' in overlay
    assert 'self.search_box.setAccessibleName("搜索历史转录")' in overlay
    assert 'self.language_combo.setAccessibleName("识别语言")' in overlay
    assert 'self.microphone_combo.setAccessibleName("麦克风")' in overlay
    assert 'self.doctor_list.setAccessibleName("诊断结果")' in overlay
    assert 'self.practice_box.setAccessibleName("VoiceFlow 试说输入框")' in overlay


def test_settings_do_not_expose_model_choice_or_download_controls():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    status_start = overlay.index("def _status_page(self):")
    status_block = overlay[status_start:overlay.index("def _dictionary_page(self):", status_start)]

    assert "model_combo" not in status_block
    assert "model_download_button" not in status_block
    assert "model_cancel_button" not in status_block
    assert "model_progress" not in status_block
    assert '("模型",' not in status_block
    assert "下载" not in status_block


def test_history_does_not_expose_internal_output_status_codes():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert '"clipboard_verified_paste_dispatched": "已完成"' in overlay
    assert '"clipboard_verified_only": "已复制"' in overlay
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
    assert "self._history_card(text, meta, entry_id)" in settings_block
    assert "self.search_box.setPlaceholderText(\"搜索最近转录\")" in settings_block
    assert "QPushButton(\"复制\")" in settings_block
    assert "QPushButton(\"再次粘贴\")" in settings_block
    assert "QPushButton(\"复制全部\")" in settings_block
    assert "copy.clicked.connect(lambda _=False, value=text: self._copy_text(value))" in settings_block
    assert "meta_parts.append(f\"尾部 {tail}\")" in settings_block
    assert "self._run_history_action(text, self._on_copy_text" in settings_block
    assert 'name="voiceflow-history-action"' in settings_block
    assert "label = self._output_status_label(status)" in settings_block
    assert "pyperclip.copy(text)" not in settings_block
    assert "self._copy_text(\"\\n\\n\".join(texts))" in settings_block
    assert "self._run_history_action(text, self._on_repaste_text" in settings_block
    assert "self._set_status_badge(\"无可复制\")" in settings_block


def test_settings_window_uses_app_shell_sidebar_not_default_tabs():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "QStackedWidget" in overlay
    assert "self.sidebar = QListWidget()" in settings_block
    assert "self.stack = QStackedWidget()" in settings_block
    assert "self.sidebar.currentRowChanged.connect(self._show_primary_page)" in settings_block
    assert "page_by_row = {0: 0, 1: 3, 2: 1, 3: 2}" in settings_block
    assert "QTabWidget" not in overlay
    assert "QLabel#sectionTitle" in settings_block


def test_settings_status_page_exposes_language_without_model_setup_actions():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "self.language_combo = QComboBox()" in settings_block
    assert '("语言", self.language_combo)' in settings_block
    assert "self.model_combo = QComboBox()" not in settings_block
    assert "def _save_settings(self):" in settings_block
    assert "for profile in user_model_profiles()" not in settings_block
    assert "model_download_button" not in settings_block
    assert "model_cancel_button" not in settings_block
    assert "self.model_progress = QProgressBar()" not in settings_block
    assert "def _open_model_setup(self):" not in settings_block
    assert "self.model_manager.start_download" not in settings_block


def test_sensevoice_language_copy_recommends_automatic_bilingual_detection():
    source = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert '("自动中英（推荐）", "auto")' in source
    assert '("自动检测（实验）", "auto")' not in source


def test_settings_merges_static_hotkey_help_into_dictation():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert "def _hotkeys_page" not in settings_block
    assert "trigger_summary()" in settings_block
    assert 'trial.clicked.connect(self._start_trial)' in settings_block


def test_dictionary_exposes_words_phrases_and_deterministic_corrections():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    settings_idx = overlay.index("class _SettingsWindow")
    overlay_window_idx = overlay.index("class OverlayWindow", settings_idx)
    settings_block = overlay[settings_idx:overlay_window_idx]

    assert 'self.dictionary_section.addItem("内置 AI 术语", "builtin-ai.txt")' in settings_block
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


def test_existing_instance_connection_opens_settings_without_waiting_for_payload():
    from overlay_webview import OverlayWindow

    class FakeSocket:
        def __init__(self):
            self.reads = 0
            self.disconnects = 0
            self.writes = []
            self.flushes = 0

        def readAll(self):
            self.reads += 1

        def disconnectFromServer(self):
            self.disconnects += 1

        def write(self, payload):
            self.writes.append(payload)

        def flush(self):
            self.flushes += 1

    class FakeServer:
        def __init__(self, socket):
            self.socket = socket
            self.pending = True

        def hasPendingConnections(self):
            return self.pending

        def nextPendingConnection(self):
            self.pending = False
            return self.socket

    socket = FakeSocket()
    overlay = object.__new__(OverlayWindow)
    overlay._single_instance_server = FakeServer(socket)
    shown = []
    overlay._show_settings = lambda: shown.append(True)

    overlay._on_instance_message()

    assert shown == [True]
    assert socket.reads == 1
    assert socket.writes == [b"shown\n"]
    assert socket.flushes == 1
    assert socket.disconnects == 1


def test_existing_instance_file_fallback_opens_settings_once(tmp_path):
    from overlay_webview import OverlayWindow

    overlay = object.__new__(OverlayWindow)
    overlay._instance_request_path = tmp_path / "show-settings.request"
    shown = []
    overlay._show_settings = lambda: shown.append(True)

    overlay._write_instance_request()
    overlay._consume_instance_request()
    overlay._consume_instance_request()

    assert shown == [True]
    assert not overlay._instance_request_path.exists()


def test_existing_instance_file_fallback_tolerates_small_clock_rollback(
    tmp_path,
    monkeypatch,
):
    import overlay_webview
    from overlay_webview import OverlayWindow

    clock = iter((100.0, 99.9))
    monkeypatch.setattr(overlay_webview.time, "time", lambda: next(clock))
    overlay = object.__new__(OverlayWindow)
    overlay._instance_request_path = tmp_path / "show-settings.request"
    shown = []
    overlay._show_settings = lambda: shown.append(True)

    overlay._write_instance_request()
    overlay._consume_instance_request()

    assert shown == [True]
    assert not overlay._instance_request_path.exists()


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


def test_stop_flow_replaces_final_text_before_minimal_delivery_feedback():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_idx = main.index("def _on_record_stop")
    stream_idx = main.index("def _start_streaming", stop_idx)
    stop_block = main[stop_idx:stream_idx]

    assert "final_generation = self._stop_streaming()" in stop_block
    assert "self.overlay.show_settling(final_generation)" in stop_block
    assert "self.overlay.show_authoritative_final(text, final_generation)" in stop_block
    assert "delivery = self.output_handler.deliver(" in stop_block
    assert "self.overlay.show_delivery_state(" in stop_block
    assert stop_block.index("self.overlay.show_authoritative_final(") < stop_block.index("delivery = self.output_handler.deliver(")
    assert stop_block.index("delivery = self.output_handler.deliver(") < stop_block.index("self.overlay.show_delivery_state(")
    assert "self.overlay.show_done()" not in stop_block
    assert "self.overlay.show_result(text)" not in stop_block


def test_overlay_has_processing_settling_spinner_and_final_checkmark():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    processing_idx = html.index("function showProcessing()")
    done_idx = html.index("function showSettling(sessionId)", processing_idx)
    processing_block = html[processing_idx:done_idx]
    processing_ticker_block = html[html.index(".processing .ticker"):html.index(".error .ticker")]

    assert ".pill.done" not in html
    assert ".pill.settling" in html
    assert ".final_text .mark span" in html
    assert ".processing .mark::before" in html
    assert ".settling .mark::before" in html
    assert ".done .mark::before" not in html
    assert ".final_ready .mark::before" in html
    assert "@keyframes spin" in html
    assert "function showDone()" not in html
    assert "showState('processing'" not in processing_block
    assert "setWidthForText" not in processing_block
    assert "txt.textContent" not in processing_block
    assert "color: transparent;" not in processing_ticker_block
    assert "color: var(--text);" in processing_ticker_block
    assert "pill.className = 'pill processing';" in processing_block
    assert "showState('done', '已完成')" not in html
    assert "setWidthForLabel(label || '');" in html[html.index("function showState(state, label)"):html.index("function showRecording(sessionId)")]
    assert "position: absolute;" in html[html.index(".processing .mark::before"):html.index(".final_ready .mark::before")]
    assert "inset: 2.5px;" in html[html.index(".processing .mark::before"):html.index(".final_ready .mark::before")]
    assert "border-right: 1.8px solid var(--green);" in html
    assert "border-bottom: 1.8px solid var(--green);" in html
    assert "def show_done(self):" not in overlay
    assert 'self._js("showProcessing()")' in overlay
    assert "showDone()" not in overlay


def test_overlay_processing_only_changes_mark_state():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    processing_css = html[html.index(".pill.processing"):html.index(".pill.final_ready")]
    processing_idx = html.index("function showProcessing()")
    processing_block = html[processing_idx:html.index("function showSettling(sessionId)", processing_idx)]

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
    assert 'id="check"' not in svg
    assert 'id="liveText"' in svg
    assert 'id="finalText"' in svg
    assert ">已完成</text>" not in svg
    assert "deliveryDismissState" in svg
    assert "· 21" not in svg
    assert "@keyframes waveState" in svg
    assert "@keyframes checkState" not in svg
    assert "@keyframes liveTextState" in svg
    assert "@keyframes finalTextState" in svg
    assert 'id="demo-spinner"' not in svg
    assert "@keyframes spinnerState" not in svg


def test_readme_demo_keeps_branded_overlay_geometry_and_copy():
    svg = (ROOT / "docs" / "voiceflow-demo.svg").read_text(encoding="utf-8")

    assert 'width="96" height="52" rx="26"' in svg
    assert "@keyframes pillState" in svg
    assert "22%, 64% { width: 380px; }" in svg
    assert "prefers-reduced-motion: reduce" in svg
    assert "明早十点，把方案同步给团队。" in svg
    assert "按一下开始，再按一下完成" in svg
    assert "已复制 · 14字" not in svg
    assert 'id="softPanel"' not in svg


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


def test_tray_menu_can_toggle_dictation_without_a_global_hotkey():
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    assert 'QAction("开始 / 停止听写"' in overlay
    assert "dictate_act.triggered.connect(self._on_record_toggle)" in overlay
    assert "on_record_toggle=self._on_record_toggle" in main


def test_flagship_capsule_uses_draft_and_authoritative_text_layers():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    assert 'id="authoritativeText"' in html
    assert 'id="draftText"' in html
    assert ".ticker-draft" in html
    assert "color: var(--muted);" in html
    assert "function updateTranscriptState(" in html
    assert "function showAuthoritativeFinal(" in html
    assert "def update_transcript_state(" in overlay
    assert "def show_authoritative_final(" in overlay
    assert "innerHTML" not in html


def test_stop_wait_keeps_text_and_uses_an_unlabelled_spinner_after_350ms():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")

    settling_start = html.index("function showSettling(sessionId)")
    settling_end = html.index("function showDeliveryState(", settling_start)
    settling = html[settling_start:settling_end]

    assert "FINALIZING_DELAY_SECONDS = 0.35" in main
    assert "pill.className = 'pill settling';" in settling
    assert "cancelStreamingQueue();" in settling
    assert "txt.textContent" not in settling
    assert "setWidthForLabel" not in settling
    assert "整理中" not in settling
    assert "pill.classList.contains('final_text')" in settling
    assert "pill.classList.contains('final_ready')" in settling
    assert ".settling .mark::before" in html
    assert ".settling .ticker" in html


def test_delivery_feedback_is_minimal_truthful_and_has_accessible_detail():
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    overlay = (ROOT / "src" / "overlay_webview.py").read_text(encoding="utf-8")

    delivery_start = html.index("function showDeliveryState(")
    delivery_end = html.index("function showResult(", delivery_start)
    delivery = html[delivery_start:delivery_end]

    assert "if (status === 'clipboard_verified_paste_dispatched')" in delivery
    assert "pill.className = 'pill final_text delivery_dismissed';" in delivery
    assert "clipboard_verified_paste_dispatched: '已完成'" not in delivery
    assert "clipboard_verified_only: '已复制到剪贴板'" in delivery
    assert "recovery_saved_clipboard_unavailable: '已保存'" in delivery
    assert "clipboard_verified_paste_dispatched: '已复制并发送粘贴'" not in delivery
    assert "字`" not in delivery
    assert "pill.setAttribute('aria-label'" in delivery
    assert "check_only" not in delivery
    assert ".pill.check_only" not in html
    assert "def show_delivery_state(" in overlay


def test_final_text_replaces_the_draft_before_delivery_feedback():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    stop_start = main.index("def _on_record_stop")
    stop_end = main.index("def _audio_sample_count", stop_start)
    stop = main[stop_start:stop_end]

    final_text = stop.index("self.overlay.show_authoritative_final(")
    delivery = stop.index("delivery = self.output_handler.deliver(")
    feedback = stop.index("self.overlay.show_delivery_state(")

    assert stop.index("finalizing_done.set()") < final_text
    assert final_text < delivery < feedback
    assert "self.overlay.show_delivery_summary(" not in stop
    assert "self.overlay.show_final_summary(" not in stop

    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")
    final_start = html.index("function showAuthoritativeFinal(")
    final_end = html.index("function showProcessing()", final_start)
    final = html[final_start:final_end]
    assert "pill.classList.contains('final_ready')" in final
    assert "pill.classList.contains('recovery')" in final


def test_success_dismisses_quietly_while_fallback_states_remain_visible():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    html = (ROOT / "src" / "overlay.html").read_text(encoding="utf-8")

    assert "FINAL_REPLACEMENT_DWELL_MS" not in html
    assert "SUCCESS_DISMISS_MS = 140" in main
    assert "FINAL_TEXT_HOLD_SHORT_MS" not in main
    assert "CLIPBOARD_ONLY_HOLD_MS = 1040" in main
    assert "RECOVERY_SAVED_HOLD_MS = 1740" in main
    hold_start = main.index("def _delivery_hold_ms")
    hold_end = main.index("def _active_engine_name", hold_start)
    hold = main[hold_start:hold_end]
    assert 'if output_status == "clipboard_verified_paste_dispatched"' in hold
    assert "return self.SUCCESS_DISMISS_MS" in hold


def test_empty_capture_is_a_neutral_cancel_not_a_red_audio_error():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    empty_capture = source.split("if len(data) == 0:", 1)[1].split(
        "cache_handoff_started", 1
    )[0]

    assert "self.overlay.show_canceled()" in empty_capture
    assert 'self.overlay.show_error("无音频")' not in empty_capture
    assert "self.overlay.hide_after(650)" in empty_capture
