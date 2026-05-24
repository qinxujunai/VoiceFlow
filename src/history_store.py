"""
Append-only local transcription history.
"""

import json
from datetime import datetime
from pathlib import Path


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)

    def append(self, raw_text="", clean_text="", corrected_text="", output_status="unknown", error=""):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "raw_text": raw_text or "",
            "clean_text": clean_text or "",
            "corrected_text": corrected_text or "",
            "output_status": output_status or "unknown",
            "error": error or "",
        }
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
