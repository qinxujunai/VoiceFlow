"""Capture evidence must reject a renderer with no usable fonts."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_offscreen_capture_rejects_empty_font_database():
    code = """
from scripts.capture_ui_states import QApplication, _prepare_capture_fonts
from PySide6.QtGui import QFontDatabase
app = QApplication([])
QFontDatabase.families = staticmethod(lambda: [])
try:
    _prepare_capture_fonts(app, False)
except RuntimeError as error:
    assert 'font' in str(error).lower()
else:
    raise AssertionError('empty font database accepted as capture evidence')
"""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_explicit_windows_offscreen_fonts_have_real_latin_and_chinese_glyphs():
    if sys.platform != "win32":
        import pytest
        pytest.skip("Windows system-font fixture")
    code = """
from scripts.capture_ui_states import QApplication, _prepare_capture_fonts
app = QApplication([])
evidence = _prepare_capture_fonts(app, True)
assert evidence['platform'] == 'offscreen'
assert evidence['mode'] == 'offscreen-system-font-fixture'
assert len(evidence['loaded_fonts']) == 3
assert evidence['probe_glyph_count'] == 13
assert {'Segoe UI', 'Microsoft YaHei'} <= set(evidence['resolved_families'])
assert all(item['sha256'] for item in evidence['loaded_fonts'])
"""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
