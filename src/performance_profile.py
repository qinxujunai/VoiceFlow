"""CPU-aware ASR thread policy for the Windows CPU build."""

from __future__ import annotations

import os


def physical_core_count() -> int:
    try:
        import psutil

        count = psutil.cpu_count(logical=False)
        if count:
            return max(2, int(count))
    except Exception:
        pass
    logical = os.cpu_count() or 4
    return max(2, int(logical) // 2)


def choose_asr_threads(*, physical_cores: int | None = None) -> tuple[int, int]:
    cores = max(2, int(physical_cores or physical_core_count()))
    if cores <= 3:
        preview, final = 1, 1
    elif cores <= 4:
        preview, final = 1, 2
    elif cores <= 5:
        preview, final = 1, 3
    elif cores <= 8:
        preview, final = 1, 4
    elif cores <= 9:
        preview, final = 1, 6
    else:
        preview, final = 2, 6

    budget = max(2, cores - 1)
    final = max(1, min(final, budget - preview))
    return preview, final


def _configured_threads(value, automatic: int) -> int:
    if value is None or str(value).strip().lower() in {"", "auto"}:
        return automatic
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return automatic


def preview_thread_count(value="auto", *, physical_cores: int | None = None) -> int:
    automatic, _ = choose_asr_threads(physical_cores=physical_cores)
    return _configured_threads(value, automatic)


def final_thread_count(value="auto", *, physical_cores: int | None = None) -> int:
    _, automatic = choose_asr_threads(physical_cores=physical_cores)
    return _configured_threads(value, automatic)
