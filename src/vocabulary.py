"""
Personal vocabulary and correction loading for VoiceFlow.
"""

from pathlib import Path


DEFAULT_FILES = [
    "builtin-ai.txt",
    "corrections.txt",
    "user-dictionary.txt",
    "phrases.txt",
]


class Vocabulary:
    def __init__(self, base_dir, files=None, directory="knowledge-base"):
        self.base_dir = Path(base_dir)
        self.directory = self.base_dir / directory
        self.files = files or DEFAULT_FILES
        self.terms = set()
        self.corrections = {}
        self.reload()

    def reload(self):
        self.terms = set()
        self.corrections = {}
        for filename in self.files:
            path = self.directory / filename
            if not path.exists():
                continue
            for line in _read_entries(path):
                self._load_line(line)
        return self

    def add_correction(self, wrong, correct):
        wrong = (wrong or "").strip()
        correct = (correct or "").strip()
        if not wrong or not correct:
            return
        self.corrections[wrong] = correct
        path = self.directory / "corrections.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{wrong}={correct}\n")

    def apply_corrections(self, text):
        if not text:
            return text
        for wrong, correct in sorted(self.corrections.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(wrong, correct)
        return text

    def _load_line(self, line):
        if "=" in line:
            wrong, correct = line.split("=", 1)
            wrong = wrong.strip()
            correct = correct.strip()
            if wrong and correct:
                self.corrections[wrong] = correct
                self.terms.add(correct)
            return

        word = line.split("/", 1)[0].strip()
        if word:
            self.terms.add(word)


def _read_entries(path):
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                yield line
