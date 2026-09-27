"""Video converter tab — file queue and FFmpeg VideoConvertWorker.

Extracted from the MainWindow monolith (window.py) with behavior kept 1:1.
The cleanup-tag list is owned by the Downloader tab's clean_tags_input and
shared here through a tags_provider callable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from .cleaner import parse_tag_list
from .converter_worker import (
    PROGRESS_BAND,
    VIDEO_INPUT_EXTENSIONS,
    VIDEO_OUTPUT_FORMATS,
    VIDEO_QUALITY_PRESETS,
    VideoConvertWorker,
)
from .history import DownloadHistory
from .icon import mark_status
from .progress import EtaEstimator
from .settings import AppSettings
from .utils import (
    install_placeholder,
    open_in_explorer,
    open_result,
    scan_media_files,
    set_controls_busy,
)
from .worker_tracking import WorkerTracker

log = logging.getLogger(__name__)


class VideoConvertTab(QWidget):
    """Tab 3 — batch video conversion queue."""

    #: Emitted after a conversion outcome lands in the shared history, so
    #: MainWindow can refresh the History tab (same pattern as DownloadTab).
    history_changed = Signal()
    #: Emitted when a batch starts / finishes so MainWindow can mark the
    #: window title (same contract as DownloadTab).
    batch_started = Signal()
    batch_finished = Signal(int, int)  # done, total

    def __init__(self, settings: AppSettings,
                 tags_provider: Callable[[], str],
                 history: DownloadHistory,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tags_provider = tags_provider
        self._history = history
        self._tracker = WorkerTracker()
        self._video_conv_files: list[Path] = []
        self._video_conv_worker: VideoConvertWorker | None = None
        self._video_conv_queue: list[Path] = []
        self._video_conv_idx = 0
        self._video_conv_total = 0
        self._video_conv_done = 0
        self._video_conv_active = False
        self._video_conv_clean_tags: list[str] | None = None  # snapshotted
        self._eta = EtaEstimator()
        self._eta_format = "%p%"
        #: Last converted file — what "Open last result" opens.
        self._last_result: Path | None = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  Public API — used by MainWindow (drag-drop)                         #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        """True while a conversion queue is running."""
        return self._video_conv_active

    def add_file(self, path: Path) -> bool:
        """Queue a single file; True when it was actually added."""
        before = len(self._video_conv_files)
        self._video_conv_add_file(path)
        return len(self._video_conv_files) > before

    def add_folder(self, folder: Path) -> int:
        """Queue supported video files under a folder; returns count added."""
        return self._video_conv_add_folder(folder)

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        root.addWidget(QLabel("Videos:"))
        self.video_conv_file_list = QListWidget()
        self.video_conv_file_list.setMinimumHeight(90)
        self.video_conv_file_list.setIconSize(QSize(14, 14))
        self.video_conv_file_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_conv_file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        root.addWidget(self.video_conv_file_list, 1)

        # Empty-state placeholder rendered *inside* the list box (P2) —
        # the old label sat below it as a separate row.
        self._video_conv_empty = install_placeholder(
            self.video_conv_file_list,
            "No videos yet.\nAdd videos or a folder to get started.",
        )

        fbtn_row = QHBoxLayout()
        self.video_conv_add_files_btn = QPushButton("Files")
        self.video_conv_add_files_btn.clicked.connect(self._video_conv_browse_files)
        self.video_conv_add_folder_btn = QPushButton("Folder")
        self.video_conv_add_folder_btn.clicked.connect(self._video_conv_browse_folder)
        self.video_conv_remove_btn = QPushButton("Remove")
        self.video_conv_remove_btn.clicked.connect(self._video_conv_remove_selected)
        self.video_conv_clear_btn = QPushButton("Clear")
        self.video_conv_clear_btn.clicked.connect(self._video_conv_clear_files)
        fbtn_row.addWidget(self.video_conv_add_files_btn)
        fbtn_row.addWidget(self.video_conv_add_folder_btn)
        fbtn_row.addWidget(self.video_conv_remove_btn)
        fbtn_row.addWidget(self.video_conv_clear_btn)
        fbtn_row.addStretch()
        root.addLayout(fbtn_row)

        # Format + quality — compact grid
        ctrl = QGridLayout()
        ctrl.setHorizontalSpacing(6)
        ctrl.setVerticalSpacing(4)
        ctrl.addWidget(QLabel("Format:"), 0, 0)
        self.video_conv_fmt_combo = QComboBox()
        self.video_conv_fmt_combo.addItems(VIDEO_OUTPUT_FORMATS)
        self.video_conv_fmt_combo.setCurrentText("mp4")
        ctrl.addWidget(self.video_conv_fmt_combo, 0, 1)

        ctrl.addWidget(QLabel("Quality:"), 0, 2)
        self.video_conv_quality_combo = QComboBox()
        for label, value in VIDEO_QUALITY_PRESETS:
            self.video_conv_quality_combo.addItem(label, value)
        self.video_conv_quality_combo.setCurrentIndex(1)
        ctrl.addWidget(self.video_conv_quality_combo, 0, 3)
        ctrl.setColumnStretch(1, 1)
        ctrl.setColumnStretch(3, 1)
        root.addLayout(ctrl)

        # Checkboxes
        chk_row = QHBoxLayout()
        self.video_conv_audio_copy_chk = QCheckBox("Copy audio")
        self.video_conv_audio_copy_chk.setChecked(True)
        self.video_conv_clean_chk = QCheckBox("Clean title")
        self.video_conv_clean_chk.setChecked(True)
        chk_row.addWidget(self.video_conv_audio_copy_chk)
        chk_row.addWidget(self.video_conv_clean_chk)
        chk_row.addStretch()
        root.addLayout(chk_row)

        # Output folder
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.video_conv_dir_input = QLineEdit(
            self._settings.saved_dir("convert_video", Path.home() / "Videos")
        )
        out_row.addWidget(self.video_conv_dir_input, 1)
        video_conv_browse_btn = QPushButton("Browse")
        video_conv_browse_btn.clicked.connect(self._video_conv_browse_dir)
        out_row.addWidget(video_conv_browse_btn)
        video_conv_open_btn = QPushButton("Open")
        video_conv_open_btn.setToolTip("Open the output folder in your file manager")
        video_conv_open_btn.clicked.connect(
            lambda: open_in_explorer(self.video_conv_dir_input.text().strip())
        )
        out_row.addWidget(video_conv_open_btn)
        root.addLayout(out_row)

        # Convert / Cancel + Progress + Status
        btn_row = QHBoxLayout()
        self.video_conv_start_btn = QPushButton("Convert")
        self.video_conv_start_btn.setObjectName("primaryButton")
        self.video_conv_start_btn.clicked.connect(self._video_conv_start)
        self.video_conv_cancel_btn = QPushButton("Cancel")
        self.video_conv_cancel_btn.setObjectName("dangerButton")
        self.video_conv_cancel_btn.clicked.connect(self._video_conv_cancel)
        self.video_conv_cancel_btn.setEnabled(False)
        btn_row.addWidget(self.video_conv_start_btn)
        btn_row.addWidget(self.video_conv_cancel_btn)
        btn_row.addStretch()
        # "Done → name" was unactionable (P2): this opens the file.
        self.open_last_btn = QPushButton("Open last result")
        self.open_last_btn.setEnabled(False)
        self.open_last_btn.setToolTip(
            "Open the last converted file with your default app."
        )
        self.open_last_btn.clicked.connect(self._open_last_result)
        btn_row.addWidget(self.open_last_btn)
        root.addLayout(btn_row)

        self.video_conv_progress = QProgressBar()
        self.video_conv_progress.setRange(0, 100)
        root.addWidget(self.video_conv_progress)
        self.video_conv_status_label = QLabel("Ready.")
        # Long errors wrap instead of clipping; selectable so they can be read.
        self.video_conv_status_label.setWordWrap(True)
        self.video_conv_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.video_conv_status_label)

        # Controls _video_conv_kick_next() reads per item — frozen for the
        # whole batch by _video_conv_freeze_settings() so one batch cannot
        # convert with mixed settings or write to several folders.
        self._video_conv_settings_widgets = [
            self.video_conv_fmt_combo, self.video_conv_quality_combo,
            self.video_conv_audio_copy_chk, self.video_conv_clean_chk,
            self.video_conv_dir_input, video_conv_browse_btn,
        ]

    # ------------------------------------------------------------------ #
    #  File list helpers                                                   #
    # ------------------------------------------------------------------ #

    def _mark_video_conv_item(self, row: int, status: str,
                              tooltip: str = "") -> None:
        """Give a video row its batch status (icon + color + tooltip).

        The painting is shared with the download and audio queues via
        icon.mark_status(), so all three read identically.
        """
        mark_status(self.video_conv_file_list.item(row), status, tooltip)

    def _set_last_result(self, path: Path) -> None:
        """Publish the file that just converted to the Open button."""
        self._last_result = path
        self.open_last_btn.setEnabled(True)
        self.open_last_btn.setToolTip(f"Open last result: {path}")

    def _open_last_result(self) -> None:
        """Open the last converted file (P2: "Done → name" was read-only)."""
        if self._last_result is None:
            return
        if not open_result(self._last_result):
            self.video_conv_status_label.setText(
                f"Result not found: {self._last_result}"
            )

    def _video_conv_add_file(self, path: Path) -> None:
        if path in self._video_conv_files:
            return
        ext = path.suffix.lstrip(".").lower()
        if ext not in VIDEO_INPUT_EXTENSIONS:
            self.video_conv_status_label.setText(
                f"Skipped (unsupported): {path.name}"
            )
            return
        self._video_conv_files.append(path)
        item = QListWidgetItem(path.name)
        # Full path on hover — the label is only the file name.
        item.setToolTip(str(path))
        self.video_conv_file_list.addItem(item)

    def _video_conv_add_folder(self, folder: Path) -> int:
        """Queue supported video files under a folder (bounded walk).

        The scan runs on the GUI thread, so app/utils.scan_media_files caps
        how much of the tree it will visit instead of letting an unbounded
        rglob freeze the window.
        """
        files, truncated = scan_media_files(folder, VIDEO_INPUT_EXTENSIONS)
        added = 0
        for path in files:
            before = len(self._video_conv_files)
            self._video_conv_add_file(path)
            added += int(len(self._video_conv_files) > before)
        msg = f"Added {added} video file(s) from folder."
        if truncated:
            msg += " Scan limit reached — the folder tree was only partly added."
        self.video_conv_status_label.setText(msg)
        return added

    def _video_conv_browse_files(self) -> None:
        exts = " ".join(f"*.{e}" for e in sorted(VIDEO_INPUT_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select video files",
            str(Path.home() / "Videos"),
            f"Video files ({exts});;All files (*)",
        )
        for p in paths:
            self._video_conv_add_file(Path(p))

    def _video_conv_browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to scan", str(Path.home() / "Videos")
        )
        if folder:
            self._video_conv_add_folder(Path(folder))

    def _video_conv_remove_selected(self) -> None:
        rows = sorted(
            {self.video_conv_file_list.row(item)
             for item in self.video_conv_file_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            if 0 <= row < len(self._video_conv_files):
                self._video_conv_files.pop(row)
            self.video_conv_file_list.takeItem(row)

    def _video_conv_clear_files(self) -> None:
        self._video_conv_files.clear()
        self.video_conv_file_list.clear()
        self.video_conv_status_label.setText("File list cleared.")

    def _video_conv_browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.video_conv_dir_input.text()
        )
        if d:
            self.video_conv_dir_input.setText(d)
            self._settings.save_dir("convert_video", d)

    # ------------------------------------------------------------------ #
    #  Conversion flow                                                     #
    # ------------------------------------------------------------------ #

    def _video_conv_start(self) -> None:
        if not self._video_conv_files:
            QMessageBox.warning(self, "No files", "Add at least one video to convert.")
            return
        outdir = Path(self.video_conv_dir_input.text().strip())
        if not outdir.is_dir():
            QMessageBox.warning(self, "Bad folder", f"Folder does not exist: {outdir}")
            return
        self._settings.save_dir("convert_video", str(outdir))

        self._video_conv_queue = list(self._video_conv_files)
        self._video_conv_idx = 0
        self._video_conv_total = len(self._video_conv_queue)
        self._video_conv_done = 0
        self._video_conv_active = True
        self._video_conv_freeze_settings(True)
        self.batch_started.emit()
        # Snapshot the shared cleanup-tag list (see the audio tab's note).
        self._video_conv_clean_tags = (
            parse_tag_list(self._tags_provider())
            if self.video_conv_clean_chk.isChecked() else None
        )

        set_controls_busy(
            (self.video_conv_start_btn, self.video_conv_add_files_btn,
             self.video_conv_add_folder_btn, self.video_conv_remove_btn,
             self.video_conv_clear_btn),
            True,
        )
        self.video_conv_cancel_btn.setEnabled(True)
        self._video_conv_kick_next()

    def _video_conv_freeze_settings(self, frozen: bool) -> None:
        """Enable/disable the settings widgets _video_conv_kick_next() reads.

        Disabled for the duration of a batch: leaving format, quality, audio
        copy, cleanup or the output folder editable mid-run let two items in
        the same batch be converted with different settings. Enabled state
        and the "why is this off?" tooltip move together
        (set_controls_busy).
        """
        set_controls_busy(self._video_conv_settings_widgets, frozen)

    def _video_conv_kick_next(self) -> None:
        if not self._video_conv_active:
            # Cancelled (or shutdown) while a finished/failed event was still
            # queued: never start another worker behind the user's back.
            return
        if self._video_conv_idx >= self._video_conv_total:
            self.video_conv_status_label.setText(
                f"Done: {self._video_conv_done}/{self._video_conv_total} converted."
            )
            self.video_conv_progress.setValue(0)
            # Window-title mark before the reset flips _video_conv_active off.
            self.batch_finished.emit(self._video_conv_done,
                                      self._video_conv_total)
            self._video_conv_reset()
            return

        src = self._video_conv_queue[self._video_conv_idx]
        idx_label = f"[{self._video_conv_idx + 1}/{self._video_conv_total}]"
        clean_tags = self._video_conv_clean_tags  # snapshotted at start

        self.video_conv_status_label.setText(f"{idx_label} Preparing {src.name}...")
        self.video_conv_progress.setValue(0)
        self._eta_format = "%p%"
        self.video_conv_progress.setFormat(self._eta_format)
        self._eta.reset(*PROGRESS_BAND)
        self._mark_video_conv_item(self._video_conv_idx, "running")

        self._video_conv_worker = VideoConvertWorker(
            src=src,
            outdir=self.video_conv_dir_input.text().strip(),
            fmt=self.video_conv_fmt_combo.currentText(),
            quality=self.video_conv_quality_combo.currentData(),
            copy_audio=self.video_conv_audio_copy_chk.isChecked(),
            clean_tags=clean_tags,
            idx_label=idx_label,
        )
        self._tracker.track(self._video_conv_worker)
        self._video_conv_worker.progress.connect(self._on_video_conv_progress)
        self._video_conv_worker.status.connect(self.video_conv_status_label.setText)
        self._video_conv_worker.finished_ok.connect(self._on_video_conv_ok)
        self._video_conv_worker.failed.connect(self._on_video_conv_fail)
        self._video_conv_worker.start()

    def _on_video_conv_progress(self, pct: int) -> None:
        """Update the bar value and show a live ETA once estimable.

        setFormat() triggers a relayout, so it is only called when the
        displayed string actually changes (progress itself emits ~5 Hz).
        """
        self.video_conv_progress.setValue(pct)
        eta = self._eta.update(pct)
        fmt = f"%p% • ETA {eta}" if eta is not None else "%p%"
        if fmt != self._eta_format:
            self._eta_format = fmt
            self.video_conv_progress.setFormat(fmt)

    def _record_conversion(self, src: Path, out_path: str,
                           error: str) -> None:
        """Append one conversion's outcome to the shared history model.

        Conversions never reached the History tab before — only downloads
        called ``history.append`` — so a failed conversion left no trace
        beyond a transient status line. Like the Downloader's record-keeping
        this method is self-fenced (a history write must never stall the
        queue), and ``history_changed`` fires on every path so the History
        tab is refreshed whether or not the write succeeded.
        """
        ok = not error
        try:
            if ok:
                filepath = out_path
                filename = Path(out_path).name
                try:
                    filesize = Path(out_path).stat().st_size
                except OSError:
                    filesize = 0
            else:
                filepath = ""
                filename = src.name
                filesize = 0
            self._history.append(
                # url = source file: it feeds the History search haystack and,
                # being a local path (not http), never triggers a bogus requeue.
                url=str(src), filepath=filepath, filename=filename,
                filesize=filesize, type_="video",
                container=self.video_conv_fmt_combo.currentText(),
                audio_only=False,
                status="completed" if ok else "failed",
                error=None if ok else error,
            )
        except Exception as exc:  # noqa: BLE001 — slot boundary: report, don't stall
            log.warning("Could not record conversion of %s: %s", src, exc)
        finally:
            self.history_changed.emit()

    def _on_video_conv_ok(self, out_path: str) -> None:
        if not self._video_conv_active:
            return
        src = (self._video_conv_queue[self._video_conv_idx]
               if self._video_conv_idx < len(self._video_conv_queue)
               else Path(out_path))
        name = Path(out_path).name
        self.video_conv_status_label.setText(
            f"[{self._video_conv_idx + 1}/{self._video_conv_total}] Done → {name}"
        )
        self._mark_video_conv_item(self._video_conv_idx, "done")
        self._record_conversion(src, out_path, "")
        self._set_last_result(Path(out_path))
        self._video_conv_idx += 1
        self._video_conv_done += 1
        self._video_conv_kick_next()

    def _on_video_conv_fail(self, msg: str) -> None:
        if not self._video_conv_active:
            return
        src = (self._video_conv_queue[self._video_conv_idx]
               if self._video_conv_idx < len(self._video_conv_queue)
               else Path("?"))
        # Selectable, word-wrapped status label + a History entry carrying the
        # error: the row tooltip alone vanished when the queue reset.
        self.video_conv_status_label.setText(
            f"[{self._video_conv_idx + 1}/{self._video_conv_total}] Error: {msg}"
        )
        self._mark_video_conv_item(self._video_conv_idx, "failed", tooltip=msg)
        self._record_conversion(src, "", msg)
        self._video_conv_idx += 1
        self._video_conv_kick_next()

    def _video_conv_cancel(self) -> None:
        """Stop the queue without blocking the GUI thread.

        cancel() sets the flag and terminates the live ffmpeg/ffprobe child,
        so the worker winds down on its own; waiting for it here would freeze
        the UI for seconds and terminate() on a thread inside Python or
        subprocess code can deadlock the process. Signals are disconnected
        first so an already-queued finished_ok/failed event does nothing —
        the _video_conv_active guards in the handlers cover the rest.
        """
        worker = self._video_conv_worker
        if worker is not None:
            try:
                worker.progress.disconnect()
                worker.status.disconnect()
                worker.finished_ok.disconnect()
                worker.failed.disconnect()
            except RuntimeError:
                pass
            worker.cancel()
            self.video_conv_status_label.setText("Cancelled.")
        self._video_conv_reset()

    def _video_conv_reset(self) -> None:
        self._video_conv_files.clear()
        self.video_conv_file_list.clear()
        self._video_conv_clean_tags = None
        self._video_conv_freeze_settings(False)
        self._eta_format = "%p%"
        self.video_conv_progress.setFormat(self._eta_format)
        set_controls_busy(
            (self.video_conv_start_btn, self.video_conv_add_files_btn,
             self.video_conv_add_folder_btn, self.video_conv_remove_btn,
             self.video_conv_clear_btn),
            False,
        )
        self.video_conv_cancel_btn.setEnabled(False)
        self._video_conv_worker = None
        self._video_conv_active = False

    # ------------------------------------------------------------------ #
    #  Shutdown — MainWindow.closeEvent polls these until they return []     #
    # ------------------------------------------------------------------ #

    def running_workers(self) -> list[QThread]:
        """Workers still inside run() (see WorkerTracker.running)."""
        return self._tracker.running()

    def shutdown(self) -> None:
        """Cancel any conversion when the window closes (idempotent)."""
        self._video_conv_cancel()
