"""Constructed-text punctuation checks; never a speech-accuracy benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punctuation import FinalPunctuationRestorer, lexical_skeleton
from punctuation_worker import SupervisedPunctuation


CASES = [
    ("zh", "有时候。我觉得。停顿。带来了很多。句号。"),
    ("zh", "这个地方我也可。以提个建议。对产品的后续补充。有很大的帮助。"),
    ("zh", "你现在有时间吗可以一起看看这个方案吗"),
    ("zh", "然后然后我们就继续吧我觉得这个方案可以"),
    ("zh", "先整理这份方案然后比较成本风险最后给出建议" * 30),
    ("en", "how are you i am fine thank you"),
    ("en", "Compare the costs and risks of these two proposals then recommend an approach"),
    ("mixed", "我想用 ChatGPT 和 Claude 讨论这个 API 的设计"),
    ("mixed", "请把这个 Python 项目推送到 GitHub 然后检查 CI 是否通过"),
    ("protected", "https://example.com/a?b=2"),
    ("protected", "x = 2"),
    ("protected", "版本 1.2.3"),
    ("protected", "E:\\my project\\a.py"),
    ("zh", "他说‘保持原文’不要把low-cost方案换掉"),
]


def working_set(pid):
    if sys.platform != "win32":
        return {"rss_bytes": None, "peak_working_set_bytes": None}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "paged_peak", "paged",
                                                "nonpaged_peak", "nonpaged", "pagefile", "pagefile_peak")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"rss_bytes": counters.working, "peak_working_set_bytes": counters.peak}
    finally:
        kernel.CloseHandle(handle)


def run(model, repeats):
    worker = SupervisedPunctuation(model)
    started = time.perf_counter()
    if not worker.load():
        raise RuntimeError("punctuation worker did not become ready")
    startup_ms = (time.perf_counter() - started) * 1000
    pid = worker._process.pid
    try:
        restorer = FinalPunctuationRestorer(worker.restore)
        results = []
        for category, source in CASES:
            durations = []
            for _ in range(repeats):
                started = time.perf_counter()
                candidate = restorer.restore(source)
                durations.append((time.perf_counter() - started) * 1000)
            results.append({"category": category, "source": source, "result": candidate,
                "content_preserved": lexical_skeleton(candidate) == lexical_skeleton(source),
                "p95_ms": sorted(durations)[max(0, int(len(durations) * .95) - 1)]})
        report = {"scope": "constructed text, development CPU, no ASR accuracy claim",
            "worker_pid": pid, "startup_ms": startup_ms, **working_set(pid),
            "results": results,
            "passed": all(row["content_preserved"] and row["p95_ms"] < 600 for row in results)}
    finally:
        worker.shutdown()
    report["worker_exited"] = worker._process is None
    report["passed"] = report["passed"] and report["worker_exited"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "models/punctuation/model.int8.onnx")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.model, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    raise SystemExit(0 if report["passed"] else 1)
