"""Chrisnov Media Toolkit — entry point.

A minimal PySide6 GUI wrapper around yt-dlp. See the README for features and setup.
"""

import sys
import ctypes
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.window import MainWindow
from app.icon import load_svg_icon


def main() -> None:
    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "icon.svg"
    if icon_path.exists():
        app.setWindowIcon(load_svg_icon(icon_path))
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "chrisnov.yt-downloader.1"
            )
        except Exception:
            pass
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
