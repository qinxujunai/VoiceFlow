from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recovery_session import RecoverySessionStore


def test_clear_all_removes_recovery_directories_and_keeps_unrelated_files(tmp_path):
    root = tmp_path / "recovery"
    store = RecoverySessionStore(root)
    first = store.start_session(
        session_id="one",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )
    first.close_interrupted()
    second = store.start_session(
        session_id="two",
        sample_rate=16000,
        channels=1,
        dtype="int16",
        model="sensevoice",
    )
    second.close_interrupted()
    unrelated = root / "README.txt"
    unrelated.write_text("keep", encoding="utf-8")

    assert set(store.clear_all()) == {"one", "two"}
    assert not (root / "one").exists()
    assert not (root / "two").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert store.clear_all() == ()


def test_clear_all_surfaces_a_locked_or_unremovable_recovery_directory(tmp_path, monkeypatch):
    root = tmp_path / "recovery"
    store = RecoverySessionStore(root)
    session_dir = root / "locked"
    session_dir.mkdir(parents=True)
    (session_dir / "audio.pcm").write_bytes(b"data")

    def fail_remove(_path):
        raise OSError("locked")

    monkeypatch.setattr("recovery_session.shutil.rmtree", fail_remove)

    try:
        store.clear_all()
    except OSError as error:
        assert "locked" in str(error)
    else:
        raise AssertionError("clear_all must surface deletion failures")
