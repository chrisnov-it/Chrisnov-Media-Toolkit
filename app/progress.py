"""Conversion progress helpers — ETA estimation and formatting.

The converter workers (app/converter_worker.py) already emit real progress:
ffmpeg's ``-progress pipe:1`` ``out_time_ms`` is mapped against the ffprobe
duration in app/ffmpeg_utils.py, throttled to ~5 Hz. What the UI lacked was
a remaining-time estimate, so the QProgressBar only showed a bare percent.

EtaEstimator fills that gap from the GUI side without touching the workers:
it extrapolates wall-clock time over the worker's known progress range
(single-pass 10-90, EBU R128 two-pass 5-90, video 10-90). No new signals,
no protocol change — the tabs just wrap their existing setValue call.
"""

from __future__ import annotations

import time
from collections.abc import Callable


def format_eta(seconds: float | None) -> str:
    """Format a remaining-time estimate for display in the progress bar.

    Returns "--:--" when the estimate is unknown (None, NaN, or negative).
    """
    if seconds is None or seconds != seconds or seconds < 0:
        return "--:--"
    total = round(seconds)
    if total >= 3600:
        return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    return f"{total // 60:02d}:{total % 60:02d}"


class EtaEstimator:
    """Wall-clock ETA estimator over a worker progress range.

    Args:
        clock: time source (time.monotonic by default); injectable for tests.
    """

    #: Minimum file fraction before an ETA is reported — avoids absurd
    #: flashes like "ETA 99:99" from the first one or two progress emits.
    MIN_FRAC = 0.03
    #: Minimum wall-clock seconds since reset before reporting.
    MIN_ELAPSED = 1.5
    #: A progress drop larger than this restarts the estimate (covers the
    #: video worker's AAC/Opus retry, which re-runs ffmpeg 10-90).
    RETRY_DROP = 5

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._floor = 10
        self._ceiling = 90
        self._start: float | None = None
        self._last_pct: int | None = None

    def reset(self, floor: int = 10, ceiling: int = 90) -> None:
        """Start estimating a new file whose progress spans floor-ceiling."""
        self._floor = floor
        self._ceiling = ceiling
        self._start = self._clock()
        self._last_pct = None

    def update(self, pct: int) -> str | None:
        """Feed a worker progress value; return formatted ETA or None.

        Returns None while the estimate is not yet meaningful (start of
        file, EBU loudness-scan phase, retry restart, or completion).
        """
        if self._start is None:
            return None
        if self._last_pct is not None and pct < self._last_pct - self.RETRY_DROP:
            # Retry / restart: rebase the clock, same range.
            self._start = self._clock()
            self._last_pct = None
            return None
        self._last_pct = pct

        span = self._ceiling - self._floor
        if span <= 0:
            return None
        frac = (pct - self._floor) / span
        if frac < self.MIN_FRAC or frac >= 1.0:
            return None
        elapsed = self._clock() - self._start
        if elapsed < self.MIN_ELAPSED:
            return None
        remaining = elapsed * (1.0 - frac) / frac
        return format_eta(remaining)
