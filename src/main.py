"""
VoiceFlow — 本地语音转文字。F2 切换录音，Esc 取消。
按 F2 开始，说完再按 F2 停止粘贴。后台持续转写，停止时秒出结果。
"""

import os
import sys
import json
import time
import argparse
import logging
import threading
import uuid
import yaml
import numpy as np
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(__file__))

from audio_capture import AudioCapture
from transcriber import Transcriber
from hotkey_manager import HotkeyManager
from output_handler import OutputHandler
from overlay_webview import OverlayWindow
from text_cleaner import TextCleaner
from history_store import HistoryStore
from recording_session import RecordingSession
from recording_state import RecordingState, RecordingStateMachine
from runtime_logging import configure_runtime_logging
from audio_activity import (
    SileroSpeechDetector,
    find_speech_onset,
    has_lexical_content,
    has_speech_activity,
)
from runtime_paths import AppPaths, prepare_runtime_layout
from streaming_transcriber import OnlinePreviewTranscriber
from punctuation import FinalPunctuationRestorer
from platform_utils import open_path
from recovery_session import RecoverySessionStore
from safe_text import SafeTextBoundary
from model_switch import ModelSwitchCoordinator
from transcript_state import FinalizationTimeline, TranscriptViewState


logger = logging.getLogger("voiceflow.runtime")


@dataclass(frozen=True)
class FinalSegmentCoverage:
    start_sample: int
    end_sample: int
    text: str
    speech: bool


@dataclass(frozen=True)
class FinalTranscriptionResult:
    text: str
    captured_samples: int
    covered_samples: int
    coverage_ok: bool
    final_source: str


class _InitWorker(threading.Thread):
    def __init__(self, system, on_done, on_error):
        super().__init__(daemon=True)
        self.system = system
        self.on_done = on_done
        self.on_error = on_error

    def run(self):
        try:
            self.system._init_modules()
            self.on_done()
        except Exception as e:
            self.on_error(e)


