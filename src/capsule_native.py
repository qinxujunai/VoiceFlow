"""Compact native Qt capsule, matching the established black/red visual contract."""

from collections import deque
import math
import os
import time

from qt_compat import (
    QColor, QFont, QFontMetricsF, QPainter, QPen, QPointF, QRectF,
    QTextBoundaryFinder, QTimer, QWidget, Qt, Signal, Slot, QObject, QEvent,
)
from platform_utils import system_high_contrast_enabled


def system_animations_enabled():
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        query = ctypes.WinDLL("user32", use_last_error=True).SystemParametersInfoW
        query.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
        query.restype = wintypes.BOOL
        enabled = wintypes.BOOL(True)
        if query(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except (OSError, AttributeError):
        pass
    return True


def split_graphemes(text):
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Grapheme, text)
    encoded = text.encode("utf-16-le")
    result = []
    start = 0
    while True:
        end = finder.toNextBoundary()
        if end < 0:
            return result
        result.append(encoded[start * 2:end * 2].decode("utf-16-le"))
        start = end


class CapsuleState:
    BASE_INTERVAL = 0.048
    HARD_LAG = 0.6
    VISIBLE_LIMIT = 64

    def __init__(self):
        self.generation = 0
        self.mode = "idle"
        self.visible = []
        self.pending = deque()
        self.next_character_at = 0.0

    @property
    def text(self):
        return "".join(self.visible)

    def _append(self, values):
        self.visible = (self.visible + list(values))[-self.VISIBLE_LIMIT:]

    def prepare_recording(self, generation):
        self.generation = int(generation)
        self.mode = "listening"
        self.visible.clear()
        self.pending.clear()
        self.next_character_at = 0.0

    def append_streaming(self, text, generation, *, now=None):
        if generation != self.generation or self.mode not in {"listening", "streaming"}:
            return
        now = time.perf_counter() if now is None else now
        self.mode = "streaming"
        self.pending.extend((char, now) for char in split_graphemes(text))
        if len(self.pending) > 256:
            self._append(self.pending.popleft()[0] for _ in range(len(self.pending) - 20))

    def advance(self, *, now=None):
        now = time.perf_counter() if now is None else now
        if not self.pending or now < self.next_character_at:
            return False
        if now - self.pending[0][1] >= self.HARD_LAG:
            self._append(char for char, _ in self.pending)
            self.pending.clear()
        else:
            self._append([self.pending.popleft()[0]])
        if self.pending:
            pressure = min(1.0, max((now - self.pending[0][1]) / 0.18, len(self.pending) / 12))
            self.next_character_at = now + self.BASE_INTERVAL - 0.031 * pressure
        return True

    def show_settling(self, generation):
        if generation < self.generation or self.mode in {"final_text", "final_ready", "recovery"}:
            return
        self.generation = int(generation)
        self.pending.clear()
        self.mode = "settling"

    def show_final(self, text, generation):
        if generation < self.generation:
            return
        self.generation = int(generation)
        self.pending.clear()
        self.visible = split_graphemes(text)[-self.VISIBLE_LIMIT:]
        self.mode = "final_text"

    def show_label(self, mode, text):
        self.pending.clear()
        self.visible = split_graphemes(text)[-self.VISIBLE_LIMIT:]
        self.mode = mode

    def reset(self):
        self.pending.clear()
        self.visible.clear()
        self.mode = "idle"


