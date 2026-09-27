"""Worker thread lifetime tracking, shared by every tab.

Workers are parentless QThreads owned by Python: the moment the last
reference disappears, Shiboken deletes the C++ object. Completion handlers
(finished_ok/failed/result/done) fire *inside* run() — before the thread
has exited — so dropping the last reference there (``self.worker = None``,
or overwriting the attribute with the next worker in _kick_next) could
destroy a QThread that was still winding down ("QThread: Destroyed while
thread is still running").

Every worker is therefore pinned in the tracked set from creation, which
makes those attribute writes unconditionally safe, and
finished → deleteLater → destroyed frees it right after the GUI event
loop has processed the deferred delete (i.e. after the thread is done).
"""

from __future__ import annotations

from PySide6.QtCore import QThread


class WorkerTracker:
    """Pins workers until their deferred delete has actually run."""

    def __init__(self) -> None:
        self._tracked: set[QThread] = set()

    def track(self, worker: QThread) -> None:
        if worker in self._tracked:
            return
        self._tracked.add(worker)
        worker.finished.connect(worker.deleteLater)
        # *_ absorbs destroyed()'s optional QObject argument; the keyword-only
        # w stays bound to the tracked worker (positional bind would clobber
        # it and break the identity-based set discard).
        worker.destroyed.connect(lambda *_, w=worker: self._tracked.discard(w))

    def running(self) -> list[QThread]:
        """Workers still executing run() — the shutdown poll in MainWindow
        waits on these before letting the last window close."""
        return [w for w in self._tracked if w.isRunning()]
