import ctypes
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from delivery import TargetSnapshot


def test_positive_composition_blocks_paste_and_a_last_moment_context_guard():
    before = TargetSnapshot(101, 202, "edit", True, True, True)
    composing = replace(before, ime_composing=True)
    assert not composing.paste_decision_from(None).allowed
    assert composing.paste_decision_from(None).reason == "ime_composition"
    assert not composing.same_input_context(before)
    assert not before.same_input_context(composing)


def test_unknown_composition_is_not_positive_evidence_to_block_ordinary_typing():
    before = TargetSnapshot(101, 202, "edit", True, True, True)
    assert before.ime_composing is None
    assert before.paste_decision_from(None).allowed


@pytest.mark.parametrize("size,expected", [(12, True), (0, False), (-1, None), (-2, None)])
def test_imm_query_reads_only_composition_size_and_releases_context(monkeypatch, size, expected):
    import delivery

    context = 0x200000000
    released = []

    def query(handle, flag, buffer, length):
        assert handle == context
        assert flag == 8
        assert buffer is None and length == 0
        return size

    api = SimpleNamespace(ImmGetContext=lambda hwnd: context,
                          ImmGetCompositionStringW=query,
                          ImmReleaseContext=lambda hwnd, handle: released.append((hwnd, handle)))
    monkeypatch.setattr(delivery, "_ime_library", lambda: api)
    assert delivery._ime_composing(303) is expected
    assert released == [(303, context)]


def test_ime_context_uses_pointer_sized_abi_on_windows():
    import delivery

    if sys.platform != "win32":
        pytest.skip("Windows IMM ABI")
    api = delivery._ime_library()
    assert api.ImmGetContext.restype is ctypes.wintypes.HANDLE
    assert api.ImmGetCompositionStringW.restype is ctypes.wintypes.LONG


def test_uia_composition_checks_presence_without_reading_unfinished_text():
    from delivery import _uia_has_composition

    class PrivateRange:
        def GetText(self, *_args):
            raise AssertionError("IME composition text must not be read")

    automation = SimpleNamespace(PatternId=SimpleNamespace(TextEditPattern=10032))
    control = SimpleNamespace(GetPattern=lambda _pattern:
                              SimpleNamespace(GetActiveComposition=lambda: PrivateRange()))
    assert _uia_has_composition(automation, control) is True
