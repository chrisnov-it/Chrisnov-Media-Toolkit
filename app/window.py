"""GUI window for Chrisnov YT Downloader."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFileDialog, QMessageBox, QProgressBar, QCheckBox,
    QListWidget, QListWidgetItem
)
from yt_dlp import YoutubeDL

from .constants import (
    RES_PRESETS, VIDEO_CONTAINERS, AUDIO_CONTAINERS, AUDIO_BITRATES,
    PLAYLIST_CONFIRM_THRESHOLD,
)
from .cleaner import (
    DEFAULT_CLEAN_TAGS, parse_tag_list, clean_title, rename_with_cleanup,
    discover_new_files,
)
from .worker import DownloadWorker, audio_extensions, video_extensions


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chrisnov YT Downloader")
        self.setMinimumWidth(640)
        self.setAcceptDrops(True)
        self.current_batch: list[str] = []
        # Build UI
        self._build_ui()

    # ---------------- Drag-and-drop ----------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        md = event.mimeData()
        if md.hasText() or md.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        md = event.mimeData()
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

    @staticmethod
    def _is_playlist_url(url: str) -> bool:
        if "list=" not in url:
            return False
        return "youtube.com" in url or "youtu.be" in url

    # ---------------- UI construction ----------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # URL
        root.addWidget(QLabel("Video URL (or drag a URL/text file here to add to queue):"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.returnPressed.connect(self._add_url_from_input)
        root.addWidget(self.url_input)

        add_row = QHBoxLayout()
        self.add_queue_btn = QPushButton("Add to queue")
        self.add_queue_btn.clicked.connect(self._add_url_from_input)
        add_row.addWidget(self.add_queue_btn)
        add_row.addStretch()
        root.addLayout(add_row)

        # Queue
        root.addWidget(QLabel("Download queue:"))
        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(110)
        root.addWidget(self.queue_list)

        qrow = QHBoxLayout()
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QPushButton("Clear queue")
        self.clear_btn.clicked.connect(self._clear_queue)
        qrow.addWidget(self.remove_btn)
        qrow.addWidget(self.clear_btn)
        qrow.addStretch()
        root.addLayout(qrow)

        # Audio-only
        self.audio_only_chk = QCheckBox("Audio only (extract soundtrack)")
        self.audio_only_chk.toggled.connect(self._on_audio_toggled)
        root.addWidget(self.audio_only_chk)

        # Skip duplicates
        self.skip_dup_chk = QCheckBox("Skip already-downloaded (download archive)")
        self.skip_dup_chk.setChecked(True)
        root.addWidget(self.skip_dup_chk)

        # Title cleanup
        self.clean_chk = QCheckBox("Clean title (strip: Official Music Video, etc.)")
        self.clean_chk.setChecked(True)
        self.clean_chk.toggled.connect(self._on_clean_toggled)
        root.addWidget(self.clean_chk)

        self.clean_tags_input = QLineEdit(", ".join(DEFAULT_CLEAN_TAGS))
        self.clean_tags_input.setClearButtonEnabled(True)
        root.addWidget(self.clean_tags_input)

        # Resolution + container + bitrate
        row1 = QHBoxLayout()
        self.res_label = QLabel("Resolution:")
        row1.addWidget(self.res_label)
        self.res_combo = QComboBox()
        for label, _ in RES_PRESETS:
            self.res_combo.addItem(label)
        self.res_combo.setCurrentIndex(2)
        row1.addWidget(self.res_combo, 1)

        self.container_label = QLabel("Container:")
        row1.addWidget(self.container_label)
        self.container_combo = QComboBox()
        self.container_combo.addItems(VIDEO_CONTAINERS)
        self.container_combo.setCurrentText("mp4")
        row1.addWidget(self.container_combo, 1)

        self.bitrate_label = QLabel("Bitrate (kbps):")
        row1.addWidget(self.bitrate_label)
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(AUDIO_BITRATES)
        self.bitrate_combo.setCurrentText("192")
        self.bitrate_combo.setEnabled(False)
        self.bitrate_label.setEnabled(False)
        row1.addWidget(self.bitrate_combo, 1)
        root.addLayout(row1)

        # Output
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Output folder:"))
        self.dir_input = QLineEdit(str(Path.home() / "Videos"))
        row2.addWidget(self.dir_input, 1)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse)
        row2.addWidget(self.browse_btn)
        root.addLayout(row2)

        # Buttons
        row3 = QHBoxLayout()
        self.download_btn = QPushButton("Start (current OR queue)")
        self.download_btn.clicked.connect(self._start_download)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        row3.addWidget(self.download_btn)
        row3.addWidget(self.cancel_btn)
        root.addLayout(row3)

        # Progress + status
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

    def _add_url_from_input(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Bad URL", "URL must start with http:// or https://")
            return
        self._add_url(url)
        self.url_input.clear()
        n = len(self.current_batch)
        self.status_label.setText(f"Queue: {n} URL(s). Press Start to download all.")

    def _remove_selected(self) -> None:
        for item in self.queue_list.selectedItems():
            row = self.queue_list.row(item)
            if 0 <= row < len(self.current_batch):
                self.current_batch.pop(row)
            self.queue_list.takeItem(row)
        self.status_label.setText(f"Queue: {len(self.current_batch)} URL(s).")

    def _clear_queue(self) -> None:
        self.current_batch.clear()
        self.queue_list.clear()
        self.status_label.setText("Queue cleared.")

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select output folder", self.dir_input.text())
        if d:
            self.dir_input.setText(d)

    def _on_audio_toggled(self, checked: bool) -> None:
        self.container_combo.clear()
        if checked:
            self.container_combo.addItems(AUDIO_CONTAINERS)
            self.container_combo.setCurrentText("mp3")
            self.res_combo.setEnabled(False)
            self.res_label.setEnabled(False)
            self.bitrate_combo.setEnabled(True)
            self.bitrate_label.setEnabled(True)
        else:
            self.container_combo.addItems(VIDEO_CONTAINERS)
            self.container_combo.setCurrentText("mp4")
            self.res_combo.setEnabled(True)
            self.res_label.setEnabled(True)
            self.bitrate_combo.setEnabled(False)
            self.bitrate_label.setEnabled(False)

    def _on_clean_toggled(self, checked: bool) -> None:
        self.clean_tags_input.setEnabled(checked)

    # ---------------- Download flow ----------------

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

        self.batch = list(self.current_batch)
        self.batch_idx = 0
        self.batch_total = len(self.batch)
        self.outdir = outdir
        self.audio_only = self.audio_only_chk.isChecked()
        self.height = RES_PRESETS[self.res_combo.currentIndex()][1]
        self.container = self.container_combo.currentText()
        self.bitrate = int(self.bitrate_combo.currentText())
        self.clean_tags = (
            parse_tag_list(self.clean_tags_input.text())
            if self.clean_chk.isChecked() else None
        )
        if self.skip_dup_chk.isChecked():
            archive_dir = Path.home() / ".config" / "chrisnov-yt-downloader"
            archive_dir.mkdir(parents=True, exist_ok=True)
            suffix = "_audio" if self.audio_only else "_video"
            self.archive_path = str(archive_dir / f"archive{suffix}.txt")
            self.status_label.setText(
                f"Archive: {self.archive_path} — already-downloaded entries will be skipped."
            )
        else:
            self.archive_path = None
        self.batch_start_ts = time.time()

        # Force-read the clean setting into self.clean_chk so the runtime
        # helper sees the latest checkbox state.
        if self.clean_chk.isChecked() and not self.clean_tags:
            QMessageBox.warning(
                self, "No cleanup tags",
                "Clean title is on but no tags are listed. Returning.",
            )
            return

        if not self._confirm_playlists():
            return

        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.add_queue_btn.setEnabled(False)
        self.url_input.setEnabled(False)
        self._kick_next()

    def _confirm_playlists(self) -> bool:
        playlist_urls = [u for u in self.batch if self._is_playlist_url(u)]
        if not playlist_urls:
            return True
        self.status_label.setText(
            f"Inspecting {len(playlist_urls)} playlist URL(s)..."
        )
        dry_opts = {
            "quiet": True, "no_warnings": True,
            "skip_download": True, "extract_flat": True,
        }
        big: list[tuple[str, int, str, str]] = []
        for p_url in playlist_urls:
            try:
                with YoutubeDL(dry_opts) as ydl:
                    info = ydl.extract_info(p_url, download=False)
            except Exception as e:
                QMessageBox.warning(self, "Playlist error", f"{p_url}\n\n{e}")
                return False
            entries = (info or {}).get("entries") or []
            n = info.get("playlist_count") or len(entries)
            if n >= PLAYLIST_CONFIRM_THRESHOLD:
                per_mb = 3 if self.audio_only else 15
                est_mb = n * per_mb
                est_str = f"{est_mb/1000:.1f} GB" if est_mb > 500 else f"{est_mb} MB"
                big.append((p_url, n, est_str, info.get("title", "?")))
        if big:
            lines = [f"• {title} — {n} entries (~{est})" for _, n, est, title in big]
            msg = ("Large playlists detected:\n\n" + "\n".join(lines) + "\n\nContinue?")
            ans = QMessageBox.question(
                self, "Confirm large playlist download",
                msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return False
        return True

    def _kick_next(self) -> None:
        if self.batch_idx >= self.batch_total:
            self.status_label.setText(
                f"Queue finished: {self.batch_done}/{self.batch_total} completed."
            )
            self.progress.setValue(0)
            self._reset_after_batch()
            return
        url = self.batch[self.batch_idx]
        idx = self.batch_idx + 1
        idx_label = f"[{idx}/{self.batch_total}]"
        self.status_label.setText(f"{idx_label} Starting: {url}")
        self.progress.setValue(0)

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
        )
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self._on_item_ok)
        self.worker.failed.connect(self._on_item_fail)
        self.worker.start()

    def _on_item_ok(self, path: str) -> None:
        renamed_list: list[str] = []
        if isinstance(path, str) and path.startswith("playlist:"):
            # Playlist finished: discover files newer than batch_start_ts
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
        self.batch_idx += 1
        self.batch_done = getattr(self, "batch_done", 0) + 1
        self._kick_next()

    def _on_item_fail(self, msg: str) -> None:
        idx = self.batch_idx + 1
        self.status_label.setText(f"[{idx}/{self.batch_total}] Error: {msg}")
        self.batch_idx += 1
        self._kick_next()

    def _cancel(self) -> None:
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.terminate()
            self.status_label.setText("Cancelled.")
        self._reset_after_batch()

    def _reset_after_batch(self) -> None:
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.add_queue_btn.setEnabled(True)
        self.url_input.setEnabled(True)
