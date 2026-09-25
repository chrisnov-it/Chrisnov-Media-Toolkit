"""yt-dlp release check for the About dialog — off the GUI thread.

The About dialog used to call ``urllib.request.urlopen()`` straight from the
GUI thread, which froze the dialog for the whole request (up to the timeout),
and it reported "update available" whenever the installed build merely
*differed* from PyPI's latest — so a self-built or nightly yt-dlp was told to
"update" downwards.

This module keeps the request in a worker thread and compares versions
numerically. The comparison helpers are pure functions (unit-tested in
tests/test_update_check.py); the worker only adds the QThread plumbing.
"""

from __future__ import annotations

import json
import re
import urllib.request

from PySide6.QtCore import Signal

from .base_worker import CancellableWorker

PYPI_YTDLP_URL = "https://pypi.org/pypi/yt-dlp/json"
_TIMEOUT_SECONDS = 3


def version_key(version: str) -> tuple[int, ...]:
    """Return a numeric sort key for a release string.

    Only the leading numeric segments count: "2026.8.19" -> (2026, 8, 19),
    "2026.8.19.dev0" -> (2026, 8, 19), "v1.2" -> (1, 2). Returns ``()`` for
    anything without a leading number ("n/a", "", "unknown") so callers can
    skip the comparison instead of guessing.
    """
    key: list[int] = []
    for segment in version.strip().lstrip("vV").split("."):
        match = re.match(r"(\d+)", segment)
        if not match:
            break
        key.append(int(match.group(1)))
    return tuple(key)


def is_newer_version(latest: str, current: str) -> bool:
    """True only when *latest* is strictly newer than *current*.

    Unparsable input returns False: never advertise an "update" we cannot
    actually prove is newer (that is how the old ``!=`` check suggested
    downgrades).
    """
    latest_key = version_key(latest)
    current_key = version_key(current)
    if not latest_key or not current_key:
        return False
    return latest_key > current_key


class UpdateCheckWorker(CancellableWorker):
    """Ask PyPI for the latest yt-dlp version, off the GUI thread.

    Emits:
        update_available(str) — the newer version, and only when it really is
            newer; nothing is emitted on equal/older versions or on any
            network/parsing failure (this is a best-effort nicety, never an
            error path the caller has to handle).
    """

    update_available = Signal(str)

    def __init__(self, current_version: str) -> None:
        super().__init__()
        self.current_version = current_version

    def run(self) -> None:
        try:
            # Constant https URL — no user input reaches this call.
            with urllib.request.urlopen(
                PYPI_YTDLP_URL, timeout=_TIMEOUT_SECONDS
            ) as resp:
                latest = json.loads(resp.read())["info"]["version"]
        except (OSError, ValueError, KeyError, TypeError):
            # Offline, proxy, or an unexpected payload: stay silent.
            return
        if self._cancelled:
            return
        latest = str(latest)
        if is_newer_version(latest, self.current_version):
            self.update_available.emit(latest)
