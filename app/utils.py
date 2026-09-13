"""Small GUI helpers shared across the window tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_in_explorer(path: str) -> None:
    """Open *path* in the system file manager (only when it is a directory)."""
    if path and Path(path).is_dir():
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
