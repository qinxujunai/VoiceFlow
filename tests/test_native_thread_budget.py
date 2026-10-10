import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize("frozen,platform,retained", [
    (True, "win32", False), (False, "win32", True), (True, "linux", True),
])
def test_only_packaged_windows_uses_the_bundled_non_asio_backend(monkeypatch, frozen, platform, retained):
    source = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.syspath_prepend(str(source))
    from runtime_bootstrap import configure_packaged_audio_backend

    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("SD_ENABLE_ASIO", "1")
    configure_packaged_audio_backend()
    assert ("SD_ENABLE_ASIO" in os.environ) is retained


def test_packaged_backend_is_prepared_before_frozen_worker_dispatch():
    root = Path(__file__).resolve().parents[1]
    hook = (root / "scripts/pyinstaller_qt_runtime_hook.py").read_text(encoding="utf-8")
    assert hook.index("configure_packaged_audio_backend()") < hook.index("multiprocessing.freeze_support()")


def test_audio_numpy_thread_pool_is_bounded_before_import():
    source = Path(__file__).resolve().parents[1] / "src"
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="16")
    code = """
import sys,os,pathlib,ctypes
sys.path.insert(0,sys.argv[1])
from runtime_bootstrap import configure_native_thread_pools
configure_native_thread_pools()
import numpy
assert os.environ['OPENBLAS_NUM_THREADS']=='1'
if sys.platform=='win32':
    dll=next((pathlib.Path(numpy.__file__).parent.parent/'numpy.libs').glob('*openblas*.dll'))
    blas=ctypes.CDLL(str(dll))
    assert blas.scipy_openblas_get_num_threads64_()==1
"""
    completed = subprocess.run([sys.executable, "-c", code, str(source)],
                               env=environment, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
