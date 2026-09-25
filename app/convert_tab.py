"""Audio converter tab — file queue and FFmpeg ConvertWorker.

Extracted from the MainWindow monolith (window.py) with behavior kept 1:1.
The cleanup-tag list is owned by the Downloader tab's clean_tags_input and
shared here through a tags_provider callable (the tabs never touch each
other's widgets).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .cleaner import parse_tag_list
from .converter_worker import (
    AUDIO_BITRATES as CONV_BITRATES,
)
from .converter_worker import (
    DEFAULT_LUFS,
    OUTPUT_FORMATS,
    SAMPLE_RATES,
    SUPPORTED_INPUT_EXTENSIONS,
    ConvertWorker,
)
from .icon import STATUS_COLORS, queue_status_icon
from .progress import EtaEstimator
from .settings import AppSettings
from .utils import open_in_explorer
from .worker_tracking import WorkerTracker


class AudioConverterTab(QWidget):
    """Tab 2 — batch audio conversion queue."""

    def __init__(self, settings: AppSettings,
                 tags_provider: Callable[[], str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tags_provider = tags_provider
        self._tracker = WorkerTracker()
        self._conv_files: list[Path] = []     # files queued for conversion
        self._conv_worker: ConvertWorker | None = None
        self._conv_queue: list[Path] = []
        self._conv_idx = 0
        self._conv_total = 0
        self._conv_done = 0
        self._conv_active = False
        self._eta = EtaEstimator()
        self._eta_format = "%p%"
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  Public API — used by MainWindow (drag-drop)                         #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        """True while a conversion queue is running."""
        return self._conv_active

    def add_file(self, path: Path) -> bool:
        """Queue a single file; True when it was actually added."""
        before = len(self._conv_files)
        self._conv_add_file(path)
        return len(self._conv_files) > before

    def add_folder(self, folder: Path) -> int:
        """Queue supported files under a folder; returns count added."""
        return self._conv_add_folder(folder)

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        # File list
        root.addWidget(QLabel("Files:"))
        self.conv_file_list = QListWidget()
        self.conv_file_list.setMinimumHeight(90)
        self.conv_file_list.setIconSize(QSize(14, 14))
        self.conv_file_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.conv_file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        root.addWidget(self.conv_file_list, 1)

        # Empty-state placeholder (mirrors the History tab)
        self._conv_empty = QLabel(
            "No files yet.\nAdd files or a folder to get started."
        )
        self._conv_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._conv_empty.setStyleSheet(
            "color: palette(text); font-size: 9pt; padding: 40px;"
        )
        root.addWidget(self._conv_empty)

        fbtn_row = QHBoxLayout()
        self.conv_add_files_btn = QPushButton("Files")
        self.conv_add_files_btn.clicked.connect(self._conv_browse_files)
        self.conv_add_folder_btn = QPushButton("Folder")
        self.conv_add_folder_btn.clicked.connect(self._conv_browse_folder)
        self.conv_remove_btn = QPushButton("Remove")
        self.conv_remove_btn.clicked.connect(self._conv_remove_selected)
        self.conv_clear_btn = QPushButton("Clear")
        self.conv_clear_btn.clicked.connect(self._conv_clear_files)
        fbtn_row.addWidget(self.conv_add_files_btn)
        fbtn_row.addWidget(self.conv_add_folder_btn)
        fbtn_row.addWidget(self.conv_remove_btn)
        fbtn_row.addWidget(self.conv_clear_btn)
        fbtn_row.addStretch()
        root.addLayout(fbtn_row)

        # Format + codec controls — compact grid
        fmt_grid = QGridLayout()
        fmt_grid.setHorizontalSpacing(6)
        fmt_grid.setVerticalSpacing(4)
        fmt_grid.addWidget(QLabel("Format:"), 0, 0)
        self.conv_fmt_combo = QComboBox()
        self.conv_fmt_combo.addItems(OUTPUT_FORMATS)
        self.conv_fmt_combo.setCurrentText("m4a")
        self.conv_fmt_combo.currentTextChanged.connect(self._on_conv_fmt_changed)
        fmt_grid.addWidget(self.conv_fmt_combo, 0, 1)

        self.conv_bitrate_label = QLabel("kbps:")
        fmt_grid.addWidget(self.conv_bitrate_label, 0, 2)
        self.conv_bitrate_combo = QComboBox()
        self.conv_bitrate_combo.addItems(CONV_BITRATES)
        self.conv_bitrate_combo.setCurrentText("128")
        fmt_grid.addWidget(self.conv_bitrate_combo, 0, 3)

        sr_label = QLabel("SR:")
        fmt_grid.addWidget(sr_label, 0, 4)
        self.conv_sr_combo = QComboBox()
        for label, _ in SAMPLE_RATES:
            self.conv_sr_combo.addItem(label)
        self.conv_sr_combo.setCurrentIndex(0)
        fmt_grid.addWidget(self.conv_sr_combo, 0, 5)

        # CBR/VBR row
        self.conv_mode_label = QLabel("Mode:")
        fmt_grid.addWidget(self.conv_mode_label, 1, 0)
        self.conv_cbr_radio = QRadioButton("CBR")
        self.conv_vbr_radio = QRadioButton("VBR")
        self.conv_cbr_radio.setChecked(True)
        self.conv_bitrate_group = QButtonGroup(self)
        self.conv_bitrate_group.addButton(self.conv_cbr_radio)
        self.conv_bitrate_group.addButton(self.conv_vbr_radio)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.conv_cbr_radio)
        mode_row.addWidget(self.conv_vbr_radio)
        mode_row.addStretch()
        fmt_grid.addLayout(mode_row, 1, 1, 1, 5)

        fmt_grid.setColumnStretch(1, 1)
        fmt_grid.setColumnStretch(3, 1)
        fmt_grid.setColumnStretch(5, 1)
        root.addLayout(fmt_grid)

        # Normalization — condensed as a row of radio buttons + spinboxes
        norm_box = QGroupBox("Normalization")
        norm_layout = QGridLayout(norm_box)
        norm_layout.setContentsMargins(6, 12, 6, 4)
        norm_layout.setHorizontalSpacing(12)
        norm_layout.setVerticalSpacing(2)

        self.conv_norm_none   = QRadioButton("None")
        self.conv_norm_ebu    = QRadioButton("EBU R128")
        self.conv_norm_peak   = QRadioButton("Peak")
        self.conv_norm_none.setChecked(True)
        norm_group = QButtonGroup(self)
        norm_group.addButton(self.conv_norm_none)
        norm_group.addButton(self.conv_norm_ebu)
        norm_group.addButton(self.conv_norm_peak)
        norm_layout.addWidget(self.conv_norm_none, 0, 0)
        norm_layout.addWidget(self.conv_norm_ebu, 0, 1)
        norm_layout.addWidget(self.conv_norm_peak, 0, 2)

        self.conv_lufs_label = QLabel("LUFS:")
        self.conv_lufs_spin  = QDoubleSpinBox()
        self.conv_lufs_spin.setRange(-30.0, -5.0)
        self.conv_lufs_spin.setSingleStep(0.5)
        self.conv_lufs_spin.setValue(DEFAULT_LUFS)
        self.conv_lufs_spin.setSuffix(" LUFS")
        norm_layout.addWidget(self.conv_lufs_label, 0, 3)
        norm_layout.addWidget(self.conv_lufs_spin, 0, 4)

        self.conv_peak_label = QLabel("Peak:")
        self.conv_peak_spin  = QDoubleSpinBox()
        self.conv_peak_spin.setRange(-12.0, 0.0)
        self.conv_peak_spin.setSingleStep(0.5)
        self.conv_peak_spin.setValue(-1.0)
        self.conv_peak_spin.setSuffix(" dBTP")
        norm_layout.addWidget(self.conv_peak_label, 0, 5)
        norm_layout.addWidget(self.conv_peak_spin, 0, 6)
        norm_layout.setColumnStretch(7, 1)

        self.conv_norm_none.toggled.connect(self._update_norm_ui)
        self.conv_norm_ebu.toggled.connect(self._update_norm_ui)
        self.conv_norm_peak.toggled.connect(self._update_norm_ui)
        self._update_norm_ui()

        root.addWidget(norm_box)

        # Extra checkboxes
        chk_row = QHBoxLayout()
        self.conv_trim_chk = QCheckBox("Trim silence")
        self.conv_clean_chk = QCheckBox("Clean title")
        self.conv_clean_chk.setChecked(True)
        chk_row.addWidget(self.conv_trim_chk)
        chk_row.addWidget(self.conv_clean_chk)
        chk_row.addStretch()
        root.addLayout(chk_row)

        # Output folder
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.conv_dir_input = QLineEdit(
            self._settings.saved_dir("convert_audio", Path.home() / "Music")
        )
        out_row.addWidget(self.conv_dir_input, 1)
        conv_browse_btn = QPushButton("Browse")
        conv_browse_btn.clicked.connect(self._conv_browse_dir)
        out_row.addWidget(conv_browse_btn)
        conv_open_btn = QPushButton("Open")
        conv_open_btn.setToolTip("Open the output folder in your file manager")
        conv_open_btn.clicked.connect(
            lambda: open_in_explorer(self.conv_dir_input.text().strip())
        )
        out_row.addWidget(conv_open_btn)
        root.addLayout(out_row)

        # Convert / Cancel + Progress + Status
        btn_row = QHBoxLayout()
        self.conv_start_btn = QPushButton("Convert")
        self.conv_start_btn.setObjectName("primaryButton")
        self.conv_start_btn.clicked.connect(self._conv_start)
        self.conv_cancel_btn = QPushButton("Cancel")
        self.conv_cancel_btn.setObjectName("dangerButton")
        self.conv_cancel_btn.clicked.connect(self._conv_cancel)
        self.conv_cancel_btn.setEnabled(False)
        btn_row.addWidget(self.conv_start_btn)
        btn_row.addWidget(self.conv_cancel_btn)
        root.addLayout(btn_row)

        self.conv_progress = QProgressBar()
        self.conv_progress.setRange(0, 100)
        root.addWidget(self.conv_progress)
        self.conv_status_label = QLabel("Ready.")
        root.addWidget(self.conv_status_label)

        self._on_conv_fmt_changed(self.conv_fmt_combo.currentText())

    # ------------------------------------------------------------------ #
    #  File list helpers                                                   #
    # ------------------------------------------------------------------ #

    def _refresh_conv_empty(self) -> None:
        """Show the empty-state placeholder iff the file list has no rows."""
        self._conv_empty.setVisible(self.conv_file_list.count() == 0)

    def _mark_conv_item(self, row: int, status: str,
                        tooltip: str = "") -> None:
        """Give a file row its batch status: amber arrow = running, green
        check = done, red cross = failed (+ optional tooltip)."""
        item = self.conv_file_list.item(row)
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

    def _conv_add_file(self, path: Path) -> None:
        """Add a single file to the converter queue (dedup by path)."""
        if path in self._conv_files:
            return
        ext = path.suffix.lstrip(".").lower()
        if ext not in SUPPORTED_INPUT_EXTENSIONS:
            self.conv_status_label.setText(
                f"Skipped (unsupported): {path.name}"
            )
            return
        self._conv_files.append(path)
        self.conv_file_list.addItem(QListWidgetItem(path.name))
        self._refresh_conv_empty()

    def _conv_add_folder(self, folder: Path) -> int:
        """Add supported audio/video files from a folder tree."""
        added = 0
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            before = len(self._conv_files)
            self._conv_add_file(path)
            added += int(len(self._conv_files) > before)
        self.conv_status_label.setText(f"Added {added} file(s) from folder.")
        return added

    def _conv_browse_files(self) -> None:
        exts = " ".join(f"*.{e}" for e in sorted(SUPPORTED_INPUT_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select audio/video files",
            str(Path.home() / "Music"),
            f"Audio/Video files ({exts});;All files (*)",
        )
        for p in paths:
            self._conv_add_file(Path(p))

    def _conv_browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to scan", str(Path.home() / "Music")
        )
        if folder:
            self._conv_add_folder(Path(folder))

    def _conv_remove_selected(self) -> None:
        rows = sorted(
            {self.conv_file_list.row(item) for item in self.conv_file_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            if 0 <= row < len(self._conv_files):
                self._conv_files.pop(row)
            self.conv_file_list.takeItem(row)
        self._refresh_conv_empty()

    def _conv_clear_files(self) -> None:
        self._conv_files.clear()
        self.conv_file_list.clear()
        self._refresh_conv_empty()
        self.conv_status_label.setText("File list cleared.")

    def _conv_browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.conv_dir_input.text()
        )
        if d:
            self.conv_dir_input.setText(d)
            self._settings.save_dir("convert_audio", d)

    def _on_conv_fmt_changed(self, fmt: str) -> None:
        """Show/hide CBR/VBR and bitrate controls depending on format."""
        lossy = fmt in ("mp3", "m4a", "opus")
        for w in (self.conv_mode_label, self.conv_cbr_radio,
                  self.conv_vbr_radio, self.conv_bitrate_label,
                  self.conv_bitrate_combo):
            w.setVisible(lossy)
        # Opus is always VBR — hide the toggle but keep bitrate visible
        if fmt == "opus":
            self.conv_mode_label.setVisible(False)
            self.conv_cbr_radio.setVisible(False)
            self.conv_vbr_radio.setVisible(False)

    def _update_norm_ui(self) -> None:
        """Show the LUFS/peak spinboxes that match the selected mode."""
        ebu  = self.conv_norm_ebu.isChecked()
        peak = self.conv_norm_peak.isChecked()
        self.conv_lufs_label.setVisible(ebu)
        self.conv_lufs_spin.setVisible(ebu)
        self.conv_peak_label.setVisible(peak)
        self.conv_peak_spin.setVisible(peak)

    # ------------------------------------------------------------------ #
    #  Conversion flow                                                     #
    # ------------------------------------------------------------------ #

    def _conv_start(self) -> None:
        if not self._conv_files:
            QMessageBox.warning(self, "No files", "Add at least one file to convert.")
            return
        outdir = Path(self.conv_dir_input.text().strip())
        if not outdir.is_dir():
            QMessageBox.warning(self, "Bad folder", f"Folder does not exist: {outdir}")
            return
        self._settings.save_dir("convert_audio", str(outdir))

        self._conv_queue  = list(self._conv_files)
        self._conv_idx    = 0
        self._conv_total  = len(self._conv_queue)
        self._conv_done   = 0
        self._conv_active = True

        self.conv_start_btn.setEnabled(False)
        self.conv_cancel_btn.setEnabled(True)
        for btn in (self.conv_add_files_btn, self.conv_add_folder_btn,
                    self.conv_remove_btn, self.conv_clear_btn):
            btn.setEnabled(False)
        self._conv_kick_next()

    def _conv_kick_next(self) -> None:
        if self._conv_idx >= self._conv_total:
            self.conv_status_label.setText(
                f"Done: {self._conv_done}/{self._conv_total} converted."
            )
            self.conv_progress.setValue(0)
            self._conv_reset()
            return

        src       = self._conv_queue[self._conv_idx]
        idx_label = f"[{self._conv_idx + 1}/{self._conv_total}]"
        fmt       = self.conv_fmt_combo.currentText()
        lossy     = fmt in ("mp3", "m4a", "opus")
        cbr       = self.conv_cbr_radio.isChecked()
        bitrate   = int(self.conv_bitrate_combo.currentText()) if lossy else 192
        sr_idx    = self.conv_sr_combo.currentIndex()
        sr        = SAMPLE_RATES[sr_idx][1]

        if self.conv_norm_ebu.isChecked():
            norm_mode = "ebu"
        elif self.conv_norm_peak.isChecked():
            norm_mode = "peak"
        else:
            norm_mode = "none"

        clean_tags = None
        if self.conv_clean_chk.isChecked():
            clean_tags = parse_tag_list(self._tags_provider())

        self.conv_status_label.setText(f"{idx_label} Preparing {src.name}...")
        self.conv_progress.setValue(0)
        self._eta_format = "%p%"
        self.conv_progress.setFormat(self._eta_format)
        if norm_mode == "ebu":
            # Two-pass loudnorm spans 5-90 (scan 5-40, encode 40-90).
            self._eta.reset(5, 90)
        else:
            self._eta.reset(10, 90)
        self._mark_conv_item(self._conv_idx, "running")

        self._conv_worker = ConvertWorker(
            src=src,
            outdir=self.conv_dir_input.text().strip(),
            fmt=fmt,
            cbr=cbr,
            bitrate=bitrate,
            sample_rate=sr,
            norm_mode=norm_mode,
            lufs_target=self.conv_lufs_spin.value(),
            peak_target=self.conv_peak_spin.value(),
            trim_silence=self.conv_trim_chk.isChecked(),
            clean_tags=clean_tags,
            idx_label=idx_label,
        )
        self._tracker.track(self._conv_worker)
        self._conv_worker.progress.connect(self._on_conv_progress)
        self._conv_worker.status.connect(self.conv_status_label.setText)
        self._conv_worker.finished_ok.connect(self._on_conv_ok)
        self._conv_worker.failed.connect(self._on_conv_fail)
        self._conv_worker.start()

    def _on_conv_progress(self, pct: int) -> None:
        """Update the bar value and show a live ETA once estimable.

        setFormat() triggers a relayout, so it is only called when the
        displayed string actually changes (progress itself emits ~5 Hz).
        """
        self.conv_progress.setValue(pct)
        eta = self._eta.update(pct)
        fmt = f"%p% • ETA {eta}" if eta is not None else "%p%"
        if fmt != self._eta_format:
            self._eta_format = fmt
            self.conv_progress.setFormat(fmt)

    def _on_conv_ok(self, out_path: str) -> None:
        name = Path(out_path).name
        self.conv_status_label.setText(
            f"[{self._conv_idx + 1}/{self._conv_total}] Done → {name}"
        )
        self._mark_conv_item(self._conv_idx, "done")
        self._conv_idx  += 1
        self._conv_done += 1
        self._conv_kick_next()

    def _on_conv_fail(self, msg: str) -> None:
        self.conv_status_label.setText(
            f"[{self._conv_idx + 1}/{self._conv_total}] Error: {msg}"
        )
        self._mark_conv_item(self._conv_idx, "failed", tooltip=msg)
        self._conv_idx += 1
        self._conv_kick_next()

    def _conv_cancel(self) -> None:
        if self._conv_worker and self._conv_worker.isRunning():
            # Disconnect signals first so an in-flight finished_ok/failed
            # callback can't call _conv_kick_next() on the already-reset
            # state (mirrors the downloader's cancel).
            try:
                self._conv_worker.progress.disconnect()
                self._conv_worker.status.disconnect()
                self._conv_worker.finished_ok.disconnect()
                self._conv_worker.failed.disconnect()
            except RuntimeError:
                pass
            self._conv_worker.cancel()
            if not self._conv_worker.wait(3000):
                self._conv_worker.terminate()
                self._conv_worker.wait(1000)
            self.conv_status_label.setText("Cancelled.")
        self._conv_reset()

    def _conv_reset(self) -> None:
        self._conv_files.clear()
        self.conv_file_list.clear()
        self._refresh_conv_empty()
        self._eta_format = "%p%"
        self.conv_progress.setFormat(self._eta_format)
        self.conv_start_btn.setEnabled(True)
        self.conv_cancel_btn.setEnabled(False)
        for btn in (self.conv_add_files_btn, self.conv_add_folder_btn,
                    self.conv_remove_btn, self.conv_clear_btn):
            btn.setEnabled(True)
        self._conv_worker = None
        self._conv_active = False
