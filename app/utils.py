"""Small GUI helpers shared across the window tabs."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

#: Tooltip swapped onto controls while a batch freezes them. Tooltips *do*
#: fire on disabled widgets (verified on native Windows), so this is the one
#: place to answer "why can't I click this?".
BATCH_BUSY_HINT = "Unavailable while a batch is running."

#: Attribute used by set_controls_busy() to remember the tooltip a widget had
#: before the batch took it over (so the original text comes back after).
_SAVED_TIP_ATTR = "_saved_busy_tip"


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
    BATCH_BUSY_HINT; the original tooltip is restored on unfreeze (kept on
    the widget as a Python attribute, so callers can toggle freely).
    """
    for widget in controls:
        if busy:
            if not hasattr(widget, _SAVED_TIP_ATTR):
                setattr(widget, _SAVED_TIP_ATTR, widget.toolTip())
            widget.setToolTip(BATCH_BUSY_HINT)
        else:
            saved = getattr(widget, _SAVED_TIP_ATTR, None)
            if saved is not None:
                widget.setToolTip(saved)
                delattr(widget, _SAVED_TIP_ATTR)
        widget.setEnabled(not busy)


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
