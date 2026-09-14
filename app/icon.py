"""Icon loading helper — render SVG to a QIcon (cross-platform safe)."""

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer


def load_svg_icon(path: Path, size: int = 256) -> QIcon:
    """Render an SVG file to a QIcon. Returns an empty QIcon on failure."""
    try:
        data = QByteArray(path.read_bytes())
    except OSError:
        return QIcon()
    renderer = QSvgRenderer(data)
    if not renderer.isValid():
        return QIcon()
    pix = QPixmap(QSize(size, size))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Bundled tab icons (inline SVG — no asset files to ship with frozen builds)
# ---------------------------------------------------------------------------

# 24×24 line-art in the Feather style (stroke-based, MIT). The literal
# "__COLOR__" is replaced at render time with the current palette color,
# so the icons follow Light/Dark mode. Text glyphs were used before, but
# their rendering depends on whatever symbols the user's fonts happen to
# ship — e.g. the Video Converter's ▣ (U+25A3) showed up as a plain box
# on Linux Mint, and other glyphs risk tofu on other systems.
_TAB_ICON_SVGS = {
    "download": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" y1="3" x2="12" y2="15"/>'
        '</svg>'
    ),
    "audio": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 18V5l12-2v13"/>'
        '<circle cx="6" cy="18" r="3"/>'
        '<circle cx="18" cy="16" r="3"/>'
        '</svg>'
    ),
    "video": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="23 7 16 12 23 17 23 7"/>'
        '<rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>'
        '</svg>'
    ),
    "history": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>'
        '</svg>'
    ),
}


def tab_icon(name: str, color: str, size: int = 64) -> QIcon:
    """Render one of the bundled tab icons in the given palette color.

    Returns an empty QIcon for an unknown name or a failed render — callers
    should treat that as "no icon" rather than showing a broken glyph.
    """
    svg = _TAB_ICON_SVGS.get(name)
    if svg is None:
        return QIcon()
    data = QByteArray(svg.replace("__COLOR__", color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    if not renderer.isValid():
        return QIcon()
    pix = QPixmap(QSize(size, size))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


# Palette → icon color (kept here so icon.py owns everything icon-related)
def palette_icon_color(palette: QPalette) -> str:
    """Return the active windowText color of a palette as "#rrggbb"."""
    try:
        return palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText
        ).name()
    except (SystemError, RuntimeError, ValueError):
        return "#8a94a0"
