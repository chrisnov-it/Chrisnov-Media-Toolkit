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

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
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
from .icon import palette_icon_color, tab_icon
from .settings import AppSettings
from .theme import widget_stylesheet
from .video_convert_tab import VideoConvertTab


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Chrisnov Media Toolkit v{APP_VERSION}")
        self.setMinimumSize(700, 480)
        self.resize(900, 620)
        self.setAcceptDrops(True)

        self._settings = AppSettings()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.history = DownloadHistory(CONFIG_DIR / "download-history.json")
        self.history.load()

        self._build_ui()

        # Cross-tab wiring. The Downloader tab must be constructed first —
        # the converter tabs receive its clean_tags_text callable.
        self.download_tab.history_changed.connect(self.history_tab.refresh)
        self.history_tab.requeue_requested.connect(self._requeue_download)

        self.history_tab.refresh()

    # ------------------------------------------------------------------ #
    #  Theme change handling                                                #
    # ------------------------------------------------------------------ #

    def changeEvent(self, event):
        """Re-apply palette-aware stylesheet when system theme changes.

        On macOS, when the user switches between Light and Dark Mode,
        Qt sends a QEvent.PaletteChange (or QEvent.ColorSchemeChange on
        Qt 6.5+). We catch it here to refresh the widget stylesheet so the
        UI adapts without needing a restart.

        Re-entrancy is guarded by checking that a stylesheet is already
        applied before re-applying, preventing infinite loops when
        setStyleSheet() itself triggers palette events.
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
                self._refresh_tab_icons()
            finally:
                self._theme_refreshing = False
        super().changeEvent(event)

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
            return
        # Downloader tab (also serves the History tab)
        if self.download_tab.is_active:
            QMessageBox.warning(
                self, "Download in progress",
                "Wait for the current download queue to finish before adding URLs.",
            )
            return
        if md.hasUrls() and md.urls():
            for url in md.urls():
                local = url.toLocalFile()
                if local:
                    try:
                        text = Path(local).read_text(encoding="utf-8")
                    except OSError:
                        continue
                    self.download_tab.add_urls_from_text(text)
                    event.acceptProposedAction()
                    return
                s = url.toString()
                if s.startswith(("http://", "https://")):
                    self.download_tab.add_url(s)
                    event.acceptProposedAction()
                    return
        elif md.hasText():
            self.download_tab.add_urls_from_text(md.text())
            event.acceptProposedAction()

    # ------------------------------------------------------------------ #
    #  Cross-tab slots                                                     #
    # ------------------------------------------------------------------ #

    def _requeue_download(self, url: str, filename: str) -> None:
        """History wants a re-download: switch to the Downloader tab and queue."""
        self._tabs.setCurrentIndex(0)
        self.download_tab.requeue(url, filename)

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
        self.audio_tab = AudioConverterTab(self._settings, self.download_tab.clean_tags_text)
        self.video_tab = VideoConvertTab(self._settings, self.download_tab.clean_tags_text)
        self.history_tab = HistoryTab(self.history)
        # Icons are set separately (in palette color) — text glyphs here
        # previously went tofu on systems missing the font's symbols.
        self._tabs.addTab(self._wrap_tab(self.download_tab), "Downloader")
        self._tabs.addTab(self._wrap_tab(self.audio_tab), "Audio Converter")
        self._tabs.addTab(self._wrap_tab(self.video_tab), "Video Converter")
        self._tabs.addTab(self._wrap_tab(self.history_tab), "History")
        self._refresh_tab_icons()
        root.addWidget(self._tabs)

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
            icon = tab_icon(name, color)
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

    def _show_about(self) -> None:
        """Show the About dialog with version, runtime, and dependency info."""
        import importlib.metadata as meta

        def _ver(pkg: str) -> str:
            try:
                return meta.version(pkg)
            except meta.PackageNotFoundError:
                return "n/a"

        def _ffmpeg_ver() -> str:
            """Version of the FFmpeg binary the app itself uses.

            Uses find_ffmpeg()/find_ffprobe() — the same resolution order as
            the workers (PyInstaller bundle, bin/ beside the exe, project
            bin/, system PATH) — so the About row reports the binary the
            app will actually run, falling back to ffprobe (same build)
            when ffmpeg is missing.
            """
            for finder in (find_ffmpeg, find_ffprobe):
                try:
                    binary = finder()
                except FileNotFoundError:
                    continue
                version = probe_version(binary)
                if version:
                    return version
            return "n/a"

        pyside_ver = _ver("PySide6")
        ytdlp_ver  = _ver("yt-dlp")
        ffmpeg_ver = _ffmpeg_ver()

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
        def _row(label: str, value: str) -> None:
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

        _row("Platform",  platform_str)
        _row("Python",    py_ver)
        _row("PySide6",   pyside_ver)
        _row("yt-dlp",    ytdlp_ver)
        _row("FFmpeg",    ffmpeg_ver)

        # Check for newer versions and show update notice
        newer_versions = []
        try:
            import json
            import urllib.request

            # Check yt-dlp latest version from PyPI
            with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=3) as resp:
                ytdlp_latest = json.loads(resp.read())["info"]["version"]
                if ytdlp_ver != "n/a" and ytdlp_ver != ytdlp_latest:
                    newer_versions.append(f"yt-dlp: {ytdlp_ver} → {ytdlp_latest}")
        except (OSError, ValueError, KeyError):
            # Best-effort network check — never block the About dialog.
            pass

        if newer_versions:
            notice = QLabel(f"Update available: {', '.join(newer_versions)}")
            notice.setStyleSheet("color: #e53e3e; font-size: 9pt; margin-top: 8px;")
            # Note: red error color is intentional — should remain red in both modes
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
            '<a href="https://chrisnov.com" style="color:#8a94a0;text-decoration:none;">'
            '© Chrisnov IT Solutions</a>'
        )
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setStyleSheet("font-size: 8pt; color: palette(text); margin-top: 4px;")
        credit.setOpenExternalLinks(True)
        layout.addWidget(credit)

        gh_link = QLabel(
            '<a href="https://github.com/chrisnov-it" style="color:#8a94a0;text-decoration:none;">'
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

        dlg.exec()
