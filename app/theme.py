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
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit, QWidget

from .constants import NEUTRAL_GRAY


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


def _base_font_points() -> int:
    """Base UI font size in points, platform-adjusted.

    macOS needs larger fonts than Linux/Windows due to different default
    DPI assumptions. The 2015 MacBook Air 13" reports 1280x800 (non-Retina)
    to the OS, so 9pt is genuinely too small there.
    """
    if sys.platform == "darwin":
        return 11
    return 9  # Windows and Linux


def _base_font_size() -> str:
    """The base font size as a CSS length ("9pt")."""
    return f"{_base_font_points()}pt"


def small_font_size() -> str:
    """Secondary text, one step below the base ("8pt" at the default size).

    Placeholders, hints and captions. Derived from the base instead of a
    hardcoded literal (P3) so the hierarchy survives a different platform
    base — a fixed "8pt" would nearly equal the 11pt macOS base.
    """
    return f"{_base_font_points() - 1}pt"


def tiny_font_size() -> str:
    """The smallest hint text, two steps below the base ("7pt" by default).

    Legends and footer links — same reasoning as small_font_size().
    """
    return f"{_base_font_points() - 2}pt"


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
        return NEUTRAL_GRAY


def _blend(fg: str, bg: str, t: float) -> str:
    """Linear blend of two ``#rrggbb`` colors: t=0 → *fg*, t=1 → *bg*.

    Used to derive a disabled-text color that is guaranteed to differ from
    both the normal text and the button background in *any* palette (light,
    dark, or constructed), unlike the palette's Disabled group — Qt palettes
    often leave that group mirroring Active, which would make a disabled
    primary button look enabled.
    """
    out = "#"
    for i in (1, 3, 5):
        a = int(fg[i:i + 2], 16)
        b = int(bg[i:i + 2], 16)
        out += f"{round(a + (b - a) * t):02x}"
    return out


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio between two ``#rrggbb`` colors (1.0 - 21.0)."""
    def lum(h: str) -> float:
        return (
            0.2126 * _channel(int(h[1:3], 16))
            + 0.7152 * _channel(int(h[3:5], 16))
            + 0.0722 * _channel(int(h[5:7], 16))
        )

    la, lb = lum(fg), lum(bg)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def muted_color(fg: str, bg: str, *, min_ratio: float = 4.5) -> str:
    """The *most muted* blend of *fg* toward *bg* that still reaches
    *min_ratio*:1 contrast against *bg*.

    Secondary text (search placeholder, About credit links) is meant to sit
    back visually, but the muted grays used for it measured ~2.8-4.0:1 —
    below WCAG AA. Blending in 5% steps and stopping before the ratio drops
    keeps the visual hierarchy while guaranteeing readability in whatever
    palette the app is running in.
    """
    best = fg
    for step in range(21):  # t = 0.00 … 1.00
        candidate = _blend(fg, bg, step / 20)
        if contrast_ratio(candidate, bg) < min_ratio:
            break
        best = candidate
    return best


def with_aa_placeholder(palette: QPalette) -> QPalette:
    """Copy of *palette* with an AA-compliant ``PlaceholderText`` role.

    QLineEdit draws its placeholder from the palette's PlaceholderText role
    (stylesheets have no placeholder pseudo-element), and the system default
    measured ~4.0:1 on the field background. Only that one role changes, so
    the rest of the widget palette — and the stylesheet, which reads the
    *application* palette — stay untouched.
    """
    out = QPalette(palette)
    try:
        text = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text).name()
        base = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Base).name()
    except (SystemError, RuntimeError, ValueError):
        return out
    out.setColor(
        QPalette.ColorRole.PlaceholderText, QColor(muted_color(text, base))
    )
    return out


