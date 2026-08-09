"""
Append-only local transcription history.
"""

import json
from datetime import datetime
from pathlib import Path


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)

    def append(
        self,
        raw_text="",
        clean_text="",
        corrected_text="",
        output_status="unknown",
        error="",
        duration=None,
        model="",
        segment_count=None,
        final_length=None,
        captured_samples=None,
        covered_samples=None,
        coverage_ok=None,
        final_source="",
        trigger_to_feedback_ms=None,
        stop_to_paste_ms=None,
        audio_frozen_ms=None,
        transcription_ms=None,
        preview_first_text_ms=None,
        preview_speech_onset_sample=None,
        preview_first_model_delta_ms=None,
        preview_first_paint_ms=None,
        preview_update_gap_ms=None,
        preview_queue_delay_ms=None,
        preview_divergence_count=None,
        preview_update_count=None,
        preview_max_chunk_chars=None,
        session_id=None,
        clipboard_verified=None,
        paste_dispatched=None,
        recovery_saved=None,
        safe_text_reasons=None,
    ):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "raw_text": raw_text or "",
            "clean_text": clean_text or "",
            "corrected_text": corrected_text or "",
            "output_status": output_status or "unknown",
            "error": error or "",
        }
        if duration is not None:
            entry["duration"] = round(float(duration), 3)
        if model:
            entry["model"] = model
        if segment_count is not None:
            entry["segment_count"] = int(segment_count)
        if final_length is not None:
            entry["final_length"] = int(final_length)
        if captured_samples is not None:
            entry["captured_samples"] = int(captured_samples)
        if covered_samples is not None:
            entry["covered_samples"] = int(covered_samples)
        if coverage_ok is not None:
            entry["coverage_ok"] = bool(coverage_ok)
        if final_source:
            entry["final_source"] = final_source
        if trigger_to_feedback_ms is not None:
            entry["trigger_to_feedback_ms"] = round(float(trigger_to_feedback_ms), 3)
        if stop_to_paste_ms is not None:
            entry["stop_to_paste_ms"] = round(float(stop_to_paste_ms), 3)
        if audio_frozen_ms is not None:
            entry["audio_frozen_ms"] = round(float(audio_frozen_ms), 3)
        if transcription_ms is not None:
            entry["transcription_ms"] = round(float(transcription_ms), 3)
        if preview_first_text_ms is not None:
            entry["preview_first_text_ms"] = round(float(preview_first_text_ms), 3)
        if preview_speech_onset_sample is not None:
            entry["preview_speech_onset_sample"] = int(preview_speech_onset_sample)
        if preview_first_model_delta_ms is not None:
            entry["preview_first_model_delta_ms"] = round(
                float(preview_first_model_delta_ms),
                3,
            )
        if preview_first_paint_ms is not None:
            entry["preview_first_paint_ms"] = round(
                float(preview_first_paint_ms),
                3,
            )
        if preview_update_gap_ms is not None:
            entry["preview_update_gap_ms"] = round(float(preview_update_gap_ms), 3)
        if preview_queue_delay_ms is not None:
            entry["preview_queue_delay_ms"] = round(
                float(preview_queue_delay_ms),
                3,
            )
        if preview_divergence_count is not None:
            entry["preview_divergence_count"] = int(preview_divergence_count)
        if preview_update_count is not None:
            entry["preview_update_count"] = int(preview_update_count)
        if preview_max_chunk_chars is not None:
            entry["preview_max_chunk_chars"] = int(preview_max_chunk_chars)
        if session_id is not None:
            entry["session_id"] = str(session_id)
        if clipboard_verified is not None:
            entry["clipboard_verified"] = bool(clipboard_verified)
        if paste_dispatched is not None:
            entry["paste_dispatched"] = bool(paste_dispatched)
        if recovery_saved is not None:
            entry["recovery_saved"] = bool(recovery_saved)
        if safe_text_reasons is not None:
            entry["safe_text_reasons"] = list(safe_text_reasons)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def last(self):
        if not self.path.exists():
            return None
        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        if not lines:
            return None
        return json.loads(lines[-1])

    def has_session_id(self, session_id):
        expected = str(session_id)
        if not self.path.exists():
            return False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                if str(json.loads(line).get("session_id", "")) == expected:
                    return True
            except (json.JSONDecodeError, AttributeError):
                continue
        return False
