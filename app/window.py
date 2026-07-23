"""GUI window for Chrisnov Media Toolkit."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFileDialog, QMessageBox, QProgressBar, QCheckBox,
    QListWidget, QListWidgetItem, QTabWidget, QGroupBox, QRadioButton,
    QButtonGroup, QDoubleSpinBox, QSpinBox, QAbstractItemView, QScrollArea,
    QSizePolicy, QGridLayout,
)
from yt_dlp import YoutubeDL  # noqa: F401 — kept for potential future use in window

from .constants import (
    APP_VERSION, RES_PRESETS, VIDEO_CONTAINERS, AUDIO_CONTAINERS, AUDIO_BITRATES,
    PLAYLIST_CONFIRM_THRESHOLD,
)
from .cleaner import (
    DEFAULT_CLEAN_TAGS, parse_tag_list, rename_with_cleanup, discover_new_files,
)
from .worker import DownloadWorker, PlaylistInspectWorker, FileSizeWorker, audio_extensions, video_extensions
from .converter_worker import (
    ConvertWorker, SUPPORTED_INPUT_EXTENSIONS, OUTPUT_FORMATS,
    AUDIO_BITRATES as CONV_BITRATES, SAMPLE_RATES, DEFAULT_LUFS,
    VideoConvertWorker, VIDEO_INPUT_EXTENSIONS, VIDEO_OUTPUT_FORMATS,
    VIDEO_QUALITY_PRESETS,
)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Chrisnov Media Toolkit v{APP_VERSION}")
        self.setMinimumSize(700, 480)
        self.resize(900, 620)
        self.setAcceptDrops(True)
        self._settings = QSettings("Chrisnov IT Solutions", "Chrisnov Media Toolkit")
        self.current_batch: list[str] = []
        self._conv_files: list[Path] = []   # files queued for conversion
        self._conv_worker: ConvertWorker | None = None
        self._video_conv_files: list[Path] = []
        self._video_conv_worker: VideoConvertWorker | None = None
        self._inspect_worker: PlaylistInspectWorker | None = None
        self._info_worker: FileSizeWorker | None = None
        self._dl_active: bool = False
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  Persistent folder settings (QSettings)                             #
    # ------------------------------------------------------------------ #

    def _saved_dir(self, key: str, default: Path) -> str:
        """Return the saved folder for *key*, falling back to *default* if the
        saved value is missing or no longer exists on disk."""
        value = self._settings.value(f"dirs/{key}", "", type=str)
        if value and Path(value).is_dir():
            return value
        return str(default)

    def _save_dir(self, key: str, path: str) -> None:
        """Persist a folder path for *key* if it points at a real directory."""
        if path and Path(path).is_dir():
            self._settings.setValue(f"dirs/{key}", path)

    @staticmethod
    def _open_in_explorer(path: str) -> None:
        """Open *path* in the system file manager."""
        if path and Path(path).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------------------ #
    #  Drag-and-drop — route to active tab                                #
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
            if md.hasUrls():
                added = 0
                for url in md.urls():
                    local = url.toLocalFile()
                    if local:
                        path = Path(local)
                        if path.is_dir():
                            added += self._conv_add_folder(path)
                        else:
                            before = len(self._conv_files)
                            self._conv_add_file(path)
                            added += int(len(self._conv_files) > before)
                if added:
                    event.acceptProposedAction()
            return
        if tab == 2:
            # Video converter tab — accept local files/folders
            if md.hasUrls():
                added = 0
                for url in md.urls():
                    local = url.toLocalFile()
                    if local:
                        path = Path(local)
                        if path.is_dir():
                            added += self._video_conv_add_folder(path)
                        else:
                            before = len(self._video_conv_files)
                            self._video_conv_add_file(path)
                            added += int(len(self._video_conv_files) > before)
                if added:
                    event.acceptProposedAction()
            return
        # Downloader tab
        if md.hasUrls() and md.urls():
            for url in md.urls():
                local = url.toLocalFile()
                if local:
                    try:
                        text = Path(local).read_text(encoding="utf-8")
                    except OSError:
                        continue
                    self._add_urls_from_text(text)
                    event.acceptProposedAction()
                    return
                s = url.toString()
                if s.startswith(("http://", "https://")):
                    self._add_url(s)
                    event.acceptProposedAction()
                    return
        elif md.hasText():
            self._add_urls_from_text(md.text())
            event.acceptProposedAction()

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
        self._tabs.addTab(self._wrap_tab(self._build_downloader_tab()), "\u2b07  Downloader")
        self._tabs.addTab(self._wrap_tab(self._build_converter_tab()), "\u266b  Audio Converter")
        self._tabs.addTab(self._wrap_tab(self._build_video_converter_tab()), "\u25a3  Video Converter")
        root.addWidget(self._tabs)

    def _wrap_tab(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget {
                font-family: "Segoe UI", "Noto Sans", Arial, sans-serif;
                font-size: 9pt;
            }
            QTabWidget::pane {
                border: 1px solid #d7dce2;
                border-radius: 6px;
                background: #fbfcfd;
            }
            QTabBar::tab {
                padding: 4px 10px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                background: #eef2f6;
                color: #26313d;
                font-size: 9pt;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                border: 1px solid #d7dce2;
                border-bottom-color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #d7dce2;
                border-radius: 6px;
                margin-top: 8px;
                padding: 8px 8px 6px 8px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px;
            }
            QLineEdit, QComboBox, QListWidget, QDoubleSpinBox, QSpinBox {
                min-height: 26px;
                border: 1px solid #cbd3dc;
                border-radius: 5px;
                padding: 2px 6px;
                background: #ffffff;
                font-size: 9pt;
            }
            QPushButton {
                min-height: 27px;
                padding: 3px 10px;
                border: 1px solid #b8c2cc;
                border-radius: 5px;
                background: #f5f7fa;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: #edf2f7;
            }
            QPushButton:pressed {
                background: #e2e8f0;
            }
            QPushButton:disabled {
                color: #8a94a0;
                background: #edf0f3;
            }
            QPushButton#primaryButton {
                color: #ffffff;
                border-color: #226ac7;
                background: #2f80ed;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background: #2a73d8;
            }
            QPushButton#dangerButton {
                color: #a62929;
                border-color: #e1b4b4;
                background: #fff5f5;
            }
            QPushButton#dangerButton:hover {
                background: #ffe8e8;
            }
            QCheckBox, QRadioButton {
                font-size: 9pt;
            }
            QProgressBar {
                min-height: 14px;
                max-height: 16px;
                border: 1px solid #cbd3dc;
                border-radius: 6px;
                text-align: center;
                background: #eef2f6;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: #2f80ed;
            }
            QLabel#appNameLabel {
                font-size: 11pt;
                font-weight: 700;
                color: #1a2533;
            }
            QLabel#versionLabel {
                font-size: 8pt;
                color: #8a94a0;
                padding-top: 2px;
            }
            QPushButton#aboutButton {
                font-size: 8pt;
                color: #4a5568;
                border-color: #d7dce2;
                background: transparent;
                min-height: 24px;
                padding: 2px 8px;
            }
            QPushButton#aboutButton:hover {
                background: #edf2f7;
            }
        """)

    # ------------------------------------------------------------------ #
    #  Tab 1 — Downloader                                                  #
    # ------------------------------------------------------------------ #

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

        platform_str = {
            "win32":  "Windows",
            "darwin": "macOS",
            "linux":  "Linux",
        }.get(sys.platform, sys.platform)
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        dlg = QDialog(self)
        dlg.setWindowTitle("About Chrisnov Media Toolkit")
        dlg.setFixedWidth(380)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(4)

        # App name + version
        name_lbl = QLabel("Chrisnov Media Toolkit")
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("font-size: 13pt; font-weight: 700; color: #1a2533;")
        layout.addWidget(name_lbl)

        ver_lbl = QLabel(f"Version {APP_VERSION}")
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setStyleSheet("font-size: 9pt; color: #8a94a0; margin-bottom: 12px;")
        layout.addWidget(ver_lbl)

        # Divider
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #d7dce2; margin: 8px 0;")
        layout.addWidget(line)

        # Info rows
        def _row(label: str, value: str) -> None:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #4a5568; font-size: 9pt;")
            val = QLabel(value)
            val.setStyleSheet("color: #1a2533; font-size: 9pt;")
            val.setAlignment(Qt.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)

        _row("Platform",  platform_str)
        _row("Python",    py_ver)
        _row("PySide6",   pyside_ver)
        _row("yt-dlp",    ytdlp_ver)

        # Divider
        line2 = QLabel()
        line2.setFixedHeight(1)
        line2.setStyleSheet("background: #d7dce2; margin: 8px 0;")
        layout.addWidget(line2)

        # Description
        desc = QLabel(
            "A minimal media downloader and converter\n"
            "built with PySide6, yt-dlp, and FFmpeg."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("font-size: 9pt; color: #4a5568;")
        layout.addWidget(desc)

        credit = QLabel("© Chrisnov IT Solutions")
        credit.setAlignment(Qt.AlignCenter)
        credit.setStyleSheet("font-size: 8pt; color: #8a94a0; margin-top: 4px;")
        layout.addWidget(credit)

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

    def _build_downloader_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
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
        self.queue_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        self.embed_meta_chk.setChecked(True)
        chk_row2.addWidget(self.embed_meta_chk)
        self.embed_thumb_chk = QCheckBox("Embed thumbnail")
        self.embed_thumb_chk.setToolTip(
            "Embed cover art. Works with mp3/m4a (audio) and mp4/mkv (video)."
        )
        chk_row2.addWidget(self.embed_thumb_chk)
        chk_row2.addStretch()
        root.addLayout(chk_row2)

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
            self._saved_dir("download_video", Path.home() / "Videos")
        )
        out_row.addWidget(self.dir_input, 1)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_dl)
        out_row.addWidget(self.browse_btn)
        self.open_dir_btn = QPushButton("Open")
        self.open_dir_btn.setToolTip("Open the output folder in your file manager")
        self.open_dir_btn.clicked.connect(
            lambda: self._open_in_explorer(self.dir_input.text().strip())
        )
        out_row.addWidget(self.open_dir_btn)
        root.addLayout(out_row)

        # Info box (hidden by default, shown after Info button click)
        self.info_box = QLabel("")
        self.info_box.setWordWrap(True)
        self.info_box.setStyleSheet(
            "background: #f0f5ff; border: 1px solid #b3d4ff; "
            "border-radius: 4px; padding: 4px 8px; font-size: 9pt; color: #1a2533;"
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

        return w

    # ------------------------------------------------------------------ #
    #  Tab 2 — Converter                                                   #
    # ------------------------------------------------------------------ #

    def _build_converter_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        # File list
        root.addWidget(QLabel("Files:"))
        self.conv_file_list = QListWidget()
        self.conv_file_list.setMinimumHeight(90)
        self.conv_file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.conv_file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        root.addWidget(self.conv_file_list, 1)

        fbtn_row = QHBoxLayout()
        add_files_btn = QPushButton("Files")
        add_files_btn.clicked.connect(self._conv_browse_files)
        add_folder_btn = QPushButton("Folder")
        add_folder_btn.clicked.connect(self._conv_browse_folder)
        self.conv_remove_btn = QPushButton("Remove")
        self.conv_remove_btn.clicked.connect(self._conv_remove_selected)
        self.conv_clear_btn = QPushButton("Clear")
        self.conv_clear_btn.clicked.connect(self._conv_clear_files)
        fbtn_row.addWidget(add_files_btn)
        fbtn_row.addWidget(add_folder_btn)
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
        self.conv_bitrate_group = QButtonGroup(w)
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
        norm_group = QButtonGroup(w)
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

        def _update_norm_ui() -> None:
            ebu  = self.conv_norm_ebu.isChecked()
            peak = self.conv_norm_peak.isChecked()
            self.conv_lufs_label.setVisible(ebu)
            self.conv_lufs_spin.setVisible(ebu)
            self.conv_peak_label.setVisible(peak)
            self.conv_peak_spin.setVisible(peak)

        self.conv_norm_none.toggled.connect(_update_norm_ui)
        self.conv_norm_ebu.toggled.connect(_update_norm_ui)
        self.conv_norm_peak.toggled.connect(_update_norm_ui)
        _update_norm_ui()

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
            self._saved_dir("convert_audio", Path.home() / "Music")
        )
        out_row.addWidget(self.conv_dir_input, 1)
        conv_browse_btn = QPushButton("Browse")
        conv_browse_btn.clicked.connect(self._conv_browse_dir)
        out_row.addWidget(conv_browse_btn)
        conv_open_btn = QPushButton("Open")
        conv_open_btn.setToolTip("Open the output folder in your file manager")
        conv_open_btn.clicked.connect(
            lambda: self._open_in_explorer(self.conv_dir_input.text().strip())
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
        return w

    # ------------------------------------------------------------------ #
    #  Tab 3 — Video Converter                                             #
    # ------------------------------------------------------------------ #

    def _build_video_converter_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        root.addWidget(QLabel("Videos:"))
        self.video_conv_file_list = QListWidget()
        self.video_conv_file_list.setMinimumHeight(90)
        self.video_conv_file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_conv_file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        root.addWidget(self.video_conv_file_list, 1)

        fbtn_row = QHBoxLayout()
        add_files_btn = QPushButton("Files")
        add_files_btn.clicked.connect(self._video_conv_browse_files)
        add_folder_btn = QPushButton("Folder")
        add_folder_btn.clicked.connect(self._video_conv_browse_folder)
        self.video_conv_remove_btn = QPushButton("Remove")
        self.video_conv_remove_btn.clicked.connect(self._video_conv_remove_selected)
        self.video_conv_clear_btn = QPushButton("Clear")
        self.video_conv_clear_btn.clicked.connect(self._video_conv_clear_files)
        fbtn_row.addWidget(add_files_btn)
        fbtn_row.addWidget(add_folder_btn)
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
            self._saved_dir("convert_video", Path.home() / "Videos")
        )
        out_row.addWidget(self.video_conv_dir_input, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._video_conv_browse_dir)
        out_row.addWidget(browse_btn)
        video_open_btn = QPushButton("Open")
        video_open_btn.setToolTip("Open the output folder in your file manager")
        video_open_btn.clicked.connect(
            lambda: self._open_in_explorer(self.video_conv_dir_input.text().strip())
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

        return w

    # ------------------------------------------------------------------ #
    #  Downloader — URL helpers                                            #
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

        if self._dl_active:
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

        self._info_worker = FileSizeWorker(url, audio, height, fmt)
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
        if not self._dl_active:
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
        if not self._dl_active:
            self.status_label.setText("Ready.")
            self.download_btn.setEnabled(True)
        self.info_box.setText(
            f"<span style='color:#a62929;'>Error: {err}</span>"
        )
        self.info_box.show()

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

    def _add_url(self, url: str) -> None:
        if url in self.current_batch:
            return
        self.current_batch.append(url)
        if self._is_playlist_url(url):
            pid = "?list=" + url.split("list=")[-1].split("&")[0][:11]
            display = f"📋 {pid}"
        elif "v=" in url:
            vid = url.split("v=")[-1].split("&")[0]
            display = f"[{vid[:11]}]"
        else:
            display = url[:40]
        self.queue_list.addItem(QListWidgetItem(display))
        if self._is_playlist_url(url):
            self.status_label.setText(
                "Playlist detected. Will fetch all entries on Start (size confirmation if >50)."
            )

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
        if "list=" not in url:
            return False
        return "youtube.com" in url or "youtu.be" in url

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
            self._save_dir(key, d)

    def _on_audio_toggled(self, checked: bool) -> None:
        # Remember whatever folder is currently shown for the mode we're leaving,
        # then restore the saved folder for the mode we're entering.
        current = self.dir_input.text().strip()
        self.container_combo.clear()
        if checked:
            self._save_dir("download_video", current)
            self.container_combo.addItems(AUDIO_CONTAINERS)
            self.container_combo.setCurrentText("mp3")
            self.res_combo.setEnabled(False)
            self.res_label.setEnabled(False)
            self.bitrate_combo.setEnabled(True)
            self.bitrate_label.setEnabled(True)
            self.dir_input.setText(
                self._saved_dir("download_audio", Path.home() / "Music")
            )
        else:
            self._save_dir("download_audio", current)
            self.container_combo.addItems(VIDEO_CONTAINERS)
            self.container_combo.setCurrentText("mp4")
            self.res_combo.setEnabled(True)
            self.res_label.setEnabled(True)
            self.bitrate_combo.setEnabled(False)
            self.bitrate_label.setEnabled(False)
            self.dir_input.setText(
                self._saved_dir("download_video", Path.home() / "Videos")
            )

    def _on_clean_toggled(self, checked: bool) -> None:
        self.clean_tags_input.setEnabled(checked)

    # ------------------------------------------------------------------ #
    #  Downloader — download flow                                          #
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
        self._save_dir(
            "download_audio" if self.audio_only_chk.isChecked() else "download_video",
            outdir,
        )

        self.batch       = list(self.current_batch)
        self.batch_idx   = 0
        self.batch_total = len(self.batch)
        self.batch_done  = 0
        self.outdir      = outdir
        self.audio_only  = self.audio_only_chk.isChecked()
        self.height      = RES_PRESETS[self.res_combo.currentIndex()][1]
        self.container   = self.container_combo.currentText()
        self.bitrate     = int(self.bitrate_combo.currentText())
        self.clean_tags  = (
            parse_tag_list(self.clean_tags_input.text())
            if self.clean_chk.isChecked() else None
        )
        self.embed_metadata  = self.embed_meta_chk.isChecked()
        self.embed_thumbnail = self.embed_thumb_chk.isChecked()

        if self.skip_dup_chk.isChecked():
            archive_dir = Path.home() / ".config" / "chrisnov-media-toolkit"
            archive_dir.mkdir(parents=True, exist_ok=True)
            suffix = "_audio" if self.audio_only else "_video"
            archive_path = archive_dir / f"archive{suffix}.txt"
            old_archive_path = (
                Path.home() / ".config" / "chrisnov-yt-downloader" / f"archive{suffix}.txt"
            )
            if old_archive_path.exists() and not archive_path.exists():
                archive_path.write_text(old_archive_path.read_text(encoding="utf-8"), encoding="utf-8")
            self.archive_path = str(archive_path)
        else:
            self.archive_path = None

        self.batch_start_ts = time.time()

        if self.clean_chk.isChecked() and not self.clean_tags:
            QMessageBox.warning(
                self, "No cleanup tags",
                "Clean title is on but no tags are listed. Returning.",
            )
            return

        # Cancel any in-flight info fetch
        if self._info_worker is not None and self._info_worker.isRunning():
            self._info_worker.cancel()
            self._info_worker.wait(3000)
            self._info_worker = None
            self.info_btn.setEnabled(True)
            self.info_btn.setText("Info")

        # Disable UI immediately so the user can't double-submit
        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.add_queue_btn.setEnabled(False)
        self.url_input.setEnabled(False)
        self._dl_active = True

        playlist_urls = [u for u in self.batch if self._is_playlist_url(u)]
        if playlist_urls:
            # Inspect playlist sizes off the GUI thread
            self.status_label.setText(
                f"Inspecting {len(playlist_urls)} playlist URL(s)..."
            )
            self._inspect_worker = PlaylistInspectWorker(
                playlist_urls, self.audio_only, PLAYLIST_CONFIRM_THRESHOLD
            )
            self._inspect_worker.progress.connect(self.status_label.setText)
            self._inspect_worker.done.connect(self._on_inspect_done)
            self._inspect_worker.error.connect(self._on_inspect_error)
            self._inspect_worker.start()
        else:
            self._kick_next()

    def _on_inspect_done(self, big: list) -> None:
        """Called when PlaylistInspectWorker finishes without error."""
        self._inspect_worker = None
        if big:
            lines = [f"• {title} — {n} entries (~{est})" for _, n, est, title in big]
            msg = "Large playlists detected:\n\n" + "\n".join(lines) + "\n\nContinue?"
            ans = QMessageBox.question(
                self, "Confirm large playlist download",
                msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
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
        if self.batch_idx >= self.batch_total:
            self.status_label.setText(
                f"Queue finished: {self.batch_done}/{self.batch_total} completed."
            )
            self.dl_progress.setValue(0)
            self._reset_after_batch()
            return
        url       = self.batch[self.batch_idx]
        idx_label = f"[{self.batch_idx + 1}/{self.batch_total}]"
        self.status_label.setText(f"{idx_label} Starting: {url}")
        self.dl_progress.setValue(0)

        self.worker = DownloadWorker(
            url=url,
            height=self.height,
            container=self.container,
            bitrate=self.bitrate,
            outdir=self.outdir,
            audio_only=self.audio_only,
            idx_label=idx_label,
            clean_tags=self.clean_tags,
            playlist=self._is_playlist_url(url),
            archive_path=getattr(self, "archive_path", None),
            embed_metadata=getattr(self, "embed_metadata", False),
            embed_thumbnail=getattr(self, "embed_thumbnail", False),
        )
        self.worker.progress.connect(self.dl_progress.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self._on_item_ok)
        self.worker.failed.connect(self._on_item_fail)
        self.worker.start()

    def _on_item_ok(self, path: str) -> None:
        renamed_list: list[str] = []
        if isinstance(path, str) and path.startswith("playlist_files:"):
            try:
                playlist_paths = json.loads(path.removeprefix("playlist_files:"))
            except json.JSONDecodeError:
                playlist_paths = []
            for p in playlist_paths:
                new = rename_with_cleanup(p, self.clean_tags)
                if new is not None:
                    renamed_list.append(new.name)
        elif isinstance(path, str) and path.startswith("playlist:"):
            exts = audio_extensions() if self.audio_only else video_extensions()
            for p in discover_new_files(self.outdir, self.batch_start_ts, exts):
                new = rename_with_cleanup(p, self.clean_tags)
                if new is not None:
                    renamed_list.append(new.name)
        else:
            new = rename_with_cleanup(path, self.clean_tags)
            if new is not None:
                renamed_list.append(new.name)
        if self.clean_tags and renamed_list:
            self.status_label.setText(
                f"Cleaned {len(renamed_list)} file(s), e.g. {renamed_list[0]!r}"
            )
        self.batch_idx  += 1
        self.batch_done += 1
        self._kick_next()

    def _on_item_fail(self, msg: str) -> None:
        self.status_label.setText(
            f"[{self.batch_idx + 1}/{self.batch_total}] Error: {msg}"
        )
        self.batch_idx += 1
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

        if hasattr(self, "worker") and self.worker.isRunning():
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
        if not getattr(self, "clean_tags", None):
            return []
        outdir = getattr(self, "outdir", None)
        start_ts = getattr(self, "batch_start_ts", None)
        if not outdir or start_ts is None:
            return []
        exts = audio_extensions() if getattr(self, "audio_only", False) else video_extensions()
        renamed: list[str] = []
        for p in discover_new_files(outdir, start_ts, exts):
            new = rename_with_cleanup(p, self.clean_tags)
            if new is not None:
                renamed.append(new.name)
        return renamed

    def _reset_after_batch(self) -> None:
        self.current_batch.clear()
        self.queue_list.clear()
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.add_queue_btn.setEnabled(True)
        self.url_input.setEnabled(True)
        self._dl_active = False

    # ------------------------------------------------------------------ #
    #  Converter — file list helpers                                       #
    # ------------------------------------------------------------------ #

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

    def _conv_clear_files(self) -> None:
        self._conv_files.clear()
        self.conv_file_list.clear()
        self.conv_status_label.setText("File list cleared.")

    def _conv_browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.conv_dir_input.text()
        )
        if d:
            self.conv_dir_input.setText(d)
            self._save_dir("convert_audio", d)

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

    # ------------------------------------------------------------------ #
    #  Converter — conversion flow                                         #
    # ------------------------------------------------------------------ #

    def _conv_start(self) -> None:
        if not self._conv_files:
            QMessageBox.warning(self, "No files", "Add at least one file to convert.")
            return
        outdir = Path(self.conv_dir_input.text().strip())
        if not outdir.is_dir():
            QMessageBox.warning(self, "Bad folder", f"Folder does not exist: {outdir}")
            return
        self._save_dir("convert_audio", str(outdir))

        self._conv_queue  = list(self._conv_files)
        self._conv_idx    = 0
        self._conv_total  = len(self._conv_queue)
        self._conv_done   = 0

        self.conv_start_btn.setEnabled(False)
        self.conv_cancel_btn.setEnabled(True)
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
            clean_tags = parse_tag_list(self.clean_tags_input.text())

        self.conv_status_label.setText(f"{idx_label} Preparing {src.name}...")
        self.conv_progress.setValue(0)

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
        self._conv_worker.progress.connect(self.conv_progress.setValue)
        self._conv_worker.status.connect(self.conv_status_label.setText)
        self._conv_worker.finished_ok.connect(self._on_conv_ok)
        self._conv_worker.failed.connect(self._on_conv_fail)
        self._conv_worker.start()

    def _on_conv_ok(self, out_path: str) -> None:
        name = Path(out_path).name
        self.conv_status_label.setText(
            f"[{self._conv_idx + 1}/{self._conv_total}] Done → {name}"
        )
        self._conv_idx  += 1
        self._conv_done += 1
        self._conv_kick_next()

    def _on_conv_fail(self, msg: str) -> None:
        self.conv_status_label.setText(
            f"[{self._conv_idx + 1}/{self._conv_total}] Error: {msg}"
        )
        self._conv_idx += 1
        self._conv_kick_next()

    def _conv_cancel(self) -> None:
        if self._conv_worker and self._conv_worker.isRunning():
            self._conv_worker.cancel()
            if not self._conv_worker.wait(3000):
                self._conv_worker.terminate()
                self._conv_worker.wait(1000)
            self.conv_status_label.setText("Cancelled.")
        self._conv_reset()

    def _conv_reset(self) -> None:
        self._conv_files.clear()
        self.conv_file_list.clear()
        self.conv_start_btn.setEnabled(True)
        self.conv_cancel_btn.setEnabled(False)
        self._conv_worker = None

    # ------------------------------------------------------------------ #
    #  Video converter — file list helpers                                #
    # ------------------------------------------------------------------ #

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
            {self.video_conv_file_list.row(item) for item in self.video_conv_file_list.selectedItems()},
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
            self._save_dir("convert_video", d)

    # ------------------------------------------------------------------ #
    #  Video converter — conversion flow                                  #
    # ------------------------------------------------------------------ #

    def _video_conv_start(self) -> None:
        if not self._video_conv_files:
            QMessageBox.warning(self, "No files", "Add at least one video to convert.")
            return
        outdir = Path(self.video_conv_dir_input.text().strip())
        if not outdir.is_dir():
            QMessageBox.warning(self, "Bad folder", f"Folder does not exist: {outdir}")
            return
        self._save_dir("convert_video", str(outdir))

        self._video_conv_queue = list(self._video_conv_files)
        self._video_conv_idx = 0
        self._video_conv_total = len(self._video_conv_queue)
        self._video_conv_done = 0

        self.video_conv_start_btn.setEnabled(False)
        self.video_conv_cancel_btn.setEnabled(True)
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
            clean_tags = parse_tag_list(self.clean_tags_input.text())

        self.video_conv_status_label.setText(f"{idx_label} Preparing {src.name}...")
        self.video_conv_progress.setValue(0)

        self._video_conv_worker = VideoConvertWorker(
            src=src,
            outdir=self.video_conv_dir_input.text().strip(),
            fmt=self.video_conv_fmt_combo.currentText(),
            quality=self.video_conv_quality_combo.currentData(),
            copy_audio=self.video_conv_audio_copy_chk.isChecked(),
            clean_tags=clean_tags,
            idx_label=idx_label,
        )
        self._video_conv_worker.progress.connect(self.video_conv_progress.setValue)
        self._video_conv_worker.status.connect(self.video_conv_status_label.setText)
        self._video_conv_worker.finished_ok.connect(self._on_video_conv_ok)
        self._video_conv_worker.failed.connect(self._on_video_conv_fail)
        self._video_conv_worker.start()

    def _on_video_conv_ok(self, out_path: str) -> None:
        name = Path(out_path).name
        self.video_conv_status_label.setText(
            f"[{self._video_conv_idx + 1}/{self._video_conv_total}] Done -> {name}"
        )
        self._video_conv_idx += 1
        self._video_conv_done += 1
        self._video_conv_kick_next()

    def _on_video_conv_fail(self, msg: str) -> None:
        self.video_conv_status_label.setText(
            f"[{self._video_conv_idx + 1}/{self._video_conv_total}] Error: {msg}"
        )
        self._video_conv_idx += 1
        self._video_conv_kick_next()

    def _video_conv_cancel(self) -> None:
        if self._video_conv_worker and self._video_conv_worker.isRunning():
            self._video_conv_worker.cancel()
            if not self._video_conv_worker.wait(3000):
                self._video_conv_worker.terminate()
                self._video_conv_worker.wait(1000)
            self.video_conv_status_label.setText("Cancelled.")
        self._video_conv_reset()

    def _video_conv_reset(self) -> None:
        self._video_conv_files.clear()
        self.video_conv_file_list.clear()
        self.video_conv_start_btn.setEnabled(True)
        self.video_conv_cancel_btn.setEnabled(False)
        self._video_conv_worker = None
