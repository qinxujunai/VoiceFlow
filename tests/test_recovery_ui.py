import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_recovery_selection_reports_partial_and_disables_unknown_format():
    from overlay_webview import _SettingsWindow
    from qt_compat import QApplication, QComboBox, QLabel, QPushButton, QWidget

    app = QApplication.instance() or QApplication([])
    fake = SimpleNamespace(recovery_combo=QComboBox(), recovery_summary=QLabel(),
                           recovery_detail=QLabel(), recovery_panel=QWidget(),
                           recover_button=QPushButton(), _recovery_action_in_progress=False)
    fake._update_recovery_selection = lambda *_args: _SettingsWindow._update_recovery_selection(fake)
    sessions = [SimpleNamespace(session_id="partial", sample_count=1600, sample_rate=16000,
                                created_at=1700000000, model="engine-secret", preview_text="",
                                partial=True, can_recover=True),
                SimpleNamespace(session_id="broken", sample_count=0, sample_rate=16000,
                                created_at=1700000000, model="engine-secret", preview_text="",
                                partial=True, can_recover=False)]
    _SettingsWindow._apply_recovery_sessions(fake, sessions)
    assert "engine-secret" not in fake.recovery_combo.itemText(0)
    assert "部分" in fake.recovery_detail.text()
    assert fake.recover_button.isEnabled()
    fake.recovery_combo.setCurrentIndex(1)
    fake._update_recovery_selection()
    assert not fake.recover_button.isEnabled()
    assert "损坏" in fake.recovery_detail.text()
    assert "保留" in fake.recovery_detail.text()
    fake.recovery_combo.close()
    fake.recovery_panel.close()
    app.processEvents()


def test_failed_delivery_never_claims_copied_or_saved():
    from capsule_native import NativeCapsuleView
    from qt_compat import QApplication

    app = QApplication.instance() or QApplication([])
    view = NativeCapsuleView()
    view.present("delivery", ["delivery_failed", 1])
    assert view.state.mode == "error"
    assert "未完成" in view.state.text
    assert "已复制" not in view.accessibleName()
    assert "已保存" not in view.accessibleName()
    view.close()
    app.processEvents()
