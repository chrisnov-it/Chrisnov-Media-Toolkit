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
# Bundled inline SVGs — tab icons + queue-status icons (no asset files to
# ship with frozen builds)
# ---------------------------------------------------------------------------

# 24×24 line-art in the Feather style (stroke-based, MIT). The literal
# "__COLOR__" is replaced at render time with a concrete color: the palette
# text color for tab icons (follows Light/Dark mode) or a fixed status
# color for the queue icons. Text glyphs were used before, but their
# rendering depends on whatever symbols the user's fonts happen to ship —
# e.g. the Video Converter's ▣ (U+25A3) showed up as a plain box on Linux
# Mint, and other glyphs risk tofu on other systems.
_BUNDLED_ICON_SVGS = {
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
    # Queue-row status marks (rendered in fixed colors, see STATUS_COLORS)
    "check": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"/>'
        '</svg>'
    ),
    "cross": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/>'
        '</svg>'
    ),
    "arrow-right": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
        ' viewBox="0 0 24 24" fill="none" stroke="__COLOR__"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="5" y1="12" x2="19" y2="12"/>'
        '<polygon points="12 5 19 12 12 19 12 5"/>'
        '</svg>'
    ),
}


def bundled_icon(name: str, color: str, size: int = 64) -> QIcon:
    """Render one of the bundled inline-SVG icons in the given color.

    Used for the tab icons (palette color) and the queue-status icons
    (fixed colors). Returns an empty QIcon for an unknown name or a
    failed render — callers should treat that as "no icon" rather than
    showing a broken glyph.
    """
    svg = _BUNDLED_ICON_SVGS.get(name)
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


# Fixed colors for queue-row status marks. Unlike the tab icons these do
# NOT follow the palette: green/red/amber must read the same in Light and
# Dark mode for the status to be scannable at a glance. Red matches the
# update-notice color used in the About dialog.
STATUS_COLORS = {
    "running": "#e0a816",   # amber
    "done": "#43a047",      # green
    "failed": "#e53e3e",    # red
}

_STATUS_ICON_NAMES = {
    "running": "arrow-right",
    "done": "check",
    "failed": "cross",
}


def queue_status_icon(status: str) -> QIcon:
    """Icon for a queue row's batch status: running / done / failed.

    Returns an empty QIcon for an unknown status so callers can set it
    unconditionally.
    """
    name = _STATUS_ICON_NAMES.get(status)
    color = STATUS_COLORS.get(status)
    if name is None or color is None:
        return QIcon()
    return bundled_icon(name, color)
