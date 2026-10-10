import os
from pathlib import Path
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_native_capsule_keeps_confirmed_text_and_discards_stale_sessions():
    from capsule_native import CapsuleState

    state = CapsuleState()
    state.prepare_recording(1)
    state.append_streaming("你好世界", 1, now=0)
    state.advance(now=0)
    assert state.text == "你"
    state.show_settling(2)
    state.append_streaming("旧内容", 1, now=1)
    state.advance(now=2)
    assert state.text == "你"
    state.show_final("完整的文字", 2)
    state.show_settling(2)
    assert state.mode == "final_text"
    assert state.text == "完整的文字"
    state.prepare_recording(3)
    assert state.text == ""
    state.show_final("迟到的终稿", 2)
    assert state.mode == "listening"
    assert state.text == ""


def test_capsule_uses_the_windows_application_font_family():
    from capsule_native import NativeCapsuleView
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    assert view.font().family() == app.font().family()
    view.close()


def test_native_capsule_bounds_backlog_and_preserves_graphemes():
    from capsule_native import CapsuleState, split_graphemes

    assert split_graphemes("你👩‍💻e\u0301🇨🇳") == ["你", "👩‍💻", "e\u0301", "🇨🇳"]
    state = CapsuleState()
    state.prepare_recording(1)
    text = "甲" * 300 + "终点👩‍💻"
    state.append_streaming(text, 1, now=0)
    state.advance(now=0.61)
    assert len(state.pending) == 0
    assert state.text.endswith("终点👩‍💻")
    assert len(split_graphemes(state.text)) <= 64


def test_native_capsule_renders_black_pill_and_three_red_bars(monkeypatch):
    monkeypatch.setattr("capsule_native.system_high_contrast_enabled", lambda: False)
    from capsule_native import NativeCapsuleView
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    view.resize(380, 48)
    view.present("prepare_recording", [1])
    view.show()
    app.processEvents()
    frame = view.grab().toImage()
    background = frame.pixelColor(215, 24)
    assert background.red() < 45 and background.green() < 45
    red_columns = []
    for x in range(140, 180):
        if any(frame.pixelColor(x, y).red() > 180 and frame.pixelColor(x, y).green() < 110 for y in range(17, 31)):
            red_columns.append(x)
    groups = []
    for x in red_columns:
        if not groups or x > groups[-1][-1] + 1:
            groups.append([])
        groups[-1].append(x)
    assert len(groups) == 3
    assert not view.frame_timer.isActive()
    view.present("levels", [[0.02], 1])
    view.present("transcript", ["确认文字", "预览", 1])
    assert view.state.text == "确认文字预览"
    view.present("settling", [2])
    view.present("levels", [[0.16, 0.16, 0.16], 1])
    assert view.state.mode == "settling"
    view.close()


def test_new_recording_cancels_previous_width_and_level_animation():
    from capsule_native import NativeCapsuleView
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    view.present("prepare_recording", [1])
    view.present("final", ["上一轮很长的文字" * 10, 1])
    view._width = 200
    view._width_start = 200
    view.present("prepare_recording", [2])
    view.present("levels", [[0.02, 0.03, 0.02], 2])
    view._animate()
    assert view._width == view.MIN_WIDTH
    assert view.state.text == ""
    view.close()


def test_dispatched_paste_retains_truthful_fallback_until_insertion_is_confirmed():
    from capsule_native import NativeCapsuleView
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    try:
        view.present("prepare_recording", [1])
        view.present("final", ["终稿", 1])
        view.present("delivery", ["clipboard_verified_paste_dispatched", 1])
        assert view._dismiss_at is None
        assert view.state.text == "已复制到剪贴板"
        assert "未出现" in view.accessibleName()
        view.present("final", ["终稿", 1])
        view.present("delivery", ["landed_confirmed", 1])
        assert view._dismiss_at is not None
        assert view.accessibleName() == "文字已输入"
    finally:
        view.close()


def test_reduced_motion_shows_stable_preview_immediately_without_a_frame_loop(monkeypatch):
    import capsule_native
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(capsule_native, "system_animations_enabled", lambda: False, raising=False)
    view = capsule_native.NativeCapsuleView()
    try:
        view.present("prepare_recording", [1])
        view.present("append_streaming", ["稳定文字👩‍💻立即可见", 1])
        assert view.accessibleName() == view.state.text
        view.present("levels", [[0.01, 0.16, 0.02], 1])
        assert view.state.text == "稳定文字👩‍💻立即可见"
        assert view.accessibleName() == view.state.text
        assert not view.state.pending
        assert view._width == view._target_width
        assert view._levels == [0.45] * 3
        assert not view.frame_timer.isActive()
        view.present("settling", [1])
        assert not view.frame_timer.isActive()
    finally:
        view.close()


