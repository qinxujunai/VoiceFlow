"""Interactive development delivery fixture; activates only after its editor is focused.

Creates an owned Win32 EDIT window and exercises the production clipboard/paste
path. No ASR or installed-build claim. Moving focus away aborts the run.
"""

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from delivery import _windows_libraries, inspect_foreground_target
from output_handler import OutputHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Windows required")
    user32, kernel32, _ = _windows_libraries()
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                       ctypes.c_size_t, ctypes.c_ssize_t)

    class WindowClass(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("procedure", callback_type),
                    ("class_extra", ctypes.c_int), ("window_extra", ctypes.c_int),
                    ("instance", wintypes.HINSTANCE), ("icon", wintypes.HICON),
                    ("cursor", wintypes.HANDLE), ("background", wintypes.HBRUSH),
                    ("menu_name", wintypes.LPCWSTR), ("class_name", wintypes.LPCWSTR)]

    signatures = [
        (kernel32.GetModuleHandleW, [wintypes.LPCWSTR], wintypes.HMODULE),
        (user32.RegisterClassW, [ctypes.POINTER(WindowClass)], wintypes.ATOM),
        (user32.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                wintypes.HINSTANCE, wintypes.LPVOID], wintypes.HWND),
        (user32.DefWindowProcW, [wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
                                ctypes.c_ssize_t], ctypes.c_ssize_t),
        (user32.ShowWindow, [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        (user32.GetMessageW, [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                             wintypes.UINT, wintypes.UINT], wintypes.BOOL),
        (user32.TranslateMessage, [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
        (user32.DispatchMessageW, [ctypes.POINTER(wintypes.MSG)], ctypes.c_ssize_t),
        (user32.PostMessageW, [wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
                              ctypes.c_ssize_t], wintypes.BOOL),
        (user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL),
        (user32.PostQuitMessage, [ctypes.c_int], None),
        (user32.SetWindowTextW, [wintypes.HWND, wintypes.LPCWSTR], wintypes.BOOL),
    ]
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result

    def procedure(window, message, wparam, lparam):
        if message == 2:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(window, message, wparam, lparam)

    callback = callback_type(procedure)
    instance = kernel32.GetModuleHandleW(None)
    window_class = WindowClass(0, callback, 0, 0, instance, None, None, 6, None,
                               "VoiceFlowOwnedDeliveryFixture")
    assert user32.RegisterClassW(ctypes.byref(window_class))
    window = user32.CreateWindowExW(0, window_class.class_name,
                                   "VoiceFlow delivery fixture - click the editor to run",
                                   0x00CF0000, 120, 120, 800, 400, None, None, instance, None)
    assert window
    editor = user32.CreateWindowExW(0x200, "EDIT", "Click here to run sanitized delivery cases.",
                                   0x50000000 | 0x10000 | 0x200000 | 0x4 | 0x40 | 0x1000,
                                   20, 20, 740, 300, window, None, instance, None)
    assert editor
    user32.ShowWindow(window, 4)  # SW_SHOWNOACTIVATE; no foreground stealing.

    def message(number, wparam=0, lparam=0):
        result = ctypes.c_size_t()
        if not user32.SendMessageTimeoutW(editor, number, wparam, lparam, 0x0023,
                                         100, ctypes.byref(result)):
            raise TimeoutError("owned fixture editor unavailable")
        return result.value

    def read_owned_editor():
        length = message(0x000E)
        buffer = ctypes.create_unicode_buffer(length + 1)
        message(0x000D, len(buffer), ctypes.addressof(buffer))
        return buffer.value

    def run():
        rows = []
        handler = None
        try:
            deadline = time.monotonic() + 120
            while True:
                target = inspect_foreground_target()
                if target.window_handle == window and target.focus_window_handle == editor:
                    break
                if time.monotonic() >= deadline or not user32.IsWindow(window):
                    raise TimeoutError("fixture was not focused; no paste attempted")
                time.sleep(.05)
            handler = OutputHandler(base_dir=args.output.parent)
            cases = [
                ("中文短句", "", 0, 0),
                ("English sentence.", "before|after", 7, 7),
                ("中英 VoiceFlow mixed 🙂", "before|REPLACE|after", 7, 14),
                ("Emoji 👩‍💻 🙂", "before|after", 7, 7),
                ("第一行\n第二行", "before|after", 7, 7),
                ("Long fixture 中文 English " * 10, "before|after", 7, 7),
            ]
            for index in range(24):
                text, initial, start, end = cases[index % len(cases)]
                if inspect_foreground_target().window_handle != window:
                    raise RuntimeError("focus left the owned fixture; no further paste attempted")
                assert user32.SetWindowTextW(editor, initial)
                message(0x00B1, start, end)  # Only this owned fixture's selection.
                stop = handler.capture_stop_target()
                if stop.window_handle != window or stop.focus_window_handle != editor:
                    raise RuntimeError("owned fixture focus changed")
                started = time.perf_counter()
                result = handler.deliver(text, start_target=None, stop_target=stop,
                                          session_id=f"native-fixture-{index:02d}")
                elapsed_ms = (time.perf_counter() - started) * 1000
                expected = initial[:start] + text + initial[end:]
                actual = read_owned_editor()
                rows.append({"case": index, "text": text, "initial": initial,
                             "selection": [start, end], "expected": expected,
                             "actual": actual, "exact_match": actual == expected,
                             "delivery_ms": elapsed_ms, "result": asdict(result)})
                if actual != expected:
                    raise AssertionError("owned fixture did not receive the exact final once")
                time.sleep(.05)
            report = {"scope": "development source, production Delivery, owned Win32 EDIT; no ASR, not packaged E2E",
                      "ok": True, "rows": rows}
        except Exception as error:
            report = {"ok": False, "error": f"{type(error).__name__}: {error}", "rows": rows}
        finally:
            if handler is not None:
                handler.shutdown()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "cases": len(rows),
                          "confirmed": sum(row["result"]["landed_confirmed"] for row in rows),
                          "error": report.get("error", "")}), flush=True)
        user32.SetWindowTextW(window, "VoiceFlow delivery fixture - finished; see evidence")

    threading.Thread(target=run, name="voiceflow-owned-fixture", daemon=True).start()
    message_record = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message_record), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message_record))
        user32.DispatchMessageW(ctypes.byref(message_record))


if __name__ == "__main__":
    main()
