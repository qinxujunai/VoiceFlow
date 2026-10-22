"""The settings window's stylesheet (light, macOS System Settings-like) and its combo chevron."""

import logging
import tempfile
from pathlib import Path

from qt_compat import Qt, QPixmap, QPainter, QPen, QColor, QPointF


logger = logging.getLogger("voiceflow.ui")


class StyleMixin:
    @staticmethod
    def _combo_arrow_path():
        """A small chevron for combo boxes, drawn once per process (QSS needs an image file)."""
        directory = Path(tempfile.gettempdir()) / "voiceflow-ui"
        path = directory / "chevron-down@2x.png"
        if not path.exists():
            directory.mkdir(parents=True, exist_ok=True)
            image = QPixmap(24, 24)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#6e6e73"), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QPointF(7, 10), QPointF(12, 15), QPointF(17, 10)])
            painter.end()
            image.save(str(path))
        return path.as_posix()

    def _style(self):
        # Quiet, native-feeling settings: light sidebar, grouped white cards on a soft grey canvas,
        # one dark primary button per page, text buttons for secondary actions.
        return """
        * {
            font-size: 13px;
        }
        QWidget#appShell {
            background: #f5f5f7;
            color: #1d1d1f;
        }
        QWidget#sidebarPanel {
            background: #ececef;
            border: none;
            border-right: 1px solid #dcdce1;
            border-radius: 0px;
        }
        QLabel#brandIcon {
            min-width: 32px;
            min-height: 32px;
        }
        QLabel#appTitle {
            font-size: 16px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#appSubtitle, QLabel#sidebarVersion {
            font-size: 11px;
            color: #6e6e73;
        }
        QListWidget#sidebar {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget#sidebar::item {
            min-height: 36px;
            padding-left: 10px;
            border-radius: 8px;
            color: #1d1d1f;
        }
        QListWidget#sidebar::item:hover {
            background: rgba(0, 0, 0, 0.04);
        }
        QListWidget#sidebar::item:selected {
            background: rgba(0, 0, 0, 0.08);
            color: #1d1d1f;
            border: none;
            font-weight: 600;
        }
        QLabel#statusBadge {
            padding: 8px 10px;
            background: #ffffff;
            color: #1f7a3a;
            border: 1px solid #e0e0e5;
            border-radius: 8px;
            font-weight: 600;
        }
        QLabel#statusBadge[attention="true"] {
            color: #9a5b00;
            background: #fff8eb;
            border-color: #f2dfb8;
        }
        QWidget#sidebarPanel QPushButton {
            color: #3a3a3c;
            background: transparent;
            border: none;
            text-align: left;
            padding: 6px 10px;
            min-height: 30px;
        }
        QWidget#sidebarPanel QPushButton:hover {
            background: rgba(0, 0, 0, 0.05);
        }
        QPushButton::menu-indicator {
            subcontrol-position: right center;
            right: 8px;
        }
        QStackedWidget#contentStack {
            background: #f5f5f7;
            border: none;
            border-radius: 0px;
        }
        QScrollArea#settingsPageScroll, QScrollArea#dictationScroll {
            background: #f5f5f7;
            border: none;
        }
        QWidget#contentPage {
            background: transparent;
            border: none;
        }
        QLabel#sectionTitle, QLabel#commandTitle {
            font-size: 26px;
            font-weight: 650;
            color: #1d1d1f;
        }
        QLabel#sectionSubtitle, QLabel#commandSubtitle, QLabel#bodyText {
            color: #6e6e73;
            font-size: 13px;
        }
        QLabel#commandSubtitle {
            font-size: 14px;
        }
        QLabel#groupCaption {
            color: #6e6e73;
            font-size: 12px;
            font-weight: 600;
            padding-left: 4px;
        }
        QWidget#groupCard, QWidget#recoveryPanel, QWidget#aboutHero, QWidget#privacyPanel {
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 12px;
        }
        QLabel#fieldName {
            color: #1d1d1f;
        }
        QLabel#rowNote, QLabel#saveNote {
            color: #6e6e73;
            font-size: 12px;
            padding: 2px 0px 6px 0px;
        }
        QCheckBox {
            spacing: 10px;
            color: #1d1d1f;
        }
        QWidget#groupCard QCheckBox {
            border-top: 1px solid #ececf0;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        QLabel#shortcutKey {
            color: #3a3a3c;
            background: #ffffff;
            border: 1px solid #d8d8dd;
            border-bottom: 2px solid #c7c7cc;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#systemStatusItem {
            color: #3a3a3c;
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 12px;
            padding: 5px 11px;
            font-size: 12px;
            font-weight: 550;
        }
        QWidget#saveBar {
            background: #fbfbfc;
            border-top: 1px solid #e3e3e8;
        }
        QLabel#recoveryTitle {
            color: #8a5600;
            font-size: 14px;
            font-weight: 650;
        }
        QLabel#subsectionTitle, QLabel#aboutVersion {
            color: #1d1d1f;
            font-size: 14px;
            font-weight: 600;
        }
        QLabel#aboutVersion {
            color: #6e6e73;
            font-weight: 500;
        }
        QLabel#aboutTitle {
            color: #1d1d1f;
            font-size: 22px;
            font-weight: 650;
        }
        QLabel#diagnosticSummary {
            color: #3a3a3c;
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 12px;
            padding: 13px;
        }
        QLabel#diagnosticName {
            color: #1d1d1f;
            font-weight: 600;
        }
        QLabel#diagnosticDetail {
            color: #6e6e73;
            font-size: 12px;
        }
        QLabel#diagnosticOk, QLabel#diagnosticAttention {
            padding: 3px 8px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#diagnosticOk {
            color: #1f7a3a;
            background: #eaf7ee;
        }
        QLabel#diagnosticAttention {
            color: #9a5b00;
            background: #fff4df;
        }
        QLabel#privacyNote {
            color: #515154;
            background: #ffffff;
            border: 1px solid #e5e5ea;
            border-radius: 11px;
            padding: 11px 13px;
        }
        QLabel#operationFeedback {
            color: #285b3a;
            background: #f0f8f2;
            border-top: 1px solid #dcebe1;
        }
        QLabel#operationFeedback[attention="true"] {
            color: #874914;
            background: #fff6ec;
            border-top-color: #f2e0c8;
        }
        QLabel#fieldValue {
            color: #1d1d1f;
            font-weight: 500;
        }
        QLineEdit, QComboBox {
            border: 1px solid #d8d8dd;
            border-radius: 8px;
            background: #ffffff;
            padding: 6px 10px;
            min-height: 20px;
            selection-background-color: #0a64d6;
            selection-color: #ffffff;
        }
        QComboBox {
            padding-right: 30px;
        }
        QComboBox:hover, QLineEdit:hover {
            border-color: #c2c2c8;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 26px;
            border: none;
        }
        QComboBox::down-arrow {
            image: url("__CHEVRON__");
            width: 12px;
            height: 12px;
        }
        QComboBox QAbstractItemView {
            border: 1px solid #d8d8dd;
            border-radius: 8px;
            background: #ffffff;
            padding: 4px;
            selection-background-color: #e8f0fd;
            selection-color: #1d1d1f;
            outline: none;
        }
        QListWidget#historyList, QListWidget#diagnosticList, QListWidget#dictionaryList {
            border: 1px solid #e5e5ea;
            border-radius: 12px;
            background: #ffffff;
            padding: 4px;
            outline: none;
        }
        QListWidget#dictionaryList {
            border: none;
            padding: 0px;
        }
        QListWidget#historyList::item, QListWidget#diagnosticList::item {
            padding: 0px;
            margin: 0px;
            border: none;
            border-bottom: 1px solid #f0f0f3;
            background: transparent;
        }
        QListWidget#dictionaryList::item {
            padding: 0px 10px;
            margin: 3px;
            border: 1px solid #e5e5ea;
            border-radius: 15px;
            background: #f7f7f9;
        }
        QListWidget#historyList::item:selected, QListWidget#diagnosticList::item:selected {
            color: #1d1d1f;
            background: #f2f6fd;
            border-radius: 8px;
        }
        QListWidget#dictionaryList::item:selected {
            color: #1d1d1f;
            background: #e8f0fd;
            border-color: #b9cff3;
        }
        QWidget#historyCard, QWidget#emptyCard, QWidget#diagnosticCard {
            background: transparent;
        }
        QLabel#historyText {
            color: #1d1d1f;
            font-size: 14px;
            font-weight: 500;
        }
        QLabel#emptyTitle {
            color: #1d1d1f;
            font-size: 15px;
            font-weight: 600;
        }
        QLabel#historyMeta {
            color: #6e6e73;
            font-size: 12px;
        }
        QPushButton {
            min-height: 30px;
            padding: 4px 14px;
            border-radius: 8px;
            border: 1px solid #d8d8dd;
            background: #ffffff;
            color: #1d1d1f;
            font-weight: 500;
        }
        QPushButton:hover {
            background: #f5f5f7;
        }
        QPushButton:pressed {
            background: #ececef;
        }
        QPushButton:disabled {
            color: #aeaeb2;
            border-color: #e5e5ea;
        }
        QPushButton:focus, QLineEdit:focus, QComboBox:focus, QListWidget:focus {
            border: 2px solid #0a64d6;
        }
        QPushButton#primaryButton {
            background: #1d1d1f;
            color: white;
            border: 1px solid #1d1d1f;
            font-weight: 600;
            padding: 4px 18px;
        }
        QPushButton#primaryButton:hover {
            background: #3a3a3c;
            border-color: #3a3a3c;
        }
        QPushButton#primaryButton:disabled {
            background: #d1d1d6;
            border-color: #d1d1d6;
            color: #ffffff;
        }
        QPushButton#textButton, QPushButton#destructiveTextButton {
            border: none;
            background: transparent;
            color: #0060c7;
            padding: 4px 8px;
            min-height: 28px;
        }
        QPushButton#destructiveTextButton {
            color: #c4271f;
        }
        QPushButton#textButton:hover, QPushButton#destructiveTextButton:hover {
            background: rgba(0, 0, 0, 0.04);
        }
        QPushButton#textButton:disabled, QPushButton#destructiveTextButton:disabled {
            color: #aeaeb2;
        }
        QPushButton#inlineCopyButton, QPushButton#inlineRepasteButton, QPushButton#inlineDeleteButton {
            min-width: 52px;
            min-height: 26px;
            padding: 2px 10px;
            font-size: 12px;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 0, 0, 0.18);
            border-radius: 3px;
            min-height: 32px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            height: 0px;
            background: transparent;
        }
        """.replace("__CHEVRON__", self._combo_arrow_path())