def apply_aa_placeholder(widget: QWidget) -> int:
    """Give every text-entry widget under *widget* an AA placeholder color.

    Qt hands widgets an **explicit palette snapshot** when they are styled
    (verified on native Windows: every QLineEdit reported WA_SetPalette with
    the raw system palette), so a single ``setPalette()`` on the window never
    reaches them — the search placeholder stayed at ~4.0:1 until the role was
    set on the edits themselves. The role is written to all three color
    groups, because an unfocused window renders with the Inactive group.
    Returns the number of widgets updated.
    """
    targets: list[QWidget] = [
        *widget.findChildren(QLineEdit),
        *widget.findChildren(QTextEdit),
        *widget.findChildren(QPlainTextEdit),
    ]
    updated = 0
    for edit in targets:
        pal = edit.palette()
        try:
            text = pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text).name()
            base = pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Base).name()
        except (SystemError, RuntimeError, ValueError):
            continue  # palette mid-update: leave the default alone
        color = QColor(muted_color(text, base))
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                      QPalette.ColorGroup.Disabled):
            pal.setColor(group, QPalette.ColorRole.PlaceholderText, color)
        edit.setPalette(pal)
        updated += 1
    return updated


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

    # Disabled buttons: mid-on-mid rendered an invisible label (1.00:1).
    # Use the normal button surface with text blended 45% toward it —
    # measured ≥4.5:1 (WCAG AA) in both light and dark palettes while still
    # reading as "muted". An explicit #primaryButton:disabled rule is also
    # required: Qt gives ID selectors higher specificity than :disabled, so
    # the blue primary rule otherwise wins and the button looks enabled.
    disabled_text = _blend(button_text, button, 0.45)

    # Frozen controls (batch) must also *look* disabled: the stylesheet sets
    # an unconditional `color:` on fields/checkboxes/radios, which overrides
    # the palette's disabled text color, so a frozen combo or checkbox used
    # to render at full strength and read as editable. Blend toward the
    # *window* so one color clears 4.5:1 on both backgrounds it is used on
    # (field surface {base} → 5.3/5.8:1, widget surface {window} →
    # 4.6/4.9:1 in light/dark) while visibly muting.
    disabled_field = _blend(window_text, window, 0.45)

    fs = _base_font_size()
    small = small_font_size()
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
QLineEdit:disabled {{
    color: {disabled_field};
}}
QComboBox:disabled {{
    color: {disabled_field};
}}
QSpinBox:disabled {{
    color: {disabled_field};
}}
QDoubleSpinBox:disabled {{
    color: {disabled_field};
}}
QListWidget::item {{
    border-bottom: 1px solid {midlight};
    padding: 2px 0px;
}}
QListWidget::item:selected {{
    background: {highlight};
    color: {highlighted_text};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {mid};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed {{
    background: {highlight};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    border: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {mid};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed {{
    background: {highlight};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    border: none;
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
    color: {disabled_text};
    background: {button};
    border-color: {midlight};
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
QPushButton#primaryButton:disabled {{
    color: {disabled_text};
    background: {button};
    border-color: {midlight};
    font-weight: 600;
}}
QPushButton#dangerButton {{
    color: {window_text};
    border-color: {midlight};
    background: transparent;
}}
QPushButton#dangerButton:hover {{
    background: {mid};
}}
QPushButton#dangerButton:disabled {{
    color: {disabled_text};
    background: transparent;
    border-color: {midlight};
}}
QCheckBox, QRadioButton {{
    font-size: {fs};
    color: {window_text};
}}
QCheckBox:disabled {{
    color: {disabled_field};
}}
QRadioButton:disabled {{
    color: {disabled_field};
}}
/* Explicit indicator box: the Windows style drew *no* indicator for the
   checked radio (a selected CBR/normalization mode was invisible in light
   mode — only the unchecked circles showed), so the indicator is painted by
   the stylesheet instead of delegated to the platform style. */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {mid};
    border-radius: 7px;
    background: {base};
}}
QRadioButton::indicator:hover {{
    border-color: {highlight};
}}
QRadioButton::indicator:checked {{
    border: 1px solid {highlight};
    background: {highlight};
}}
QRadioButton:disabled::indicator {{
    border-color: {midlight};
    background: {base};
}}
QRadioButton:disabled::indicator:checked {{
    border-color: {mid};
    background: {mid};
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
    font-size: {small};
    color: {mid};
    padding-top: 2px;
}}
QPushButton#aboutButton {{
    font-size: {small};
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
