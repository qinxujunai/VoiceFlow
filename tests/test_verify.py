from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verify_uses_explicit_py_compile_file_list():
    from scripts import verify

    assert verify.PYTHON_FILES
    assert all("*" not in item for item in verify.PYTHON_FILES)
    assert "src/main.py" in verify.PYTHON_FILES
    assert "src/transcriber.py" in verify.PYTHON_FILES
    assert "scripts/verify.py" in verify.PYTHON_FILES
    assert "test_integration.py" in verify.PYTHON_FILES


def test_verify_runs_the_project_quality_gate():
    verify_script = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")

    assert '"doctor"' in verify_script
    assert '"py_compile"' in verify_script
    assert '"pytest"' in verify_script
    assert '"benchmark"' in verify_script
    assert '"integration"' in verify_script
    assert '"--quick"' in verify_script
    assert "stdout=subprocess.PIPE" in verify_script
    assert "stderr=subprocess.STDOUT" in verify_script


def test_verify_forces_utf8_subprocess_output():
    from scripts import verify

    env = verify._quality_gate_env()

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUNBUFFERED"] == "1"


def test_verify_reconfigures_parent_stdout():
    verify_script = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")

    assert "sys.stdout.reconfigure" in verify_script
    assert "_force_utf8_stdout()" in verify_script


def test_integration_fails_on_empty_or_slow_transcription():
    integration = (ROOT / "test_integration.py").read_text(encoding="utf-8")

    assert "MIN_TEXT_CHARS" in integration
    assert "MAX_RTF" in integration
    assert "转写结果为空或过短" in integration
    assert "转写速度异常" in integration
