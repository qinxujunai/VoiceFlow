from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recovery_session import RecoverySessionStore


def _directory_link(target, link):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("directory links unavailable")
        import _winapi
        _winapi.CreateJunction(str(target), str(link))


def test_clear_all_refuses_root_junction_without_deleting_external_audio(tmp_path):
    store = RecoverySessionStore(tmp_path / "recovery")
    external = tmp_path / "outside"
    audio = external / "external-session" / "audio.pcm"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"external audio")
    link = tmp_path / "linked-root"
    _directory_link(external, link)
    store.root = link

    with pytest.raises(OSError):
        store.clear_all()

    assert audio.read_bytes() == b"external audio"


def test_clear_all_refuses_session_junction_before_removing_other_sessions(tmp_path):
    store = RecoverySessionStore(tmp_path / "recovery")
    own = store.root / "a-owned"
    own.mkdir()
    (own / "audio.pcm").write_bytes(b"owned audio")
    external = tmp_path / "outside"
    external.mkdir()
    audio = external / "audio.pcm"
    audio.write_bytes(b"external audio")
    _directory_link(external, store.root / "z-linked")

    with pytest.raises(OSError):
        store.clear_all()

    assert (own / "audio.pcm").read_bytes() == b"owned audio"
    assert audio.read_bytes() == b"external audio"


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
