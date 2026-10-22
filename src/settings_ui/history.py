"""The 历史 page: recent dictations, copy and re-paste, delete with undo, recovery of undelivered audio."""

import logging
import threading
from datetime import datetime

from qt_compat import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
    QMessageBox,
    Qt,
    QSize,
    Slot,
    QTimer,
)

from history_store import HistoryStore
from platform_utils import trigger_summary

logger = logging.getLogger("voiceflow.ui")


class HistoryMixin:
    def _recent_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(14)
        layout.addLayout(self._section_header("历史", "查看和复制最近结果。复制后，在需要的位置按 Ctrl+V。"))

        self.recovery_panel = QWidget()
        self.recovery_panel.setObjectName("recoveryPanel")
        recovery_layout = QVBoxLayout(self.recovery_panel)
        recovery_layout.setContentsMargins(14, 12, 14, 12)
        recovery_layout.setSpacing(8)
        self.recovery_summary = QLabel("")
        self.recovery_summary.setObjectName("recoveryTitle")
        self.recovery_detail = QLabel("尚未交付的录音不会自动删除。恢复并复制成功后删除；不再需要时可手动删除。")
        self.recovery_detail.setObjectName("sectionSubtitle")
        self.recovery_detail.setWordWrap(True)
        self.recovery_combo = QComboBox()
        self.recovery_combo.setAccessibleName("可恢复录音")
        recovery_actions = QHBoxLayout()
        self._recovery_actions = recovery_actions
        self.recover_button = QPushButton("重新识别并复制")
        self.recover_button.setObjectName("primaryButton")
        self.recover_button.clicked.connect(self._recover_selected_session)
        copy_preview = QPushButton("复制已有预览")
        copy_preview.clicked.connect(self._copy_recovery_preview)
        self.delete_recovery_button = QPushButton("删除录音")
        self.delete_recovery_button.clicked.connect(self._delete_recovery)
        self.recovery_combo.currentIndexChanged.connect(self._update_recovery_selection)
        recovery_actions.addWidget(self.recover_button)
        recovery_actions.addWidget(copy_preview)
        recovery_actions.addWidget(self.delete_recovery_button)
        recovery_actions.addStretch(1)
        recovery_layout.addWidget(self.recovery_summary)
        recovery_layout.addWidget(self.recovery_detail)
        recovery_layout.addWidget(self.recovery_combo)
        recovery_layout.addLayout(recovery_actions)
        self.recovery_panel.setVisible(False)
        layout.addWidget(self.recovery_panel)

        toolbar = QHBoxLayout()
        self._history_toolbar = toolbar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索最近转录")
        self.search_box.setAccessibleName("搜索历史转录")
        self.search_box.setClearButtonEnabled(True)
        self._history_search_timer = QTimer(self)
        self._history_search_timer.setSingleShot(True)
        self._history_search_timer.setInterval(140)
        self._history_search_timer.timeout.connect(self._render_history)
        self.search_box.textChanged.connect(
            lambda _text: self._history_search_timer.start()
        )
        toolbar.addWidget(self.search_box, 1)
        refresh = QPushButton("刷新")
        refresh.setObjectName("textButton")
        refresh.clicked.connect(self._refresh_history)
        toolbar.addWidget(refresh)
        copy_all = QPushButton("复制全部")
        copy_all.setObjectName("textButton")
        copy_all.clicked.connect(self._copy_all_visible)
        toolbar.addWidget(copy_all)
        clear_history = QPushButton("清空历史")
        clear_history.setObjectName("textButton")
        clear_history.clicked.connect(self._clear_history)
        toolbar.addWidget(clear_history)
        clear_local_data = QPushButton("清除本机数据")
        clear_local_data.setObjectName("destructiveTextButton")
        clear_local_data.clicked.connect(self._clear_local_data)
        toolbar.addWidget(clear_local_data)
        self.undo_history_button = QPushButton("撤销删除")
        self.undo_history_button.setObjectName("textButton")
        self.undo_history_button.setVisible(False)
        self.undo_history_button.clicked.connect(self._undo_history_delete)
        toolbar.addWidget(self.undo_history_button)
        layout.addLayout(toolbar)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.setAccessibleName("历史转录列表")
        self.history_list.itemDoubleClicked.connect(lambda item: self._copy_text(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.history_list, 1)

        return self._scrollable_page(page)

    def _output_status_label(self, status):
        return {
            "landed_confirmed": "已输入",
            "clipboard_verified_paste_dispatched": "已复制，输入未确认",
            "clipboard_verified_only": "已复制",
            "recovery_saved_clipboard_unavailable": "已保存",
            "clipboard_copied_paste_sent": "已复制，输入未确认",
            "clipboard_copied_integrity_warning": "已复制",
            "fallback": "已复制",
            "typed": "输入未确认",
            "error": "失败",
            "unknown": "未知",
        }.get(status, "未知")

    def _format_timestamp(self, value):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.strftime("%m月%d日 %H:%M")
        except Exception:
            return value

    def _refresh_history(self):
        if self._history_refresh_in_progress or self._refresh_in_progress:
            return
        self._history_refresh_in_progress = True
        self._set_status_badge("正在刷新历史")

        def run():
            try:
                payload = {"ok": True, "rows": self._read_history_rows()}
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
            self.history_refresh_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-history-refresh",
            daemon=True,
        ).start()

    def _read_history_rows(self):
        if self._on_read_history:
            return list(self._on_read_history())
        return HistoryStore(self.paths.history_file).read_recent(80)

    @Slot(object)
    def _finish_history_refresh(self, payload):
        self._history_refresh_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge(
                f"历史读取失败：{payload.get('error', '未知错误')}",
                attention=True,
            )
            return
        self._history_rows = payload["rows"]
        self._render_history()
        self._set_status_badge("历史已刷新")

    def _render_history(self):
        if not hasattr(self, "history_list"):
            return
        query = self.search_box.text().strip().lower() if hasattr(self, "search_box") else ""
        self._history_render_generation += 1
        generation = self._history_render_generation
        self.history_list.clear()
        cards = []
        for row in self._history_rows:
            text = row.get("corrected_text") or row.get("clean_text") or row.get("error") or ""
            if query and query not in text.lower():
                continue
            timestamp = self._format_timestamp(row.get("timestamp", ""))
            duration = row.get("duration")
            status = self._output_status_label(row.get("output_status", "unknown"))
            tail = row.get("final_tail", "")
            meta_parts = [part for part in (timestamp, f"{float(duration):.1f}s" if duration is not None else "", status) if part]
            if tail:
                meta_parts.append(f"尾部 {tail}")
            cards.append((text, " · ".join(meta_parts), row.get("_entry_id", "")))
        self._pending_history_cards = cards
        if not cards:
            empty = QListWidgetItem()
            empty.setData(Qt.ItemDataRole.UserRole, "")
            empty.setSizeHint(QSize(0, 180))
            self.history_list.addItem(empty)
            self.history_list.setItemWidget(empty, self._empty_card())
            return
        self._render_history_batch(generation)

    def _render_history_batch(self, generation):
        if generation != self._history_render_generation:
            return
        batch = self._pending_history_cards[:8]
        del self._pending_history_cards[: len(batch)]
        for text, meta, entry_id in batch:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, text)
            item.setSizeHint(QSize(0, 104))
            self.history_list.addItem(item)
            self.history_list.setItemWidget(
                item,
                self._history_card(text, meta, entry_id),
            )
        QTimer.singleShot(0, self._resize_history_cards)
        if self._pending_history_cards:
            QTimer.singleShot(
                0,
                lambda active=generation: self._render_history_batch(active),
            )

    def _history_card(self, text, meta, entry_id=""):
        card = QWidget()
        card.setObjectName("historyCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(12)

        text_group = QVBoxLayout()
        text_group.setSpacing(4)
        display_text = text if len(text) <= 180 else f"{text[:180]}…"
        body = QLabel(display_text)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setObjectName("historyText")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setToolTip(text)
        info = QLabel(meta)
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setObjectName("historyMeta")
        text_group.addWidget(body)
        text_group.addWidget(info)
        record = next((record for record in self._history_rows if record.get("_entry_id") == entry_id), {})
        if len(text) > 180 or record.get("raw_text") or record.get("output_status"):
            details = QPushButton("查看详情")
            details.setObjectName("inlineCopyButton")
            detail_text = QLabel()
            detail_text.setTextFormat(Qt.TextFormat.PlainText)
            detail_text.setWordWrap(True)
            detail_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_text.setText("终稿：\n" + text + ("\n\n原始识别：\n" + record["raw_text"] if record.get("raw_text") else "")
                                + "\n\n交付：" + self._output_status_label(record.get("output_status", "unknown")))
            detail_text.hide()
            def toggle_details():
                detail_text.setVisible(detail_text.isHidden())
                details.setText("收起详情" if detail_text.isVisible() else "查看详情")
                QTimer.singleShot(0, self._resize_history_cards)
            details.clicked.connect(toggle_details)
            text_group.addWidget(details)
            text_group.addWidget(detail_text)
        row.addLayout(text_group, 1)

        copy = QPushButton("复制")
        copy.setObjectName("inlineCopyButton")
        copy.clicked.connect(lambda _=False, value=text: self._copy_text(value))
        row.addWidget(copy)
        delete = QPushButton("删除")
        delete.setObjectName("inlineDeleteButton")
        delete.setEnabled(bool(entry_id))
        delete.clicked.connect(
            lambda _=False, value=entry_id: self._delete_history_entry(value)
        )
        row.addWidget(delete)
        return card

    def _resize_history_cards(self):
        for index in range(self.history_list.count()):
            item = self.history_list.item(index)
            widget = self.history_list.itemWidget(item)
            if widget:
                width = max(1, self.history_list.viewport().width())
                # Item margins and frame can make the card narrower than the viewport; size for the narrower one.
                if 0 < widget.width() < width:
                    width = widget.width()
                layout = widget.layout()
                height = max(widget.minimumSizeHint().height(), layout.heightForWidth(width))
                item.setSizeHint(QSize(width, height))

    def _delete_history_entry(self, entry_id):
        if not entry_id or not self._on_delete_history:
            self._set_status_badge("暂时无法删除", attention=True)
            return
        self._run_history_mutation("delete", entry_id)

    def _clear_history(self):
        if not self._history_rows:
            self._set_status_badge("没有历史记录")
            return
        if not self._on_clear_history:
            self._set_status_badge("暂时无法清空", attention=True)
            return
        answer = QMessageBox.question(
            self,
            "清空全部历史",
            "将永久删除全部本地听写历史（包括未显示的记录）和待交付文字，保留可恢复录音。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._clear_history_undo()
        self._run_history_mutation("clear")

    def _clear_local_data(self):
        if not self._on_clear_local_data or self._history_action_in_progress:
            self._set_status_badge("暂时无法清除本机数据", attention=True)
            return
        answer = QMessageBox.question(
            self,
            "清除本机听写数据",
            "将永久删除本地历史、待交付文字和未交付录音，保留配置、词典和模型。"
            "Windows 剪贴板及其历史、同步记录需自行清理。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._clear_history_undo()
        self._run_history_mutation("clear_local")

    def _undo_history_delete(self):
        token = self._history_undo_token
        if token is None or not self._on_restore_history:
            return
        self._history_undo_token = None
        self.undo_history_button.setVisible(False)
        self._run_history_mutation("restore", token=token)

    def _clear_history_undo(self):
        self._history_undo_generation += 1
        self._history_undo_token = None
        if hasattr(self, "undo_history_button"):
            self.undo_history_button.setVisible(False)

    def _run_history_mutation(self, action, entry_id="", token=None):
        if self._history_action_in_progress:
            return
        self._history_action_in_progress = True
        self._set_status_badge("正在删除历史")

        def run():
            try:
                undo_token = None
                if action == "clear":
                    changed = int(self._on_clear_history())
                elif action == "clear_local":
                    result = self._on_clear_local_data()
                    changed = int(
                        result.get("history_entries", 0)
                        + result.get("recovery_sessions", 0)
                        + result.get("pending_deliveries", 0)
                    )
                elif action == "restore":
                    changed = int(bool(self._on_restore_history(token)))
                else:
                    undo_token = self._on_delete_history(entry_id)
                    changed = int(bool(undo_token))
                payload = {
                    "ok": True,
                    "action": action,
                    "changed": changed,
                    "undo_token": undo_token,
                }
            except Exception as error:
                payload = {"ok": False, "action": action, "error": str(error)}
            self.history_mutation_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-history-delete",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_history_mutation(self, payload):
        self._history_action_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge(
                f"历史删除失败：{payload.get('error', '未知错误')}",
                attention=True,
            )
            return
        action = payload.get("action")
        if action == "delete" and payload.get("undo_token"):
            self._history_undo_token = payload["undo_token"]
            self._history_undo_generation += 1
            generation = self._history_undo_generation
            self.undo_history_button.setVisible(True)
            QTimer.singleShot(
                5000,
                lambda active=generation: (
                    self._clear_history_undo()
                    if active == self._history_undo_generation
                    else None
                ),
            )
            self._set_status_badge("历史已删除，可撤销")
        elif action == "restore":
            self._set_status_badge("已恢复")
        elif action == "clear_local":
            self._set_status_badge("本机听写数据已清除")
        else:
            self._set_status_badge("历史已清空")
        self._refresh_history()

    def _empty_card(self):
        card = QWidget()
        card.setObjectName("emptyCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 40, 14, 40)
        layout.setSpacing(6)
        title = QLabel("暂无转录")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note = QLabel(f"按 {trigger_summary()} 说一句话，结果会出现在这里")
        note.setObjectName("historyMeta")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(note)
        return card

    def _selected_text(self):
        item = self.history_list.currentItem() if hasattr(self, "history_list") else None
        if not item and hasattr(self, "history_list") and self.history_list.count() > 0:
            item = self.history_list.item(0)
            self.history_list.setCurrentItem(item)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _copy_selected(self):
        text = self._selected_text()
        self._copy_text(text)

    def _copy_text(self, text):
        if not text:
            self._set_status_badge("无可复制")
            return
        if not self._on_copy_text:
            self._set_status_badge("复制失败", attention=True)
            return
        self._run_history_action(text, self._on_copy_text, "正在复制")

    def _repaste_selected(self):
        text = self._selected_text()
        self._repaste_text(text)

    def _repaste_text(self, text):
        self._copy_text(text)

    def _run_history_action(self, text, callback, pending_label):
        if self._history_action_in_progress:
            self._set_status_badge("上一项操作仍在进行")
            return
        self._history_action_in_progress = True
        self._set_status_badge(pending_label)

        def run():
            try:
                payload = {"ok": True, "status": callback(text)}
            except Exception as error:
                payload = {"ok": False, "error": str(error)}
            self.history_action_finished.emit(payload)

        threading.Thread(
            target=run,
            name="voiceflow-history-action",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_history_action(self, payload):
        self._history_action_in_progress = False
        if not payload.get("ok"):
            self._set_status_badge("操作失败", attention=True)
            return
        status = payload.get("status", "unknown")
        label = self._output_status_label(status)
        self._set_status_badge(label, attention=label in {"失败", "未知"})

    def _refresh_recovery(self):
        self._apply_recovery_sessions(self.recovery_store.list_recoverable())

    def _apply_recovery_sessions(self, sessions):
        self.recovery_combo.clear()
        for session in sessions:
            minutes = session.sample_count / max(1, session.sample_rate) / 60
            created = datetime.fromtimestamp(session.created_at).strftime("%m月%d日 %H:%M")
            self.recovery_combo.addItem(
                f"{created} · {minutes:.1f} 分钟" if session.can_recover else f"{created} · 信息损坏",
                session.session_id,
            )
            index = self.recovery_combo.count() - 1
            self.recovery_combo.setItemData(
                index,
                session.preview_text,
                int(Qt.ItemDataRole.UserRole) + 1,
            )
            self.recovery_combo.setItemData(index, session, int(Qt.ItemDataRole.UserRole) + 2)
        self.recovery_summary.setText(f"有 {len(sessions)} 段尚未交付的录音")
        self.recovery_panel.setVisible(bool(sessions))
        self._update_recovery_selection()

    def _update_recovery_selection(self, *_args):
        session = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 2)
        available = session is not None and session.can_recover
        self.recover_button.setEnabled(available and not self._recovery_action_in_progress)
        if session is not None and not session.can_recover:
            detail = "录音信息损坏，原文件已保留。无法可靠识别，不再需要时可手动删除。"
        elif session is not None and session.partial:
            detail = "这段录音可能只保存了部分内容，末尾可能缺失。恢复后仍保留原录音，不再需要时可手动删除。"
        else:
            detail = "尚未交付的录音不会自动删除。恢复并复制成功后删除；不再需要时可手动删除。"
        self.recovery_detail.setText(detail)

    def _recover_selected_session(self):
        session_id = self.recovery_combo.currentData()
        session = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 2)
        if (
            not session_id
            or session is None or not session.can_recover
            or not self._on_recover_session
            or self._recovery_action_in_progress
        ):
            return
        self._recovery_action_in_progress = True
        self.recover_button.setEnabled(False)
        self.delete_recovery_button.setEnabled(False)
        self._set_status_badge("正在从本地录音恢复文字")

        def run():
            try:
                result = self._on_recover_session(str(session_id))
            except Exception as error:
                result = {"ok": False, "error": str(error)}
            result = dict(result or {})
            result["action"] = "recover"
            self.recovery_finished.emit(result)

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_recovery(self, result):
        self._recovery_action_in_progress = False
        self.recover_button.setEnabled(True)
        self.delete_recovery_button.setEnabled(True)
        self._update_recovery_selection()
        if result.get("action") == "delete":
            if result.get("ok"):
                self._set_status_badge("恢复录音已删除")
                self.refresh()
            else:
                self._set_status_badge("没有找到这段恢复录音")
            return
        if result.get("ok"):
            message = ("已恢复保存的部分，文字已复制。原录音仍保留" if result.get("partial") else
                       "文字已复制到剪贴板，原录音仍保留" if result.get("recording_retained") else
                       "恢复完成，文字已复制到剪贴板")
            self._set_status_badge(message)
            self._refresh_history()
            self._refresh_recovery()
        else:
            self._set_status_badge(f"恢复未完成：{result.get('error', '录音仍已保留')}")

    def _copy_recovery_preview(self):
        preview = self.recovery_combo.currentData(int(Qt.ItemDataRole.UserRole) + 1) or ""
        if not preview:
            self._set_status_badge("这段录音还没有可复制的预览文字")
            return
        self._copy_text(preview)

    def _delete_recovery(self):
        session_id = self.recovery_combo.currentData()
        if (
            not session_id
            or not self._on_delete_recovery
            or self._recovery_action_in_progress
        ):
            return
        answer = QMessageBox.question(
            self,
            "删除恢复录音",
            "这段本地恢复录音将被永久删除。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._recovery_action_in_progress = True
        self.recover_button.setEnabled(False)
        self.delete_recovery_button.setEnabled(False)
        self._set_status_badge("正在删除恢复录音")

        def run():
            try:
                ok = bool(self._on_delete_recovery(str(session_id)))
                result = {"ok": ok, "action": "delete"}
            except Exception as error:
                result = {"ok": False, "action": "delete", "error": str(error)}
            self.recovery_finished.emit(result)

        threading.Thread(
            target=run,
            name="voiceflow-recovery-delete",
            daemon=True,
        ).start()

    def _copy_all_visible(self):
        texts = []
        for i in range(self.history_list.count()):
            text = self.history_list.item(i).data(Qt.ItemDataRole.UserRole)
            if text:
                texts.append(text)
        if not texts:
            self._set_status_badge("无可复制")
            return
        self._copy_text("\n\n".join(texts))
