"""Chrisnov Media Toolkit — entry point.

A minimal PySide6 GUI wrapper around yt-dlp. See the README for features and setup.
"""

import sys
import ctypes
import os
from pathlib import Path

# Put bundled/local bin directory in PATH so that both shutil.which and yt-dlp find ffmpeg/ffprobe
if hasattr(sys, "_MEIPASS"):
    bin_dir = Path(sys._MEIPASS) / "bin"
else:
    bin_dir = Path(__file__).resolve().parent / "bin"

if bin_dir.exists():
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

from PySide6.QtWidgets import QApplication

from app.window import MainWindow
from app.icon import load_svg_icon


def main() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "chrisnov.media-toolkit.1"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Chrisnov Media Toolkit")
    app.setOrganizationName("Chrisnov IT Solutions")

    icon_path = Path(__file__).resolve().parent / "icon.svg"
    icon = None
    if icon_path.exists():
        icon = load_svg_icon(icon_path)
        app.setWindowIcon(icon)

    w = MainWindow()
    if icon is not None:
        w.setWindowIcon(icon)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
