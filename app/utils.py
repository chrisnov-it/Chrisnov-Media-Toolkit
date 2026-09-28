"""Small GUI helpers shared across the window tabs."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QListWidget, QWidget

from .theme import _base_font_size

#: Tooltip swapped onto controls while a batch freezes them. Tooltips *do*
#: fire on disabled widgets (verified on native Windows), so this is the one
#: place to answer "why can't I click this?".
BATCH_BUSY_HINT = "Unavailable while a batch is running."

#: Attribute used by set_controls_busy() to remember the tooltip a widget had
#: before the batch took it over (so the original text comes back after).
_SAVED_TIP_ATTR = "_saved_busy_tip"

#: Same idea for the enabled state: some controls are *already* off outside a
#: batch (bitrate in video mode, the cleanup-tag field with Clean title off).
#: Unfreezing must restore what was there, not blindly re-enable everything.
_SAVED_ENABLED_ATTR = "_saved_busy_enabled"


def clip_text(text: str, max_len: int) -> str:
    """Clip *text* to *max_len* characters, marking the cut with an ellipsis.

    Queue rows used raw slices (``identifier[:20]``), which silently cut
    identifiers mid-word with no hint that anything was hidden. Returns
    *text* unchanged when it already fits.
    """
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    return text[: max_len - 1] + "…"


def set_controls_busy(controls: Iterable[QWidget], busy: bool) -> None:
    """Freeze/unfreeze *controls* for a batch, with an explanatory tooltip.

    While busy each control is disabled and its tooltip is replaced by
    BATCH_BUSY_HINT; on unfreeze the original tooltip **and** the original
    enabled state come back (both kept as Python attributes, so callers can
    toggle freely). Restoring the state — instead of forcing enabled — is
    what lets the Downloader freeze settings that are legitimately off
    outside a batch (bitrate in video mode, the cleanup-tag field with
    Clean title off) without switching them on behind the user's back.
    """
    for widget in controls:
        if busy:
            if not hasattr(widget, _SAVED_TIP_ATTR):
                setattr(widget, _SAVED_TIP_ATTR, widget.toolTip())
            if not hasattr(widget, _SAVED_ENABLED_ATTR):
                setattr(widget, _SAVED_ENABLED_ATTR, widget.isEnabled())
            widget.setToolTip(BATCH_BUSY_HINT)
            widget.setEnabled(False)
        else:
            saved = getattr(widget, _SAVED_TIP_ATTR, None)
            if saved is not None:
                widget.setToolTip(saved)
                delattr(widget, _SAVED_TIP_ATTR)
            saved_enabled = getattr(widget, _SAVED_ENABLED_ATTR, None)
            if saved_enabled is not None:
                widget.setEnabled(saved_enabled)
                delattr(widget, _SAVED_ENABLED_ATTR)


class ListPlaceholder(QLabel):
    """Centred empty-state hint rendered *inside* a list widget.

    The empty states used to be plain labels stacked **below** the list —
    the queue box itself looked broken/empty, and in History the order was
    list → legend → message. Parenting the label to the list's viewport
    puts the hint where the missing rows would be; the model signals keep
    it in sync (visible iff the list has no rows) and the viewport resize
    keeps it centred when the window grows.
    """

    def __init__(self, list_widget: QListWidget, text: str) -> None:
        super().__init__(text, list_widget.viewport())
        self._list = list_widget
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(
            "color: palette(text); font-size: "
            f"{_base_font_size()}; padding: 24px;"
        )
        # Clicks/selection must reach the list (and its scrollbar), never me.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        model = list_widget.model()
        model.rowsInserted.connect(self.sync)
        model.rowsRemoved.connect(self.sync)
        model.modelReset.connect(self.sync)
        model.layoutChanged.connect(self.sync)
        list_widget.viewport().installEventFilter(self)
        self.sync()

    def sync(self, *_args) -> None:
        """Re-centre the label and show it iff the list is empty."""
        self.setGeometry(self._list.viewport().rect())
        self.setVisible(self._list.count() == 0)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.sync()
        return False


def install_placeholder(list_widget: QListWidget, text: str) -> ListPlaceholder:
    """Give *list_widget* an in-list empty-state hint (see ListPlaceholder)."""
    return ListPlaceholder(list_widget, text)


def open_result(path: str | Path) -> bool:
    """Open a finished result: files with the default app, folders in the
    file manager.

    The status lines only *reported* the last result ("Done → name",
    "Cleaned N file(s)") with no way to act on it — this is the action the
    "Open last result" buttons call. Returns False when there is nothing to
    open (missing/empty path) so the caller can explain instead of silently
    launching nothing.
    """
    if not path:
        return False
    target = Path(path)
    if not target.exists():
        return False
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))))


def open_in_explorer(path: str) -> None:
    """Open *path* in the system file manager (only when it is a directory)."""
    if path and Path(path).is_dir():
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def scan_media_files(
    folder: Path,
    extensions: set[str],
    *,
    max_entries: int = 100_000,
    max_files: int = 10_000,
) -> tuple[list[Path], bool]:
    """Collect media files under *folder* — bounded, safe for the GUI thread.

    The converter tabs used ``folder.rglob("*")`` + ``is_file()`` +
    ``sorted()``, which walked, stat'ed and sorted the *entire* tree inside
    the window's thread: pointing at a huge or a network folder froze the UI
    for as long as the walk took. This walks with ``os.scandir`` (each entry
    already carries its type, so no extra stat per file), skips hidden
    entries such as ``.git``, never follows directory symlinks, and stops
    after *max_entries* entries or *max_files* matches.

    Returns ``(files, truncated)`` with the files sorted by path, matching
    the old ordering.
    """
    wanted = {e.lower().lstrip(".") for e in extensions if e.strip()}
    found: list[Path] = []
    truncated = False
    seen = 0
    stack = [Path(folder)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    seen += 1
                    if seen > max_entries or len(found) >= max_files:
                        truncated = True
                        stack.clear()
                        break
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        if not entry.is_file():
                            continue
                    except OSError:
                        continue  # entry vanished or is unreadable
                    suffix = Path(entry.name).suffix[1:].lower()
                    if suffix in wanted:
                        found.append(Path(entry.path))
        except OSError:
            continue  # folder itself is unreadable (permissions, unplugged...)
    return sorted(found), truncated
