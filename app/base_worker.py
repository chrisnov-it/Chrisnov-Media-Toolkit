"""Base worker class with cancellation support."""

from __future__ import annotations

from PySide6.QtCore import QThread


class CancellableWorker(QThread):
    """QThread subclass with a standard cancellation pattern.

    Subclasses should:
    1. Call `super().__init__()` in their `__init__`
    2. Check `self._cancelled` periodically in long-running operations
       and abort cleanly when it flips
    3. Override `cancel()` (calling `super().cancel()` first) when they own
       a child process that must be terminated too — the converter workers
       do this for their FFmpeg child

    Cancellation is *requested* by the owning tab, not by the worker itself:
    the GUI thread calls `worker.cancel()` and the worker winds down.
    """

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. Sets the internal flag; subclasses should
        also terminate any child processes here if applicable."""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        """Read-only access to the cancellation flag."""
        return self._cancelled