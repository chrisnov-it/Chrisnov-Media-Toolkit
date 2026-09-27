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
from PySide6.QtGui import QKeySequence, QShortcut
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
from .utils import install_placeholder, open_in_explorer


def _fmt_size(n: int) -> str:
    """Human-readable byte size: whole KB, one decimal MB/GB, exact B."""
    if n > 1e9:
        return f"{n / 1e9:.1f} GB"
    if n > 1e6:
        return f"{n / 1e6:.1f} MB"
    if n > 1e3:
        return f"{n / 1e3:.0f} KB"
    return f"{n} B"


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
        title = QLabel("History")
        title.setStyleSheet("font-weight:600; font-size:10pt;")
        header.addWidget(title)
        self._history_summary = QLabel("")
        self._history_summary.setStyleSheet(
            "color: palette(text); font-size: 8pt; padding-left: 4px;"
        )
        header.addWidget(self._history_summary)
        header.addStretch()
        self._history_remove_btn = QPushButton("Remove")
        self._history_remove_btn.setToolTip(
            "Remove the selected entry from the history (or press Delete)"
        )
        self._history_remove_btn.setEnabled(False)
        self._history_remove_btn.clicked.connect(self._on_history_remove)
        header.addWidget(self._history_remove_btn)
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
        self._history_list.itemSelectionChanged.connect(self._sync_remove_button)
        root.addWidget(self._history_list, 1)

        # Empty-state placeholder — rendered *inside* the list box (P2): the
        # old label sat below the list, so the order was list → legend →
        # message and the empty box itself looked broken. The wording still
        # flips between "no downloads yet" and "no matches" in refresh().
        self._history_empty = install_placeholder(
            self._history_list,
            "No downloads yet.\nPress Start to begin downloading.",
        )

        # Delete removes the selected row (same action as the Remove button;
        # scoped to this list so Delete in the search field keeps deleting
        # text).
        del_sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete),
                           self._history_list)
        del_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        del_sc.activated.connect(self._on_history_remove)

        # Legend
        legend = QLabel("\U0001f4c2 = Open folder   \U0001f501 = Download again")
        legend.setStyleSheet("color: palette(text); font-size: 7pt;")
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(legend)

    # ------------------------------------------------------------------ #
    #  Rendering and actions                                               #
    # ------------------------------------------------------------------ #

    def refresh(self, filter_text: str | None = None,
                filter_type: str | None = None) -> None:
        """Re-populate the history list from the model (old _history_render).

        Called with no arguments by the history_changed signal (a download
        finished) and after Clear All: the current search text and type
        filter are then reused, so a new entry landing no longer silently
        resets what the user had typed or filtered.
        """
        if filter_text is None:
            filter_text = self._history_search.text()
        if filter_type is None:
            filter_type = self._history_filter.currentText()
        self._history_list.clear()
        query = filter_text.lower().strip()
        n_total = len(self._history.entries)
        n_shown = 0
        total_bytes = 0

        for model_index, entry in enumerate(self._history.entries):
            # Filter by type
            if filter_type != "All" and entry.get("type", "").lower() != filter_type.lower():
                continue

            # Search by filename or URL
            if query:
                haystack = (entry.get("filename", "") + " " + entry.get("url", "")).lower()
                if query not in haystack:
                    continue

            # Only visible rows count towards the summary: summing every
            # entry (before the filters) left "(3 items …)" on screen while
            # one filtered row was actually shown.
            n_shown += 1
            total_bytes += entry.get("filesize_bytes", 0)
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
            size_str = _fmt_size(filesize)

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
            # Where this row lives in the *model*: under a search/type filter
            # the visible row number is not the model number, and item.data()
            # hands back a *copy* of the dict, so identity matching cannot
            # recover it (Remove needs the real model index).
            item.setData(Qt.ItemDataRole.UserRole + 1, model_index)
            # Failed entries carry their reason: show it inline (the list
            # word-wraps) and in the tooltip, since the queue row that
            # originally held the error resets with the batch.
            error = (entry.get("error") or "").strip()
            if error and not completed:
                item.setText(f"{display}  —  {error}")
                item.setToolTip(error)
            self._history_list.addItem(item)

        # Update summary — the numbers describe what is on screen, so a
        # filter narrows them too ("1 of 2 items … shown").
        if n_shown == n_total:
            self._history_summary.setText(
                f"({n_total} items, {_fmt_size(total_bytes)} total)"
            )
        else:
            self._history_summary.setText(
                f"({n_shown} of {n_total} items, {_fmt_size(total_bytes)} shown)"
            )
        # Empty-state wording depends on *why* nothing is shown: an empty
        # history says "no downloads yet", a filter that hides every row
        # says "no matches" — never both claims at once.
        if n_total == 0:
            self._history_empty.setText(
                "No downloads yet.\nPress Start to begin downloading."
            )
        else:
            self._history_empty.setText(
                "No matching entries.\nAdjust the search or filter."
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

    def _sync_remove_button(self) -> None:
        """Remove only makes sense with a selected row."""
        self._history_remove_btn.setEnabled(bool(self._history_list.selectedItems()))

    def _on_history_remove(self) -> None:
        """Delete the selected entry (Remove button / Delete key).

        The row carries the entry *and* its model index, so removal works
        from a filtered view too — the visible row number is not the model
        number once a search or type filter is active. Nothing happens when
        the selection is empty or the model already moved on (remove_at is
        bounds-checked).
        """
        item = self._history_list.currentItem()
        if item is None:
            return
        model_index = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(model_index, int):
            return
        if not self._history.remove_at(model_index):
            return
        self.refresh()
        self._sync_remove_button()

    def _on_history_item_action(self, item: QListWidgetItem) -> None:
        """Handle double-click on a history item: Open Folder or Re-download."""
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return

        filepath = entry.get("filepath", "")
        url = entry.get("url", "")

        if filepath and Path(filepath).exists():
            # Open the containing folder — existence-based, not status-based:
            # a failed entry whose file is still on disk (renamed output, a
            # conversion's source, a vanished-then-restored download) opens
            # where the file actually is instead of silently requeueing.
            # For playlist entries, whose filepath is the output directory
            # itself, open that directory directly.
            target = Path(filepath)
            open_in_explorer(str(target if target.is_dir() else target.parent))
            return

        if url.startswith(("http://", "https://")):
            # Re-download (for failed items or when file missing) — MainWindow
            # switches to the Downloader tab and queues the URL there. Only
            # real URLs: conversion entries store a local source path in url
            # (it feeds the search haystack) and must not be queued as a URL.
            self.requeue_requested.emit(url, entry.get("filename", ""))
