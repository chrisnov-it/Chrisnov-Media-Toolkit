"""GUI window for Chrisnov Media Toolkit — a thin shell around the tabs.

The window owns only cross-cutting concerns: the tab layout, drag-and-drop
routing, system-theme changes, and the About dialog. Each tab (downloader,
audio converter, video converter, history) is its own widget class:

    app/download_tab.py      — URL queue + download workers (BatchState)
    app/convert_tab.py       — audio conversion queue (ConvertWorker)
    app/video_convert_tab.py — video conversion queue (VideoConvertWorker)
    app/history_tab.py       — history list/search/re-queue

Cross-tab wiring:
    download_tab.history_changed  -> history_tab.refresh
    history_tab.requeue_requested -> MainWindow._requeue_download
                                     -> download_tab.requeue
    clean tags: converter tabs read them via download_tab.clean_tags_text
"""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .constants import APP_VERSION, CONFIG_DIR
from .convert_tab import AudioConverterTab
from .download_tab import DownloadTab
from .ffmpeg_utils import find_ffmpeg, find_ffprobe, probe_version
from .history import DownloadHistory
from .history_tab import HistoryTab
from .icon import bundled_icon, palette_icon_color
from .settings import AppSettings
from .theme import apply_aa_placeholder, muted_color, widget_stylesheet, with_aa_placeholder
from .update_check import UpdateCheckWorker
from .video_convert_tab import VideoConvertTab
from .worker_tracking import WorkerTracker

#: How long a closing window waits for cancelled workers to exit before
#: falling back to terminate(). Cooperative cancel normally takes well under
#: a second (ffmpeg children are killed, yt-dlp aborts at its next hook).
SHUTDOWN_TIMEOUT_S = 10.0


