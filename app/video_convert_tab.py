"""Video converter tab — file queue and FFmpeg VideoConvertWorker.

Extracted from the MainWindow monolith (window.py) with behavior kept 1:1.
The cleanup-tag list is owned by the Downloader tab's clean_tags_input and
shared here through a tags_provider callable.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor
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
    VIDEO_INPUT_EXTENSIONS,
    VIDEO_OUTPUT_FORMATS,
    VIDEO_QUALITY_PRESETS,
    VideoConvertWorker,
)
from .icon import STATUS_COLORS, queue_status_icon
from .progress import EtaEstimator
from .settings import AppSettings
from .utils import open_in_explorer
from .worker_tracking import WorkerTracker


class VideoConvertTab(QWidget):
    """Tab 3 — batch video conversion queue."""

    def __init__(self, settings: AppSettings,
                 tags_provider: Callable[[], str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tags_provider = tags_provider
        self._tracker = WorkerTracker()
        self._video_conv_files: list[Path] = []
        self._video_conv_worker: VideoConvertWorker | None = None
        self._video_conv_queue: list[Path] = []
        self._video_conv_idx = 0
        self._video_conv_total = 0
        self._video_conv_done = 0
        self._video_conv_active = False
        self._eta = EtaEstimator()
        self._eta_format = "%p%"
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

        # Empty-state placeholder (mirrors the History tab)
        self._video_conv_empty = QLabel(
            "No videos yet.\nAdd videos or a folder to get started."
        )
        self._video_conv_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_conv_empty.setStyleSheet(
            "color: palette(text); font-size: 9pt; padding: 40px;"
        )
        root.addWidget(self._video_conv_empty)

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
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._video_conv_browse_dir)
        out_row.addWidget(browse_btn)
        video_open_btn = QPushButton("Open")
        video_open_btn.setToolTip("Open the output folder in your file manager")
        video_open_btn.clicked.connect(
            lambda: open_in_explorer(self.video_conv_dir_input.text().strip())
        )
        out_row.addWidget(video_open_btn)
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
        root.addLayout(btn_row)

        self.video_conv_progress = QProgressBar()
        self.video_conv_progress.setRange(0, 100)
        root.addWidget(self.video_conv_progress)
        self.video_conv_status_label = QLabel("Ready.")
        root.addWidget(self.video_conv_status_label)

    # ------------------------------------------------------------------ #
    #  File list helpers                                                   #
    # ------------------------------------------------------------------ #

    def _refresh_video_conv_empty(self) -> None:
        """Show the empty-state placeholder iff the video list has no rows."""
        self._video_conv_empty.setVisible(self.video_conv_file_list.count() == 0)

    def _mark_video_conv_item(self, row: int, status: str,
                              tooltip: str = "") -> None:
        """Give a video row its batch status: amber arrow = running, green
        check = done, red cross = failed (+ optional tooltip)."""
        item = self.video_conv_file_list.item(row)
        if item is None:
            return
        icon = queue_status_icon(status)
        if not icon.isNull():
            item.setIcon(icon)
        color = STATUS_COLORS.get(status)
        if color:
            item.setForeground(QBrush(QColor(color)))
        if tooltip:
            item.setToolTip(tooltip)

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
        self.video_conv_file_list.addItem(QListWidgetItem(path.name))
        self._refresh_video_conv_empty()

    def _video_conv_add_folder(self, folder: Path) -> int:
        added = 0
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            before = len(self._video_conv_files)
            self._video_conv_add_file(path)
            added += int(len(self._video_conv_files) > before)
        self.video_conv_status_label.setText(f"Added {added} video file(s) from folder.")
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
        self._refresh_video_conv_empty()

    def _video_conv_clear_files(self) -> None:
        self._video_conv_files.clear()
        self.video_conv_file_list.clear()
        self._refresh_video_conv_empty()
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

        self.video_conv_start_btn.setEnabled(False)
        self.video_conv_cancel_btn.setEnabled(True)
        for btn in (self.video_conv_add_files_btn, self.video_conv_add_folder_btn,
                    self.video_conv_remove_btn, self.video_conv_clear_btn):
            btn.setEnabled(False)
        self._video_conv_kick_next()

    def _video_conv_kick_next(self) -> None:
        if self._video_conv_idx >= self._video_conv_total:
            self.video_conv_status_label.setText(
                f"Done: {self._video_conv_done}/{self._video_conv_total} converted."
            )
            self.video_conv_progress.setValue(0)
            self._video_conv_reset()
            return

        src = self._video_conv_queue[self._video_conv_idx]
        idx_label = f"[{self._video_conv_idx + 1}/{self._video_conv_total}]"
        clean_tags = None
        if self.video_conv_clean_chk.isChecked():
            clean_tags = parse_tag_list(self._tags_provider())

        self.video_conv_status_label.setText(f"{idx_label} Preparing {src.name}...")
        self.video_conv_progress.setValue(0)
        self._eta_format = "%p%"
        self.video_conv_progress.setFormat(self._eta_format)
        self._eta.reset(10, 90)
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

    def _on_video_conv_ok(self, out_path: str) -> None:
        name = Path(out_path).name
        self.video_conv_status_label.setText(
            f"[{self._video_conv_idx + 1}/{self._video_conv_total}] Done -> {name}"
        )
        self._mark_video_conv_item(self._video_conv_idx, "done")
        self._video_conv_idx += 1
        self._video_conv_done += 1
        self._video_conv_kick_next()

    def _on_video_conv_fail(self, msg: str) -> None:
        self.video_conv_status_label.setText(
            f"[{self._video_conv_idx + 1}/{self._video_conv_total}] Error: {msg}"
        )
        self._mark_video_conv_item(self._video_conv_idx, "failed", tooltip=msg)
        self._video_conv_idx += 1
        self._video_conv_kick_next()

    def _video_conv_cancel(self) -> None:
        if self._video_conv_worker and self._video_conv_worker.isRunning():
            # Disconnect signals first so an in-flight finished_ok/failed
            # callback can't call _video_conv_kick_next() on the already-reset
            # state (mirrors the downloader's cancel).
            try:
                self._video_conv_worker.progress.disconnect()
                self._video_conv_worker.status.disconnect()
                self._video_conv_worker.finished_ok.disconnect()
                self._video_conv_worker.failed.disconnect()
            except RuntimeError:
                pass
            self._video_conv_worker.cancel()
            if not self._video_conv_worker.wait(3000):
                self._video_conv_worker.terminate()
                self._video_conv_worker.wait(1000)
            self.video_conv_status_label.setText("Cancelled.")
        self._video_conv_reset()

    def _video_conv_reset(self) -> None:
        self._video_conv_files.clear()
        self.video_conv_file_list.clear()
        self._refresh_video_conv_empty()
        self._eta_format = "%p%"
        self.video_conv_progress.setFormat(self._eta_format)
        self.video_conv_start_btn.setEnabled(True)
        self.video_conv_cancel_btn.setEnabled(False)
        for btn in (self.video_conv_add_files_btn, self.video_conv_add_folder_btn,
                    self.video_conv_remove_btn, self.video_conv_clear_btn):
            btn.setEnabled(True)
        self._video_conv_worker = None
        self._video_conv_active = False