class VoiceInputSystem:
    STREAM_PREVIEW_POLL_SECONDS = 0.04
    FINAL_SEGMENT_SECONDS = 18.0
    FINAL_SEGMENT_OVERLAP_SECONDS = 1.0
    FINAL_SEGMENT_HOLD_SECONDS = 0.32
    SEGMENTED_FINAL_MIN_SECONDS = 20.0
    PREVIEW_ENDPOINT_LIMIT = 256
    FINAL_CACHE_HANDOFF_TIMEOUT_SECONDS = 3.0
    FINALIZING_DELAY_SECONDS = 0.35
    SUCCESS_DISMISS_MS = 140
    CLIPBOARD_ONLY_HOLD_MS = 1040
    RECOVERY_SAVED_HOLD_MS = 1740

    def __init__(self, config_path=None, *, paths=None):
        self.paths = paths or AppPaths.discover(config_path=config_path)
        self.migration = prepare_runtime_layout(self.paths)
        self.base_dir = str(self.paths.data_dir)
        configure_runtime_logging(str(self.paths.logs_dir / "runtime.jsonl"))
        config_path = str(self.paths.config_file)
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.config_path = config_path
        self._recording_state = RecordingStateMachine()
        self._shutdown_started = False
        self._streaming = False
        self._stream_stop_event = None
        self._stream_generation = 0
        self._latest_text = ""  # 后台转写的最新结果
        self.preview_transcriber = None
        self._preview_started_at = None
        self._preview_first_text_ms = None
        self._speech_onset_sample = None
        self._speech_onset_at = None
        self._preview_first_model_delta_at = None
        self._preview_first_model_delta_ms = None
        self._preview_first_paint_ms = None
        self._preview_queue_delay_ms = None
        self._preview_last_delta_at = None
        self._preview_update_gap_ms = None
        self._preview_active_speech_since_delta_ms = 0.0
        self._preview_active_speech_update_gap_ms = None
        self._preview_divergence_count = 0
        self._preview_update_count = 0
        self._preview_max_chunk_chars = 0
        self._last_trigger_to_feedback_ms = None
        self._final_segments = []
        self._finalized_audio_len = 0
        self._final_cache_lock = threading.Lock()
        self._final_cache_state_lock = threading.Lock()
        self._final_cache_idle = threading.Event()
        self._final_cache_idle.set()
        self._preview_endpoint_lock = threading.Lock()
        self._preview_endpoint_samples = []
        self._transcribe_lock = threading.Lock()
        recovery_config = self.config.get("recovery", {})
        self._recovery_enabled = bool(recovery_config.get("enabled", True))
        self._recovery_store = RecoverySessionStore(
            self.paths.recovery_dir,
            retention_hours=float(recovery_config.get("retention_hours", 24)),
        )
        self._recovery_store.purge_expired()
        self._recovery_journal = None
        self._active_session_id = None
        self._target_snapshot = None
        self._safe_text = SafeTextBoundary()
        vad_config = self.config.get("vad", {})
        self._speech_gate_enabled = bool(vad_config.get("enabled", True))
        self._speech_rms_threshold = float(vad_config.get("asr_energy_floor", 0.002))
        self._speech_min_active_ms = int(vad_config.get("min_speech_ms", 90))
        self._speech_detector = None
        if self._speech_gate_enabled:
            vad_model = self.paths.resolve_asset(
                vad_config.get("model_path", "assets/silero_vad.onnx"),
            )
            try:
                self._speech_detector = SileroSpeechDetector(
                    vad_model,
                    threshold=float(vad_config.get("speech_probability_threshold", 0.5)),
                    min_speech_ms=self._speech_min_active_ms,
                    sample_rate=int(self.config.get("audio", {}).get("sample_rate", 16000)),
                )
            except Exception:
                logger.exception("Silero VAD unavailable; using the energy safety gate")
        self.overlay = OverlayWindow(self.paths)
        self.history = HistoryStore(self.paths.history_file)
        self.punctuation = FinalPunctuationRestorer()

    def _init_modules(self):
        print("[启动] 音频...", flush=True)
        self.audio = AudioCapture(self.config_path)
        self.audio.set_level_callback(self._on_audio_levels)
        self.session = RecordingSession(self.audio)

        print("[启动] ASR...", flush=True)
        self.overlay.show_processing()
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        switch = ModelSwitchCoordinator(
            self.paths.model_switch_dir,
            self.paths.config_file,
        )
        pending_switch = switch.pending()
        self.transcriber = Transcriber(
            self.config_path,
            asset_roots=self.paths.asset_roots,
        )
        try:
            self.transcriber.load_engine(engine)
        except Exception as candidate_error:
            if not pending_switch or pending_switch.get("candidate_engine") != engine:
                raise
            previous = switch.rollback(str(candidate_error))
            logger.exception(
                "candidate model failed startup validation; rolling back to %s",
                previous,
            )
            with open(self.config_path, "r", encoding="utf-8") as stream:
                self.config = yaml.safe_load(stream) or {}
            engine = self.config.get("engine", {}).get("active", previous or "sensevoice")
            self.transcriber = Transcriber(
                self.config_path,
                asset_roots=self.paths.asset_roots,
            )
            self.transcriber.load_engine(engine)
        else:
            if pending_switch and pending_switch.get("candidate_engine") == engine:
                switch.commit(engine)
        print(f"[启动] {engine}", flush=True)

        try:
            self.preview_transcriber = OnlinePreviewTranscriber.from_config(
                self.config,
                resolve_asset=self.paths.resolve_asset,
                sample_rate=self.audio.sample_rate,
            )
            print("[启动] 实时预览", flush=True)
        except Exception as exc:
            self.preview_transcriber = None
            logger.warning(
                "real-time preview unavailable; keeping the quiet recording capsule: %s",
                exc,
            )

        self.output_handler = OutputHandler(
            self.config_path, base_dir=self.base_dir, overlay=self.overlay
        )
        for pending in self.output_handler.recover_pending():
            session_id = pending["session_id"]
            if not self.history.has_session_id(session_id):
                self.history.append(
                    raw_text=pending["text"],
                    clean_text=pending["text"],
                    corrected_text=pending["text"],
                    output_status="clipboard_verified_only",
                    model=engine,
                    final_source="pending_delivery_recovery",
                    session_id=session_id,
                    clipboard_verified=True,
                    paste_dispatched=False,
                    recovery_saved=False,
                )
            self.output_handler.acknowledge_delivery(session_id)
        self.overlay.set_actions(
            on_record_toggle=self._on_record_toggle,
            on_copy_last=self._copy_last_text,
            on_repaste_last=self._repaste_last_text,
            on_copy_text=self._copy_text,
            on_output_text=self._output_text,
            on_open_dictionary=self._open_dictionary,
            on_quit=self.shutdown,
            on_recording_painted=self._on_recording_painted,
            on_preview_painted=self._on_preview_painted,
            on_recover_session=self._recover_session,
            on_delete_recovery=self._recovery_store.delete,
            on_read_history=self.history.read_recent,
            on_delete_history=self.history.delete_entry,
            on_clear_history=self.history.clear,
        )
        self.cleaner = TextCleaner(self.config, base_dir=self.base_dir)
        print("[启动] 就绪", flush=True)

    # ---- 录音 ----

    def _on_audio_levels(self, levels):
        if self._recording_state.current is not RecordingState.RECORDING:
            return
        self.overlay.update_audio_level(levels, self._stream_generation)

    def _on_recording_painted(self, generation, elapsed_ms):
        if generation != self._stream_generation:
            return
        self._last_trigger_to_feedback_ms = float(elapsed_ms)

    def _on_preview_painted(self, generation, painted_at):
        if generation != self._stream_generation:
            return
        if self._preview_first_paint_ms is not None or self._speech_onset_at is None:
            return
        self._preview_first_paint_ms = max(
            0.0,
            (float(painted_at) - self._speech_onset_at) * 1000,
        )
        self._preview_first_text_ms = self._preview_first_paint_ms
        if self._preview_first_model_delta_at is not None:
            self._preview_queue_delay_ms = max(
                0.0,
                (float(painted_at) - self._preview_first_model_delta_at) * 1000,
            )

    def _on_record_toggle(self, triggered_at=None):
        state = self._recording_state.current
        if state is RecordingState.RECORDING:
            self._on_record_stop(triggered_at)
        elif state is RecordingState.IDLE:
            self._on_record_start(triggered_at)

    def _can_record_toggle(self):
        return self._recording_state.current in {
            RecordingState.IDLE,
            RecordingState.RECORDING,
        }

    def _on_record_start(self, triggered_at=None):
        if not self._recording_state.claim_start():
            return
        try:
            self._stream_generation += 1
            generation = self._stream_generation
            self._active_session_id = uuid.uuid4().hex
            self._target_snapshot = self.output_handler.capture_target()
            if self._recovery_enabled:
                self._recovery_journal = self._recovery_store.start_session(
                    session_id=self._active_session_id,
                    sample_rate=self.audio.sample_rate,
                    channels=getattr(self.audio, "channels", 1),
                    dtype=getattr(self.audio, "dtype", "int16"),
                    model=self._active_engine_name(),
                )
                self.audio.set_recovery_sink(self._recovery_journal)
            self._last_trigger_to_feedback_ms = None
            self.overlay.show_recording(generation, triggered_at)
            self.session.start()
            self._recording_state.mark_recording()
            if self._recovery_journal is not None:
                self._recovery_journal.mark_state("recording")
            self._latest_text = ""
            self._preview_started_at = time.perf_counter()
            self._preview_first_text_ms = None
            self._speech_onset_sample = None
            self._speech_onset_at = None
            self._preview_first_model_delta_at = None
            self._preview_first_model_delta_ms = None
            self._preview_first_paint_ms = None
            self._preview_queue_delay_ms = None
            self._preview_last_delta_at = None
            self._preview_update_gap_ms = None
            self._preview_active_speech_since_delta_ms = 0.0
            self._preview_active_speech_update_gap_ms = None
            self._preview_divergence_count = 0
            self._preview_update_count = 0
            self._preview_max_chunk_chars = 0
            self._reset_final_cache()
            self._start_streaming(generation)
            print("[录音] 开始", flush=True)
        except Exception as e:
            self.audio.set_recovery_sink(None)
            if self._recovery_journal is not None:
                self._recovery_journal.close_interrupted()
                self._recovery_journal = None
            self._recording_state.abort_start()
            self.overlay.show_error(str(e))
            logger.exception("recording start failed")
            print(f"[错误] {e}", flush=True)

    def _on_record_stop(self, triggered_at=None):
        stop_started = triggered_at if triggered_at is not None else time.perf_counter()
        finalizing_done = threading.Event()
        finalizing_timer = None
        if not self._recording_state.claim_stop():
            return

        try:
            freeze_started = time.perf_counter()
            self.session.freeze()
            audio_frozen_ms = (time.perf_counter() - freeze_started) * 1000
            stream_handoff_started = time.perf_counter()
            final_generation = self._stop_streaming()
            stream_handoff_ms = (
                time.perf_counter() - stream_handoff_started
            ) * 1000
            finalizing_timer = threading.Timer(
                self.FINALIZING_DELAY_SECONDS,
                lambda: (
                    self.overlay.show_settling(final_generation)
                    if not finalizing_done.is_set()
                    else None
                ),
            )
            finalizing_timer.daemon = True
            finalizing_timer.start()
            if self._recovery_journal is not None:
                self._recovery_journal.mark_state(
                    "finalizing",
                    preview_text=self._latest_text,
                )
            teardown_started = time.perf_counter()
            try:
                result = self.session.stop()
            finally:
                self.audio.set_recovery_sink(None)
                audio_teardown_ms = (time.perf_counter() - teardown_started) * 1000
            data = result.audio_data
            if len(data) == 0:
                if self._recovery_journal is not None:
                    self._recovery_journal.close_without_recovery()
                    self._recovery_journal = None
                self.overlay.show_canceled()
                self.overlay.hide_after(650)
                return

            cache_handoff_started = time.perf_counter()
            self._await_final_cache_handoff()
            stream_handoff_ms += (
                time.perf_counter() - cache_handoff_started
            ) * 1000

            total_samples = result.total_samples or len(data)
            duration = result.duration or (total_samples / self.audio.sample_rate)
            transcription_started = time.perf_counter()
            final_result = self._transcribe_final_result(
                data,
                buffer_start_sample=result.start_sample,
                total_samples=total_samples,
            )
            transcription_ms = (time.perf_counter() - transcription_started) * 1000
            raw_text = final_result.text
            safe_text_started = time.perf_counter()
            safe_result = self._safe_text.sanitize(raw_text)
            text = self.cleaner.clean(safe_result.text) if safe_result.text else ""
            text = self.punctuation.restore(text)
            if text and not has_lexical_content(text):
                text = ""
            safe_text_ms = (time.perf_counter() - safe_text_started) * 1000

            # Safety: if final transcription empty but streaming had text, use streaming text
            if not text and self._latest_text:
                preview_safe = self._safe_text.sanitize(self._latest_text)
                preview_text = self.cleaner.clean(preview_safe.text)
                text = preview_text if has_lexical_content(preview_text) else ""
                if text:
                    safe_result = preview_safe
                    final_result = FinalTranscriptionResult(
                        text=text,
                        captured_samples=total_samples,
                        covered_samples=final_result.covered_samples,
                        coverage_ok=False,
                        final_source="preview_safety_fallback",
                    )

            if text:
                finalizing_done.set()
                print(f"[转写] {text} ({duration:.1f}s)", flush=True)
                self.overlay.show_authoritative_final(text, final_generation)
                self._recording_state.mark_delivering()
                delivery_started = time.perf_counter()
                delivery = self.output_handler.deliver(
                    text,
                    start_target=self._target_snapshot,
                    session_id=self._active_session_id or uuid.uuid4().hex,
                    allow_paste=final_result.coverage_ok,
                )
                delivery_ms = (time.perf_counter() - delivery_started) * 1000
                timeline = FinalizationTimeline(
                    audio_frozen_ms=audio_frozen_ms,
                    audio_teardown_ms=audio_teardown_ms,
                    stream_handoff_ms=stream_handoff_ms,
                    transcription_ms=transcription_ms,
                    safe_text_ms=safe_text_ms,
                    delivery_ms=delivery_ms,
                )
                output_status = delivery.output_status
                stop_to_paste_ms = (time.perf_counter() - stop_started) * 1000
                segment_count = len(self._snapshot_final_cache()[0])
                self.history.append(
                    raw_text=raw_text,
                    clean_text=text,
                    corrected_text=text,
                    output_status=output_status,
                    duration=duration,
                    model=self._active_engine_name(),
                    segment_count=segment_count,
                    final_length=len(text),
                    captured_samples=final_result.captured_samples,
                    covered_samples=final_result.covered_samples,
                    coverage_ok=final_result.coverage_ok,
                    final_source=final_result.final_source,
                    trigger_to_feedback_ms=self._last_trigger_to_feedback_ms,
                    stop_to_paste_ms=stop_to_paste_ms,
                    audio_frozen_ms=timeline.audio_frozen_ms,
                    audio_teardown_ms=timeline.audio_teardown_ms,
                    stream_handoff_ms=timeline.stream_handoff_ms,
                    transcription_ms=timeline.transcription_ms,
                    safe_text_ms=timeline.safe_text_ms,
                    delivery_ms=timeline.delivery_ms,
                    preview_first_text_ms=self._preview_first_text_ms,
                    preview_speech_onset_sample=self._speech_onset_sample,
                    preview_first_model_delta_ms=self._preview_first_model_delta_ms,
                    preview_first_paint_ms=self._preview_first_paint_ms,
                    preview_update_gap_ms=self._preview_update_gap_ms,
                    preview_active_speech_update_gap_ms=(
                        self._preview_active_speech_update_gap_ms
                    ),
                    preview_queue_delay_ms=self._preview_queue_delay_ms,
                    preview_divergence_count=self._preview_divergence_count,
                    preview_update_count=self._preview_update_count,
                    preview_max_chunk_chars=self._preview_max_chunk_chars,
                    session_id=self._active_session_id,
                    clipboard_verified=delivery.clipboard_verified,
                    paste_dispatched=delivery.paste_dispatched,
                    recovery_saved=delivery.recovery_saved,
                    safe_text_reasons=safe_result.reasons,
                    delivery_reason=delivery.reason,
                    target_evidence=delivery.target_evidence,
                )
                self.output_handler.acknowledge_delivery(self._active_session_id)
                self.overlay.complete_onboarding()
                delivered_completely = (
                    final_result.coverage_ok
                    and delivery.clipboard_verified
                    and not delivery.recovery_saved
                )
                if delivered_completely and self._recovery_journal is not None:
                    self._recovery_journal.mark_delivered(delivery.text_sha256)
                    self._recovery_journal = None
                elif self._recovery_journal is not None:
                    self._recovery_journal.close_interrupted()
                    self._recovery_journal = None
                self.overlay.show_delivery_state(output_status, final_generation)
                self.overlay.hide_after(
                    self._delivery_hold_ms(output_status, duration)
                )
                if delivered_completely:
                    self._recording_state.mark_complete()
                else:
                    self._recording_state.mark_recoverable()
                    self._recording_state.acknowledge_recovery()
            else:
                finalizing_done.set()
                if self._recovery_journal is not None:
                    self._recovery_journal.close_interrupted()
                    self._recovery_journal = None
                self._recording_state.mark_recoverable()
                self._recording_state.acknowledge_recovery()
                self.overlay.hide_after(0)

        except Exception as e:
            finalizing_done.set()
            self.audio.set_recovery_sink(None)
            if self._recovery_journal is not None:
                self._recovery_journal.close_interrupted()
                self._recovery_journal = None
            self._recording_state.mark_error()
            self._recording_state.mark_recoverable()
            self._recording_state.acknowledge_recovery()
            self.overlay.show_error(str(e))
            self.history.append(output_status="error", error=str(e))
            logger.exception("recording finalization failed")
            import traceback
            traceback.print_exc()
        finally:
            finalizing_done.set()
            if finalizing_timer is not None:
                finalizing_timer.cancel()
            if hasattr(self, "output_handler"):
                self.output_handler.cancel_target_tracking()
            self._recording_state.complete_processing()
            self._active_session_id = None
            self._target_snapshot = None

    def _audio_sample_count(self):
        sample_count = getattr(self.audio, "sample_count", None)
        if sample_count is not None:
            return int(sample_count)
        return sum(len(block) for block in getattr(self.audio, "_audio_buffer", []))

    def _audio_buffer_start_sample(self):
        return int(getattr(self.audio, "buffer_start_sample", 0))

    def _audio_snapshot(self, start_sample, end_sample):
        snapshot = getattr(self.audio, "snapshot_audio", None)
        if snapshot is not None:
            return snapshot(start_sample, end_sample)
        blocks = getattr(self.audio, "_audio_buffer", [])
        if not blocks:
            return np.array([], dtype=np.int16)
        chunk = np.concatenate(tuple(blocks), axis=0).flatten()
        return chunk[max(0, start_sample):max(0, end_sample)].copy()

    def _append_preview_delta(self, delta, generation):
        if generation != self._stream_generation:
            return
        delta = str(delta or "")
        if not delta:
            return
        now = time.perf_counter()
        if (
            self._preview_first_model_delta_ms is None
            and self._speech_onset_at is not None
        ):
            self._preview_first_model_delta_at = now
            self._preview_first_model_delta_ms = max(
                0.0,
                (now - self._speech_onset_at) * 1000,
            )
        if self._preview_last_delta_at is not None:
            gap_ms = (
                now - self._preview_last_delta_at
            ) * 1000
            self._preview_update_gap_ms = max(
                gap_ms,
                self._preview_update_gap_ms or 0.0,
            )
            active_gap_ms = float(
                getattr(self, "_preview_active_speech_since_delta_ms", 0.0)
            )
            self._preview_active_speech_update_gap_ms = max(
                active_gap_ms,
                self._preview_active_speech_update_gap_ms or 0.0,
            )
        self._preview_active_speech_since_delta_ms = 0.0
        self._preview_last_delta_at = now
        self._preview_update_count += 1
        self._preview_max_chunk_chars = max(
            self._preview_max_chunk_chars,
            len(delta),
        )
        self.overlay.append_streaming(delta, generation)

    def _feed_preview_audio(
        self,
        preview,
        preview_session,
        next_sample,
        generation,
    ):
        total_samples = self._audio_sample_count()
        if total_samples <= next_sample:
            return next_sample
        new_audio = self._audio_snapshot(next_sample, total_samples)
        if not len(new_audio):
            return next_sample
        normalized = np.asarray(new_audio, dtype=np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(normalized)))) if len(normalized) else 0.0
        if rms >= getattr(self, "_speech_rms_threshold", 0.002):
            self._preview_active_speech_since_delta_ms = float(
                getattr(self, "_preview_active_speech_since_delta_ms", 0.0)
            ) + len(new_audio) / self.audio.sample_rate * 1000.0
        if getattr(self, "_speech_onset_sample", None) is None:
            onset = find_speech_onset(
                new_audio,
                self.audio.sample_rate,
                rms_threshold=getattr(self, "_speech_rms_threshold", 0.002),
                min_active_ms=getattr(self, "_speech_min_active_ms", 90),
            )
            if onset is not None:
                self._speech_onset_sample = next_sample + onset
                if self._preview_started_at is not None:
                    self._speech_onset_at = (
                        self._preview_started_at
                        + self._speech_onset_sample / self.audio.sample_rate
                    )
        update = preview.accept_pcm(
            preview_session,
            new_audio,
            self.audio.sample_rate,
        )
        next_sample += len(new_audio)
        if update.text:
            self._latest_text = preview_session.committed_text
        if update.endpoint_final:
            self._note_preview_endpoint(update.audio_end_sample)
        if update.hypothesis_diverged:
            self._preview_divergence_count += 1
        if generation == self._stream_generation and update.delta:
            self._append_preview_delta(update.delta, generation)
        return next_sample

    def _reset_final_cache(self):
        with self._final_cache_lock:
            self._final_segments = []
            self._finalized_audio_len = 0
        endpoint_lock = getattr(self, "_preview_endpoint_lock", None)
        if endpoint_lock is not None:
            with endpoint_lock:
                self._preview_endpoint_samples = []
        idle = getattr(self, "_final_cache_idle", None)
        if idle is not None:
            idle.set()

    def _await_final_cache_handoff(self):
        idle = getattr(self, "_final_cache_idle", None)
        if idle is None:
            return True
        completed = idle.wait(self.FINAL_CACHE_HANDOFF_TIMEOUT_SECONDS)
        if not completed:
            logger.warning("progressive final cache handoff timed out")
        return completed

    def _next_final_segment(self, chunk, finalized_audio_len):
        segment_range = self._next_final_segment_range(len(chunk), finalized_audio_len)
        if segment_range is None:
            return None, finalized_audio_len
        start, end = segment_range
        return chunk[start:end], end

    def _next_final_segment_range(self, total_samples, finalized_audio_len):
        segment_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_SECONDS)
        overlap_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_OVERLAP_SECONDS)
        hold_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_HOLD_SECONDS)
        stable_len = max(0, total_samples - hold_samples)
        endpoint = self._next_stable_endpoint(finalized_audio_len, stable_len)
        if endpoint is not None:
            start = max(0, finalized_audio_len - overlap_samples)
            return start, endpoint
        if segment_samples <= 0 or stable_len - finalized_audio_len < segment_samples:
            return None
        start = max(0, finalized_audio_len - overlap_samples)
        end = finalized_audio_len + segment_samples
        return start, end

    def _note_preview_endpoint(self, sample_index):
        sample_index = max(0, int(sample_index))
        lock = getattr(self, "_preview_endpoint_lock", None)
        if lock is None:
            return
        with lock:
            if not self._preview_endpoint_samples or sample_index > self._preview_endpoint_samples[-1]:
                self._preview_endpoint_samples.append(sample_index)
                if len(self._preview_endpoint_samples) > self.PREVIEW_ENDPOINT_LIMIT:
                    del self._preview_endpoint_samples[:-self.PREVIEW_ENDPOINT_LIMIT]

    def _consume_preview_endpoint(self, sample_index):
        lock = getattr(self, "_preview_endpoint_lock", None)
        if lock is None:
            return False
        sample_index = int(sample_index)
        with lock:
            natural_endpoint = sample_index in self._preview_endpoint_samples
            self._preview_endpoint_samples = [
                value for value in self._preview_endpoint_samples
                if value > sample_index
            ]
        return natural_endpoint

    def _next_stable_endpoint(self, finalized_audio_len, stable_len):
        lock = getattr(self, "_preview_endpoint_lock", None)
        if lock is None:
            return None
        minimum = finalized_audio_len + int(self.audio.sample_rate * 2.0)
        maximum = min(
            stable_len,
            finalized_audio_len + int(self.audio.sample_rate * self.FINAL_SEGMENT_SECONDS),
        )
        with lock:
            candidates = [
                value for value in self._preview_endpoint_samples
                if minimum <= value <= maximum
            ]
        return candidates[-1] if candidates else None

    @staticmethod
    def _segment_text(segment):
        return segment.text if isinstance(segment, FinalSegmentCoverage) else str(segment)

    def _append_final_segment(self, text, finalized_audio_len):
        self._commit_final_segment(
            text,
            max(0, finalized_audio_len - int(self.audio.sample_rate * self.FINAL_SEGMENT_SECONDS)),
            finalized_audio_len,
            bool(text and text.strip()),
        )

    def _commit_final_segment(self, text, start_sample, end_sample, speech):
        with self._final_cache_lock:
            self._final_segments.append(
                FinalSegmentCoverage(
                    start_sample=max(0, int(start_sample)),
                    end_sample=max(0, int(end_sample)),
                    text=(text or "").strip(),
                    speech=bool(speech),
                )
            )
            self._finalized_audio_len = max(self._finalized_audio_len, int(end_sample))

    def _snapshot_final_cache(self, tail_parts=None):
        lock = getattr(self, "_final_cache_lock", None)
        if lock is None:
            parts = list(getattr(self, "_final_segments", []))
            if tail_parts is not None:
                parts = parts[-tail_parts:]
            return parts, getattr(self, "_finalized_audio_len", 0)
        with lock:
            parts = self._final_segments if tail_parts is None else self._final_segments[-tail_parts:]
            return list(parts), self._finalized_audio_len

    def _join_transcript_parts(self, parts):
        joined = ""
        for part in parts:
            part = (part or "").strip()
            if not part:
                continue
            joined = self._merge_transcript_pair(joined, part) if joined else part
        return joined.strip()

    def _merge_transcript_pair(self, left, right):
        left = (left or "").rstrip()
        right = (right or "").lstrip()
        if not left:
            return right
        if not right:
            return left
        max_overlap = min(len(left), len(right), 80)
        for size in range(max_overlap, 1, -1):
            if left[-size:] == right[:size]:
                return left + right[size:]

        def normalized(value):
            chars = []
            raw_ends = []
            for index, char in enumerate(value):
                if char.isalnum() or "\u3400" <= char <= "\u9fff":
                    chars.append(char.casefold())
                    raw_ends.append(index + 1)
            return chars, raw_ends

        left_chars, _ = normalized(left)
        right_chars, right_ends = normalized(right)
        max_normalized_overlap = min(len(left_chars), len(right_chars), 80)
        for size in range(max_normalized_overlap, 1, -1):
            if left_chars[-size:] == right_chars[:size]:
                return left + right[right_ends[size - 1]:]
        return f"{left} {right}"

    def _should_use_segmented_final(
        self,
        data,
        segments,
        finalized_audio_len,
        *,
        buffer_start_sample=0,
        total_samples=None,
    ):
        total_samples = len(data) if total_samples is None else total_samples
        duration = total_samples / self.audio.sample_rate
        return (
            duration >= self.SEGMENTED_FINAL_MIN_SECONDS
            and bool(segments)
            and buffer_start_sample <= finalized_audio_len <= total_samples
        )

    def _segment_coverage_end(self, segments):
        covered_until = 0
        previous_start = -1
        for segment in segments:
            if segment.end_sample <= segment.start_sample:
                return 0, False
            if segment.start_sample < previous_start:
                return covered_until, False
            if segment.start_sample > covered_until:
                return covered_until, False
            if segment.speech and not segment.text:
                return covered_until, False
            previous_start = segment.start_sample
            covered_until = max(covered_until, segment.end_sample)
        return covered_until, True

    def _transcribe_complete_pcm(self, data, total_samples, source):
        text = self._transcribe_audio(data) or ""
        covered_samples = len(data)
        coverage_ok = covered_samples == total_samples
        return FinalTranscriptionResult(
            text=text,
            captured_samples=total_samples,
            covered_samples=covered_samples,
            coverage_ok=coverage_ok,
            final_source=source,
        )

    def _transcribe_final_result(self, data, *, buffer_start_sample=0, total_samples=None):
        total_samples = len(data) if total_samples is None else total_samples
        segments, finalized_audio_len = self._snapshot_final_cache()
        if self._should_use_segmented_final(
            data,
            segments,
            finalized_audio_len,
            buffer_start_sample=buffer_start_sample,
            total_samples=total_samples,
        ):
            covered_until, segments_ok = self._segment_coverage_end(segments)
            full_pcm_available = buffer_start_sample == 0 and len(data) == total_samples
            if not segments_ok or covered_until < finalized_audio_len:
                if full_pcm_available:
                    return self._transcribe_complete_pcm(
                        data,
                        total_samples,
                        "full_pcm_fallback",
                    )
                return FinalTranscriptionResult(
                    text="",
                    captured_samples=total_samples,
                    covered_samples=covered_until,
                    coverage_ok=False,
                    final_source="coverage_failed",
                )

            overlap_samples = int(self.audio.sample_rate * self.FINAL_SEGMENT_OVERLAP_SECONDS)
            tail_start = max(buffer_start_sample, finalized_audio_len - overlap_samples)
            tail = data[tail_start - buffer_start_sample:]
            tail_end = buffer_start_sample + len(data)
            tail_has_speech = self._contains_speech(tail) if len(tail) else False
            tail_text = (
                self._transcribe_audio(tail, activity_checked=True)
                if tail_has_speech else ""
            )
            parts = [self._segment_text(segment) for segment in segments]
            text = self._join_transcript_parts(parts + [tail_text])
            committed = getattr(self, "_latest_text", "")
            suspiciously_short = (
                bool(committed)
                and len(text) < max(1, int(len(committed) * 0.65))
            )
            if (
                (tail_has_speech and not tail_text)
                or (not text and any(segment.speech for segment in segments))
                or suspiciously_short
            ):
                if full_pcm_available:
                    return self._transcribe_complete_pcm(
                        data,
                        total_samples,
                        "full_pcm_fallback",
                    )
            tail_contiguous = tail_start <= covered_until
            covered_samples = (
                min(total_samples, tail_end)
                if tail_contiguous
                else min(total_samples, covered_until)
            )
            return FinalTranscriptionResult(
                text=text,
                captured_samples=total_samples,
                covered_samples=covered_samples,
                coverage_ok=covered_samples == total_samples,
                final_source="segments_plus_tail",
            )

        source = "full_pcm" if buffer_start_sample == 0 else "incomplete_pcm"
        result = self._transcribe_complete_pcm(data, total_samples, source)
        if (
            not result.text
            and buffer_start_sample == 0
            and getattr(self, "_latest_text", "")
        ):
            result = self._transcribe_complete_pcm(
                data,
                total_samples,
                "full_pcm_retry",
            )
        return result

    def _transcribe_final_text(self, data, *, buffer_start_sample=0, total_samples=None):
        return self._transcribe_final_result(
            data,
            buffer_start_sample=buffer_start_sample,
            total_samples=total_samples,
        ).text

    def _contains_speech(self, audio_data):
        if (
            getattr(self, "_speech_gate_enabled", False)
            and not has_speech_activity(
                audio_data,
                self.audio.sample_rate,
                rms_threshold=self._speech_rms_threshold,
                min_active_ms=self._speech_min_active_ms,
            )
        ):
            return False
        detector = getattr(self, "_speech_detector", None)
        if detector is not None and not detector.has_speech(
            audio_data,
            self.audio.sample_rate,
        ):
            return False
        return True

    def _transcribe_audio(self, audio_data, *, blocking=True, activity_checked=False):
        if not activity_checked and not self._contains_speech(audio_data):
            return ""
        lock = getattr(self, "_transcribe_lock", None)
        if lock is None:
            return self.transcriber.transcribe(audio_data, self.audio.sample_rate)
        acquired = lock.acquire(blocking=blocking)
        if not acquired:
            return None
        try:
            return self.transcriber.transcribe(audio_data, self.audio.sample_rate)
        finally:
            lock.release()

    def _delivery_hold_ms(self, output_status, _duration):
        if output_status == "clipboard_verified_paste_dispatched":
            return self.SUCCESS_DISMISS_MS
        if output_status == "clipboard_verified_only":
            return self.CLIPBOARD_ONLY_HOLD_MS
        if output_status == "recovery_saved_clipboard_unavailable":
            return self.RECOVERY_SAVED_HOLD_MS
        return self.CLIPBOARD_ONLY_HOLD_MS

    def _active_engine_name(self):
        return self.config.get("engine", {}).get("active", "sensevoice")

    def _start_streaming(self, generation):
        """Start independent online preview and progressive final-cache workers."""
        self._streaming = True
        stop_event = threading.Event()
        self._stream_stop_event = stop_event
        preview = getattr(self, "preview_transcriber", None)
        preview_session = preview.create_session() if preview is not None else None

        def preview_loop():
            next_sample = 0
            if preview is None or preview_session is None:
                return
            while not stop_event.is_set():
                try:
                    next_sample = self._feed_preview_audio(
                        preview,
                        preview_session,
                        next_sample,
                        generation,
                    )
                except Exception:
                    logger.exception("real-time streaming preview failed")
                    return
                stop_event.wait(self.STREAM_PREVIEW_POLL_SECONDS)

        def final_cache_loop():
            while not stop_event.is_set():
                try:
                    total_samples = self._audio_sample_count()
                    _, finalized_len = self._snapshot_final_cache()
                    segment_range = self._next_final_segment_range(
                        total_samples,
                        finalized_len,
                    )
                    if segment_range is not None:
                        with self._final_cache_state_lock:
                            if stop_event.is_set():
                                break
                            self._final_cache_idle.clear()
                        try:
                            segment_start, segment_end = segment_range
                            segment = self._audio_snapshot(segment_start, segment_end)
                            has_speech = self._contains_speech(segment)
                            segment_text = (
                                self._transcribe_audio(
                                    segment,
                                    blocking=False,
                                    activity_checked=True,
                                )
                                if has_speech else ""
                            )
                            if segment_text is not None and (
                                not has_speech or segment_text
                            ):
                                natural_endpoint = self._consume_preview_endpoint(
                                    segment_end
                                )
                                self._commit_final_segment(
                                    segment_text,
                                    segment_start,
                                    segment_end,
                                    has_speech,
                                )
                                segments, covered_to = self._snapshot_final_cache()
                                authoritative = self._join_transcript_parts(
                                    [self._segment_text(item) for item in segments]
                                )
                                if (
                                    natural_endpoint
                                    and authoritative
                                    and generation == self._stream_generation
                                ):
                                    self.overlay.update_transcript_state(
                                        TranscriptViewState(
                                            session_id=generation,
                                            authoritative_prefix=authoritative,
                                            covered_start_sample=0,
                                            covered_end_sample=covered_to,
                                        )
                                    )
                        finally:
                            self._final_cache_idle.set()
                except Exception:
                    logger.exception("progressive final cache failed")
                stop_event.wait(0.08)

        self._stream_thread = threading.Thread(target=preview_loop, daemon=True)
        self._final_cache_thread = threading.Thread(target=final_cache_loop, daemon=True)
        self._stream_thread.start()
        self._final_cache_thread.start()

    def _stop_streaming(self):
        self._streaming = False
        stop_event = getattr(self, "_stream_stop_event", None)
        if stop_event is not None:
            with self._final_cache_state_lock:
                stop_event.set()
        self._stream_generation += 1
        final_generation = self._stream_generation
        self._stream_thread = None
        self._final_cache_thread = None
        if getattr(self, "_stream_stop_event", None) is stop_event:
            self._stream_stop_event = None
        return final_generation

    def _final_text_from_cache(self):
        raw_text = (self._latest_text or "").strip()
        if not raw_text:
            return "", "", False
        return raw_text, self.cleaner.clean(raw_text), True

    def _on_record_cancel(self):
        should_cancel = self._recording_state.claim_cancel()
        if should_cancel:
            self._stop_streaming()
            self.session.cancel()
            self.audio.set_recovery_sink(None)
            if self._recovery_journal is not None:
                self._recovery_journal.close_without_recovery()
                self._recovery_journal = None
            self._active_session_id = None
            self._target_snapshot = None
            if hasattr(self, "output_handler"):
                self.output_handler.cancel_target_tracking()
            self.overlay.show_canceled()
            self.overlay.hide_after(800)
        print("[录音] 已取消", flush=True)

    def _copy_last_text(self):
        last = self.history.last()
        text = (last.get("corrected_text") or last.get("clean_text", "")) if last else ""
        if text:
            status = self._copy_text(text)
            message = "已复制" if status == "clipboard_verified_only" else "复制失败"
            self.overlay.show_result(message)
            self.overlay.hide_after(1200)

    def _repaste_last_text(self):
        last = self.history.last()
        text = (last.get("corrected_text") or last.get("clean_text", "")) if last else ""
        self._output_text(text)

    def _output_text(self, text):
        if text and hasattr(self, "output_handler"):
            return self.output_handler.output(text)
        return "empty"

    def _copy_text(self, text):
        if text and hasattr(self, "output_handler"):
            return self.output_handler.copy_only(text)
        return "empty"

    def _recover_session(self, session_id):
        if self._recording_state.current is not RecordingState.IDLE:
            return {"ok": False, "error": "请先结束当前听写"}
        audio = self._recovery_store.read_pcm(session_id)
        if not len(audio):
            return {"ok": False, "error": "恢复录音不存在或为空"}
        raw_text = self._transcribe_audio(audio, activity_checked=False)
        safe = self._safe_text.sanitize(raw_text or "")
        if safe.rejected or not safe.text:
            return {"ok": False, "error": "没有得到可信文字，录音已继续保留"}
        text = self.cleaner.clean(safe.text)
        delivery = self.output_handler.deliver(
            text,
            start_target=None,
            session_id=f"recovered-{session_id}",
            allow_paste=False,
        )
        if not delivery.clipboard_verified:
            return {"ok": False, "error": "剪贴板暂时不可用，录音已继续保留"}
        self.history.append(
            raw_text=raw_text,
            clean_text=text,
            corrected_text=text,
            output_status=delivery.output_status,
            model=self._active_engine_name(),
            captured_samples=len(audio),
            covered_samples=len(audio),
            coverage_ok=True,
            final_source="recovered_pcm",
            session_id=session_id,
            clipboard_verified=True,
            paste_dispatched=False,
            recovery_saved=False,
            safe_text_reasons=safe.reasons,
        )
        self.output_handler.acknowledge_delivery(f"recovered-{session_id}")
        self._recovery_store.delete(session_id)
        return {"ok": True, "text": text, "output_status": delivery.output_status}

    def _open_dictionary(self):
        open_path(self.paths.knowledge_dir)

    # ---- 生命周期 ----

    def start(self):
        ptt_raw = self.config.get("hotkeys", {}).get("push_to_talk", "f2")
        if isinstance(ptt_raw, list):
            ptt = " / ".join(k.upper() for k in ptt_raw)
        else:
            ptt = ptt_raw.upper()
        engine = self.config.get("engine", {}).get("active", "sensevoice")
        print(f"\n  VoiceFlow | {engine} | {ptt.upper()}=录音/停止  Esc=取消\n", flush=True)

        self._install_console_handler()
        self.overlay.start(on_ready=self._on_overlay_ready)
        self.shutdown()

    def _install_console_handler(self):
        if os.name != "nt":
            return
        try:
            import ctypes

            handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            def handler(_ctrl_type):
                self.shutdown()
                return False

            self._console_handler_ref = handler_type(handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_handler_ref, True)
        except Exception:
            pass

    def _on_overlay_ready(self):
        from qt_compat import QTimer

        self.overlay.show_startup_window()

        def on_done():
            try:
                self._start_hotkeys()
                recoverable = self._recovery_store.list_recoverable()
                if recoverable:
                    self.overlay.show_recovery_available(len(recoverable))
                else:
                    self.overlay.show_idle()
                print("  说点什么吧", flush=True)
            except Exception as e:
                print(f"[错误] {e}", flush=True)
                self.overlay.show_error("快捷键不可用，请从托盘菜单开始听写")

        def on_error(e):
            import traceback
            traceback.print_exc()

        QTimer.singleShot(100, lambda: _InitWorker(self, on_done, on_error).start())

    def _start_hotkeys(self):
        self.hotkey_mgr = HotkeyManager(
            config_path=self.config_path,
            callbacks={
                "on_record_toggle": self._on_record_toggle,
                "can_record_toggle": self._can_record_toggle,
                "on_record_cancel": self._on_record_cancel,
            },
        )
        self.hotkey_mgr.start()

    def shutdown(self):
        if self._shutdown_started:
            return
        self._shutdown_started = True

        self._stop_streaming()
        previous_state = self._recording_state.shutdown()
        if previous_state is RecordingState.RECORDING and hasattr(self, "session"):
            try:
                self.session.cancel()
            except Exception:
                pass

        if hasattr(self, "hotkey_mgr"):
            self.hotkey_mgr.stop()
        if hasattr(self, "output_handler"):
            self.output_handler.shutdown()
        print("\n[系统] 已退出", flush=True)


