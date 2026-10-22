"""The 诊断 and 关于 pages: runtime checks, update check."""

import logging
import threading

from qt_compat import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    Qt,
    QSize,
    Slot,
)

from tray_icon import TRAY_ICON_IDLE, build_tray_icon
from runtime_paths import RuntimeMode
from version import APP_VERSION, display_version
from update_checker import check_latest_release
from runtime_services import format_diagnostics, run_runtime_diagnostics
from platform_utils import data_location_label, icon_asset_name, open_path, platform_label

logger = logging.getLogger("voiceflow.ui")


class DiagnosticsMixin:
    def _diagnostics_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addLayout(
            self._section_header(
                "诊断",
                "检查 VoiceFlow 是否已经准备好，并给出下一步。",
            )
        )
        header.addStretch(1)
        self.doctor_button = QPushButton("运行检查")
        self.doctor_button.setObjectName("primaryButton")
        self.doctor_button.setAccessibleName("运行 VoiceFlow 诊断")
        self.doctor_button.clicked.connect(self._run_doctor)
        header.addWidget(self.doctor_button)
        layout.addLayout(header)
        self.doctor_summary = QLabel("尚未运行检查")
        self.doctor_summary.setObjectName("diagnosticSummary")
        self.doctor_summary.setWordWrap(True)
        layout.addWidget(self.doctor_summary)
        self.doctor_list = QListWidget()
        self.doctor_list.setObjectName("diagnosticList")
        self.doctor_list.setAccessibleName("诊断结果")
        layout.addWidget(self.doctor_list, 1)
        actions = QHBoxLayout()
        copy_report = QPushButton("复制诊断报告")
        copy_report.clicked.connect(self._copy_diagnostics)
        open_data = QPushButton("打开数据目录")
        open_data.clicked.connect(lambda: open_path(self.paths.data_dir))
        actions.addWidget(copy_report)
        actions.addWidget(open_data)
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _about_page(self):
        page = QWidget()
        page.setObjectName("contentPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(16)

        about_hero = QWidget()
        about_hero.setObjectName("aboutHero")
        about_layout = QHBoxLayout(about_hero)
        about_layout.setContentsMargins(18, 16, 18, 16)
        about_layout.setSpacing(14)
        about_icon = QLabel()
        icon_path = str(
            self.paths.install_resource(f"assets/{icon_asset_name()}")
        )
        about_icon.setPixmap(
            build_tray_icon(TRAY_ICON_IDLE, icon_path).pixmap(48, 48)
        )
        about_copy = QVBoxLayout()
        about_copy.setSpacing(2)
        about_title = QLabel("VoiceFlow")
        about_title.setObjectName("aboutTitle")
        version = QLabel(f"版本 {display_version()} · {platform_label()}")
        version.setObjectName("aboutVersion")
        about_copy.addWidget(about_title)
        about_copy.addWidget(version)
        about_layout.addWidget(about_icon)
        about_layout.addLayout(about_copy)
        about_layout.addStretch(1)
        layout.addWidget(about_hero)

        privacy_panel = QWidget()
        privacy_panel.setObjectName("privacyPanel")
        privacy_layout = QVBoxLayout(privacy_panel)
        privacy_layout.setContentsMargins(18, 15, 18, 15)
        privacy_layout.setSpacing(5)
        privacy_title = QLabel("离线，是明确的产品边界")
        privacy_title.setObjectName("subsectionTitle")
        privacy = QLabel(
            "录音与识别默认只在本机完成。识别结果先进入剪贴板，"
            "即使自动粘贴没有落到输入框，仍可从剪贴板或本地历史找回。"
        )
        privacy.setObjectName("bodyText")
        privacy.setWordWrap(True)
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(privacy)
        layout.addWidget(privacy_panel)

        data_location = (
            data_location_label(self.paths.data_dir)
            if self.paths.mode is RuntimeMode.FROZEN
            else "项目目录（开发模式）"
        )
        data = QLabel(f"用户数据：{data_location}")
        data.setObjectName("sectionSubtitle")
        data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(data)
        actions = QHBoxLayout()
        open_data = QPushButton("打开数据目录")
        open_data.clicked.connect(lambda: open_path(self.paths.data_dir))
        open_licenses = QPushButton("查看第三方许可")
        open_licenses.clicked.connect(
            lambda: open_path(self.paths.install_resource("THIRD_PARTY_NOTICES.md"))
        )
        actions.addWidget(open_data)
        actions.addWidget(open_licenses)
        actions.addStretch(1)
        layout.addLayout(actions)

        update_row = QHBoxLayout()
        self.check_update_button = QPushButton("检查更新")
        self.check_update_button.clicked.connect(self._check_for_update)
        self.update_status = QLabel("仅在点击后检查；日常运行不会联网。")
        self.update_status.setObjectName("sectionSubtitle")
        self.update_status.setWordWrap(True)
        update_row.addWidget(self.check_update_button)
        update_row.addWidget(self.update_status, 1)
        layout.addLayout(update_row)
        layout.addStretch(1)
        return page

    def _check_for_update(self):
        if getattr(self, "_update_check_in_progress", False):
            return
        self._update_check_in_progress = True
        self.check_update_button.setEnabled(False)
        self.update_status.setText("正在核对稳定 Release 和 SHA-256…")

        def run():
            result = check_latest_release(APP_VERSION)
            self.update_finished.emit(result.as_dict())

        threading.Thread(
            target=run,
            name="voiceflow-update-check",
            daemon=True,
        ).start()

    @Slot(object)
    def _finish_update_check(self, result):
        self._update_check_in_progress = False
        self.check_update_button.setEnabled(True)
        state = result.get("state")
        if state == "available":
            url = result.get("installer_url", "")
            self.update_status.setText(
                f"{result.get('message', '发现新版本')} "
                f"<a href=\"{url}\">下载 VoiceFlow {result.get('latest_version', '')}</a>"
            )
            self.update_status.setOpenExternalLinks(True)
        else:
            self.update_status.setText(
                result.get("message", "更新检查未完成")
            )

    def _run_doctor(self):
        if self._doctor_in_progress:
            return
        self._doctor_in_progress = True
        self.doctor_summary.setText("正在检查 VoiceFlow…")
        self.doctor_list.clear()
        self.doctor_button.setEnabled(False)
        self.diagnostics_action.setEnabled(False)

        def run():
            try:
                result = run_runtime_diagnostics(self.paths)
                self.doctor_finished.emit(result)
            except Exception as error:
                self.doctor_finished.emit(
                    {
                        "ok": False,
                        "checks": [
                            {
                                "name": "diagnostics",
                                "status": "missing",
                                "detail": str(error),
                            }
                        ],
                    }
                )

        threading.Thread(target=run, daemon=True).start()

    @Slot(object)
    def _finish_doctor(self, result):
        self._doctor_in_progress = False
        self._last_diagnostics = result
        self.doctor_list.clear()
        labels = {
            "runtime_mode": "运行方式",
            "config": "配置",
            "config_parse": "配置格式",
            "data_directory": "数据目录",
            "logs_directory": "历史与日志",
            "knowledge_base": "词典",
            "active_model": "离线模型",
            "vad_model": "语音检测",
            "diagnostics": "诊断服务",
        }
        for check in result.get("checks", []):
            ok = check.get("status") == "ok"
            state = "正常" if ok else "需要处理"
            key = check.get("name")
            name = labels.get(key, key or "检查项")
            detail = check.get("detail", "")
            if key == "runtime_mode":
                detail = "已安装版本" if detail == "frozen" else "开发模式"
            elif key == "active_model" and detail == "sensevoice":
                detail = "SenseVoice 已验证"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, check)
            item.setSizeHint(QSize(0, 62))
            self.doctor_list.addItem(item)
            self.doctor_list.setItemWidget(
                item,
                self._diagnostic_card(state, name, detail, ok),
            )
        ok = bool(result.get("ok"))
        self.doctor_summary.setText(
            "一切正常，VoiceFlow 可以离线使用。"
            if ok
            else "发现需要处理的项目。请根据列表修复后再次检查。"
        )
        self.doctor_button.setEnabled(True)
        self.diagnostics_action.setEnabled(True)
        self._set_status_badge(
            "检查完成" if ok else "需要处理",
            attention=not ok,
        )

    def _diagnostic_card(self, state, name, detail, ok):
        card = QWidget()
        card.setObjectName("diagnosticCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(12)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel(name)
        title.setObjectName("diagnosticName")
        description = QLabel(detail)
        description.setObjectName("diagnosticDetail")
        description.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(description)
        layout.addLayout(copy, 1)

        badge = QLabel(state)
        badge.setObjectName(
            "diagnosticOk" if ok else "diagnosticAttention"
        )
        layout.addWidget(badge)
        return card

    def _copy_diagnostics(self):
        if not self._last_diagnostics:
            self._set_status_badge("请先运行检查")
            return
        self._copy_text(format_diagnostics(self._last_diagnostics))
