"""Small GUI helpers shared across the window tabs."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


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
