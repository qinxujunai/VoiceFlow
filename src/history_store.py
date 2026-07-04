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
        final_tail="",
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
        if final_tail:
            entry["final_tail"] = final_tail
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
