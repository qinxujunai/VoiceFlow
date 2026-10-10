"""Keep QtGui's native platform/IME plugins without unused rendering engines."""

from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
# These optional image/input plugins pull PDF and QML/Quick/VirtualKeyboard
# libraries into a Widgets application. Windows IME uses the qwindows platform.
binaries = [
    entry for entry in binaries
    if Path(entry[0]).name.casefold() not in {"qpdf.dll", "qtvirtualkeyboardplugin.dll"}
]
