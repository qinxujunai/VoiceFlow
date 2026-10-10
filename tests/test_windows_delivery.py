"""Exercise the real Windows token boundary without reading or editing user input."""

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows token APIs")


def _reference_current_integrity():
    # Separate DLL objects prevent the reference from changing production's ABI.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetSidSubAuthorityCount.argtypes = [wintypes.LPVOID]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [wintypes.LPVOID, wintypes.DWORD]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

    token = wintypes.HANDLE()
    assert advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token))
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 25, None, 0, ctypes.byref(required))
        assert required.value > 0
        buffer = ctypes.create_string_buffer(required.value)
        assert advapi32.GetTokenInformation(
            token, 25, buffer, required.value, ctypes.byref(required)
        )
        sid = ctypes.c_void_p.from_buffer(buffer).value
        count = advapi32.GetSidSubAuthorityCount(sid).contents.value
        assert count > 0
        return int(advapi32.GetSidSubAuthority(sid, count - 1).contents.value)
    finally:
        assert kernel32.CloseHandle(token)


def test_current_process_integrity_matches_real_typed_windows_token():
    from delivery import _process_integrity_level

    expected = _reference_current_integrity()
    assert 0 <= expected <= 0x5000
    assert _process_integrity_level(os.getpid()) == expected


def test_current_process_is_integrity_compatible_with_itself():
    from delivery import _integrity_compatible

    assert _integrity_compatible(os.getpid())


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="Windows x64 ABI")
def test_current_process_integrity_with_token_buffer_above_four_gib(monkeypatch):
    import delivery

    expected = _reference_current_integrity()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.VirtualAlloc.argtypes = [
        wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD
    ]
    kernel32.VirtualAlloc.restype = wintypes.LPVOID
    kernel32.VirtualFree.argtypes = [wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
    kernel32.VirtualFree.restype = wintypes.BOOL
    address = kernel32.VirtualAlloc(0x200000000, 0x10000, 0x3000, 0x04)
    if not address:
        # A separate already-loaded library may occupy the first requested range.
        address = kernel32.VirtualAlloc(0x300000000, 0x10000, 0x3000, 0x04)
    assert address and address > 0xFFFFFFFF

    def high_address_buffer(size):
        assert 0 < size <= 0x10000
        return (ctypes.c_char * size).from_address(address)

    try:
        monkeypatch.setattr(delivery.ctypes, "create_string_buffer", high_address_buffer)
        assert delivery._process_integrity_level(os.getpid()) == expected
    finally:
        assert kernel32.VirtualFree(address, 0, 0x8000)


@pytest.mark.parametrize("process_id", [0, -1, 0xFFFFFFFF])
def test_invalid_process_integrity_is_unknown_and_does_not_allow_paste(process_id):
    from delivery import _integrity_compatible, _process_integrity_level

    assert _process_integrity_level(process_id) is None
    assert not _integrity_compatible(process_id)
