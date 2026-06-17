from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verify_uses_explicit_py_compile_file_list():
    from scripts import verify

    assert verify.PYTHON_FILES
    assert all("*" not in item for item in verify.PYTHON_FILES)
    assert "src/main.py" in verify.PYTHON_FILES
    assert "src/transcriber.py" in verify.PYTHON_FILES


def test_verify_runs_the_project_quality_gate():
    verify_script = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")

    assert '"doctor"' in verify_script
    assert '"py_compile"' in verify_script
    assert '"pytest"' in verify_script
    assert '"benchmark"' in verify_script
    assert '"integration"' in verify_script
    assert '"--quick"' in verify_script
