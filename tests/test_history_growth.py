import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from history_store import HistoryStore


def test_recent_history_does_not_read_or_allocate_the_unrelated_prefix(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        for index in range(10000):
            stream.write(json.dumps({"session_id": str(index), "corrected_text": "fixture " * 40}) + "\n")
    original_read = Path.read_text

    def forbid_full_read(candidate, *args, **kwargs):
        if candidate == path:
            raise AssertionError("recent history read the entire unrelated prefix")
        return original_read(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_full_read)
    store = HistoryStore(path)
    rows = store.read_recent(80)
    assert [row["session_id"] for row in rows] == [str(index) for index in range(9999, 9919, -1)]
    assert store.last()["session_id"] == "9999"
    assert store.has_session_id("9999")
    assert not store.has_session_id("missing")


def test_zero_and_negative_history_limits_never_expose_all_history(tmp_path):
    store = HistoryStore(tmp_path / "history.jsonl")
    store.append(corrected_text="fixture")
    assert store.read_recent(0) == []
    assert store.read_recent(-1) == []


def test_recent_tail_preserves_unicode_crlf_and_a_line_spanning_many_blocks(tmp_path):
    path = tmp_path / "history.jsonl"
    text = "中文👩‍💻\u2028\u2029" * 20000
    payload = {"session_id": "large", "corrected_text": text}
    path.write_bytes((json.dumps({"session_id": "first"}) + "\r\n\r\n" +
                      json.dumps(payload, ensure_ascii=False)).encode("utf-8"))
    rows = HistoryStore(path).read_recent(2)
    assert [row["session_id"] for row in rows] == ["large", "first"]
    assert rows[0]["corrected_text"] == text


def test_recent_tail_skips_corrupt_records_without_hiding_valid_newer_text(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_bytes(b'not-json\n\xff\xfe\n{"corrected_text":"recoverable"}\n')
    rows = HistoryStore(path).read_recent(80)
    assert len(rows) == 1
    assert rows[0]["corrected_text"] == "recoverable"


def test_recent_history_reads_only_a_bounded_tail_of_the_real_file(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        for index in range(100000):
            stream.write(json.dumps({"session_id": str(index), "corrected_text": "fixture " * 40}) + "\n")
    original_open = Path.open
    read_sizes = []

    class ObservedFile:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def read(self, size=-1):
            assert 0 < size <= 64 * 1024
            result = self.stream.read(size)
            read_sizes.append(len(result))
            return result

    def observed_open(candidate, *args, **kwargs):
        stream = original_open(candidate, *args, **kwargs)
        return ObservedFile(stream) if candidate == path else stream

    monkeypatch.setattr(Path, "open", observed_open)
    assert len(HistoryStore(path).read_recent(80)) == 80
    assert sum(read_sizes) == 64 * 1024


def test_deleting_and_restoring_unicode_record_does_not_split_its_text(tmp_path):
    store = HistoryStore(tmp_path / "history.jsonl")
    text = "before\u2028中文👩‍💻\u2029after"
    store.append(corrected_text="first")
    store.append(corrected_text=text)
    store.append(corrected_text="last")
    entry = store.read_recent()[1]
    token = store.delete_entry_with_undo(entry["_entry_id"])
    assert token is not None
    assert [row["corrected_text"] for row in store.read_recent()] == ["last", "first"]
    assert store.restore_entry(token)
    assert [row["corrected_text"] for row in store.read_recent()] == ["last", text, "first"]