def test_disabling_animation_during_a_preview_flushes_backlog(monkeypatch):
    import capsule_native
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    enabled = [True]
    monkeypatch.setattr(capsule_native, "system_animations_enabled", lambda: enabled[0])
    view = capsule_native.NativeCapsuleView()
    try:
        view.present("prepare_recording", [1])
        view.present("append_streaming", ["稳定的文字无需等待", 1])
        assert view.state.pending
        enabled[0] = False
        view._motion_checked_at -= 2
        view._animate()
        assert view.state.text == "稳定的文字无需等待"
        assert view.accessibleName() == view.state.text
        assert not view.state.pending
        assert not view.frame_timer.isActive()
    finally:
        view.close()


def test_animated_preview_accessible_name_tracks_rendered_text(monkeypatch):
    import capsule_native
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(capsule_native, "system_animations_enabled", lambda: True)
    view = capsule_native.NativeCapsuleView()
    try:
        view.present("prepare_recording", [1])
        view.present("append_streaming", ["清楚的反馈", 1])
        assert view.accessibleName() == "清"
        view.state.next_character_at = 0
        view._animate()
        assert view.state.text == "清楚"
        assert view.accessibleName() == view.state.text
    finally:
        view.close()


@pytest.mark.parametrize("background,foreground", [("#ffffff", "#000000"), ("#001833", "#ffff00")])
def test_high_contrast_capsule_uses_opaque_system_background_and_foreground(monkeypatch, background, foreground):
    import capsule_native
    from PySide6.QtGui import QPalette
    from qt_compat import QApplication, QColor

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(capsule_native, "system_high_contrast_enabled", lambda: True, raising=False)
    monkeypatch.setattr(capsule_native, "system_animations_enabled", lambda: False)
    view = capsule_native.NativeCapsuleView()
    try:
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(foreground))
        view.setPalette(palette)
        view.resize(380, 48)
        view.present("prepare_recording", [1])
        view.show()
        app.processEvents()
        frame = view.grab().toImage()
        assert frame.pixelColor(215, 24) == QColor(background)
        assert any(frame.pixelColor(x, y) == QColor(foreground)
                   for x in range(140, 234) for y in range(6, 42))
        # Recording remains red; the system-colored outline keeps its shape
        # distinguishable when that red has poor contrast with the chosen theme.
        assert any(frame.pixelColor(x, y).red() > 180 and frame.pixelColor(x, y).green() < 110
                   for x in range(148, 178) for y in range(19, 30))
        view.present("processing", [])
        frame = view.grab().toImage()
        assert any(frame.pixelColor(x, y) == QColor(foreground)
                   for x in range(160, 178) for y in range(12, 36))
    finally:
        view.close()


def test_capsule_refreshes_system_colors_when_theme_changes_without_a_new_recording(monkeypatch):
    import capsule_native
    from qt_compat import QApplication, QEvent

    app = QApplication.instance() or QApplication([])
    enabled = [False]
    monkeypatch.setattr(capsule_native, "system_high_contrast_enabled", lambda: enabled[0], raising=False)
    view = capsule_native.NativeCapsuleView()
    try:
        view.present("prepare_recording", [1])
        assert not view._high_contrast_active
        enabled[0] = True
        app.sendEvent(view, QEvent(QEvent.Type.ApplicationPaletteChange))
        assert view._high_contrast_active
        assert view.state.mode == "listening"
        enabled[0] = False
        app.sendEvent(view, QEvent(QEvent.Type.ThemeChange))
        assert not view._high_contrast_active
    finally:
        view.close()


@pytest.mark.parametrize("query_succeeds,flags,expected", [(True, 1, True), (True, 0, False), (False, 1, False)])
def test_high_contrast_system_query_uses_typed_win32_contract(monkeypatch, query_succeeds, flags, expected):
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace
    import platform_utils

    class Query:
        def __call__(self, action, size, pointer, update):
            assert action == 0x0042 and update == 0
            assert size == ctypes.sizeof(pointer._obj) == pointer._obj.cbSize
            assert self.argtypes == [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
            assert self.restype is wintypes.BOOL
            pointer._obj.dwFlags = flags
            return query_succeeds

    monkeypatch.setattr(platform_utils.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(SystemParametersInfoW=Query()))
    assert platform_utils.system_high_contrast_enabled() is expected
