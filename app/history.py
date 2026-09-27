"""Download history model — versioned JSON persistence, newest first.

Qt-free on purpose so it can be unit-tested without a QApplication; the
History tab and Download tab only read/append entries and re-render.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from pathlib import Path

from .constants import MAX_HISTORY_ENTRIES

VERSION = 1

log = logging.getLogger(__name__)


class DownloadHistory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[dict] = []

    def load(self) -> None:
        """Load entries from JSON.

        A truncated write, a cloud-sync conflict or a hand-edit must never
        lose the whole history: when the main file is unusable the previous
        atomic-save copy (.bak) is tried before falling back to [].
        """
        raw_items = self._read_items(self.path)
        if raw_items is None:
            backup = self.path.with_name(self.path.name + ".bak")
            raw_items = self._read_items(backup)
        if raw_items is None:
            self.entries = []
            return
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
        # Cap on load too: append() only caps what it adds, so a hand-edited
        # or legacy file could otherwise load unbounded and stay that way.
        if len(self.entries) > MAX_HISTORY_ENTRIES:
            self.entries = self.entries[:MAX_HISTORY_ENTRIES]

    def _read_items(self, path: Path) -> list | None:
        """Parse the "items" list out of one history file.

        Returns None when the file is missing, unreadable, not JSON, or has a
        schema this version doesn't understand — the caller then tries the
        next source instead of silently discarding the data.
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
            return None
        if (
            isinstance(data, dict)
            and data.get("version") == VERSION
            and isinstance(data.get("items"), list)
        ):
            return data["items"]
        return None

    def save(self) -> bool:
        """Atomically replace the history file, keeping the old copy as .bak.

        The payload is written to a sibling .tmp first and moved into place
        with os.replace(), so a crash or power loss mid-write can only lose
        the newest entry — never truncate the file the next load() reads.
        Returns False (and logs) when the write failed; append()/clear()
        fire-and-forget that warning (the in-memory history keeps working),
        while callers that need to know — tests, explicit saves — get the bool.
        """
        tmp = self.path.with_name(self.path.name + ".tmp")
        backup = self.path.with_name(self.path.name + ".bak")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(
                    {"version": VERSION, "items": self.entries},
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            if self.path.exists():
                os.replace(self.path, backup)
            os.replace(tmp, self.path)
            return True
        except OSError as exc:
            log.warning("Could not save download history to %s: %s", self.path, exc)
            with contextlib.suppress(OSError):
                tmp.unlink()
            return False

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
