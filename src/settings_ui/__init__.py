"""Settings window pieces, one module per page.

`overlay_webview._SettingsWindow` composes these mixins with QMainWindow; it owns construction,
navigation and window events. Each mixin holds one page's widgets and behaviour; method bodies
use `self` exactly as before the split (2026-10-22), so behaviour is unchanged.
"""
