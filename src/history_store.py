"""
Append-only local transcription history.
"""

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()

    @staticmethod
    def _entry_id(line):
        return hashlib.sha256(line.encode("utf-8")).hexdigest()

    def _write_lines_atomic(self, lines):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        content = "\n".join(lines)
        if content:
            content += "\n"
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

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
        audio_teardown_ms=None,
        stream_handoff_ms=None,
        transcription_ms=None,
        safe_text_ms=None,
        delivery_ms=None,
        preview_first_text_ms=None,
        preview_speech_onset_sample=None,
        preview_first_model_delta_ms=None,
        preview_first_paint_ms=None,
        preview_update_gap_ms=None,
        preview_active_speech_update_gap_ms=None,
        preview_queue_delay_ms=None,
        preview_divergence_count=None,
        preview_update_count=None,
        preview_max_chunk_chars=None,
        session_id=None,
        clipboard_verified=None,
        paste_dispatched=None,
        landed_confirmed=None,
        recovery_saved=None,
        safe_text_reasons=None,
        delivery_reason="",
        target_evidence="",
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
        if audio_teardown_ms is not None:
            entry["audio_teardown_ms"] = round(float(audio_teardown_ms), 3)
        if stream_handoff_ms is not None:
            entry["stream_handoff_ms"] = round(float(stream_handoff_ms), 3)
        if transcription_ms is not None:
            entry["transcription_ms"] = round(float(transcription_ms), 3)
        if safe_text_ms is not None:
            entry["safe_text_ms"] = round(float(safe_text_ms), 3)
        if delivery_ms is not None:
            entry["delivery_ms"] = round(float(delivery_ms), 3)
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
        if preview_active_speech_update_gap_ms is not None:
            entry["preview_active_speech_update_gap_ms"] = round(
                float(preview_active_speech_update_gap_ms),
                3,
            )
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
        if landed_confirmed is not None:
            entry["landed_confirmed"] = bool(landed_confirmed)
        if recovery_saved is not None:
            entry["recovery_saved"] = bool(recovery_saved)
        if safe_text_reasons is not None:
            entry["safe_text_reasons"] = list(safe_text_reasons)
        if delivery_reason:
            entry["delivery_reason"] = str(delivery_reason)
        if target_evidence:
            entry["target_evidence"] = str(target_evidence)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        return entry

    def _iter_lines_reverse(self):
        try:
            stream = self.path.open("rb")
        except FileNotFoundError:
            return
        with stream:
            stream.seek(0, os.SEEK_END)
            position = stream.tell()
            tail = []
            while position:
                size = min(position, 64 * 1024)
                position -= size
                stream.seek(position)
                parts = stream.read(size).split(b"\n")
                tail.append(parts[-1])
                if len(parts) > 1:
                    yield b"".join(reversed(tail)).rstrip(b"\r")
                    for part in reversed(parts[1:-1]):
                        yield part.rstrip(b"\r")
                    tail = [parts[0]]
            if tail:
                yield b"".join(reversed(tail)).rstrip(b"\r")

    @staticmethod
    def _parse_line(line):
        try:
            text = line.decode("utf-8")
            record = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return (text, record) if isinstance(record, dict) else None

    def read_recent(self, limit=80):
        limit = max(0, int(limit))
        if not limit:
            return []
        rows = []
        seen = 0
        with self._lock:
            for line in self._iter_lines_reverse():
                if not line:
                    continue
                seen += 1
                parsed = self._parse_line(line)
                if parsed is not None:
                    text, record = parsed
                    record["_entry_id"] = self._entry_id(text)
                    rows.append(record)
                if seen >= limit:
                    break
        return rows

    def delete_entry(self, entry_id):
        return bool(self.delete_entry_with_undo(entry_id))

    def find_entry(self, entry_id):
        expected = str(entry_id or "")
        if not expected:
            return None
        with self._lock:
            for line in self._iter_lines_reverse():
                parsed = self._parse_line(line)
                if parsed is not None and self._entry_id(parsed[0]) == expected:
                    return parsed[1]
        return None

    def _read_lines(self):
        lines = self.path.read_text(encoding="utf-8").split("\n")
        if lines and not lines[-1]:
            lines.pop()
        return lines

    def delete_entry_with_undo(self, entry_id):
        expected = str(entry_id or "")
        if not expected or not self.path.exists():
            return None
        with self._lock:
            lines = self._read_lines()
            for index in range(len(lines) - 1, -1, -1):
                if self._entry_id(lines[index]) != expected:
                    continue
                line = lines.pop(index)
                self._write_lines_atomic(lines)
                return {"line": line, "index": index}
        return None

    def restore_entry(self, token):
        if not isinstance(token, dict):
            return False
        line = token.get("line")
        try:
            index = int(token.get("index", -1))
            record = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if index < 0 or not isinstance(record, dict):
            return False
        with self._lock:
            lines = (
                self._read_lines()
                if self.path.exists()
                else []
            )
            if any(self._entry_id(existing) == self._entry_id(line) for existing in lines):
                return False
            lines.insert(min(index, len(lines)), line)
            self._write_lines_atomic(lines)
        return True

    def clear(self):
        if not self.path.exists():
            return 0
        with self._lock:
            lines = [
                line
                for line in self._read_lines()
                if line
            ]
            self._write_lines_atomic([])
        return len(lines)

    def last(self):
        with self._lock:
            for line in self._iter_lines_reverse():
                parsed = self._parse_line(line)
                if parsed is not None:
                    return parsed[1]
        return None

    def has_session_id(self, session_id):
        expected = str(session_id)
        with self._lock:
            for line in self._iter_lines_reverse():
                parsed = self._parse_line(line)
                if parsed is not None and str(parsed[1].get("session_id", "")) == expected:
                    return True
        return False
