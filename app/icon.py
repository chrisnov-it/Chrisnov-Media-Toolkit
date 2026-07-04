"""Icon loading helper — render SVG to a QIcon (cross-platform safe)."""

from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
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