class _FFmpegVersionWorker(QThread):
    """Resolve the FFmpeg version off the GUI thread for the About dialog.

    ``probe_version()`` spawns a subprocess with a 5 s timeout; running it
    while the dialog was being built froze the About window for up to five
    seconds on a cold or antivirus-scanned disk. Same reasoning as
    ``UpdateCheckWorker``: the dialog must never wait for an external
    process. Emits ``ready`` with ``"n/a"`` when no usable binary is found.
    """

    ready = Signal(str)

    def run(self) -> None:
        # Same resolution order as the workers: bundled ffmpeg first, then
        # ffprobe (same build) as a fallback.
        for finder in (find_ffmpeg, find_ffprobe):
            try:
                binary = finder()
            except FileNotFoundError:
                continue
            version = probe_version(binary)
            if version:
                self.ready.emit(version)
                return
        self.ready.emit("n/a")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        #: Title without any batch marker — what a new batch (and the app
        #: at rest) shows; batch_finished appends "✓ Done (x/y)".
        self._base_title = f"Chrisnov Media Toolkit v{APP_VERSION}"
        self.setWindowTitle(self._base_title)
        self.setMinimumSize(700, 480)
        # 700 (not 620): the Downloader tab's natural height is ~605 px, so
        # at 620 the progress bar and status line sat below the fold (65 px
        # of scroll) — the batch's only progress feedback required scrolling
        # to see. Everything fits without scrolling at the default size now;
        # smaller windows still scroll via the per-tab QScrollArea.
        self.resize(900, 700)
        self.setAcceptDrops(True)

        self._settings = AppSettings()
        self._tracker = WorkerTracker()
        # (label, installed version) of the About dialog's update notice, set
        # while the dialog is open so a late worker answer can be dropped.
        self._about_update_target: tuple[QLabel, str] | None = None
        # Same holder for the FFmpeg version row filled in by the background
        # probe (see _start_ffmpeg_probe).
        self._about_ffmpeg_label: QLabel | None = None
        # Shutdown state — see closeEvent()/shutdown() below.
        self._shutting_down = False
        self._shutdown_deadline = 0.0
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(100)
        self._shutdown_timer.timeout.connect(self._retry_close)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.history = DownloadHistory(CONFIG_DIR / "download-history.json")
        self.history.load()

        self._build_ui()

        # Cross-tab wiring. The Downloader tab must be constructed first —
        # the converter tabs receive its clean_tags_text callable. Both
        # converter tabs append to the shared history, so their
        # history_changed also refreshes the History tab.
        self.download_tab.history_changed.connect(self.history_tab.refresh)
        self.audio_tab.history_changed.connect(self.history_tab.refresh)
        self.video_tab.history_changed.connect(self.history_tab.refresh)
        self.history_tab.requeue_requested.connect(self._requeue_download)
        # Batch lifecycle → window title (P2: a finished batch used to leave
        # no trace: no tray, no flash, no title change).
        for tab in (self.download_tab, self.audio_tab, self.video_tab):
            tab.batch_started.connect(self._on_batch_started)
            tab.batch_finished.connect(self._on_batch_finished)

        # AA-compliant placeholder text for every QLineEdit in the window.
        # Set on the window (not the app) so children inherit it and the
        # system theme change below can simply re-apply it — and on the
        # edits themselves, since Qt keeps explicit palette snapshots on
        # them (a window-level setPalette() alone never reaches them).
        self.setPalette(with_aa_placeholder(self.palette()))
        apply_aa_placeholder(self)

        self.history_tab.refresh()

    # ------------------------------------------------------------------ #
    #  Batch completion → window title + taskbar attention                #
    # ------------------------------------------------------------------ #

    def _on_batch_started(self) -> None:
        """Drop any "✓ Done" marker as soon as a new batch is running."""
        if self.windowTitle() != self._base_title:
            self.setWindowTitle(self._base_title)

    def _on_batch_finished(self, done: int, total: int) -> None:
        """Mark the title and ask the taskbar for attention.

        The app had no completion signal anywhere — the window title only
        ever showed the version, so a long batch finishing in the background
        was invisible. QApplication.alert() flashes the taskbar entry until
        the window is focused (a no-op when it is already active).
        """
        self.setWindowTitle(f"✓ Done ({done}/{total}) — {self._base_title}")
        QApplication.alert(self, 5000)

    # ------------------------------------------------------------------ #
    #  Theme change handling                                                #
    # ------------------------------------------------------------------ #

    def changeEvent(self, event: QEvent) -> None:
        """Re-apply palette-aware stylesheet when system theme changes.

        On macOS, when the user switches between Light and Dark Mode,
        Qt sends a QEvent.PaletteChange (or QEvent.ColorSchemeChange on
        Qt 6.5+). We catch it here to refresh the widget stylesheet so the
        UI adapts without needing a restart.

        Re-entrancy is guarded by the _theme_refreshing flag: setStyleSheet()
        itself can trigger another palette event, and the flag makes that
        nested call a no-op instead of an infinite loop.
        """
        # ColorSchemeChange only exists on Qt 6.5+; guard for older builds.
        color_scheme_change = getattr(QEvent.Type, "ColorSchemeChange", None)
        theme_event_types = {QEvent.Type.PaletteChange}
        if color_scheme_change is not None:
            theme_event_types.add(color_scheme_change)
        if event.type() in theme_event_types and not getattr(self, "_theme_refreshing", False):
            # Guard against re-entrancy: setStyleSheet can trigger PaletteChange
            self._theme_refreshing = True
            try:
                self.setStyleSheet(widget_stylesheet())
                # The system palette (incl. PlaceholderText) just changed, so
                # the AA placeholder override has to be re-derived from it.
                # Inside the guard: setPalette also fires PaletteChange, and
                # re-styling re-snapshots the line edits' palettes.
                self.setPalette(with_aa_placeholder(self.palette()))
                apply_aa_placeholder(self)
                self._refresh_tab_icons()
            finally:
                self._theme_refreshing = False
        super().changeEvent(event)

    # ------------------------------------------------------------------ #
    #  Shutdown — cancel workers before the window goes away               #
    # ------------------------------------------------------------------ #

    def shutdown(self) -> None:
        """Ask every worker-owning tab to cancel its workers. Idempotent.

        (HistoryTab owns no workers and is deliberately not in the loop.)
        Called from closeEvent() and from QApplication.aboutToQuit (a quit
        that never sends a close event, e.g. session logout). The shutdown
        deadline starts here so closeEvent() always gets its full grace
        period no matter which of the two runs first.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        self._shutdown_deadline = time.monotonic() + SHUTDOWN_TIMEOUT_S
        for tab in (self.download_tab, self.audio_tab, self.video_tab):
            tab.shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cancel every worker, then wait for its thread before closing.

        Without this the interpreter tore the tabs down while their QThreads
        were still inside run() ("QThread: Destroyed while thread is still
        running" — and a possible abort) and left ffmpeg children orphaned
        mid-encode. The wait is asynchronous: the close is ignored and a
        100 ms timer retries, so the GUI stays responsive while the workers
        wind down cooperatively. terminate() is only a last resort for a
        worker that ignored its cancel flag for SHUTDOWN_TIMEOUT_S.
        """
        self.shutdown()
        if "— stopping…" not in self.windowTitle():
            self.setWindowTitle(f"{self.windowTitle()} — stopping…")
        running = self._running_workers()
        if running and time.monotonic() < self._shutdown_deadline:
            event.ignore()
            # Grey the window out while it waits: otherwise the user could
            # start a new batch behind the shutdown.
            self.setEnabled(False)
            if not self._shutdown_timer.isActive():
                self._shutdown_timer.start()
            return
        self._shutdown_timer.stop()
        for worker in running:
            worker.terminate()
            worker.wait(1000)
        # No super().closeEvent(): the default QWidget handler must not be
        # able to re-ignore what we just accepted.
        event.accept()

    def _retry_close(self) -> None:
        """Polling slot: re-attempt the close once the workers have exited."""
        self.close()

    def _running_workers(self) -> list[QThread]:
        """Every tracked worker still inside run() (all tabs + this window)."""
        running = list(self._tracker.running())
        for tab in (self.download_tab, self.audio_tab, self.video_tab):
            running.extend(tab.running_workers())
        return running

    # ------------------------------------------------------------------ #
    #  Drag-and-drop — route to active tab                                  #
    # ------------------------------------------------------------------ #

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        md = event.mimeData()
        if md.hasText() or md.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        tab = self._tabs.currentIndex()
        md  = event.mimeData()
        if tab == 1:
            # Audio converter tab — accept local files/folders
            if self.audio_tab.is_active:
                QMessageBox.warning(
                    self, "Conversion in progress",
                    "Wait for the current conversion queue to finish before adding files.",
                )
                return
            if md.hasUrls():
                added = 0
                for url in md.urls():
                    local = url.toLocalFile()
                    if local:
                        path = Path(local)
                        if path.is_dir():
                            added += self.audio_tab.add_folder(path)
                        else:
                            added += int(self.audio_tab.add_file(path))
                if added:
                    event.acceptProposedAction()
                else:
                    # Silent drops looked like the app was broken (P2).
                    self.audio_tab.conv_status_label.setText(
                        "Nothing added — drop audio files or a folder."
                    )
            elif md.hasText():
                self.audio_tab.conv_status_label.setText(
                    "Nothing to convert here — drop audio files or a folder, "
                    "not text."
                )
            return
        if tab == 2:
            # Video converter tab — accept local files/folders
            if self.video_tab.is_active:
                QMessageBox.warning(
                    self, "Conversion in progress",
                    "Wait for the current conversion queue to finish before adding files.",
                )
                return
            if md.hasUrls():
                added = 0
                for url in md.urls():
                    local = url.toLocalFile()
                    if local:
                        path = Path(local)
                        if path.is_dir():
                            added += self.video_tab.add_folder(path)
                        else:
                            added += int(self.video_tab.add_file(path))
                if added:
                    event.acceptProposedAction()
                else:
                    self.video_tab.video_conv_status_label.setText(
                        "Nothing added — drop video files or a folder."
                    )
            elif md.hasText():
                self.video_tab.video_conv_status_label.setText(
                    "Nothing to convert here — drop video files or a folder, "
                    "not text."
                )
            return
        # Downloader tab (also serves the History tab)
        if self.download_tab.is_active:
            QMessageBox.warning(
                self, "Download in progress",
                "Wait for the current download queue to finish before adding URLs.",
            )
            return
        if md.hasUrls() and md.urls():
            added = 0
            for url in md.urls():
                local = url.toLocalFile()
                if local:
                    try:
                        text = Path(local).read_text(encoding="utf-8")
                    except (OSError, UnicodeError):
                        # Unreadable OR not UTF-8 (an mp3/mkv dropped on the
                        # Downloader tab): UnicodeDecodeError is a ValueError,
                        # not an OSError, and used to escape the drop handler.
                        continue
                    self.download_tab.add_urls_from_text(text)
                    added += 1
                    # Keep going: dropping several .txt/URL items used to
                    # return here and silently ignore every item after the
                    # first (same for the http URL branch below).
                    continue
                s = url.toString()
                if s.startswith(("http://", "https://")):
                    self.download_tab.add_url(s)
                    added += 1
            if added:
                event.acceptProposedAction()
                self._show_downloader_after_queue()
            elif not md.hasText():
                # e.g. a media file dropped on the Downloader: explain instead
                # of doing nothing.
                self.download_tab.status_label.setText(
                    "Nothing queued — drop http(s) links, a .txt of links, "
                    "or paste with Ctrl+V."
                )
        elif md.hasText():
            self.download_tab.add_urls_from_text(md.text())
            event.acceptProposedAction()
            self._show_downloader_after_queue()

    # ------------------------------------------------------------------ #
    #  Cross-tab slots                                                     #
    # ------------------------------------------------------------------ #

    def _requeue_download(self, url: str, filename: str) -> None:
        """History wants a re-download: switch to the Downloader tab and queue."""
        self._tabs.setCurrentIndex(0)
        self.download_tab.requeue(url, filename)

    def _show_downloader_after_queue(self) -> None:
        """Dropped/pasted URLs land in the Downloader's queue — go look at it.

        Dropping a link while the History tab was open queued it silently on
        a tab the user could not see (the requeue action already switched
        tabs; the drop path did not).
        """
        if self._tabs.currentIndex() != 0:
            self._tabs.setCurrentIndex(0)

    # ------------------------------------------------------------------ #
    #  Top-level UI                                                        #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self._apply_style()
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # Header: app name + version label + About button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        app_label = QLabel("Chrisnov Media Toolkit")
        app_label.setObjectName("appNameLabel")
        ver_label = QLabel(f"v{APP_VERSION}")
        ver_label.setObjectName("versionLabel")
        about_btn = QPushButton("About")
        about_btn.setObjectName("aboutButton")
        about_btn.setFixedWidth(56)
        about_btn.clicked.connect(self._show_about)
        header.addWidget(app_label)
        header.addSpacing(4)
        header.addWidget(ver_label)
        header.addStretch()
        header.addWidget(about_btn)
        root.addLayout(header)

        self._tabs = QTabWidget()
        self._tabs.setIconSize(QSize(16, 16))
        self.download_tab = DownloadTab(self._settings, self.history)
        self.audio_tab = AudioConverterTab(
            self._settings, self.download_tab.clean_tags_text, self.history
        )
        self.video_tab = VideoConvertTab(
            self._settings, self.download_tab.clean_tags_text, self.history
        )
        self.history_tab = HistoryTab(self.history)
        # Icons are set separately (in palette color) — text glyphs here
        # previously went tofu on systems missing the font's symbols.
        self._tabs.addTab(self._wrap_tab(self.download_tab), "Downloader")
        self._tabs.addTab(self._wrap_tab(self.audio_tab), "Audio Converter")
        self._tabs.addTab(self._wrap_tab(self.video_tab), "Video Converter")
        self._tabs.addTab(self._wrap_tab(self.history_tab), "History")
        self._refresh_tab_icons()
        root.addWidget(self._tabs)

        # F1 opens the About dialog from anywhere in the app
        QShortcut(QKeySequence("F1"), self).activated.connect(self._show_about)

    def _wrap_tab(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def _refresh_tab_icons(self) -> None:
        """(Re)render the tab icons in the current palette's text color.

        Called after the tabs are built and again on theme changes so the
        SVG icons follow Light/Dark mode instead of shipping baked-in colors.
        """
        if not hasattr(self, "_tabs"):
            return
        color = palette_icon_color(self.palette())
        for i, name in enumerate(("download", "audio", "video", "history")):
            icon = bundled_icon(name, color)
            if not icon.isNull():
                self._tabs.setTabIcon(i, icon)

    def _apply_style(self) -> None:
        """Apply the palette-aware stylesheet from theme.py.

        Uses palette-derived colors instead of hardcoded hex values so the
        UI adapts automatically to Light/Dark Mode and platform font sizes.
        """
        self.setStyleSheet(widget_stylesheet())

    # ------------------------------------------------------------------ #
    #  About dialog                                                         #
    # ------------------------------------------------------------------ #

    def _about_link_color(self) -> str:
        """Muted-but-readable link color for the About dialog's footer.

        Derived from the live palette through theme.muted_color(), so it
        clears WCAG AA (4.5:1) in both light and dark mode — the previous
        hardcoded gray measured ~2.8:1 on the light window (P2).
        """
        pal = self.palette()
        try:
            fg = pal.color(QPalette.ColorRole.WindowText).name()
            bg = pal.color(QPalette.ColorRole.Window).name()
        except (SystemError, RuntimeError, ValueError):
            return "#808080"  # palette mid-update: legible neutral
        return muted_color(fg, bg)

    def _show_about(self) -> None:
        """Show the About dialog with version, runtime, and dependency info."""
        import importlib.metadata as meta

        def _ver(pkg: str) -> str:
            try:
                return meta.version(pkg)
            except meta.PackageNotFoundError:
                return "n/a"

        pyside_ver = _ver("PySide6")
        ytdlp_ver  = _ver("yt-dlp")
        # NOTE: the FFmpeg version is filled in by _start_ffmpeg_probe()
        # below. It used to be probed right here — `ffmpeg -version` is a
        # subprocess with a 5 s timeout, so building the dialog froze the GUI
        # for that long on a cold or antivirus-scanned disk.

        platform_str = {
            "win32":  "Windows",
            "darwin": "macOS",
            "linux":  "Linux",
        }.get(sys.platform, sys.platform)
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        dlg = QDialog(self)
        dlg.setWindowTitle("About Chrisnov Media Toolkit")
        dlg.setFixedWidth(380)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(4)

        # App name + version
        name_lbl = QLabel("Chrisnov Media Toolkit")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(name_lbl)

        ver_lbl = QLabel(f"Version {APP_VERSION}")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_lbl.setStyleSheet("font-size: 9pt; color: palette(text); margin-bottom: 12px;")
        layout.addWidget(ver_lbl)

        # Divider
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background: palette(dark); margin: 8px 0;")
        layout.addWidget(line)

        # Info rows
        def _row(label: str, value: str) -> QLabel:
            """Add one label/value row; returns the value label so a row that
            is filled in asynchronously (FFmpeg) can be updated later."""
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: palette(text); font-size: 9pt;")
            val = QLabel(value)
            val.setStyleSheet("color: palette(windowText); font-size: 9pt;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)
            return val

        _row("Platform",  platform_str)
        _row("Python",    py_ver)
        _row("PySide6",   pyside_ver)
        _row("yt-dlp",    ytdlp_ver)
        ffmpeg_lbl = _row("FFmpeg", "detecting…")

        # Update notice — filled in asynchronously by UpdateCheckWorker so the
        # dialog never blocks on the network (see app/update_check.py) and only
        # a genuinely newer version is advertised.
        notice = QLabel("")
        notice.setStyleSheet("color: #e53e3e; font-size: 9pt; margin-top: 8px;")
        # Note: red error color is intentional — should remain red in both modes
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.hide()
        layout.addWidget(notice)

        # Divider
        line2 = QLabel()
        line2.setFixedHeight(1)
        line2.setStyleSheet("background: palette(dark); margin: 8px 0;")
        layout.addWidget(line2)

        # Description
        desc = QLabel(
            "A minimal media downloader and converter\n"
            "built with PySide6, yt-dlp, and FFmpeg."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 9pt; color: palette(text);")
        layout.addWidget(desc)

        credit = QLabel(
            # Secondary link text must still clear WCAG AA: the hardcoded
            # muted gray measured ~2.8:1 on the light window (P2), so the
            # color is derived from the live palette instead.
            f'<a href="https://chrisnov.com" style="color:{self._about_link_color()};'
            'text-decoration:none;">'
            '© Chrisnov IT Solutions</a>'
        )
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setStyleSheet("font-size: 8pt; color: palette(text); margin-top: 4px;")
        credit.setOpenExternalLinks(True)
        layout.addWidget(credit)

        gh_link = QLabel(
            f'<a href="https://github.com/chrisnov-it" style="color:'
            f'{self._about_link_color()};text-decoration:none;">'
            "chrisnov-it on GitHub</a>"
        )
        gh_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gh_link.setStyleSheet("font-size: 7pt; color: palette(text);")
        gh_link.setOpenExternalLinks(True)
        layout.addWidget(gh_link)

        # Close button
        layout.addSpacing(8)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        close_btn.setFixedWidth(80)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        if ytdlp_ver != "n/a":
            self._start_update_check(notice, ytdlp_ver)
        self._start_ffmpeg_probe(ffmpeg_lbl)
        try:
            dlg.exec()
        finally:
            # The dialog and its labels are destroyed when exec() returns; drop
            # the reference so a late worker answer is ignored instead of
            # touching a deleted C++ object.
            self._about_update_target = None
            self._about_ffmpeg_label = None

    # ------------------------------------------------------------------ #
    #  About dialog — yt-dlp update notice                                 #
    # ------------------------------------------------------------------ #

    def _start_update_check(self, notice: QLabel, current: str) -> None:
        """Ask PyPI for the latest yt-dlp version, in the background."""
        self._about_update_target = (notice, current)
        worker = UpdateCheckWorker(current)
        self._tracker.track(worker)
        worker.update_available.connect(self._show_update_notice)
        worker.start()

    def _start_ffmpeg_probe(self, label: QLabel) -> None:
        """Fill the About dialog's FFmpeg row from a worker thread.

        `ffmpeg -version` blocks for as long as the process needs (up to the
        probe's 5 s timeout), so it must never run on the GUI thread — see
        _FFmpegVersionWorker.
        """
        self._about_ffmpeg_label = label
        worker = _FFmpegVersionWorker()
        self._tracker.track(worker)
        worker.ready.connect(self._show_ffmpeg_version)
        worker.start()

    def _show_ffmpeg_version(self, version: str) -> None:
        """Set the About dialog's FFmpeg row (GUI thread, queued delivery).

        The dialog may already be closed when the probe answers — then the
        holder was cleared by _show_about()'s finally and the label itself is
        gone, so a late answer is dropped instead of raising.
        """
        target = self._about_ffmpeg_label
        self._about_ffmpeg_label = None
        if target is None:
            return
        with contextlib.suppress(RuntimeError):
            target.setText(version)

    def _show_update_notice(self, latest: str) -> None:
        """Fill in the About dialog's update notice.

        Runs on the GUI thread (MainWindow is a QObject, so the worker's
        signal is delivered queued). The dialog may already be closed by the
        time the check answers — then the label is gone and Qt raises
        RuntimeError from its wrapper.
        """
        target = self._about_update_target
        self._about_update_target = None
        if target is None:
            return
        notice, current = target
        with contextlib.suppress(RuntimeError):
            notice.setText(f"Update available: yt-dlp {current} → {latest}")
            notice.show()
