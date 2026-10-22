"""Validate native input dispatch at the Win32 boundary without typing into apps."""

import sys
from pathlib import Path

import pytest

# Exercises Win32 APIs, struct layouts or Windows release artifacts; covered by Windows quality.
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only contract")


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_windows_cannot_use_the_unchecked_cross_platform_paste_path(monkeypatch):
    import output_handler
    from types import SimpleNamespace

    monkeypatch.setattr(output_handler.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(hotkey=lambda *_args: None))
    handler = output_handler.OutputHandler.__new__(output_handler.OutputHandler)
    with pytest.raises(RuntimeError, match="checked"):
        handler._dispatch_paste()


@windows_only
@pytest.mark.parametrize("terminal, keys", [
    (False, [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]),
    (True, [(0x11, 0), (0x10, 0), (0x56, 0), (0x56, 2), (0x10, 2), (0x11, 2)]),
])
def test_native_paste_dispatches_exactly_one_chord(monkeypatch, terminal, keys):
    import delivery

    sent = []

    class InputApi:
        def GetAsyncKeyState(self, _key):
            return 0

        def SendInput(self, count, events, size):
            sent.append([(event.ki.wVk, event.ki.dwFlags) for event in events])
            assert size == 40 if sys.maxsize > 2**32 else size == 28
            return count

    monkeypatch.setattr(delivery, "_windows_libraries", lambda: (InputApi(), None, None))
    result = delivery.dispatch_windows_paste(guard=lambda: True, terminal=terminal)
    assert result.dispatched
    assert sent == [keys]
    assert all(key != 0x0D for key, _ in keys)


def test_held_physical_modifier_never_gets_released_or_pasted(monkeypatch):
    import delivery

    class InputApi:
        def GetAsyncKeyState(self, _key):
            return 0x8000

        def SendInput(self, *_args):
            pytest.fail("A held physical key must not be released or pasted")

    monkeypatch.setattr(delivery, "_windows_libraries", lambda: (InputApi(), None, None))
    result = delivery.dispatch_windows_paste(guard=lambda: True, modifier_timeout=0)
    assert not result.dispatched
    assert result.reason == "modifier_held"


def test_paste_guard_is_checked_after_waiting_for_modifiers(monkeypatch):
    import delivery

    class InputApi:
        def GetAsyncKeyState(self, _key):
            return 0

        def SendInput(self, *_args):
            pytest.fail("Changed target or clipboard must block dispatch")

    monkeypatch.setattr(delivery, "_windows_libraries", lambda: (InputApi(), None, None))
    result = delivery.dispatch_windows_paste(guard=lambda: False)
    assert not result.dispatched
    assert result.reason == "delivery_context_changed"


def test_partial_send_releases_only_injected_keys_and_never_retries_paste(monkeypatch):
    import delivery

    sent = []

    class InputApi:
        def GetAsyncKeyState(self, _key):
            return 0

        def SendInput(self, count, events, _size):
            sent.append([(event.ki.wVk, event.ki.dwFlags) for event in events])
            return 1 if len(sent) == 1 else count

    monkeypatch.setattr(delivery, "_windows_libraries", lambda: (InputApi(), None, None))
    result = delivery.dispatch_windows_paste(guard=lambda: True)
    assert not result.dispatched
    assert result.reason == "paste_dispatch_partial"
    assert sent[1:] == [[(0x11, 2)]]