class NativeCapsuleView(QWidget):
    preview_painted = Signal(int)
    HEIGHT = 34.0
    MIN_WIDTH = 86.0
    MAX_WIDTH = 312.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        font = QFont(self.font())
        font.setPixelSize(13)
        self.setFont(font)
        self.state = CapsuleState()
        self._width = self.MIN_WIDTH
        self._width_start = self._width
        self._target_width = self._width
        self._width_changed_at = 0.0
        self._levels = [0.45] * 3
        self._level_starts = self._levels[:]
        self._level_targets = self._levels[:]
        self._levels_changed_at = 0.0
        self._painted_generation = None
        self._dismiss_at = None
        self._motion_enabled = system_animations_enabled()
        self._high_contrast_active = system_high_contrast_enabled()
        self._motion_checked_at = time.perf_counter()
        self.frame_timer = QTimer(self)
        self.frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.frame_timer.setInterval(16)
        self.frame_timer.timeout.connect(self._animate)

    @Slot(str, object)
    def present(self, command, args):
        now = time.perf_counter()
        self._refresh_motion_preference(now)
        announcement = None
        if command == "prepare_recording":
            self.state.prepare_recording(*args)
            self._width = self._width_start = self._target_width = self.MIN_WIDTH
            self._width_changed_at = now
            self._levels = [0.45] * 3
            self._level_starts = self._levels[:]
            self._level_targets = self._levels[:]
            self._levels_changed_at = now
            self._painted_generation = None
            self._dismiss_at = None
        elif command == "append_streaming":
            self.state.append_streaming(*args, now=now)
            self.state.advance(now=now)
        elif command == "transcript":
            authoritative, draft, generation = args
            if generation == self.state.generation and self.state.mode in {"listening", "streaming"}:
                self.state.show_final(authoritative + draft, generation)
                self.state.mode = "streaming"
        elif command == "final":
            self.state.show_final(*args)
        elif command == "settling":
            self.state.show_settling(*args)
        elif command == "levels":
            levels, generation = args
            if generation == self.state.generation and self.state.mode in {"listening", "streaming"}:
                levels = list(levels[:3]) + [0.0] * max(0, 3 - len(levels))
                self._level_starts = self._levels[:]
                self._level_targets = [0.36 + math.sqrt(min(0.16, max(0, level)) / 0.16) * 0.92 for level in levels]
                self._levels_changed_at = now
        elif command == "processing":
            self.state.show_label("processing", "处理中")
        elif command == "delivery":
            status, generation = args
            if generation >= self.state.generation:
                self.state.generation = generation
                self.state.pending.clear()
                self._dismiss_at = None
                if status == "landed_confirmed":
                    self._dismiss_at = now
                    announcement = "文字已输入"
                elif status == "recovery_saved_clipboard_unavailable":
                    self.state.show_label("recovery", "已保存")
                    announcement = "文字已保存，可在最近转录中复制"
                elif status == "delivery_failed":
                    self.state.show_label("error", "复制和保存未完成")
                    announcement = "复制和保存未完成，请查看可恢复的录音"
                else:
                    self.state.show_label("final_ready", "已复制到剪贴板")
                    announcement = "文字已复制；如果未出现，请在目标位置按 Ctrl+V"
        elif command == "label":
            self.state.show_label(*args)
        elif command == "reset":
            self.state.reset()
            self._dismiss_at = None
        else:
            raise ValueError(f"unknown capsule command: {command}")
        self._retarget_width(now)
        if not self._motion_enabled:
            self._settle_without_motion(now)
        self._update_accessible_name(announcement)
        self.update()
        if self._has_motion(now):
            self.frame_timer.start()
        else:
            self.frame_timer.stop()

    def _update_accessible_name(self, announcement=None):
        self.setAccessibleName(announcement or self.state.text or
                               {"listening": "正在录音", "settling": "正在完成识别"}.get(self.state.mode, "VoiceFlow"))

    def _retarget_width(self, now):
        text_width = QFontMetricsF(self.font()).horizontalAdvance(self.state.text)
        target = min(self.MAX_WIDTH, max(self.MIN_WIDTH, 62.0 + text_width)) if self.state.text else self.MIN_WIDTH
        if self.state.mode == "streaming":
            target = max(self._target_width, target, 96.0)
        if target != self._target_width:
            self._width_start = self._width
            self._target_width = target
            self._width_changed_at = now

    def _has_motion(self, now):
        if not self._motion_enabled:
            return False
        return (bool(self.state.pending) or abs(self._width - self._target_width) > 0.05
                or any(abs(a - b) > 0.001 for a, b in zip(self._levels, self._level_targets))
                or self.state.mode in {"processing", "settling"}
                or self._dismiss_at is not None and now - self._dismiss_at < 0.12)

    def _animate(self):
        now = time.perf_counter()
        self._refresh_motion_preference(now)
        if not self._motion_enabled:
            self._settle_without_motion(now)
            self.update()
            self.frame_timer.stop()
            return
        if self.state.advance(now=now):
            self._retarget_width(now)
            self._update_accessible_name()
        progress = min(1.0, max(0.0, (now - self._width_changed_at) / 0.18))
        self._width = self._width_start + (self._target_width - self._width_start) * (1 - (1 - progress) ** 3)
        progress = min(1.0, max(0.0, (now - self._levels_changed_at) / 0.09))
        self._levels = [a + (b - a) * progress for a, b in zip(self._level_starts, self._level_targets)]
        self.update()
        if not self._has_motion(now):
            self.frame_timer.stop()

    def _refresh_motion_preference(self, now):
        if now - self._motion_checked_at >= 1.0:
            self._motion_enabled = system_animations_enabled()
            self._high_contrast_active = system_high_contrast_enabled()
            self._motion_checked_at = now

    def event(self, event):
        if (hasattr(self, "_high_contrast_active") and event.type() in {
                QEvent.Type.ApplicationPaletteChange, QEvent.Type.PaletteChange,
                QEvent.Type.ThemeChange}):
            self._high_contrast_active = system_high_contrast_enabled()
            self.update()
        return super().event(event)

    def showEvent(self, event):
        self._high_contrast_active = system_high_contrast_enabled()
        super().showEvent(event)

    def _settle_without_motion(self, now):
        had_pending = bool(self.state.pending)
        self.state._append(char for char, _ in self.state.pending)
        self.state.pending.clear()
        self._retarget_width(now)
        self._width = self._width_start = self._target_width
        self._levels = [0.45] * 3
        if had_pending:
            self._update_accessible_name()

    def paintEvent(self, _event):
        if self.state.mode == "idle":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        high_contrast = self._high_contrast_active
        foreground = self.palette().windowText().color() if high_contrast else QColor("#f5f5f7")
        if self._dismiss_at is not None and self._motion_enabled and not high_contrast:
            painter.setOpacity(max(0.0, 1 - (time.perf_counter() - self._dismiss_at) / 0.12))
        rect = QRectF((self.width() - self._width) / 2, (self.height() - self.HEIGHT) / 2, self._width, self.HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        if not high_contrast:
            for spread, alpha in ((3, 6), (2, 10), (1, 16)):
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawRoundedRect(rect.adjusted(-spread, -spread + 1, spread, spread + 1), 17 + spread, 17 + spread)
        background = self.palette().window().color() if high_contrast else QColor(24, 24, 26, 225)
        painter.setBrush(background)
        tint = (foreground if high_contrast else
                QColor(255, 69, 58, 44) if self.state.mode in {"listening", "streaming"} else QColor(255, 255, 255, 24))
        painter.setPen(QPen(tint, 2.0 if high_contrast else 0.5))
        painter.drawRoundedRect(rect, 17, 17)
        mark_x = rect.x() + 16
        center_y = rect.center().y()
        if self.state.mode in {"processing", "settling"}:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(foreground if high_contrast else QColor(245, 245, 247, 55), 1.6))
            ring = QRectF(mark_x - 1, center_y - 6.5, 13, 13)
            painter.drawEllipse(ring)
            painter.setPen(QPen(foreground if high_contrast else QColor(245, 245, 247, 235), 1.6))
            angle = int(-time.perf_counter() / 0.78 * 5760) if self._motion_enabled else 0
            painter.drawArc(ring, angle, 1152)
        elif self.state.mode != "final_text":
            color = QColor("#ff453a") if self.state.mode in {"listening", "streaming"} else QColor("#9b9b9f")
            if self.state.mode == "error":
                color = QColor("#ffb340")
            if high_contrast and self.state.mode not in {"listening", "streaming"}:
                color = foreground
            painter.setPen(QPen(foreground, 1.0) if high_contrast else Qt.PenStyle.NoPen)
            painter.setBrush(color)
            for index, height in enumerate((7, 12, 8)):
                height *= self._levels[index]
                if high_contrast:
                    height = max(5, height)
                painter.drawRoundedRect(QRectF(mark_x + (6 if high_contrast else 4) * index,
                                              center_y - height / 2, 4 if high_contrast else 2, height), 1, 1)
        text_rect = QRectF(rect.x() + 38, rect.y(), max(0.0, rect.width() - 50), rect.height())
        text = self.state.text
        metrics = QFontMetricsF(self.font())
        graphemes = split_graphemes(text)
        while graphemes and metrics.horizontalAdvance("".join(graphemes)) > text_rect.width():
            graphemes.pop(0)
        painter.setFont(self.font())
        painter.setPen(foreground)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "".join(graphemes))
        painter.end()
        generation = self.state.generation
        if self.state.mode == "streaming" and text and self._painted_generation != generation:
            self._painted_generation = generation
            QTimer.singleShot(0, lambda: self.preview_painted.emit(generation) if self.state.generation == generation else None)


class NativeCapsuleBridge(QObject):
    render_requested = Signal(str, object)
    render_then_show_requested = Signal(str, object)
    render_then_hide_requested = Signal(str, object)
    show_requested = Signal()
    hide_requested = Signal()
    hide_after_requested = Signal(int)
    tray_state_requested = Signal(str)
    settings_requested = Signal()
    startup_requested = Signal()
    onboarding_completed_requested = Signal()

    def __init__(self, view, before_show):
        super().__init__()
        self.view = view
        self.before_show = before_show
        self.render_requested.connect(view.present)
        self.render_then_show_requested.connect(self._show_prepared)
        self.render_then_hide_requested.connect(self._hide_and_reset)

    @Slot(str, object)
    def _show_prepared(self, command, args):
        self.view.present(command, args)
        self.before_show()
        self.show_requested.emit()

    @Slot(str, object)
    def _hide_and_reset(self, command, args):
        self.hide_requested.emit()
        self.view.present(command, args)
