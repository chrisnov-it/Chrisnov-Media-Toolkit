"""Platform-aware theming: font scaling, Dark Mode detection, and stylesheets.

This module centralizes the app's visual theme so that:
- Font sizes are readable on macOS (where 9pt is too small)
- Dark Mode is detected and respected via Qt's palette system
- The global stylesheet uses palette() references instead of hardcoded hex
  colors, so it adapts automatically to system appearance changes

Usage in main.py:
    from app.theme import global_stylesheet, enable_high_dpi
    enable_high_dpi()
    app.setStyleSheet(global_stylesheet())

Usage in window.py:
    from app.theme import widget_stylesheet
    self.setStyleSheet(widget_stylesheet())
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette


def enable_high_dpi() -> None:
    """Enable HiDPI screen scaling before QApplication is created.

    Qt 6 always enables High-DPI scaling and High-DPI pixmaps — the two Qt 5
    application attributes are deprecated no-ops there and newer PySide6
    stubs stop exposing them, so each attribute is only set when it still
    exists. Keeps the call site in main.py valid on any Qt version.
    """
    # Must be set before QApplication is instantiated
    from PySide6.QtWidgets import QApplication
    for attr_name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(Qt.ApplicationAttribute, attr_name, None)
        if attr is not None:
            QApplication.setAttribute(attr, True)


def _base_font_size() -> str:
    """Return the base font size in points, platform-adjusted.

    macOS needs larger fonts than Linux/Windows due to different default
    DPI assumptions. The 2015 MacBook Air 13" reports 1280x800 (non-Retina)
    to the OS, so 9pt is genuinely too small there.
    """
    if sys.platform == "darwin":
        return "11pt"
    if sys.platform == "win32":
        return "9pt"
    return "9pt"  # Linux default (unchanged)


def _font_family() -> str:
    """Return a font-family stack with macOS-native fonts first."""
    if sys.platform == "darwin":
        return "\".SF NS Text\", \"-apple-system\", \"Segoe UI\", \"Noto Sans\", Arial, sans-serif"
    if sys.platform == "win32":
        return "\"Segoe UI\", \"Noto Sans\", Arial, sans-serif"
    return "\"Noto Sans\", \"Segoe UI\", Arial, sans-serif"  # Linux


def global_stylesheet() -> str:
    """Return the global QApplication stylesheet.

    Uses palette() references so it automatically adapts to Light/Dark mode.
    Sets the base font size platform-appropriately.
    """
    fs = _base_font_size()
    ff = _font_family()
    return f"""
* {{ font-family: {ff}; font-size: {fs}; }}
QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QListWidget,
QGroupBox, QTabWidget::pane, QRadioButton, QCheckBox {{
    color: palette(windowText);
}}
QWidget {{
    background-color: palette(window);
    color: palette(windowText);
}}
"""


def _palette_color(palette: QPalette, role: QPalette.ColorRole) -> str:
    """Extract a hex color string from a palette role.

    Falls back to a reasonable default if the palette is mid-update
    (SystemError during PaletteChange events).
    """
    try:
        c = palette.color(QPalette.ColorGroup.Active, role)
        return c.name()
    except (SystemError, RuntimeError, ValueError):
        # Fallback: use a generic gray to avoid crashes during theme transitions
        return "#8a94a0"


def widget_stylesheet(palette: QPalette | None = None) -> str:
    """Return MainWindow's widget stylesheet, palette-aware.

    Instead of hardcoding hex colors, this reads from the application palette
    so the UI adapts when the system switches between Light and Dark Mode.

    The palette provides:
    - Window / WindowText          → main background and text
    - Base / Text                  → input field backgrounds and text
    - Highlight / HighlightedText  → accent/selected colors
    - Mid / Button / ButtonText    → button backgrounds and text
    - Midlight / Dark              → borders and dividers
    """
    from PySide6.QtGui import QGuiApplication
    if palette is None:
        palette = QGuiApplication.palette()  # static: app palette, no instance needed

    window = _palette_color(palette, QPalette.ColorRole.Window)
    window_text = _palette_color(palette, QPalette.ColorRole.WindowText)
    base = _palette_color(palette, QPalette.ColorRole.Base)
    text = _palette_color(palette, QPalette.ColorRole.Text)
    highlight = _palette_color(palette, QPalette.ColorRole.Highlight)
    highlighted_text = _palette_color(palette, QPalette.ColorRole.HighlightedText)
    button = _palette_color(palette, QPalette.ColorRole.Button)
    button_text = _palette_color(palette, QPalette.ColorRole.ButtonText)
    mid = _palette_color(palette, QPalette.ColorRole.Mid)
    midlight = _palette_color(palette, QPalette.ColorRole.Midlight)
    dark_role = _palette_color(palette, QPalette.ColorRole.Dark)

    fs = _base_font_size()
    ff = _font_family()

    # Accent color for primary/danger buttons — use highlight in dark mode
    primary_bg = highlight
    primary_border = highlight
    primary_text = highlighted_text

    return f"""
QWidget {{
    font-family: {ff};
    font-size: {fs};
    background-color: {window};
    color: {window_text};
}}
QTabWidget::pane {{
    border: 1px solid {midlight};
    border-radius: 6px;
    background: {base};
}}
QTabBar::tab {{
    padding: 4px 10px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    background: {mid};
    color: {window_text};
    font-size: {fs};
}}
QTabBar::tab:selected {{
    background: {base};
    border: 1px solid {midlight};
    border-bottom-color: {base};
}}
QGroupBox {{
    border: 1px solid {midlight};
    border-radius: 6px;
    margin-top: 8px;
    padding: 8px 8px 6px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 3px;
}}
QLineEdit, QComboBox, QListWidget, QDoubleSpinBox, QSpinBox {{
    min-height: 26px;
    border: 1px solid {dark_role};
    border-radius: 5px;
    padding: 2px 6px;
    background: {base};
    color: {text};
    font-size: {fs};
}}
QPushButton {{
    min-height: 27px;
    padding: 3px 10px;
    border: 1px solid {mid};
    border-radius: 5px;
    background: {button};
    color: {button_text};
    font-size: {fs};
}}
QPushButton:hover {{
    background: {midlight};
}}
QPushButton:pressed {{
    background: {dark_role};
}}
QPushButton:disabled {{
    color: {mid};
    background: {mid};
}}
QPushButton#primaryButton {{
    color: {primary_text};
    border-color: {primary_border};
    background: {primary_bg};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background: {midlight};
}}
QPushButton#dangerButton {{
    color: {window_text};
    border-color: {midlight};
    background: transparent;
}}
QPushButton#dangerButton:hover {{
    background: {mid};
}}
QCheckBox, QRadioButton {{
    font-size: {fs};
    color: {window_text};
}}
QProgressBar {{
    min-height: 14px;
    max-height: 16px;
    border: 1px solid {dark_role};
    border-radius: 6px;
    text-align: center;
    background: {mid};
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: {highlight};
}}
QLabel#appNameLabel {{
    font-size: 13pt;
    font-weight: 700;
    color: {window_text};
}}
QLabel#versionLabel {{
    font-size: 8pt;
    color: {mid};
    padding-top: 2px;
}}
QPushButton#aboutButton {{
    font-size: 8pt;
    color: {window_text};
    border-color: {midlight};
    background: transparent;
    min-height: 24px;
    padding: 2px 8px;
}}
QPushButton#aboutButton:hover {{
    background: {mid};
}}
"""
