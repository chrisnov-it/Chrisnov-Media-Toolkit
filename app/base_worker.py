"""Base worker class with cancellation support."""

from __future__ import annotations

from PySide6.QtCore import QThread


class CancellableWorker(QThread):
    """QThread subclass with a standard cancellation pattern.

    Subclasses should:
    1. Call `super().__init__()` in their `__init__`
    2. Check `self._cancelled` periodically in long-running operations
    3. Call `self.cancel()` to request cancellation (sets flag + optional process termination)
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