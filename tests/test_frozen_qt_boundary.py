from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_frozen_qt import check_native_qt_package


@pytest.mark.parametrize("name", ["Qt6Qml.dll", "Qt6Quick.dll", "Qt6VirtualKeyboard.dll", "Qt6Pdf.dll",
                                  "QtWebEngineProcess.exe", "qpdf.dll", "qtvirtualkeyboardplugin.dll"])
def test_native_package_rejects_unexpected_renderer_dependencies(tmp_path, name):
    (tmp_path / name).write_bytes(b"fixture")
    with pytest.raises(ValueError, match="excluded"):
        check_native_qt_package(tmp_path)


def test_native_package_keeps_the_windows_platform_plugin(tmp_path):
    with pytest.raises(ValueError, match="platform plugin"):
        check_native_qt_package(tmp_path)
    plugin = tmp_path / "PySide6/plugins/platforms/qwindows.dll"
    plugin.parent.mkdir(parents=True)
    plugin.write_bytes(b"fixture")
    assert check_native_qt_package(tmp_path)
