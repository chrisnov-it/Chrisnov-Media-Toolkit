"""Chrisnov Media Toolkit — entry point.

A minimal PySide6 GUI wrapper around yt-dlp. See the README for features and setup.
"""

import sys
import ctypes
import os
from pathlib import Path

# Put bundled/local bin directories in PATH so that both shutil.which and
# yt-dlp find ffmpeg/ffprobe.
#   - frozen app: binaries bundled inside the exe (PyInstaller _MEIPASS)
#   - frozen app: bin/ folder next to the exe (NSIS optional FFmpeg component)
#   - dev runs:   project-local bin/
_bin_dirs: list[Path] = []
if hasattr(sys, "_MEIPASS"):
    _bin_dirs.append(Path(sys._MEIPASS) / "bin")
if getattr(sys, "frozen", False):
    _bin_dirs.append(Path(sys.executable).resolve().parent / "bin")
else:
    _bin_dirs.append(Path(__file__).resolve().parent / "bin")
for _bin_dir in _bin_dirs:
    if _bin_dir.exists():
        os.environ["PATH"] = str(_bin_dir) + os.pathsep + os.environ.get("PATH", "")

from PySide6.QtWidgets import QApplication

from app.theme import global_stylesheet, enable_high_dpi
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

    # Enable HiDPI scaling BEFORE QApplication is created — critical for
    # readable fonts on macOS (especially MacBook Air 2015 where 9pt is
    # too small without proper DPI scaling).
    enable_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName("Chrisnov Media Toolkit")
    app.setOrganizationName("Chrisnov IT Solutions")

    # Global stylesheet — palette-aware (adapts to Light/Dark Mode) with
    # platform-adjusted font sizes (11pt on macOS, 9pt on Linux/Windows).
    app.setStyleSheet(global_stylesheet())

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
