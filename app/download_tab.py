"""Downloader tab — URL queue, batch state, and yt-dlp workers.

Extracted from the MainWindow monolith (window.py) with behavior kept
1:1. Two structural changes:

  - All per-batch state lives in a BatchState dataclass instead of
    lazily-set attributes (batch, batch_idx, outdir, ...) that needed
    getattr() fallbacks whenever a handler could run before they were set.
  - History appends go through the shared DownloadHistory model and emit
    history_changed so the History tab can re-render itself.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .cleaner import (
    DEFAULT_CLEAN_TAGS,
    discover_new_files,
    parse_tag_list,
    rename_with_cleanup,
)
from .constants import (
    AUDIO_BITRATES,
    AUDIO_CONTAINERS,
    CONFIG_DIR,
    PLAYLIST_CONFIRM_THRESHOLD,
    RES_PRESETS,
    VIDEO_CONTAINERS,
)
from .history import DownloadHistory
from .settings import AppSettings
from .theme import _base_font_size as _font_size
from .utils import open_in_explorer
from .worker import (
    DownloadWorker,
    FileSizeWorker,
    PlaylistInspectWorker,
    audio_extensions,
    video_extensions,
)
from .worker_tracking import WorkerTracker
from .yt_dlp_opts import is_playlist_url


@dataclass
class BatchState:
    """Snapshot of everything a running download batch needs.

    Replaces the lazily-set MainWindow attributes (batch, batch_idx,
    batch_total, batch_done, outdir, audio_only, dl_height, container,
    bitrate, clean_tags, embed_metadata, embed_thumbnail, archive_path,
    batch_start_ts) and the _dl_active flag — a batch is running iff
    DownloadTab._batch is not None.
    """

    urls: list[str]
    outdir: str
    audio_only: bool
    height: int | None          # max video height; None = best (no limit)
    container: str
    bitrate: int
    clean_tags: list[str] | None
    embed_metadata: bool
    embed_thumbnail: bool
    archive_path: str | None
    idx: int = 0
    done: int = 0
    start_ts: float = field(default_factory=time.time)
    total: int = field(init=False)

    def __post_init__(self) -> None:
        self.total = len(self.urls)


class DownloadTab(QWidget):
    """Tab 1 — URL queue and download workers."""

    #: Emitted after every history append (success or failure) so the
    #: History tab can re-render itself.
    history_changed = Signal()

    def __init__(self, settings: AppSettings, history: DownloadHistory,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._history = history
        self._tracker = WorkerTracker()

        self.current_batch: list[str] = []
        self.worker: DownloadWorker | None = None
        self._inspect_worker: PlaylistInspectWorker | None = None
        self._info_worker: FileSizeWorker | None = None
        self._batch: BatchState | None = None

        # Cookie settings for authenticated downloads (Instagram, Vimeo
        # private, etc.)
        self.cookie_path = settings.get_str("cookie_path", "")
        self.cookies_from_browser = settings.get_bool("cookies_from_browser", False)

        self._build_ui()

    # ------------------------------------------------------------------ #
    #  Public API — used by MainWindow (drag-drop) and HistoryTab          #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        """True while a download batch (incl. playlist inspection) runs."""
        return self._batch is not None

    def add_url(self, url: str) -> bool:
        """Public queue-add used by drag-drop and history re-queue."""
        return self._add_url(url)

    def add_urls_from_text(self, text: str) -> None:
        """Extract every http(s) token from *text* into the queue."""
        self._add_urls_from_text(text)

    def requeue(self, url: str, filename: str = "") -> None:
        """Re-queue a past download (History tab double-click)."""
        self.url_input.setText(url)
        if self._add_url(url):
            self.status_label.setText(f"Re-queued: {filename or url}")
        # else: _add_url already set a status message explaining why

    def clean_tags_text(self) -> str:
        """Current cleanup-tag list, shared with the converter tabs."""
        return self.clean_tags_input.text()

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        # URL input row: label, input, Add button, Info button — all one row
        url_grid = QHBoxLayout()
        url_grid.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.returnPressed.connect(self._add_url_from_input)
        url_grid.addWidget(self.url_input, 1)
        self.add_queue_btn = QPushButton("Add")
        self.add_queue_btn.clicked.connect(self._add_url_from_input)
        url_grid.addWidget(self.add_queue_btn)
        self.info_btn = QPushButton("Info")
        self.info_btn.setToolTip("Fetch video details: title, size, length before downloading")
        self.info_btn.clicked.connect(self._fetch_video_info)
        url_grid.addWidget(self.info_btn)
        root.addLayout(url_grid)

        # Queue + controls
        root.addWidget(QLabel("Queue:"))
        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(90)
        self.queue_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.queue_list, 1)

        qrow = QHBoxLayout()
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_queue)
        qrow.addWidget(self.remove_btn)
        qrow.addWidget(self.clear_btn)
        qrow.addStretch()
        root.addLayout(qrow)

        # Checkboxes compact rows
        chk_row = QHBoxLayout()
        self.audio_only_chk = QCheckBox("Audio only")
        self.audio_only_chk.toggled.connect(self._on_audio_toggled)
        chk_row.addWidget(self.audio_only_chk)
        self.skip_dup_chk = QCheckBox("Skip duplicates")
        self.skip_dup_chk.setChecked(True)
        chk_row.addWidget(self.skip_dup_chk)
        self.clean_chk = QCheckBox("Clean title")
        self.clean_chk.setChecked(True)
        self.clean_chk.toggled.connect(self._on_clean_toggled)
        chk_row.addWidget(self.clean_chk)
        chk_row.addStretch()
        root.addLayout(chk_row)

        chk_row2 = QHBoxLayout()
        self.embed_meta_chk = QCheckBox("Embed metadata")
        self.embed_meta_chk.setToolTip("Write title, artist, and other tags into the file")
        # Default: unchecked (matches the default video mode; auto-enabled when
        # the user checks "Audio only" via _on_audio_toggled)
        self.embed_meta_chk.setChecked(False)
        chk_row2.addWidget(self.embed_meta_chk)
        self.embed_thumb_chk = QCheckBox("Embed thumbnail")
        self.embed_thumb_chk.setToolTip(
            "Embed cover art. Works with mp3/m4a (audio) and mp4/mkv (video)."
        )
        chk_row2.addWidget(self.embed_thumb_chk)
        chk_row2.addStretch()
        root.addLayout(chk_row2)

        # Cookie settings row (for Instagram private, Vimeo private, etc.)
        cookie_row = QHBoxLayout()
        self.cookies_browser_chk = QCheckBox("Use browser cookies")
        self.cookies_browser_chk.setToolTip(
            "Use cookies from your browser for platforms that require authentication "
            "(Instagram, Vimeo private videos, etc.)"
        )
        self.cookies_browser_chk.setChecked(self.cookies_from_browser)
        self.cookies_browser_chk.toggled.connect(self._on_cookies_toggled)
        cookie_row.addWidget(self.cookies_browser_chk)

        self.cookie_path_btn = QPushButton("Cookie file...")
        self.cookie_path_btn.setToolTip("Select a cookies.txt file from your browser")
        self.cookie_path_btn.clicked.connect(self._browse_cookie_file)
        cookie_row.addWidget(self.cookie_path_btn)

        self.cookie_path_label = QLabel(
            self.cookie_path[:40] + "..." if len(self.cookie_path) > 40 else self.cookie_path
        )
        self.cookie_path_label.setStyleSheet(
            "color: palette(text);" if not self.cookie_path else ""
        )
        cookie_row.addWidget(self.cookie_path_label)
        cookie_row.addStretch()
        root.addLayout(cookie_row)

        # Clean tags input (shown only when clean_chk is on)
        self.clean_tags_input = QLineEdit(", ".join(DEFAULT_CLEAN_TAGS))
        self.clean_tags_input.setClearButtonEnabled(True)
        root.addWidget(self.clean_tags_input)

        # Resolution / container / bitrate — compact grid row
        ctrl = QGridLayout()
        ctrl.setHorizontalSpacing(6)
        ctrl.setVerticalSpacing(4)
        self.res_label = QLabel("Resolution:")
        ctrl.addWidget(self.res_label, 0, 0)
        self.res_combo = QComboBox()
        for label, _ in RES_PRESETS:
            self.res_combo.addItem(label)
        self.res_combo.setCurrentIndex(2)
        ctrl.addWidget(self.res_combo, 0, 1)

        self.container_label = QLabel("Format:")
        ctrl.addWidget(self.container_label, 0, 2)
        self.container_combo = QComboBox()
        self.container_combo.addItems(VIDEO_CONTAINERS)
        self.container_combo.setCurrentText("mp4")
        ctrl.addWidget(self.container_combo, 0, 3)

        self.bitrate_label = QLabel("kbps:")
        ctrl.addWidget(self.bitrate_label, 0, 4)
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(AUDIO_BITRATES)
        self.bitrate_combo.setCurrentText("192")
        self.bitrate_combo.setEnabled(False)
        self.bitrate_label.setEnabled(False)
        ctrl.addWidget(self.bitrate_combo, 0, 5)
        ctrl.setColumnStretch(1, 1)
        ctrl.setColumnStretch(3, 1)
        ctrl.setColumnStretch(5, 1)
        root.addLayout(ctrl)

        # Output folder row
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.dir_input = QLineEdit(
            self._settings.saved_dir("download_video", Path.home() / "Videos")
        )
        out_row.addWidget(self.dir_input, 1)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_dl)
        out_row.addWidget(self.browse_btn)
        self.open_dir_btn = QPushButton("Open")
        self.open_dir_btn.setToolTip("Open the output folder in your file manager")
        self.open_dir_btn.clicked.connect(
            lambda: open_in_explorer(self.dir_input.text().strip())
        )
        out_row.addWidget(self.open_dir_btn)
        root.addLayout(out_row)

        # Info box (hidden by default, shown after Info button click)
        self.info_box = QLabel("")
        self.info_box.setWordWrap(True)
        self.info_box.setStyleSheet(
            "background: palette(light, mid); border: 1px solid palette(light, midlight); "
            "border-radius: 4px; padding: 4px 8px; font-size: "
            + _font_size() + "; color: palette(windowText);"
        )
        self.info_box.hide()
        root.addWidget(self.info_box)

        # Start / Cancel + Progress + Status
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Start")
        self.download_btn.setObjectName("primaryButton")
        self.download_btn.clicked.connect(self._start_download)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.clicked.connect(self._cancel_download)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.cancel_btn)
        root.addLayout(btn_row)

        self.dl_progress = QProgressBar()
        self.dl_progress.setRange(0, 100)
        root.addWidget(self.dl_progress)
        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------ #
    #  URL helpers                                                         #
    # ------------------------------------------------------------------ #

    def _add_urls_from_text(self, text: str) -> None:
        n_added = 0
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            for token in s.split():
                if token.startswith(("http://", "https://")):
                    self._add_url(token)
                    n_added += 1
        if n_added == 0 and text.strip().startswith(("http://", "https://")):
            self._add_url(text.strip())
            n_added = 1
        self.status_label.setText(f"Added {n_added} URL(s) to queue.")

    def _add_url(self, url: str) -> bool:
        """Add a URL to the queue. Returns False when a batch is active and
        the URL was rejected (drag-drop and history re-queue must wait)."""
        if self._batch is not None:
            self.status_label.setText(
                "Download in progress — add new URLs after the queue finishes."
            )
            return False
        if url in self.current_batch:
            return True
        self.current_batch.append(url)
        host = (urlparse(url).hostname or "").lower()
        if self._is_playlist_url(url):
            # Extract identifier from list parameter (YouTube, Vimeo, etc.)
            if "list=" in url:
                identifier = url.split("list=")[-1].split("&")[0]
                # YouTube playlist IDs are typically 11-34 chars, Vimeo/others vary
                display = f"\U0001f4cb {identifier[:20]}"
            else:
                display = f"\U0001f4cb {url[:30]}"
        elif "v=" in url:
            vid = url.split("v=")[-1].split("&")[0]
            display = f"[{vid[:11]}]"
        elif host in ("vimeo.com", "player.vimeo.com"):
            # Vimeo URL: https://vimeo.com/123456789
            vid = url.rstrip("/").split("/")[-1]
            display = f"[{vid[:11]}]"
        elif host in ("instagram.com", "www.instagram.com", "dailymotion.com", "www.dailymotion.com"):
            # Instagram/Dailymotion: extract last path segment
            vid = url.rstrip("/").split("/")[-1]
            display = f"[{vid[:15]}]"
        else:
            display = url[:40]
        self.queue_list.addItem(QListWidgetItem(display))
        if self._is_playlist_url(url):
            self.status_label.setText(
                "Playlist detected. Will fetch all entries on Start (size confirmation if >50)."
            )
        return True

    def _add_url_from_input(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Bad URL", "URL must start with http:// or https://")
            return
        self._add_url(url)
        self.url_input.clear()
        self.status_label.setText(
            f"Queue: {len(self.current_batch)} URL(s). Press Start to download all."
        )

    @staticmethod
    def _is_playlist_url(url: str) -> bool:
        # Delegates to the shared classifier in yt_dlp_opts (unit-tested there);
        # see is_playlist_url() for why watch?v=X&list=Y is NOT a playlist.
        return is_playlist_url(url)

    def _remove_selected(self) -> None:
        # Collect rows descending so each pop/takeItem doesn't shift remaining indices
        rows = sorted(
            {self.queue_list.row(item) for item in self.queue_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            if 0 <= row < len(self.current_batch):
                self.current_batch.pop(row)
            self.queue_list.takeItem(row)
        self.status_label.setText(f"Queue: {len(self.current_batch)} URL(s).")

    def _clear_queue(self) -> None:
        self.current_batch.clear()
        self.queue_list.clear()
        self.status_label.setText("Queue cleared.")

    def _browse_dl(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.dir_input.text()
        )
        if d:
            self.dir_input.setText(d)
            key = "download_audio" if self.audio_only_chk.isChecked() else "download_video"
            self._settings.save_dir(key, d)

    def _on_audio_toggled(self, checked: bool) -> None:
        # Audio mode benefits from metadata embedding (ID3 tags) so the user
        # doesn't have to manually edit tags later. Video files don't need it,
        # so we toggle the checkbox to match the mode.
        self.embed_meta_chk.setChecked(checked)
        # Remember whatever folder is currently shown for the mode we're leaving,
        # then restore the saved folder for the mode we're entering.
        current = self.dir_input.text().strip()
        self.container_combo.clear()
        if checked:
            self._settings.save_dir("download_video", current)
            self.container_combo.addItems(AUDIO_CONTAINERS)
            self.container_combo.setCurrentText("mp3")
            self.res_combo.setEnabled(False)
            self.res_label.setEnabled(False)
            self.bitrate_combo.setEnabled(True)
            self.bitrate_label.setEnabled(True)
            self.dir_input.setText(
                self._settings.saved_dir("download_audio", Path.home() / "Music")
            )
        else:
            self._settings.save_dir("download_audio", current)
            self.container_combo.addItems(VIDEO_CONTAINERS)
            self.container_combo.setCurrentText("mp4")
            self.res_combo.setEnabled(True)
            self.res_label.setEnabled(True)
            self.bitrate_combo.setEnabled(False)
            self.bitrate_label.setEnabled(False)
            self.dir_input.setText(
                self._settings.saved_dir("download_video", Path.home() / "Videos")
            )

    def _on_clean_toggled(self, checked: bool) -> None:
        self.clean_tags_input.setEnabled(checked)

    def _on_cookies_toggled(self, checked: bool) -> None:
        self.cookies_from_browser = checked
        self._settings.set_value("cookies_from_browser", checked)
        self.cookie_path_label.setStyleSheet(
            "color: palette(text);" if not self.cookie_path else ""
        )

    def _browse_cookie_file(self) -> None:
        d, _ = QFileDialog.getOpenFileName(
            self, "Select cookies.txt file",
            str(Path.home()),
            "Cookie files (*.txt);;All files (*)"
        )
        if d:
            self.cookie_path = d
            self._settings.set_value("cookie_path", d)
            if len(d) > 40:
                self.cookie_path_label.setText(d[:40] + "...")
            else:
                self.cookie_path_label.setText(d)
            self.cookie_path_label.setStyleSheet("")

    # ------------------------------------------------------------------ #
    #  Info fetch (FileSizeWorker)                                         #
    # ------------------------------------------------------------------ #

    def _fetch_video_info(self) -> None:
        """Fetch metadata (title, size, length) for a single URL."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Enter a URL first.")
            return
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Bad URL", "URL must start with http:// or https://")
            return

        if self._batch is not None:
            QMessageBox.warning(
                self, "Download in progress",
                "Wait for the current download to finish before fetching info."
            )
            return

        self.info_btn.setEnabled(False)
        self.info_btn.setText("...")
        self.download_btn.setEnabled(False)
        self.status_label.setText("Fetching info...")

        audio = self.audio_only_chk.isChecked()
        height = RES_PRESETS[self.res_combo.currentIndex()][1]
        fmt = self.container_combo.currentText()

        self._info_worker = FileSizeWorker(
            url, audio, height, fmt,
            cookie_path=self.cookie_path if self.cookie_path else None,
            cookies_from_browser=self.cookies_from_browser
        )
        self._tracker.track(self._info_worker)
        self._info_worker.result.connect(self._on_info_result)
        self._info_worker.error.connect(self._on_info_error)
        self._info_worker.start()

    def _on_info_result(self, title: str, length_sec: float | None,
                        filesize_mb: float | None, fmt_note: str,
                        audio: bool, resolution: str) -> None:
        """Display fetched metadata in the info box."""
        self._info_worker = None
        self.info_btn.setEnabled(True)
        self.info_btn.setText("Info")
        if self._batch is None:
            self.status_label.setText("Ready.")
            self.download_btn.setEnabled(True)

        mins = ""
        if length_sec:
            m, s = divmod(int(length_sec), 60)
            if m >= 60:
                h, m = divmod(m, 60)
                mins = f"{h}h{m:02d}m{s:02d}s"
            else:
                mins = f"{m}m{s:02d}s"

        size_str = f"{filesize_mb:.1f} MB" if filesize_mb else "unknown"

        msg = f"<b>{title}</b><br>"
        if mins:
            msg += f"Length: {mins} &nbsp;|&nbsp; "
        msg += f"Format: {fmt_note} &nbsp;|&nbsp; "
        msg += f"Est. size: <b>{size_str}</b>"

        if audio:
            msg += f"<br><i>Audio-only mode. Resolution: {resolution}</i>"
        else:
            msg += f"<br><i>Video mode. Resolution: {resolution}</i>"

        self.info_box.setText(msg)
        self.info_box.show()

    def _on_info_error(self, err: str) -> None:
        self._info_worker = None
        self.info_btn.setEnabled(True)
        self.info_btn.setText("Info")
        if self._batch is None:
            self.status_label.setText("Ready.")
            self.download_btn.setEnabled(True)
        self.info_box.setText(
            f"<span style='color:#a62929;'>Error: {err}</span>"
        )
        self.info_box.show()

    # ------------------------------------------------------------------ #
    #  Download flow                                                       #
    # ------------------------------------------------------------------ #

    def _start_download(self) -> None:
        typed = self.url_input.text().strip()
        if typed and typed.startswith(("http://", "https://")):
            self._add_url(typed)
            self.url_input.clear()

        if not self.current_batch:
            QMessageBox.warning(self, "No URLs", "Add at least one URL to the queue.")
            return
        outdir = self.dir_input.text().strip()
        if not Path(outdir).is_dir():
            QMessageBox.warning(self, "Bad folder", f"Folder does not exist: {outdir}")
            return
        clean_tags = (
            parse_tag_list(self.clean_tags_input.text())
            if self.clean_chk.isChecked() else None
        )
        # Validate BEFORE building any state so early returns never leave a
        # half-initialized batch behind (the old code set attrs, then warned).
        if self.clean_chk.isChecked() and not clean_tags:
            QMessageBox.warning(
                self, "No cleanup tags",
                "Clean title is on but no tags are listed. Returning.",
            )
            return

        audio_only = self.audio_only_chk.isChecked()
        self._settings.save_dir(
            "download_audio" if audio_only else "download_video",
            outdir,
        )
        batch = BatchState(
            urls=list(self.current_batch),
            outdir=outdir,
            audio_only=audio_only,
            height=RES_PRESETS[self.res_combo.currentIndex()][1],
            container=self.container_combo.currentText(),
            bitrate=int(self.bitrate_combo.currentText()),
            clean_tags=clean_tags,
            embed_metadata=self.embed_meta_chk.isChecked(),
            embed_thumbnail=self.embed_thumb_chk.isChecked(),
            archive_path=self._resolve_archive(audio_only),
        )
        self._batch = batch

        # Cancel any in-flight info fetch
        if self._info_worker is not None and self._info_worker.isRunning():
            self._info_worker.cancel()
            self._info_worker.wait(3000)
            self._info_worker = None
            self.info_btn.setEnabled(True)
            self.info_btn.setText("Info")

        # Disable UI immediately so the user can't double-submit or touch
        # the queue mid-batch (edits can't reach the running snapshot and
        # would be wiped by the batch reset)
        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.add_queue_btn.setEnabled(False)
        self.url_input.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)

        playlist_urls = [u for u in batch.urls if self._is_playlist_url(u)]
        if playlist_urls:
            # Inspect playlist sizes off the GUI thread
            self.status_label.setText(
                f"Inspecting {len(playlist_urls)} playlist URL(s)..."
            )
            self._inspect_worker = PlaylistInspectWorker(
                playlist_urls, batch.audio_only, PLAYLIST_CONFIRM_THRESHOLD,
                cookie_path=self.cookie_path if self.cookie_path else None,
                cookies_from_browser=self.cookies_from_browser
            )
            self._tracker.track(self._inspect_worker)
            self._inspect_worker.progress.connect(self.status_label.setText)
            self._inspect_worker.done.connect(self._on_inspect_done)
            self._inspect_worker.error.connect(self._on_inspect_error)
            self._inspect_worker.start()
        else:
            self._kick_next()

    def _resolve_archive(self, audio_only: bool) -> str | None:
        """Locate the skip-duplicates archive, migrating the legacy
        chrisnov-yt-downloader file once when the new one is absent."""
        if not self.skip_dup_chk.isChecked():
            return None
        archive_dir = CONFIG_DIR
        archive_dir.mkdir(parents=True, exist_ok=True)
        suffix = "_audio" if audio_only else "_video"
        archive_path = archive_dir / f"archive{suffix}.txt"
        old_archive_path = (
            Path.home() / ".config" / "chrisnov-yt-downloader" / f"archive{suffix}.txt"
        )
        if old_archive_path.exists() and not archive_path.exists():
            archive_path.write_text(
                old_archive_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        return str(archive_path)

    def _on_inspect_done(self, big: list) -> None:
        """Called when PlaylistInspectWorker finishes without error."""
        self._inspect_worker = None
        if big:
            lines = [f"• {title} — {n} entries (~{est})" for _, n, est, title in big]
            msg = "Large playlists detected:\n\n" + "\n".join(lines) + "\n\nContinue?"
            ans = QMessageBox.question(
                self, "Confirm large playlist download",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self.status_label.setText("Download cancelled.")
                self._reset_after_batch()
                return
        self._kick_next()

    def _on_inspect_error(self, url: str, msg: str) -> None:
        """Called when PlaylistInspectWorker hits a network/parse error."""
        self._inspect_worker = None
        QMessageBox.warning(self, "Playlist error", f"{url}\n\n{msg}")
        self.status_label.setText("Download cancelled.")
        self._reset_after_batch()

    def _kick_next(self) -> None:
        batch = self._batch
        if batch is None:
            return
        if batch.idx >= batch.total:
            self.status_label.setText(
                f"Queue finished: {batch.done}/{batch.total} completed."
            )
            self.dl_progress.setValue(0)
            self._reset_after_batch()
            return
        url = batch.urls[batch.idx]
        idx_label = f"[{batch.idx + 1}/{batch.total}]"
        self.status_label.setText(f"{idx_label} Starting: {url}")
        self.dl_progress.setValue(0)

        self.worker = DownloadWorker(
            url=url,
            height=batch.height,
            container=batch.container,
            bitrate=batch.bitrate,
            outdir=batch.outdir,
            audio_only=batch.audio_only,
            idx_label=idx_label,
            clean_tags=batch.clean_tags,
            playlist=self._is_playlist_url(url),
            archive_path=batch.archive_path,
            embed_metadata=batch.embed_metadata,
            embed_thumbnail=batch.embed_thumbnail,
            cookie_path=self.cookie_path if self.cookie_path else None,
            cookies_from_browser=self.cookies_from_browser,
        )
        self._tracker.track(self.worker)
        self.worker.progress.connect(self.dl_progress.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self._on_item_ok)
        self.worker.failed.connect(self._on_item_fail)
        self.worker.start()

    def _on_item_ok(self, path: str) -> None:
        batch = self._batch
        if batch is None:
            return
        url = batch.urls[batch.idx] if batch.idx < len(batch.urls) else ""

        if isinstance(path, str) and path.startswith(("playlist_files:", "playlist:")):
            # Playlist batches: collect the final paths (post-rename when
            # cleaning ran, original otherwise) and build a readable history
            # label instead of the raw worker payload.
            if path.startswith("playlist_files:"):
                playlist_files, playlist_label, renamed = self._collect_playlist_files(path, batch)
            else:
                playlist_files, playlist_label, renamed = self._discover_playlist_files(path, batch)
            total_bytes = sum(f.stat().st_size for f in playlist_files if f.exists())
            self._history.append(
                url=url, filepath=batch.outdir, filename=playlist_label,
                filesize=total_bytes,
                type_="playlist", container=batch.container,
                audio_only=batch.audio_only, status="completed",
            )
        else:
            final_path, renamed = self._finish_single_file(path, batch)
            self._history.append(
                url=url, filepath=str(final_path), filename=final_path.name,
                filesize=final_path.stat().st_size if final_path.exists() else 0,
                type_="audio" if batch.audio_only else "video",
                container=batch.container, audio_only=batch.audio_only,
                status="completed",
            )

        if batch.clean_tags and renamed:
            self.status_label.setText(
                f"Cleaned {len(renamed)} file(s), e.g. {renamed[0]!r}"
            )

        batch.idx += 1
        batch.done += 1
        self.history_changed.emit()
        self._kick_next()

    def _collect_playlist_files(self, payload: str, batch: BatchState
                                ) -> tuple[list[Path], str, list[str]]:
        """Rename every file in a playlist_files: JSON payload (single worker
        run that itself collected all output files)."""
        try:
            raw = json.loads(payload.removeprefix("playlist_files:"))
        except json.JSONDecodeError:
            raw = []
        if not isinstance(raw, list):
            raw = []
        files: list[Path] = []
        renamed: list[str] = []
        for p in raw:
            new = rename_with_cleanup(p, batch.clean_tags)
            files.append(new if new is not None else Path(p))
            if new is not None:
                renamed.append(new.name)
        label = f"Playlist — {len(files)} file(s)"
        return files, label, renamed

    def _discover_playlist_files(self, payload: str, batch: BatchState
                                 ) -> tuple[list[Path], str, list[str]]:
        """playlist:N:Title payload — discover files the worker wrote since
        the batch started (used when the worker could not collect paths)."""
        exts = audio_extensions() if batch.audio_only else video_extensions()
        files: list[Path] = []
        renamed: list[str] = []
        for p in discover_new_files(batch.outdir, batch.start_ts, exts):
            new = rename_with_cleanup(p, batch.clean_tags)
            files.append(new if new is not None else p)
            if new is not None:
                renamed.append(new.name)
        parts = payload.split(":", 2)
        n = parts[1] if len(parts) > 1 else "?"
        title = parts[2] if len(parts) > 2 else ""
        label = (
            f"Playlist: {title} — {n} item(s)" if title else f"Playlist — {n} item(s)"
        )
        return files, label, renamed

    def _finish_single_file(self, path: str, batch: BatchState) -> tuple[Path, list[str]]:
        """Rename a single downloaded file when cleanup is enabled."""
        new = rename_with_cleanup(path, batch.clean_tags)
        if new is not None:
            return new, [new.name]
        return Path(path), []

    def _on_item_fail(self, msg: str) -> None:
        batch = self._batch
        if batch is None:
            return
        url = batch.urls[batch.idx] if batch.idx < len(batch.urls) else ""
        self._history.append(
            url=url, filepath="",
            filename=url.split("/")[-1][:40] if url else "?",
            filesize=0, type_="audio" if batch.audio_only else "video",
            container=batch.container, audio_only=batch.audio_only,
            status="failed", error=msg,
        )
        self.status_label.setText(
            f"[{batch.idx + 1}/{batch.total}] Error: {msg}"
        )
        batch.idx += 1
        self.history_changed.emit()
        self._kick_next()

    def _cancel_download(self) -> None:
        # If still inspecting playlists, cancel that first
        if self._inspect_worker and self._inspect_worker.isRunning():
            self._inspect_worker.done.disconnect()
            self._inspect_worker.error.disconnect()
            self._inspect_worker.progress.disconnect()
            self._inspect_worker.cancel()
            self._inspect_worker.wait(3000)
            self._inspect_worker = None
            self.status_label.setText("Cancelled.")
            self._reset_after_batch()
            return

        if self.worker is not None and self.worker.isRunning():
            # Disconnect signals first so any in-flight finished_ok/failed
            # callbacks don't call _kick_next() on the already-reset state.
            try:
                self.worker.progress.disconnect()
                self.worker.status.disconnect()
                self.worker.finished_ok.disconnect()
                self.worker.failed.disconnect()
            except RuntimeError:
                pass
            # Ask yt-dlp to stop cleanly via the cancel flag; give it up to
            # 5 s to honour the request before falling back to terminate().
            self.worker.cancel()
            if not self.worker.wait(5000):
                self.worker.terminate()
                self.worker.wait(2000)
            cleaned = self._cleanup_recent_downloads()
            if cleaned:
                self.status_label.setText(
                    f"Cancelled. Cleaned {len(cleaned)} completed file(s), e.g. {cleaned[0]!r}"
                )
            else:
                self.status_label.setText("Cancelled.")
        self._reset_after_batch()

    def _cleanup_recent_downloads(self) -> list[str]:
        """Title-clean files that already landed before the cancel took."""
        batch = self._batch
        if batch is None or not batch.clean_tags:
            return []
        exts = audio_extensions() if batch.audio_only else video_extensions()
        renamed: list[str] = []
        for p in discover_new_files(batch.outdir, batch.start_ts, exts):
            new = rename_with_cleanup(p, batch.clean_tags)
            if new is not None:
                renamed.append(new.name)
        return renamed

    def _reset_after_batch(self) -> None:
        self.current_batch.clear()
        self.queue_list.clear()
        # Drop the last download worker reference; the tracker keeps the
        # object alive until its thread has fully exited.
        self.worker = None
        self._batch = None
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.add_queue_btn.setEnabled(True)
        self.url_input.setEnabled(True)
        self.remove_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
