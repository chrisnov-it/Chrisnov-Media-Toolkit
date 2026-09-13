"""Download history tab — list, search/filter, and re-queue actions.

Extracted from the MainWindow monolith (window.py) with behavior kept 1:1.
The tab owns only presentation; entries live in the shared DownloadHistory
model, and re-queue requests are emitted as a signal that MainWindow routes
to the Downloader tab.
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .history import DownloadHistory
from .utils import open_in_explorer


class HistoryTab(QWidget):
    """Tab 4 — download history list."""

    #: (url, filename) — emitted when a failed/missing entry is re-queued.
    requeue_requested = Signal(str, str)

    def __init__(self, history: DownloadHistory,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history = history
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(5)

        # Header
        header = QHBoxLayout()
        title = QLabel("Download History")
        title.setStyleSheet("font-weight:600; font-size:10pt;")
        header.addWidget(title)
        self._history_summary = QLabel("")
        self._history_summary.setStyleSheet(
            "color: palette(text); font-size: 8pt; padding-left: 4px;"
        )
        header.addWidget(self._history_summary)
        header.addStretch()
        self._history_clear_btn = QPushButton("Clear All")
        self._history_clear_btn.clicked.connect(self._on_history_clear)
        header.addWidget(self._history_clear_btn)
        root.addLayout(header)

        # Search / filter row
        filter_row = QHBoxLayout()
        self._history_search = QLineEdit()
        self._history_search.setPlaceholderText("Search by filename or URL...")
        self._history_search.textChanged.connect(self._on_history_search_changed)
        filter_row.addWidget(self._history_search, 1)
        self._history_filter = QComboBox()
        self._history_filter.addItems(["All", "Audio", "Video", "Playlist"])
        self._history_filter.currentTextChanged.connect(self._on_history_search_changed)
        filter_row.addWidget(self._history_filter)
        root.addLayout(filter_row)

        # Table-like list widget
        self._history_list = QListWidget()
        self._history_list.setMinimumHeight(150)
        self._history_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._history_list.setWordWrap(True)
        self._history_list.itemDoubleClicked.connect(self._on_history_item_action)
        root.addWidget(self._history_list, 1)

        # Legend
        legend = QLabel("\U0001f4c2 = Open folder   \U0001f501 = Download again")
        legend.setStyleSheet("color: palette(text); font-size: 7pt;")
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(legend)

        # Empty state placeholder
        self._history_empty = QLabel("No downloads yet.\nPress Start to begin downloading.")
        self._history_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._history_empty.setStyleSheet(
            "color: palette(text); font-size: 9pt; padding: 40px;"
        )
        root.addWidget(self._history_empty)

    # ------------------------------------------------------------------ #
    #  Rendering and actions                                               #
    # ------------------------------------------------------------------ #

    def refresh(self, filter_text: str = "", filter_type: str = "All") -> None:
        """Re-populate the history list from the model (old _history_render)."""
        self._history_list.clear()
        query = filter_text.lower().strip()
        n_total = len(self._history.entries)
        n_shown = 0
        total_bytes = 0

        for entry in self._history.entries:
            total_bytes += entry.get("filesize_bytes", 0)

            # Filter by type
            if filter_type != "All" and entry.get("type", "").lower() != filter_type.lower():
                continue

            # Search by filename or URL
            if query:
                haystack = (entry.get("filename", "") + " " + entry.get("url", "")).lower()
                if query not in haystack:
                    continue

            n_shown += 1
            filename = entry.get("filename", "?")
            filesize = entry.get("filesize_bytes", 0)
            status = entry.get("status", "?")
            ts = entry.get("timestamp", 0)

            # Relative time
            delta = int(time.time()) - int(ts)
            if delta < 60:
                rel = "just now"
            elif delta < 3600:
                rel = f"{delta // 60}m ago"
            elif delta < 86400:
                rel = f"{delta // 3600}h ago"
            else:
                rel = f"{delta // 86400}d ago"

            # Human-readable size
            if filesize > 1e9:
                size_str = f"{filesize / 1e9:.1f} GB"
            elif filesize > 1e6:
                size_str = f"{filesize / 1e6:.1f} MB"
            elif filesize > 1e3:
                size_str = f"{filesize / 1e3:.0f} KB"
            else:
                size_str = f"{filesize} B"

            # Status color
            completed = status == "completed"
            type_icon = {"audio": "\U0001f3b5", "video": "\U0001f3ac", "playlist": "\U0001f4cb"}
            icon = type_icon.get(entry.get("type", ""), "\U0001f4c1")

            display = (
                f"{icon}  {filename}  |  {size_str:>8s}  |  {rel:>10s}  |  "
                f"{'✅' if completed else '❌'} {status}"
            )
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._history_list.addItem(item)

        # Update summary
        size_total = ""
        if total_bytes > 1e9:
            size_total = f"{total_bytes / 1e9:.1f} GB"
        elif total_bytes > 1e6:
            size_total = f"{total_bytes / 1e6:.1f} MB"
        self._history_summary.setText(
            f"({n_total} items, {size_total} total)" if size_total else f"({n_total} items)"
        )
        self._history_empty.setVisible(n_shown == 0)

    def _on_history_search_changed(self) -> None:
        """Re-render history when search text or filter changes."""
        self.refresh(
            filter_text=self._history_search.text(),
            filter_type=self._history_filter.currentText(),
        )

    def _on_history_clear(self) -> None:
        """Clear all history after confirmation."""
        if not self._history.entries:
            return
        ans = QMessageBox.question(
            self, "Clear history",
            f"Delete all {len(self._history.entries)} history entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._history.clear()
        self.refresh()

    def _on_history_item_action(self, item: QListWidgetItem) -> None:
        """Handle double-click on a history item: Open Folder or Re-download."""
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return

        filepath = entry.get("filepath", "")
        url = entry.get("url", "")
        status = entry.get("status", "")

        if filepath and Path(filepath).exists() and status == "completed":
            # Open the containing folder — for playlist entries, whose filepath
            # is the output directory itself, open that directory directly.
            target = Path(filepath)
            open_in_explorer(str(target if target.is_dir() else target.parent))
            return

        if url:
            # Re-download (for failed items or when file missing) — MainWindow
            # switches to the Downloader tab and queues the URL there.
            self.requeue_requested.emit(url, entry.get("filename", ""))