# ---- 测试 ----

def test_mode(config_path):
    paths = AppPaths.discover(config_path=config_path)
    prepare_runtime_layout(paths)
    config_path = str(paths.config_file)
    print("\n=== 测试模式 ===")
    audio = AudioCapture(config_path)
    transcriber = Transcriber(config_path, asset_roots=paths.asset_roots)
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    engine = config.get("engine", {}).get("active", "sensevoice")
    print(f"引擎: {engine}")
    transcriber.load_engine(engine)

    for i in [3, 2, 1]:
        print(f"{i}...")
        time.sleep(1)
    print("开始!")
    audio.start_recording()
    time.sleep(5)
    data = audio.stop_recording()
    if len(data) == 0:
        print("无音频")
        return
    d = len(data) / audio.sample_rate
    print(f"录音: {d:.1f}s, 转写中...")
    t0 = time.time()
    text = transcriber.transcribe(data, audio.sample_rate)
    print(f"结果: {text}")
    print(f"耗时: {time.time()-t0:.2f}s, RTF: {(time.time()-t0)/d:.3f}")


def runtime_smoke(config_path=None):
    """Headless packaged-runtime contract used by platform build jobs."""
    from runtime_services import run_runtime_diagnostics

    paths = AppPaths.discover(config_path=config_path)
    migration = prepare_runtime_layout(paths)
    diagnostics = run_runtime_diagnostics(paths)
    payload = {
        "ok": diagnostics["ok"],
        "runtime_mode": paths.mode.value,
        "schema_version": migration.schema_version,
        "checks": diagnostics["checks"],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if diagnostics["ok"] else 1


def main():
    p = argparse.ArgumentParser(description="VoiceFlow")
    p.add_argument("--test", action="store_true")
    p.add_argument("--runtime-smoke", action="store_true")
    p.add_argument("--config", default=None)
    args = p.parse_args()

    if args.runtime_smoke:
        raise SystemExit(runtime_smoke(args.config))
    if args.test:
        config_path = args.config or os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config.yaml",
        )
        test_mode(config_path)
    else:
        VoiceInputSystem(args.config).start()


if __name__ == "__main__":
    main()
