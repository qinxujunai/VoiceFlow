"""The 词典 page: categories, search, bulk delete with undo, save."""

import logging
import os
import threading
import copy

from qt_compat import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QListView,
    QAbstractItemView,
    QComboBox,
    QMessageBox,
    Qt,
    QSize,
    Slot,
)

from platform_utils import open_path

logger = logging.getLogger("voiceflow.ui")


class DictionaryMixin:
    def _dictionary_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(14)
        layout.addLayout(
            self._section_header(
                "词典",
                "英文术语会规范大小写；明确纠错不会改变你的原意。",
            )
        )

        self.dictionary_section = QComboBox()
        self.dictionary_section.setAccessibleName("词典分区")
        self.dictionary_section.addItem("内置 AI 术语", "builtin-ai.txt")
        self.dictionary_section.addItem("专有词", "user-dictionary.txt")
        self.dictionary_section.addItem("常用短语", "phrases.txt")
        self.dictionary_section.addItem("确定性纠错", "corrections.txt")
        self.dictionary_section.setMinimumWidth(180)
        self.dictionary_search = QLineEdit()
        self.dictionary_search.setPlaceholderText("搜索当前分类")
        self.dictionary_search.setAccessibleName("搜索词典")
        self.dictionary_search.setClearButtonEnabled(True)
        self.dictionary_search.textChanged.connect(self._filter_dictionary)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        filter_row.addWidget(self.dictionary_section)
        filter_row.addWidget(self.dictionary_search, 1)
        layout.addLayout(filter_row)
        dictionary_card = QWidget()
        dictionary_card.setObjectName("groupCard")
        card_layout = QVBoxLayout(dictionary_card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        add_row = QHBoxLayout()
        self._dictionary_add_row = add_row
        self.dictionary_input = QLineEdit()
        self.dictionary_input.setAccessibleName("新增词典条目")
        self.dictionary_input.setPlaceholderText("添加专有词")
        self.dictionary_input.returnPressed.connect(self._add_dictionary_entry)
        self.dictionary_correct_input = QLineEdit()
        self.dictionary_correct_input.setPlaceholderText("应改为")
        self.dictionary_correct_input.setAccessibleName("正确词")
        self.dictionary_correct_input.returnPressed.connect(self._add_dictionary_entry)
        self.dictionary_correct_input.hide()
        self.dictionary_add_button = QPushButton("添加")
        self.dictionary_add_button.setObjectName("primaryButton")
        self.dictionary_add_button.clicked.connect(self._add_dictionary_entry)
        add_row.addWidget(self.dictionary_input, 1)
        add_row.addWidget(self.dictionary_correct_input, 1)
        add_row.addWidget(self.dictionary_add_button)
        card_layout.addLayout(add_row)

        self.dictionary_hint = QLabel("每项单独一行，双击可以修改。")
        self.dictionary_hint.setObjectName("rowNote")
        self.dictionary_hint.setWordWrap(True)
        card_layout.addWidget(self.dictionary_hint)

        self.dictionary_list = QListWidget()
        self.dictionary_list.setObjectName("dictionaryList")
        self.dictionary_list.setAccessibleName("词典条目")
        self.dictionary_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.dictionary_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.dictionary_list.setWrapping(True)
        self.dictionary_list.setSpacing(8)
        self.dictionary_list.setMinimumHeight(180)
        self.dictionary_list.itemChanged.connect(self._dictionary_item_changed)
        card_layout.addWidget(self.dictionary_list, 1)
        layout.addWidget(dictionary_card, 1)

        self.dictionary_count = QLabel("0 项")
        self.dictionary_count.setObjectName("historyMeta")

        self.dictionary_section.currentIndexChanged.connect(
            self._change_dictionary_section
        )
        self._active_dictionary_filename = self.dictionary_section.currentData()

        note = QLabel(
            "词典只保存在这台电脑。纠错只按你指定的两个词替换，不改写你的意思。"
        )
        note.setObjectName("rowNote")
        note.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.dictionary_remove_button = QPushButton("删除所选")
        self.dictionary_remove_button.setObjectName("textButton")
        self._dictionary_actions = actions
        self.dictionary_remove_button.clicked.connect(
            self._remove_dictionary_entries
        )
        save = self.dictionary_save_button = QPushButton("保存词典")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save_dictionary)
        open_folder = QPushButton("打开词典目录")
        open_folder.setObjectName("textButton")
        open_folder.clicked.connect(
            lambda: open_path(self.paths.knowledge_dir)
        )
        selection_actions = QHBoxLayout()
        selection_actions.setSpacing(6)
        self._dictionary_selection_actions = selection_actions
        selection_actions.addWidget(self.dictionary_count)
        self.dictionary_select_button = QPushButton("全选搜索结果")
        self.dictionary_select_button.setObjectName("textButton")
        self.dictionary_select_button.clicked.connect(self._select_dictionary_results)
        self.dictionary_clear_button = QPushButton("清空当前分类")
        self.dictionary_clear_button.setObjectName("destructiveTextButton")
        self.dictionary_clear_button.clicked.connect(self._clear_dictionary)
        selection_actions.addWidget(self.dictionary_select_button)
        selection_actions.addWidget(self.dictionary_remove_button)
        self.dictionary_undo_button = QPushButton("撤销删除")
        self.dictionary_undo_button.setObjectName("textButton")
        self.dictionary_undo_button.clicked.connect(self._undo_dictionary_delete)
        self.dictionary_undo_button.hide()
        selection_actions.addWidget(self.dictionary_undo_button)
        selection_actions.addWidget(self.dictionary_clear_button)
        selection_actions.addStretch(1)
        layout.addLayout(selection_actions)
        actions.addWidget(note, 1)
        actions.addWidget(open_folder)
        actions.addWidget(save)
        layout.addLayout(actions)
        return self._scrollable_page(page)

    def _read_dictionary_entries(self):
        entries = {}
        for filename in (
            "builtin-ai.txt",
            "user-dictionary.txt",
            "phrases.txt",
            "corrections.txt",
        ):
            try:
                raw = self._dictionary_path(filename).read_text(encoding="utf-8")
                entries[filename] = [
                    line
                    for line in raw.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
            except FileNotFoundError:
                entries[filename] = []
        return entries

    def _dictionary_path(self, filename):
        return self.paths.knowledge_dir / filename

    def _load_dictionary(self):
        self._dictionary_entries = self._read_dictionary_entries()
        self._active_dictionary_filename = self.dictionary_section.currentData()
        self._render_dictionary_section()

    def _store_dictionary_section(self):
        filename = self._active_dictionary_filename
        if not filename or not hasattr(self, "dictionary_list"):
            return
        if filename == "builtin-ai.txt":
            return
        entries = []
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            value = (item.data(Qt.ItemDataRole.UserRole) or item.text()).strip()
            if value and value not in entries:
                entries.append(value)
        if entries != self._dictionary_entries.get(filename, []):
            self._dictionary_dirty = True
        self._dictionary_entries[filename] = entries

    def _render_dictionary_section(self):
        filename = self._active_dictionary_filename
        if not filename or not hasattr(self, "dictionary_list"):
            return
        self.dictionary_list.blockSignals(True)
        self.dictionary_list.clear()
        readonly = filename == "builtin-ai.txt"
        corrections = filename == "corrections.txt"
        self.dictionary_list.setViewMode(QListView.ViewMode.ListMode if corrections else QListView.ViewMode.IconMode)
        for value in self._dictionary_entries.get(filename, []):
            item = QListWidgetItem(value.replace("=", "  →  ", 1) if corrections else value)
            if corrections:
                item.setData(Qt.ItemDataRole.UserRole, value)
            if not readonly:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                if not corrections:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            if not corrections:
                item.setSizeHint(QSize(min(300, max(72, self.dictionary_list.fontMetrics().horizontalAdvance(value) + 46)), 40))
            self.dictionary_list.addItem(item)
        self.dictionary_list.blockSignals(False)
        self.dictionary_input.setEnabled(not readonly)
        self.dictionary_add_button.setEnabled(not readonly)
        self.dictionary_remove_button.setEnabled(not readonly)
        self.dictionary_select_button.setEnabled(not readonly)
        self.dictionary_clear_button.setEnabled(not readonly)
        self.dictionary_correct_input.setVisible(corrections)
        if readonly:
            self.dictionary_input.setPlaceholderText("内置术语不可编辑")
            self.dictionary_hint.setText(
                "内置术语随 VoiceFlow 更新；识别到相同英文时会规范大小写。"
            )
        elif corrections:
            self.dictionary_input.setPlaceholderText("识别成")
            self.dictionary_hint.setText("明确指定应改为哪个词。修改时删除旧项，再添加新项。")
        elif filename == "phrases.txt":
            self.dictionary_input.setPlaceholderText("添加常用短语")
            self.dictionary_hint.setText("添加经常完整说出的短语，双击可以修改。")
        else:
            self.dictionary_input.setPlaceholderText("添加专有词")
            self.dictionary_hint.setText(
                "添加人名、品牌或项目名；英文会规范大小写，误识别请使用确定性纠错。"
            )
        self._update_dictionary_count()
        self._filter_dictionary()

    def _change_dictionary_section(self, _index):
        self._store_dictionary_section()
        self._active_dictionary_filename = self.dictionary_section.currentData()
        self._render_dictionary_section()

    def _valid_dictionary_entry(self, value):
        if self._active_dictionary_filename == "builtin-ai.txt":
            return False
        if self._active_dictionary_filename != "corrections.txt":
            return bool(value)
        if value.count("=") != 1:
            return False
        wrong, correct = (part.strip() for part in value.split("=", 1))
        return bool(wrong and correct)

    def _add_dictionary_entry(self):
        value = self.dictionary_input.text().strip()
        if self._active_dictionary_filename == "corrections.txt" and self.dictionary_correct_input.text().strip():
            value += "=" + self.dictionary_correct_input.text().strip()
        if not self._valid_dictionary_entry(value):
            message = (
                "请使用“错误词=正确词”"
                if self._active_dictionary_filename == "corrections.txt"
                else "请输入内容"
            )
            self._set_status_badge(message, attention=True)
            return
        existing = {
            (self.dictionary_list.item(index).data(Qt.ItemDataRole.UserRole) or self.dictionary_list.item(index).text()).strip()
            for index in range(self.dictionary_list.count())
        }
        if value in existing:
            self._set_status_badge("词典中已有这一项")
            return
        self._store_dictionary_section()
        self._dictionary_entries[self._active_dictionary_filename].append(value)
        self._dictionary_dirty = True
        self._render_dictionary_section()
        self.dictionary_input.clear()
        self.dictionary_correct_input.clear()
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已添加，保存后生效")

    def _remove_dictionary_entries(self):
        if self._active_dictionary_filename == "builtin-ai.txt":
            self._set_status_badge("内置术语不可删除")
            return
        selected = [self.dictionary_list.item(index) for index in range(self.dictionary_list.count())
                    if self.dictionary_list.item(index).checkState() == Qt.CheckState.Checked]
        if not selected:
            selected = self.dictionary_list.selectedItems()
        if not selected:
            self._set_status_badge("请选择要删除的内容")
            return
        self._remember_dictionary_delete()
        for item in selected:
            self.dictionary_list.takeItem(self.dictionary_list.row(item))
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已移除，保存后生效")

    def _dictionary_item_changed(self, item):
        value = (item.data(Qt.ItemDataRole.UserRole) or item.text()).strip()
        if not self._valid_dictionary_entry(value):
            self._set_status_badge("这一项格式不正确", attention=True)
            return
        self.dictionary_list.blockSignals(True)
        if self._active_dictionary_filename != "corrections.txt":
            item.setText(value)
        self.dictionary_list.blockSignals(False)
        self._store_dictionary_section()
        self._update_dictionary_count()

    def _update_dictionary_count(self):
        if hasattr(self, "dictionary_count"):
            selected = sum(self.dictionary_list.item(index).checkState() == Qt.CheckState.Checked for index in range(self.dictionary_list.count()))
            self.dictionary_count.setText(f"{self.dictionary_list.count()} 项 · 已选 {selected} 项")

    def _filter_dictionary(self, *_args):
        query = self.dictionary_search.text().casefold().strip()
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            item.setHidden(query not in item.text().casefold())

    def _select_dictionary_results(self):
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            if not item.isHidden() and self._active_dictionary_filename != "builtin-ai.txt":
                item.setCheckState(Qt.CheckState.Checked)

    def _remember_dictionary_delete(self):
        self._store_dictionary_section()
        self._dictionary_undo = (self._active_dictionary_filename, list(self._dictionary_entries[self._active_dictionary_filename]))
        self.dictionary_undo_button.show()

    def _undo_dictionary_delete(self):
        if self._dictionary_undo:
            filename, entries = self._dictionary_undo
            self._store_dictionary_section()
            current = self._dictionary_entries[filename]
            self._dictionary_entries[filename] = entries + [value for value in current if value not in entries]
            self._dictionary_dirty = True
            self._dictionary_undo = None
            self.dictionary_undo_button.hide()
            if filename == self._active_dictionary_filename:
                self._render_dictionary_section()
            self._set_status_badge("已撤销删除，保存词典后生效")

    def _clear_dictionary(self):
        if self._active_dictionary_filename == "builtin-ai.txt":
            return
        count = self.dictionary_list.count()
        if not count or QMessageBox.question(self, "清空当前分类", f"清空“{self.dictionary_section.currentText()}”的 {count} 项？其他分类不受影响。") != QMessageBox.StandardButton.Yes:
            return
        self._remember_dictionary_delete()
        self.dictionary_list.clear()
        self._store_dictionary_section()
        self._update_dictionary_count()
        self._set_status_badge("已清空当前分类，可以撤销；保存词典后生效")

    def _save_dictionary(self):
        if self._dictionary_save_in_progress:
            return
        self._store_dictionary_section()
        self._dictionary_generation += 1
        entries = copy.deepcopy(self._dictionary_entries)
        self._dictionary_save_in_progress = True
        self.dictionary_save_button.setEnabled(False)
        self._set_status_badge("正在保存词典")

        def run():
            originals, written = {}, []
            try:
                if any(not self._valid_correction(value) for value in entries.get("corrections.txt", [])):
                    raise ValueError("请检查纠错的两个词")
                for filename, values in entries.items():
                    if filename == "builtin-ai.txt":
                        continue
                    path = self._dictionary_path(filename)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    originals[path] = path.read_bytes() if path.exists() else None
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text("\n".join(values) + ("\n" if values else ""), encoding="utf-8")
                    os.replace(temporary, path)
                    written.append(path)
                result = {"ok": True, "entries": entries}
            except Exception as error:
                for path in reversed(written):
                    try:
                        if originals[path] is None:
                            path.unlink()
                        else:
                            temporary = path.with_suffix(".rollback.tmp")
                            temporary.write_bytes(originals[path])
                            os.replace(temporary, path)
                    except OSError:
                        logger.exception("dictionary rollback failed")
                result = {"ok": False, "error": str(error)}
            self.dictionary_finished.emit(result)

        threading.Thread(target=run, name="voiceflow-dictionary-save", daemon=True).start()

    @Slot(object)
    def _finish_dictionary_save(self, result):
        self._dictionary_generation += 1
        self._dictionary_save_in_progress = False
        self.dictionary_save_button.setEnabled(True)
        if result["ok"]:
            self._dictionary_dirty = self._dictionary_entries != result["entries"]
            self._set_status_badge("词典已保存" if not self._dictionary_dirty else "词典已保存；新的更改尚未保存")
        else:
            self._set_status_badge(f"词典保存失败，草稿已保留：{result['error']}", attention=True)

    @staticmethod
    def _valid_correction(value):
        if value.count("=") != 1:
            return False
        wrong, correct = (part.strip() for part in value.split("=", 1))
        return bool(wrong and correct)
