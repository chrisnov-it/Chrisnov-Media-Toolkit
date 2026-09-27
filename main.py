"""Chrisnov Media Toolkit — entry point.

A minimal PySide6 GUI wrapper around yt-dlp. See the README for features and setup.
"""

import contextlib
import ctypes
import os
import sys
import threading
import traceback
from datetime import datetime
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

from PySide6.QtWidgets import QApplication, QMessageBox

from app.icon import load_svg_icon
from app.settings import APP_NAME, ORG_NAME
from app.theme import enable_high_dpi, global_stylesheet
from app.window import MainWindow


def _install_excepthook() -> None:
    """Make unhandled exceptions visible instead of losing them.

    The Windows build is a windowed (no-console) exe, so everything Python
    prints to stderr is discarded: an uncaught exception — including one
    raised inside a Qt slot, which PySide6 routes through sys.excepthook —
    looked like the app silently stopping. The hook appends the traceback to
    ``~/.config/chrisnov-media-toolkit/crash.log`` and shows a short dialog,
    then chains to the previous hook so terminal runs still print the full
    traceback. Never raises: a failing hook would otherwise mask the very
    error it is trying to report.
    """
    default_hook = sys.excepthook

    def _hook(exc_type: type[BaseException], exc: BaseException, tb) -> None:
        report = "".join(traceback.format_exception(exc_type, exc, tb))
        log_path: Path | None = None
        try:
            from app.constants import CONFIG_DIR

            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = CONFIG_DIR / "crash.log"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n"
                    f"{report}"
                )
        except OSError:
            log_path = None  # unwritable config dir: the dialog still shows
        try:
            # Only on the GUI thread with a QApplication alive: the hook also
            # fires before the app exists (import-time failures) or from a
            # worker thread, where calling Qt would raise again.
            if (
                QApplication.instance() is not None
                and threading.current_thread() is threading.main_thread()
            ):
                where = (
                    f"\n\nDetails were written to:\n{log_path}"
                    if log_path else ""
                )
                QMessageBox.critical(
                    None, "Unexpected error",
                    f"{exc_type.__name__}: {exc}{where}",
                )
        except Exception:  # noqa: BLE001 — a failing dialog must not mask the error
            pass
        default_hook(exc_type, exc, tb)

    sys.excepthook = _hook


def main() -> None:
    # First thing: every later failure (including ones raised inside Qt
    # slots) must reach the dialog + crash.log instead of vanishing.
    _install_excepthook()

    if sys.platform == "win32":
        # Best-effort: an invalid AppUserModelID only costs taskbar grouping,
        # so a failure here must never stop the app from starting.
        with contextlib.suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "chrisnov.media-toolkit.1"
            )

    # Enable HiDPI scaling BEFORE QApplication is created — critical for
    # readable fonts on macOS (especially MacBook Air 2015 where 9pt is
    # too small without proper DPI scaling).
    enable_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

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
    # Safety net for quits that never send a close event (session logout):
    # cancel every worker. The normal window-close path additionally waits
    # for them in MainWindow.closeEvent before the loop exits.
    app.aboutToQuit.connect(w.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
