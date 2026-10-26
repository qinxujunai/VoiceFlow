"""Confirmation requires a single replacement and the exact inserted span."""

import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from delivery import DeliveryCoordinator, FocusMonitor, TargetSnapshot, VerifiedClipboard


def target(**values):
    return replace(TargetSnapshot(101, 202, "edit", True, True, True,
                                  provider="uia", runtime_id="42.1",
                                  focus_window_handle=303,
                                  selection_start=3, selection_end=5, document_length=10),
                   **values)


def test_single_replacement_equation_uses_utf16_for_native_edit():
    from insertion_verification import replacement_matches

    before = target()
    text = "中文🙂"
    after = replace(before, selection_start=7, selection_end=7, document_length=12)
    assert replacement_matches(before, after, text, encoding="utf-16-le", line_ending="\r\n")
    assert not replacement_matches(before, before, text, encoding="utf-16-le", line_ending="\r\n")
    assert not replacement_matches(before, replace(after, document_length=16), text,
                                   encoding="utf-16-le", line_ending="\r\n")


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-8"])
@pytest.mark.parametrize("ending", ["\r\n", "\n", "preserve"])
def test_equation_handles_selection_and_native_line_endings(encoding, ending):
    from insertion_verification import replacement_matches

    before = target()
    text = "A\n中🙂"
    normalized = text if ending == "preserve" else text.replace("\n", ending)
    inserted = len(normalized.encode(encoding)) // (2 if encoding == "utf-16-le" else 1)
    after = replace(before, selection_start=3 + inserted, selection_end=3 + inserted,
                    document_length=8 + inserted)
    assert replacement_matches(before, after, text, encoding=encoding, line_ending=ending)


@pytest.mark.parametrize("changes", [
    {"process_id": 999}, {"focus_window_handle": 999}, {"runtime_id": "42.2"},
    {"document_id": 22}, {"selection_start": 4, "selection_end": 8},
    {"document_length": None}, {"integrity_compatible": False},
])
def test_changed_or_ambiguous_context_cannot_be_confirmed(changes):
    from insertion_verification import replacement_matches

    before = target(document_id=11)
    after = replace(before, selection_start=7, selection_end=7, document_length=12)
    assert not replacement_matches(before, replace(after, **changes), "中文🙂",
                                   encoding="utf-16-le", line_ending="\r\n")


@pytest.mark.parametrize("confirmed", [False, True])
def test_coordinator_only_confirms_actual_verifier_evidence(tmp_path, confirmed):
    before = target()
    observed = {"clipboard": "", "pastes": 0, "verifications": 0}

    def copy(text):
        observed["clipboard"] = text

    def paste():
        observed["pastes"] += 1
        return True

    def verify(snapshot, text):
        observed["verifications"] += 1
        assert snapshot == before
        assert text == "唯一终稿🙂"
        assert observed["pastes"] == 1
        return confirmed

    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(copy=copy, paste=lambda: observed["clipboard"]),
        inspect_target=lambda: before, dispatch_paste=paste,
        ledger_dir=tmp_path / "pending", verify_insertion=verify)
    result = coordinator.deliver("唯一终稿🙂", start_target=None, session_id="verification")
    assert observed["pastes"] == observed["verifications"] == 1
    assert result.landed_confirmed is confirmed
    assert result.output_status == ("landed_confirmed" if confirmed else
                                    "clipboard_verified_paste_dispatched")


def test_insertion_timeout_uses_the_same_mta_thread_and_never_retries_paste():
    threads = []
    entered = threading.Event()
    release = threading.Event()

    @contextmanager
    def context(*_args):
        yield

    def verify(_target, _text):
        threads.append(threading.get_ident())
        entered.set()
        release.wait(2)
        return True

    monitor = FocusMonitor(inspector=lambda: target(), initializer=context,
                           subscriber=context, insertion_verifier=verify)
    try:
        monitor.warmup()
        started = time.perf_counter()
        assert not monitor.verify_insertion(target(), "文字", timeout=.02)
        # Returns at its 20 ms timeout, not after the hung verifier's 2 s; 0.5 s leaves room for a busy CI runner
        # (0.153 s was seen on macOS on 2026-10-25).
        assert time.perf_counter() - started < .5
        assert entered.wait(.5)
        worker = monitor._thread
        for _ in range(30):
            assert not monitor.verify_insertion(target(), "文字", timeout=0)
        assert monitor._thread is worker
        assert monitor._requests.qsize() <= 8
        release.set()
        deadline = time.monotonic() + .5
        while monitor.observe(timeout=.1).snapshot.window_handle != 101:
            assert time.monotonic() < deadline
            time.sleep(.001)
        assert len(threads) == 1
    finally:
        release.set()
        monitor.shutdown()


@pytest.mark.parametrize("actual,collapsed,expected", [
    ("唯一终稿🙂", True, True), ("错误内容", True, False),
    ("唯一终稿🙂 extra", True, False), ("唯一终稿🙂", False, False),
])
def test_uia_reads_only_the_bounded_inserted_span(monkeypatch, actual, collapsed, expected):
    from insertion_verification import _read_inserted_span

    observed = []

    class Range:
        def CompareEndpoints(self, source, other, target_endpoint):
            return 0 if source == target_endpoint or collapsed else -1

        def Clone(self):
            return Range()

        def MoveEndpointByUnit(self, endpoint, unit, count, *, waitTime):
            assert waitTime == 0
            assert count == -len("唯一终稿🙂")
            observed.append("move")
            return count

        def GetText(self, maximum):
            assert maximum == len("唯一终稿🙂".encode("utf-16-le")) // 2 + 1
            observed.append("bounded read")
            return actual

    control = SimpleNamespace(ProcessId=202, GetRuntimeId=lambda: [42, 1],
                              IsPassword=False, IsEnabled=True,
                              GetPattern=lambda _pattern: SimpleNamespace(GetSelection=lambda: [Range()]))
    automation = SimpleNamespace(GetFocusedControl=lambda: control,
                                  PatternId=SimpleNamespace(TextPattern=10014),
                                  TextPatternRangeEndpoint=SimpleNamespace(Start=0, End=1),
                                  TextUnit=SimpleNamespace(Character=0))
    monkeypatch.setitem(sys.modules, "uiautomation", automation)
    assert _read_inserted_span(target(), "唯一终稿🙂") is expected
    assert observed == (["move", "bounded read"] if collapsed else [])


def test_verifier_exception_remains_unverified_and_does_not_retry_paste(tmp_path):
    observed = {"clipboard": "", "pastes": 0}

    def copy(text):
        observed["clipboard"] = text

    def paste():
        observed["pastes"] += 1
        return True

    def unavailable(*_args):
        raise OSError("provider unavailable")

    coordinator = DeliveryCoordinator(
        clipboard=VerifiedClipboard(copy=copy, paste=lambda: observed["clipboard"]),
        inspect_target=target, dispatch_paste=paste, verify_insertion=unavailable,
        ledger_dir=tmp_path / "pending")
    result = coordinator.deliver("仍可手动粘贴", start_target=None, session_id="unavailable")
    assert result.clipboard_verified and result.paste_dispatched
    assert not result.landed_confirmed
    assert observed["pastes"] == 1
