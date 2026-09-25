"""Download history model — versioned JSON persistence, newest first.

Qt-free on purpose so it can be unit-tested without a QApplication; the
History tab and Download tab only read/append entries and re-render.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .constants import MAX_HISTORY_ENTRIES

VERSION = 1


class DownloadHistory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[dict] = []

    def load(self) -> None:
        """Load entries from JSON; missing/corrupt/wrong-version resets to []."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.entries = []
            return
        if (
            isinstance(data, dict)
            and data.get("version") == VERSION
            and isinstance(data.get("items"), list)
        ):
            raw_items = data["items"]
        else:
            raw_items = []
        # Only dicts are entries: a truncated write, a cloud-sync conflict or a
        # hand-edited file can leave scalars in the list, and the History tab
        # calls .get() on every entry (rendering must never crash the app).
        self.entries = [e for e in raw_items if isinstance(e, dict)]
        # Legacy entries stored the raw worker payload (e.g.
        # "playlist_files:[...]") as the filename — replace it with a
        # readable label. Numeric fields are coerced too: the History tab
        # sums filesize_bytes and int()-casts timestamp, so a string there
        # would raise TypeError mid-render.
        for entry in self.entries:
            fn = entry.get("filename")
            if isinstance(fn, str) and fn.startswith(("playlist_files:", "playlist:")):
                entry["filename"] = "Playlist"
            if "filesize_bytes" in entry and not isinstance(entry["filesize_bytes"], int):
                entry["filesize_bytes"] = 0
            if "timestamp" in entry and not isinstance(entry["timestamp"], int):
                entry["timestamp"] = 0

    def save(self) -> None:
        """Write entries to JSON, creating the parent dir. Best-effort."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {"version": VERSION, "items": self.entries},
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def append(self, *, url: str, filepath: str, filename: str, filesize: int,
               type_: str, container: str, audio_only: bool, status: str,
               error: str | None = None) -> None:
        """Insert a record at the front, cap the list, and persist."""
        entry: dict = {
            "url": url,
            "filepath": filepath,
            "filename": filename,
            "filesize_bytes": filesize,
            "type": type_,
            "container": container,
            "audio_only": audio_only,
            "timestamp": int(time.time()),
            "status": status,
        }
        if error:
            entry["error"] = error
        self.entries.insert(0, entry)
        # Keep the JSON lightweight; only the most recent entries survive.
        if len(self.entries) > MAX_HISTORY_ENTRIES:
            self.entries = self.entries[:MAX_HISTORY_ENTRIES]
        self.save()

    def clear(self) -> None:
        """Remove all entries and persist the empty list."""
        self.entries.clear()
        self.save()
