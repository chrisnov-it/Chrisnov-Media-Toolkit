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

import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
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
    CLEAR_CONFIRM_ROWS,
    CONFIG_DIR,
    PLAYLIST_CONFIRM_THRESHOLD,
    RES_PRESETS,
    VIDEO_CONTAINERS,
)
from .history import DownloadHistory
from .icon import bundled_icon, mark_status, palette_icon_color
from .progress import EtaEstimator
from .settings import AppSettings
from .theme import _base_font_size as _font_size
from .utils import (
    clip_text,
    install_placeholder,
    open_in_explorer,
    open_result,
    set_controls_busy,
)
from .worker import (
    DownloadWorker,
    FileSizeWorker,
    PlaylistInspectWorker,
    audio_extensions,
    video_extensions,
    ytdlp_update_hint,
)
from .worker_tracking import WorkerTracker
from .yt_dlp_opts import is_playlist_url

log = logging.getLogger(__name__)


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
    #: Emitted when a batch starts / finishes so MainWindow can mark the
    #: window title (a finished batch used to leave no trace anywhere).
    batch_started = Signal()
    batch_finished = Signal(int, int)  # done, total

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
        #: Last file (or folder, for playlists) that finished — what the
        #: "Open last result" button opens (the status line alone only said
        #: "Cleaned N file(s)…" with no way to act on it).
        self._last_result: Path | None = None
        #: Progress-bar ETA state for the current item (see _on_dl_progress).
        self._eta = EtaEstimator()
        self._eta_label = "%p%"
        self._eta_format = "%p%"

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
        self.url_input.setAccessibleName("Video URL")
        self.url_input.returnPressed.connect(self._add_url_from_input)
        # Start follows what can actually be started (P3): enabled while the
        # queue holds URLs or a URL is typed, disabled otherwise.
        self.url_input.textChanged.connect(lambda _t: self._sync_queue_actions())
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
        self.queue_list.setAccessibleName("Download queue")
        self.queue_list.setMinimumHeight(90)
        self.queue_list.setIconSize(QSize(14, 14))
        self.queue_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.queue_list, 1)
        # In-list empty state (P2): the Downloader had no placeholder at
        # all, so an empty queue was just a blank box.
        self.queue_placeholder = install_placeholder(
            self.queue_list, "No URLs queued yet.\nPaste or drop URLs here (Ctrl+V)."
        )

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
        # The label is clipped for layout reasons — hover shows the whole path.
        self.cookie_path_label.setToolTip(self.cookie_path)
        self.cookie_path_label.setStyleSheet(
            "color: palette(text);" if not self.cookie_path else ""
        )
        cookie_row.addWidget(self.cookie_path_label)
        cookie_row.addStretch()
        root.addLayout(cookie_row)

        # Clean tags input (shown only when clean_chk is on)
        self.clean_tags_input = QLineEdit(", ".join(DEFAULT_CLEAN_TAGS))
        self.clean_tags_input.setClearButtonEnabled(True)
        self.clean_tags_input.setAccessibleName("Cleanup tags")
        # The field is a long comma list scrolled to the right, so its start
        # is cut off on screen (P3): the full list stays on hover.
        self.clean_tags_input.setToolTip(self.clean_tags_input.text())
        self.clean_tags_input.textChanged.connect(
            lambda t: self.clean_tags_input.setToolTip(t)
        )
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
        self.dir_input.setAccessibleName("Download output folder")
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
        self.info_box.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
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
        btn_row.addStretch()
        # The status line reports the last result but could not act on it.
        self.open_last_btn = QPushButton("Open last result")
        self.open_last_btn.setEnabled(False)
        self.open_last_btn.setToolTip(
            "Open the last finished file with your default app "
            "(a playlist opens its folder)."
        )
        self.open_last_btn.clicked.connect(self._open_last_result)
        btn_row.addWidget(self.open_last_btn)
        root.addLayout(btn_row)

        self.dl_progress = QProgressBar()
        self.dl_progress.setRange(0, 100)
        root.addWidget(self.dl_progress)
        self.status_label = QLabel("Ready.")
        # Long errors/URLs wrap instead of clipping, and the text can be
        # selected so an error can actually be read and copied.
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.status_label)

        # Ctrl+V/Cmd+V anywhere on this tab queues every URL in the
        # clipboard. A focused text field keeps its normal paste — the
        # line edit wins the key via ShortcutOverride, and _paste_clipboard
        # replays the default paste if the shortcut still fires.
        paste_sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Paste), self)
        paste_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        paste_sc.activated.connect(self._paste_clipboard)

        # P3 shortcuts: Ctrl+Enter starts the batch (the classic "submit"
        # gesture), Esc cancels it. Both are guarded — the handlers run on a
        # live signal, so Start must not fire mid-batch (it would snapshot a
        # second batch over the running one) and Esc must not wipe an idle
        # queue (an accidental press would discard URLs the user queued).
        for seq in ("Ctrl+Return", "Ctrl+KeypadEnter"):
            start_sc = QShortcut(QKeySequence(seq), self)
            start_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            start_sc.activated.connect(self._start_if_idle)
        esc_sc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc_sc.activated.connect(self._cancel_if_running)

        # Everything _start_download() snapshots into BatchState: frozen for
        # the whole batch like the converter tabs do (P2). Editing any of
        # these mid-run could never apply — the batch reads its snapshot —
        # yet they all stayed clickable.
        self._batch_settings_widgets = (
            self.download_btn, self.add_queue_btn, self.url_input,
            self.remove_btn, self.clear_btn, self.info_btn,
            self.audio_only_chk, self.skip_dup_chk, self.clean_chk,
            self.embed_meta_chk, self.embed_thumb_chk,
            self.cookies_browser_chk, self.cookie_path_btn,
            self.clean_tags_input, self.res_combo, self.container_combo,
            self.bitrate_combo, self.dir_input, self.browse_btn,
        )

        # Initial idle state: nothing queued, so Start/Remove/Clear start
        # disabled instead of dead-clickable (P3).
        self._sync_queue_actions()

    # ------------------------------------------------------------------ #
    #  URL helpers                                                         #
    # ------------------------------------------------------------------ #

    def _set_batch_busy(self, busy: bool) -> None:
        """Freeze/unfreeze the queue *and* the settings for a batch.

        set_controls_busy() restores each control's own pre-batch state, so
        controls that are legitimately off (bitrate in video mode, the
        cleanup-tag field with Clean title off) come back off.
        """
        set_controls_busy(self._batch_settings_widgets, busy)

    def _set_last_result(self, path: Path) -> None:
        """Publish the file/folder that just finished to the Open button."""
        self._last_result = path
        self.open_last_btn.setEnabled(True)
        self.open_last_btn.setToolTip(f"Open last result: {path}")

    def _open_last_result(self) -> None:
        """Open the last finished result (P2: the status line only said so)."""
        if self._last_result is None:
            return
        if not open_result(self._last_result):
            self.status_label.setText(f"Result not found: {self._last_result}")

    # ------------------------------------------------------------------ #
    #  Idle-state sync + guarded shortcuts (P3)                            #
    # ------------------------------------------------------------------ #

    def _sync_queue_actions(self) -> None:
        """Keep Start/Remove/Clear enabled exactly when they can do work.

        Start used to stay clickable with an empty queue and answer with a
        warning dialog (validate-on-click); now it is disabled until the
        queue holds a URL or one is typed. Remove/Clear follow the queue.
        A running batch owns these states (set_controls_busy saved them at
        freeze), so the sync stays out while _batch is set.
        """
        if self._batch is not None:
            return
        has_urls = bool(self.current_batch)
        can_start = has_urls or bool(self.url_input.text().strip())
        self.download_btn.setEnabled(can_start)
        self.remove_btn.setEnabled(has_urls)
        self.clear_btn.setEnabled(has_urls)

    def _start_if_idle(self) -> None:
        """Ctrl+Enter: start only when no batch is running."""
        if self._batch is None:
            self._start_download()

    def _cancel_if_running(self) -> None:
        """Esc: cancel only a running batch — an idle press must never
        wipe the queue (_reset_after_batch clears it)."""
        if self._batch is not None:
            self._cancel_download()

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
        # "Added 0 URL(s)" told the user nothing — a dropped paragraph or a
        # random file used to look like a silent no-op.
        if n_added:
            self.status_label.setText(f"Added {n_added} URL(s) to queue.")
        else:
            self.status_label.setText(
                "No http(s) URLs found — paste links, a .txt of links, or a URL list."
            )

    def _paste_clipboard(self) -> None:
        """Ctrl+V/Cmd+V outside text fields: queue every URL in the clipboard."""
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit)):
            focus.paste()  # replay the native paste this shortcut intercepted
            return
        self.add_urls_from_text(QApplication.clipboard().text())

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
        is_playlist = self._is_playlist_url(url)
        if is_playlist:
            # Extract identifier from list parameter (YouTube, Vimeo, etc.)
            if "list=" in url:
                identifier = url.split("list=")[-1].split("&")[0]
                # YouTube playlist IDs are typically 11-34 chars, Vimeo/others vary
                display = clip_text(identifier, 20)
            else:
                display = clip_text(url, 30)
        elif "v=" in url:
            vid = url.split("v=")[-1].split("&")[0]
            display = f"[{clip_text(vid, 11)}]"
        elif host in ("vimeo.com", "player.vimeo.com"):
            # Vimeo URL: https://vimeo.com/123456789
            vid = url.rstrip("/").split("/")[-1]
            display = f"[{clip_text(vid, 11)}]"
        elif host in ("instagram.com", "www.instagram.com", "dailymotion.com", "www.dailymotion.com"):
            # Instagram/Dailymotion: extract last path segment
            vid = url.rstrip("/").split("/")[-1]
            display = f"[{clip_text(vid, 15)}]"
        else:
            display = clip_text(url, 40)
        # Full URL in the tooltip: the label is a clipped preview, the row
        # hover shows exactly what will be downloaded.
        item = QListWidgetItem(display)
        item.setToolTip(url)
        if is_playlist:
            # Icon, not a 📋 text glyph: glyphs render differently (or as
            # tofu) depending on the user's fonts — see icon.py. The batch
            # later replaces it with the row's status icon.
            item.setIcon(
                bundled_icon("clipboard", palette_icon_color(self.palette()))
            )
        self.queue_list.addItem(item)
        if is_playlist:
            self.status_label.setText(
                "Playlist detected. Will fetch all entries on Start (size confirmation if >50)."
            )
        self._sync_queue_actions()
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
        self._sync_queue_actions()
        self.status_label.setText(f"Queue: {len(self.current_batch)} URL(s).")

    def _clear_queue(self) -> None:
        # Confirm once the queue is big enough to hurt to rebuild (P3) —
        # Clear All history already asked, but a full playlist queue was
        # wiped by a single misclick with no way back.
        n = len(self.current_batch)
        if n >= CLEAR_CONFIRM_ROWS:
            ans = QMessageBox.question(
                self, "Clear queue",
                f"Remove all {n} URL(s) from the queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.current_batch.clear()
        self.queue_list.clear()
        self._sync_queue_actions()
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
            # The label clips long paths — hover must show the chosen one.
            self.cookie_path_label.setToolTip(d)
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

        # Keep the button's label and Start untouched (P3): the old "..."
        # text left no word on screen, and Start can safely cancel the
        # in-flight fetch (_start_download cancels it before the batch).
        self.info_btn.setEnabled(False)
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
        self._sync_queue_actions()
        if self._batch is None:
            self.status_label.setText("Ready.")
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
        self._sync_queue_actions()
        if self._batch is None:
            self.status_label.setText("Ready.")
        # Darker than STATUS_COLORS["failed"] (#e53e3e) on purpose: this is
        # body text in the info box, and #a62929 keeps AA contrast on the
        # light background while #e53e3e is the status *mark* red.
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
                "Clean title is on but no cleanup tags are listed.\n"
                "Add at least one tag, or turn Clean title off.",
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
        self.batch_started.emit()

        # Cancel any in-flight info fetch
        if self._info_worker is not None and self._info_worker.isRunning():
            self._info_worker.cancel()
            self._info_worker.wait(3000)
            self._info_worker = None
            self.info_btn.setEnabled(True)

        # Disable UI immediately so the user can't double-submit or touch
        # the queue mid-batch (edits can't reach the running snapshot and
        # would be wiped by the batch reset). Queue *and* settings both —
        # the batch reads its snapshot, so a live setting could only lie.
        # The controls also get a tooltip explaining the freeze (tooltips
        # still fire on disabled widgets).
        self._set_batch_busy(True)
        self.cancel_btn.setEnabled(True)

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
        if self._batch is None:
            # Cancelled while this event was still queued: the batch state
            # and the queue are gone, so don't prompt or restart anything.
            return
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
                # Nothing was downloaded — keep the queued URLs so declining a
                # huge playlist doesn't silently throw the whole queue away.
                self._reset_after_batch(clear_queue=False)
                return
        self._kick_next()

    def _on_inspect_error(self, url: str, msg: str) -> None:
        """Called when PlaylistInspectWorker hits a network/parse error."""
        self._inspect_worker = None
        if self._batch is None:
            # Cancelled while this event was still queued — a late warning
            # dialog + _reset_after_batch() would wipe the user's new queue.
            return
        QMessageBox.warning(self, "Playlist error", f"{url}\n\n{msg}")
        self.status_label.setText("Download cancelled.")
        # Same as declining: the batch never started, so the queue is intact
        # and the user should still be able to edit or retry it.
        self._reset_after_batch(clear_queue=False)

    def _mark_queue_item(self, row: int, status: str,
                         tooltip: str = "") -> None:
        """Give a queue row its batch status: amber arrow = running, green
        check = done, red cross = failed (+ optional tooltip). Rows stay
        aligned with batch.urls because queue edits are blocked mid-batch;
        the painting itself is shared with the converter queues via
        icon.mark_status()."""
        mark_status(self.queue_list.item(row), status, tooltip)

    def _kick_next(self) -> None:
        batch = self._batch
        if batch is None:
            return
        if batch.idx >= batch.total:
            self.status_label.setText(
                f"Queue finished: {batch.done}/{batch.total} completed."
            )
            self.dl_progress.setValue(0)
            # Tell the window before the state resets (P2: a finished batch
            # used to leave no trace — the title only ever showed the version).
            self.batch_finished.emit(batch.done, batch.total)
            self._reset_after_batch()
            return
        url = batch.urls[batch.idx]
        idx_label = f"[{batch.idx + 1}/{batch.total}]"
        self.status_label.setText(f"{idx_label} Starting: {url}")
        self.dl_progress.setValue(0)
        # Progress bar carries the position + a live ETA while downloading
        # (same pattern as the converter tabs; download progress spans the
        # full 0-100 range for each item).
        self._eta_label = f"{idx_label} %p%"
        self._eta_format = self._eta_label
        self.dl_progress.setFormat(self._eta_label)
        self._eta.reset(0, 100)
        self._mark_queue_item(batch.idx, "running")

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
        self.worker.progress.connect(self._on_dl_progress)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self._on_item_ok)
        self.worker.failed.connect(self._on_item_fail)
        self.worker.start()

    def _on_dl_progress(self, pct: int) -> None:
        """Update the bar and show a live ETA once estimable.

        setFormat() triggers a relayout, so it is only called when the
        displayed string actually changes (yt-dlp progress emits fast).
        """
        self.dl_progress.setValue(pct)
        eta = self._eta.update(pct)
        fmt = (
            f"{self._eta_label} • ETA {eta}" if eta is not None
            else self._eta_label
        )
        if fmt != self._eta_format:
            self._eta_format = fmt
            self.dl_progress.setFormat(fmt)

    def _on_item_ok(self, path: str) -> None:
        batch = self._batch
        if batch is None:
            return
        url = batch.urls[batch.idx] if batch.idx < len(batch.urls) else ""

        # Record the result in its own try: stat()/rename/history can all fail
        # (TOCTOU on a file that just vanished, full disk, ...) and that must
        # never escape the Qt slot — a raised exception used to skip
        # batch.idx += 1 / _kick_next() and freeze the whole queue.
        completed = False   # a history entry was written for a real on-disk file
        row_status = "done" # icon shown on the queue row
        missing_note: str | None = None
        playlist_failed = 0 # playlist items the worker could not download
        try:
            if isinstance(path, str) and path.startswith(("playlist_files:", "playlist:")):
                # Playlist batches: collect the final paths (post-rename when
                # cleaning ran, original otherwise) and build a readable history
                # label instead of the raw worker payload.
                if path.startswith("playlist_files:"):
                    playlist_files, playlist_label, renamed, playlist_failed = self._collect_playlist_files(path, batch)
                else:
                    playlist_files, playlist_label, renamed, playlist_failed = self._discover_playlist_files(path, batch)
                total_bytes = sum(self._size_of(f) for f in playlist_files)
                self._history.append(
                    url=url, filepath=batch.outdir, filename=playlist_label,
                    filesize=total_bytes,
                    type_="playlist", container=batch.container,
                    audio_only=batch.audio_only, status="completed",
                )
                completed = True
                self._set_last_result(Path(batch.outdir))
            else:
                final_path, renamed = self._finish_single_file(path, batch)
                if final_path.exists():
                    self._history.append(
                        url=url, filepath=str(final_path), filename=final_path.name,
                        filesize=self._size_of(final_path),
                        type_="audio" if batch.audio_only else "video",
                        container=batch.container, audio_only=batch.audio_only,
                        status="completed",
                    )
                    completed = True
                    self._set_last_result(final_path)
                else:
                    # yt-dlp can report success for something we cannot find
                    # (removed/moved externally, or a path we failed to
                    # resolve). Recording status="completed" would put a dead
                    # entry in the history: zero size, a folder that cannot be
                    # opened, and a "requeue" that hides what really happened.
                    self._history.append(
                        url=url, filepath=str(final_path), filename=final_path.name,
                        filesize=0,
                        type_="audio" if batch.audio_only else "video",
                        container=batch.container, audio_only=batch.audio_only,
                        status="failed",
                        error=f"File not found after download: {final_path}",
                    )
                    row_status = "failed"
                    missing_note = (
                        f"[{batch.idx + 1}/{batch.total}] Reported OK, but the "
                        f"file is missing: {final_path.name}"
                    )

            if batch.clean_tags and renamed:
                self.status_label.setText(
                    f"Cleaned {len(renamed)} file(s), e.g. {renamed[0]!r}"
                )
            if playlist_failed:
                # Partial playlist success: the queue row says "done" (files
                # were saved), so say out loud how many items did not make it.
                got = len(playlist_files)
                summary = (
                    f"Downloaded {got} of {got + playlist_failed} playlist "
                    f"item(s) — {playlist_failed} failed"
                )
                if renamed:
                    summary += f", {len(renamed)} cleaned"
                self.status_label.setText(f"[{batch.idx + 1}/{batch.total}] {summary}")
            if missing_note is not None:
                self.status_label.setText(missing_note)
            self._mark_queue_item(batch.idx, row_status)
        except Exception as exc:  # noqa: BLE001 — slot boundary: report, don't stall
            log.warning("Could not record finished download %s: %s", url, exc)
            self.status_label.setText(
                f"[{batch.idx + 1}/{batch.total}] Finished, but recording the "
                f"result failed: {exc}"
            )
            # Best-effort row mark: even this must not escape the slot.
            with contextlib.suppress(Exception):
                self._mark_queue_item(batch.idx, "failed", tooltip=str(exc))
        finally:
            if completed:
                batch.done += 1
            batch.idx += 1
            self.history_changed.emit()
            self._kick_next()

    @staticmethod
    def _size_of(path: Path) -> int:
        """File size in bytes, 0 when it vanished between exists() and stat()."""
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _collect_playlist_files(self, payload: str, batch: BatchState
                                ) -> tuple[list[Path], str, list[str], int]:
        """Rename every file in a playlist_files: payload (single worker
        run that itself collected all output files) and report how many
        playlist items failed.

        A resilient playlist run sends ``{"files": [...], "failed": n,
        "total": n}`` so partial success stays visible; a plain JSON list
        (what older workers and history rows carry) is also accepted.
        Returns (files, label, renamed, failed_count)."""
        try:
            raw = json.loads(payload.removeprefix("playlist_files:"))
        except json.JSONDecodeError:
            raw = None
        if isinstance(raw, dict):
            raw_files = raw.get("files")
            try:
                failed = int(raw.get("failed") or 0)
            except (TypeError, ValueError):
                failed = 0
        else:
            raw_files = raw
            failed = 0
        if not isinstance(raw_files, list):
            raw_files = []
        files: list[Path] = []
        renamed: list[str] = []
        for p in raw_files:
            new = rename_with_cleanup(p, batch.clean_tags)
            files.append(new if new is not None else Path(p))
            if new is not None:
                renamed.append(new.name)
        label = f"Playlist — {len(files)} file(s)"
        if failed:
            label += f", {failed} failed"
        return files, label, renamed, failed

    def _discover_playlist_files(self, payload: str, batch: BatchState
                                 ) -> tuple[list[Path], str, list[str], int]:
        """playlist:N:Title payload — discover files the worker wrote since
        the batch started (used when the worker could not collect paths).
        Returns (files, label, renamed, failed_count) — never a failed
        count: nothing is known about individual items here."""
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
        return files, label, renamed, 0

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
        # Same fencing as _on_item_ok: bookkeeping must never be able to
        # escape the slot and strand the batch mid-queue.
        try:
            self._history.append(
                url=url, filepath="",
                filename=url.split("/")[-1][:40] if url else "?",
                filesize=0, type_="audio" if batch.audio_only else "video",
                container=batch.container, audio_only=batch.audio_only,
                status="failed", error=msg,
            )
            hint = ytdlp_update_hint(msg)
            status = f"[{batch.idx + 1}/{batch.total}] Error: {msg}"
            if hint:
                status += f" — {hint}"
            self._mark_queue_item(
                batch.idx, "failed", tooltip=msg + (f"\n\n{hint}" if hint else "")
            )
            self.status_label.setText(status)
        except Exception as exc:  # noqa: BLE001 — slot boundary: report, don't stall
            log.warning("Could not record failed download %s: %s", url, exc)
            self.status_label.setText(f"[{batch.idx + 1}/{batch.total}] Error: {msg}")
        finally:
            batch.idx += 1
            self.history_changed.emit()
            self._kick_next()

    def _cancel_download(self) -> None:
        """Stop the current batch without blocking the GUI thread.

        Cancellation is cooperative: the flag makes yt-dlp abort at its next
        progress hook (and the converter tabs' workers kill their own
        ffmpeg/ffprobe children). Waiting for the thread here froze the UI
        for up to 7 s, and QThread.terminate() on a thread that is inside
        Python or subprocess code can deadlock the whole process — so the
        worker is left to wind down on its own, kept alive by WorkerTracker
        and ignored thanks to the self._batch is None guards in the handlers.
        """
        was_running = False

        # Disconnect first so an already-queued done/error/finished event
        # cannot drive _kick_next() or a modal dialog after the reset.
        inspect = self._inspect_worker
        if inspect is not None:
            was_running = True
            self._disconnect_signals(inspect, "done", "error", "progress")
            inspect.cancel()
            self._inspect_worker = None

        worker = self.worker
        if worker is not None:
            was_running = True
            self._disconnect_signals(worker, "progress", "status",
                                     "finished_ok", "failed")
            worker.cancel()

        if was_running:
            cleaned = self._cleanup_recent_downloads()
            if cleaned:
                self.status_label.setText(
                    f"Cancelled. Cleaned {len(cleaned)} completed file(s), "
                    f"e.g. {cleaned[0]!r}"
                )
            else:
                self.status_label.setText("Cancelled.")
        self._reset_after_batch()

    @staticmethod
    def _disconnect_signals(worker, *names: str) -> None:
        """Drop every connection to the named signals (best-effort).

        PySide raises RuntimeError when a signal has no connections left —
        expected here, since handlers may already have run.
        """
        for name in names:
            with contextlib.suppress(RuntimeError, TypeError):
                getattr(worker, name).disconnect()

    def shutdown(self) -> None:
        """Cancel every worker when the window closes (idempotent)."""
        info = self._info_worker
        if info is not None:
            self._disconnect_signals(info, "result", "error")
            info.cancel()
            self._info_worker = None
            self.info_btn.setEnabled(True)
        self._cancel_download()

    def running_workers(self) -> list[QThread]:
        """Live workers, so MainWindow can wait for them at shutdown."""
        return self._tracker.running()

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

    def _reset_after_batch(self, *, clear_queue: bool = True) -> None:
        """Return the tab to idle after a batch ends.

        clear_queue=False keeps the queued URLs: used when the batch never
        actually started (playlist declined, inspect failed), where wiping
        the queue threw away entries the user had not acted on yet.
        """
        if clear_queue:
            self.current_batch.clear()
            self.queue_list.clear()
        # Drop the last download worker reference; the tracker keeps the
        # object alive until its thread has fully exited.
        self.worker = None
        self._batch = None
        self._set_batch_busy(False)
        # Reset the bar's format: the "[i/n] … ETA" string is per-batch.
        self._eta_label = "%p%"
        self._eta_format = "%p%"
        self.dl_progress.setFormat("%p%")
        self.cancel_btn.setEnabled(False)
        # The thaw restores the pre-batch state, but the batch may have just
        # emptied the queue (clear_queue=True) — Start/Remove/Clear must end
        # up matching the *current* queue (P3).
        self._sync_queue_actions()
