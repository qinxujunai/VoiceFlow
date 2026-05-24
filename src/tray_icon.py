"""
Small, status-aware tray icons for VoiceFlow.
"""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


TRAY_ICON_IDLE = "idle"
TRAY_ICON_RECORDING = "recording"
TRAY_ICON_PROCESSING = "processing"
TRAY_ICON_ERROR = "error"

_ICON_SIZES = (16, 20, 24, 32)


def build_tray_icon(state=TRAY_ICON_IDLE, icon_path=None):
    icon = QIcon()
    for size in _ICON_SIZES:
        icon.addPixmap(_draw_pixmap(size, state, icon_path))
    return icon


def _draw_pixmap(size, state, icon_path=None):
    pixmap = _base_pixmap(size, icon_path)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if state == TRAY_ICON_RECORDING:
        _draw_status_dot(painter, size, QColor(255, 69, 58))
    elif state == TRAY_ICON_PROCESSING:
        _draw_processing_ring(painter, size)
    elif state == TRAY_ICON_ERROR:
        _draw_status_dot(painter, size, QColor(255, 159, 10))

    painter.end()
    return pixmap


def _base_pixmap(size, icon_path=None):
    if icon_path:
        app_icon = QIcon(icon_path)
        pixmap = app_icon.pixmap(size, size)
        if not pixmap.isNull():
            return pixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_waveform(painter, size)
    painter.end()
    return pixmap


def _draw_waveform(painter, size):
    x_positions = [0.30, 0.42, 0.54, 0.66]
    heights = [0.28, 0.50, 0.38, 0.62]
    center_y = size / 2

    outline = QPen(QColor(28, 28, 30, 210))
    outline.setCapStyle(Qt.PenCapStyle.RoundCap)
    outline.setWidthF(max(2.1, size * 0.15))

    stroke = QPen(QColor(246, 246, 248))
    stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroke.setWidthF(max(1.1, size * 0.075))

    for pen in (outline, stroke):
        painter.setPen(pen)
        for x_ratio, height_ratio in zip(x_positions, heights):
            half_height = size * height_ratio / 2
            x = size * x_ratio
            painter.drawLine(
                QPointF(x, center_y - half_height),
                QPointF(x, center_y + half_height),
            )


def _draw_status_dot(painter, size, color):
    diameter = max(5.0, size * 0.34)
    x = size - diameter - size * 0.08
    y = size * 0.08

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(28, 28, 30, 230))
    painter.drawEllipse(
        QPointF(x + diameter / 2, y + diameter / 2),
        diameter / 2,
        diameter / 2,
    )

    painter.setBrush(color)
    painter.drawEllipse(
        QPointF(x + diameter / 2, y + diameter / 2),
        diameter * 0.34,
        diameter * 0.34,
    )


def _draw_processing_ring(painter, size):
    diameter = max(6.0, size * 0.38)
    x = size - diameter - size * 0.05
    y = size * 0.06
    center = QPointF(x + diameter / 2, y + diameter / 2)

    outline = QPen(QColor(28, 28, 30, 220))
    outline.setWidthF(max(1.4, size * 0.08))
    outline.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(outline)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(center, diameter * 0.39, diameter * 0.39)

    stroke = QPen(QColor(10, 132, 255))
    stroke.setWidthF(max(0.9, size * 0.045))
    stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(stroke)
    painter.drawArc(
        int(x + diameter * 0.16),
        int(y + diameter * 0.16),
        int(diameter * 0.68),
        int(diameter * 0.68),
        30 * 16,
        280 * 16,
    )
