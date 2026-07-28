import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_balanced_thread_policy_matches_supported_cpu_tiers():
    from performance_profile import choose_asr_threads

    assert choose_asr_threads(physical_cores=4) == (1, 2)
    assert choose_asr_threads(physical_cores=8) == (1, 4)
    assert choose_asr_threads(physical_cores=12) == (2, 6)


def test_asr_threads_always_leave_one_physical_core_for_ui_and_audio():
    from performance_profile import choose_asr_threads

    for cores in range(2, 33):
        preview, final = choose_asr_threads(physical_cores=cores)
        assert preview >= 1
        assert final >= 1
        assert preview + final <= max(2, cores - 1)
